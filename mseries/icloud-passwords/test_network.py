"""Run with the installed client venv; all Apple calls are mocked."""
import importlib.util
import plistlib
import unittest
from unittest.mock import patch

CLIENT_AVAILABLE = all(importlib.util.find_spec(name) is not None for name in ('icp', 'srp', 'nacl', 'secretstorage'))

class Device:
    def meta_headers(self):
        return {'X-Mme-Device-Id':'TEST-DEVICE'}

class Anisette:
    def headers(self):
        return {'X-Apple-I-MD':'TEST-MACHINE-DATA'}

class Response:
    status_code = 200
    ok = True
    headers = {'Content-Type':'text/x-xml-plist'}
    def __init__(self, data):
        self.content = plistlib.dumps(data)

@unittest.skipUnless(CLIENT_AVAILABLE, 'Use the installed client venv')
class NetworkTests(unittest.TestCase):
    def test_grandslam_identity_and_verified_tls(self):
        from icp.auth.gsa import GSAClient
        with patch('icp.auth.gsa.requests.post', return_value=Response({'Response':{'Status':{'ec':0}}})) as post:
            GSAClient(Device(), Anisette())._request({'o':'init'})
        kwargs=post.call_args.kwargs
        self.assertIs(kwargs['verify'],True)
        self.assertTrue(kwargs['headers']['X-MMe-Client-Info'].startswith('<PC> <Windows;'))

    def test_delegates_windows_settings_mac(self):
        from icp.auth import icloud
        response=Response({'dsid':'TEST', 'delegates':{'com.apple.mobileme':{
            'status':0, 'service-data':{'tokens':{'mmeAuthToken':'TEST-TOKEN'}}}}})
        with patch('icp.auth.icloud.requests.post',return_value=response) as post:
            icloud.login_mobileme('test@example.invalid','TEST-PET','TEST','TEST',Device(),Anisette())
            self.assertTrue(post.call_args.kwargs['headers']['X-Mme-Client-Info'].startswith('<PC>'))
            self.assertIs(post.call_args.kwargs['verify'],True)
            icloud.fetch_account_settings({'mme':{'dsid':'TEST','mmeAuthToken':'TEST-TOKEN'}},Device(),Anisette())
            self.assertTrue(post.call_args.kwargs['headers']['X-Mme-Client-Info'].startswith('<MacBookPro'))
            self.assertIs(post.call_args.kwargs['verify'],True)

    def test_escrow_identity_and_consent_gate(self):
        from icp.escrow.srp import EscrowRecovery, EscrowGateError
        rec=EscrowRecovery('https://example.invalid','TEST','TEST',Anisette())
        self.assertTrue(rec._headers()['X-Mme-Client-Info'].startswith('<PC> <Windows;'))
        # Header compatibility does not remove the original irreversible-consent gate.
        with patch.object(rec, '_invoke') as invoke:
            with self.assertRaises(EscrowGateError):
                rec.try_recover_escrow('TEST-LABEL', b'TEST-PASSCODE')
            invoke.assert_not_called()

    def test_web_session_verifies_tls(self):
        from icp.auth.webauth import WebAuthSession
        self.assertIs(WebAuthSession('TEST-FRAME').http.verify,True)

if __name__=='__main__':
    unittest.main()
