"""Bounded RAM-only Rev E fan test. Leaves existing locked-stop flash intact.

GP16: 25 kHz PWM, non-inverting two-transistor interface. GP15: input-only
hardware falling-edge count (PWM slice 7 B). OEOVER explicitly disables output.
Watchdog reset returns to boot.py GP16 Low; this is NOT a certified safety stop.
"""
from machine import Pin, PWM, I2C, WDT, mem32, reset, unique_id
stop_pin = Pin(16, Pin.OUT, value=0)
import time
import json
import binascii
import os

STAGES = [(0, 3), (20, 5), (40, 5), (60, 5), (0, 8)]
PWM7 = 0x4005008c
GPIO15_CTRL = 0x4001407c
pwm = None
wdt = None
ina_original = None
bus0 = None
bus1 = None
sdp_running = False
tach_saved = None
command = 0


def emit(kind, **fields):
    fields.update(kind=kind, pico_ms=time.ticks_ms(), command_percent=command)
    print(json.dumps(fields))


def crc8(data):
    crc = 255
    for v in data:
        crc ^= v
        for _ in range(8):
            crc = ((crc << 1) ^ 0x31) & 255 if crc & 128 else (crc << 1) & 255
    return crc


def read16(reg):
    b = bus1.readfrom_mem(0x40, reg, 2)
    return (b[0] << 8) | b[1]


def write16(reg, value):
    bus1.writeto_mem(0x40, reg, bytes([value >> 8, value & 255]))


def read_sensors():
    frame = bus0.readfrom(0x25, 9)
    for i in (0, 3, 6):
        if crc8(frame[i:i+2]) != frame[i+2]:
            raise ValueError('SDP CRC')
    scale = (frame[6] << 8) | frame[7]
    if scale != 240:
        raise ValueError('Unexpected SDP scale')
    dp = (frame[0] << 8) | frame[1]
    if dp & 0x8000:
        dp -= 65536
    write16(0, (ina_original & 0x7000) | 0x0523)
    started = time.ticks_ms()
    while True:
        flags = read16(6)
        if flags & 8:
            break
        if time.ticks_diff(time.ticks_ms(), started) > 200:
            raise OSError('INA260 conversion timeout')
        time.sleep_ms(2)
    if flags & 4:
        raise ValueError('INA260 overflow')
    ina = b''.join(bus1.readfrom_mem(0x40, r, 2) for r in (1, 2, 3))
    current = (ina[0] << 8) | ina[1]
    if current & 0x8000:
        current -= 65536
    voltage = (ina[2] << 8) | ina[3]
    power = (ina[4] << 8) | ina[5]
    return dict(sdp_frame_hex=binascii.hexlify(frame).decode(), sdp_crc_ok=True,
                differential_pressure_pa=dp / 240.0,
                ina_frame_hex=binascii.hexlify(ina).decode(), ina_flags=flags,
                current_ma=current * 1.25, bus_voltage_v=voltage * 0.00125,
                power_w=power * 0.01)


def stop():
    global command, pwm
    command = 0
    if pwm is not None:
        pwm.duty_u16(0)
        pwm.deinit()
        pwm = None
    Pin(16, Pin.OUT, value=0)


