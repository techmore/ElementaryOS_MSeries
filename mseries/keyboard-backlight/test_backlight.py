import importlib.util
from pathlib import Path
import tempfile
import unittest

spec = importlib.util.spec_from_file_location('backlight', Path(__file__).with_name('backlight.py'))
backlight = importlib.util.module_from_spec(spec)
spec.loader.exec_module(backlight)


class SensorTests(unittest.TestCase):
    def test_lid_angle_is_never_used_as_illuminance(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for number, name, value in [(0, 'aop-sensors-las', '999'), (1, 'aop-sensors-als', '12.5')]:
                device = root / f'iio:device{number}'
                device.mkdir()
                (device / 'name').write_text(name)
                (device / 'in_illuminance_input').write_text(value)
            self.assertEqual(backlight.illuminance(root), 12.5)

    def test_invalid_sensor_does_not_change_lighting(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            device = root / 'iio:device0'
            device.mkdir()
            (device / 'name').write_text('aop-sensors-als')
            for value in ('nan', 'inf', '-1', 'unavailable'):
                (device / 'in_illuminance_input').write_text(value)
                with self.subTest(value=value), self.assertRaises(OSError):
                    backlight.illuminance(root)


if __name__ == '__main__':
    unittest.main()
