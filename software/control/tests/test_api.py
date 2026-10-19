import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from windtunnel.app import create_app

ORIGIN = "http://127.0.0.1:8765"
CODE = "test-only-one-time-bootstrap-credential"


class Clock:
    def __init__(self):
        self.now = 100.0

    def __call__(self):
        return self.now


@pytest.fixture
def env(tmp_path):
    clock = Clock()
    app = create_app(tmp_path, CODE, ORIGIN, clock, background=False)
    with TestClient(app, base_url=ORIGIN, client=("127.0.0.1", 1234)) as local:
        result = local.post("/api/v1/local/session", json={"code": CODE}, headers={"Origin": ORIGIN})
        assert result.status_code == 200
        local.headers.update({"Origin": ORIGIN, "X-CSRF-Token": result.json()["csrf_token"]})
        yield app, local, clock


def external(env, ip="192.168.100.40", scopes=None):
    app, local, _ = env
    response = local.post("/api/v1/local/clients", json={"name": "Test client", "allowed_ips": [ip],
        "scopes": scopes or ["read", "plan", "control", "stop"]})
    assert response.status_code == 201
    client = TestClient(app, base_url=ORIGIN, client=(ip, 2345))
    client.headers["Authorization"] = "Bearer " + response.json()["token"]
    return client, response.json()


def recipe(seconds=3):
    return {"name": "Synthetic test", "steps": [{"pwm_percent": 40, "settle_s": 1, "record_s": seconds}], "repeat": 1}


def payload(client, seconds=3):
    s = client.get("/api/v1/status").json()
    return {"recipe": recipe(seconds), "control_epoch": s["control_epoch"],
            "remote_permit_id": s["remote"]["permit"]["id"] if s["remote"]["enabled"] else None}


def start(client, body=None, key=None):
    return client.post("/api/v1/runs", json=body or payload(client), headers={"Idempotency-Key": key or str(uuid4())})


def advance(env, seconds, heartbeat=True):
    app, local, clock = env
    # Bound the fake-clock increments so the heartbeat does not accidentally expire.
    for _ in range(int(seconds * 2)):
        clock.now += 0.5
        if heartbeat:
            local.post("/api/v1/local/heartbeat", json={})
        with app.state.controller.lock:
            app.state.controller.tick()


def test_no_credentials_and_local_ip_are_not_identity(env):
    client = TestClient(env[0], base_url=ORIGIN, client=("127.0.0.1", 1235))
    assert client.get("/api/v1/status").status_code == 401
    assert client.post("/api/v1/control/remote-permit", json={}).status_code == 401


def test_bootstrap_is_single_use_and_secret_not_echoed(env):
    local = env[1]
    assert local.post("/api/v1/local/session", json={"code": CODE}).status_code == 401
    r = local.post("/api/v1/local/session", json={"code": "secret"})
    assert r.status_code == 422 and "secret" not in r.text


def test_origin_host_and_csrf(env):
    local = env[1]
    assert local.post("/api/v1/stop", json={}, headers={"Origin": "http://evil.test"}).status_code == 403
    assert local.post("/api/v1/stop", json={}, headers={"X-CSRF-Token": "bad"}).status_code == 403
    assert local.get("/api/v1/status", headers={"Host": "evil.test"}).status_code == 400
    assert local.post("/api/v1/stop", content="x" * 17000).status_code == 413


def test_three_remote_gates_and_no_privilege_promotion(env):
    app, local, _ = env
    remote, info = external(env)
    assert start(remote).status_code == 403
    assert local.post("/api/v1/control/remote-permit", json={}).status_code == 200
    badip = TestClient(app, base_url=ORIGIN, client=("192.168.100.41", 42))
    assert badip.get("/api/v1/status", headers={"Authorization": "Bearer " + info["token"],
        "X-Forwarded-For": "192.168.100.40"}).status_code == 403
    assert remote.get("/api/v1/status", headers={"Authorization": "Bearer incorrect"}).status_code == 401
    assert remote.post("/api/v1/control/remote-permit", json={}).status_code == 403
    assert remote.post("/api/v1/local/heartbeat", json={}).status_code == 403
    body = payload(remote); body["source"] = "local"
    assert start(remote, body).status_code == 422
    assert start(remote).status_code == 202
    assert app.state.controller.device.pwm == 40


