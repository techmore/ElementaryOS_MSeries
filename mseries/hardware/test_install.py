from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class InstallTests(unittest.TestCase):
    def test_offline_stage_idempotence_mask_and_removal(self):
        with tempfile.TemporaryDirectory() as t:
            d = Path(t)
            command = ['bash', str(ROOT / 'install-hardware-support.sh'), '--root', str(d)]
            subprocess.run(command, check=True, capture_output=True)
            unit = d / 'usr/lib/systemd/user/graphical-session.target.wants/mseries-sleep-cost.service'
            self.assertTrue(unit.is_file())
            self.assertTrue((d / 'usr/bin/mseries-power-report').is_file())
            watcher = d / 'usr/lib/systemd/user/graphical-session.target.wants/mseries-peripherals.service'
            self.assertEqual(watcher.readlink(), Path('../mseries-peripherals.service'))
            self.assertEqual((d / 'usr/bin/mseries-peripherals').readlink(),
                             Path('../libexec/mseries/peripherals'))
            self.assertIn('ExecStart=/usr/bin/python3 -I /usr/libexec/mseries/peripherals watch',
                          (d / 'usr/lib/systemd/user/mseries-peripherals.service').read_text())
            self.assertFalse((d / 'etc/udev/hwdb.d/90-mseries-keyboard.hwdb').exists())
            bt = d / 'etc/systemd/system/suspend.target.wants/mseries-bluetooth-resume-fix.service'
            self.assertFalse(bt.is_symlink())
            unit.unlink(); unit.symlink_to('/dev/null')
            subprocess.run(command, check=True, capture_output=True)
            self.assertEqual(unit.readlink(), Path('/dev/null'))
            subprocess.run(command + ['--enable-bluetooth'], check=True, capture_output=True)
            self.assertTrue(bt.is_symlink())
            # Enabling never invokes systemctl/rebind/reloads; native hardware
            # behavior belongs to the separately gated service after resume.
            self.assertIn('ExecStart=/usr/libexec/mseries/bluetooth-resume-fix',
                          (d / 'usr/lib/systemd/system/mseries-bluetooth-resume-fix.service').read_text())
            subprocess.run(command + ['--uninstall'], check=True, capture_output=True)
            self.assertFalse((d / 'usr/bin/mseries-power-report').is_symlink())
            self.assertFalse(watcher.is_symlink())
            self.assertFalse((d / 'usr/bin/mseries-peripherals').is_symlink())
            self.assertFalse((d / 'usr/libexec/mseries/peripherals').exists())
            self.assertFalse(bt.is_symlink())
            self.assertEqual(unit.readlink(), Path('/dev/null'))

    def test_uninstall_preserves_a_preexisting_command(self):
        with tempfile.TemporaryDirectory() as t:
            d = Path(t); command = d / 'usr/bin/mseries-power-report'
            command.parent.mkdir(parents=True)
            command.write_text('administrator command')
            install = ['bash', str(ROOT / 'install-hardware-support.sh'), '--root', str(d)]
            subprocess.run(install, check=True, capture_output=True)
            subprocess.run(install + ['--uninstall'], check=True, capture_output=True)
            self.assertEqual(command.read_text(), 'administrator command')

    def test_keyboard_option_compiles_only_requested_root(self):
        with tempfile.TemporaryDirectory() as t:
            d = Path(t); tools = d / 'tools'; tools.mkdir(); root = d / 'root'; root.mkdir()
            hwdb = tools / 'systemd-hwdb'
            hwdb.write_text('#!/bin/sh\nprintf "%s\\n" "$*" > "' + str(d / 'call') + '"\n')
            hwdb.chmod(0o755)
            import os
            subprocess.run(['bash', str(ROOT / 'install-hardware-support.sh'), '--root', str(root),
                            '--keyboard-keys'], env={**os.environ, 'PATH': str(tools) + ':' + os.environ['PATH']},
                           check=True, capture_output=True)
            self.assertEqual((d / 'call').read_text().strip(), f'--root={root.resolve()} update')
            self.assertTrue((root / 'etc/udev/hwdb.d/90-mseries-keyboard.hwdb').is_file())


if __name__ == '__main__':
    unittest.main()
