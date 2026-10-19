"""Finite-run USB controller. No API handler blocks on serial I/O.

The worker's drive lease depends on fresh Controller.set_pwm calls, not on the
worker merely being alive. Any failure discards run intent and requires ack.
"""
from copy import deepcopy
import math
import time

from .pico import DEVICE_ID, PicoMonitor, decode_sample, empty_sample


def validate_control(frame):
    if not isinstance(frame,dict) or type(frame.get('ok')) is not bool:
        raise ValueError('PICO_PROTOCOL')
    if frame.get('device_id') != DEVICE_ID: raise ValueError('PICO_ID_MISMATCH')
    if frame.get('protocol') != 2 or frame.get('firmware') != '0.3.0-control':
        raise ValueError('PICO_FIRMWARE_MISMATCH')
    for name in ('seq','pico_ms','safety_epoch','sample_seq'):
        if type(frame.get(name)) is not int or frame[name]<0: raise ValueError('PICO_SEQUENCE')
    if not isinstance(frame.get('boot_id'),str) or len(frame['boot_id']) != 16:
        raise ValueError('PICO_SEQUENCE')
    pwm=frame.get('fan_command_percent')
    if type(pwm) not in (int,float) or not (pwm==0 or 20<=pwm<=100): raise ValueError('PICO_PWM_RANGE')
    if frame.get('fan_enabled') is not (pwm>0) or frame.get('fan_locked_stop') is not False:
        raise ValueError('PICO_PWM_STATE')
    if pwm==0 and (type(frame.get('gp16_level')) is not int or frame['gp16_level'] != 0):
        raise ValueError('PICO_STOP_NOT_CONFIRMED')
    if frame.get('lease_ms')!=2000 or frame.get('watchdog_ms')!=3000 or frame.get('pwm_hz')!=25000:
        raise ValueError('PICO_SAFETY_CONFIG')
    if pwm and (not frame.get('arm_id') or frame.get('watchdog_enabled') is not True or frame.get('fault')):
        raise ValueError('PICO_UNSAFE_DRIVE')


def decode_control(frame, now):
    validate_control(frame)
    age=frame.get('sample_age_ms')
    if age is None:
        return empty_sample('WARMING_UP')
    if type(age) is not int or not 0<=age<=1500: raise ValueError('PICO_STALE')
    s=decode_sample(frame,now-age/1000,validator=validate_control)
    raw=frame['raw']
    edges,window,total=(raw.get(k) for k in ('tach_edges','tach_window_us','tach_total_edges'))
    if (type(edges) is not int or not 0<=edges<=65535 or type(window) is not int
            or not 100000<=window<=2000000 or type(total) is not int or total<edges or raw.get('tach_ppr')!=2):
        raise ValueError('PICO_TACH_FORMAT')
    hz=edges*1e6/window
    if not math.isfinite(hz) or hz>150: raise ValueError('PICO_TACH_RANGE')
    s.update(seq=frame['sample_seq'],response_seq=frame['seq'],fan_locked_stop=False,
             gp16_level=frame['gp16_level'],pwm_applied_percent=frame['fan_command_percent'],
             rpm_estimated=hz*30,rpm_reason=None,pulses_per_revolution_assumed=2,
             tach_edges=edges,tach_window_us=window,tach_total_edges=total,tach_hz=hz,
             tach_window_mixed_pwm=raw.get('tach_window_mixed_pwm'),
             firmware_fault=frame.get('fault'),arm_id=frame.get('arm_id'),
             safety_epoch=frame['safety_epoch'],run_id_on_pico=frame.get('run_id'))
    return s


