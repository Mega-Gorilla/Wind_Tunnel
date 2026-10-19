"""Shared bounded raw sensor acquisition; never touches fan control pins."""
from machine import Pin, I2C
import binascii
import time

def crc8(data):
    crc = 255
    for v in data:
        crc ^= v
        for _ in range(8):
            crc = ((crc << 1) ^ 0x31) & 255 if crc & 128 else (crc << 1) & 255
    return crc


def words(data):
    result = []
    for n in range(0, len(data), 3):
        if crc8(data[n:n+2]) != data[n+2]:
            raise ValueError('SDP_CRC')
        result.append((data[n] << 8) | data[n+1])
    return result


def hx(data):
    return binascii.hexlify(data).decode()


class Sensors:
    def __init__(self):
        self.buses = {}
        self.ready = {}
        self.retry = {}
        self.identity = {}

    def bus(self, number):
        if number not in self.buses:
            sda, scl = (0, 1) if number == 0 else (2, 3)
            self.buses[number] = I2C(number, sda=Pin(sda), scl=Pin(scl), freq=100000, timeout=50000)
        return self.buses[number]

    def ina_read(self, reg):
        b = self.bus(1).readfrom_mem(0x40, reg, 2)
        return (b[0] << 8) | b[1]

    def wait_bme(self, mask):
        started = time.ticks_ms()
        while self.bus(1).readfrom_mem(0x77, 0xF3, 1)[0] & mask:
            if time.ticks_diff(time.ticks_ms(), started) > 200:
                raise OSError('BME_TIMEOUT')
            time.sleep_ms(2)

    def initialize(self, name):
        if name == 'sdp':
            bus = self.bus(0)
            bus.writeto(0x25, b'\x3f\xf9')
            time.sleep_ms(2)
            bus.writeto(0x25, b'\x36\x7c')
            time.sleep_ms(1)
            bus.writeto(0x25, b'\xe1\x02')
            time.sleep_ms(1)
            frame = bus.readfrom(0x25, 18)
            ident = words(frame)
            if ((ident[0] << 16) | ident[1]) & 0xffffff00 != 0x03020b00:
                raise ValueError('SDP_ID')
            self.identity['sdp_identity_frame_hex'] = hx(frame)
            bus.writeto(0x25, b'\x36\x15')
            self.sdp_started = time.ticks_ms()
        elif name == 'bme':
            bus = self.bus(1)
            if bus.readfrom_mem(0x77, 0xD0, 1)[0] != 0x60:
                raise ValueError('BME_ID')
            self.wait_bme(1)
            self.identity['bme_cal_88_hex'] = hx(bus.readfrom_mem(0x77, 0x88, 26))
            self.identity['bme_cal_e1_hex'] = hx(bus.readfrom_mem(0x77, 0xE1, 7))
            self.identity['bme_chip_id'] = 0x60
            bus.writeto_mem(0x77, 0xF4, b'\x00')
            self.wait_bme(8)
            bus.writeto_mem(0x77, 0xF5, b'\x00')
            bus.writeto_mem(0x77, 0xF2, b'\x01')
        else:
            manufacturer, die = self.ina_read(0xfe), self.ina_read(0xff)
            if manufacturer != 0x5449 or die >> 4 != 0x227:
                raise ValueError('INA_ID')
            self.identity['ina_manufacturer_id'] = manufacturer
            self.identity['ina_die_id'] = die
            self.ina_config = (self.ina_read(0) & 0x7000) | 0x0523
        self.ready[name] = True

    def sample(self):
        row = {'errors': {}}
        for name in ('sdp', 'bme', 'ina'):
            try:
                if not self.ready.get(name):
                    if name in self.retry and time.ticks_diff(time.ticks_ms(), self.retry[name]) < 5000:
                        raise OSError('RETRY_PENDING')
                    self.retry[name] = time.ticks_ms()
                    self.initialize(name)
                if name == 'sdp':
                    if time.ticks_diff(time.ticks_ms(), self.sdp_started) < 5000:
                        row['errors'][name] = 'WARMING_UP'
                        continue
                    frame = self.bus(0).readfrom(0x25, 9)
                    if words(frame)[2] != 240:
                        raise ValueError('SDP_SCALE')
                    row['sdp_frame_hex'] = hx(frame)
                elif name == 'bme':
                    self.bus(1).writeto_mem(0x77, 0xF4, b'\x25')
                    time.sleep_ms(20)
                    self.wait_bme(8)
                    row['bme_frame_hex'] = hx(self.bus(1).readfrom_mem(0x77, 0xF7, 8))
                else:
                    self.bus(1).writeto_mem(0x40, 0, bytes([self.ina_config >> 8, self.ina_config & 255]))
                    started = time.ticks_ms()
                    while True:
                        flags = self.ina_read(6)
                        if flags & 8:
                            break
                        if time.ticks_diff(time.ticks_ms(), started) > 200:
                            raise OSError('INA_TIMEOUT')
                        time.sleep_ms(2)
                    if flags & 4:
                        raise ValueError('INA_OVERFLOW')
                    row['ina_flags'] = flags
                    row['ina_frame_hex'] = hx(b''.join(self.bus(1).readfrom_mem(0x40, r, 2) for r in (1, 2, 3)))
                row[name + '_read_ms'] = time.ticks_ms()
            except Exception as exc:
                self.ready[name] = False
                row['errors'][name] = str(exc)
        row['identity'] = dict(self.identity)
        return row


