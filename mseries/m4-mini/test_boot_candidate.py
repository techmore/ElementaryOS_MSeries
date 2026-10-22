#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Exercise the explicit candidate boundary without changing factory references."""
import copy
import importlib.util
import json
from pathlib import Path
import subprocess
import unittest

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('image_driver', HERE / 'build-research-image.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class CandidateBootTests(unittest.TestCase):
    def test_fresh_receipt_must_keep_sources_board_and_config(self):
        sources = json.loads((HERE / 'research.json').read_text())['gravity_stack']
        dtb = '1' * 64
        receipt = {'trusted_fresh_build_receipts': True,
                   'source_commits': {'bootloader': sources['bootloader']['commit'],
                                      'uboot': sources['u-boot']['commit'], 'kernel': sources['linux']['commit']},
                   'configuration': 'NO_DISPLAY; no appended config overrides',
                   'inputs': {'dtb': {'sha256': dtb}}, 'boot_bin_sha256': 'a' * 64}
        self.assertEqual(module.fresh_boot_hash(receipt, sources, dtb), 'a' * 64)
        for key, value in [('source_commits', {}), ('trusted_fresh_build_receipts', False),
                           ('configuration', 'different'), ('boot_bin_sha256', 'invalid')]:
            changed = copy.deepcopy(receipt)
            changed[key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                module.fresh_boot_hash(changed, sources, dtb)
        with self.assertRaises(ValueError):
            module.fresh_boot_hash(receipt, sources, '2' * 64)

    def test_candidate_patch_keeps_hash_check_and_applies_without_source_change(self):
        hook = module.REPO / module.BOOT_HOOK
        original = hook.read_text()
        baseline = json.loads((HERE / 'receipts/2026-10-21-repeatable-boot-chain.json').read_text())['boot_bin_sha256']
        self.assertEqual(module.boot_hash_patch(original, baseline, baseline), '')
        patch = module.boot_hash_patch(original, baseline, 'a' * 64)
        added = [line for line in patch.splitlines() if line.startswith('+') and not line.startswith('+++')]
        self.assertEqual(len(added), 1)
        self.assertIn('sha256sum --check --status', added[0])
        subprocess.run(['git', 'apply', '--check', '-'], cwd=module.REPO, input=patch, text=True, check=True)
        self.assertEqual(hook.read_text(), original)
        with self.assertRaises(ValueError):
            module.boot_hash_patch('unknown hook', baseline, 'a' * 64)


if __name__ == '__main__':
    unittest.main()
