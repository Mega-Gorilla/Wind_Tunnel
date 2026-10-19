"""Finite-run firmware and host contract tests, with fake GPIO/USB only."""
from copy import deepcopy
import importlib.util
import json
import os
from pathlib import Path
import sys
import types

import pytest
from fastapi.testclient import TestClient

from windtunnel.app import create_app
from windtunnel.pico_control import PicoControl, decode_control
from test_api import CODE, ORIGIN, Clock, start, payload
from test_pico import frame


class PicoClock:
    def __init__(self): self.ms=100000
    def ticks_ms(self): return self.ms % (2**30)
    def ticks_us(self): return (self.ms*1000) % (2**30)
    def ticks_diff(self,a,b): return (a-b+2**29) % (2**30)-2**29
    def ticks_add(self,a,b): return (a+b) % (2**30)


@pytest.fixture
def fw(monkeypatch):
    pins={}
    class Pin:
        OUT=1;IN=0
        def __init__(self,n,mode=None,value=None):
            self.n=n
            if value is not None: pins[n]=value
        def value(self,v=None):
            if v is not None: pins[self.n]=v
            return pins.get(self.n,0)
    class WDT:
        def __init__(self,timeout): self.timeout=timeout;self.feeds=0
        def feed(self): self.feeds+=1
    machine=types.SimpleNamespace(Pin=Pin,PWM=object,I2C=object,WDT=WDT,mem32={},
        unique_id=lambda:bytes.fromhex('e660583883976d2d'),reset=lambda:None)
    monkeypatch.setitem(sys.modules,'machine',machine)
    directory=Path(os.environ.get('WT_FIRMWARE_DIR',Path(__file__).resolve().parents[3]/'Electronics/pico/firmware'))
    for name in ('wt_sensors','control_main'):
        spec=importlib.util.spec_from_file_location(name,directory/(name+'.py'))
        module=importlib.util.module_from_spec(spec)
        monkeypatch.setitem(sys.modules,name,module)
        spec.loader.exec_module(module)
    clock=PicoClock();module.time=clock
    class Fan:
        percent=0
        def __init__(self): self.writes=[]
        def set(self,v): self.percent=v;self.writes.append(v)
    class Sensors:
        def __init__(self): self.raw=frame()['raw']
        def sample(self): return deepcopy(self.raw)
    class Tach:
        edges=0; total=0
        def sample(self):
            self.total+=self.edges
            return dict(tach_edges=self.edges,tach_window_us=500000,tach_total_edges=self.total,
                        tach_counter=self.total&65535,tach_hz=self.edges*2,tach_ppr=2)
    c=module.Control(Fan(),Sensors(),Tach());c.acquire()
    return module,c,clock


def arm(fw,duration=10000):
    m,c,_=fw
    r=c.respond(dict(cmd='arm',boot_id=m.BOOT_ID,epoch=c.epoch,duration_ms=duration,run_id='test-run'))
    assert r['ok'],r
    return r


def drive(fw,a,pwm=40,seq=1):
    m,c,_=fw
    return c.respond(dict(cmd='drive',boot_id=m.BOOT_ID,epoch=a['safety_epoch'],arm_id=a['arm_id'],
                          command_seq=seq,pwm_percent=pwm))


def test_arm_drive_stop_and_no_replay(fw):
    m,c,_=fw
    assert not c.respond({'cmd':'drive','pwm_percent':100})['ok'] and c.fan.percent==0
    a=arm(fw); assert c.fan.percent==0 and c.wdt.timeout==3000
    assert drive(fw,a)['fan_command_percent']==40
    r=c.respond({'cmd':'stop'}); assert r['gp16_level']==0 and r['arm_id'] is None
    assert not drive(fw,a,100,2)['ok'] and c.fan.percent==0


@pytest.mark.parametrize('bad',[-1,1,19,101,float('nan'),float('inf'),True])
def test_invalid_pwm_stops_an_armed_run(fw,bad):
    a=arm(fw);drive(fw,a,40)
    r=drive(fw,a,bad,2)
    assert not r['ok'] and r['fan_command_percent']==0 and r['fault']=='PROTOCOL_ERROR'


def test_repeated_command_stops_and_ack_does_not_rearm(fw):
    _,c,_=fw;a=arm(fw);drive(fw,a)
    r=drive(fw,a,40,1)
    assert not r['ok'] and c.fault=='PROTOCOL_ERROR' and c.fan.percent==0
    assert c.respond({'cmd':'ack'})['ok']
    assert c.fault is None and c.arm_id is None


