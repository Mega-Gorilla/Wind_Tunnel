"""Read-only analysis of saved measurements; does not connect to hardware."""
import json
import statistics
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
ROOT = BASE.parents[1]
raw = json.loads((BASE / 'fan_fullrange/raw.json').read_text(encoding='utf-8'))
summary = json.loads((BASE / 'fan_fullrange/summary.json').read_text(encoding='utf-8'))
rows = [e['data'] for e in raw['records'] if e['data'].get('kind') == 'sample']
assert len(rows) == 134 and not raw.get('host_error')
assert not any(e['data'].get('kind') == 'fatal' for e in raw['records'])
checked_pairs = 0
for previous, current in zip(rows, rows[1:]):
    if previous['phase'] == current['phase']:
        assert ((current['tach_counter'] - previous['tach_counter']) & 0xffff) == current['tach_edges']
        assert current['index'] == previous['index'] + 1
        checked_pairs += 1
for row in rows:
    hz = row['tach_edges'] * 1e6 / row['tach_window_us']
    assert abs(hz - row['tach_hz']) < 0.001
    assert abs(hz * 30 - row['rpm_assuming_2ppr']) < 0.01
assert len({(r['phase'], r['index']) for r in rows}) == len(rows)

def window_report(group):
    windows = [r['tach_window_us'] / 1e6 for r in group]
    return {
        'sample_count': len(group), 'duration_s': sum(windows),
        'total_edges': sum(r['tach_edges'] for r in group),
        'zero_edge_windows': sum(r['tach_edges'] == 0 for r in group),
        'sampled_gpio_levels': sorted({r['tach_level'] for r in group}),
        'counter_min': min(r['tach_counter'] for r in group),
        'counter_max': max(r['tach_counter'] for r in group),
        'window_s_min': min(windows), 'window_s_max': max(windows),
        'frequency_hz_min': min(r['tach_edges'] / t for r, t in zip(group, windows)),
        'frequency_hz_max': max(r['tach_edges'] / t for r, t in zip(group, windows)),
    }

initial = [r for r in rows if r['phase'] == 0]
active = [r for r in rows if r['command_percent'] > 0]
final = [r for r in rows if r['phase'] == 6]
last_nonzero = max(i for i, r in enumerate(final) if r['tach_edges'])
suffix = final[last_nonzero + 1:]
assert initial and suffix and all(r['tach_edges'] == 0 for r in initial + suffix)
old = {}
for condition, folder in [('low', '174103'), ('high', '174151'), ('50hz', '174244')]:
    path = ROOT / ('measurements/simultaneous_20260911_' + folder) / 'settled_analysis.json'
    s = json.loads(path.read_text(encoding='utf-8'))
    old[condition] = {
        'source': str(path.relative_to(ROOT)), 'pi_saved_events': s['pi_saved_events'],
        'pi_status': s['pi_status'], 'pi_request_ms': s['pi_request_ms'],
        'pi_event_span_ms': s['pi_event_span_ms'],
        'scope_steady_min_v': s['scope_steady_min_v'],
        'scope_steady_max_v': s['scope_steady_max_v'],
        'scope_steady_median_v': s['scope_steady_median_v'],
        'scope_period_ms_median': statistics.median(s['scope_period_ms']) if s['scope_period_ms'] else None,
        'python_poll_transitions': s['python_poll']['transition_count'],
        'native_poll_transitions': s['native_poll']['transition_count'],
    }
report = {
    'analysis_type': 'Offline reanalysis; no new fan run or reference instrument capture',
    'old_problem': 'Excess counts (not merely missing pulses); cause was not established',
    'old_32bit': old,
    'current_data': 'fan_fullrange/raw.json',
    'current_method': 'Pico RP2040 PWM slice7 B falling-edge counter at GP15, divider1, TOP65535',
    'sample_count': len(rows), 'verified_within_phase_counter_pairs': checked_pairs,
    'initial_stopped': window_report(initial),
    'active': window_report(active),
    'active_zero_windows': [{k: r[k] for k in ('phase', 'index', 'command_percent', 'stage_elapsed_ms', 'tach_window_us', 'tach_level')} for r in active if r['tach_edges'] == 0],
    'final_stopped_zero_suffix': window_report(suffix),
    'stop_first_window': {k: final[0][k] for k in ('tach_edges', 'tach_window_us', 'tach_counter')},
    'phase_tail_frequencies': [{'command_percent': p['command_percent'], 'edges': p['tach_edges'],
                               'window_s': p['tach_window_s'], 'hz': p['tach_hz'],
                               'rpm_assuming_2ppr': p['rpm_assuming_2ppr']} for p in summary['phases']],
    'conclusion': 'Previously observed massive overcount was not observed on the new Pico fan setup. Functional acquisition improved; absolute accuracy and root-cause repair are not proven.',
    'limits': [
        'Different signal source, board, wiring and counting method; not a controlled old-vs-new accuracy comparison.',
        'GPIO Low samples are logic-level observations, not an independent measurement of input voltage.',
        'There is one zero-count startup window. Nonzero counts afterward do not prove zero missed pulses or zero extra edges.',
        'Counter continuity was checked for 127 within-phase pairs. Six phase boundaries use a fresh baseline; inter-phase counts are not part of the recorded measurement windows.',
        'No concurrent oscilloscope, optical tachometer or known-frequency reference in this run.',
        'No known 50 Hz/DC-low stimulus test was performed on Pico.',
        'The saved commissioning firmware still reports rpm=null; temporary diagnostics implement counting only.',
        'Window aggregation has roughly one-edge granularity: about 60 rpm at 0.5 s, 6 rpm at 5 s (2 ppr). This is not total measurement accuracy.',
    ],
    'official_reference': 'https://www.raspberrypi.com/documentation/pico-sdk/hardware.html#hardware_pwm',
}
(BASE / 'tach_improvement_audit.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps(report, ensure_ascii=False, indent=2))
