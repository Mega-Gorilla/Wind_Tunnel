"""One-shot MicroPython RAM test; never writes Pico files or runs the fan."""
from machine import Pin, I2C, unique_id
fan_stop = Pin(16, Pin.OUT, value=0)
import time
import json
import binascii


def emit(kind, **data):
    data.update(kind=kind, pico_ms=time.ticks_ms(), gp16_level=fan_stop.value())
    print(json.dumps(data))


def crc8(data):
    crc = 255
    for value in data:
        crc ^= value
        for _ in range(8):
            crc = ((crc << 1) ^ 0x31) & 255 if crc & 128 else (crc << 1) & 255
    return crc


def words(data):
    if len(data) % 3:
        raise ValueError("SDP frame length")
    result = []
    for offset in range(0, len(data), 3):
        if crc8(data[offset:offset + 2]) != data[offset + 2]:
            raise ValueError("SDP CRC at byte %d" % offset)
        result.append((data[offset] << 8) | data[offset + 1])
    return result


def hx(data):
    return binascii.hexlify(data).decode()


def wait_bme(bus, mask, timeout_ms=200):
    start = time.ticks_ms()
    while bus.readfrom_mem(0x77, 0xF3, 1)[0] & mask:
        if time.ticks_diff(time.ticks_ms(), start) > timeout_ms:
            raise OSError("BME status timeout")
        time.sleep_ms(2)


def ina_read(bus, register):
    data = bus.readfrom_mem(0x40, register, 2)
    return (data[0] << 8) | data[1]


def ina_write(bus, register, value):
    bus.writeto_mem(0x40, register, bytes([value >> 8, value & 255]))


