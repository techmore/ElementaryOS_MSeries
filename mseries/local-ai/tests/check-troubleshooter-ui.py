#!/usr/bin/python3
"""Private GTK verification regression. Only a temporary synthetic helper is run."""
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import subprocess
import time
import unittest
import uuid
from gi.repository import GLib

source = Path(__file__).resolve().parents[1] / 'troubleshooter-ui.py'
spec = importlib.util.spec_from_file_location('troubleshooter_ui', source)
ui = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ui)


class VerificationUI(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.previous_home = os.environ.get('HOME')
        os.environ['HOME'] = self.directory.name
        self.home = Path(self.directory.name)
        helper = self.home / '.local/bin/mseries-verify'
        helper.parent.mkdir(parents=True)
        helper.write_text('''#!/usr/bin/python3
import json,pathlib,sys,time,os
home=pathlib.Path.home()
with (home/'calls').open('a') as log: log.write(' '.join(sys.argv[1:])+'\\n')
(home/'pid').write_text(str(os.getpid()))
time.sleep(float((home/'delay').read_text()))
mode=(home/'mode').read_text()
if mode=='fail': raise SystemExit(1)
if mode=='invalid': print('{"items": [null]}'); raise SystemExit(0)
if sys.argv[1]=='status': print(json.dumps({'items':[{'id':'fixture','title':'Synthetic visual confirmation','state':'ask','detail':'Fixture only'}]}))
''')
        helper.chmod(0o700)
        (self.home / 'delay').write_text('0.25')
        (self.home / 'mode').write_text('ok')
        self.app = ui.Troubleshooter()
        self.app.set_application_id('org.techmore.Test' + uuid.uuid4().hex)
        self.app.register(None)
        self.app.activate()

    def pump(self, predicate, timeout=4):
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            while GLib.MainContext.default().pending():
                GLib.MainContext.default().iteration(False)
            if predicate():
                return
            time.sleep(0.005)
        self.fail('Private GTK condition timed out')

    def wait_done(self):
        self.pump(lambda: not self.app._verification_busy)

    def tearDown(self):
        for window in self.app.get_windows():
            window.close()
        self.app.quit()
        # Allow cancellation workers to reap before deleting their private files.
        time.sleep(0.15)
        while GLib.MainContext.default().pending():
            GLib.MainContext.default().iteration(False)
        if self.previous_home is None:
            os.environ.pop('HOME', None)
        else:
            os.environ['HOME'] = self.previous_home
        self.directory.cleanup()

    def capture(self, state):
        output = os.environ.get('MSERIES_UI_CAPTURE')
        if not output:
            return
        from gi.repository import GdkX11
        deadline = time.monotonic() + .1
        while time.monotonic() < deadline:
            while GLib.MainContext.default().pending():
                GLib.MainContext.default().iteration(False)
            time.sleep(.005)
        window = self.app.get_active_window()
        self.assertEqual(window.get_scale_factor(), int(os.environ.get('GDK_SCALE', '1')))
        Path(output).mkdir(parents=True, exist_ok=True)
        subprocess.run(['ffmpeg', '-loglevel', 'error', '-y', '-f', 'x11grab', '-draw_mouse', '0', '-window_id', str(window.get_surface().get_xid()), '-i', os.environ['DISPLAY'], '-frames:v', '1',
                        str(Path(output) / ('troubleshooter-' + state + '.png'))], check=True)

    def test_initial_window_and_heartbeat_during_all_commands(self):
        self.assertTrue(self.app.get_active_window().get_visible())
        self.assertTrue(self.app._verification_busy)
        ticks = []
        timer = GLib.timeout_add(20, lambda: ticks.append(time.monotonic()) or True)
        try:
            self.wait_done()
            self.assertGreaterEqual(len(ticks), 5)
            self.assertIn('1', self.app.verification_status.get_text())
            self.capture('ready')
            for action in (lambda: self.app.run_checks(None),
                           lambda: self.app.answer_check(None, 'fixture', 'yes')):
                before = len(ticks)
                action()
                generation = self.app._verification_generation
                self.app.run_checks(None)  # duplicate while pending is ignored
                self.assertEqual(generation, self.app._verification_generation)
                self.assertFalse(self.app.checklist.get_sensitive())
                self.wait_done()
                self.assertGreaterEqual(len(ticks) - before, 10)
                self.assertTrue(self.app.verify_button.get_sensitive())
            calls = (self.home / 'calls').read_text().splitlines()
            self.assertEqual(calls, ['status --json', 'run --quiet', 'status --json',
                                     'confirm fixture yes', 'status --json'])
        finally:
            GLib.source_remove(timer)

    def test_fail_malformed_and_recover_preserve_content(self):
        self.wait_done()
        original = self.app.checklist.get_first_child()
        for mode in ('fail', 'invalid'):
            (self.home / 'mode').write_text(mode)
            self.app.refresh_checklist()
            self.wait_done()
            self.assertIn('unavailable', self.app.verification_status.get_text())
            self.capture('error')
            self.assertIs(self.app.checklist.get_first_child(), original)
            self.assertTrue(self.app.checklist.get_sensitive())
        (self.home / 'mode').write_text('ok')
        self.app.refresh_checklist()
        self.wait_done()
        self.assertIn('1', self.app.verification_status.get_text())

    def test_close_cancels_and_reaps_without_stale_completion(self):
        self.wait_done()
        (self.home / 'delay').write_text('30')
        self.app.run_checks(None)
        self.pump(lambda: 'run --quiet' in (self.home / 'calls').read_text())
        pid = int((self.home / 'pid').read_text())
        self.app.get_active_window().close()
        generation = self.app._verification_generation
        def absent():
            try:
                os.kill(pid, 0)
                return False
            except ProcessLookupError:
                return True
        self.pump(absent)
        self.assertEqual(generation, self.app._verification_generation)
        self.app.verification_finished(generation - 1, [], None)
        self.assertEqual(generation, self.app._verification_generation)

    def test_timeout_recovery(self):
        self.wait_done()
        (self.home / 'delay').write_text('30')
        self.app.start_verification(['run', '--quiet'], .15, 'Fixture timeout')
        self.wait_done()
        self.assertIn('unavailable', self.app.verification_status.get_text())
        self.assertTrue(self.app.verify_button.get_sensitive())


if __name__ == '__main__':
    unittest.main()
