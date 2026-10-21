#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Provisioning regressions with synthetic PCI/DT/firmware inputs; no hardware."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

REPO = Path(__file__).resolve().parents[2]
HELPER = REPO / 'mkosi.images/apple-silicon/mkosi.extra/usr/sbin/mseries-wifi-firmware'


class FirmwareTests(unittest.TestCase):
    def fixture(self, pci, board, chip, signature=False):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        for name in ['bin', 'firmware', 'handoff']:
            (root / name).mkdir()
        for name, body in {'uname': 'echo aarch64', 'lspci': f"echo '{pci}'", 'logger': 'exit 0'}.items():
            path = root / 'bin' / name
            path.write_text('#!/bin/sh\n' + body + '\n')
            path.chmod(0o755)
        (root / 'compatible').write_bytes(board.encode() + b'\0apple,t8132\0')
        for ext in ['bin', 'clm_blob', 'txcap_blob', 'txt'] + (['sig'] if signature else []):
            (root / 'handoff' / f'brcmfmac{chip}-pcie.{ext}').write_text('synthetic fixture\n')
        env = dict(os.environ, PATH=str(root / 'bin') + ':' + os.environ['PATH'],
                   MSERIES_FIRMWARE_DIR=str(root / 'firmware'),
                   MSERIES_HANDOFF_DIR=str(root / 'handoff'),
                   MSERIES_APPLE_COMPATIBLE=str(root / 'compatible'))
        return root, env

    def run_helper(self, env):
        return subprocess.run(['bash', str(HELPER)], env=env, capture_output=True, text=True, check=True).stderr

    def test_j773g_complete_handoff(self):
        root, env = self.fixture('14e4:4434', 'apple,j773g', '4388c0', True)
        self.assertIn('firmware provisioned', self.run_helper(env))
        self.assertEqual(len(list((root / 'firmware').iterdir())), 5)
        for path in (root / 'firmware').iterdir():
            self.assertEqual(path.read_bytes(), (root / 'handoff' / path.name).read_bytes())

    def test_j773g_missing_signature(self):
        _, env = self.fixture('14e4:4434', 'apple,j773g', '4388c0')
        log = self.run_helper(env)
        self.assertIn('MISSING', log)
        self.assertIn('.sig', log)

    def test_other_4388_board_is_not_assigned_mini_revision(self):
        root, env = self.fixture('14e4:4434', 'apple,j513', '4388c0', True)
        self.run_helper(env)
        self.assertEqual(list((root / 'firmware').iterdir()), [])

    def test_legacy_handoffs_do_not_require_signature(self):
        for pci, chip in [('14e4:4425', '4378b1'), ('14e4:4433', '4387c2')]:
            with self.subTest(chip=chip):
                root, env = self.fixture(pci, 'apple,j314s', chip)
                self.assertIn('firmware provisioned', self.run_helper(env))
                self.assertEqual(len(list((root / 'firmware').iterdir())), 4)

    def test_transform_copies_4388_family(self):
        _, env = self.fixture('14e4:4434', 'apple,j773g', '4388c0')
        text = (REPO / 'transform/elementary-grow.sh').read_text()
        function = text.split('detect_chip() {', 1)[1].split('\n}', 1)[0]
        result = subprocess.check_output(['bash', '-c', 'detect_chip() {' + function + '\n}\ndetect_chip'], env=env, text=True)
        self.assertEqual(result.strip(), '4388')


if __name__ == '__main__':
    unittest.main()
