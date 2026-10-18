import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location('setup', Path(__file__).parents[1] / 'setup_desktop.py')
setup = importlib.util.module_from_spec(spec); spec.loader.exec_module(setup)


class SetupTests(unittest.TestCase):
    def test_exact_public_path_and_loopback_are_preserved(self):
        values = setup.environment('MSERIES_WEBRTC_PUBLIC_URL=https://mdm.stoverparc.org/' + 'a' * 48 + '/\nSTUN_URL=stun:stun.cloudflare.com:3478\n')
        self.assertEqual(values['HOST'], '127.0.0.1')
        self.assertEqual(values['PORT'], '8789')
        self.assertEqual(values['MSERIES_WEBRTC_ORIGINS'], 'http://localhost:8789,http://127.0.0.1:8789,https://mdm.stoverparc.org')

    def test_untrusted_environment_and_invalid_tunnel_refused(self):
        base = 'MSERIES_WEBRTC_PUBLIC_URL=https://mdm.stoverparc.org/' + 'a' * 48 + '/\n'
        for extra in ['LD_PRELOAD=/tmp/library\n', 'HOST=0.0.0.0\n', 'PORT=9999\n', 'PORT=8789\nPORT=8789\n', 'TURN_URL=turn:relay\n']:
            with self.subTest(extra=extra), self.assertRaises(ValueError):
                setup.environment(base + extra)
        with self.assertRaises(ValueError):
            setup.environment(base.replace('mdm.stoverparc.org', 'other.example'))
        with self.assertRaises(ValueError):
            setup.unit('-oProxyCommand=sh', Path('/tmp/key'))

    def test_unit_quotes_spaces_and_escapes_systemd_specifiers(self):
        text = setup.unit('sdolbec@100.127.99.74', Path('/home/user/with spaces%/key'))
        self.assertIn('with spaces%%/key', text)
        self.assertIn('"StrictHostKeyChecking=yes"', text)
        self.assertIn('"127.0.0.1:18789:127.0.0.1:8789"', text)
        self.assertIn('Wants=mseries-webrtc.service', text)
        self.assertNotIn('sudo', text)


if __name__ == '__main__':
    unittest.main()
