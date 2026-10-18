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

    def test_settings_bulk_update_removes_absent_keys_without_unset(self):
        self.win.open_instance('dev-0000')
        self.win.fill_settings('dev-0000', 'config:\n  limits.cpu: 1\n')
        self.win.set_cpu.set_text('2')
        with patch.object(self.win, 'bgl') as write, patch('orchard_incus.window.backend.incus') as cli:
            self.win.apply_settings()
            self.assertFalse(self.win.settings_apply.get_sensitive())
            self.win.apply_settings()
            self.assertEqual(write.call_count, 1, 'double activation must not submit another write')
            write.call_args.args[0]()
            cli.assert_called_once_with('config', 'set', 'dev-0000',
                                        'limits.cpu=2', 'limits.memory=', 'boot.autostart=')
            write.call_args.kwargs['fail']()
            self.assertTrue(self.win.settings_apply.get_sensitive())

    def test_settings_completion_does_not_reload_another_instances_edits(self):
        self.win.open_instance('dev-0000')
        self.win.fill_settings('dev-0000', 'config:\n')
        with patch.object(self.win, 'bgl') as write:
            self.win.apply_settings()
            done = write.call_args.kwargs['done']
        self.win.open_instance('dev-0001')
        self.win.fill_settings('dev-0001', 'config:\n  limits.cpu: 4\n')
        self.win.set_cpu.set_text('8')
        with patch.object(self.win, 'load_tab') as reload_tab:
            done(None)
            reload_tab.assert_not_called()
        self.assertEqual(self.win.set_cpu.get_text(), '8')

    def test_relative_host_share_path_is_rejected_without_clearing_inputs(self):
        self.win.open_instance('dev-0000')
        self.win.sh_host.set_text('relative-folder')
        self.win.sh_path.set_text('/mnt/data')
        with patch.object(self.win, 'bgl') as write:
            self.win.add_share()
            write.assert_not_called()
        self.assertEqual(self.win.sh_host.get_text(), 'relative-folder')
        self.assertIn('absolute paths', self.win.toast.get_title())


    def test_open_instance_clears_filter_that_hides_dashboard_target(self):
        self.win.search.set_text('dev-0000')
        self.win.filter_instances()
        self.win.open_instance('dev-0001')
        self.assertEqual(self.win.cur, 'dev-0001')
        self.assertEqual(self.win.d_title.get_text(), 'dev-0001')
        self.assertEqual(self.win.search.get_text(), '')

    def test_explicit_open_repairs_detail_when_row_is_already_selected(self):
        self.win.open_instance('dev-0000')
        self.win.cur = None
        self.win.open_instance('dev-0000')
        self.assertEqual(self.win.cur, 'dev-0000')
        self.assertEqual(self.win.stack.get_visible_child_name(), 'detail')

    def test_rename_selection_waits_for_refreshed_inventory(self):
        self.win.open_instance('dev-0000')
        self.win.select_after_refresh = 'renamed-dev'
        renamed = fixture()
        renamed['name'] = 'renamed-dev'
        self.win.show([renamed, fixture(1)])
        self.assertIsNone(self.win.select_after_refresh)
        self.assertEqual(self.win.cur, 'renamed-dev')
        self.assertEqual(self.win.list.get_selected_row().name, 'renamed-dev')

    def test_device_edits_serialize_and_duplicate_clicks_are_ignored(self):
        self.win.open_instance('dev-0000')
        with patch.object(self.win, 'bgl') as work, patch('orchard_incus.window.backend.incus') as cli:
            self.win.remove_device('dev-0000', 'port-a')
            self.win.remove_device('dev-0000', 'share-b')
            self.win.remove_device('dev-0000', 'share-b')
            self.assertEqual(work.call_count, 1)
            self.assertEqual(len(self.win.instance_writes['dev-0000']), 2)
            first = work.call_args
            first.args[0]()
            first.kwargs['done'](None)
            self.assertEqual(work.call_count, 2)
            second = work.call_args
            second.args[0]()
            second.kwargs['done'](None)
            self.assertFalse(self.win.instance_writes)
            self.assertEqual(cli.call_args_list[0].args, ('config', 'device', 'remove', 'dev-0000', 'port-a'))
            self.assertEqual(cli.call_args_list[1].args, ('config', 'device', 'remove', 'dev-0000', 'share-b'))

    def test_failed_metadata_edit_releases_next_edit(self):
        with patch.object(self.win, 'bgl') as work:
            self.win.edit_instance('dev-0000', lambda: None)
            self.win.edit_instance('dev-0000', lambda: None)
            work.call_args.kwargs['fail']()
            self.assertEqual(work.call_count, 2)
            work.call_args.kwargs['done'](None)
            self.assertNotIn('dev-0000', self.win.instance_writes)

    def test_vm_console_and_agent_hint_are_contextual(self):
        self.win.open_instance('dev-0000')
        self.assertFalse(self.win.console_button.get_visible())
        vm = fixture()
        vm['type'] = 'virtual-machine'
        self.win.show([vm])
        self.assertTrue(self.win.console_button.get_visible())
        self.assertTrue(self.win.vm_agent_hint.get_visible())
        with patch('orchard_incus.window.subprocess.Popen') as terminal:
            self.win.console()
            terminal.assert_called_once_with(['io.elementary.terminal', '-e',
                                             'incus console dev-0000 --type=console'])

    def test_device_inventory_rows_remain_visible_at_narrow_size(self):
        self.win.set_default_size(780, 480)
        self.win.open_instance('dev-0000')
        self.win.tabs.set_visible_child_name('de')
        self.win.fill_devices('dev-0000', {'devices': {}, 'expanded_devices': {
            'eth0': {'type': 'nic', 'network': 'incusbr0'},
            'root': {'type': 'disk', 'pool': 'default', 'path': '/'}}})
        self.win.present()
        until = time.monotonic() + .4
        context = GLib.MainContext.default()
        while time.monotonic() < until:
            while context.pending():
                context.iteration(False)
            time.sleep(.002)
        row = self.win.dev_list.get_first_child()
        valid, bounds = row.compute_bounds(self.win)
        self.assertTrue(valid)
        top, bottom = bounds.get_y(), bounds.get_y() + bounds.get_height()
        ancestor = row.get_parent()
        while ancestor is not None:
            if isinstance(ancestor, (Gtk.Viewport, Gtk.ScrolledWindow)):
                valid, clip = ancestor.compute_bounds(self.win)
                if valid:
                    top = max(top, clip.get_y())
                    bottom = min(bottom, clip.get_y() + clip.get_height())
            ancestor = ancestor.get_parent()
        self.assertGreaterEqual(bottom - top, 40, 'the first device card must be readable, not clipped into a tiny viewport')

    def test_creation_rejects_an_existing_inventory_name_before_launch(self):
        with patch('orchard_incus.window.subprocess.Popen') as launch, patch.object(self.win, 'cleanup_instance') as cleanup:
            self.win.start_create('dev-0000', 'cached-image', [])
            launch.assert_not_called()
            cleanup.assert_not_called()
        self.assertFalse(self.win.jobs)
        self.assertIn('already exists', self.win.toast.get_title())

    def test_new_instance_form_disables_duplicate_name(self):
        self.win.on_new()
        dialog = next(w for w in Gtk.Window.get_toplevels() if w and w.get_title() == 'New Instance')
        def walk(widget):
            yield widget
            child = widget.get_first_child()
            while child:
                yield from walk(child)
                child = child.get_next_sibling()
        grid = next(widget for widget in walk(dialog) if isinstance(widget, Gtk.Grid))
        grid.get_child_at(1, 0).set_text('dev-0000')
        self.assertFalse(dialog.get_widget_for_response(Gtk.ResponseType.ACCEPT).get_sensitive())
        dialog.destroy()
