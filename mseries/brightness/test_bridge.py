import importlib.util
from pathlib import Path
import unittest
from unittest.mock import Mock

spec = importlib.util.spec_from_file_location('bridge', Path(__file__).with_name('shell-bridge.py'))
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class BridgeTests(unittest.TestCase):
    def setUp(self):
        self.bridge = module.Bridge.__new__(module.Bridge)
        self.bridge.settings = Mock()
        self.bridge.settings.get_boolean.return_value = True
        self.bridge.settings.get_int.return_value = 30
        self.bridge.saved = None
        self.bridge.last_set = None
        self.panel = {'value': 315, 'min': 5, 'max': 500}
        self.bridge.panel = Mock(return_value=(5, self.panel))
        def write(serial, panel, value):
            self.panel['value'] = round(value)
            self.bridge.last_set = round(value)
        self.bridge.set_value = Mock(side_effect=write)

    def test_dim_round_trip_restores_original_level(self):
        self.bridge.dim(True)
        self.assertEqual(self.panel['value'], 150)
        self.bridge.dim(True)  # repeated idle events must not replace the original
        self.bridge.dim(False)
        self.assertEqual(self.panel['value'], 315)

    def test_manual_change_during_dim_is_preserved(self):
        self.bridge.dim(True)
        self.panel['value'] = 250
        self.bridge.dim(False)
        self.assertEqual(self.panel['value'], 250)

    def test_disabled_dimming_does_not_touch_backlight(self):
        self.bridge.settings.get_boolean.return_value = False
        self.bridge.dim(True)
        self.bridge.set_value.assert_not_called()

    def test_invalid_auto_targets_cannot_reach_display_api(self):
        for value in (-1, 1.1, float('nan'), float('inf')):
            with self.subTest(value=value), self.assertRaises(ValueError):
                self.bridge.auto(value)
        self.bridge.set_value.assert_not_called()

    def test_auto_does_not_undim_display(self):
        self.bridge.dim(True)
        self.bridge.auto(.9)
        self.assertEqual(self.panel['value'], 150)
