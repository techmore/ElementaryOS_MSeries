#!/usr/bin/python3
"""The CPU ceiling applies only on battery in power-saver; balanced (a burst) or AC lifts it. Fake sysfs, mock powerprofilesctl."""
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent / 'power/mseries-power'


class CapPolicy(unittest.TestCase):
    def run_case(self, on_ac, profile):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            sys_root = root / 'sys'
            (sys_root / 'class/power_supply/macsmc-ac').mkdir(parents=True)
            (sys_root / 'class/power_supply/macsmc-ac/online').write_text('%d\n' % on_ac)
            for name, hw in (('policy0', 2064000), ('policy2', 3036000), ('policy6', 3036000)):
                p = sys_root / 'devices/system/cpu/cpufreq' / name
                p.mkdir(parents=True)
                (p / 'cpuinfo_max_freq').write_text('%d\n' % hw)
                (p / 'scaling_max_freq').write_text('%d\n' % hw)
            bindir = root / 'bin'
            bindir.mkdir()
            tool = bindir / 'powerprofilesctl'
            tool.write_text('#!/bin/sh\n[ "$1" = get ] && echo %s\n' % profile)
            tool.chmod(0o755)
            conf = root / 'power.conf'
            conf.write_text('BATTERY_CAP_KHZ=2208000\n')
            env = {**os.environ, 'MSERIES_SYS': str(sys_root), 'MSERIES_CONF': str(conf), 'PATH': '%s:%s' % (bindir, os.environ['PATH'])}
            subprocess.run(['bash', str(SCRIPT), 'cap'], env=env, check=True, capture_output=True)
            read = lambda n: int((sys_root / 'devices/system/cpu/cpufreq' / n / 'scaling_max_freq').read_text())
            return read('policy0'), read('policy2'), read('policy6')

    def test_battery_power_saver_caps_performance_clusters_only(self):
        self.assertEqual(self.run_case(0, 'power-saver'), (2064000, 2208000, 2208000))

    def test_battery_balanced_lifts_the_cap_for_a_burst(self):
        self.assertEqual(self.run_case(0, 'balanced'), (2064000, 3036000, 3036000))

    def test_ac_is_never_capped(self):
        self.assertEqual(self.run_case(1, 'power-saver'), (2064000, 3036000, 3036000))
        self.assertEqual(self.run_case(1, 'balanced'), (2064000, 3036000, 3036000))


if __name__ == '__main__':
    unittest.main()
