"""No hardware access: protocol, compensation, failure and locked-stop contracts."""
from copy import deepcopy
import importlib.util
import json
import os
from pathlib import Path
import sys
import time
import types

import pytest
from fastapi.testclient import TestClient

from windtunnel.app import create_app
from windtunnel.pico import DEVICE_ID, PicoMonitor, decode_sample, validate_envelope
from windtunnel.sensor_conversion import calibration, compensate_bme, convert_ina, crc8
from test_api import Clock, CODE, ORIGIN, external, start, recipe


def frame():
    # Preserved real bytes from stopped_sw1_on, 2026-10-17; not a live reading.
    return dict(protocol=1, firmware='0.2.0-monitor', device_id=DEVICE_ID,
        boot_id='0123456789abcdef', seq=1, pico_ms=56064, fan_locked_stop=True,
        fan_command_percent=0, fan_enabled=False, gp16_level=0, ok=True, kind='telemetry',
        raw=dict(errors={}, sdp_frame_hex='ffffac16150300f003',
            bme_frame_hex='4b7d0083c5004aa0', ina_frame_hex='000325a10005', ina_flags=8,
            identity=dict(sdp_identity_frame_hex='0302ce0b01aa0000810000819c4227145341',
                bme_cal_88_hex='a36e8b673200fd8ef7d5d00b9e22dafff9ffac260ad8bd10004b',
                bme_cal_e1_hex='9e01000d22031e', bme_chip_id=96,
                ina_manufacturer_id=21577, ina_die_id=8816)))


def test_preserved_bytes_decode_units_and_null_unmeasured():
    s = decode_sample(frame(), 10)
    assert s['valid'] and not s['simulation'] and s['source'] == 'pico_usb'
    assert s['differential_pressure_pa'] == -1/240
    assert s['current_a'] == .00375 and s['power_w'] == .05
    assert s['bus_voltage_v'] == pytest.approx(12.04125)
    assert 20 < s['temperature_c'] < 40 and 0 < s['relative_humidity_percent'] < 100
    assert s['rpm_estimated'] is None and s['airspeed_m_s'] is None
    assert s['gp16_level'] == 0 and s['raw'] == frame()['raw']


@pytest.mark.parametrize('field,value', [('device_id','wrong'),('firmware','0.1.0-commissioning'),
    ('gp16_level',1),('gp16_level',False),('fan_enabled',True),('fan_command_percent',1),
    ('fan_locked_stop',False),('seq',0),('seq',True),('pico_ms',-1),('boot_id','bad'),('ok',False)])
def test_reject_bad_envelope(field, value):
    f = frame(); f[field] = value
    with pytest.raises(ValueError):
        validate_envelope(f)


@pytest.mark.parametrize('name,field,value', [('sdp','sdp_frame_hex','000000000000000000'),
    ('bme','bme_frame_hex','00'),('bme','bme_frame_hex','8000008000008000'),
    ('ina','ina_flags',4),('ina','ina_flags',0),('ina','ina_frame_hex','000080000000')])
def test_independent_sensor_failure(name, field, value):
    f = frame(); f['raw'][field] = value
    s = decode_sample(f, 10)
    assert not s['valid'] and set(s['sensor_errors']) == {name}
    key = {'sdp':'differential_pressure_pa','bme':'temperature_c','ina':'current_a'}
    for sensor in key:
        assert (s[key[sensor]] is None) == (sensor == name)


def test_warmup_is_distinct_and_other_values_available():
    f = frame(); f['raw']['errors']['sdp'] = 'WARMING_UP'
    s = decode_sample(f, 10)
    assert s['reason'] == 'WARMING_UP' and s['temperature_c'] is not None
    assert s['differential_pressure_pa'] is None


def test_datasheet_conversion_vectors():
    assert crc8(bytes.fromhex('beef')) == 0x92
    c = dict(T1=27504,T2=26435,T3=-1000,P1=36477,P2=-10685,P3=3024,P4=2855,
             P5=140,P6=-7,P7=15500,P8=-14600,P9=6000,H1=75,H2=362,H3=0,H4=334,H5=50,H6=30)
    v = compensate_bme(519888,415148,30000,c)
    assert v['temperature_c'] == pytest.approx(25.08248, abs=.0001)
    assert v['pressure_pa'] == pytest.approx(100653.27, abs=.1)
    assert convert_ina(bytes.fromhex('271025703a7f')) == dict(current_ma=12500.,bus_voltage_v=11.98,power_w=149.75)
    assert convert_ina(bytes.fromhex('ffff25800001'))['current_ma'] == -1.25
    with pytest.raises(ValueError): calibration(bytes(26),bytes(7))


class FragmentedSerial:
    def __init__(self):
        self.seq = 0
    def write(self, data):
        request = json.loads(data)
        assert request['cmd'] in ('sample','stop')
        f = frame(); self.seq += 1; f.update(id=request['id'],seq=self.seq)
        self.parts = [b'{"id":"stale"}\n']
        data = (json.dumps(f)+'\n').encode()
        self.parts += [data[n:n+31] for n in range(0,len(data),31)]
    def read_until(self, *args, **kwargs):
        return self.parts.pop(0) if self.parts else b''


