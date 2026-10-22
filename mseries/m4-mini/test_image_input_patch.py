#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Exercise candidate-only hook hash updates without editing the source checkout."""
import copy
import importlib.util
import json
from pathlib import Path
import subprocess
import unittest

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('image_inputs', HERE / 'prepare-image-inputs.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class CandidatePatchTests(unittest.TestCase):
    def setUp(self):
        self.hook = module.REPO / module.HOOK
        self.original = self.hook.read_text()
        self.baseline = json.loads((HERE / 'receipts/2026-10-21-gravity-kernel-build.json').read_text())

    def test_same_candidate_needs_no_patch(self):
        self.assertEqual(module.live_hook_patch(self.original, self.baseline, self.baseline), '')

    def test_different_hashes_keep_checks_and_apply_cleanly(self):
        candidate = copy.deepcopy(self.baseline)
        candidate['artifacts']['arch/arm64/boot/Image'] = 'a' * 64
        candidate['config_sha256'] = 'b' * 64
        patch = module.live_hook_patch(self.original, self.baseline, candidate)
        added = [line[1:] for line in patch.splitlines() if line.startswith('+') and not line.startswith('+++')]
        self.assertEqual(len(added), 2)
        self.assertTrue(all('sha256sum --check --status' in line for line in added))
        self.assertIn('a' * 64, patch)
        self.assertIn('b' * 64, patch)
        subprocess.run(['git', 'apply', '--check', '-'], input=patch, text=True, cwd=module.REPO, check=True)
        self.assertEqual(self.hook.read_text(), self.original)

    def test_unknown_hook_baseline_is_rejected(self):
        with self.assertRaises(ValueError):
            module.live_hook_patch('unreviewed hook', self.baseline, self.baseline)


if __name__ == '__main__':
    unittest.main()