def test_lease_expires_without_pi_or_ui(fw):
    _,c,clock=fw;a=arm(fw);drive(fw,a)
    clock.ms+=2001;c.deadlines()
    assert c.fan.percent==0 and c.fault=='LEASE_EXPIRED' and c.arm_id is None
    assert not drive(fw,a,100,2)['ok']


def test_absolute_run_limit_cannot_be_extended_by_drive(fw):
    _,c,clock=fw;a=arm(fw,1500)
    for seq in (1,2):
        clock.ms+=500;c.acquire();assert drive(fw,a,40,seq)['ok']
    clock.ms+=500;c.deadlines()
    assert c.fault=='RUN_LIMIT' and c.fan.percent==0


def test_ticks_wrap_preserves_timeout(fw):
    _,c,clock=fw;clock.ms=2**30-1000;c.acquire();a=arm(fw);drive(fw,a)
    clock.ms+=2001;c.deadlines()
    assert c.fault=='LEASE_EXPIRED' and c.fan.percent==0


@pytest.mark.parametrize('field,value,reason',[
    ('ina_frame_hex','020025a10005','CURRENT_RANGE'),
    ('ina_frame_hex','000300000000','SUPPLY_RANGE'),
    ('sdp_frame_hex','7ffface1230300f003','PRESSURE_RANGE'),
    ('errors',{'bme':'I2C error'},'SENSOR_ERROR')])
def test_onboard_sensor_faults_stop_before_reply(fw,field,value,reason):
    _,c,clock=fw;a=arm(fw);drive(fw,a)
    c.sensors.raw[field]=value;clock.ms+=500;c.acquire()
    assert c.fault==reason and c.fan.percent==0 and c.arm_id is None


def test_two_high_current_samples_and_missing_tach(fw):
    _,c,clock=fw;a=arm(fw);drive(fw,a)
    c.sensors.raw['ina_frame_hex']='019025a10005'  # 500 mA
    clock.ms+=500;c.acquire();assert c.fan.percent==40
    clock.ms+=500;c.acquire();assert c.fault=='CURRENT_RANGE'


def test_tach_missing_is_detected_after_spinup(fw):
    _,c,clock=fw;a=arm(fw);drive(fw,a)
    clock.ms+=3500;c.acquire()
    assert c.fault=='TACH_MISSING' and c.fan.percent==0


def test_tach_counter_wrap_and_formula(fw):
    m,_,clock=fw
    tach=m.Tach.__new__(m.Tach);tach.t=clock.ticks_us();tach.n=65530;tach.total=100
    m.mem32[m.GPIO15_CTRL]=0x2004;m.mem32[m.PWM7+8]=4
    clock.ms+=500;r=tach.sample()
    assert r['tach_edges']==10 and r['tach_total_edges']==110 and r['tach_hz']==20
    m.mem32[m.GPIO15_CTRL]=0x3004
    with pytest.raises(ValueError,match='TACH_PIN_NOT_INPUT_ONLY'): tach.sample()


def test_decode_actual_tach_and_mixed_window(fw):
    _,c,clock=fw;c.tach.edges=20;clock.ms+=500;c.acquire()
    r=c.respond({'cmd':'sample'});s=decode_control(r,10)
    assert s['rpm_estimated']==1200 and s['tach_edges']==20 and s['tach_window_us']==500000
    assert s['pulses_per_revolution_assumed']==2 and not s['simulation']


class Serial:
    def __init__(self,c): self.c=c;self.sent=[];self.callback=None
    def write(self,data):
        req=json.loads(data);self.sent.append(req)
        reply=self.c.respond(req)
        if self.callback: self.callback(req)
        self.response=(json.dumps(reply)+'\n').encode()
    def read_until(self,*args,**kwargs):
        result=self.response;self.response=b'';return result
    def close(self): pass


def adapter(fw,clock):
    d=PicoControl(clock=clock);d.connection=Serial(fw[1]);d.stop_pending.set();d._cycle()
    assert d.latest['valid'] and d.precheck() is None
    return d


def test_worker_requires_fresh_controller_authority(fw):
    clock=Clock();d=adapter(fw,clock);d.begin_run('test',10);d._cycle()
    assert d.is_armed('test')
    clock.now+=.76;d._cycle();assert d.intent is None and d.pwm==0
    d._cycle();assert fw[1].fan.percent==0 and fw[1].arm_id is None
    assert d.fault=='PICO_CONTROLLER_HEARTBEAT_LOST'


