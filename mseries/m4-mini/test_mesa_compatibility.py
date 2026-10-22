#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Frozen Mesa version boundaries and linkage to independently compiled sources."""
import copy
import hashlib
import importlib.util
import json
import io
import tarfile
import tempfile
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
        self.assertEqual(len(final), 11)
        for phase in module.MANIFEST['phases']:
            path = module.DIRECTORY / phase['file']
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), phase['sha256'])
        compiled = json.loads((HERE / 'receipts/2026-10-22-mesa-combined-candidate-build.json').read_text())
        for name, record in compiled['candidate_sources'].items():
            self.assertEqual(final[name], record['after_sha256'])

    def test_source_bundle_roundtrip_and_frozen_patch_rejection(self):
        with tempfile.TemporaryDirectory(prefix='m4-mesa-bundle-') as temp:
            root = Path(temp)
            source = root / 'source'
            (source / 'licenses').mkdir(parents=True)
            (source / 'licenses/MIT').write_text('Unit fixture license placeholder, not a release source tree.')
            bundle = root / module.BUNDLE_NAME
            record = module.source_bundle(bundle, source)
            self.assertEqual(record['sha256'], hashlib.sha256(bundle.read_bytes()).hexdigest())
            module.verify_source_bundle(bundle, module.CURRENT_VERSION)
            with tarfile.open(bundle) as archive:
                files = {m.name: archive.extractfile(m).read() for m in archive}
            patch = module.BUNDLE_ROOT + '/gravity/mesa-compatibility/' + next(iter(module.snapshot(module.CURRENT_VERSION)['patches']))
            files[patch] += b'\ncorrupt source patch\n'
            index = module.BUNDLE_ROOT + '/SOURCE-SHA256SUMS'
            files[index] = ''.join(hashlib.sha256(data).hexdigest() + '  ' +
                str(Path(name).relative_to(module.BUNDLE_ROOT)) + '\n'
                for name, data in sorted(files.items()) if name != index).encode()
            changed = root / 'changed.tar.gz'
            with tarfile.open(changed, 'w:gz') as archive:
                for name, data in files.items():
                    info = tarfile.TarInfo(name)
                    info.size = len(data)
                    archive.addfile(info, io.BytesIO(data))
            with self.assertRaisesRegex(ValueError, 'patch mismatch'):
                module.verify_source_bundle(changed, module.CURRENT_VERSION)

    def test_source_bundle_rejects_unsafe_and_incomplete_members(self):
        with tempfile.TemporaryDirectory(prefix='m4-mesa-bad-bundle-') as temp:
            root = Path(temp)
            for index, name in enumerate([module.BUNDLE_ROOT + '/../outside', module.BUNDLE_ROOT + '/link']):
                bundle = root / str(index)
                with tarfile.open(bundle, 'w:gz') as archive:
                    info = tarfile.TarInfo(name)
                    if index:
                        info.type = tarfile.SYMTYPE
                        info.linkname = '/outside'
                    archive.addfile(info)
                with self.assertRaisesRegex(ValueError, 'unsafe'):
                    module.verify_source_bundle(bundle, module.CURRENT_VERSION)
            empty = root / 'empty'
            with tarfile.open(empty, 'w:gz'):
                pass
            with self.assertRaisesRegex(ValueError, 'incomplete'):
                module.verify_source_bundle(empty, module.CURRENT_VERSION)

    def test_revision5_snapshot_is_immutable_and_still_accepts_actual_package(self):
        version = '26.3.0~devel+gravity.87ac51d-5'
        selected = module.snapshot(version)
        self.assertEqual(hashlib.sha256(json.dumps(selected, sort_keys=True).encode()).hexdigest(),
                         'd0fa638137aaa15aabb8f231ed335eaa813cad1a90224ec4dc261cd4f9a7833d')
        actual = json.loads((HERE / 'receipts/2026-10-22-mesa5-hosted-success.json').read_text())
        checked = actual['independent_package_check']
        claim = {'package_version': version, 'compatibility_patches': checked['compatibility_patches'],
                 'patched_sources_sha256': checked['patched_sources_sha256'],
                 'supplemental_tests': selected['supplemental_tests']}
        module.metadata(version, claim, claim)
        self.assertEqual(module.supplemental_receipt_names(version),
                         {'helper-divergence', 'rodata-upload'})
        self.assertEqual(module.supplemental_receipt_names(module.CURRENT_VERSION),
                         {'helper-divergence', 'rodata-upload', 'external-sampler'})

    def test_unknown_versions_rejected(self):
        with self.assertRaises(ValueError):
            module.snapshot('future-unreviewed')


if __name__ == '__main__':
    unittest.main()
