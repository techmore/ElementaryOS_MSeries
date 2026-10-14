import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location('audio_watchdog', Path(__file__).with_name('audio-watchdog.py'))
watchdog = importlib.util.module_from_spec(spec)
spec.loader.exec_module(watchdog)


class BudgetTests(unittest.TestCase):
    def test_first_restart_is_allowed(self):
        self.assertEqual(watchdog.allowed([], 1000.0), (True, ''))

    def test_never_twice_within_the_settle_time(self):
        self.assertFalse(watchdog.allowed([990.0], 1000.0)[0])

    def test_gap_between_stack_restarts(self):
        self.assertFalse(watchdog.allowed([900.0], 1000.0)[0])
        self.assertTrue(watchdog.allowed([800.0], 1000.0)[0])

    def test_budget_is_exhausted_after_three_in_the_window(self):
        ok, why = watchdog.allowed([100.0, 400.0, 700.0], 1000.0)
        self.assertFalse(ok)
        self.assertIn('already restarted', why)

    def test_old_restarts_leave_the_window(self):
        self.assertTrue(watchdog.allowed([100.0, 400.0, 700.0], 3000.0)[0])


if __name__ == '__main__':
    unittest.main()
