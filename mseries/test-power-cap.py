#!/usr/bin/python3
"""The CPU ceiling applies only on battery in power-saver; balanced (a burst) or AC lifts it. Fake sysfs, mock powerprofilesctl."""
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent / 'power/mseries-power'


class CapPolicy(unittest.TestCase):
    def run_case(self, on_ac, profile, cap=2208000, fail=False):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            sys_root = root / 'sys'
            (sys_root / 'class/power_supply/macsmc-ac').mkdir(parents=True)
            (sys_root / 'class/power_supply/macsmc-ac/online').write_text('%d\n' % on_ac)
            for name, hw in (('policy0', 2064000), ('policy2', 3036000), ('policy6', 3036000)):
                p = sys_root / 'devices/system/cpu/cpufreq' / name
                p.mkdir(parents=True)
                (p / 'cpuinfo_min_freq').write_text('600000\n')
                (p / 'cpuinfo_max_freq').write_text('%d\n' % hw)
                (p / 'scaling_max_freq').write_text('%d\n' % hw)
            bindir = root / 'bin'
            bindir.mkdir()
            tool = bindir / 'powerprofilesctl'
            tool.write_text('#!/bin/sh\n[ "$1" = get ] && echo %s\n' % profile)
            tool.chmod(0o755)
            conf = root / 'power.conf'
            conf.write_text('BATTERY_CAP_KHZ=%d\n' % cap)
            if fail:
                path = sys_root / 'devices/system/cpu/cpufreq/policy0/scaling_max_freq'
                path.unlink()
                path.mkdir()
            env = {**os.environ, 'MSERIES_SYS': str(sys_root), 'MSERIES_CONF': str(conf), 'PATH': '%s:%s' % (bindir, os.environ['PATH'])}
            result = subprocess.run(['bash', str(SCRIPT), 'cap'], env=env, capture_output=True)
            if fail:
                self.assertNotEqual(result.returncode, 0)
                return
            self.assertEqual(result.returncode, 0, result.stderr.decode())
            read = lambda n: int((sys_root / 'devices/system/cpu/cpufreq' / n / 'scaling_max_freq').read_text())
            return read('policy0'), read('policy2'), read('policy6')

    def test_battery_power_saver_caps_performance_clusters_only(self):
        self.assertEqual(self.run_case(0, 'power-saver'), (2064000, 2208000, 2208000))

    def test_battery_balanced_lifts_the_cap_for_a_burst(self):
        self.assertEqual(self.run_case(0, 'balanced'), (2064000, 3036000, 3036000))

    def test_ac_is_never_capped(self):
        self.assertEqual(self.run_case(1, 'power-saver'), (2064000, 3036000, 3036000))
        self.assertEqual(self.run_case(1, 'balanced'), (2064000, 3036000, 3036000))

    def test_cap_is_clamped_to_hardware_range(self):
        self.assertEqual(self.run_case(0, 'power-saver', 9999999), (2064000, 3036000, 3036000))
        self.assertEqual(self.run_case(0, 'power-saver', 1), (2064000, 600000, 600000))

    def test_write_failure_is_reported(self):
        self.run_case(0, 'power-saver', fail=True)

    def test_missing_sensors_do_not_crash_status(self):
        with tempfile.TemporaryDirectory() as directory:
            env = {**os.environ, 'MSERIES_SYS': directory, 'MSERIES_CONF': directory + '/absent'}
            result = subprocess.run(['bash', str(SCRIPT), 'status'], env=env, capture_output=True)
            self.assertEqual(result.returncode, 0, result.stderr.decode())
            self.assertIn(b'health unknown', result.stdout)

    def test_failed_limit_does_not_persist_success(self):
        with tempfile.TemporaryDirectory() as directory:
            conf = Path(directory)/'power.conf'
            env = {**os.environ, 'MSERIES_SYS': directory, 'MSERIES_CONF': str(conf)}
            result = subprocess.run(['bash', str(SCRIPT), 'limit', '80'], env=env, capture_output=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertFalse(conf.exists())


class VrrEvidence(unittest.TestCase):
    def test_sensor_discovery_and_percentiles(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            sensor = root/'sys/class/hwmon/hwmon42'
            sensor.mkdir(parents=True)
            (sensor/'power7_label').write_text('Total System Power')
            (sensor/'power7_input').write_text('1000000')
            tools = root/'bin'
            tools.mkdir()
            for name, body in (('sudo', 'exit 1'), ('sleep', 'printf 3000000 > "$TEST_SENSOR"')):
                tool = tools/name
                tool.write_text('#!/bin/sh\n' + body + '\n')
                tool.chmod(0o755)
            env = {**os.environ, 'MSERIES_SYS': str(root/'sys'), 'TEST_SENSOR': str(sensor/'power7_input'),
                   'PATH': str(tools) + os.pathsep + os.environ['PATH']}
            result = subprocess.run(['bash', str(SCRIPT.parent/'vrr-check.sh'), '2'], env=env,
                                    capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn('n=2  p10=1.20 W  p50=2.00 W  p90=2.80 W', result.stdout)

    def test_invalid_duration_is_rejected(self):
        result = subprocess.run(['bash', str(SCRIPT.parent/'vrr-check.sh'), '0'], capture_output=True)
        self.assertEqual(result.returncode, 2)


if __name__ == '__main__':
    unittest.main()
