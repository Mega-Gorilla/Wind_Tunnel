"""Host-side double-precision conversion of preserved sensor bytes.

Sources:
https://www.bosch-sensortec.com/media/boschsensortec/downloads/datasheets/bst-bme280-ds002.pdf
https://sensirion.com/media/documents/90500156/6167E43B/Sensirion_Differential_Pressure_Datasheet_SDP8xx_Digital.pdf
https://www.ti.com/lit/ds/symlink/ina260.pdf
"""
import statistics
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


def summarize(raw):
    records = [entry['data'] for entry in raw['records']]
    identities = [r for r in records if r.get('kind') == 'identity']
    if len(identities) != 1:
        raise ValueError("Missing/duplicate identity record")
    ident = identities[0]
    if 'ina_manufacturer_id' in ident:
        if ident['ina_manufacturer_id'] != 0x5449 or ident['ina_die_id'] >> 4 != 0x227:
            raise ValueError("INA260 identity mismatch")
    c = calibration(bytes.fromhex(ident['bme_cal_88_hex']), bytes.fromhex(ident['bme_cal_e1_hex']))
    samples = []
    for r in records:
        if r.get('kind') != 'sample':
            continue
        if r['gp16_level'] != 0:
            raise ValueError("Fan stop readback failed")
        row = {k: r[k] for k in ('index', 'elapsed_ms', 'pico_ms')}
        errors = []
        if 'sdp_error' in r:
            errors.append(r['sdp_error'])
        else:
            frame = bytes.fromhex(r['sdp_frame_hex'])
            if len(frame) != 9 or any(crc8(frame[i:i+2]) != frame[i+2] for i in (0, 3, 6)):
                raise ValueError("Host SDP CRC failed")
            dp, temp, scale = [int.from_bytes(frame[i:i+2], 'big') for i in (0, 3, 6)]
            if scale != 240:
                raise ValueError("Unexpected SDP scale")
            row.update(differential_pressure_pa=signed(dp, 16) / scale,
                       sdp_chip_temperature_c=signed(temp, 16) / 200.0)
        if 'bme_error' in r:
            errors.append(r['bme_error'])
        else:
            frame = bytes.fromhex(r['bme_frame_hex'])
            if len(frame) != 8:
                raise ValueError("BME frame length")
            adc_p = int.from_bytes(frame[:3], 'big') >> 4
            adc_t = int.from_bytes(frame[3:6], 'big') >> 4
            adc_h = int.from_bytes(frame[6:8], 'big')
            row.update(adc_temperature=adc_t, adc_pressure=adc_p, adc_humidity=adc_h)
            row.update(compensate_bme(adc_t, adc_p, adc_h, c))
        if 'ina_manufacturer_id' in ident:
            if 'ina_error' in r:
                errors.append(r['ina_error'])
            elif not (r.get('ina_flags', 0) & 8) or r['ina_flags'] & 4:
                errors.append('INA260 not ready or overflow')
            else:
                row.update(convert_ina(bytes.fromhex(r['ina_frame_hex'])))
        row['errors'] = errors
        samples.append(row)
    metrics = {}
    for name in ('differential_pressure_pa', 'temperature_c', 'humidity_pct',
                 'pressure_pa', 'sdp_chip_temperature_c',
                 'current_ma', 'bus_voltage_v', 'power_w'):
        values = [r[name] for r in samples if name in r]
        if values:
            metrics[name] = dict(count=len(values), mean=statistics.mean(values),
                                 min=min(values), max=max(values),
                                 sample_stdev=statistics.stdev(values) if len(values) > 1 else None)
    cleanup = [r for r in records if r.get('kind') == 'cleanup']
    return {'identity': ident, 'calibration': c, 'sample_count': len(samples),
            'metrics': metrics, 'samples': samples,
            'sample_errors': sum(bool(r['errors']) for r in samples),
            'fatal_errors': [r for r in records if r.get('kind') == 'fatal'],
            'cleanup': cleanup,
            'notes': ['No automatic zero subtraction or additional absolute-pressure correction applied to SDP.',
                      'BME pressure is local absolute pressure, not reduced to sea level.',
                      'BME T/P/H: forced mode, oversampling x1, IIR off.',
                      'SDP continuous DP compensation, average-till-read; not a 1-second boxcar average.',
                      'Sample timestamps are Pico read times; Pi receipt time is not acquisition time.',
                      'GP16 low is a command/readback, not a physical rotor/RPM measurement.',
                      'When INA260 is present: triggered current/bus, 16 averages, 1.1 ms each; CVRF checked.',
                      'INA260 power register is unsigned even for negative current; 10 mW resolution.',
                      'Temporary RAM diagnostic; Pico flash application unchanged.']}
