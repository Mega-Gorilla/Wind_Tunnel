"""Recompute and validate all captured values; no hardware operations."""
from pathlib import Path
import sys, json, hashlib, statistics, math
BASE=Path(__file__).resolve().parent
ROOT=BASE.parents[2]
sys.path.insert(0,str(ROOT/'hardware/pico/diagnostics'))
from compensation import crc8,signed,convert_ina,calibration,compensate_bme,summarize

folder=BASE.parent/'fan_fullrange'
raw=json.loads((folder/'raw.json').read_text(encoding='utf-8'))
source=(folder/'fan_steps.py').read_bytes()
assert hashlib.sha256(source).hexdigest()==raw['source_sha256']
assert source==(BASE/'fan_steps.py').read_bytes()
assert not raw.get('host_error'),raw.get('host_error')
records=[r['data'] for r in raw['records']]
assert not [r for r in records if r.get('kind')=='fatal']
start,=[r for r in records if r.get('kind')=='start']
identity,=[r for r in records if r.get('kind')=='identity']
done,=[r for r in records if r.get('kind')=='done']
assert not done['errors'] and done['gp16_level']==0
assert done['ina_restored_config']==start['ina_original_config']
assert done['bme_restored_registers']==identity['bme_original_registers']
assert identity['ina_manufacturer_id']==0x5449 and identity['ina_die_id']>>4==0x227
assert identity['bme_chip_id']==0x60
assert raw['after']['status']['gp16_level']==0
assert raw['after']['status']['fan_enabled'] is False
assert raw['after']['status']['firmware']=='0.1.0-commissioning'
cal=calibration(bytes.fromhex(identity['bme_cal_88_hex']),bytes.fromhex(identity['bme_cal_e1_hex']))
samples=[]
for entry in raw['records']:
    r=entry['data']
    if r.get('kind')!='sample': continue
    sdp=bytes.fromhex(r['sdp_frame_hex']); bme=bytes.fromhex(r['bme_frame_hex'])
    assert len(sdp)==9 and len(bme)==8
    assert all(crc8(sdp[i:i+2])==sdp[i+2] for i in (0,3,6))
    assert int.from_bytes(sdp[6:8],'big')==240
    assert r['bme_status']&9==0
    assert r['ina_flags']&8 and not r['ina_flags']&4
    row=dict(r,pi_received_at=entry['pi_received_at'])
    row.update(convert_ina(bytes.fromhex(r['ina_frame_hex'])))
    row.update(compensate_bme(int.from_bytes(bme[3:6],'big')>>4,int.from_bytes(bme[:3],'big')>>4,int.from_bytes(bme[6:8],'big'),cal))
    row['differential_pressure_pa']=signed(int.from_bytes(sdp[:2],'big'),16)/240
    row['sdp_chip_temperature_c']=signed(int.from_bytes(sdp[3:5],'big'),16)/200
    row['tach_hz']=r['tach_edges']*1e6/r['tach_window_us']
    row['rpm_assuming_2ppr']=row['tach_hz']*30
    assert all(math.isfinite(v) for v in (row['temperature_c'],row['pressure_pa'],row['humidity_pct']))
    assert 10.8<=row['bus_voltage_v']<=13.2 and -20<=row['current_ma']<=600
    assert abs(row['differential_pressure_pa'])<=100
    samples.append(row)
keys=['current_ma','bus_voltage_v','power_w','differential_pressure_pa','temperature_c','humidity_pct','pressure_pa','sdp_chip_temperature_c']
def stats(rows):
    return {k:dict(mean=statistics.mean(r[k] for r in rows),min=min(r[k] for r in rows),max=max(r[k] for r in rows),sample_stdev=statistics.stdev(r[k] for r in rows)) for k in keys}
phases=[]
for phase,(duty,seconds) in enumerate(start['stages']):
    rr=[r for r in samples if r['phase']==phase]
    assert len(rr)==seconds*2 and [r['index'] for r in rr]==list(range(seconds*2))
    assert all(r['command_percent']==duty for r in rr)
    assert all(abs(r['duty_u16']-round(65535*duty/100))<=1 for r in rr)
    chosen=rr[-4:] if phase==0 else rr[-10:]
    edges=sum(r['tach_edges'] for r in chosen); duration=sum(r['tach_window_us'] for r in chosen)/1e6
    phases.append(dict(phase=phase,command_percent=duty,stage_seconds=seconds,sample_count=len(rr),
                       selected_indices=[r['index'] for r in chosen],selected_sample_count=len(chosen),
                       tach_edges=edges,tach_window_s=duration,tach_hz=edges/duration,
                       rpm_assuming_2ppr=edges/duration*30,metrics=stats(chosen)))
assert len(samples)==134
assert phases[0]['tach_edges']==0 and phases[-1]['tach_edges']==0
assert all(p['tach_edges']>0 for p in phases[1:-1])
assert all(a['rpm_assuming_2ppr']<b['rpm_assuming_2ppr'] for a,b in zip(phases[1:5],phases[2:6]))
result=dict(started_at=raw['started_at'],finished_at=raw['finished_at'],
            source_sha256=raw['source_sha256'],sample_count=len(samples),sensor_count=3,
            sample_errors=0,crc_errors=0,final_tach_edges=0,final_tach_window_s=phases[-1]['tach_window_s'],
            all_samples_metrics=stats(samples),phases=phases,done=done,after=raw['after'],
            calibration=cal,samples=samples,
            notes=['Each sensor is read sequentially within a nominal 0.5 second cycle, not simultaneously.',
                   'Each running phase is 10 s; summaries use only the last approximately 5 s, not a certified steady-state test.',
                   'Tach is counted by the Pico RP2040 PWM7 B hardware counter, not by Pi GPIO or an oscilloscope.',
                   'RPM assumes 2 pulses/revolution and is not independently calibrated.',
                   'PWM values are software duty commands; the fan connector waveform was not measured.',
                   'Signed SDP pressure retained; pressure ports/tubing and Pitot orientation not verified; no velocity conversion.',
                   'BME pressure is local absolute pressure, not sea-level corrected. Temperature may reflect installation heating.',
                   'INA260 is a fan-branch measurement, not total system power. Resolution: current 1.25 mA, power 10 mW.',
                   'Pico flash untouched. RAM program exits by hard reset to commissioning locked-stop firmware.',
                   'No long endurance, unplug/fault injection, overcurrent trip or independent calibration test performed.'])
(folder/'summary.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({k:v for k,v in result.items() if k not in ('samples','calibration','notes')},ensure_ascii=False,indent=2))
