"""Verify the isolated Firefox kiosk using its temporary loopback BiDi port."""
import json
import time
from pathlib import Path
import subprocess
import sys
import websocket

ws = websocket.create_connection('ws://127.0.0.1:9222/session', suppress_origin=True, timeout=15)
seq = 0


def command(method, params):
    global seq
    seq += 1
    ws.send(json.dumps({'id':seq, 'method':method, 'params':params}))
    while True:
        result = json.loads(ws.recv())
        if result.get('id') == seq:
            if result.get('type') == 'error':
                raise RuntimeError(result.get('message', result.get('error')))
            return result['result']


session = command('session.new', {'capabilities': {}})
contexts = command('browsingContext.getTree', {})['contexts']
print('CONTEXTS', [{'url': c['url'].split('#')[0], 'context': c['context']} for c in contexts], flush=True)
context = next(c['context'] for c in contexts if c['url'].startswith('http://127.0.0.1:8765/'))


def evaluate(expression):
    reply = command('script.evaluate', {'expression':'(async()=>JSON.stringify(('+expression+') ?? null))()',
        'target':{'context':context}, 'awaitPromise':True})
    if reply['type'] != 'success':
        raise RuntimeError('Browser evaluation failed')
    return json.loads(reply['result']['value'])


def wait_for(expression, timeout=20):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if evaluate(expression):
            return
        time.sleep(.3)
    raise TimeoutError(expression)


def tap(selector):
    wait_for(f'(()=>{{const e=document.querySelector({json.dumps(selector)});return !!e && !e.disabled && e.getBoundingClientRect().height>0;}})()')
    xy = evaluate(f'(()=>{{const r=document.querySelector({json.dumps(selector)}).getBoundingClientRect();return [Math.round(r.x+r.width/2),Math.round(r.y+r.height/2)];}})()')
    # Physical touch is configured as mouse emulation in this Pi's labwc setup.
    command('input.performActions', {'context':context, 'actions':[{
        'type':'pointer', 'id':'kiosk-pointer', 'parameters':{'pointerType':'mouse'},
        'actions':[{'type':'pointerMove','x':xy[0],'y':xy[1],'duration':0},
                   {'type':'pointerDown','button':0}, {'type':'pointerUp','button':0}]}]})


def screenshot(name):
    output = Path.home() / 'windtunnel-control/evidence'
    subprocess.run(['grim', str(output / name)], check=True)


def main():
    wait_for('document.querySelector("#login").hidden && !document.querySelector("#stop").disabled')
    tap('[data-page="monitor"]')
    details = evaluate('({visibility:document.visibilityState,width:innerWidth,height:innerHeight,loginHidden:document.querySelector("#login").hidden,state:document.querySelector("#system-state").textContent})')
    print('DISPLAY', json.dumps(details, ensure_ascii=True), flush=True)
    assert details['visibility'] == 'visible'
    assert [details['width'], details['height']] == [800,480]
    checks=['authenticated local display visible at 800x480']
    layout = evaluate('({overflow:document.documentElement.scrollWidth>innerWidth,monitorFits:document.querySelector("main").scrollHeight<=document.querySelector("main").clientHeight,stopHeight:document.querySelector("#stop").getBoundingClientRect().height,icons:[...document.querySelectorAll("nav svg use")].every(e=>e.getBBox().width>0)})')
    assert not layout['overflow'] and layout['monitorFits'] and layout['stopHeight'] >= 48 and layout['icons']
    checks.append('no horizontal overflow; monitor fits; stop >=48px; SVG icons render')
    if '--full' in sys.argv:
        tap('[data-page="test"]')
        wait_for('!document.querySelector("#test").hidden')
        tap('#review')
        wait_for('!document.querySelector("#confirmation").hidden')
        tap('#start-run')
        wait_for('document.querySelector("#system-state").textContent.includes("試験中")')
        wait_for('Number(document.querySelector("#rpm").textContent)>100')
        screenshot('pi-sim-running.png')
        wait_for('document.querySelector("#system-state").textContent.includes("停止待機")')
        checks.append('screen pointer actions start finite simulation; automatic completion')
        tap('[data-page="history"]')
        wait_for('document.querySelector(".history-row")?.textContent.includes("完了")')
        checks.append('completed simulation recorded in visible history')
        tap('[data-page="test"]')
        tap('#review')
        tap('#start-run')
        wait_for('document.querySelector("#system-state").textContent.includes("試験中")')
        tap('#stop')
        wait_for('document.querySelector("#system-state").textContent.includes("停止待機")')
        checks.append('screen stop cancels simulation')
        tap('[data-page="settings"]')
        tap('#remote-on')
        wait_for('document.querySelector("#remote-mode").textContent==="ON"')
        tap('#remote-off')
        wait_for('document.querySelector("#remote-mode").textContent==="OFF"')
        screenshot('pi-settings.png')
        checks.append('screen remote mode ON/OFF; final OFF')
        tap('[data-page="monitor"]')
        command('browsingContext.reload', {'context':context,'wait':'complete'})
        wait_for('document.querySelector("#login").hidden && !document.querySelector("#stop").disabled')
        checks.append('reload retains authenticated local session')
    status = evaluate('(await (await fetch("/api/v1/status")).json())')
    assert status['simulation'] and status['state'] == 'IDLE'
    assert not status['remote']['enabled'] and status['pwm_requested_percent'] == 0
    assert status['telemetry']['valid'] and status['telemetry']['age_ms'] < 1500
    checks.append('simulation true; idle; remote OFF; requested PWM 0; telemetry fresh')
    screenshot('pi-final.png')
    output = Path.home() / 'windtunnel-control/evidence'
    name = 'ui-full-result.json' if '--full' in sys.argv else 'ui-status-result.json'
    (output / name).write_text(json.dumps({'passed':True,'browser':session['capabilities'].get('browserVersion'),
        'display':details,'checks':checks,'status':status},ensure_ascii=False,indent=2),encoding='utf-8')
    print('PASS', len(checks), 'checks; simulation only', flush=True)


try:
    main()
finally:
    command('session.end', {})
    ws.close()