errors = []
try:
    if binascii.hexlify(unique_id()).decode() != 'e660583883976d2d':
        raise ValueError('Wrong Pico')
    if 'RP2040' not in os.uname().machine:
        raise ValueError('This register map is RP2040 only')
    for gp in (0, 1, 2, 3):
        if not Pin(gp, Pin.IN).value():
            raise OSError('I2C idle low GP%d' % gp)
    bus0 = I2C(0, sda=Pin(0), scl=Pin(1), freq=100000, timeout=50000)
    bus1 = I2C(1, sda=Pin(2), scl=Pin(3), freq=100000, timeout=50000)
    if read16(0xfe) != 0x5449 or read16(0xff) >> 4 != 0x227:
        raise ValueError('INA260 identity mismatch')
    ina_original = read16(0)
    bus0.writeto(0x25, b'\x3f\xf9')
    time.sleep_ms(2)
    bus0.writeto(0x25, b'\x36\x15')
    sdp_running = True
    time.sleep_ms(30)
    initial = read_sensors()
    if not 10.8 <= initial['bus_voltage_v'] <= 13.2:
        raise ValueError('Fan supply not within 10.8-13.2 V; check SW1')
    if not -20 <= initial['current_ma'] <= 80:
        raise ValueError('Unexpected stopped-fan current; do not start')
    # No object on slice 7 is in use in the commissioning firmware.
    Pin(15, Pin.IN)
    if mem32[PWM7] & 1:
        raise ValueError('PWM slice 7 already active')
    tach_saved = [mem32[GPIO15_CTRL]] + [mem32[PWM7 + i] for i in (0, 4, 8, 12, 16)]
    mem32[PWM7] = 0
    mem32[GPIO15_CTRL] = (tach_saved[0] & ~0x0003331f) | 0x2004
    mem32[PWM7 + 4] = 0x10
    mem32[PWM7 + 8] = 0
    mem32[PWM7 + 12] = 0
    mem32[PWM7 + 16] = 0xffff
    mem32[PWM7] = 0x31
    assert mem32[GPIO15_CTRL] & 0x301f == 0x2004  # Input only, never drive Tach.
    # Enable watchdog BEFORE permitting nonzero PWM. A hard reset returns the
    # flashed commissioning application to its locked-stop state.
    wdt = WDT(timeout=3000)
    pwm = PWM(Pin(16), freq=25000, duty_u16=0)
    emit('start', stages=STAGES, pwm_hz=pwm.freq(), watchdog_ms=3000,
         tach_method='RP2040 PWM7 B falling-edge counter, GP15 output disabled',
         rpm_pulses_per_revolution_assumed=2, initial=initial,
         ina_original_config=ina_original)
    overall_start = time.ticks_ms()
    for phase, (duty, seconds) in enumerate(STAGES):
        wdt.feed()
        command = duty
        pwm.duty_u16(round(65535 * duty / 100))
        emit('phase', phase=phase, seconds=seconds, duty_u16=pwm.duty_u16())
        begin = time.ticks_ms()
        previous_t = time.ticks_us()
        previous_n = mem32[PWM7 + 8] & 0xffff
        edges_in_phase = 0
        high_current_samples = 0
        for index in range(seconds * 2):
            target_ms = (index + 1) * 500
            while time.ticks_diff(time.ticks_ms(), begin) < target_ms:
                if time.ticks_diff(time.ticks_ms(), overall_start) > 32000:
                    raise RuntimeError('Bounded runtime exceeded')
                time.sleep_ms(20)
                wdt.feed()
            t = time.ticks_us()
            n = mem32[PWM7 + 8] & 0xffff
            delta = (n - previous_n) & 0xffff
            dt = time.ticks_diff(t, previous_t)
            previous_t, previous_n = t, n
            edges_in_phase += delta
            row = read_sensors()
            hz = delta * 1000000.0 / dt
            row.update(phase=phase, index=index, stage_elapsed_ms=time.ticks_diff(time.ticks_ms(), begin),
                       tach_edges=delta, tach_window_us=dt, tach_counter=n,
                       tach_hz=hz, rpm_assuming_2ppr=hz * 30.0,
                       tach_level=Pin(15).value(), duty_u16=pwm.duty_u16())
            if command == 0:
                row['gp16_level_when_stopped'] = Pin(16).value()
            # Check and STOP before printing any abnormal reading.
            reason = None
            if not 10.8 <= row['bus_voltage_v'] <= 13.2:
                reason = 'Bus voltage outside 10.8-13.2 V'
            if row['current_ma'] < -20 or row['current_ma'] > 600:
                reason = 'Current outside -20..600 mA'
            high_current_samples = high_current_samples + 1 if row['current_ma'] > 450 else 0
            if high_current_samples >= 2:
                reason = 'Current above 450 mA for two samples'
            if abs(row['differential_pressure_pa']) > 100:
                reason = 'Differential pressure above 100 Pa'
            if hz > 150 or (phase == 0 and hz > 2):
                reason = 'Unexpected Tach count; abort for inspection'
            if reason:
                row['abort_reason'] = reason
                row['command_at_measurement'] = command
                stop()
                emit('sample', **row)
                raise RuntimeError(reason)
            emit('sample', **row)
            wdt.feed()
        if duty > 0 and edges_in_phase == 0:
            raise RuntimeError('No Tach edges at commanded speed; stop before escalating')
except Exception as exc:
    stop()
    errors.append(repr(exc))
    emit('fatal', error=repr(exc))
finally:
    stop()
    if wdt is not None:
        wdt.feed()
    if sdp_running:
        try:
            bus0.writeto(0x25, b'\x3f\xf9')
            time.sleep_ms(2)
        except Exception as exc:
            errors.append('SDP stop: ' + repr(exc))
    restored = None
    if ina_original is not None:
        try:
            write16(0, ina_original & 0x7fff)
            restored = read16(0)
            if restored != ina_original:
                raise ValueError('INA260 config restore mismatch')
        except Exception as exc:
            errors.append('INA restore: ' + repr(exc))
    if tach_saved is not None:
        mem32[PWM7] = 0
        mem32[GPIO15_CTRL] = tach_saved[0]
        for offset, value in zip((4, 8, 12, 16), tach_saved[2:]):
            mem32[PWM7 + offset] = value
        mem32[PWM7] = tach_saved[1]
    Pin(15, Pin.IN)
    for gp in (0, 1, 2, 3):
        Pin(gp, Pin.IN)
    emit('done', errors=errors, gp16_level=Pin(16).value(), ina_restored_config=restored,
         next_action='hard_reset_to_existing_locked_stop_firmware')
    time.sleep_ms(150)
    reset()
