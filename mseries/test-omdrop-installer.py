"""Exercise installer failure paths with all absolute destinations redirected to a temp tree."""
from pathlib import Path
import os
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parent

class InstallerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.lib = self.root / 'usr/lib/omdrop'
        script = (ROOT / 'install-omdrop-radio.sh').read_text()
        script = script.replace('repo=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)',
                                'repo=' + str(ROOT.parent))
        script = script.replace('/usr/', str(self.root / 'usr') + '/')
        script = script.replace('need_root install', ':').replace('need_root uninstall', ':')
        self.script = self.root / 'installer.sh'
        self.script.write_text(script)
        bin_dir = self.root / 'bin'
        bin_dir.mkdir()
        for name, body in {'systemctl': 'echo systemctl >> "$CALLS"',
                           'install': 'exit 42'}.items():
            path = bin_dir / name
            path.write_text('#!/bin/sh\n' + body + '\n')
            path.chmod(0o755)
        self.calls = self.root / 'calls'
        self.env = dict(os.environ, PATH=str(bin_dir) + ':' + os.environ['PATH'],
                        CALLS=str(self.calls))

    def run_script(self, command):
        return subprocess.run(['bash', str(self.script), command], env=self.env,
                              capture_output=True, text=True, timeout=10)

    def test_existing_install_is_preserved(self):
        self.lib.mkdir(parents=True)
        marker = self.lib / 'keep'
        marker.write_text('original')
        result = self.run_script('install')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('Refusing to overwrite', result.stderr)
        self.assertEqual(marker.read_text(), 'original')
        self.assertFalse(self.calls.exists())

    def test_failed_copy_aborts_before_system_changes(self):
        result = self.run_script('install')
        self.assertEqual(result.returncode, 42)
        self.assertFalse(self.calls.exists())
        self.assertFalse((self.lib / '.mseries-installed-files').exists())

    def test_uninstall_without_manifest_leaves_services_alone(self):
        result = self.run_script('uninstall')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(self.calls.exists())

if __name__ == '__main__':
    unittest.main()
