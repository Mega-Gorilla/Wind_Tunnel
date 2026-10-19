"""Nonblocking controller adapter for the stopped-fan Pico monitor protocol.

Only this worker owns USB. Reconnects never enter REPL, reset the board or run PWM.
"""
from copy import deepcopy
import json
import math
import threading
import time
from uuid import uuid4

from .sensor_conversion import calibration, compensate_bme, convert_ina, crc8, signed
from .store import utc_now

DEVICE_ID = 'e660583883976d2d'
PORT = '/dev/serial/by-id/usb-MicroPython_Board_in_FS_mode_e660583883976d2d-if00'
FIELDS = ('differential_pressure_pa', 'sdp_chip_temperature_c', 'temperature_c',
          'relative_humidity_percent', 'ambient_pressure_pa', 'bus_voltage_v', 'current_a', 'power_w')


def empty_sample(reason='CONNECTING'):
    return dict(simulation=False, source='pico_usb', connected=False, valid=False,
                reason=reason, seq=None, boot_id=None, monotonic_s=None, received_at=None,
                pwm_applied_percent=None, rpm_estimated=None, rpm_reason='not_measured_in_monitor_firmware',
                pulses_per_revolution_assumed=None, airspeed_m_s=None,
                airspeed_reason='pressure_mapping_and_calibration_pending', sw1_position='unknown',
                settled=None, sensor_errors={}, **dict.fromkeys(FIELDS))


def validate_envelope(frame):
    if not isinstance(frame, dict) or frame.get('ok') is not True:
        raise ValueError('PICO_PROTOCOL')
    if frame.get('device_id') != DEVICE_ID:
        raise ValueError('PICO_ID_MISMATCH')
    if frame.get('protocol') != 1 or frame.get('firmware') != '0.2.0-monitor':
        raise ValueError('PICO_FIRMWARE_MISMATCH')
    if (frame.get('fan_locked_stop') is not True or frame.get('fan_enabled') is not False
            or type(frame.get('gp16_level')) is not int or frame['gp16_level'] != 0
            or type(frame.get('fan_command_percent')) is not int or frame['fan_command_percent'] != 0):
        raise ValueError('PICO_STOP_NOT_CONFIRMED')
    if (not isinstance(frame.get('boot_id'), str) or len(frame['boot_id']) != 16
            or type(frame.get('seq')) is not int or frame['seq'] < 1
            or type(frame.get('pico_ms')) is not int or not 0 <= frame['pico_ms'] < 2**30):
        raise ValueError('PICO_SEQUENCE')


def sensor_words(value, length):
    b = bytes.fromhex(value)
    if len(b) != length or any(crc8(b[n:n+2]) != b[n+2] for n in range(0, length, 3)):
        raise ValueError('SDP_CRC_OR_LENGTH')
    return [int.from_bytes(b[n:n+2], 'big') for n in range(0, length, 3)]


def decode_sample(frame, now, validator=validate_envelope):
    validator(frame)
    if frame.get('kind') != 'telemetry' or not isinstance(frame.get('raw'), dict):
        raise ValueError('PICO_TELEMETRY_REQUIRED')
    raw = frame['raw']
    ident = raw.get('identity', {})
    reported = raw.get('errors', {})
    if not isinstance(ident, dict) or not isinstance(reported, dict):
        raise ValueError('PICO_SENSOR_FORMAT')
    result = empty_sample()
    errors = {}
    for name in ('sdp', 'bme', 'ina'):
        try:
            if name in reported:
                raise ValueError(str(reported[name])[:100])
            if name == 'sdp':
                identity = sensor_words(ident['sdp_identity_frame_hex'], 18)
                if ((identity[0] << 16) | identity[1]) & 0xffffff00 != 0x03020b00:
                    raise ValueError('SDP_ID')
                dp, temp, scale = sensor_words(raw['sdp_frame_hex'], 9)
                if scale != 240:
                    raise ValueError('SDP_SCALE')
                values = {'differential_pressure_pa': signed(dp, 16)/scale,
                          'sdp_chip_temperature_c': signed(temp, 16)/200}
                if abs(values['differential_pressure_pa']) > 125:
                    raise ValueError('SDP_RANGE')
            elif name == 'bme':
                if ident['bme_chip_id'] != 0x60:
                    raise ValueError('BME_ID')
                c = calibration(bytes.fromhex(ident['bme_cal_88_hex']), bytes.fromhex(ident['bme_cal_e1_hex']))
                b = bytes.fromhex(raw['bme_frame_hex'])
                if len(b) != 8:
                    raise ValueError('BME_LENGTH')
                v = compensate_bme(int.from_bytes(b[3:6], 'big') >> 4,
                                   int.from_bytes(b[:3], 'big') >> 4, int.from_bytes(b[6:8], 'big'), c)
                if not -40 <= v['temperature_c'] <= 85 or not 30000 <= v['pressure_pa'] <= 110000:
                    raise ValueError('BME_RANGE')
                values = dict(temperature_c=v['temperature_c'], ambient_pressure_pa=v['pressure_pa'],
                              relative_humidity_percent=v['humidity_pct'])
            else:
                if ident['ina_manufacturer_id'] != 0x5449 or ident['ina_die_id'] >> 4 != 0x227:
                    raise ValueError('INA_ID')
                if type(raw['ina_flags']) is not int or not raw['ina_flags'] & 8 or raw['ina_flags'] & 4:
                    raise ValueError('INA_NOT_READY_OR_OVERFLOW')
                v = convert_ina(bytes.fromhex(raw['ina_frame_hex']))
                values = dict(current_a=v['current_ma']/1000, bus_voltage_v=v['bus_voltage_v'], power_w=v['power_w'])
            if not all(math.isfinite(value) for value in values.values()):
                raise ValueError('NON_FINITE_SENSOR')
            result.update(values)
        except (ValueError, KeyError, TypeError, OverflowError) as exc:
            errors[name] = str(exc)[:100]
    result.update(seq=frame['seq'], boot_id=frame['boot_id'], pico_ms=frame['pico_ms'],
                  firmware=frame['firmware'], device_id=frame['device_id'], monotonic_s=now,
                  received_at=utc_now(), connected=True, valid=not errors, sensor_errors=errors,
                  reason=('WARMING_UP' if errors == {'sdp':'WARMING_UP'} else 'PICO_SENSOR_ERROR') if errors else None,
                  pwm_applied_percent=0, fan_locked_stop=True, gp16_level=0,
                  raw=deepcopy(raw))
    return result


