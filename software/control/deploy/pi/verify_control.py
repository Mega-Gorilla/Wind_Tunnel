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


def input_value(selector,value):
    evaluate('(()=>{const e=document.querySelector('+json.dumps(selector)+');e.value='+json.dumps(str(value))+';e.dispatchEvent(new Event("input",{bubbles:true}));return true;})()')


def prepare(name,pwms,settle=3,record=5):
    tap('[data-page="test"]')
    if len(pwms)>1:
        tap('#preset')
    else:
        evaluate('(()=>{document.querySelectorAll("#steps tr").forEach((r,i)=>{if(i)r.remove()});return true;})()')
    input_value('#test-name',name)
    for i,pwm in enumerate(pwms,1):
        input_value(f'#steps tr:nth-child({i}) input[aria-label="PWM"]',pwm)
        input_value(f'#steps tr:nth-child({i}) input[aria-label="整定待ち秒"]',settle)
        input_value(f'#steps tr:nth-child({i}) input[aria-label="収録秒"]',record)
    evaluate('(()=>{document.querySelector("#review").scrollIntoView({block:"center"});return true;})()')
    tap('#review')
    wait_for('!document.querySelector("#confirmation").hidden')
    assert '実機ファンが回転します' in evaluate('document.querySelector("#confirm-text").textContent')
    tap('#start-run')
    wait_for('document.querySelector("#monitor").hidden===false')
    wait_for('(await (await fetch("/api/v1/status")).json()).active_run!=null')
    return status()['active_run']['id']


def collect(run_id,cancel_after=None):
    rows=[];start=time.monotonic();cancelled=False;saved=False
    while time.monotonic()-start<75:
        s=status();rows.append(s)
        if s['fault']:raise AssertionError(s['fault'])
        if s['active_run'] is None:break
        if s['telemetry']['rpm_estimated'] and s['telemetry']['rpm_estimated']>300 and not saved:
            screenshot('pico-control/pi-running-'+run_id[:8]+'.png');saved=True
        if cancel_after and time.monotonic()-start>cancel_after and not cancelled:
            tap('#stop');cancelled=True
        time.sleep(.5)
    assert rows[-1]['active_run'] is None,'Run did not terminate'
    run=evaluate('(await (await fetch("/api/v1/runs/'+run_id+'")).json())')
    assert run['state']==('CANCELLED' if cancel_after else 'COMPLETED'),run
    assert run['stop_acknowledged'] is True
    exported=evaluate('(await (await fetch("/api/v1/runs/'+run_id+'/export?format=json")).json())')
    assert all(s['valid'] for s in exported['samples'])
    assert all(s['missed_acquisitions_before']==0 for s in exported['samples']), 'Acquisition gap'
    assert len({(s['boot_id'],s['seq']) for s in exported['samples']})==len(exported['samples'])
    csv=evaluate('(await (await fetch("/api/v1/runs/'+run_id+'/export?format=csv")).text())')
    assert 'pulses_per_revolution_assumed' in csv and 'pwm_requested_percent' in csv
    out=Path.home()/'windtunnel-control/evidence/pico-control'
    (out/(run_id+'.json')).write_text(json.dumps(exported,indent=2),encoding='utf-8')
    (out/(run_id+'.csv')).write_text(csv,encoding='utf-8')
    (out/(run_id+'-observed.json')).write_text(json.dumps(rows,indent=2),encoding='utf-8')
    deadline=time.monotonic()+20
    zero_count=0
    while time.monotonic()<deadline:
        s=status()
        assert s['pwm_requested_percent']==0 and not s['fault']
        if s['telemetry']['rpm_estimated']==0 and s['telemetry']['pwm_applied_percent']==0:
            zero_count+=1
            if zero_count>=3:break
        else:zero_count=0
        time.sleep(.6)
    assert zero_count>=3,'Tach did not reach zero after coast-down'
    print('RUN_PASS',run_id,run['state'],len(rows),'observations',flush=True)
    return dict(run=run,observed=rows)


def main():
    output=Path.home()/'windtunnel-control/evidence/pico-control'
    wait_for('document.querySelector("#login").hidden && !document.querySelector("#stop").disabled',timeout=60)
    wait_for('(await (await fetch("/api/v1/status")).json()).telemetry.valid',timeout=20)
    tap('[data-page="monitor"]')
    details=evaluate('({visibility:document.visibilityState,width:innerWidth,height:innerHeight,badge:document.querySelector("#mode-badge").textContent,overflow:document.documentElement.scrollWidth>innerWidth,monitorFits:document.querySelector("main").scrollHeight<=document.querySelector("main").clientHeight,stopHeight:document.querySelector("#stop").getBoundingClientRect().height})')
    assert details['visibility']=='visible' and [details['width'],details['height']]==[800,480],details
    assert not details['overflow'] and details['monitorFits'] and details['stopHeight']>=48,details
    s=status();assert not s['simulation'] and s['fan_control_available'] and s['telemetry']['rpm_estimated']==0 and not s['fault'],s
    assert not s['remote']['enabled'] and s['pwm_requested_percent']==0
    print('UI_READY',json.dumps(details,ensure_ascii=True),flush=True)
    results=[]
    if '--status' not in sys.argv:
        first=prepare('実機UI低速確認',[20])
        results.append(collect(first))
        second=prepare('実機UI 20-100% 段階検証',[20,40,60,80,100],settle=4,record=6)
        results.append(collect(second))
        third=prepare('実機UI停止ボタン確認',[40],settle=3,record=15)
        results.append(collect(third,cancel_after=5))
        tap('[data-page="history"]')
        wait_for('document.querySelector(".history-row")?.textContent.includes("実測試験")')
        screenshot('pico-control/pi-history.png')
        tap('[data-page="monitor"]')
    s=status()
    assert s['state']=='IDLE' and s['telemetry']['valid'] and s['telemetry']['rpm_estimated']==0
    assert s['pwm_requested_percent']==0 and s['telemetry']['pwm_applied_percent']==0 and not s['remote']['enabled']
    screenshot('pico-control/pi-final.png')
    result=dict(passed=True,display=details,runs=results,final=s)
    (output/('ui-status.json' if '--status' in sys.argv else 'ui-control-result.json')).write_text(json.dumps(result,indent=2),encoding='utf-8')
    print('UI_CONTROL_PASS',len(results),'runs; final PWM=0 RPM=0 remote=OFF',flush=True)


try:
    main()
finally:
    # Stop through the same authenticated UI on any test failure as well.
    try:tap('#stop')
    except Exception:pass
    command('session.end',{})
    ws.close()
