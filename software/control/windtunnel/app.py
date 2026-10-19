import csv
import io
import json
import secrets
import sqlite3
import time
from contextlib import asynccontextmanager, contextmanager
from pathlib import Path
from urllib.parse import urlsplit
from uuid import uuid4

from fastapi import FastAPI, Header, Query, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException

from .controller import Controller
from .models import BootstrapRequest, ClientRequest, FaultRequest, PermitRequest, Recipe, StartRequest
from .security import Security, deny
from .store import Store

STATIC = Path(__file__).parent / "static"


def create_app(data_dir, bootstrap_code=None, origin="http://127.0.0.1:8765", clock=time.monotonic, background=True, device=None):
    data_dir = Path(data_dir)
    data_dir.mkdir(parents=True, exist_ok=True)
    simulation = device is None or device.simulation
    store = Store(data_dir / ("simulation.sqlite3" if simulation else "monitor.sqlite3"))
    controller = Controller(store, clock, device)
    security = Security(store, bootstrap_code or secrets.token_urlsafe(32), clock)

    @asynccontextmanager
    async def lifespan(app):
        if background:
            controller.launch()
        try:
            yield
        finally:
            controller.shutdown()
            store.close()

    app = FastAPI(title="Wind Tunnel " + ("SIMULATION" if simulation else "PICO") + " API", version="0.3.0", lifespan=lifespan,
                  docs_url=None, redoc_url=None,
                  description="Simulation, stopped-only acquisition, or finite real-Pico PWM tests. Remote permission has no timer; OFF, restart, faults or missing local heartbeat revoke it. Peer IP and Bearer scope are also required.")
    app.state.controller, app.state.security = controller, security
    authority = urlsplit(origin).netloc

    @app.middleware("http")
    async def boundary(request: Request, call_next):
        request_id = str(uuid4())
        if request.headers.get("host") != authority:
            return JSONResponse({"code": "HOST_DENIED", "request_id": request_id}, 400)
        if request.headers.get("origin") not in (None, origin):
            return JSONResponse({"code": "ORIGIN_DENIED", "request_id": request_id}, 403)
        if request.method not in ("GET", "HEAD", "OPTIONS"):
            length = request.headers.get("content-length")
            if request.headers.get("transfer-encoding") or not length or not length.isdigit():
                return JSONResponse({"code": "CONTENT_LENGTH_REQUIRED", "request_id": request_id}, 411)
            if int(length) > 16384:
                return JSONResponse({"code": "BODY_TOO_LARGE", "request_id": request_id}, 413)
            # All browser state changes require same-origin, including the bootstrap exchange.
            if ("wt_session" in request.cookies or request.url.path == "/api/v1/local/session") and not request.headers.get("authorization"):
                if request.headers.get("origin") != origin:
                    return JSONResponse({"code": "ORIGIN_REQUIRED", "request_id": request_id}, 403)
        response = await call_next(request)
        response.headers.update({
            "Cache-Control": "no-store", "X-Request-ID": request_id,
            "X-Content-Type-Options": "nosniff", "Referrer-Policy": "no-referrer",
            "Content-Security-Policy": "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'",
        })
        return response

    @app.exception_handler(HTTPException)
    async def http_error(request, exc):
        detail = exc.detail if isinstance(exc.detail, dict) else {"code": "REQUEST_FAILED", "message": str(exc.detail)}
        return JSONResponse(detail, status_code=exc.status_code)

    @app.exception_handler(RequestValidationError)
    async def validation_error(request, exc):
        # Do not echo request values (bootstrap codes / API tokens) into error responses.
        return JSONResponse({"code": "INVALID_REQUEST", "fields": [list(e["loc"]) for e in exc.errors()]}, 422)

    @contextmanager
    def guard(request, scope="read", local=False):
        with controller.lock:
            try:
                principal = security.authenticate(request, scope, local)
                controller.tick()
                yield principal
                if request.method not in ("GET", "HEAD") and not request.url.path.endswith("/heartbeat"):
                    store.event("api", principal.id, request.method + " " + request.url.path)
            except sqlite3.Error:
                controller.storage_failure()
                deny("STORAGE_FAILURE", 503)
            except HTTPException:
                raise
            except Exception:
                controller.storage_failure()
                deny("CONTROLLER_FAILURE", 503)

    @app.post("/api/v1/local/session", tags=["local"])
    def bootstrap(spec: BootstrapRequest, request: Request, response: Response):
        with controller.lock:
            session, csrf = security.bootstrap(spec.code, request.client.host)
            response.set_cookie("wt_session", session, httponly=True, samesite="strict",
                                secure=origin.startswith("https:"), max_age=8 * 3600)
            controller.heartbeat()
            return {"csrf_token": csrf, "simulation": simulation}

    @app.post("/api/v1/local/heartbeat", tags=["local"])
    def heartbeat(request: Request, response: Response):
        with guard(request, local=True):
            controller.heartbeat()
            security.renew_local_session(request, response, origin.startswith('https:'))
            return {"ok": True}

    @app.get("/api/v1/status")
    def status(request: Request):
        with guard(request):
            return controller.status()

    @app.get("/api/v1/telemetry/latest")
    def telemetry(request: Request):
        with guard(request):
            return controller.status()["telemetry"]

    @app.get("/api/v1/capabilities")
    def capabilities(request: Request):
        with guard(request):
            return {"simulation": simulation, "hardware_supported": not simulation,
                    "fan_control_available": controller.device.supports_runs,
                    "mode": ["pwm"] if controller.device.supports_runs else ["monitor_locked_stop"],
                    "max_run_s": 300, "max_steps": 12, "pwm_percent": "0 or 20–100",
                    "telemetry_hz": 2, "transport": "polling", "airspeed_calibrated": False,
                    "remote_gate": ["mode_on", "exact_peer_ip", "bearer_token_scope"],
                    "proxy_headers_trusted": False, "remote_permit_timeout_s": None,
                    "remote_permit_revoked_on": ["off", "stop", "restart", "fault", "ui_heartbeat_lost"]}

    @app.post("/api/v1/runs/validate")
    def validate(spec: Recipe, request: Request):
        with guard(request, "plan"):
            if not controller.device.supports_runs:
                deny('HARDWARE_MONITOR_ONLY', 409)
            return {"valid": True, "simulation": simulation, "duration_s": spec.duration_s,
                    "note": "Start rechecks authority, epoch, permit, device and storage."}

    @app.post("/api/v1/runs", status_code=202)
    def start(spec: StartRequest, request: Request,
              idempotency_key: str = Header(min_length=8, max_length=100, pattern=r"^[A-Za-z0-9_-]+$")):
        with guard(request, "control") as principal:
            return controller.start(spec, principal, idempotency_key)

    @app.get("/api/v1/runs")
    def runs(request: Request, limit: int = Query(20, ge=1, le=50), offset: int = Query(0, ge=0)):
        with guard(request):
            items = store.runs(limit, offset)
            return {"items": [controller.get_run(r["id"]) for r in items], "offset": offset, "limit": limit}

    @app.get("/api/v1/runs/{run_id}")
    def run(run_id: str, request: Request):
        with guard(request):
            return controller.get_run(run_id)

    @app.post("/api/v1/runs/{run_id}/cancel")
    def cancel(run_id: str, request: Request):
        with guard(request, "stop"):
            current = controller.get_run(run_id)
            if current["state"] in ("RUNNING","ARMING","STOPPING"):
                controller.stop("run_cancelled")
            return controller.get_run(run_id)

    @app.post("/api/v1/stop")
    def stop(request: Request):
        with guard(request, "stop"):
            controller.stop()
            return controller.status()

    @app.get("/api/v1/control/remote-permit")
    def remote_status(request: Request):
        with guard(request):
            return controller.permit_status()

    @app.post("/api/v1/control/remote-permit", tags=["local"])
    def remote_on(spec: PermitRequest, request: Request):
        with guard(request, local=True):
            return controller.set_permit(spec)

    @app.delete("/api/v1/control/remote-permit", tags=["local"])
    def remote_off(request: Request):
        with guard(request, local=True):
            controller.remote_off()
            return controller.permit_status()

    @app.get("/api/v1/local/clients", tags=["local"])
    def clients(request: Request):
        with guard(request, local=True):
            return {"items": [security.public_client(c) for c in store.clients()]}

    @app.post("/api/v1/local/clients", tags=["local"], status_code=201)
    def new_client(spec: ClientRequest, request: Request):
        with guard(request, local=True):
            return security.create_client(spec)

    @app.delete("/api/v1/local/clients/{client_id}", tags=["local"])
    def revoke(client_id: str, request: Request):
        with guard(request, local=True):
            client = next((c for c in store.clients() if c["id"] == client_id), None)
            if not client:
                deny("CLIENT_NOT_FOUND", 404)
            if controller.active and controller.active["owner"] == client_id:
                controller.stop("client_revoked")
            client["revoked"] = True
            store.save_client(client)
            return {"revoked": True}

    @app.post("/api/v1/local/simulation/fault", tags=["simulation"])
    def inject_fault(spec: FaultRequest, request: Request):
        with guard(request, local=True):
            if not simulation:
                deny('SIMULATION_ONLY', 409)
            controller.device.fault = spec.fault
            controller.tick()
            return controller.status()

    @app.post("/api/v1/faults/acknowledge", tags=["local"])
    def acknowledge(request: Request):
        with guard(request, local=True):
            controller.acknowledge()
            return controller.status()

    @app.get("/api/v1/runs/{run_id}/export")
    def export(run_id: str, request: Request, format: str = Query("csv", pattern="^(csv|json)$")):
        with guard(request):
            run_data = controller.get_run(run_id)
            samples = store.samples(run_id)
        prefix='simulation' if run_data['simulation'] else 'measurement'
        headers = {"Content-Disposition": f'attachment; filename="{prefix}-{run_data["id"]}.{format}"'}
        if format == "json":
            return JSONResponse({"simulation": run_data['simulation'], "run": run_data, "samples": samples}, headers=headers)
        keys = ["run_id", "simulation", "received_at", "elapsed_s", "step_index", "phase", "valid",
                "pwm_requested_percent", "pwm_applied_percent", "rpm_estimated", "differential_pressure_pa", "temperature_c",
                "relative_humidity_percent", "ambient_pressure_pa", "bus_voltage_v", "current_a", "power_w",
                "tach_edges", "tach_window_us", "tach_total_edges", "tach_hz", "pulses_per_revolution_assumed", "tach_window_mixed_pwm", "missed_acquisitions_before", "boot_id", "seq"]
        buffer = io.StringIO(newline="")
        writer = csv.DictWriter(buffer, fieldnames=keys, extrasaction="ignore")
        writer.writeheader()
        # Free-form names are intentionally not CSV cells; all text here is server-generated.
        writer.writerows(samples)
        return Response("\ufeff" + buffer.getvalue(), media_type="text/csv; charset=utf-8", headers=headers)

    app.mount("/static", StaticFiles(directory=STATIC), name="static")

    @app.get("/", include_in_schema=False)
    def index():
        return FileResponse(STATIC / "index.html")

    original_openapi = app.openapi

    def openapi():
        schema = original_openapi()
        schema.setdefault("components", {})["securitySchemes"] = {
            "ApiToken": {"type": "http", "scheme": "bearer", "description": "Requires configured peer IP; operations also require local remote-mode permit."},
            "LocalSession": {"type": "apiKey", "in": "cookie", "name": "wt_session", "description": "One-time local bootstrap. Writes also require X-CSRF-Token and matching Origin."},
        }
        for path, methods in schema["paths"].items():
            for operation in methods.values():
                operation["security"] = [] if path.endswith("/local/session") else (
                    [{"LocalSession": []}] if "local" in operation.get("tags", []) or "simulation" in operation.get("tags", [])
                    else [{"ApiToken": []}, {"LocalSession": []}])
        return schema

    app.openapi = openapi
    return app
