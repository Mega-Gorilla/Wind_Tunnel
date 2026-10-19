"""Run on Pi: deploy only locked-stop commissioning code over MicroPython REPL."""
from pathlib import Path
import sys, time, hashlib, json
import serial
from serial.tools import list_ports

ports = [p for p in list_ports.comports() if p.vid == 0x2e8a and p.pid == 0x0005]
if len(ports) != 1:
    raise RuntimeError('Expected exactly one MicroPython Pico: '+repr(ports))
port = ports[0]
print('PORT', port.device, 'SERIAL', port.serial_number, flush=True)
s = serial.Serial(port.device, 115200, timeout=0.2, write_timeout=3, exclusive=True)


def until(marker, timeout=5):
    data = bytearray()
    end = time.monotonic()+timeout
    while not data.endswith(marker):
        data.extend(s.read(1))
        if time.monotonic() > end:
            raise TimeoutError(repr(bytes(data)))
    return bytes(data)


def execute(code):
    code = code.encode()
    for offset in range(0, len(code), 128):
        s.write(code[offset:offset+128])
        time.sleep(0.01)
    s.write(b'\x04')
    if s.read(2) != b'OK':
        raise RuntimeError('REPL did not acknowledge')
    out = until(b'\x04')[:-1]
    err = until(b'\x04')[:-1]
    until(b'>')
    if err:
        raise RuntimeError(err.decode())
    return out.decode()


try:
    s.write(b'\r\x03\x03')
    time.sleep(0.25)
    s.reset_input_buffer()
    s.write(b'\x01')
    until(b'raw REPL; CTRL-B to exit\r\n>')
    print(execute('from machine import Pin; Pin(16, Pin.OUT, value=0); import os,sys; print(sys.implementation); print(os.listdir())'))
    root = Path(__file__).resolve().parents[0]
    for name in ('boot.py','main.py'):
        data = (root/name).read_bytes()
        # No deletion of existing application files: only fresh filesystem is expected.
        execute('import os; assert '+repr(name)+' not in os.listdir(), "existing file: stop and back up"')
        execute('f=open('+repr(name+'.new')+',"wb")')
        for offset in range(0,len(data),128):
            execute('f.write('+repr(data[offset:offset+128])+')')
        execute('f.close()')
        actual=execute('import hashlib,binascii; print(binascii.hexlify(hashlib.sha256(open('+repr(name+'.new')+',"rb").read()).digest()).decode())').strip()
        assert actual == hashlib.sha256(data).hexdigest(), 'upload hash mismatch'
        execute('os.rename('+repr(name+'.new')+','+repr(name)+'); os.sync()')
        print('VERIFIED',name,actual,flush=True)
    # Return to friendly REPL and soft-reboot into boot.py/main.py.
    s.write(b'\x02')
    time.sleep(0.1)
    s.write(b'\x04')
    time.sleep(1)
    s.reset_input_buffer()
    s.write(b'{"cmd":"status","id":"deploy-check"}\n')
    reply=until(b'\n',timeout=5).decode().strip()
    print('STATUS',reply)
    status=json.loads(reply)['status']
    assert status['gp16_level']==0 and status['fan_enabled'] is False
finally:
    s.close()
