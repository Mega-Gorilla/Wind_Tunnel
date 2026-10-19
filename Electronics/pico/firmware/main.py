"""USB JSON commissioning firmware. Deliberately cannot run the fan.

Not the acquisition/control firmware: no RPM or calibrated sensor readings.
Commands (one JSON object per line): status, scan, stop; optional id echoed.
"""
from machine import Pin, I2C, unique_id
fan_stop = Pin(16, Pin.OUT, value=0)
import sys
import time
import select
import json
import os
import binascii

VERSION = "0.1.0-commissioning"
DEVICE_ID = binascii.hexlify(unique_id()).decode()
BOOT_ID = binascii.hexlify(os.urandom(8)).decode()
seq = 0
tach = Pin(15, Pin.IN)  # External 10k pull-up; do not drive the Tach line.


def status():
    return {"firmware": VERSION, "board": "Pico RP2040 / Carrier Rev E",
            "device_id": DEVICE_ID, "fan_enabled": False,
            "fan_command_percent": 0, "gp16_level": fan_stop.value(),
            "tach_level": tach.value(), "rpm": None,
            "rpm_valid": False, "mode": "commissioning_locked_stop"}


def inspect_bus(bus_id, sda, scl):
    result = {"bus": bus_id, "sda_gp": sda, "scl_gp": scl, "hz": 100000}
    # Never attempt recovery clock pulses on this first commissioning pass.
    result["idle_sda"] = Pin(sda, Pin.IN).value()
    result["idle_scl"] = Pin(scl, Pin.IN).value()
    if not result["idle_sda"] or not result["idle_scl"]:
        result["error"] = "bus_not_idle_high_check_power_wiring_pullups"
        return result
    try:
        bus = I2C(bus_id, sda=Pin(sda), scl=Pin(scl), freq=100000, timeout=50000)
        addresses = bus.scan()
        result["addresses"] = ["0x%02x" % a for a in addresses]
        result["identities"] = {}
        if bus_id == 0 and 0x25 in addresses:
            result["identities"]["0x25"] = {"candidate": "SDP810-125Pa", "identity_verified": False}
        if bus_id == 1:
            for address in (0x76, 0x77):
                if address in addresses:
                    chip_id = bus.readfrom_mem(address, 0xD0, 1)[0]
                    result["identities"]["0x%02x" % address] = {
                        "chip_id": chip_id, "bme280_id_matches": chip_id == 0x60}
            if 0x40 in addresses:
                def reg16(reg):
                    b = bus.readfrom_mem(0x40, reg, 2)
                    return (b[0] << 8) | b[1]
                manufacturer, die = reg16(0xFE), reg16(0xFF)
                result["identities"]["0x40"] = {
                    "manufacturer_id": manufacturer, "die_id": die,
                    "ina260_id_matches": manufacturer == 0x5449 and (die >> 4) == 0x227}
    except Exception as exc:
        result["error"] = repr(exc)
    finally:
        Pin(sda, Pin.IN)
        Pin(scl, Pin.IN)
    return result


def respond(request):
    global seq
    fan_stop.value(0)
    seq += 1
    response = {"seq": seq, "boot_id": BOOT_ID, "pico_ms": time.ticks_ms()}
    if not isinstance(request, dict):
        response.update(ok=False, error="JSON_object_required")
        return response
    response["id"] = request.get("id")
    command = request.get("cmd")
    if command in ("status", "stop"):
        response.update(ok=True, status=status())
    elif command == "scan":
        response.update(ok=True, buses=[inspect_bus(0, 0, 1), inspect_bus(1, 2, 3)])
    else:
        response.update(ok=False, error="unsupported_command_fan_locked_stop")
    return response


def main():
    poll = select.poll()
    poll.register(sys.stdin, select.POLLIN)
    line = ""
    overflow = False
    while True:
        fan_stop.value(0)
        if not poll.poll(100):
            continue
        char = sys.stdin.read(1)
        if not char:
            time.sleep_ms(20)
            continue
        if char in "\r\n":
            if line or overflow:
                try:
                    reply = ({"ok": False, "error": "line_too_long"} if overflow
                             else respond(json.loads(line)))
                except Exception as exc:
                    reply = {"ok": False, "error": repr(exc)}
                print(json.dumps(reply))
            line, overflow = "", False
        elif len(line) < 256 and not overflow:
            line += char
        else:
            overflow = True


try:
    main()
finally:
    fan_stop.value(0)
