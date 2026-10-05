import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location('measure_dpi', Path(__file__).resolve().parents[1] / 'tools/measure_dpi.py')
measurement = importlib.util.module_from_spec(spec)
spec.loader.exec_module(measurement)


class DpiMeasurementTests(unittest.TestCase):
    def test_pointing_report_signed_axes_ignore_buttons_and_wheel(self):
        self.assertEqual(measurement.motion(bytes.fromhex('1f 90 01 e0 fc ff 01')), (400, -800))
        self.assertEqual(measurement.motion(bytes.fromhex('00 ff 7f 01 80 00 00')), (32767, -32767))
        with self.assertRaises(RuntimeError):
            measurement.motion(bytes.fromhex('05 00 01 00 01 07'))

    def test_known_one_inch_travel_and_either_direction(self):
        self.assertEqual(measurement.measured_dpi(400, 2.54), 400)
        self.assertEqual(measurement.measured_dpi(-3200, 2.54), 3200)
        self.assertAlmostEqual(measurement.measured_dpi(1575, 5), 800.1)
        for distance in (0, -1, float('nan'), float('inf')):
            with self.subTest(distance=distance), self.assertRaises(ValueError):
                measurement.measured_dpi(1, distance)


if __name__ == '__main__':
    unittest.main()
