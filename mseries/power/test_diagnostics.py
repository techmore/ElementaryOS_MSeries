import importlib.util
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch


def load(name):
    spec = importlib.util.spec_from_file_location(name, Path(__file__).with_name(name + '.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


sleep = load('sleep_cost')
power = load('power_report')


def valid(**changes):
    result = dict(start_boot_id='boot-a', boot_id='boot-a', action='suspend',
                  start_real='10000', end_real='13600', start_boot='100', end_boot='3700',
                  start_awake='100', end_awake='102', start_energy='50000000',
                  end_energy='48000000', start_charger='0', end_charger='0',
                  start_status='Discharging', end_status='Discharging', energy_full='60000000')
    result.update(changes)
    return result


class FakeSystem:
    def __init__(self):
        self.now = (10000, 100)
        self.awake = 100
        self.notifications = []
        self.lock = 'unlocked'
        self.delivered = True
    def clocks(self): return self.now
    def awake_clock(self): return self.awake
    def boot_id(self): return 'boot-a'
    def lock_state(self): return self.lock
    def sleep(self, seconds): pass
    def notify(self, title, body):
        self.notifications.append((title, body))
        return self.delivered


class SleepTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        for key, value in [('LOG', self.root / 'cost.log'), ('PENDING', self.root / 'pending'),
                           ('POWER_SUPPLY', self.root / 'supplies')]:
            p = patch.object(sleep, key, value)
            p.start(); self.addCleanup(p.stop)
        sleep.POWER_SUPPLY.mkdir()

    def record(self, records):
        sleep.LOG.write_text('\n'.join(' '.join(f'{k}={v}' for k, v in r.items()) for r in records) + '\n')

    def test_valid_cost(self):
        self.assertEqual(sleep.judge(valid()), 'valid')
        self.assertEqual(sleep.used(valid()), (2, 1))
        self.assertIn('2.00 W average', sleep.describe(valid()))

    def test_reject_unreliable_measurements(self):
        cases = [dict(end_real='nan'), dict(start_real='inf'), dict(end_boot='-inf'),
                 dict(start_boot_id='unknown'), dict(boot_id='boot-b'), dict(start_energy='-1'),
                 dict(start_charger='1'), dict(end_status='Charging'), dict(start_charger=''),
                 dict(end_status='Unknown'), dict(end_energy='51000000'), dict(end_real='15000'),
                 dict(end_awake='3700'), dict(end_awake='nan'), dict(end_awake='99')]
        for changes in cases:
            with self.subTest(changes=changes):
                self.assertNotEqual(sleep.judge(valid(**changes)), 'valid')

    def test_missing_and_corrupt_records_do_not_crash(self):
        self.assertIn('not counted', sleep.describe({'verdict': 'valid'}))
        self.assertIn('not counted', sleep.describe(valid(end_real='nan')))
        self.record([{'verdict': 'valid'}, valid(end_real='nan')])
        self.assertEqual(sleep.unannounced(FakeSystem(), 0, set()), [])

    def test_hook_round_trip_and_failed_suspend(self):
        battery = sleep.POWER_SUPPLY / 'macsmc-battery'; battery.mkdir()
        ac = sleep.POWER_SUPPLY / 'macsmc-ac'; ac.mkdir()
        for key, val in dict(type='Battery', present='1', status='Discharging',
                             energy_now='50000000', energy_full='60000000').items():
            (battery / key).write_text(val)
        (ac / 'type').write_text('Mains'); (ac / 'online').write_text('0')
        system = FakeSystem()
        sleep.record_pre(system, 'suspend')
        system.now = (13600, 3700); system.awake = 102
        (battery / 'energy_now').write_text('48000000')
        sleep.record_post(system, 'suspend')
        self.assertFalse(sleep.PENDING.exists())
        self.assertEqual(sleep.last_record()['verdict'], 'valid')
        sleep.record_pre(system, 'suspend')
        system.now = (13610, 3710); system.awake = 112
        sleep.record_post(system, 'suspend')
        self.assertEqual(sleep.last_record()['verdict'], 'no-sleep')

    def test_missing_pre_and_bounded_log(self):
        for _ in range(sleep.KEEP + 2):
            sleep.record_post(FakeSystem(), 'suspend')
        self.assertEqual(len(sleep.records()), sleep.KEEP)
        self.assertEqual(sleep.last_record()['verdict'], 'missing-reading')

    def test_aggregate_sleeps_and_retry_undelivered_notification(self):
        self.record([valid(), valid(start_real='13600', end_real='14200', start_boot='3700',
                                  end_boot='4300', start_awake='102', end_awake='104')])
        system = FakeSystem(); system.now = (14200, 4300)
        # The first long sleep remains in the initial resume batch, even if unlock
        # follows another short sleep. after_resume captures its lower time bound.
        self.assertIsNotNone(sleep.notice(sleep.records()))
        self.record([valid()]); system.now = (13600, 3700)
        shown = set(); system.delivered = False
        sleep.after_resume(system, shown)
        self.assertEqual(len(system.notifications), 3)
        self.assertEqual(shown, set())
        system.delivered = True
        sleep.after_resume(system, shown)
        self.assertEqual(shown, {'13600'})
        sleep.after_resume(system, shown)
        self.assertEqual(len(system.notifications), 4)

    def test_unknown_lock_state_does_not_notify(self):
        self.record([valid()])
        system = FakeSystem(); system.now = (13600, 3700); system.lock = 'unknown'
        sleep.after_resume(system, set())
        self.assertEqual(system.notifications, [])

    def test_logind_property_order_does_not_matter(self):
        result = subprocess.CompletedProcess([], 0, 'LockedHint=no\nActive=yes\n')
        with patch.dict('os.environ', {'XDG_SESSION_ID': 'c1'}), patch.object(sleep.subprocess, 'run', return_value=result):
            self.assertEqual(sleep.System().lock_state(), 'unlocked')
        result.stdout = 'Active=yes\nLockedHint=yes\n'
        with patch.dict('os.environ', {'XDG_SESSION_ID': 'c1'}), patch.object(sleep.subprocess, 'run', return_value=result):
            self.assertEqual(sleep.System().lock_state(), 'locked')

    def test_watcher_restart_does_not_repeat_delivered_notification(self):
        self.record([valid()])
        system = FakeSystem(); system.now = (13600, 3700)
        system.sleep_events = lambda: iter([False])
        with patch.dict('os.environ', {'XDG_RUNTIME_DIR': str(self.root)}):
            sleep.watch(system)
            self.assertEqual(len(system.notifications), 1)
            sleep.watch(system)
            self.assertEqual(len(system.notifications), 1)


class PowerTests(unittest.TestCase):
    def test_nonfinite_and_excessive_samples_are_rejected(self):
        for arg in ['nan', 'inf', '-1', '0', '301']:
            p = subprocess.run([sys.executable, str(Path(power.__file__)), '--sample', arg], capture_output=True)
            self.assertEqual(p.returncode, 2)

    def test_pid_reuse_does_not_attribute_old_process_ticks(self):
        with patch.object(power, 'processes', side_effect=[{'1': ('app', 5, 100)}, {'1': ('app', 500, 101)}]), \
             patch.object(power, 'cpu_totals', return_value=None):
            text = '\n'.join(power.activity_section(1, sleep=lambda _: None))
        self.assertIn('No process used', text)

    def test_charger_power_is_not_whole_machine_power(self):
        with tempfile.TemporaryDirectory() as t, patch.object(power, 'POWER_SUPPLY', Path(t)):
            b = Path(t) / 'battery'; b.mkdir()
            a = Path(t) / 'ac'; a.mkdir()
            for key, value in {'type': 'Battery', 'status': 'Not charging', 'power_now': '0'}.items():
                (b / key).write_text(value)
            (a / 'type').write_text('Mains'); (a / 'online').write_text('1')
            self.assertIn('hides its draw', '\n'.join(power.battery_section()))
            (b / 'status').write_text('Discharging'); (b / 'power_now').write_text('-2500000')
            self.assertIn('2.50 W', '\n'.join(power.battery_section()))


if __name__ == '__main__':
    unittest.main()