def test_scope_and_ipv4_mapped_address(env):
    remote, _ = external(env, scopes=["read", "plan"])
    env[1].post("/api/v1/control/remote-permit", json={})
    assert start(remote).status_code == 403
    assert remote.post("/api/v1/stop", json={}).status_code == 403
    assert remote.post("/api/v1/runs/validate", json=recipe()).status_code == 200
    r = env[1].post("/api/v1/local/clients", json={"name": "ipv6", "allowed_ips": ["::ffff:127.0.0.1"], "scopes": ["read"]})
    assert r.json()["allowed_ips"] == ["127.0.0.1"]


@pytest.mark.parametrize("ip", ["0.0.0.0/0", "192.168.100.*", "localhost", "fe80::1%eth0", "no-ip"])
def test_allowlist_rejects_non_exact_ips(env, ip):
    assert env[1].post("/api/v1/local/clients", json={"name": "bad", "allowed_ips": [ip], "scopes": ["read"]}).status_code == 422


def test_remote_off_cancels_but_read_remains_available(env):
    remote, _ = external(env)
    env[1].post("/api/v1/control/remote-permit", json={})
    run = start(remote).json()
    env[1].delete("/api/v1/control/remote-permit", headers={"Content-Length": "0"})
    s = remote.get("/api/v1/status").json()
    assert not s["remote"]["enabled"] and s["pwm_requested_percent"] == 0
    assert remote.get(f'/api/v1/runs/{run["id"]}').json()["state"] == "CANCELLED"
    assert remote.post("/api/v1/stop", json={}).status_code == 200
    assert start(remote).status_code == 403


def test_unlimited_permit_and_heartbeat_loss(env):
    remote, _ = external(env)
    local = env[1]
    assert local.post("/api/v1/control/remote-permit", json={"duration_s": 600}).status_code == 422
    assert local.post("/api/v1/control/remote-permit", json={}).status_code == 200
    permit = remote.get("/api/v1/status").json()['remote']['permit']
    # Advance 30 hours with simulated healthy local heartbeats at each tick.
    # No real-time sleeps; also verifies sliding authentication renewal past 8 h.
    for _ in range(10):
        env[2].now += 3 * 3600
        env[0].state.controller.heartbeat()  # Represents healthy heartbeats during skipped time.
        assert local.post('/api/v1/local/heartbeat', json={}).status_code == 200
        s = remote.get('/api/v1/status').json()
        assert s['remote']['enabled'] and s['remote']['permit'] == permit
        assert permit['unlimited'] and permit['remaining_s'] is None
    assert start(remote, payload(remote, 20)).status_code == 202
    advance(env, 6, heartbeat=False)
    assert remote.get("/api/v1/status").json()["active_run"] is None


def test_local_heartbeat_loss_also_stops(env):
    assert start(env[1], payload(env[1], 20)).status_code == 202
    advance(env, 6, heartbeat=False)
    assert env[0].state.controller.device.pwm == 0


def test_single_owner_and_stop_invalidates_old_start(env):
    local = env[1]
    old = payload(local)
    assert start(local, old).status_code == 202
    assert start(local, old).status_code == 409
    local.post("/api/v1/stop", json={})
    assert start(local, old).status_code == 409
    assert start(local).status_code == 202


