#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Hosted root options must reject ordinary invocations before filesystem work."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

HERE = Path(__file__).resolve().parent


class HostedRootBoundaryTests(unittest.TestCase):
    def test_root_modes_require_explicit_github_environment(self):
        env = dict(os.environ, GITHUB_ACTIONS='false')
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            output = root / 'must-not-exist'
            cases = [
                ('build-research-image.py', ['--hosted-root', '--summary-only', '--inputs', str(root),
                 '--boot-bundle', str(root / 'missing.bin'), '--mkosi-source', str(root),
                 '--image-version', '20261022020000', '--output', str(output)], 'hosted-root mode requires'),
                ('check-desktop-root.py', ['--id-map=host-root', '--root', str(root),
                 '--receipt', str(output)], 'host-root inspection requires'),
                ('test-factory-retention.py', ['--id-map=host-root', '--root', str(root),
                 '--smoke', str(root / 'missing')], 'host-root inspection requires'),
            ]
            for script, args, expected in cases:
                with self.subTest(script=script):
                    result = subprocess.run([sys.executable, str(HERE / script), *args],
                                            env=env, text=True, capture_output=True)
                    self.assertNotEqual(result.returncode, 0)
                    self.assertIn(expected, result.stderr)
                    self.assertFalse(output.exists())


if __name__ == '__main__':
    unittest.main()