def test_serial_fragmentation_stale_reply_sequence_and_stop_only():
    d = PicoMonitor(); d.connection = FragmentedSerial()
    assert d._exchange('sample')['seq'] == 1
    assert d._exchange('stop')['seq'] == 2
    d.connection.seq = 0
    with pytest.raises(ValueError,match='PICO_SEQUENCE'): d._exchange('sample')
    with pytest.raises(ValueError,match='HARDWARE_MONITOR_ONLY'): d.set_pwm(1)
    assert d.pwm == 0


def test_freshness_never_refreshed_by_polling():
    d = PicoMonitor(); d.latest = decode_sample(frame(),10)
    assert d.sample(10.5,0)['valid']
    s = d.sample(12,0)
    assert not s['valid'] and s['reason']=='PICO_STALE' and s['monotonic_s']==10


def test_worker_reconnects_after_failed_open_and_only_sends_safe_commands():
    attempts=[]; closed=[]
    class Connection(FragmentedSerial):
        def reset_input_buffer(self): pass
        def close(self): closed.append(True)
    def factory(*args,**kwargs):
        attempts.append(True)
        assert kwargs['exclusive'] is True
        if len(attempts)==1: raise OSError('USB disconnected')
        return Connection()
    d=PicoMonitor(serial_factory=factory)
    d.set_pwm(0);d.start()
    try:
        deadline=time.monotonic()+4
        while time.monotonic()<deadline and not d.sample(time.monotonic(),0)['valid']: time.sleep(.02)
        assert len(attempts)==2 and d.latest['valid'] and d.fault=='none' and d.pwm==0
    finally: d.close()
    assert closed and not d.thread.is_alive()


def test_real_api_rejects_operation_and_revokes_on_disconnect(tmp_path):
    clock = Clock(); d = PicoMonitor(clock=clock); d.latest = decode_sample(frame(),clock())
    app = create_app(tmp_path,CODE,ORIGIN,clock,background=False,device=d)
    with TestClient(app,base_url=ORIGIN,client=('127.0.0.1',1234)) as local:
        r = local.post('/api/v1/local/session',json={'code':CODE},headers={'Origin':ORIGIN})
        local.headers.update({'Origin':ORIGIN,'X-CSRF-Token':r.json()['csrf_token']})
        assert not r.json()['simulation']
        remote,_ = external((app,local,clock))
        assert local.post('/api/v1/control/remote-permit',json={}).status_code == 200
        for client in (local,remote):
            assert start(client).json()['code'] == 'HARDWARE_MONITOR_ONLY'
            assert client.post('/api/v1/runs/validate',json=recipe()).status_code == 409
        assert local.post('/api/v1/local/simulation/fault',json={'fault':'none'}).status_code == 409
        d._failure('PICO_DISCONNECTED'); clock.now += .5
        s = local.get('/api/v1/status').json()
        assert s['fault']=='PICO_DISCONNECTED' and not s['remote']['enabled']
        assert s['telemetry']['temperature_c'] is None
        assert local.post('/api/v1/faults/acknowledge',json={}).status_code == 409
        d.latest = decode_sample(frame(),clock()); d.problem='none'; clock.now += .5
        assert local.post('/api/v1/faults/acknowledge',json={}).status_code == 200
        assert not local.get('/api/v1/status').json()['remote']['enabled']
        assert local.get('/api/v1/runs').json()['items']==[]
    assert (tmp_path/'monitor.sqlite3').exists() and not (tmp_path/'simulation.sqlite3').exists()


def test_expired_local_session_cannot_renew(tmp_path):
    clock=Clock(); app=create_app(tmp_path,CODE,ORIGIN,clock,background=False)
    with TestClient(app,base_url=ORIGIN,client=('127.0.0.1',1)) as client:
        r=client.post('/api/v1/local/session',json={'code':CODE},headers={'Origin':ORIGIN})
        client.headers.update({'Origin':ORIGIN,'X-CSRF-Token':r.json()['csrf_token']})
        clock.now += 8*3600+1
        assert client.post('/api/v1/local/heartbeat',json={}).status_code==401


def test_firmware_never_drives_gp16_high(monkeypatch):
    path=Path(os.environ.get('WT_MONITOR_FIRMWARE',Path(__file__).resolve().parents[3]/'Electronics/pico/firmware/monitor_main.py'))
    writes=[]
    class Pin:
        OUT=1
        def __init__(self,number,mode=None,value=None):
            self.number=number; self.level=value
            if number==16 and value is not None: writes.append(value)
        def value(self,value=None):
            if value is not None:
                self.level=value
                if self.number==16: writes.append(value)
            return self.level
    monkeypatch.setitem(sys.modules,'machine',types.SimpleNamespace(Pin=Pin,I2C=object,unique_id=lambda:bytes.fromhex(DEVICE_ID)))
    monkeypatch.setattr(time,'ticks_ms',lambda:100,raising=False)
    spec=importlib.util.spec_from_file_location('monitor_firmware_under_test',path)
    module=importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    m=module.Monitor(); m.sensors=types.SimpleNamespace(sample=lambda:frame()['raw'])
    for cmd in ('run','pwm','set_pwm','fan','unknown'):
        assert m.respond({'cmd':cmd,'pwm':100})['error']=='FAN_LOCKED_STOP'
    for cmd in ('stop','status','sample'):
        r=m.respond({'cmd':cmd}); validate_envelope(r)
        assert r['gp16_level']==0
    assert writes and set(writes)=={0}