class PicoControl(PicoMonitor):
    supports_runs=True
    name='pico_control'

    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs)
        self.intent=None
        self.armed_run=None
        self.generation=0
        self.control_at=float('-inf')
        self.ack_pending=False
        self.stop_confirmed=False
        self.frame=None
        self.drive_seq=0

    def validate_response(self,frame): validate_control(frame)

    def precheck(self):
        with self.lock:
            t=self.latest
            if self.problem!='none' or not t['valid'] or t['monotonic_s'] is None or self.clock()-t['monotonic_s']>1.5:
                return 'DEVICE_NOT_READY'
            if not 10.8<=t['bus_voltage_v']<=13.2: return 'SUPPLY_CHECK_SW1'
            if not -.020<=t['current_a']<=.080: return 'STOPPED_CURRENT'
            if t['rpm_estimated'] is None or t['rpm_estimated']>60: return 'WAIT_FOR_FAN_STOP'
            if not self.stop_confirmed: return 'STOP_NOT_CONFIRMED'
        return None

    def begin_run(self,run_id,duration_s):
        with self.lock:
            self.generation+=1
            self.intent=dict(run_id=run_id,duration_ms=math.ceil(duration_s*1000)+2000)
            self.pwm=0
            self.control_at=self.clock()
            self.stop_confirmed=False

    def is_armed(self,run_id):
        with self.lock: return self.armed_run==run_id and self.problem=='none'

    def set_pwm(self,value):
        if not (value==0 or 20<=value<=100): raise ValueError('PWM_RANGE')
        with self.lock:
            if value and self.intent is None: raise ValueError('PICO_NOT_ARMED')
            self.pwm=float(value)
            self.control_at=self.clock()

    def stop(self):
        with self.lock:
            self.generation+=1
            self.intent=None
            self.armed_run=None
            self.pwm=0
            self.stop_confirmed=False
            self.stop_pending.set()

    def request_ack(self):
        with self.lock:
            if self.intent is not None: raise ValueError('PICO_BUSY')
            self.ack_pending=True

    def close(self):
        self.stop()
        deadline=time.monotonic()+1.5
        while self.thread and self.thread.is_alive() and not self.stop_confirmed and time.monotonic()<deadline:
            time.sleep(.02)
        super().close()

    def _trip(self,reason,empty=False):
        with self.lock:
            if self.problem=='none': self.problem=reason
            if self.intent is not None or self.armed_run is not None:
                self.generation+=1
                self.intent=self.armed_run=None
                self.pwm=0
                self.stop_pending.set()
                self.stop_confirmed=False
            if empty: self.latest=empty_sample(reason)
            self.ack_pending=False

    def _talk(self,command):
        previous=self.last_boot
        frame=self._exchange(command)
        self.frame=frame
        if previous is not None and previous != frame['boot_id']:
            self._trip('PICO_RESTARTED')
            self.stop_pending.set()
        if frame.get('fault'): self._trip('PICO_FW_'+frame['fault'])
        if not frame['ok']: raise ValueError('PICO_CMD_'+str(frame.get('error','REJECTED'))[:80])
        return frame

    def _publish(self,frame):
        result=decode_control(frame,self.clock())
        with self.lock: self.latest=result
        if frame.get('fault'): self._trip('PICO_FW_'+frame['fault'])
        elif not result['valid'] and result['reason']!='WARMING_UP': self._trip('PICO_SENSOR_ERROR')

    def _cycle(self):
        with self.lock:
            generation=self.generation
            intent=deepcopy(self.intent)
            value=self.pwm
            control_at=self.control_at
            pending=self.stop_pending.is_set()
            if pending: self.stop_pending.clear()
            ack=self.ack_pending
        if pending:
            frame=self._talk('stop')
            with self.lock:
                if generation==self.generation: self.stop_confirmed=frame['fan_command_percent']==0 and frame['arm_id'] is None
            self._publish(frame)
            return
        if ack:
            frame=self._talk('ack')
            with self.lock:
                self.problem='none'
                self.ack_pending=False
                self.stop_confirmed=True
            self._publish(frame)
            return
        if intent:
            if self.clock()-control_at>.75:
                self._trip('PICO_CONTROLLER_HEARTBEAT_LOST')
                return
            with self.lock:
                if generation!=self.generation or self.problem!='none': return
            if self.armed_run!=intent['run_id']:
                frame=self._talk(dict(cmd='arm',boot_id=self.frame['boot_id'],epoch=self.frame['safety_epoch'],**intent))
                with self.lock:
                    if generation!=self.generation: self.stop_pending.set()
                    elif frame['arm_id'] and frame['run_id']==intent['run_id']:
                        self.armed_run=intent['run_id'];self.drive_seq=0
                    else: raise ValueError('PICO_ARM_NOT_CONFIRMED')
                self._publish(frame)
                return
            self.drive_seq+=1
            frame=self._talk(dict(cmd='drive',boot_id=self.frame['boot_id'],epoch=self.frame['safety_epoch'],
                arm_id=self.frame['arm_id'],command_seq=self.drive_seq,pwm_percent=value))
            with self.lock:
                if generation!=self.generation: self.stop_pending.set()
            if frame['fan_command_percent']!=value or frame['run_id']!=intent['run_id']:
                raise ValueError('PICO_APPLY_NOT_CONFIRMED')
        else:
            frame=self._talk('sample')
            if frame['fan_command_percent'] or frame['arm_id']:
                self.stop_pending.set()
                raise ValueError('PICO_UNEXPECTED_DRIVE')
        self._publish(frame)

    def _loop(self):
        try:
            while not self.halt.is_set():
                try:
                    if self.connection is None:
                        factory=self.serial_factory
                        if factory is None:
                            import serial
                            factory=serial.Serial
                        self.connection=factory(self.port,115200,timeout=.1,write_timeout=.3,exclusive=True)
                        self.connection.reset_input_buffer()
                        self.stop_pending.set()
                    started=self.clock()
                    self._cycle()
                    self.halt.wait(max(0,.25-(self.clock()-started)))
                except Exception as exc:
                    reason=str(exc) if isinstance(exc,ValueError) and str(exc).startswith('PICO_') else 'PICO_DISCONNECTED'
                    self._trip(reason,empty=True)
                    if self.connection:
                        try:
                            # Best effort stop; no waiting for a failed transport. Firmware lease is independent.
                            self.connection.write(b'{"cmd":"stop","id":"transport-failure"}\n')
                        except Exception: pass
                        try: self.connection.close()
                        except Exception: pass
                        self.connection=None
                    self.halt.wait(1)
        finally:
            if self.connection:
                try: self.connection.close()
                except Exception: pass
                self.connection=None
