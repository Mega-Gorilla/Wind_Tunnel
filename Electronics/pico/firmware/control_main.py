"""RP2040 Carrier Rev E finite-run firmware, protocol 2. Installed as main.py.

GP15 is input-only PWM7 B falling-edge count. GP16 drives non-inverting 25 kHz.
No automatic arm, resume or retained PWM. Lease 2 s; watchdog 3 s once armed.
"""
from machine import Pin
Pin(16, Pin.OUT, value=0)
from machine import PWM, WDT, mem32, unique_id, reset
import binascii
import json
import os
import select
import sys
import time
from wt_sensors import Sensors

VERSION = '0.3.0-control'
DEVICE_ID = binascii.hexlify(unique_id()).decode()
BOOT_ID = binascii.hexlify(os.urandom(8)).decode()
PWM7 = 0x4005008c
GPIO15_CTRL = 0x4001407c


class Tach:
    def __init__(self):
        if 'RP2040' not in os.uname().machine:
            raise ValueError('RP2040_REQUIRED')
        Pin(15, Pin.IN)
        mem32[PWM7] = 0
        mem32[GPIO15_CTRL] = (mem32[GPIO15_CTRL] & ~0x0003331f) | 0x2004
        mem32[PWM7+4] = 0x10
        mem32[PWM7+8] = 0
        mem32[PWM7+12] = 0
        mem32[PWM7+16] = 0xffff
        mem32[PWM7] = 0x31
        self.t, self.n, self.total = time.ticks_us(), 0, 0

    def sample(self):
        if mem32[GPIO15_CTRL] & 0x301f != 0x2004:
            raise ValueError('TACH_PIN_NOT_INPUT_ONLY')
        t, n = time.ticks_us(), mem32[PWM7+8] & 0xffff
        dt, edges = time.ticks_diff(t, self.t), (n-self.n) & 0xffff
        self.t, self.n = t, n
        self.total += edges
        if not 100000 <= dt <= 2000000:
            raise ValueError('TACH_WINDOW')
        return dict(tach_edges=edges, tach_window_us=dt, tach_counter=n,
                    tach_total_edges=self.total, tach_hz=edges*1000000.0/dt,
                    tach_ppr=2, tach_method='PWM7_B_falling_input_only')


class Fan:
    def __init__(self):
        self.pwm = None
        self.percent = 0
        self.set(0)

    def set(self, value):
        if value == 0:
            if self.pwm is not None:
                self.pwm.duty_u16(0)
                self.pwm.deinit()
                self.pwm = None
            Pin(16, Pin.OUT, value=0)
        else:
            if self.pwm is None:
                self.pwm = PWM(Pin(16), freq=25000, duty_u16=0)
            self.pwm.duty_u16(round(value*65535/100))
        self.percent = value


