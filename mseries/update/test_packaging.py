#!/usr/bin/env python3
"""The updater's install script and systemd units: staged into a directory, never the host."""
import configparser
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

HERE = Path(__file__).resolve().parent


def unit(name):
    parser = configparser.ConfigParser(strict=False, interpolation=None)
    parser.optionxform = str
    parser.read(HERE / 'systemd' / name)
    return parser


class Packaging(unittest.TestCase):
    def test_install_stages_command_and_units_and_enables_nothing(self):
        with tempfile.TemporaryDirectory() as directory:
            env = dict(os.environ, DESTDIR=directory)
            subprocess.run(['bash', str(HERE / 'install.sh')], env=env, check=True, capture_output=True)
            command = Path(directory, 'usr/sbin/mseries-update')
            self.assertTrue(os.access(command, os.X_OK))
            self.assertEqual(4, len(list(Path(directory, 'usr/lib/systemd/system').glob('mseries-update-*'))))
            self.assertFalse(Path(directory, 'etc').exists(), 'no configuration, source or enablement is installed')
            subprocess.run(['bash', str(HERE / 'install.sh'), '--uninstall'], env=env, check=True, capture_output=True)
            self.assertFalse(command.exists())

    def test_boot_unit_runs_before_any_session_and_only_after_opt_in(self):
        boot = unit('mseries-update-boot.service')
        self.assertIn('display-manager.service', boot['Unit']['Before'])
        self.assertEqual('/var/lib/mseries-update/state.json', boot['Unit']['ConditionPathExists'])
        self.assertEqual('oneshot', boot['Service']['Type'])
        self.assertEqual('/usr/sbin/mseries-update boot', boot['Service']['ExecStart'])

    def test_confirm_unit_runs_after_login_and_only_while_an_update_is_unconfirmed(self):
        confirm = unit('mseries-update-confirm.service')
        self.assertIn('display-manager.service', confirm['Unit']['After'])
        self.assertIn('mseries-update-boot.service', confirm['Unit']['After'])
        self.assertTrue(confirm['Unit']['ConditionPathExists'].endswith('/pending-confirm'))

    def test_no_unit_restarts_the_desktop(self):
        for path in (HERE / 'systemd').iterdir():
            text = path.read_text()
            for forbidden in ('wingpanel', 'gala', 'plank', 'systemctl restart', 'pkill', 'Restart=always'):
                self.assertNotIn(forbidden, text, f'{path.name} must not touch the running session')
        self.assertNotIn('systemctl enable', (HERE / 'install.sh').read_text().split('# Nothing is enabled')[0].replace('#', ''))

    def test_auto_check_is_battery_aware_and_the_timer_is_opt_in(self):
        auto = unit('mseries-update-auto.service')
        self.assertEqual('true', auto['Unit']['ConditionACPower'])
        timer = unit('mseries-update-auto.timer')
        self.assertEqual('timers.target', timer['Install']['WantedBy'])
        self.assertIn('opt-in', timer['Unit']['Description'])


if __name__ == '__main__':
    unittest.main()
