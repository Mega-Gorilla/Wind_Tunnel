"""Pure host tests; no hardware access."""
import unittest
from compensation import calibration, compensate_bme, convert_ina, crc8, signed


class ConversionTests(unittest.TestCase):
    def test_sensirion_crc_vector(self):
        self.assertEqual(crc8(bytes.fromhex('beef')), 0x92)

    def test_signed_fields(self):
        self.assertEqual(signed(0xfff, 12), -1)
        self.assertEqual(signed(0x800, 12), -2048)
        self.assertEqual(signed(0x7ff, 12), 2047)
        self.assertEqual(signed(0xff, 8), -1)

    def test_bosch_temperature_pressure_vector(self):
        c = dict(T1=27504, T2=26435, T3=-1000, P1=36477, P2=-10685,
                 P3=3024, P4=2855, P5=140, P6=-7, P7=15500, P8=-14600,
                 P9=6000, H1=75, H2=362, H3=0, H4=334, H5=50, H6=30)
        result = compensate_bme(519888, 415148, 30000, c)
        self.assertAlmostEqual(result['temperature_c'], 25.08248, places=4)
        self.assertAlmostEqual(result['pressure_pa'], 100653.27, places=1)

    def test_calibration_rejects_empty(self):
        with self.assertRaises(ValueError):
            calibration(bytes(26), bytes(7))

    def test_ti_ina260_datasheet_vector(self):
        result = convert_ina(bytes.fromhex('271025703a7f'))
        self.assertEqual(result['current_ma'], 12500.0)
        self.assertAlmostEqual(result['bus_voltage_v'], 11.98)
        self.assertAlmostEqual(result['power_w'], 149.75)

    def test_ina260_signed_current_unsigned_power(self):
        result = convert_ina(bytes.fromhex('ffff25800001'))
        self.assertEqual(result['current_ma'], -1.25)
        self.assertEqual(result['bus_voltage_v'], 12.0)
        self.assertEqual(result['power_w'], 0.01)

    def test_ina260_invalid_frame(self):
        with self.assertRaises(ValueError):
            convert_ina(bytes(5))
        with self.assertRaises(ValueError):
            convert_ina(bytes.fromhex('000080000000'))


if __name__ == '__main__':
    unittest.main()
