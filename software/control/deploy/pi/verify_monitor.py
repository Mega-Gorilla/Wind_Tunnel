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
    output = Path.home() / 'windtunnel-control/evidence/pico-monitor'
    subprocess.run(['grim', str(output / name)], check=True)


def main():
    wait_for('document.querySelector("#login").hidden && !document.querySelector("#stop").disabled')
    wait_for('document.querySelector("#freshness").textContent.includes("実Pico")',timeout=30)
    tap('[data-page="monitor"]')
    details=evaluate('({visibility:document.visibilityState,width:innerWidth,height:innerHeight,badge:document.querySelector("#mode-badge").textContent,overflow:document.documentElement.scrollWidth>innerWidth,monitorFits:document.querySelector("main").scrollHeight<=document.querySelector("main").clientHeight,stopHeight:document.querySelector("#stop").getBoundingClientRect().height,rpm:document.querySelector("#rpm").textContent})')
    print('DISPLAY',json.dumps(details,ensure_ascii=True),flush=True)
    assert details['visibility']=='visible' and [details['width'],details['height']]==[800,480]
    assert not details['overflow'] and details['monitorFits'] and details['stopHeight']>=48
    assert details['rpm']=='—' and details['badge']=='実測・停止専用'
    checks=['800x480 visible real monitor; fits screen; RPM not falsely zero']
    rows=[]
    for _ in range(30):
        # Sample UI and its most recently rendered status atomically in one browser turn.
        row=evaluate('({status:status,display:{dp:document.querySelector("#dp").textContent,environment:document.querySelector("#environment").textContent,electrical:document.querySelector("#electrical").textContent}})')
        s=row['status']; t=s['telemetry']
        assert not s['simulation'] and s['state']=='IDLE' and not s['fan_control_available']
        assert t['valid'] and t['connected'] and t['age_ms']<1500 and not t['sensor_errors']
        assert s['pwm_requested_percent']==t['pwm_applied_percent']==t['gp16_level']==0
        assert t['rpm_estimated'] is None and t['airspeed_m_s'] is None
        assert abs(float(row['display']['dp'])-t['differential_pressure_pa'])<=.0051
        rows.append(row);time.sleep(1)
    assert len({r['status']['telemetry']['seq'] for r in rows})==30
    checks.append('30 live snapshots; all sensors valid, fresh and GP16 LOW; DP matches UI rounding')
    screenshot('pi-real-monitor.png')
    tap('[data-page="test"]')
    assert evaluate('document.querySelector("#review").disabled && !document.querySelector("#hardware-test-note").hidden')
    checks.append('real run button disabled with explanation')
    result=evaluate('(await fetch("/api/v1/runs/validate",{method:"POST",headers:{"Content-Type":"application/json","X-CSRF-Token":sessionStorage.getItem("wt_csrf")},body:JSON.stringify({name:"denied",steps:[{pwm_percent:40,settle_s:1,record_s:1}],repeat:1})})).status')
    assert result==409
    checks.append('real API recipe validation denied, no PWM sent')
    tap('[data-page="settings"]');tap('#remote-on')
    wait_for('document.querySelector("#remote-mode").textContent==="ON"')
    permitted=evaluate('(await (await fetch("/api/v1/status")).json()).remote')
    assert permitted['enabled'] and permitted['permit']['unlimited'] and permitted['permit']['remaining_s'] is None
    assert evaluate('document.querySelector("#permit-note").textContent.includes("無期限") && document.querySelector("#simulation-faults").hidden')
    time.sleep(1)
    assert evaluate('document.querySelector("#remote-mode").textContent==="ON"')
    screenshot('pi-real-settings.png')
    tap('#remote-off');wait_for('document.querySelector("#remote-mode").textContent==="OFF"')
    checks.append('UI ON unlimited / OFF, simulation injection hidden')
    tap('[data-page="monitor"]')
    command('browsingContext.reload',{'context':context,'wait':'complete'})
    wait_for('document.querySelector("#freshness").textContent.includes("実Pico")')
    checks.append('page reload continues authenticated real acquisition')
    final=evaluate('(await (await fetch("/api/v1/status")).json())')
    assert not final['remote']['enabled'] and final['pwm_requested_percent']==0 and final['telemetry']['valid']
    output=Path.home()/'windtunnel-control/evidence/pico-monitor'
    name='ui-real-result.json'
    (output/name).write_text(json.dumps({'passed':True,'browser':session['capabilities'].get('browserVersion'),'display':details,'checks':checks,'snapshots':rows,'final_status':final},ensure_ascii=False,indent=2),encoding='utf-8')
    print('PASS',len(checks),'real monitor checks',flush=True)
    print('FINAL',json.dumps(final),flush=True)


try:
    main()
finally:
    command('session.end',{})
    ws.close()

