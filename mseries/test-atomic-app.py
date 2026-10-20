#!/usr/bin/env python3
"""Fault and concurrency checks for the prepared-release activation prototype."""
import importlib.util
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

SCRIPT = Path(__file__).with_name('atomic-app.py')
SPEC = importlib.util.spec_from_file_location('atomic_app', SCRIPT)
APP = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(APP)


class AtomicAppTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name)
        self.root = self.directory / 'store'
        self.sources = []
        for name in ('old', 'new'):
            source = self.directory / name
            source.mkdir()
            (source / 'start').write_text('#!/bin/sh\nprintf "' + name + '\\n"\n')
            (source / 'start').chmod(0o755)
            self.sources.append(source)

    def deploy(self, store, index):
        return store.deploy(self.sources[index], 'start', str(index) * 64, 'test-publisher')

    def launched(self):
        return subprocess.check_output([str(self.root / 'demo/current/app/start')], text=True).strip()

    def test_update_and_rollback_keep_complete_releases(self):
        with APP.Store(self.root, 'demo') as store:
            first = self.deploy(store, 0)
            second = self.deploy(store, 1)
            self.assertEqual(first['current'], second['previous'])
            self.assertEqual('new', self.launched())
            store.rollback()
            self.assertEqual('old', self.launched())
            self.assertEqual(2, len(list(store.releases.iterdir())))

    def test_failed_activation_keeps_previous_app_and_history(self):
        with APP.Store(self.root, 'demo') as store:
            first = self.deploy(store, 0)
            with patch.object(APP.os, 'replace', side_effect=OSError('interrupted activation')):
                with self.assertRaises(OSError):
                    self.deploy(store, 1)
            self.assertEqual(first['current'], store.status()['current'])
            self.assertEqual('old', self.launched())
            self.assertFalse(list(store.path.glob('.staging-*')))
            self.assertFalse(list(store.path.glob('.current-*')))

    def test_partial_copy_never_changes_selector(self):
        with APP.Store(self.root, 'demo') as store:
            self.deploy(store, 0)
            with patch.object(APP.shutil, 'copytree', side_effect=OSError('disk full')):
                with self.assertRaises(OSError):
                    self.deploy(store, 1)
            self.assertEqual('old', self.launched())
            self.assertFalse(list(store.path.glob('.staging-*')))

    def test_launch_path_is_pinned_across_an_update(self):
        with APP.Store(self.root, 'demo') as store:
            self.deploy(store, 0)
            old_launch = store.launch()
            self.deploy(store, 1)
            self.assertEqual('old', subprocess.check_output([str(old_launch)], text=True).strip())
            self.assertEqual('new', self.launched())
        output = subprocess.check_output([
            sys.executable, str(SCRIPT), '--root', str(self.root), '--app', 'demo', 'run', '--'
        ], text=True)
        self.assertEqual('new', output.strip())

    def test_sync_failure_after_switch_reports_active_but_not_durable(self):
        with APP.Store(self.root, 'demo') as store:
            self.deploy(store, 0)
            replaced = False
            original_replace = APP.os.replace
            original_sync = APP.sync_directory

            def replace(source, target):
                nonlocal replaced
                original_replace(source, target)
                replaced = True

            def sync(path):
                if replaced and Path(path) == store.path:
                    raise OSError('simulated directory I/O failure')
                original_sync(path)

            with patch.object(APP.os, 'replace', side_effect=replace), \
                    patch.object(APP, 'sync_directory', side_effect=sync):
                result = self.deploy(store, 1)
            self.assertFalse(result['activation_durable'])
            self.assertEqual('new', self.launched())
            store.rollback()
            self.assertEqual('old', self.launched())

    def test_first_install_syncs_new_parent_directory_entries(self):
        with patch.object(APP, 'sync_directory', wraps=APP.sync_directory) as sync:
            with APP.Store(self.root, 'demo'):
                pass
        synced = [call.args[0].resolve() for call in sync.call_args_list]
        self.assertIn(self.directory.resolve(), synced)
        self.assertIn(self.root.resolve(), synced)
        self.assertIn((self.root / 'demo').resolve(), synced)

    def test_escaping_symlink_is_rejected(self):
        (self.sources[1] / 'escape').symlink_to('/etc/passwd')
        with APP.Store(self.root, 'demo') as store:
            self.deploy(store, 0)
            with self.assertRaises(ValueError):
                self.deploy(store, 1)
            self.assertEqual('old', self.launched())

    def test_missing_entrypoint_and_rollback_fail_without_activation(self):
        with APP.Store(self.root, 'demo') as store:
            with self.assertRaises(ValueError):
                store.rollback()
            (self.sources[0] / 'start').unlink()
            with self.assertRaises(ValueError):
                self.deploy(store, 0)
            self.assertIsNone(store.status()['current'])

    def test_concurrent_deployments_serialize_history(self):
        processes = [subprocess.Popen([
            sys.executable, str(SCRIPT), '--root', str(self.root), '--app', 'demo',
            'deploy', '--source', str(source), '--entrypoint', 'start',
            '--artifact-sha256', str(index) * 64, '--publisher-fingerprint', 'test',
        ], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            for index, source in enumerate(self.sources)]
        for process in processes:
            stdout, stderr = process.communicate(timeout=15)
            self.assertEqual(0, process.returncode, stdout + stderr)
        with APP.Store(self.root, 'demo') as store:
            self.assertIsNotNone(store.status()['previous'])
            current = self.launched()
            store.rollback()
            self.assertNotEqual(current, self.launched())


if __name__ == '__main__':
    unittest.main()
