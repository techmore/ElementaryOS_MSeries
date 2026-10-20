"""Run with xvfb-run -a /usr/bin/python3 -m unittest discover ..."""
import importlib.util
import io
import json
from pathlib import Path
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parent

def load(name, filename):
    spec = importlib.util.spec_from_file_location(name, HERE / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

worker = load('worker', 'worker.py')

class WorkerTests(unittest.TestCase):
    def test_private_prompt_protocol(self):
        out = io.StringIO()
        with patch('sys.stdout', out), patch('sys.stdin', io.StringIO('{"value":"TEST_SECRET"}\n')):
            self.assertEqual(worker.prompt('password', 'Password'), 'TEST_SECRET')
        self.assertNotIn('TEST_SECRET', out.getvalue())
        self.assertEqual(json.loads(out.getvalue())['kind'], 'password')

    def test_cancel_and_error_redaction(self):
        with patch('sys.stdout', io.StringIO()), patch('sys.stdin', io.StringIO('{"cancel":true}\n')):
            with self.assertRaises(KeyboardInterrupt):
                worker.prompt('passcode', 'Passcode')
        for text in ('token=TEST_SECRET ec=-80045', 'join failed: TEST_SECRET',
                     'SSLError TEST_SECRET', 'TEST_SECRET'):
            self.assertNotIn('TEST_SECRET', worker.friendly_error(text))

class GuiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import os
        if not os.environ.get('DISPLAY'):
            raise unittest.SkipTest('Run native GUI tests under xvfb-run')
        cls.gui = load('passwords_gui', 'app.py')

    def setUp(self):
        self.app = self.gui.Passwords()
        self.app.start = lambda action: None
        self.app.set_application_id("org.techmore.mseries.Test" + self._testMethodName.replace("_", ""))
        self.app.register()
        self.app.activate()

    def tearDown(self):
        if self.app.dialog:
            self.app.dialog.destroy()
        self.app.window.destroy()
        self.app.quit()

    def test_signin_remains_reachable_in_short_window(self):
        import time
        settings = self.gui.Gtk.Settings.get_default()
        original_font = settings.props.gtk_font_name
        self.addCleanup(settings.set_property, 'gtk-font-name', original_font)
        settings.props.gtk_font_name = 'Sans 14'
        self.app.window.set_default_size(540, 420)
        context = self.gui.GLib.MainContext.default()
        deadline = time.monotonic() + 0.5
        while time.monotonic() < deadline:
            while context.pending():
                context.iteration(False)
            time.sleep(0.01)
        self.assertLessEqual(self.app.window.get_height(), 440)
        scroll = self.app.stack.get_child_by_name('login')
        adjustment = scroll.get_vadjustment()
        self.assertGreater(adjustment.get_upper(), adjustment.get_page_size())
        adjustment.set_value(adjustment.get_upper() - adjustment.get_page_size())
        self.assertGreater(adjustment.get_value(), 0)
        self.assertTrue(self.app.signin.grab_focus())
        self.assertTrue(self.app.signin.get_sensitive())

    def test_empty_and_synced_vault(self):
        self.app.event(None, {'type':'vault', 'credentials':[], 'signed_in':False, 'joined':False})
        self.assertEqual(self.app.stack.get_visible_child_name(), 'login')
        self.app.event(None, {'type':'vault', 'credentials':[
            {'domain':'example.invalid','title':'Example','username':'test-user','password':'DEMO_PASSWORD'}],
            'signed_in':True,'joined':True,'updated':1})
        self.assertEqual(self.app.stack.get_visible_child_name(), 'vault')
        row=self.app.list.get_row_at_index(0)
        self.app.select(self.app.list,row)
        self.assertEqual(self.app.saved_password.get_text(),'DEMO_PASSWORD')
        self.app.search.set_text('no-match')
        self.app.populate()
        self.assertIsNone(self.app.list.get_row_at_index(0))
        self.assertEqual(self.app.saved_password.get_text(),'')

    def test_code_waits_validates_and_normalizes(self):
        self.app.show_prompt({'kind':'code','label':'Verify your device'})
        button=self.app.dialog.get_widget_for_response(self.gui.Gtk.ResponseType.OK)
        self.assertFalse(button.get_sensitive())
        self.assertIn('Waiting for you',self.app.status.get_text())
        self.assertFalse(self.app.spinner.get_spinning())
        self.app.prompt_input.set_text('12345')
        self.assertFalse(button.get_sensitive())
        self.app.prompt_input.set_text('１２３４５６')
        self.assertFalse(button.get_sensitive())
        self.app.prompt_input.set_text('123 456')
        self.assertTrue(button.get_sensitive())
        sent=[]
        self.app.reply=lambda value=None,**kwargs:sent.append(value)
        self.app.dialog.response(self.gui.Gtk.ResponseType.OK)
        self.assertEqual(sent,['123456'])
        self.assertIsNone(self.app.dialog)

    def test_empty_search_has_recovery_hint(self):
        self.app.search.set_text('missing')
        self.app.populate()
        self.assertEqual(self.app.results.get_visible_child_name(),'empty')
        self.assertIn('Try another',self.app.empty_results.get_text())

    def test_recovery_requires_explicit_consent(self):
        self.app.show_prompt({'kind':'confirm','label':'Allow one recovery attempt?'})
        button=self.app.dialog.get_widget_for_response(self.gui.Gtk.ResponseType.OK)
        self.assertFalse(button.get_sensitive())
        self.app.dialog.response(self.gui.Gtk.ResponseType.CANCEL)
        self.assertIsNone(self.app.dialog)

    def test_login_clears_widget_and_cancel_clears_pending_secrets(self):
        self.app.email.set_text('test@example.invalid')
        self.app.password.set_text('DEMO_PASSWORD')
        self.app.login()
        self.assertEqual(self.app.password.get_text(),'')
        self.assertEqual(self.app.credentials['password'],'DEMO_PASSWORD')
        self.app.close()
        self.assertFalse(self.app.credentials)

    def test_recovery_blocks_close_and_cancellation(self):
        self.app.event(None,{'type':'recovery','active':True})
        self.assertFalse(self.app.cancel.get_sensitive())
        self.assertTrue(self.app.close())
        self.app.recovering=False

if __name__=='__main__':
    unittest.main()