i0 = None
i1 = None
original = None
ina_original = None
sdp_started = False
try:
    assert crc8(b'\xbe\xef') == 0x92
    assert fan_stop.value() == 0
    emit("start", device_id=hx(unique_id()), samples=30, interval_ms=1000,
         warmup_ms=5000, fan_command_percent=0,
         sdp_mode="0x3615 differential pressure, sensor average-till-read",
         bme_mode="forced; T/P/H x1; IIR off",
         ina_mode="triggered current and bus; 16 averages; 1.1 ms per conversion")
    for gp in (0, 1, 2, 3):
        if not Pin(gp, Pin.IN).value():
            raise OSError("I2C idle Low on GP%d" % gp)
    i0 = I2C(0, sda=Pin(0), scl=Pin(1), freq=100000, timeout=50000)
    i1 = I2C(1, sda=Pin(2), scl=Pin(3), freq=100000, timeout=50000)
    i0.writeto(0x25, b'\x3f\xf9')
    time.sleep_ms(2)
    i0.writeto(0x25, b'\x36\x7c')
    time.sleep_ms(1)
    i0.writeto(0x25, b'\xe1\x02')
    time.sleep_ms(1)
    product_frame = i0.readfrom(0x25, 18)
    ident = words(product_frame)
    product = (ident[0] << 16) | ident[1]
    if product & 0xffffff00 != 0x03020b00:
        raise ValueError("Unexpected SDP product: %08x" % product)
    chip = i1.readfrom_mem(0x77, 0xD0, 1)[0]
    if chip != 0x60:
        raise ValueError("BME chip ID mismatch")
    ina_manufacturer = ina_read(i1, 0xFE)
    ina_die = ina_read(i1, 0xFF)
    if ina_manufacturer != 0x5449 or ina_die >> 4 != 0x227:
        raise ValueError("INA260 identity mismatch")
    ina_original = ina_read(i1, 0x00)
    # Preserve reserved bits, never set reset bit. Each trigger yields a stable
    # register set after CVRF, avoiding mixed continuous-conversion samples.
    ina_trigger = (ina_original & 0x7000) | 0x0523
    wait_bme(i1, 1)
    cal1 = i1.readfrom_mem(0x77, 0x88, 26)
    cal2 = i1.readfrom_mem(0x77, 0xE1, 7)
    original = {"ctrl_hum": i1.readfrom_mem(0x77, 0xF2, 1)[0],
                "ctrl_meas": i1.readfrom_mem(0x77, 0xF4, 1)[0],
                "config": i1.readfrom_mem(0x77, 0xF5, 1)[0]}
    emit("identity", sdp_product_hex="%08x" % product,
         sdp_identity_frame_hex=hx(product_frame), sdp_identity_crc_ok=True,
         bme_chip_id=chip, bme_cal_88_hex=hx(cal1), bme_cal_e1_hex=hx(cal2),
         bme_original_registers=original,
         ina_address=0x40, ina_manufacturer_id=ina_manufacturer, ina_die_id=ina_die,
         ina_original_config=ina_original, ina_test_config=ina_trigger)
    i1.writeto_mem(0x77, 0xF4, bytes([original["ctrl_meas"] & 0xfc]))
    wait_bme(i1, 8)
    i1.writeto_mem(0x77, 0xF5, b'\x00')
    i1.writeto_mem(0x77, 0xF2, b'\x01')
    i0.writeto(0x25, b'\x36\x15')
    sdp_started = True
    time.sleep_ms(5000)
    start = time.ticks_ms()
    for index in range(30):
        delay = index * 1000 - time.ticks_diff(time.ticks_ms(), start)
        if delay > 0:
            time.sleep_ms(delay)
        fan_stop.value(0)
        row = {"index": index, "elapsed_ms": time.ticks_diff(time.ticks_ms(), start)}
        try:
            frame = i0.readfrom(0x25, 9)
            row["sdp_frame_hex"] = hx(frame)
            row["sdp_read_ms"] = time.ticks_ms()
            values = words(frame)
            if values[2] != 240:
                raise ValueError("Unexpected SDP scale %d" % values[2])
            row["sdp_crc_ok"] = True
        except Exception as exc:
            row["sdp_error"] = repr(exc)
        try:
            i1.writeto_mem(0x77, 0xF4, b'\x25')
            time.sleep_ms(20)
            wait_bme(i1, 8)
            row["bme_frame_hex"] = hx(i1.readfrom_mem(0x77, 0xF7, 8))
            row["bme_read_ms"] = time.ticks_ms()
            row["bme_status"] = i1.readfrom_mem(0x77, 0xF3, 1)[0]
        except Exception as exc:
            row["bme_error"] = repr(exc)
        try:
            ina_write(i1, 0x00, ina_trigger)
            triggered = time.ticks_ms()
            while True:
                flags = ina_read(i1, 0x06)
                if flags & 8:
                    break
                if time.ticks_diff(time.ticks_ms(), triggered) > 200:
                    raise OSError("INA260 conversion-ready timeout")
                time.sleep_ms(2)
            row["ina_flags"] = flags
            if flags & 4:
                raise ValueError("INA260 math overflow")
            row["ina_frame_hex"] = hx(b''.join(
                i1.readfrom_mem(0x40, reg, 2) for reg in (0x01, 0x02, 0x03)))
            row["ina_read_ms"] = time.ticks_ms()
            row["ina_conversion_ms"] = time.ticks_diff(time.ticks_ms(), triggered)
        except Exception as exc:
            row["ina_error"] = repr(exc)
        emit("sample", **row)
except Exception as exc:
    emit("fatal", error=repr(exc))
finally:
    fan_stop.value(0)
    errors = []
    if i0 is not None and sdp_started:
        try:
            i0.writeto(0x25, b'\x3f\xf9')
            time.sleep_ms(2)
        except Exception as exc:
            errors.append("SDP stop: " + repr(exc))
    if i1 is not None and original is not None:
        try:
            i1.writeto_mem(0x77, 0xF4, b'\x00')
            wait_bme(i1, 8)
            i1.writeto_mem(0x77, 0xF5, bytes([original["config"]]))
            i1.writeto_mem(0x77, 0xF2, bytes([original["ctrl_hum"]]))
            i1.writeto_mem(0x77, 0xF4, bytes([original["ctrl_meas"]]))
        except Exception as exc:
            errors.append("BME restore: " + repr(exc))
    ina_restored = None
    if i1 is not None and ina_original is not None:
        try:
            ina_write(i1, 0x00, ina_original & 0x7fff)
            ina_restored = ina_read(i1, 0x00)
            if ina_restored != ina_original:
                raise ValueError("INA260 config restore mismatch")
        except Exception as exc:
            errors.append("INA restore: " + repr(exc))
    for gp in (0, 1, 2, 3):
        Pin(gp, Pin.IN)
    fan_stop.value(0)
    emit("cleanup", errors=errors, fan_command_percent=0,
         ina_restored_config=ina_restored)
