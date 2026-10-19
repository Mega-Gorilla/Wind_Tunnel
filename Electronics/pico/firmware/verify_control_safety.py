"""Pi-only commissioning: <=20% / 10 seconds, then omit drive lease deliberately.

No service may own USB concurrently. Every exit attempts stop. The firmware's
independent 2 s lease and 10 s absolute bound remain in force if this process dies.
"""
import json
from pathlib import Path
import sys
import time
import serial

from windtunnel.pico import PORT
from windtunnel.pico_control import decode_control, validate_control


def main():
    evidence=Path(sys.argv[1]);evidence.mkdir(parents=True,exist_ok=True)
    samples=[];seq=0
    s=serial.Serial(PORT,115200,timeout=.1,write_timeout=.3,exclusive=True)

    def request(cmd,**kw):
        nonlocal seq
        seq+=1;ident='safety-'+str(seq)
        s.write((json.dumps(dict(cmd=cmd,id=ident,**kw))+'\n').encode())
        deadline=time.monotonic()+2;data=b''
        while time.monotonic()<deadline:
            data+=s.read_until(b'\n')
            if not data.endswith(b'\n'):continue
            r=json.loads(data);data=b''
            if r.get('id')!=ident:continue
            validate_control(r)
            assert r['ok'],r.get('error')
            samples.append(dict(host_monotonic_s=time.monotonic(),frame=r))
            return r
        raise TimeoutError('Pico response')

    try:
        s.reset_input_buffer();r=request('stop')
        for _ in range(12):
            time.sleep(.5);r=request('sample')
        t=decode_control(r,time.monotonic())
        assert t['valid'] and t['rpm_estimated']==0 and r['gp16_level']==0,t
        assert 10.8<=t['bus_voltage_v']<=13.2 and -.020<=t['current_a']<=.080,t
        if r['fault']:r=request('ack')
        print('STOPPED_SENSOR_CHECK_PASS',json.dumps(t),flush=True)
        a=request('arm',boot_id=r['boot_id'],epoch=r['safety_epoch'],duration_ms=10000,run_id='commissioning-lease-20pct')
        assert a['watchdog_enabled'] and a['fan_command_percent']==0
        authority=dict(boot_id=a['boot_id'],epoch=a['safety_epoch'],arm_id=a['arm_id'])
        for n in range(1,17):
            r=request('drive',command_seq=n,pwm_percent=20,**authority)
            assert r['fault'] is None and r['fan_command_percent']==20,r
            time.sleep(.25)
        assert decode_control(r,time.monotonic())['rpm_estimated']>200
        last_drive=samples[-1]['host_monotonic_s']
        # Status requests intentionally do not renew the lease.
        while time.monotonic()-last_drive<4:
            r=request('status')
            if r['fault']=='LEASE_EXPIRED':break
            time.sleep(.1)
        observed_stop_delay=time.monotonic()-last_drive
        assert r['fault']=='LEASE_EXPIRED' and r['fan_command_percent']==0 and r['gp16_level']==0 and r['arm_id'] is None,r
        print('INDEPENDENT_LEASE_STOP_PASS',round(observed_stop_delay,3),flush=True)
        for _ in range(30):
            time.sleep(.5);r=request('sample')
            if r['raw']['tach_edges']==0 and r['sample_age_ms']<1000:break
        assert r['raw']['tach_edges']==0,'Wait for coast-down'
        r=request('ack');assert r['fault'] is None and r['arm_id'] is None
        result=dict(passed=True,observed_lease_stop_delay_s=observed_stop_delay,
                    note='Observed via status polling, not oscilloscope timing. WDT configured; hard-hang test not performed.',
                    samples=samples,final=r)
        (evidence/'firmware-safety.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
        print('SAFETY_TEST_PASS_FINAL_STOP',r['raw']['tach_edges'],flush=True)
    finally:
        try:request('stop')
        finally:
            (evidence/'firmware-safety-raw.json').write_text(json.dumps(samples,indent=2),encoding='utf-8')
            s.close()


if __name__=='__main__':main()
