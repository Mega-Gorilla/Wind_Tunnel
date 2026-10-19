"""Host-side double-precision conversion of preserved sensor bytes.

Sources:
https://www.bosch-sensortec.com/media/boschsensortec/downloads/datasheets/bst-bme280-ds002.pdf
https://sensirion.com/media/documents/90500156/6167E43B/Sensirion_Differential_Pressure_Datasheet_SDP8xx_Digital.pdf
https://www.ti.com/lit/ds/symlink/ina260.pdf
"""
import struct


def signed(value, bits):
    return value - (1 << bits) if value & (1 << (bits - 1)) else value


def crc8(data):
    crc = 255
    for value in data:
        crc ^= value
        for _ in range(8):
            crc = ((crc << 1) ^ 0x31) & 255 if crc & 128 else (crc << 1) & 255
    return crc


def calibration(first, second):
    if len(first) != 26 or len(second) != 7:
        raise ValueError("BME calibration length")
    values = struct.unpack('<HhhHhhhhhhhh', first[:24])
    c = dict(zip(('T1', 'T2', 'T3', 'P1', 'P2', 'P3', 'P4', 'P5',
                  'P6', 'P7', 'P8', 'P9'), values))
    c.update(H1=first[25], H2=struct.unpack('<h', second[:2])[0],
             H3=second[2], H4=signed((second[3] << 4) | (second[4] & 15), 12),
             H5=signed((second[5] << 4) | (second[4] >> 4), 12),
             H6=signed(second[6], 8))
    if c['T1'] in (0, 65535) or c['P1'] in (0, 65535):
        raise ValueError("Invalid BME calibration")
    return c


def compensate_bme(adc_t, adc_p, adc_h, c):
    if adc_t == 0x80000 or adc_p == 0x80000 or adc_h == 0x8000:
        raise ValueError("BME skipped-measurement sentinel")
    v1 = (adc_t / 16384.0 - c['T1'] / 1024.0) * c['T2']
    v2 = (adc_t / 131072.0 - c['T1'] / 8192.0) ** 2 * c['T3']
    fine = int(v1 + v2)
    temperature = (v1 + v2) / 5120.0
    v1 = fine / 2.0 - 64000.0
    v2 = v1 * v1 * c['P6'] / 32768.0
    v2 += v1 * c['P5'] * 2.0
    v2 = v2 / 4.0 + c['P4'] * 65536.0
    v1 = (c['P3'] * v1 * v1 / 524288.0 + c['P2'] * v1) / 524288.0
    v1 = (1.0 + v1 / 32768.0) * c['P1']
    if v1 == 0:
        raise ValueError("BME pressure divisor zero")
    pressure = (1048576.0 - adc_p - v2 / 4096.0) * 6250.0 / v1
    v1 = c['P9'] * pressure * pressure / 2147483648.0
    v2 = pressure * c['P8'] / 32768.0
    pressure += (v1 + v2 + c['P7']) / 16.0
    h = fine - 76800.0
    h = ((adc_h - (c['H4'] * 64.0 + c['H5'] / 16384.0 * h)) *
         (c['H2'] / 65536.0 * (1.0 + c['H6'] / 67108864.0 * h *
                              (1.0 + c['H3'] / 67108864.0 * h))))
    h *= 1.0 - c['H1'] * h / 524288.0
    return {'temperature_c': temperature, 'pressure_pa': pressure,
            'humidity_pct': min(100.0, max(0.0, h)), 'humidity_unclipped_pct': h}


def convert_ina(frame):
    """Registers 01, 02, 03 in that order, each big-endian; power unsigned."""
    if len(frame) != 6:
        raise ValueError("INA260 frame length")
    current, voltage, power = struct.unpack('>hHH', frame)
    if voltage & 0x8000:
        raise ValueError("INA260 reserved bus-voltage bit set")
    return {'current_ma': current * 1.25, 'bus_voltage_v': voltage * 0.00125,
            'power_w': power * 0.01}