class PicoMonitor:
    simulation = False
    supports_runs = False
    name = 'pico_monitor'
    pwm = 0

    def __init__(self, port=PORT, clock=time.monotonic, serial_factory=None):
        self.port, self.clock, self.serial_factory = port, clock, serial_factory
        self.lock = threading.Lock()
        self.latest = empty_sample()
        self.problem = 'none'
        self.halt, self.stop_pending = threading.Event(), threading.Event()
        self.thread = None
        self.last_boot, self.last_seq = None, -1
        self.connection = None

    @property
    def fault(self):
        with self.lock:
            return self.problem

    def start(self):
        self.thread = threading.Thread(target=self._loop, daemon=True, name='pico-usb-monitor')
        self.thread.start()

    def close(self):
        self.halt.set()
        if self.thread:
            self.thread.join(timeout=3)

    def set_pwm(self, value):
        if value != 0:
            raise ValueError('HARDWARE_MONITOR_ONLY')
        self.stop_pending.set()

    def stop(self):
        self.set_pwm(0)

    def validate_response(self, frame):
        validate_envelope(frame)

    def sample(self, now, dt):
        with self.lock:
            result = deepcopy(self.latest)
        if result['monotonic_s'] is not None and now - result['monotonic_s'] > 1.5:
            result.update(valid=False, reason='PICO_STALE', connected=False)
        return result

    def _exchange(self, command):
        ident = uuid4().hex
        body = {'cmd':command} if isinstance(command,str) else dict(command)
        body['id'] = ident
        self.connection.write((json.dumps(body)+'\n').encode())
        deadline = self.clock() + 1
        pending = bytearray()
        while not self.halt.is_set() and self.clock() < deadline:
            part = self.connection.read_until(b'\n', size=4097-len(pending))
            if not part:
                continue
            pending.extend(part)
            if len(pending) > 4096:
                raise ValueError('PICO_FRAME_LENGTH')
            if not pending.endswith(b'\n'):
                continue
            try:
                frame = json.loads(pending)
            except ValueError:
                raise ValueError('PICO_INVALID_JSON') from None
            pending.clear()
            if not isinstance(frame, dict) or frame.get('id') != ident:
                continue
            self.validate_response(frame)
            if frame['boot_id'] == self.last_boot and frame['seq'] <= self.last_seq:
                raise ValueError('PICO_SEQUENCE')
            self.last_boot, self.last_seq = frame['boot_id'], frame['seq']
            return frame
        raise TimeoutError('PICO_TIMEOUT')

    def _failure(self, reason):
        with self.lock:
            self.latest = empty_sample(reason)
            self.problem = reason

    def _loop(self):
        while not self.halt.is_set():
            try:
                if self.connection is None:
                    factory = self.serial_factory
                    if factory is None:
                        import serial
                        factory = serial.Serial
                    self.connection = factory(self.port, 115200, timeout=.15, write_timeout=.3, exclusive=True)
                    self.connection.reset_input_buffer()
                start = self.clock()
                if self.stop_pending.is_set():
                    self.stop_pending.clear()
                    self._exchange('stop')
                result = decode_sample(self._exchange('sample'), self.clock())
                with self.lock:
                    self.latest = result
                    self.problem = 'none' if result['valid'] or result['reason']=='WARMING_UP' else 'PICO_SENSOR_ERROR'
                self.halt.wait(max(0, .5 - (self.clock()-start)))
            except Exception as exc:
                reason = str(exc) if isinstance(exc, ValueError) and str(exc).startswith('PICO_') else 'PICO_DISCONNECTED'
                self._failure(reason)
                if self.connection:
                    self.connection.close()
                    self.connection = None
                self.halt.wait(1)
        if self.connection:
            self.connection.close()
            self.connection = None
