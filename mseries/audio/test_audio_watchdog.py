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


class ProbeTests(unittest.TestCase):
    def setUp(self):
        self.saved = (watchdog.shutil.which, watchdog.run)

    def tearDown(self):
        watchdog.shutil.which, watchdog.run = self.saved

    def fake(self, tools, returncode=0):
        calls = []
        watchdog.shutil.which = lambda name: '/usr/bin/' + name if name in tools else None
        def run(*args, **kwargs):
            calls.append(args[0])
            return type('R', (), {'returncode': returncode, 'stdout': ''})()
        watchdog.run = run
        return calls

    def test_prefers_pactl(self):
        calls = self.fake({'pactl', 'wpctl'})
        self.assertTrue(watchdog.probe())
        self.assertEqual(calls, ['pactl'])

    def test_falls_back_to_wpctl_when_pactl_is_missing(self):
        calls = self.fake({'wpctl'})
        self.assertTrue(watchdog.probe())
        self.assertEqual(calls, ['wpctl'])

    def test_a_failing_probe_is_a_failure(self):
        self.fake({'wpctl'}, returncode=1)
        self.assertFalse(watchdog.probe())

    def test_no_tool_at_all_never_reports_a_failure(self):
        calls = self.fake(set())
        self.assertTrue(watchdog.probe())
        self.assertEqual(calls, [])


class HangSimulation(unittest.TestCase):
    """Runs the real main loop against a simulated hang (fast clock, fake system calls)."""

    class Done(Exception):
        pass

    def setUp(self):
        self.saved = {name: getattr(watchdog, name) for name in (
            'apple_silicon', 'session_ok', 'units_state', 'probe', 'restart_stack', 'notify',
            'TICK', 'SETTLE', 'PROBE_INTERVAL', 'STACK_GAP')}
        self.saved_sleep = watchdog.time.sleep
        self.restarts = 0
        self.notices = []
        self.ticks = 0
        watchdog.apple_silicon = lambda: True
        watchdog.session_ok = lambda: True
        watchdog.units_state = lambda: 'active'
        watchdog.notify = lambda headline, body: self.notices.append(headline)
        watchdog.TICK = watchdog.PROBE_INTERVAL = 0.0
        watchdog.SETTLE = watchdog.STACK_GAP = 0.0

        def sleep(_seconds):
            self.ticks += 1
            if self.ticks > 60:
                raise self.Done()
        watchdog.time.sleep = sleep

    def tearDown(self):
        for name, value in self.saved.items():
            setattr(watchdog, name, value)
        watchdog.time.sleep = self.saved_sleep

    def run_loop(self):
        with self.assertRaises(self.Done):
            watchdog.main()

    def test_a_hang_that_a_restart_cures_is_restarted_once(self):
        state = {'hung': True}
        watchdog.probe = lambda: not state['hung']

        def restart():
            self.restarts += 1
            state['hung'] = False
            return True
        watchdog.restart_stack = restart
        self.run_loop()
        self.assertEqual(self.restarts, 1)
        self.assertEqual(self.notices, ['Audio restarted'])

    def test_a_healthy_server_is_never_restarted(self):
        watchdog.probe = lambda: True
        watchdog.restart_stack = lambda: self.fail('restarted a healthy server')
        self.run_loop()

    def test_a_single_failed_probe_is_not_enough(self):
        answers = iter([False] + [True] * 100)
        watchdog.probe = lambda: next(answers)
        watchdog.restart_stack = lambda: self.fail('restarted after one failed probe')
        self.run_loop()

    def test_a_hang_nothing_cures_stops_at_the_budget_and_tells_the_user_once(self):
        watchdog.probe = lambda: False

        def restart():
            self.restarts += 1
            return True
        watchdog.restart_stack = restart
        self.run_loop()
        self.assertEqual(self.restarts, 3)
        self.assertEqual(self.notices.count('Audio is not responding'), 1)

    def test_nothing_happens_while_the_screen_is_locked(self):
        watchdog.session_ok = lambda: False
        watchdog.probe = lambda: False
        watchdog.restart_stack = lambda: self.fail('restarted under the lock screen')
        self.run_loop()


if __name__ == '__main__':
    unittest.main()
