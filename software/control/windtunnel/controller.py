import hashlib
import json
import threading
import time
from copy import deepcopy
from uuid import uuid4

from .security import deny
from .simulator import SimulatedPico
from .store import utc_now


class Controller:
    """One controller; bounded USB I/O lives outside this lock in a worker."""
    def __init__(self, store, clock=time.monotonic, device=None):
        self.store, self.clock = store, clock
        self.lock = threading.RLock()
        self.device = device if device is not None else SimulatedPico()
        self.control_epoch = 0
        self.permit = None
        self.active = None
        self.fault = None
        self.heartbeat_at = float("-inf")
        self.last_sample = self.clock()
        self.latest = self.device.sample(self.last_sample, 0)
        if self.device.simulation:
            self.latest["received_at"] = utc_now()
        self.halt = threading.Event()
        self.thread = None
        self.started_mono = None
        self.ack_pending = False
        self.recorded_sample = None

    def launch(self):
        self.device.start()
        self.thread = threading.Thread(target=self._loop, daemon=True, name="windtunnel-controller")
        self.thread.start()

    def _loop(self):
        while not self.halt.wait(0.05):
            with self.lock:
                try:
                    self.tick()
                except Exception:
                    self.storage_failure()

    def storage_failure(self):
        self.device.stop()
        self.control_epoch += 1
        self.permit = None
        self.fault = "STORAGE_OR_CONTROLLER_FAILURE"
        if self.active:
            self.active.update(state="FAILED", reason=self.fault, finished_at=utc_now())
            # Preserve an in-memory terminal snapshot if the database is unavailable.
            self.failed_snapshot = deepcopy(self.active)
            self.active = None

    def shutdown(self):
        self.halt.set()
        if self.thread:
            self.thread.join(timeout=2)
        with self.lock:
            try:
                self.stop("service_shutdown", "INTERRUPTED")
            finally:
                self.device.stop()
                self.device.close()

    def heartbeat(self):
        self.heartbeat_at = self.clock()

    def permit_status(self):
        p = deepcopy(self.permit)
        if p:
            p["remaining_s"] = None
            p["expires_at"] = None
            p["unlimited"] = True
        return {"enabled": p is not None, "permit": p}

    def set_permit(self, spec):
        self.tick()
        if self.active:
            deny("CONTROL_BUSY", 409)
        if self.clock() - self.heartbeat_at > 5:
            deny("LOCAL_UI_HEARTBEAT_REQUIRED", 409)
        if self.fault or not self.latest['valid']:
            deny("FAULT_ACTIVE", 409)
        self.control_epoch += 1
        self.permit = {"id": str(uuid4()),
                       "max_pwm_percent": spec.max_pwm_percent}
        return self.permit_status()

    def remote_off(self, reason="remote_mode_off"):
        self.permit = None
        self.control_epoch += 1
        if self.active and self.active["source"] == "remote":
            self._finish("CANCELLED", reason)

    def start(self, request, principal, key):
        self.tick()
        if not self.device.supports_runs:
            deny('HARDWARE_MONITOR_ONLY', 409)
        if not principal.local:
            if not self.permit:
                deny("REMOTE_MODE_OFF")
        digest = hashlib.sha256(request.model_dump_json().encode()).hexdigest()
        previous = self.store.replay(principal.id, key)
        if previous:
            if previous[0] != digest:
                deny("IDEMPOTENCY_CONFLICT", 409)
            return self.get_run(previous[1]["id"])
        if request.control_epoch != self.control_epoch:
            deny("STALE_CONTROL_EPOCH", 409)
        if self.active:
            deny("CONTROL_BUSY", 409)
        if self.fault or not self.latest["valid"]:
            deny("DEVICE_NOT_READY", 503)
        if hasattr(self.device,'precheck'):
            problem=self.device.precheck()
            if problem: deny(problem,409)
        if self.clock() - self.heartbeat_at > 5:
            deny("LOCAL_UI_HEARTBEAT_REQUIRED", 409)
        if principal.local and self.permit:
            deny("TURN_REMOTE_MODE_OFF_FIRST", 409)
        if not principal.local:
            if request.remote_permit_id != self.permit["id"]:
                deny("STALE_REMOTE_PERMIT", 409)
            if max(s.pwm_percent for s in request.recipe.steps) > self.permit["max_pwm_percent"]:
                deny("PWM_LIMIT_EXCEEDED", 422)
        run = {
            "id": str(uuid4()), "simulation": self.device.simulation, "owner": principal.id,
            "owner_name": principal.name, "source": "local" if principal.local else "remote",
            "peer_ip": principal.ip, "recipe": request.recipe.model_dump(),
            "recipe_hash": hashlib.sha256(request.recipe.model_dump_json().encode()).hexdigest(),
            "state": "ARMING" if hasattr(self.device,'begin_run') else "RUNNING", "started_at": utc_now(), "finished_at": None,
            "reason": None, "duration_s": request.recipe.duration_s, "elapsed_s": 0,
            "step_index": 0, "phase": "settle", "control_epoch": self.control_epoch,
        }
        # Persist identity + idempotency key atomically BEFORE applying PWM.
        self.store.create_run(run, key, digest)
        self.active = run
        self.recorded_sample = None
        self.arming_since = self.clock()
        self.started_mono = None if hasattr(self.device,'begin_run') else self.clock()
        if hasattr(self.device,'begin_run'):
            self.device.begin_run(run['id'],run['duration_s'])
            self.active['phase']='precheck'
        self.tick()
        return deepcopy(run)

    def stop(self, reason="stop_requested", terminal="CANCELLED"):
        if not self.active or self.active['state']!='STOPPING':
            self.device.stop()  # Safety action precedes storage.
        self.control_epoch += 1
        self.permit = None
        if self.active:
            self._finish(terminal, reason)

    def _finish(self, state, reason):
        if self.active['state']=='STOPPING':
            if state=='FAILED': self.pending_finish.update(state=state,reason=reason)
            return
        self.device.stop()
        run = self.active
        elapsed=min(run['duration_s'],self.clock()-self.started_mono) if self.started_mono is not None else 0
        if hasattr(self.device,'begin_run'):
            self.pending_finish=dict(state=state,reason=reason)
            self.stopping_since=self.clock()
            run.update(state='STOPPING',phase='stopping',elapsed_s=elapsed)
            self.store.update_run(run)
            return
        run.update(state=state, reason=reason, finished_at=utc_now(),
                   elapsed_s=elapsed)
        self.store.update_run(run)
        self.active = None

    def tick(self):
        now = self.clock()
        if now - self.heartbeat_at > 5 and (self.active or self.permit):
            self.stop("local_ui_heartbeat_lost")
        if self.device.fault != "none":
            self.fault = "SIMULATED_" + self.device.fault.upper() if self.device.simulation else self.device.fault
            if self.active or self.permit:
                self.stop(self.fault, "FAILED")
        if self.active and self.active['state']=='STOPPING':
            if self.device.stop_confirmed or now-self.stopping_since>3:
                confirmed=self.device.stop_confirmed
                terminal=self.pending_finish if confirmed else dict(state='FAILED',reason='PICO_STOP_UNCONFIRMED')
                if not confirmed: self.fault='PICO_STOP_UNCONFIRMED'
                self.active.update(**terminal,stop_acknowledged=confirmed,finished_at=utc_now())
                self.store.update_run(self.active)
                self.active=None
        if self.active and self.active['state']=='ARMING':
            self.device.set_pwm(0)
            if self.device.is_armed(self.active['id']):
                self.started_mono=now
                self.active.update(state='RUNNING',started_at=utc_now(),phase='settle')
                self.store.update_run(self.active)
            elif now-self.arming_since>4:
                self.fault='PICO_ARM_TIMEOUT'
                self.stop(self.fault,'FAILED')
        if self.active and self.active['state']=='RUNNING' and self.started_mono is not None:
            elapsed = now - self.started_mono
            self.active["elapsed_s"] = elapsed
            if elapsed >= self.active["duration_s"]:
                self._finish("COMPLETED", "recipe_complete")
            else:
                remaining = elapsed
                steps = self.active["recipe"]["steps"] * self.active["recipe"]["repeat"]
                for index, step in enumerate(steps):
                    length = step["settle_s"] + step["record_s"]
                    if remaining < length:
                        self.active.update(step_index=index, phase="settle" if remaining < step["settle_s"] else "record")
                        self.device.set_pwm(step["pwm_percent"])
                        break
                    remaining -= length
        # Observe the USB worker's latest acquisition on every control tick.
        # A second independent 2 Hz timer can skip Pico acquisitions by phase drift.
        if not self.device.simulation or now - self.last_sample >= 0.5:
            self.latest = self.device.sample(now, now - self.last_sample)
            if self.device.simulation:
                self.latest["received_at"] = utc_now()
            self.last_sample = now
            if not self.device.simulation and self.latest['reason'] == 'PICO_STALE':
                self.fault = 'PICO_STALE'
                if self.active or self.permit:
                    self.stop('PICO_STALE','FAILED')
            sample_key=(self.latest.get('boot_id'),self.latest.get('seq'))
            if self.active and (self.device.simulation or sample_key!=self.recorded_sample):
                gap=0
                if (not self.device.simulation and self.recorded_sample is not None
                        and sample_key[0]==self.recorded_sample[0]
                        and type(sample_key[1]) is int and type(self.recorded_sample[1]) is int):
                    gap=max(0,sample_key[1]-self.recorded_sample[1]-1)
                self.store.sample(self.active["id"], {**self.latest,
                    "pwm_requested_percent": self.device.pwm,
                    "missed_acquisitions_before": gap,
                    "elapsed_s": self.active["elapsed_s"], "step_index": self.active["step_index"],
                    "phase": self.active["phase"], "run_id": self.active["id"]})
                self.recorded_sample=sample_key
        if self.ack_pending and not self.device.ack_pending:
            self.ack_pending=False
            if self.device.fault=='none' and self.latest['valid']:
                self.fault=None

    def status(self):
        stamp = self.last_sample if self.device.simulation else self.latest.get('monotonic_s')
        return {
            "simulation": self.device.simulation, "device": self.device.name,
            "fan_control_available": self.device.supports_runs,
            "state": "FAULT" if self.fault else self.active['state'] if self.active else "IDLE",
            "acknowledging": self.ack_pending,
            "fault": self.fault, "control_epoch": self.control_epoch,
            "pwm_requested_percent": self.device.pwm,
            "active_run": deepcopy(self.active), "remote": self.permit_status(),
            "ui_alive": self.clock() - self.heartbeat_at <= 5,
            "telemetry": {**self.latest, "age_ms": max(0, (self.clock() - stamp) * 1000) if stamp is not None else None},
            "stop_note": "設定値0と羽根の物理停止は別。" + ("表示はすべて模擬値です。" if self.device.simulation else "実測RPMは2 pulse/rev仮定。" if self.device.supports_runs else "停止専用。RPM未計測。"),
        }

    def get_run(self, run_id):
        if self.active and self.active["id"] == run_id:
            return deepcopy(self.active)
        failed = getattr(self, "failed_snapshot", None)
        if failed and failed["id"] == run_id:
            return deepcopy(failed)
        run = self.store.run(run_id)
        if not run:
            deny("RUN_NOT_FOUND", 404)
        return run

    def acknowledge(self):
        if self.active: deny('CONTROL_BUSY',409)
        if self.fault == "STORAGE_OR_CONTROLLER_FAILURE":
            deny("RESTART_AND_CHECK_STORAGE", 409)
        if hasattr(self.device,'request_ack'):
            if not self.latest['valid']: deny('FAULT_CAUSE_REMAINS',409)
            self.device.request_ack()
            self.ack_pending=True
            return
        if self.device.fault != "none" or not self.latest['valid']:
            deny("FAULT_CAUSE_REMAINS", 409)
        if self.fault == "STORAGE_OR_CONTROLLER_FAILURE":
            deny("RESTART_AND_CHECK_STORAGE", 409)
        self.fault = None
        self.device.stop()
