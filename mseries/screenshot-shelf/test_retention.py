#!/usr/bin/python3
"""Private-display tests; never use the owner's screenshots, portal or clipboard.

Run: bash mseries/screenshot-shelf/test-retention.sh
"""
import importlib.machinery
import importlib.util
import os
from pathlib import Path
import tempfile
import uuid
import unittest
from unittest.mock import patch, Mock

loader = importlib.machinery.SourceFileLoader('shelf_retention', str(Path(__file__).with_name('mseries-screenshot-shelf')))
spec = importlib.util.spec_from_loader(loader.name, loader)
shelf = importlib.util.module_from_spec(spec)
loader.exec_module(shelf)
shelf.Gtk.init()


class RetentionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.original = self.root / 'Screenshot fixture.png'
        pixels = shelf.GdkPixbuf.Pixbuf.new(shelf.GdkPixbuf.Colorspace.RGB, True, 8, 2, 2)
        pixels.fill(0x43acdeff)
        pixels.savev(str(self.original), 'png', [], [])
        self.stage = self.root / 'stage'
        self.stage.mkdir()
        self.patches = [patch.object(shelf, 'STAGE', str(self.stage)), patch.object(shelf, 'LOG', str(self.root / 'log')), patch.object(shelf, 'running_flatpak_apps', return_value=set())]
        for p in self.patches:
            p.start()
        self.app = shelf.ShelfApp()
        self.app.set_application_id("org.techmore.mseries.Test" + uuid.uuid4().hex)
        self.app.register(None)
        self.windows = []
        self.timer = patch.object(shelf.GLib, 'timeout_add_seconds', return_value=0)
        self.scheduled = self.timer.start()
        self.real_timeout = shelf.GLib.timeout_add
        self.short_timer = patch.object(shelf.GLib, 'timeout_add', return_value=0)
        self.short_timer.start()

    def tearDown(self):
        for w in self.windows:
            w.close()
        self.short_timer.stop()
        self.timer.stop()
        for p in reversed(self.patches):
            p.stop()
        self.tmp.cleanup()

    def show(self):
        self.app.show(str(self.original))
        self.windows.append(self.app.shelf)
        return self.app.shelf

    def capture(self, w, state):
        destination = os.environ.get('SHELF_TEST_CAPTURE_DIR')
        if not destination:
            return
        Path(destination).mkdir(parents=True, exist_ok=True)
        for dark in (False, True):
            shelf.Gtk.Settings.get_default().set_property('gtk-application-prefer-dark-theme', dark)
            loop = shelf.GLib.MainLoop()
            failures = []
            def render():
                try:
                    child = w.get_child()
                    width, height = child.get_width(), child.get_height()
                    self.assertLessEqual(width, 420)
                    snapshot = shelf.Gtk.Snapshot()
                    shelf.Gtk.WidgetPaintable.new(child).snapshot(snapshot, width, height)
                    texture = w.get_native().get_renderer().render_texture(snapshot.to_node(), shelf.Graphene.Rect().init(0, 0, width, height))
                    texture.save_to_png(str(Path(destination) / (state + ('-dark.png' if dark else '-light.png'))))
                except Exception as error:
                    failures.append(error)
                finally:
                    loop.quit()
                return False
            # Give the private frame clock time to lay out and paint each theme.
            self.real_timeout(200, render)
            loop.run()
            if failures:
                raise failures[0]

    def test_completed_drag_keeps_original_and_allows_retry(self):
        w = self.show()
        self.capture(w, "ready")
        w.on_prepare(None, 0, 0)
        for _ in range(2):
            w.on_drag_begin(Mock(), None)
            w.on_drag_end(None, None, True)
            self.assertFalse(w.finished)
            self.assertEqual(w.hint.get_label(), 'Saved · Check attachment')
        self.capture(w, "check-attachment")
        w.finish('expired')
        self.scheduled.assert_called_with(shelf.EXPORT_GRACE_SECONDS, w.cleanup)
        w.cleanup()
        self.assertTrue(self.original.exists())
        self.assertFalse(Path(w.staged).exists())

    def test_cancel_and_clipboard_copy_use_full_image_without_removing_original(self):
        w = self.show()
        w.on_drag_begin(Mock(), None)
        w.on_drag_cancel(None, None, Mock(value_nick='no-target'))
        self.assertEqual(w.copy_button.get_label(), 'Copied')
        self.assertEqual(w.clip_texture.get_width(), 2)
        w.on_drag_end(None, None, False)
        self.assertFalse(w.finished)
        self.assertEqual(w.hint.get_label(), 'Not accepted · Saved')
        w.cleanup()
        self.assertTrue(self.original.exists())

    def test_replacement_during_drag_waits_and_does_not_clear_new_card(self):
        old = self.show()
        old.on_prepare(None, 0, 0)
        old.on_drag_begin(Mock(), None)
        old_bytes = Path(old.staged).read_bytes()
        self.original.write_bytes(old_bytes + b"fixture-new-shot")
        new = self.show()
        self.assertEqual(Path(old.staged).read_bytes(), old_bytes)
        self.assertEqual(Path(new.staged).read_bytes(), self.original.read_bytes())
        self.assertFalse(old.finished)
        self.assertTrue(Path(old.staged).exists())
        self.assertNotEqual(old.staged, new.staged)
        old.on_drag_end(None, None, False)
        self.assertTrue(old.finished)
        self.assertIs(self.app.shelf, new)
        old.cleanup()
        self.assertTrue(Path(new.staged).exists())
        self.assertTrue(self.original.exists())

    def test_portal_export_survives_card_until_grace_cleanup(self):
        w = self.show()
        portal = Mock(path=w.staged, granted={'org.example.Fixture'})
        with patch.object(shelf, 'running_flatpak_apps', return_value={'org.example.Fixture'}), patch.object(shelf, 'PortalExport', return_value=portal):
            w.on_prepare(None, 0, 0)
        w.finish('dismissed')
        portal.remove.assert_not_called()
        self.scheduled.assert_called_with(shelf.EXPORT_GRACE_SECONDS, w.cleanup)
        w.cleanup()
        portal.remove.assert_called_once()
        self.assertTrue(self.original.exists())

    def test_portal_failure_offers_staged_copy_and_retains_original(self):
        w = self.show()
        with patch.object(shelf, 'running_flatpak_apps', return_value={'org.example.Fixture'}), patch.object(shelf, 'PortalExport', side_effect=OSError('fixture portal unavailable')):
            self.assertEqual(w.drop_path(), w.staged)
        w.cleanup()
        self.assertTrue(self.original.exists())

    def test_snapshot_input_is_not_a_staged_file(self):
        w = self.show()
        w.staged = str(self.original)
        w.cleanup()
        self.assertTrue(self.original.exists())
        alias = self.root / "original-alias.png"
        alias.symlink_to(self.original)
        w.staged = str(alias)
        w.cleanup()
        self.assertTrue(self.original.exists())
        self.assertTrue(alias.exists())

    def test_dismiss_and_expiry_keep_original(self):
        for reason in ('dismissed', 'expired', 'replaced'):
            w = self.show()
            w.finish(reason)
            self.scheduled.assert_called_with(1, w.cleanup)
            w.cleanup()
            self.assertTrue(self.original.exists())


if __name__ == '__main__':
    unittest.main()
