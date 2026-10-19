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
    # DOM completion precedes Firefox/Wayland compositing on this Pi.
    evaluate('await new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r)))')
    time.sleep(.4)
    subprocess.run(['grim', str(output / name)], check=True)




def status():
    return evaluate('(await (await fetch("/api/v1/status")).json())')


def scroll_to(selector):
    evaluate('(()=>{document.querySelector('+json.dumps(selector)+').scrollIntoView({block:"center"});return true;})()')
    time.sleep(.2)


def drag(x,y,dy):
    actions=[{'type':'pointerMove','x':int(x),'y':int(y),'duration':0},{'type':'pointerDown','button':0}]
    for i in range(1,13):
        actions.append({'type':'pointerMove','x':int(x),'y':int(y+dy*i/12),'duration':25})
    actions.append({'type':'pointerUp','button':0})
    command('input.performActions',{'context':context,'actions':[{'type':'pointer','id':'kiosk-pointer','parameters':{'pointerType':'mouse'},'actions':actions}]})
    time.sleep(.2)


def drag_from(selector,dy):
    r=evaluate('(()=>{const r=document.querySelector('+json.dumps(selector)+').getBoundingClientRect();return {x:r.x+r.width/2,y:r.y+r.height/2};})()')
    drag(r['x'],r['y'],dy)


def key(label):
    # Address by the observed aria-label, retaining real pointer input.
    tap('#touch-keys button[aria-label='+json.dumps(label,ensure_ascii=False)+']')


def main():
    out=Path.home()/'windtunnel-control/evidence/touch-ui'
    out.mkdir(parents=True,exist_ok=True)
    wait_for('document.querySelector("#login").hidden && !document.querySelector("#stop").disabled',timeout=60)
    wait_for('(await (await fetch("/api/v1/status")).json()).telemetry.valid')
    before=status()
    assert before['state']=='IDLE' and before['telemetry']['rpm_estimated']==0 and not before['remote']['enabled'],before
    command('browsingContext.reload',{'context':context,'wait':'complete'})
    wait_for('document.querySelector("#login").hidden && !document.querySelector("#stop").disabled')
    evaluate('(()=>{window.touchTestRequests=[];const original=window.fetch;window.fetch=(url,options)=>{if(options?.method==="POST")window.touchTestRequests.push(String(url));return original(url,options);};return true;})()')
    checks=[]
    tap('[data-page="settings"]')
    assert evaluate('document.querySelector("#touch-keyboard-enabled").checked')
    drag(740,360,-200)
    assert evaluate('document.querySelector("main").scrollTop')>100
    drag(740,150,180)
    checks.append('settings drag scrolling with Pi mouse-emulated touch event path')
    scroll_to('#remote-on');drag_from('#remote-on',-100)
    assert status()['remote']['enabled'] is False
    tap('#stop');tap('#message-close')
    checks.append('remote ON drag suppressed; stop accessible immediately afterwards')
    tap('[data-page="test"]');tap('#preset')
    scroll_to('#steps tr:nth-child(2) td:last-child button')
    drag_from('#steps tr:nth-child(2) td:last-child button',-100)
    assert evaluate('document.querySelectorAll("#steps tr").length')==5
    checks.append('table drag does not delete row')
    time.sleep(.5)
    scroll_to('#steps tr:first-child input[aria-label="PWM"]')
    tap('#steps tr:first-child input[aria-label="PWM"]')
    wait_for('!document.querySelector("#touch-editor").hidden')
    assert evaluate('document.querySelector("main").inert')
    key('6');key('0')
    assert evaluate('document.querySelector("#touch-value").value')=='60'
    assert evaluate('document.querySelector("#steps tr:first-child input").value')=='20'
    screenshot('touch-ui/pi-keypad.png')
    key('入力を決定')
    assert evaluate('document.querySelector("#steps tr:first-child input").value')=='60'
    checks.append('numeric screen keyboard commits draft; background is inert; stop unobstructed')
    tap('#steps tr:first-child input[aria-label="PWM"]')
    key('1');key('0');key('1');key('入力を決定')
    assert evaluate('document.querySelector("#touch-hint").dataset.error==="true"')
    tap('#stop');tap('#message-close')
    assert evaluate('document.querySelector("#touch-editor").hidden')
    assert evaluate('document.querySelector("#steps tr:first-child input").value')=='60'
    checks.append('range error rejected; stop cancels pending keyboard edits')
    scroll_to('#test-name');tap('#test-name');wait_for('!document.querySelector("#touch-editor").hidden')
    for c in 'test':key(c)
    key('英字と数字記号を切替');key('1')
    screenshot('touch-ui/pi-keyboard.png')
    key('入力を決定')
    assert evaluate('document.querySelector("#test-name").value')=='test1'
    checks.append('text and symbol keyboard')
    scroll_to('#review');tap('#review');wait_for('!document.querySelector("#confirmation").hidden')
    drag_from('#start-run',-90);time.sleep(.5)
    assert status()['active_run'] is None
    tap('#dismiss')
    assert not evaluate('window.touchTestRequests.some(p=>p==="/api/v1/runs" || p==="/api/v1/control/remote-permit")')
    checks.append('drag from start never starts fan; no start/remote-permit requests')
    tap('[data-page="history"]');wait_for('document.querySelector(".history-row")!=null')
    drag(740,360,-180)
    assert evaluate('document.querySelector("main").scrollTop')>100
    checks.append('existing real history scrolls without changing runs')
    screenshot('touch-ui/pi-history-scroll.png')
    # Reload clears draft edits; stored measurements remain untouched.
    command('browsingContext.reload',{'context':context,'wait':'complete'})
    wait_for('document.querySelector("#login").hidden && !document.querySelector("#stop").disabled')
    tap('[data-page="monitor"]')
    final=status()
    assert final['state']=='IDLE' and final['telemetry']['valid'] and final['telemetry']['rpm_estimated']==0
    assert final['pwm_requested_percent']==0 and final['telemetry']['pwm_applied_percent']==0 and not final['remote']['enabled']
    details=evaluate('({width:innerWidth,height:innerHeight,stopHeight:document.querySelector("#stop").getBoundingClientRect().height,overflow:document.documentElement.scrollWidth>innerWidth})')
    assert [details['width'],details['height']]==[800,480] and details['stopHeight']>=48 and not details['overflow']
    checks.append('reload retains authenticated stop-only test state, fixed stop and 800x480 layout')
    screenshot('touch-ui/pi-final.png')
    (out/'ui-touch-result.json').write_text(json.dumps(dict(passed=True,checks=checks,display=details,final=final),indent=2),encoding='utf-8')
    print('PI_TOUCH_PASS',len(checks),'checks; PWM=0 RPM=0; no run started',flush=True)


try:
    main()
finally:
    command('session.end',{})
    ws.close()
