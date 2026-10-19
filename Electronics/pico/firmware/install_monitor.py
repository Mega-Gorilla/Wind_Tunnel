"""Run on the Pi with kiosk stopped: install the reviewed locked-stop monitor.

No firmware flashing or boot.py changes. Read-back hashes and version/ID checks
are mandatory. The existing main.py is preserved on Pico and in the evidence dir.
"""
import hashlib
import json
from pathlib import Path
import sys
import time

import serial

DEVICE_ID = 'e660583883976d2d'
PORT = '/dev/serial/by-id/usb-MicroPython_Board_in_FS_mode_' + DEVICE_ID + '-if00'


def main():
    source = Path(sys.argv[1]).read_bytes()
    evidence = Path(sys.argv[2]); evidence.mkdir(parents=True, exist_ok=True)
    assert b"VERSION = '0.2.0-monitor'" in source
    digest = hashlib.sha256(source).hexdigest()
    s = serial.Serial(PORT,115200,timeout=.1,write_timeout=3,exclusive=True)
    raw = False

    def until(marker, timeout=10):
        data=bytearray(); end=time.monotonic()+timeout
        while not data.endswith(marker):
            data.extend(s.read(1))
            if time.monotonic()>end: raise TimeoutError(repr(bytes(data[-300:])))
        return bytes(data)

    def execute(code):
        data=code.encode()
        for offset in range(0,len(data),128):
            s.write(data[offset:offset+128]); time.sleep(.01)
        s.write(b'\x04')
        if until(b'OK') != b'OK': raise RuntimeError('REPL acknowledgement')
        out=until(b'\x04')[:-1]; err=until(b'\x04')[:-1]; until(b'>')
        if err: raise RuntimeError(err.decode())
        return out.decode().strip()

    try:
        s.write(b'\r\x03\x03'); time.sleep(.3); s.reset_input_buffer()
        s.write(b'\x01'); until(b'raw REPL; CTRL-B to exit\r\n>'); raw=True
        ident=execute('from machine import Pin,unique_id; Pin(16,Pin.OUT,value=0); import os,binascii,hashlib; print(binascii.hexlify(unique_id()).decode())')
        assert ident==DEVICE_ID, 'Unexpected Pico'
        old=bytes.fromhex(execute('print(binascii.hexlify(open("main.py","rb").read()).decode())'))
        boot=bytes.fromhex(execute('print(binascii.hexlify(open("boot.py","rb").read()).decode())'))
        assert b'Pin' in boot and b'16' in boot and b'value=0' in boot, 'Review existing boot stop guard'
        assert b'0.1.0-commissioning' in old or b'0.2.0-monitor' in old, 'Unknown main.py; stop for review'
        old_hash=hashlib.sha256(old).hexdigest()
        (evidence/('main-before-'+old_hash[:12]+'.py')).write_bytes(old)
        (evidence/'boot-preserved.py').write_bytes(boot)
        backup='main.backup-'+old_hash[:12]+'.py'
        # Copy only once, preserving the old main.py until the verified replacement.
        execute('p='+repr(backup)+'\nif p not in os.listdir():\n f=open(p,"wb"); f.write(open("main.py","rb").read()); f.close()')
        execute('assert "main.monitor.new" not in os.listdir(), "Review unfinished prior upload"; f=open("main.monitor.new","wb")')
        for offset in range(0,len(source),128): execute('f.write('+repr(source[offset:offset+128])+')')
        execute('f.close(); os.sync()')
        actual=execute('print(binascii.hexlify(hashlib.sha256(open("main.monitor.new","rb").read()).digest()).decode())')
        assert actual==digest, 'Upload mismatch'
        execute('os.rename("main.monitor.new","main.py"); os.sync(); Pin(16,Pin.OUT,value=0)')
        s.write(b'\x02'); raw=False; time.sleep(.1); s.write(b'\x04'); time.sleep(1)
        s.reset_input_buffer()
        s.write(b'{"cmd":"status","id":"installed-monitor"}\n')
        reply=json.loads(until(b'\n',timeout=5))
        assert reply['ok'] and reply['firmware']=='0.2.0-monitor' and reply['device_id']==DEVICE_ID
        assert reply['gp16_level']==0 and reply['fan_command_percent']==0 and reply['fan_locked_stop'] is True
        result={'installed_sha256':digest,'previous_sha256':old_hash,'pico_backup':backup,'status':reply}
        (evidence/'firmware-install.json').write_text(json.dumps(result,indent=2))
        print(json.dumps(result),flush=True)
    finally:
        if raw:
            try: execute('from machine import Pin; Pin(16,Pin.OUT,value=0)')
            except Exception: pass
            # Leave failure in a stopped REPL; do not launch unverified code.
        s.close()


if __name__=='__main__': main()
