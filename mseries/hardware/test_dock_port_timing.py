import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location('port_timing', Path(__file__).with_name('dock-port-timing.py'))
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


def state(partners=(), dock=(), connected=(), active=()):
    return {'partners': list(partners), 'dock': list(dock), 'connected': list(connected), 'active_modes': list(active)}


class TimingTests(unittest.TestCase):
    def test_requires_clean_detach_before_timing(self):
        t = m.Tracker()
        self.assertEqual(t.observe(0, state(dock=['dock'])), 'wait-detach')
        self.assertEqual(t.observe(1, state()), 'wait-detach')
        self.assertEqual(t.observe(3, state()), 'ready-for-plug')
        self.assertIsNone(t.start)

    def test_partner_and_later_stages_share_one_monotonic_origin(self):
        t = m.Tracker()
        t.observe(0, state());t.observe(2, state())
        t.observe(5, state(partners=['p']))
        t.observe(8, state(partners=['p'], dock=['d']))
        t.observe(10, state(partners=['p'], dock=['d'], connected=['DP']))
        t.observe(12, state(partners=['p'], dock=['d'], connected=['DP'], active=['mode']))
        self.assertEqual(t.first, {'partner_detected': 0, 'dock_enumerated': 3, 'monitor_connected': 5, 'compositor_active': 7})
        self.assertFalse(t.complete)
        self.assertEqual(t.observe(15, state(partners=['p'], dock=['d'], connected=['DP'], active=['mode'])), 'complete')

    def test_partner_arriving_on_baseline_completion_is_not_swallowed(self):
        t = m.Tracker()
        t.observe(0, state())
        self.assertEqual(t.observe(2, state(partners=['new'])), 'waiting-for-active-mode')
        self.assertEqual(t.origin, 'partner_detected')
        self.assertEqual(t.first['partner_detected'], 0)

    def test_existing_partner_does_not_start_a_trial(self):
        t = m.Tracker();t.observe(0, state(partners=['other']));t.observe(2, state(partners=['other']))
        self.assertEqual(t.observe(4, state(partners=['other'])), 'ready-for-plug')
        self.assertIsNone(t.start)

    def test_fallback_origin_is_explicit_and_active_stability_resets(self):
        t = m.Tracker();t.observe(0, state());t.observe(2, state())
        t.observe(4, state(dock=['d'], active=['m']));self.assertEqual(t.origin, 'dock_enumerated')
        t.observe(6, state(dock=['d']));self.assertIsNone(t.active_since)
        t.observe(7, state(dock=['d'], active=['m']));self.assertFalse(t.complete)
        t.observe(10, state(dock=['d'], active=['m']));self.assertTrue(t.complete)


if __name__ == '__main__':
    unittest.main()
