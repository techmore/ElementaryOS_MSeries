import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


sensors = load(HERE / 'sensors.py', 'sensors')
sys.modules['sensors'] = sensors
scenarios = load(HERE.parent / 'benchmarks' / 'power_scenarios.py', 'power_scenarios')


class Fixture:
    def __init__(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def put(self, rel, value):
        path = self.root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f'{value}\n')


class SensorTests(unittest.TestCase):
    def setUp(self):
        self.fx = Fixture()
        self.addCleanup(self.fx.tmp.cleanup)

    def test_system_power_found_by_label_not_index(self):
        self.fx.put('sys/class/hwmon/hwmon0/name', 'other')
        self.fx.put('sys/class/hwmon/hwmon0/power1_label', 'CPU Power')
        self.fx.put('sys/class/hwmon/hwmon7/name', 'macsmc_hwmon')
        self.fx.put('sys/class/hwmon/hwmon7/power3_label', 'Total System Power')
        self.fx.put('sys/class/hwmon/hwmon7/power3_input', 9500000)
        path = sensors.find_system_power(self.fx.root)
        self.assertEqual(path.name, 'power3_input')
        source = sensors.PowerSource(self.fx.root)
        self.assertEqual(source.name, 'smc_total_system_power')
        self.assertAlmostEqual(source.watts(), 9.5)

    def test_macsmc_rail_preferred_over_other_matching_label(self):
        self.fx.put('sys/class/hwmon/hwmon1/name', 'other')
        self.fx.put('sys/class/hwmon/hwmon1/power1_label', 'Total System Power')
        self.fx.put('sys/class/hwmon/hwmon4/name', 'macsmc_hwmon')
        self.fx.put('sys/class/hwmon/hwmon4/power1_label', 'Total System Power')
        self.assertIn('hwmon4', str(sensors.find_system_power(self.fx.root)))

    def test_battery_fallback_only_while_discharging(self):
        self.fx.put('sys/class/power_supply/hidpp_battery_0/type', 'Battery')
        self.fx.put('sys/class/power_supply/hidpp_battery_0/scope', 'Device')
        self.fx.put('sys/class/power_supply/macsmc-battery/type', 'Battery')
        self.fx.put('sys/class/power_supply/macsmc-battery/scope', 'System')
        self.fx.put('sys/class/power_supply/macsmc-battery/power_now', -7250000)
        self.fx.put('sys/class/power_supply/macsmc-ac/type', 'Mains')
        self.fx.put('sys/class/power_supply/macsmc-ac/online', 0)
        source = sensors.PowerSource(self.fx.root)
        self.assertEqual(source.name, 'battery_flow')
        self.assertEqual(sensors.find_battery(self.fx.root).name, 'macsmc-battery')
        self.assertAlmostEqual(source.watts(), 7.25)
        self.fx.put('sys/class/power_supply/macsmc-ac/online', 1)
        self.assertIsNone(source.watts())

    def test_summarize_reports_median_and_percentiles(self):
        summary = sensors.summarize([5, 1, 3, None, 2, 4])
        self.assertEqual(summary['n'], 5)
        self.assertEqual(summary['median'], 3)
        self.assertAlmostEqual(summary['p10'], 1.4)
        self.assertAlmostEqual(summary['p90'], 4.6)
        self.assertEqual(sensors.summarize([None]), {'n': 0})

    def test_interrupts_keyed_by_stable_device_name(self):
        self.fx.put('proc/interrupts', '\n'.join([
            '           CPU0       CPU1',
            ' 92:       1000        276  AIC2 66381 Level     38bc08000.mbox-recv',
            ' 58:         10          5  AIC2 66598 Level     406408000.mbox-recv',
            ' 12:          1          1  AIC2  1234 Level     apple-spi',
            'IPI0:        50         60  Rescheduling interrupts',
        ]))
        self.assertEqual(sensors.interrupts(root=self.fx.root),
                         {'38bc08000.mbox-recv': 1276, '406408000.mbox-recv': 15})
        self.assertEqual(sensors.interrupts_rate({'a': 10}, {'a': 40, 'b': 3}, 10), {'a': 3.0})

    def test_process_counters_and_delta(self):
        stat = '42 (pantheon-compos) S ' + ' '.join(['0'] * 10) + ' 300 100 ' + ' '.join(['0'] * 30)
        self.fx.put('proc/42/stat', stat)
        self.fx.put('proc/42/comm', 'pantheon-compos')
        self.fx.put('proc/42/task/42/status', 'voluntary_ctxt_switches:\t70\nnonvoluntary_ctxt_switches:\t30')
        self.fx.put('proc/42/task/43/status', 'voluntary_ctxt_switches:\t5\nnonvoluntary_ctxt_switches:\t0')
        self.assertEqual(sensors.pids_named('pantheon-compos', self.fx.root), [42])
        counters = sensors.process_counters(42, self.fx.root)
        self.assertEqual(counters, {'ticks': 400, 'ctxt_switches': 105})
        later = {'ticks': 600, 'ctxt_switches': 1105}
        self.assertEqual(sensors.counters_delta(counters, later, 10, hz=100),
                         {'cpu_pct': 20.0, 'ctxt_switches_per_s': 100.0})
        self.assertIsNone(sensors.process_counters(99, self.fx.root))

    def test_cpu_busy_and_load(self):
        self.fx.put('proc/stat', 'cpu  100 0 100 700 100 0 0 0 0 0\ncpu0 1 1 1 1 1 1 1 1')
        self.fx.put('proc/loadavg', '0.42 0.30 0.20 1/300 1234')
        busy, total = sensors.cpu_times(self.fx.root)
        self.assertEqual((busy, total), (200, 1000))
        self.assertEqual(sensors.cpu_busy_pct((200, 1000), (250, 1100)), 50.0)
        self.assertEqual(sensors.load_average(self.fx.root), 0.42)

    def test_sample_uses_fixed_cadence(self):
        now = [0.0]

        class Source:
            def watts(self):
                return 4.0

        def sleep(seconds):
            now[0] += seconds
        readings = sensors.sample(Source(), 3, clock=lambda: now[0], sleep=sleep)
        self.assertEqual(readings, [4.0, 4.0, 4.0])