def test_stop_racing_arm_discards_armed_response(fw):
    clock=Clock();d=adapter(fw,clock);d.begin_run('test',10)
    d.connection.callback=lambda req:d.stop() if req['cmd']=='arm' else None
    d._cycle();assert d.armed_run is None and d.intent is None
    d._cycle();assert fw[1].arm_id is None and fw[1].fan.percent==0
    assert not any(r['cmd']=='drive' for r in d.connection.sent)


def test_real_run_waits_for_arm_and_stop_ack(fw,tmp_path):
    clock=Clock();d=adapter(fw,clock)
    app=create_app(tmp_path,CODE,ORIGIN,clock,background=False,device=d)
    with TestClient(app,base_url=ORIGIN,client=('127.0.0.1',1234)) as client:
        r=client.post('/api/v1/local/session',json={'code':CODE},headers={'Origin':ORIGIN})
        client.headers.update({'Origin':ORIGIN,'X-CSRF-Token':r.json()['csrf_token']})
        run=start(client).json();assert run['state']=='ARMING' and fw[1].fan.percent==0
        d._cycle();s=client.get('/api/v1/status').json();assert s['active_run']['state']=='RUNNING'
        d._cycle();assert fw[1].fan.percent==40
        s=client.post('/api/v1/stop',json={}).json();assert s['active_run']['state']=='STOPPING'
        assert client.get('/api/v1/runs/'+run['id']).json()['state']=='STOPPING'
        d._cycle();client.get('/api/v1/status')
        done=client.get('/api/v1/runs/'+run['id']).json()
        assert done['state']=='CANCELLED' and done['stop_acknowledged'] is True and fw[1].fan.percent==0


def test_sw1_off_and_spinning_block_arm(fw):
    _,c,_=fw;c.sensors.raw['ina_frame_hex']='000300000000';c.acquire()
    r=c.respond(dict(cmd='arm',boot_id=fw[0].BOOT_ID,epoch=c.epoch,duration_ms=10000,run_id='test'))
    assert not r['ok'] and r['error']=='SUPPLY_CHECK_SW1' and c.wdt is None


@pytest.mark.parametrize('outcome',['confirmed','fault','timeout'])
def test_completion_requires_stop_ack_without_fault(fw,tmp_path,outcome):
    clock=Clock();d=adapter(fw,clock)
    app=create_app(tmp_path,CODE,ORIGIN,clock,background=False,device=d)
    with TestClient(app,base_url=ORIGIN,client=('127.0.0.1',1234)) as client:
        r=client.post('/api/v1/local/session',json={'code':CODE},headers={'Origin':ORIGIN})
        client.headers.update({'Origin':ORIGIN,'X-CSRF-Token':r.json()['csrf_token']})
        run=start(client).json();d._cycle();client.get('/api/v1/status');d._cycle()
        ctl=app.state.controller
        clock.now+=run['duration_s'];d._publish(fw[1].respond({'cmd':'sample'}));ctl.heartbeat();ctl.tick()
        assert ctl.active['state']=='STOPPING'
        if outcome=='fault': fw[1].stop('CURRENT_RANGE')
        if outcome!='timeout': d._cycle()
        else: clock.now+=3.1;ctl.heartbeat()
        ctl.tick();done=ctl.get_run(run['id'])
        assert done['state']==('COMPLETED' if outcome=='confirmed' else 'FAILED')
        assert done['stop_acknowledged']==(outcome!='timeout')
        if outcome=='fault': assert done['reason']=='PICO_FW_CURRENT_RANGE'
        if outcome=='timeout': assert done['reason']=='PICO_STOP_UNCONFIRMED'


def test_capture_new_acquisition_without_second_two_hz_clock(fw,tmp_path):
    clock=Clock();d=adapter(fw,clock)
    app=create_app(tmp_path,CODE,ORIGIN,clock,background=False,device=d)
    with TestClient(app,base_url=ORIGIN,client=('127.0.0.1',1234)) as client:
        r=client.post('/api/v1/local/session',json={'code':CODE},headers={'Origin':ORIGIN})
        client.headers.update({'Origin':ORIGIN,'X-CSRF-Token':r.json()['csrf_token']})
        run=start(client).json();ctl=app.state.controller
        d._cycle();ctl.tick()
        for advance in (1,1,3):
            for _ in range(advance): fw[1].acquire()
            d._publish(fw[1].respond({'cmd':'sample'}))
            clock.now+=.05;ctl.tick();ctl.tick()
        samples=ctl.store.samples(run['id'])
        assert len(samples)==4 and [s['missed_acquisitions_before'] for s in samples]==[0,0,0,2]
        assert len({s['seq'] for s in samples})==len(samples)
        assert 'pwm_requested_percent' in samples[-1]
