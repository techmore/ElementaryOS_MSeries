#!/usr/bin/python3
import importlib.util
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('trial', Path(__file__).with_name('dock-trial.py'))
trial = importlib.util.module_from_spec(spec)
spec.loader.exec_module(trial)


class ControllerTest(unittest.TestCase):
    def setUp(self):
        self.scratch = tempfile.TemporaryDirectory()
        self.addCleanup(self.scratch.cleanup)
        root = Path(self.scratch.name)
        self.marker = root / 'user-disabled'
        self.marker.write_text('original owner opt-out\n')
        self.calls = []
        self.timer_active = True
        self.patches = [patch.object(trial, 'STATE', root / 'state'),
                        patch.object(trial, 'MARKER', self.marker),
                        patch.object(trial, 'UNITS', root / 'units')]
        for item in self.patches:
            item.start()
            self.addCleanup(item.stop)

    def systemctl(self, *args, **kwargs):
        self.calls.append(args)
        if args == ('is-active', trial.TIMER):
            return SimpleNamespace(stdout='active' if self.timer_active else 'inactive')
        if args == ('is-active', trial.UNIT):
            return SimpleNamespace(stdout='active' if ('start', trial.UNIT) in self.calls else 'inactive')
        if args == ('start', trial.UNIT):
            self.assertFalse(self.marker.exists())
            self.assertIn(('start', trial.TIMER), self.calls)
        return SimpleNamespace(stdout='')

    def test_old_compositor_never_enables(self):
        with patch.object(trial, 'ready', return_value=False), patch.object(trial, 'systemctl', self.systemctl):
            with self.assertRaises(RuntimeError):
                trial.arm(60)
        self.assertTrue(self.marker.exists())
        self.assertNotIn(('start', trial.UNIT), self.calls)

    def test_failed_deadline_never_removes_guard(self):
        self.timer_active = False
        with patch.object(trial, 'ready', return_value=True), patch.object(trial, 'configure'), patch.object(trial, 'systemctl', self.systemctl):
            with self.assertRaises(RuntimeError):
                trial.arm(60)
        self.assertTrue(self.marker.exists())
        self.assertNotIn(('start', trial.UNIT), self.calls)

    def test_arm_then_stop_restores_exact_opt_out(self):
        with patch.object(trial, 'ready', return_value=True), patch.object(trial, 'configure'), patch.object(trial, 'systemctl', self.systemctl):
            trial.arm(60)
            self.assertFalse(self.marker.exists())
            trial.stop()
        self.assertEqual(self.marker.read_text(), 'original owner opt-out\n')
        self.assertIn(('stop', trial.UNIT), self.calls)

    def test_marker_failure_still_stops_unit(self):
        with patch.object(trial, 'restore', side_effect=OSError('simulated I/O failure')), patch.object(trial, 'systemctl', self.systemctl):
            with self.assertRaises(OSError):
                trial.stop()
        self.assertIn(('stop', trial.UNIT), self.calls)

    def test_timer_stop_timeout_still_stops_unit(self):
        def fail_timer(*args, **kwargs):
            self.calls.append(args)
            if args == ('stop', trial.TIMER):
                raise TimeoutError('simulated timeout')
            return SimpleNamespace(stdout='')
        with patch.object(trial, 'systemctl', fail_timer):
            with self.assertRaises(TimeoutError):
                trial.stop()
        self.assertIn(('stop', trial.UNIT), self.calls)


if __name__ == '__main__':
    unittest.main()
