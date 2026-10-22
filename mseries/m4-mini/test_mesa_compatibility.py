#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Frozen Mesa version boundaries and linkage to independently compiled sources."""
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import unittest

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('mesa_compatibility', HERE / 'mesa-compatibility.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class MesaCompatibilityTests(unittest.TestCase):
    def test_actual_historical_build_remains_valid(self):
        old = json.loads((HERE / 'receipts/2026-10-21-hosted-mesa-success.json').read_text())['build']
        module.metadata(module.HISTORICAL_VERSION, old)
        changed = copy.deepcopy(old)
        changed['compatibility_patches'] = {'unreviewed.patch': '0' * 64}
        with self.assertRaises(ValueError):
            module.metadata(module.HISTORICAL_VERSION, changed)

    def test_new_version_requires_exact_patch_source_and_test_claims(self):
        version = module.CURRENT_VERSION
        selected = module.snapshot(version)
        claim = {'package_version': version, 'compatibility_patches': dict(selected['patches']),
                 'patched_sources_sha256': dict(selected['patched_sources_sha256']),
                 'supplemental_tests': dict(selected['supplemental_tests'])}
        module.metadata(version, claim, claim)
        for field in ['package_version', 'compatibility_patches', 'patched_sources_sha256', 'supplemental_tests']:
            broken = copy.deepcopy(claim)
            del broken[field]
            with self.subTest(field=field), self.assertRaises(ValueError):
                module.metadata(version, broken, claim)
        broken = copy.deepcopy(claim)
        broken['patched_sources_sha256']['src/asahi/vulkan/hk_shader.c'] = '0' * 64
        with self.assertRaises(ValueError):
            module.metadata(version, claim, broken)

    def test_patch_files_and_compiled_followup_sources_are_bound(self):
        final = module.snapshot(module.CURRENT_VERSION)['patched_sources_sha256']
        self.assertEqual(len(final), 10)
        for phase in module.MANIFEST['phases']:
            path = module.DIRECTORY / phase['file']
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), phase['sha256'])
        compiled = json.loads((HERE / 'receipts/2026-10-22-mesa-combined-candidate-build.json').read_text())
        for name, record in compiled['candidate_sources'].items():
            self.assertEqual(final[name], record['after_sha256'])

    def test_unknown_versions_rejected(self):
        with self.assertRaises(ValueError):
            module.snapshot('future-unreviewed')


if __name__ == '__main__':
    unittest.main()