def test_idempotency_is_atomic_and_survives_completion(env):
    local = env[1]; body = payload(local); key = str(uuid4())
    with ThreadPoolExecutor(max_workers=6) as pool:
        responses = list(pool.map(lambda _: start(local, body, key), range(6)))
    assert all(r.status_code == 202 for r in responses)
    assert len({r.json()["id"] for r in responses}) == 1
    advance(env, 4)
    again = start(local, body, key)
    assert again.status_code == 202 and again.json()["state"] == "COMPLETED"
    changed = json.loads(json.dumps(body)); changed["recipe"]["name"] = "different"
    assert start(local, changed, key).status_code == 409
    assert len(local.get("/api/v1/runs").json()["items"]) == 1
    assert env[0].state.controller.device.pwm == 0


def test_recording_export_and_units(env):
    local = env[1]; run = start(local).json(); advance(env, 4)
    result = local.get(f'/api/v1/runs/{run["id"]}/export?format=json').json()
    assert result["simulation"] and result["run"]["state"] == "COMPLETED"
    samples = result["samples"]
    assert {s["phase"] for s in samples} == {"settle", "record"}
    assert all(s["current_a"] < 1 and s["ambient_pressure_pa"] > 100000 for s in samples)
    assert all(s["airspeed_m_s"] is None and s["differential_pressure_pa"] <= 0 for s in samples)
    assert local.get(f'/api/v1/runs/{run["id"]}/export').text.startswith("\ufeffrun_id,simulation")


@pytest.mark.parametrize("fault", ["offline", "sensor", "power"])
def test_fault_stops_and_ack_does_not_resume(env, fault):
    local = env[1]; start(local)
    local.post("/api/v1/local/simulation/fault", json={"fault": fault})
    assert env[0].state.controller.device.pwm == 0
    assert local.post("/api/v1/faults/acknowledge", json={}).status_code == 409
    local.post("/api/v1/local/simulation/fault", json={"fault": "none"})
    assert local.post("/api/v1/faults/acknowledge", json={}).status_code == 200
    assert local.get("/api/v1/status").json()["active_run"] is None


def test_revoke_token_stops_its_active_run(env):
    remote, info = external(env); local = env[1]
    local.post("/api/v1/control/remote-permit", json={})
    start(remote)
    assert local.delete(f'/api/v1/local/clients/{info["id"]}', headers={"Content-Length": "0"}).status_code == 200
    assert env[0].state.controller.device.pwm == 0
    assert remote.get("/api/v1/status").status_code == 401
    assert "token_hash" not in local.get("/api/v1/local/clients").text


@pytest.mark.parametrize("bad", [
    {"steps": [{"pwm_percent": 10, "settle_s": 0, "record_s": 1}]},
    {"steps": [{"pwm_percent": 101, "settle_s": 0, "record_s": 1}]},
    {"steps": [{"pwm_percent": 20, "settle_s": 120, "record_s": 120}], "repeat": 2},
    {"steps": []}, {"repeat": True}, {"mode": "python"}, {"source": "local"},
])
def test_invalid_recipes(env, bad):
    r = recipe(); r.update(bad)
    assert env[1].post("/api/v1/runs/validate", json=r).status_code == 422


def test_non_finite_recipe_rejected(env):
    body = json.dumps(recipe()).replace('"pwm_percent": 40', '"pwm_percent": NaN')
    assert env[1].post("/api/v1/runs/validate", content=body, headers={"Content-Type": "application/json"}).status_code == 422


def test_pwm_permit_limit(env):
    remote, _ = external(env)
    env[1].post("/api/v1/control/remote-permit", json={"max_pwm_percent": 20})
    assert start(remote).status_code == 422


def test_storage_failure_stops_before_logging(env, monkeypatch):
    local = env[1]; start(local)
    def fail(*args):
        raise sqlite3.OperationalError("disk full")
    monkeypatch.setattr(env[0].state.controller.store, "sample", fail)
    env[2].now += 0.5
    assert local.get("/api/v1/status").status_code == 503
    assert env[0].state.controller.device.pwm == 0
    assert env[0].state.controller.fault == "STORAGE_OR_CONTROLLER_FAILURE"


