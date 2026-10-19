"""Pi host for bounded fan tests. Raw records flushed to disk as they arrive."""
import argparse
from datetime import datetime
import hashlib
import json
from pathlib import Path
import time
import serial

PORT = '/dev/serial/by-id/usb-MicroPython_Board_in_FS_mode_e660583883976d2d-if00'


def now():
    return datetime.now().astimezone().isoformat(timespec='milliseconds')


def stopped(ser, tag):
    ser.write((json.dumps({'cmd': 'stop', 'id': tag}) + '\n').encode())
    deadline = time.monotonic() + 4
    while time.monotonic() < deadline:
        line = ser.readline().decode(errors='replace').strip()
        try:
            reply = json.loads(line)
        except ValueError:
            continue
        if reply.get('id') == tag:
            status = reply['status']
            assert status['device_id'] == 'e660583883976d2d'
            assert status['firmware'] == '0.1.0-commissioning'
            assert status['gp16_level'] == 0 and status['fan_enabled'] is False
            assert status['fan_command_percent'] == 0
            return reply
    raise TimeoutError('No stopped status response')


def run(destination, source_path):
    destination.mkdir(parents=True, exist_ok=False)
    source = source_path.read_bytes()
    (destination / 'fan_steps.py').write_bytes(source)
    result = dict(started_at=now(), records=[], source_sha256=hashlib.sha256(source).hexdigest())
    ser = None
    entered = False
    done = False
    with (destination / 'records.jsonl').open('w', encoding='utf-8') as journal:
        try:
            ser = serial.Serial(PORT, 115200, timeout=0.1, write_timeout=2, exclusive=True)
            ser.reset_input_buffer()
            result['before'] = stopped(ser, 'fan-before')
            ser.write(b'\r\x03\x03')
            entered = True
            time.sleep(0.25)
            ser.reset_input_buffer()
            ser.write(b'\x01')
            banner = bytearray()
            deadline = time.monotonic() + 3
            while not banner.endswith(b'raw REPL; CTRL-B to exit\r\n>'):
                banner.extend(ser.read(1))
                if time.monotonic() > deadline:
                    raise TimeoutError('Raw REPL entry')
            for pos in range(0, len(source), 128):
                ser.write(source[pos:pos+128])
                time.sleep(0.01)
            ser.write(b'\x04')
            if ser.read(2) != b'OK':
                raise RuntimeError('No raw REPL acknowledgement')
            deadline = time.monotonic() + 38
            line = bytearray()
            while time.monotonic() < deadline:
                ch = ser.read(1)
                if ch == b'\x04':
                    raise RuntimeError('Unexpected raw REPL EOF; inspect diagnostic text')
                line.extend(ch)
                if ch != b'\n':
                    continue
                txt = line.decode(errors='replace').strip()
                line.clear()
                try:
                    data = json.loads(txt)
                except ValueError:
                    data = {'kind': 'text', 'text': txt}
                record = {'pi_received_at': now(), 'data': data}
                result['records'].append(record)
                journal.write(json.dumps(record) + '\n')
                journal.flush()
                if data.get('kind') in ('start', 'phase', 'fatal', 'done'):
                    print(json.dumps(record), flush=True)
                if data.get('kind') == 'done':
                    done = True
                    break
            if not done:
                raise TimeoutError('No done record within bounded test')
        except Exception as exc:
            result['host_error'] = repr(exc)
        finally:
            if ser is not None:
                if entered and not done:
                    try:
                        ser.write(b'\x03\x03')  # RAM test finally stops and resets.
                    except Exception:
                        pass
                ser.close()
            if entered:
                # Hardware reset clears the watchdog and re-enumerates USB.
                time.sleep(1.5)
                deadline = time.monotonic() + 7
                while time.monotonic() < deadline:
                    try:
                        with serial.Serial(PORT, 115200, timeout=0.1, write_timeout=1, exclusive=True) as check:
                            check.reset_input_buffer()
                            result['after'] = stopped(check, 'fan-after')
                        break
                    except Exception as exc:
                        result['last_reconnect_error'] = repr(exc)
                        time.sleep(0.25)
            result['finished_at'] = now()
            (destination / 'raw.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    print('RESULT_DIRECTORY', destination, flush=True)
    print('POST_STATUS', json.dumps(result.get('after')), flush=True)
    if 'after' not in result:
        raise RuntimeError('Cannot confirm final stop; turn SW1 off')
    if result.get('host_error') or any(r['data'].get('kind') == 'fatal' for r in result['records']):
        raise RuntimeError('Test aborted; final stop confirmed; inspect raw records')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('destination', type=Path)
    parser.add_argument('--source', type=Path, default=Path(__file__).with_name('fan_steps.py'))
    args = parser.parse_args()
    run(args.destination, args.source)
