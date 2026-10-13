#!/usr/bin/env python3
import importlib.util
from pathlib import Path
import tempfile
import subprocess
import sys
import unittest

spec = importlib.util.spec_from_file_location('kernel_gate', Path(__file__).with_name('check-kernel-config.py'))
gate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gate)


class KernelGateTests(unittest.TestCase):
    def report(self, text, required):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'config'
            path.write_text(text)
            return gate.inspect(path, required)

    def test_disabled_and_absent_are_distinct_and_both_fail(self):
        report = self.report('# CONFIG_DRM_APPLE is not set\nCONFIG_LOCALVERSION="test"\n', ('DRM_APPLE', 'DRM_ASAHI'))
        self.assertEqual(report['symbols']['DRM_APPLE'], 'n')
        self.assertEqual(report['symbols']['DRM_ASAHI'], 'absent')
        self.assertEqual(report['missing_required'], ['DRM_APPLE', 'DRM_ASAHI'])

    def test_drivers_allow_modules_but_page_size_requires_builtin(self):
        report = self.report('CONFIG_DRM_APPLE=m\nCONFIG_ARM64_16K_PAGES=m\n', ('DRM_APPLE', 'ARM64_16K_PAGES'))
        self.assertEqual(report['missing_required'], ['ARM64_16K_PAGES'])

    def test_cli_missing_required_exits_one(self):
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / 'config'
            config.write_text('CONFIG_ARM64_16K_PAGES=y\n')
            result = subprocess.run([sys.executable, str(Path(__file__).with_name('check-kernel-config.py')), str(config)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 1)
            self.assertIn('missing_required', result.stdout)

    def test_empty_input_rejected(self):
        with self.assertRaises(ValueError):
            self.report('not a config\n', ())

    def test_preserved_running_kernel_meets_strict_gate(self):
        report = gate.inspect(Path(__file__).parent / 'fairydust/usb4/running-config', gate.BASELINE + gate.EXPERIMENTAL)
        self.assertEqual(report['missing_required'], [])


if __name__ == '__main__':
    unittest.main()