def test_restart_defaults_off_and_interrupts_unfinished_run(tmp_path):
    clock = Clock()
    app = create_app(tmp_path, CODE, ORIGIN, clock, background=False)
    # Simulate a saved RUNNING row surviving an abrupt process termination.
    app.state.controller.store.create_run({"id": "old", "owner": "client", "state": "RUNNING", "simulation": True}, "key", "hash")
    app.state.controller.store.close()
    reopened = create_app(tmp_path, CODE, ORIGIN, clock, background=False)
    assert reopened.state.controller.store.run("old")["state"] == "INTERRUPTED"
    assert reopened.state.controller.device.pwm == 0
    assert reopened.state.controller.permit is None
    assert reopened.state.controller.store.replay("client", "key")[0] == "hash"
    reopened.state.controller.store.close()


def test_openapi_and_static_have_no_external_assets(env):
    local = env[1]
    schema = local.get("/openapi.json").json()
    assert "ApiToken" in schema["components"]["securitySchemes"]
    assert "/api/v1/runs" in schema["paths"]
    assert "serial" not in schema["paths"]
    html = local.get("/")
    assert "接続確認中" in html.text and "https://" not in html.text
    assert "frame-ancestors 'none'" in html.headers["content-security-policy"]


def test_stop_client_can_stop_another_owner_without_remote_permit(env):
    stop_client, _ = external(env, scopes=["read", "stop"])
    run = start(env[1]).json()
    assert stop_client.post("/api/v1/stop", json={}).status_code == 200
    assert env[1].get(f'/api/v1/runs/{run["id"]}').json()["state"] == "CANCELLED"


def test_old_permit_cannot_start_after_off_on(env):
    remote, _ = external(env); local = env[1]
    local.post("/api/v1/control/remote-permit", json={})
    old = payload(remote)
    local.delete("/api/v1/control/remote-permit", headers={"Content-Length": "0"})
    local.post("/api/v1/control/remote-permit", json={})
    assert start(remote, old).status_code == 409
    old["control_epoch"] = local.get("/api/v1/status").json()["control_epoch"]
    assert start(remote, old).status_code == 409


def test_cancel_completed_run_does_not_stop_current_run(env):
    local = env[1]; old = start(local).json(); advance(env, 4)
    new = start(local).json()
    assert local.post(f'/api/v1/runs/{old["id"]}/cancel', json={}).json()["state"] == "COMPLETED"
    assert env[0].state.controller.active["id"] == new["id"]


def test_client_secret_is_hashed_in_database(env):
    _, info = external(env)
    stored = env[0].state.controller.store.clients()
    assert info["token"] not in json.dumps(stored)
    assert len(stored[0]["token_hash"]) == 64


def test_runtime_directory_has_one_controller(tmp_path):
    from windtunnel.instance import InstanceLock
    lock = InstanceLock(tmp_path / "controller.lock")
    try:
        with pytest.raises(RuntimeError):
            InstanceLock(tmp_path / "controller.lock")
    finally:
        lock.close()
    InstanceLock(tmp_path / "controller.lock").close()


def test_bootstrap_rejects_non_loopback_even_with_valid_secret(tmp_path):
    app = create_app(tmp_path, CODE, ORIGIN, background=False)
    with TestClient(app, base_url=ORIGIN, client=("192.168.100.40", 1234)) as remote:
        r = remote.post("/api/v1/local/session", json={"code": CODE}, headers={"Origin": ORIGIN})
        assert r.status_code == 403


def test_unexpected_controller_failure_latches_stop(env, monkeypatch):
    start(env[1])
    def fail(*args):
        raise RuntimeError("unexpected simulator failure")
    monkeypatch.setattr(env[0].state.controller.device, "sample", fail)
    env[2].now += 0.5
    assert env[1].get("/api/v1/status").status_code == 503
    assert env[0].state.controller.device.pwm == 0
    assert env[0].state.controller.active is None
