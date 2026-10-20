#!/usr/bin/env python3
import importlib.util
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

source = Path(__file__).resolve().parents[1] / 'launcher/macos-check.py'
spec = importlib.util.spec_from_file_location('macos_check', source)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class ReadinessTests(unittest.TestCase):
    def test_empty_bundle_is_not_ready(self):
        with tempfile.TemporaryDirectory() as folder:
            for check in ('guest', 'firmware'):
                self.assertFalse(module.check(check, Path(folder), 'unused')[0])

    def test_invalid_identity_is_not_ready(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            for name in ('disk.img', 'aux.img'):
                (root / name).write_bytes(b'fixture')
            (root / 'vm.json').write_text('[]')
            self.assertFalse(module.check('guest', root, 'unused')[0])
            (root / 'vm.json').write_text('{"fixture": true}')
            ready, detail = module.check('guest', root, 'unused')
            self.assertTrue(ready)
            self.assertIn('not verified', detail)

    @patch.object(module.shutil, 'which', return_value='/fixture/qemu')
    @patch.object(module.subprocess, 'run')
    def test_qemu_query_does_not_boot_a_guest(self, run, which):
        run.return_value = subprocess.CompletedProcess([], 0, 'vmapple  Apple Virtual Machine\n', '')
        self.assertTrue(module.check('qemu', Path('/unused'), 'qemu')[0])
        self.assertEqual(run.call_args.args[0], ['/fixture/qemu', '-machine', 'help'])
        self.assertEqual(run.call_args.kwargs['timeout'], 5)
        run.side_effect = subprocess.TimeoutExpired('qemu', 5)
        self.assertFalse(module.check('qemu', Path('/unused'), 'qemu')[0])

    def test_files_cannot_imply_hardware_qualification(self):
        self.assertFalse(module.check('qualification', Path('/unused'), 'unused')[0])


if __name__ == '__main__':
    unittest.main()
