#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Reject failed/foreign artifacts and unsafe or incomplete downloaded payloads."""
import copy
import hashlib
import importlib.util
from pathlib import Path
import stat
import tempfile
import unittest
import zipfile

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('fetch_candidates', HERE / 'fetch-hosted-candidates.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
SHA = 'a' * 40


class ProvenanceTests(unittest.TestCase):
    def setUp(self):
        self.run = {'id': 42, 'repository': {'full_name': module.REPOSITORY},
                    'head_repository': {'full_name': module.REPOSITORY},
                    'path': module.WORKFLOW, 'event': 'workflow_dispatch',
                    'head_sha': SHA, 'status': 'completed', 'conclusion': 'success'}
        self.jobs = [{'name': 'build-m4-kernel', 'status': 'completed', 'conclusion': 'success'}]

    def test_matching_completed_build(self):
        module.validate_run(self.run, self.jobs, 'kernel', SHA, 42)

    def test_foreign_failed_pending_and_wrong_source_runs(self):
        cases = [('status', 'in_progress'), ('conclusion', 'failure'),
                 ('head_sha', 'b' * 40), ('path', '.github/workflows/release.yml'),
                 ('event', 'pull_request'), ('id', 43)]
        for key, value in cases:
            with self.subTest(key=key):
                run = copy.deepcopy(self.run)
                run[key] = value
                with self.assertRaises(ValueError):
                    module.validate_run(run, self.jobs, 'kernel', SHA, 42)
        for key in ['repository', 'head_repository']:
            run = copy.deepcopy(self.run)
            run[key]['full_name'] = 'other/project'
            with self.assertRaises(ValueError):
                module.validate_run(run, self.jobs, 'kernel', SHA, 42)
        for jobs in [[], self.jobs * 2, [dict(self.jobs[0], conclusion='skipped')]]:
            with self.assertRaises(ValueError):
                module.validate_run(self.run, jobs, 'kernel', SHA, 42)

    def test_missing_duplicate_expired_artifacts(self):
        artifact = {'name': 'm4-kernel-candidate-42', 'expired': False, 'id': 5}
        self.assertEqual(module.select_artifact([artifact], 'kernel', 42)['id'], 5)
        for artifacts in [[], [artifact, artifact], [dict(artifact, expired=True)]]:
            with self.assertRaises(ValueError):
                module.select_artifact(artifacts, 'kernel', 42)

    def test_payload_corruption_missing_checksums_and_commit(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'source-commit.txt').write_text(SHA + '\n')
            package = root / 'test_1_arm64.deb'
            package.write_bytes(b'package fixture')
            checksum = hashlib.sha256(package.read_bytes()).hexdigest()
            manifest = root / 'SHA256SUMS'
            manifest.write_text(checksum + '  ' + package.name + '\n')
            self.assertEqual(module.verify_payload(root, SHA), {package.name: checksum})
            package.write_bytes(b'corrupt')
            with self.assertRaises(ValueError):
                module.verify_payload(root, SHA)
            for invalid in [checksum + '  ../outside.deb\n', '',
                            checksum + '  ' + package.name + '\n' + checksum + '  ' + package.name + '\n']:
                manifest.write_text(invalid)
                with self.assertRaises(ValueError):
                    module.verify_payload(root, SHA)
            with self.assertRaises(ValueError):
                module.verify_payload(root, 'b' * 40)

    def test_boot_manifest_requires_both_stage_files(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'source-commit.txt').write_text(SHA)
            for name in ['boot.bin', 'm1n1-stage1.bin']:
                (root / name).write_bytes(name.encode())
            manifest = root / 'SHA256SUMS'
            manifest.write_text(''.join(hashlib.sha256((root / name).read_bytes()).hexdigest()
                                       + '  ' + name + '\n' for name in ['boot.bin', 'm1n1-stage1.bin']))
            self.assertEqual(len(module.verify_payload(root, SHA, 'boot')), 2)
            (root / 'm1n1-stage1.bin').unlink()
            with self.assertRaises(ValueError):
                module.verify_payload(root, SHA, 'boot')

    def test_archive_paths_symlinks_duplicates(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            archive = root / 'artifact.zip'
            for name in ['../escape', '/absolute', 'bad\\name']:
                with zipfile.ZipFile(archive, 'w') as output:
                    output.writestr(name, b'bad')
                with self.assertRaises(ValueError):
                    module.extract(archive, root / 'target')
            link = zipfile.ZipInfo('link')
            link.external_attr = (stat.S_IFLNK | 0o777) << 16
            with zipfile.ZipFile(archive, 'w') as output:
                output.writestr(link, '../escape')
            with self.assertRaises(ValueError):
                module.extract(archive, root / 'target')
            self.assertFalse((root / 'target').exists())
            with zipfile.ZipFile(archive, 'w') as output:
                output.writestr('reproduction/recipe.py', 'source')
            module.extract(archive, root / 'target')
            self.assertEqual((root / 'target/reproduction/recipe.py').read_text(), 'source')


if __name__ == '__main__':
    unittest.main()