class ScenarioTests(unittest.TestCase):
    def test_alternation_rule(self):
        self.assertTrue(scenarios.alternation_ok(['a', 'b', 'a', 'b', 'a', 'b']))
        self.assertFalse(scenarios.alternation_ok(['a', 'a', 'a', 'b', 'b', 'b']))
        self.assertFalse(scenarios.alternation_ok(['a', 'b', 'a', 'b']))
        self.assertFalse(scenarios.alternation_ok(['a', 'b', 'c', 'a', 'b', 'c']))

    def test_parse_redraw_sums_counters(self):
        lines = ['redraw stats /30s: commits=10 [brave(1)=5] redraw_requests=20 vblanks=7 frames_queued=7 '
                 'frames_empty=1', 'redraw stats /30s: commits=2 redraw_requests=3 vblanks=1 frames_queued=1 '
                 'frames_empty=0']
        self.assertEqual(scenarios.parse_redraw(lines), {'commits': 12, 'redraw_requests': 23, 'vblanks': 8,
                                                         'frames_queued': 8, 'frames_empty': 1})

    def test_compare_requires_alternation_and_qualification(self):
        with tempfile.TemporaryDirectory() as tmp:
            paths = []
            for i, (label, watts, qualified) in enumerate([('off', 9.0, True), ('on', 7.0, True),
                                                            ('off', 9.2, True), ('on', 7.1, True),
                                                            ('off', 8.9, True), ('on', 6.9, False)]):
                path = Path(tmp, f'{i}.json')
                path.write_text(json.dumps({'label': label, 'qualified': qualified,
                                            'context': {'time': f'2026-10-21T12:00:0{i}+00:00'},
                                            'scenarios': {'idle': {'watts': {'n': 60, 'median': watts}}}}))
                paths.append(path)
            report = scenarios.compare(paths)
            self.assertTrue(report['alternation_ok'])
            self.assertEqual(report['verdict'],
                             'indicative only: at least one run was taken on a busy machine (--force)')
            self.assertEqual(report['scenarios']['idle']['off']['median'], 9.0)
            self.assertEqual(report['scenarios']['idle']['on']['runs'], 3)
            self.assertIn('not comparable', scenarios.compare(paths[:4])['verdict'])


if __name__ == '__main__':
    unittest.main()
