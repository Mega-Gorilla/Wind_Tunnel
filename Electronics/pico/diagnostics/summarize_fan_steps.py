"""Recompute bounded fan test data on the host from preserved sensor bytes."""
import argparse
import hashlib
import json
from pathlib import Path
import statistics
from compensation import crc8, signed, convert_ina


def analyze(folder):
    raw = json.loads((folder / 'raw.json').read_text(encoding='utf-8'))
    assert hashlib.sha256((folder / 'fan_steps.py').read_bytes()).hexdigest() == raw['source_sha256']
    records = [x['data'] for x in raw['records']]
    assert not raw.get('host_error')
    assert not any(r['kind'] == 'fatal' for r in records)
    done = [r for r in records if r['kind'] == 'done']
    assert len(done) == 1 and not done[0]['errors'] and done[0]['gp16_level'] == 0
    assert raw['after']['status']['gp16_level'] == 0
    assert raw['after']['status']['fan_enabled'] is False
    samples = []
    for r in records:
        if r['kind'] != 'sample':
            continue
        frame = bytes.fromhex(r['sdp_frame_hex'])
        assert len(frame) == 9
        assert all(crc8(frame[i:i+2]) == frame[i+2] for i in (0, 3, 6))
        assert int.from_bytes(frame[6:8], 'big') == 240
        assert r['ina_flags'] & 8 and not r['ina_flags'] & 4
        row = dict(r)
        row.update(convert_ina(bytes.fromhex(r['ina_frame_hex'])))
        row['differential_pressure_pa'] = signed(int.from_bytes(frame[:2], 'big'), 16) / 240
        row['tach_hz'] = r['tach_edges'] * 1e6 / r['tach_window_us']
        row['rpm_assuming_2ppr'] = row['tach_hz'] * 30
        samples.append(row)
    phase_summaries = []
    for phase, expected in enumerate((6, 10, 10, 10, 16)):
        all_rows = [r for r in samples if r['phase'] == phase]
        assert len(all_rows) == expected
        assert [r['index'] for r in all_rows] == list(range(expected))
        start_index = 12 if phase == 4 else 4
        selected = [r for r in all_rows if r['index'] >= start_index]
        edges = sum(r['tach_edges'] for r in selected)
        window = sum(r['tach_window_us'] for r in selected) / 1e6
        metrics = {}
        for key in ('current_ma', 'bus_voltage_v', 'power_w', 'differential_pressure_pa'):
            values = [r[key] for r in selected]
            metrics[key] = dict(mean=statistics.mean(values), min=min(values), max=max(values))
        phase_summaries.append(dict(phase=phase, command_percent=selected[0]['command_percent'],
                                    selected_indices=[r['index'] for r in selected],
                                    tach_edges=edges, tach_window_s=window,
                                    tach_hz=edges / window,
                                    rpm_assuming_2ppr=edges / window * 30, metrics=metrics))
    last = phase_summaries[-1]
    summary = dict(started_at=raw['started_at'], finished_at=raw['finished_at'],
                   samples_count=len(samples), crc_errors=0, phases=phase_summaries,
                   final_tach_zero_in_selected_window=last['tach_edges'] == 0,
                   before=raw['before'], after=raw['after'], done=done[0],
                   notes=['Tach: RP2040 PWM slice 7 B falling-edge hardware counter on GP15.',
                          'GP15 output is explicitly disabled by OEOVER throughout counting.',
                          'RPM assumes two Tach pulses/revolution; not independently calibrated.',
                          'Running rows exclude the first approximately two seconds of each step.',
                          'Final stop summary uses the last approximately two seconds.',
                          'Duty is the software command at GP16, not an oscilloscope measurement at the fan.',
                          'SDP pressure is signed raw calibrated output; no zero subtraction or wind-speed conversion.',
                          'Negative pressure can result from pressure-port/tube conditions; cause not established.',
                          'Temporary RAM code; fan reset to locked-stop firmware; no permanent run commands installed.'])
    (folder / 'summary.json').write_text(json.dumps(summary, indent=2), encoding='utf-8')
    print(json.dumps(summary, indent=2))
    return summary


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('folder', type=Path)
    analyze(parser.parse_args().folder)
