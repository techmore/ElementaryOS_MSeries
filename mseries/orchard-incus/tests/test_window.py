"""GTK integration with synthetic inventories; never runs Incus."""
import os
from pathlib import Path
import sys
import tempfile
import subprocess
import time
import unittest
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
try:
    import gi
    gi.require_version('Gtk', '4.0')
    from gi.repository import Gtk, GLib, Gdk
    HAVE = Gtk.init_check()
except Exception:
    HAVE = False


def fixture(n=0):
    return {'name': f'dev-{n:04}', 'status': 'Running', 'type': 'container',
            'config': {'image.description': 'Debian development', 'image.os': 'Debian'},
            'state': {'memory': {'usage': 1048576}, 'cpu': {'usage': 1000}, 'processes': 3,
                      'network': {'eth0': {'addresses': [{'family': 'inet', 'scope': 'global', 'address': f'10.0.0.{n % 250 + 1}'}]}}}}


@unittest.skipUnless(HAVE, 'needs a display (use xvfb-run)')
class WindowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from orchard_incus.window import Window
        cls.Window = Window
        cls.app = Gtk.Application(application_id='io.github.techmore.OrchardFixture')
        cls.app.register(None)

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.patches = [patch('orchard_incus.window.STATE_FILE', self.temp.name + '/state.json'),
                        patch.object(self.Window, 'check_incus'), patch.object(self.Window, 'bg'),
                        patch.object(self.Window, 'read')]
        for p in self.patches:
            p.start()
        self.win = self.Window(self.app)
        self.win.show([fixture(), fixture(1)])
        context = GLib.MainContext.default()
        while context.pending():
            context.iteration(False)

    def tearDown(self):
        self.win.close()
        for p in reversed(self.patches):
            p.stop()
        self.temp.cleanup()

    def test_search_ip_image_no_match_and_clear(self):
        self.win.search.set_text('10.0.0.2')
        self.win.filter_instances()
        self.assertEqual(self.win.cur, 'dev-0001')
        self.win.search.set_text('no-such-instance')
        self.win.filter_instances()
        self.assertTrue(self.win.no_matches.get_visible())
        self.assertIsNone(self.win.cur)
        self.win.search.set_text('deBIAN')
        self.win.filter_instances()
        self.assertFalse(self.win.no_matches.get_visible())
        self.assertIsNotNone(self.win.cur)

    def test_output_tail_is_bounded(self):
        self.win.append_out('dev-0000', 'λ' * 400000)
        b = self.win.exec_buf('dev-0000')
        self.assertEqual(b.get_char_count(), 262144)

    def test_busy_other_instance_does_not_change_detail(self):
        self.win.open_instance('dev-0000')
        self.win.run_op('dev-0001', 'Starting…', lambda: None)
        self.assertEqual(self.win.d_title.get_text(), 'dev-0000')
        self.assertEqual(self.win.cur, 'dev-0000')

    def test_settings_cannot_apply_until_current_instance_loaded(self):
        self.win.open_instance('dev-0000')
        self.win.fill_settings('dev-0000', 'config:\n  limits.cpu: 2\n')
        self.assertTrue(self.win.settings_apply.get_sensitive())
        self.win.open_instance('dev-0001')
        self.assertFalse(self.win.settings_apply.get_sensitive())
        with patch.object(self.win, 'bgl') as write:
            self.win.apply_settings()
            write.assert_not_called()

    def test_refresh_coalesces_and_replays_after_slow_response(self):
        self.win.refresh()
        self.win.refresh()
        self.win.refresh()
        self.assertEqual(self.win.bg.call_count, 1)
        self.assertTrue(self.win._refresh_again)
        done = self.win.bg.call_args.args[1]
        done([fixture()])
        self.assertFalse(self.win._listing)
        self.assertTrue(self.win._rf_pending)

    def test_dashboard_is_keyboard_activatable(self):
        row = self.win.dash_rows['dev-0001']
        self.assertIsInstance(row, Gtk.Button)
        row.emit('clicked')
        self.assertEqual(self.win.cur, 'dev-0001')

    def test_window_close_removes_all_timers_and_ignores_late_results(self):
        sources = list(self.win.sources)
        self.assertGreaterEqual(len(sources), 2)
        self.win.on_close()
        self.assertTrue(self.win.closing)
        self.assertFalse(self.win.sources)
        context = GLib.MainContext.default()
        for source in sources:
            self.assertIsNone(context.find_source_by_id(source))
        with patch.object(self.win, 'error_dialog') as error:
            self.win.finish(None, RuntimeError('late error'), None, None, 'late')
            error.assert_not_called()

    def test_event_burst_does_not_stack_address_timers(self):
        before = len(self.win.sources)
        event = '{"metadata":{"action":"instance-started","source":"/1.0/instances/dev-0000"}}'
        for _ in range(1000):
            self.win.on_event(event)
        self.assertLessEqual(len(self.win.sources) - before, 3)

    def test_noisy_command_completes_with_utf8_and_bounded_gtk_buffer(self):
        self.win.open_instance('dev-0000')
        self.win.cmd.set_text('synthetic output test')
        popen = subprocess.Popen
        with patch('orchard_incus.window.subprocess.Popen', side_effect=lambda *a, **kw:
                   popen([sys.executable, '-c', "import sys; sys.stdout.buffer.write(('λ' * 1000000 + '\\nFINAL✓\\n').encode())"], **kw)):
            self.win.run_cmd()
        deadline = time.monotonic() + 5
        context = GLib.MainContext.default()
        while self.win.exec_proc and time.monotonic() < deadline:
            while context.pending():
                context.iteration(False)
            time.sleep(.002)
        self.assertFalse(self.win.exec_proc)
        buf = self.win.exec_buf('dev-0000')
        self.assertLessEqual(buf.get_char_count(), 262144)
        text = buf.get_text(buf.get_start_iter(), buf.get_end_iter(), False)
        self.assertIn('FINAL✓', text)
        self.assertNotIn('�', text)
        self.assertTrue(text.endswith('[exit 0]\n\n'))

    def test_loading_new_snapshot_inventory_removes_old_actions(self):
        self.win.open_instance('dev-0000')
        self.win.tabs.set_visible_child_name('sn')
        self.win.fill_snaps('dev-0000', [{'name': 'old-snapshot'}])
        self.win.open_instance('dev-0001')
        row = self.win.snap_list.get_first_child()
        self.assertIsInstance(row.get_child(), Gtk.Label)
        self.assertEqual(row.get_child().get_text(), 'Loading snapshots…')