class Control:
    def __init__(self, fan=None, sensors=None, tach=None):
        self.fan = fan or Fan()
        self.sensors = sensors or Sensors()
        self.tach = tach or Tach()
        self.epoch = 0
        self.arm_id = None
        self.run_id = None
        self.fault = None
        self.wdt = None
        self.seq = self.sample_seq = 0
        self.command_seq = -1
        self.raw = {'errors': {'sdp':'WARMING_UP','bme':'WARMING_UP','ina':'WARMING_UP'}}
        self.tach_data = None
        self.sample_ms = None
        self.next_sample = time.ticks_ms()
        self.mixed = False
        self.window_pwm = 0
        self.over_current = 0
        self.last_edge_ms = self.spinup_ms = time.ticks_ms()
        self.reboot_requested = False

    def set_pwm(self, value):
        if value != self.fan.percent:
            self.mixed = True
            if value and not self.fan.percent:
                self.spinup_ms = self.last_edge_ms = time.ticks_ms()
        self.fan.set(value)

    def stop(self, reason=None):
        self.set_pwm(0)
        self.epoch += 1
        self.arm_id = self.run_id = None
        self.command_seq = -1
        if reason and self.fault is None:
            self.fault = reason

    def electrical(self):
        b = binascii.unhexlify(self.raw['ina_frame_hex'])
        current = (b[0] << 8) | b[1]
        if current & 0x8000: current -= 65536
        return current*1.25, ((b[2] << 8) | b[3])*.00125

    def sensor_ready(self):
        return (self.sample_ms is not None and time.ticks_diff(time.ticks_ms(), self.sample_ms) <= 1500
                and not self.raw['errors'] and self.tach_data is not None)

    def ready_to_arm(self):
        if not self.sensor_ready(): raise ValueError('SENSORS_NOT_READY')
        current, voltage = self.electrical()
        if not 10.8 <= voltage <= 13.2: raise ValueError('SUPPLY_CHECK_SW1')
        if not -20 <= current <= 80: raise ValueError('STOPPED_CURRENT')
        if self.tach_data['tach_hz'] > 2: raise ValueError('WAIT_FOR_FAN_STOP')

    def deadlines(self):
        if self.arm_id:
            now = time.ticks_ms()
            if time.ticks_diff(now, self.lease_at) > 2000:
                self.stop('LEASE_EXPIRED')
            elif time.ticks_diff(now, self.armed_at) >= self.duration_ms:
                self.stop('RUN_LIMIT')
            elif not self.sensor_ready():
                self.stop('SENSOR_STALE')

    def acquire(self):
        self.raw = self.sensors.sample()
        self.tach_data = self.tach.sample()
        now = time.ticks_ms()
        self.sample_ms = now
        self.sample_seq += 1
        self.raw.update(self.tach_data)
        self.raw.update(tach_window_mixed_pwm=self.mixed, pwm_window_start_percent=self.window_pwm,
                        pwm_window_end_percent=self.fan.percent)
        self.mixed = False
        self.window_pwm = self.fan.percent
        if self.tach_data['tach_edges']: self.last_edge_ms = now
        if self.tach_data['tach_hz'] > 150:
            self.stop('TACH_RANGE')
        if self.arm_id:
            if self.raw['errors']:
                self.stop('SENSOR_ERROR')
                return
            current, voltage = self.electrical()
            b = binascii.unhexlify(self.raw['sdp_frame_hex'])
            dp = (b[0] << 8) | b[1]
            if dp & 0x8000: dp -= 65536
            self.over_current = self.over_current+1 if current > 450 else 0
            if not 10.8 <= voltage <= 13.2: self.stop('SUPPLY_RANGE')
            elif current < -20 or current > 600 or self.over_current >= 2: self.stop('CURRENT_RANGE')
            elif abs(dp/240.0) > 100: self.stop('PRESSURE_RANGE')
            elif (self.fan.percent and time.ticks_diff(now,self.spinup_ms)>3000
                  and time.ticks_diff(now,self.last_edge_ms)>2000): self.stop('TACH_MISSING')

    def service(self):
        self.deadlines()
        if time.ticks_diff(time.ticks_ms(), self.next_sample) >= 0:
            self.acquire()
            self.next_sample = time.ticks_add(self.next_sample,500)
            # No catch-up burst after a bounded slow sensor read.
            if time.ticks_diff(time.ticks_ms(), self.next_sample)>=0:
                self.next_sample = time.ticks_add(time.ticks_ms(),500)
        self.deadlines()
        if self.wdt: self.wdt.feed()

    def respond(self, request):
        self.deadlines()
        error = None
        cmd = request.get('cmd') if isinstance(request,dict) else None
        try:
            if cmd in ('stop','reboot'):
                self.stop()
                self.reboot_requested = cmd == 'reboot'
            elif cmd in ('status','sample'):
                pass
            elif cmd == 'ack':
                if self.arm_id or self.fan.percent: raise ValueError('BUSY')
                self.ready_to_arm()
                self.stop()
                self.fault = None
            elif cmd == 'arm':
                if self.arm_id or self.fault: raise ValueError('BUSY_OR_FAULT')
                if request.get('boot_id') != BOOT_ID or request.get('epoch') != self.epoch:
                    raise ValueError('STALE_AUTHORITY')
                duration = request.get('duration_ms')
                if type(duration) is not int or not 1000 <= duration <= 302000:
                    raise ValueError('DURATION_RANGE')
                if not isinstance(request.get('run_id'),str) or not 1 <= len(request['run_id']) <= 64:
                    raise ValueError('RUN_ID')
                self.ready_to_arm()
                if self.wdt is None: self.wdt = WDT(timeout=3000)
                self.wdt.feed()
                self.arm_id = binascii.hexlify(os.urandom(8)).decode()
                self.run_id = request['run_id']
                self.armed_at = self.lease_at = time.ticks_ms()
                self.duration_ms = duration
                self.command_seq = -1
                self.over_current = 0
            elif cmd == 'drive':
                if (not self.arm_id or self.fault or request.get('arm_id') != self.arm_id
                        or request.get('epoch') != self.epoch or request.get('boot_id') != BOOT_ID):
                    raise ValueError('STALE_AUTHORITY')
                sequence, value = request.get('command_seq'), request.get('pwm_percent')
                if type(sequence) is not int or sequence <= self.command_seq: raise ValueError('COMMAND_SEQUENCE')
                if type(value) not in (int,float) or not (value==0 or 20<=value<=100): raise ValueError('PWM_RANGE')
                if not self.sensor_ready(): raise ValueError('SENSORS_NOT_READY')
                self.set_pwm(value)
                self.command_seq = sequence
                self.lease_at = time.ticks_ms()
            else:
                raise ValueError('UNKNOWN_COMMAND')
        except Exception as exc:
            if self.arm_id or self.fan.percent: self.stop('PROTOCOL_ERROR')
            error = str(exc)
        self.seq += 1
        return dict(protocol=2, firmware=VERSION, device_id=DEVICE_ID, boot_id=BOOT_ID,
                    seq=self.seq, pico_ms=time.ticks_ms(), id=request.get('id') if isinstance(request,dict) else None,
                    ok=error is None, error=error, kind='telemetry', sample_seq=self.sample_seq,
                    sample_age_ms=time.ticks_diff(time.ticks_ms(),self.sample_ms) if self.sample_ms is not None else None,
                    raw=self.raw, fault=self.fault, safety_epoch=self.epoch, arm_id=self.arm_id, run_id=self.run_id,
                    fan_command_percent=self.fan.percent, fan_enabled=self.fan.percent>0,
                    fan_locked_stop=False, pwm_hz=25000, gp16_level=Pin(16).value() if not self.fan.percent else None,
                    lease_ms=2000, watchdog_ms=3000, watchdog_enabled=self.wdt is not None)

    def main(self):
        poll=select.poll();poll.register(sys.stdin,select.POLLIN)
        line='';overflow=False
        while True:
            self.service()
            # A bounded batch keeps long or malicious input from starving deadlines.
            for _ in range(512):
                if not poll.poll(0): break
                char=sys.stdin.read(1)
                if char in ('\r','\n'):
                    if line or overflow:
                        try:
                            if overflow: raise ValueError('LINE_TOO_LONG')
                            reply=self.respond(json.loads(line))
                        except Exception:
                            self.stop('PROTOCOL_ERROR')
                            reply={'ok':False,'error':'INVALID_JSON_OR_LENGTH'}
                        # Check lease again after potentially blocking USB output.
                        print(json.dumps(reply))
                    line='';overflow=False
                elif char:
                    if len(line)<512 and not overflow: line+=char
                    else: overflow=True
                if self.reboot_requested: reset()
            time.sleep_ms(10)


if __name__=='__main__':
    control=None
    try:
        control=Control()
        # First counter interval must be meaningful, without blocking USB for seconds.
        control.next_sample=time.ticks_add(time.ticks_ms(),500)
        control.main()
    finally:
        if control: control.stop()
        else: Pin(16,Pin.OUT,value=0)
