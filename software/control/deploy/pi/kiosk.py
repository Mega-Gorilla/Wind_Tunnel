"""Own only this application's backend and Firefox processes.

No serial/GPIO access. A fresh controller/session accompanies each kiosk start.
The browser receives a private local HTML redirect, never a token in argv.
"""
import html
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import time
from urllib.request import ProxyHandler, build_opener

ROOT = Path(__file__).resolve().parents[2]
BACKEND = os.environ.get('WT_BACKEND', 'simulation')
if BACKEND not in ('simulation', 'pico-monitor', 'pico-control'):
    raise ValueError('Unknown WT_BACKEND')
DATA = Path.home() / '.local/share/windtunnel-control' / ('monitor' if BACKEND.startswith('pico-') else 'simulation')
PROFILE = Path.home() / '.local/share/windtunnel-control/firefox'
ORIGIN = 'http://127.0.0.1:8765'
stopping = False


def request_stop(_signum, _frame):
    global stopping
    stopping = True


def finish(process):
    if process is not None and process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=8)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=3)


def main():
    os.umask(0o077)
    for directory in (DATA, PROFILE):
        directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        directory.chmod(0o700)
    access = DATA / 'local-access.html'
    previous = access.read_bytes() if access.exists() else None
    redirect = DATA / 'kiosk-start.html'
    server = browser = None
    signal.signal(signal.SIGTERM, request_stop)
    signal.signal(signal.SIGINT, request_stop)
    opener = build_opener(ProxyHandler({}))
    try:
        server = subprocess.Popen([sys.executable, '-m', 'windtunnel', '--backend', BACKEND, '--data-dir', str(DATA)], cwd=ROOT)
        deadline = time.monotonic() + 60
        while not stopping:
            if server.poll() is not None:
                raise RuntimeError('Backend exited before readiness')
            if time.monotonic() > deadline:
                raise TimeoutError('Backend did not become ready')
            try:
                content = access.read_bytes()
                if content != previous:
                    with opener.open(ORIGIN + '/openapi.json', timeout=2) as response:
                        if response.status == 200:
                            break
            except (OSError, TimeoutError):
                pass
            time.sleep(.2)
        if stopping:
            return 0
        match = re.search(r'href="(http://127\.0\.0\.1:8765/#bootstrap=[A-Za-z0-9_-]+)"', content.decode())
        if not match:
            raise RuntimeError('Unexpected local bootstrap format')
        redirect.write_text('<!doctype html><meta charset="utf-8"><meta http-equiv="refresh" content="0;url='
                            + html.escape(match[1], quote=True) + '"><title>Wind Tunnel</title>', encoding='utf-8')
        # Use an isolated Firefox profile. Chromium 149's GPU process spun at 100%
        # on this armhf Pi, even with GPU acceleration disabled. Do not weaken sandboxes.
        (PROFILE / 'user.js').write_text('\n'.join([
            'user_pref("browser.shell.checkDefaultBrowser", false);',
            'user_pref("browser.sessionstore.resume_from_crash", false);',
            'user_pref("browser.startup.homepage_override.mstone", "ignore");',
            'user_pref("browser.aboutwelcome.enabled", false);',
            'user_pref("datareporting.policy.dataSubmissionEnabled", false);',
            'user_pref("datareporting.healthreport.uploadEnabled", false);',
            'user_pref("toolkit.telemetry.enabled", false);',
            'user_pref("layers.acceleration.disabled", true);',
            'user_pref("gfx.webrender.software", true);',
        ]), encoding='utf-8')
        flags = ['firefox', '--no-remote', '--profile', str(PROFILE), '--kiosk', '--private-window']
        # Temporary local diagnostic port; absent from normal deployment.
        if os.environ.get('WT_KIOSK_DEBUG') == '1':
            flags.extend(['--remote-debugging-port', '9222'])
        with (DATA / 'firefox.log').open('a', encoding='utf-8') as browser_log:
            browser = subprocess.Popen(flags + [redirect.as_uri()], stdout=subprocess.DEVNULL, stderr=browser_log)
        print('KIOSK_STARTED: ' + BACKEND + ', local display', flush=True)
        while not stopping:
            if server.poll() is not None:
                raise RuntimeError('Backend exited; restart with fresh local credentials')
            if browser.poll() is not None:
                return 0 if browser.returncode == 0 else 1
            time.sleep(.5)
        return 0
    finally:
        # Stop the controller before closing the display. systemd owns remaining descendants.
        finish(server)
        finish(browser)
        redirect.unlink(missing_ok=True)


if __name__ == '__main__':
    raise SystemExit(main())
