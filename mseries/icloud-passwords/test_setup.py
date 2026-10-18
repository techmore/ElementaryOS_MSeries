"""Offline integration contracts; no owner credentials, keyring writes or Apple calls."""
import base64
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
import io
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('setup', HERE / 'setup.py')
setup = importlib.util.module_from_spec(spec)
spec.loader.exec_module(setup)


class IntegrationTests(unittest.TestCase):
    def fixture(self, root):
        (root / 'icp/auth').mkdir(parents=True)
        (root / 'extension').mkdir()
        (root / 'icp/auth/session.py').write_text(
            'def _master_key():\n    key = _key_from_secret_service()\n'
            '    return key if key is not None else _key_from_file()\n')
        (root / 'extension/manifest.json').write_text(json.dumps({
            'background': {'service_worker': 'background.js', 'scripts': ['background.js']},
            'browser_specific_settings': {'gecko': {}}, 'manifest_version': 3}))

    def test_fail_closed_and_available_key(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            self.fixture(root)
            setup.prepare_source(root)
            class SessionError(Exception):
                pass
            scope = {'SessionError': SessionError, '_key_from_secret_service': lambda: None}
            exec(compile((root / 'icp/auth/session.py').read_text(), 'session', 'exec'), scope)
            with self.assertRaises(SessionError):
                scope['_master_key']()
            scope['_key_from_secret_service'] = lambda: b'test-key'
            self.assertEqual(scope['_master_key'](), b'test-key')

    def test_manifest_id_stable_and_chromium_only(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            self.fixture(root)
            extension_id = setup.prepare_source(root)
            manifest = json.loads((root / 'extension/manifest.json').read_text())
            self.assertNotIn('scripts', manifest['background'])
            self.assertNotIn('browser_specific_settings', manifest)
            self.assertEqual(extension_id, 'hagjmolifioccmojhoplpopjklljajno')
            self.assertTrue(base64.b64decode(manifest['key'], validate=True))

    def test_unexpected_apple_root_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            with patch.object(setup.urllib.request, 'urlopen', return_value=io.BytesIO(b'UNTRUSTED-CERTIFICATE')):
                with self.assertRaisesRegex(RuntimeError, 'pin mismatch'):
                    setup.install_ca_bundle(Path(d))
            self.assertFalse((Path(d) / 'ca-bundle.pem').exists())

    def test_upstream_drift_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            self.fixture(root)
            (root / 'icp/auth/session.py').write_text('changed upstream')
            with self.assertRaises(RuntimeError):
                setup.prepare_source(root)


if __name__ == '__main__':
    unittest.main()
