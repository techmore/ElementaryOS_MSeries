#!/usr/bin/python3
"""Run the installer's generated wrapper with private fake dock executables."""
import os
from pathlib import Path
import re
import shlex
import signal
import subprocess
import tempfile
import time
import unittest

REPO = Path(__file__).resolve().parents[2]


class LauncherTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.home = Path(self.temporary.name)
        self.wrapper = self.home / 'wrapper'
        self.patched = self.home / 'patched'
        self.stock = self.home / 'stock'
        self.flag = self.home / '.cache/mseries-dock-failed'
        self.stock_ran = self.home / 'stock-ran'
        self.child_pid = self.home / 'child-pid'
        tools = self.home / 'tools'
        tools.mkdir()
        self.write_executable(tools / 'logger', '#!/bin/sh\nexit 0\n')
        self.write_executable(tools / 'ldd', '#!/bin/sh\n[ "${MISSING_LIB:-}" != 1 ] || echo "libmissing => not found"\nexit 0\n')
        self.write_executable(self.stock, '#!/bin/sh\nprintf stock > "$HOME/stock-ran"\n')
        self.write_executable(self.patched, '''#!/usr/bin/python3
import os, signal, sys
from pathlib import Path
if os.environ.get('CHILD_MODE') == 'hold':
    Path(os.environ['HOME'], 'child-pid').write_text(str(os.getpid()))
    while True:
        signal.pause()
sys.exit(int(os.environ.get('CHILD_MODE', '0')))
''')
        source = (REPO / 'mseries/install-dock-drawers.sh').read_text()
        launcher = re.search(r'cat > "\$wrapper" <<LAUNCHER\n.*?\nLAUNCHER\n', source, re.S)
        self.assertIsNotNone(launcher)
        variables = {'prefix': self.home, 'patched': self.patched,
                     'stock': self.stock, 'wrapper': self.wrapper}
        generation = '\n'.join(f'{key}={shlex.quote(str(value))}' for key, value in variables.items())
        subprocess.run(['bash', '-c', generation + '\n' + launcher[0]], check=True)
        subprocess.run(['sh', '-n', self.wrapper], check=True)
        self.env = os.environ | {'HOME': str(self.home), 'PATH': str(tools) + ':' + os.environ['PATH']}

    @staticmethod
    def write_executable(path, content):
        path.write_text(content)
        path.chmod(0o755)

    def run_wrapper(self, mode='0', **extra):
        return subprocess.run(['sh', self.wrapper], env=self.env | {'CHILD_MODE': mode} | extra,
                              timeout=5, capture_output=True).returncode

    def start_wrapper(self):
        process = subprocess.Popen(['sh', self.wrapper], env=self.env | {'CHILD_MODE': 'hold'},
                                   start_new_session=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        def cleanup():
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            process.wait()
        self.addCleanup(cleanup)
        deadline = time.monotonic() + 3
        while not self.child_pid.exists() and time.monotonic() < deadline:
            time.sleep(.01)
        self.assertTrue(self.child_pid.exists())
        return process, int(self.child_pid.read_text())

    def test_user_disabled_blocks_patched_and_stock_fallback(self):
        marker = self.home / '.config/mseries/dock/user-disabled'
        marker.parent.mkdir(parents=True)
        marker.touch()
        self.patched.unlink()  # Even a missing patched binary must not start stock.
        process = subprocess.Popen(['sh', self.wrapper], env=self.env)
        try:
            with self.assertRaises(subprocess.TimeoutExpired):
                process.wait(timeout=.15)
            self.assertFalse(self.stock_ran.exists())
            self.assertFalse(self.child_pid.exists())
        finally:
            process.terminate()
            process.wait(timeout=3)

    def test_normal_exit_does_not_fallback(self):
        self.assertEqual(self.run_wrapper(), 0)
        self.assertFalse(self.flag.exists())
        self.assertFalse(self.stock_ran.exists())

    def test_signal_statuses_do_not_fallback(self):
        for status in (129, 130, 137, 143):
            with self.subTest(status=status):
                self.assertEqual(self.run_wrapper(str(status)), status)
                self.assertFalse(self.flag.exists())
                self.assertFalse(self.stock_ran.exists())

    def test_real_early_failure_falls_back_and_persists(self):
        self.assertEqual(self.run_wrapper('7'), 0)
        self.assertTrue(self.flag.exists())
        self.assertTrue(self.stock_ran.exists())
        self.stock_ran.unlink()
        self.assertEqual(self.run_wrapper('hold'), 0)
        self.assertTrue(self.stock_ran.exists())
        self.assertFalse(self.child_pid.exists())

    def test_missing_binary_falls_back(self):
        self.patched.unlink()
        self.assertEqual(self.run_wrapper(), 0)
        self.assertTrue(self.stock_ran.exists())

    def test_missing_library_falls_back(self):
        self.assertEqual(self.run_wrapper(MISSING_LIB='1'), 0)
        self.assertTrue(self.stock_ran.exists())

    def test_session_stop_reaps_dock_without_fallback(self):
        for stop in (signal.SIGHUP, signal.SIGINT, signal.SIGTERM):
            with self.subTest(signal=stop):
                self.child_pid.unlink(missing_ok=True)
                process, child = self.start_wrapper()
                process.send_signal(stop)
                self.assertEqual(process.wait(timeout=3), 128 + stop)
                with self.assertRaises(ProcessLookupError):
                    os.kill(child, 0)
                self.assertFalse(self.flag.exists())
                self.assertFalse(self.stock_ran.exists())

    def test_dock_termination_does_not_fallback(self):
        process, child = self.start_wrapper()
        os.kill(child, signal.SIGTERM)
        self.assertEqual(process.wait(timeout=3), 143)
        self.assertFalse(self.flag.exists())
        self.assertFalse(self.stock_ran.exists())


if __name__ == '__main__':
    unittest.main()
