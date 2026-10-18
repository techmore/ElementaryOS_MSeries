"""Approval/code handoff: mocked Apple, no real account or recovery requests."""
import importlib.util
import io
from pathlib import Path
import unittest
from unittest.mock import patch, MagicMock

AVAILABLE = all(importlib.util.find_spec(name) is not None for name in ('icp','srp','secretstorage'))

@unittest.skipUnless(AVAILABLE, 'Use the client venv')
class ApprovalTests(unittest.TestCase):
    def run_flow(self, network_error=None):
        from icp.auth.gsa import GSAClient
        from icp.cli import app, ui
        import requests
        spec=importlib.util.spec_from_file_location('worker_2fa',Path(__file__).with_name('worker.py'))
        worker=importlib.util.module_from_spec(spec); spec.loader.exec_module(worker)
        events=[]
        class Device:
            def meta_headers(self): return {}
        class Anisette:
            def headers(self): return {}
        def send(*args, **kwargs):
            # The code box must be offered BEFORE Apple's request returns.
            self.assertEqual(events[0]['type'],'prompt')
            self.assertEqual(events[0]['kind'],'code')
            self.assertTrue(kwargs['verify'])
            if network_error:
                raise network_error
            response=MagicMock(); response.ok=True
            return response
        def login(argv):
            GSAClient(Device(),Anisette()).trigger_trusted_factor('TEST-ID','TEST-TOKEN')
            self.assertEqual(ui.ask('6-digit code: '),'123456')
            return 1  # avoid loading any real snapshot
        collection=MagicMock(); collection.is_locked.return_value=False
        original=GSAClient.trigger_trusted_factor
        try:
            with patch.object(worker,'emit',side_effect=lambda event_type,**fields:events.append(dict(type=event_type,**fields))), \
                 patch('sys.stdin',io.StringIO('{"value":"123456"}\n')), \
                 patch('sys.argv',['worker.py','login']), \
                 patch('icp.auth.gsa.requests.get',side_effect=send) as request, \
                 patch('secretstorage.dbus_init'), \
                 patch('secretstorage.get_default_collection',return_value=collection), \
                 patch.object(app,'main',side_effect=login), \
                 patch.multiple(ui,ask=ui.ask,secret=ui.secret,step=ui.step,out=ui.out,warn=ui.warn,err=ui.err,confirm_yn=ui.confirm_yn), \
                 patch.object(app,'_select_bottle',app._select_bottle):
                worker.main()
                self.assertEqual(request.call_count,1)
                self.assertEqual(sum(e['type']=='prompt' for e in events),1)
                if isinstance(network_error, requests.exceptions.SSLError):
                    self.assertTrue(any(e['type']=='error' and 'secure connection' in e['text'] for e in events))
        finally:
            GSAClient.trigger_trusted_factor=original

    def test_code_box_precedes_notification_response(self):
        self.run_flow()

    def test_notification_read_timeout_still_waits_for_code_once(self):
        import requests
        self.run_flow(requests.ReadTimeout('TEST-TIMEOUT'))

    def test_tls_error_is_fatal(self):
        import requests
        self.run_flow(requests.exceptions.SSLError('TEST-CERTIFICATE-FAILURE'))

if __name__=='__main__': unittest.main()
