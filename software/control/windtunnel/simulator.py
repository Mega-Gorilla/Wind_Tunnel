"""Synthetic first-order model; not a calibrated fan or wind-speed model."""
import math


class SimulatedPico:
    simulation = True
    supports_runs = True
    name = 'simulated_pico'

    def start(self):
        pass

    def close(self):
        pass

    def __init__(self):
        self.pwm = 0.0
        self.rpm = 0.0
        self.seq = 0
        self.fault = "none"

    def set_pwm(self, value):
        self.pwm = float(value)

    def stop(self):
        self.set_pwm(0)

    def sample(self, now, dt):
        self.seq += 1
        self.rpm += (self.pwm * 24 - self.rpm) * (1 - math.exp(-max(0, dt) / 1.2))
        if self.rpm < 0.5:
            self.rpm = 0.0
        valid = self.fault == "none"
        current = 0.004 + 0.35 * (self.pwm / 100) ** 2
        return {
            "simulation": True, "source": "simulated_pico", "seq": self.seq,
            "monotonic_s": now, "connected": self.fault != "offline",
            "valid": valid, "reason": None if valid else self.fault,
            "pwm_applied_percent": self.pwm if self.fault != "offline" else None,
            "rpm_estimated": round(self.rpm, 1) if valid else None,
            "pulses_per_revolution_assumed": 2,
            "differential_pressure_pa": round(-20 * (self.rpm / 2400) ** 2, 3) if valid else None,
            "temperature_c": 27 + 0.1 * math.sin(now / 20) if valid else None,
            "relative_humidity_percent": 36.0 if valid else None,
            "ambient_pressure_pa": 102350.0 if valid else None,
            "bus_voltage_v": 12.0 if valid else None,
            "current_a": round(current, 5) if valid else None,
            "power_w": round(12 * current, 4) if valid else None,
            "airspeed_m_s": None, "airspeed_reason": "pressure_mapping_and_calibration_pending",
            "sw1_position": "unknown", "settled": None,
        }
