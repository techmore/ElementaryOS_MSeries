import importlib.util
import os
from pathlib import Path
import tempfile
import unittest

spec = importlib.util.spec_from_file_location('gateway', Path(__file__).parents[1] / 'deploy/gateway.py')
gateway = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gateway)


class GatewayTests(unittest.TestCase):
    def test_expand_only_reviewed_imports_and_preserve_live_update_contract(self):
        path = sorted(gateway.IMPORTS)[0]
        base = f'{{\n admin off\n}}\nimport {path}\nexample.org {{ respond "old site" }}\n'.encode()
        deps = {path: b'(existing_log) {\n log {\n output stdout\n }\n}\n'}
        raw = gateway.construct(base, deps, 'a' * 48)
        validated = gateway.construct(base, deps, 'a' * 48, expand=True)
        self.assertIn(f'import {path}'.encode(), raw)
        self.assertNotIn(f'import {path}'.encode(), validated)
        for data in (raw, validated):
            self.assertIn(b'admin off', data)
            self.assertIn(b'example.org { respond "old site" }', data)
            self.assertIn(b'handle_path /' + b'a' * 48 + b'/*', data)
            self.assertIn(b'tls_server_name techmore-2.tailf80972.ts.net', data)
            self.assertNotIn(b'tls_insecure_skip_verify', data)

    def test_unreviewed_syntax_and_existing_mdm_refused(self):
        cases = [b'import /tmp/unreviewed\n', b'import *.caddy\n', b'site { import /tmp/inline }\n',
                 b'example.org { respond {$SECRET} }\n', b'mdm.stoverparc.org { respond ok }\n',
                 b'*.stoverparc.org { respond ok }\n']
        for base in cases:
            with self.subTest(base=base), self.assertRaises(ValueError):
                gateway.construct(base, {}, 'a' * 48)
        path = sorted(gateway.IMPORTS)[0]
        with self.assertRaises(ValueError):
            gateway.construct(f'import {path}\n'.encode(), {path: b'import /tmp/nested\n'}, 'a' * 48)
        with self.assertRaises(ValueError):
            gateway.construct(b'example.org {}', {}, '../invalid')

    def fixture(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        root = Path(directory.name)
        config = root / 'Caddyfile'
        config.write_bytes(b'original')
        config.chmod(0o640)
        recovery = root / 'recovery'; recovery.mkdir()
        base, meta = gateway.capture(config, os.getuid())
        return config, recovery, base, meta

    def test_atomic_success_preserves_mode_and_backup(self):
        config, recovery, base, meta = self.fixture()
        calls = []
        result = gateway.transaction(config, base, b'candidate', meta, recovery,
                                     runner=lambda cmd, directory, phase: calls.append(phase))
        self.assertEqual(result['state'], 'restarted')
        self.assertFalse(result['public_tls_verified'])
        self.assertEqual(config.read_bytes(), b'candidate')
        self.assertEqual(config.stat().st_mode & 0o777, 0o640)
        self.assertEqual((recovery / 'original.Caddyfile').read_bytes(), base)
        self.assertEqual(calls, ['validate', 'restart', 'active'])

    def test_validation_failure_leaves_live_file_untouched(self):
        config, recovery, base, meta = self.fixture()
        def runner(*args):
            raise RuntimeError('validation failed')
        with self.assertRaises(RuntimeError):
            gateway.transaction(config, base, b'candidate', meta, recovery, runner=runner)
        self.assertEqual(gateway.capture(config, os.getuid()), (base, meta))

    def test_failed_restart_rolls_back_and_checks_recovery(self):
        config, recovery, base, meta = self.fixture()
        calls = []
        def runner(cmd, directory, phase):
            calls.append(phase)
            if phase == 'restart':
                raise RuntimeError('restart failed')
        with self.assertRaises(RuntimeError):
            gateway.transaction(config, base, b'candidate', meta, recovery, runner=runner)
        self.assertEqual(config.read_bytes(), base)
        self.assertEqual(calls, ['validate', 'restart', 'rollback', 'rollback-active'])

    def test_concurrent_admin_edit_is_never_overwritten(self):
        config, recovery, base, meta = self.fixture()
        def runner(cmd, directory, phase):
            if phase == 'restart':
                config.write_bytes(b'concurrent administrator edit')
                raise RuntimeError('restart failed')
        with self.assertRaises(ValueError):
            gateway.transaction(config, base, b'candidate', meta, recovery, runner=runner)
        self.assertEqual(config.read_bytes(), b'concurrent administrator edit')

    def test_import_drift_after_validation_prevents_replace(self):
        config, recovery, base, meta = self.fixture()
        count = 0
        def dependencies():
            nonlocal count
            count += 1
            if count == 2:
                raise ValueError('import changed')
        with self.assertRaises(ValueError):
            gateway.transaction(config, base, b'candidate', meta, recovery,
                                runner=lambda *args: None, check_dependencies=dependencies)
        self.assertEqual(config.read_bytes(), base)

    def test_symlink_and_digest_drift_refused(self):
        config, _, _, _ = self.fixture()
        link = config.parent / 'link'; link.symlink_to(config)
        with self.assertRaises(OSError):
            gateway.capture(link, os.getuid())
        with self.assertRaises(ValueError):
            gateway.capture(config, os.getuid(), '0' * 64)


if __name__ == '__main__':
    unittest.main()
