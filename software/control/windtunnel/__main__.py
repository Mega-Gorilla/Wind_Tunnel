import argparse
import os
import secrets
import socket
import subprocess
import threading
import webbrowser
from pathlib import Path

import uvicorn

from .app import create_app
from .instance import InstanceLock


def main():
    parser = argparse.ArgumentParser(description="Simulation or stopped-only Pico sensor monitor")
    parser.add_argument('--backend', choices=['simulation', 'pico-monitor', 'pico-control'], default='simulation')
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--data-dir", type=Path, default=Path(".runtime"))
    parser.add_argument("--open", action="store_true", help="Open local kiosk using a one-time URL fragment")
    args = parser.parse_args()
    # A locked, loopback-only socket prevents starting a second controller on the same port.
    sock = socket.socket()
    if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
    else:
        # Linux needs this to rebind after a graceful restart with TIME_WAIT peers.
        # SO_REUSEPORT stays disabled; the data-directory lock is a separate guard.
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(("127.0.0.1", args.port))
    origin = f"http://127.0.0.1:{args.port}"
    code = secrets.token_urlsafe(32)
    args.data_dir.mkdir(parents=True, exist_ok=True)
    instance = InstanceLock(args.data_dir / "controller.lock")
    os.chmod(args.data_dir, 0o700)
    if os.name == "nt":
        # Restrict runtime credentials/history to the current Windows user, without shell expansion.
        identity = subprocess.check_output(["whoami"], text=True).strip()
        subprocess.run(["icacls", str(args.data_dir.resolve()), "/inheritance:r", "/grant:r", f"{identity}:(OI)(CI)F"],
                       check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    access = args.data_dir / "local-access.html"
    url = origin + "/#bootstrap=" + code
    access.write_text(f'<!doctype html><meta charset="utf-8"><title>Local access</title><a href="{url}">本体の操作画面を開く（一回限り）</a>', encoding="utf-8")
    os.chmod(access, 0o600)
    device = None
    if args.backend == 'pico-monitor':
        from .pico import PicoMonitor
        device = PicoMonitor()
    elif args.backend == 'pico-control':
        from .pico_control import PicoControl
        device = PicoControl()
    application = create_app(args.data_dir, code, origin, device=device)
    print(f"{args.backend}: {origin} ; local access file: {access.resolve()}", flush=True)
    if args.open:
        threading.Timer(1, lambda: webbrowser.open(url)).start()
    server = uvicorn.Server(uvicorn.Config(application, host="127.0.0.1", port=args.port, workers=1,
        proxy_headers=False, access_log=False, limit_concurrency=32, timeout_graceful_shutdown=3))
    try:
        server.run(sockets=[sock])
    finally:
        access.unlink(missing_ok=True)
        sock.close()
        instance.close()


if __name__ == "__main__":
    main()
