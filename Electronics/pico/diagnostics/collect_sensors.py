"""Run on Pi. Acquire a bounded RAM-only sensor test, then restore main.py."""
from pathlib import Path
from datetime import datetime
import argparse
import hashlib
import json
import time
import serial
from compensation import summarize

PORT = '/dev/serial/by-id/usb-MicroPython_Board_in_FS_mode_e660583883976d2d-if00'


def now():
    return datetime.now().astimezone().isoformat(timespec='milliseconds')


def run(destination):
    destination.mkdir(parents=True, exist_ok=False)
    source = Path(__file__).with_name('sample_sensors.py').read_bytes()
    raw = dict(started_at=now(), port=PORT, records=[],
               diagnostic_sha256=hashlib.sha256(source).hexdigest(), fan_command_percent=0)
    (destination / 'sample_sensors.py').write_bytes(source)
    s = serial.Serial(PORT, 115200, timeout=0.1, write_timeout=3, exclusive=True)
    in_repl = False

    def until(marker, timeout=5, record_lines=False):
        data, line = bytearray(), bytearray()
        deadline = time.monotonic() + timeout
        while not data.endswith(marker):
            char = s.read(1)
            data.extend(char)
            if record_lines:
                line.extend(char)
                if char == b'\n':
                    text = line.decode(errors='replace').strip()
                    try:
                        value = json.loads(text)
                    except ValueError:
                        value = {'kind': 'non_json', 'text': text}
                    raw['records'].append({'pi_received_at': now(), 'data': value})
                    line.clear()
            if time.monotonic() > deadline:
                raise TimeoutError(repr(bytes(data[-400:])))
        return bytes(data)

    def request_stop(tag):
        s.write((json.dumps({'cmd': 'stop', 'id': tag}) + '\n').encode())
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            line = s.readline().decode(errors='replace').strip()
            try:
                reply = json.loads(line)
            except ValueError:
                continue
            if reply.get('id') != tag:
                continue
            status = reply['status']
            assert status['device_id'] == 'e660583883976d2d'
            assert status['gp16_level'] == 0 and status['fan_enabled'] is False
            assert status['fan_command_percent'] == 0
            return reply
        raise TimeoutError('No stopped-fan JSON response')

    try:
        s.reset_input_buffer()
        raw['before'] = request_stop('sensor-test-before')
        print('PRECHECK: stopped-fan response verified', flush=True)
        s.write(b'\r\x03\x03')
        in_repl = True
        time.sleep(0.25)
        s.reset_input_buffer()
        s.write(b'\x01')
        until(b'raw REPL; CTRL-B to exit\r\n>')
        for offset in range(0, len(source), 128):
            s.write(source[offset:offset+128])
            time.sleep(0.01)
        s.write(b'\x04')
        if s.read(2) != b'OK':
            raise RuntimeError('No raw REPL acknowledgement')
        raw['stdout'] = until(b'\x04', timeout=40, record_lines=True)[:-1].decode()
        raw['stderr'] = until(b'\x04')[:-1].decode()
        until(b'>')
        if raw['stderr']:
            raise RuntimeError(raw['stderr'])
    except Exception as exc:
        raw['host_error'] = repr(exc)
    finally:
        if in_repl:
            try:
                # Ctrl-C runs the RAM test's finally block if it is still active.
                # No PWM is created and no code path drives GP16 high.
                s.write(b'\x03\x03')
                time.sleep(0.25)
                s.write(b'\x02')
                time.sleep(0.1)
                s.write(b'\x04')
                time.sleep(1)
                s.reset_input_buffer()
                raw['after'] = request_stop('sensor-test-after')
            except Exception as exc:
                raw['restore_error'] = repr(exc)
        s.close()
        raw['finished_at'] = now()
        (destination / 'raw.json').write_text(json.dumps(raw, indent=2), encoding='utf-8')
    summary = summarize(raw)
    summary.update(started_at=raw['started_at'], finished_at=raw['finished_at'],
                   before=raw.get('before'), after=raw.get('after'),
                   host_error=raw.get('host_error'), restore_error=raw.get('restore_error'))
    (destination / 'summary.json').write_text(json.dumps(summary, indent=2), encoding='utf-8')
    print(json.dumps({k: summary[k] for k in ('started_at', 'finished_at', 'sample_count',
                     'metrics', 'sample_errors', 'fatal_errors', 'cleanup', 'host_error',
                     'restore_error')}, indent=2), flush=True)
    print('RESULT_DIRECTORY', str(destination), flush=True)
    good = (not raw.get('host_error') and not raw.get('restore_error') and
            summary['sample_count'] == 30 and not summary['sample_errors'] and
            not summary['fatal_errors'] and len(summary['cleanup']) == 1 and
            not summary['cleanup'][0]['errors'] and raw.get('after'))
    if 'ina_manufacturer_id' in summary['identity']:
        good = good and all(summary['metrics'].get(key, {}).get('count') == 30
                            for key in ('current_ma', 'bus_voltage_v', 'power_w'))
    if not good:
        raise RuntimeError('Sensor test incomplete: inspect preserved raw.json')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('destination', type=Path)
    run(parser.parse_args().destination)
