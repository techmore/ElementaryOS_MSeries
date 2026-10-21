#!/usr/bin/python3
"""Fake displays and private GTK only. Run through test-canvas.sh."""
import importlib.machinery
import importlib.util
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

loader = importlib.machinery.SourceFileLoader('display_ui', str(Path(__file__).with_name('mseries-display-settings')))
spec = importlib.util.spec_from_loader(loader.name, loader)
ui = importlib.util.module_from_spec(spec)
loader.exec_module(ui)

class CanvasTests(unittest.TestCase):
    def setUp(self):
        self.app = ui.App()
        self.addCleanup(self.app.destroy)
        self.canvas = self.app.canvas
        self.app.be.apply = Mock(side_effect=AssertionError('No display writes in a UI test'))

    def test_long_labels_are_ellipsized_not_cropped(self):
        text = 'Built-in display (primary) — ' + '長い名前' * 20
        layout = self.canvas.label_layout(text, 100)
        self.assertLessEqual(layout.get_pixel_size()[0], 100)
        self.assertTrue(layout.is_ellipsized())
        self.assertEqual(layout.get_text(), text)

    def test_labels_follow_the_widget_font(self):
        context = self.canvas.get_pango_context()
        context.set_font_description(ui.Pango.FontDescription.from_string('Sans 11'))
        small = self.canvas.label_layout('Display', 1000).get_pixel_size()[1]
        context.set_font_description(ui.Pango.FontDescription.from_string('Sans 22'))
        large = self.canvas.label_layout('Display', 1000).get_pixel_size()[1]
        self.assertGreater(large, small * 1.5)

    def test_keyboard_selection_changes_controls_without_display_write(self):
        first = self.app.sel
        self.assertTrue(self.canvas.on_key(None, SimpleNamespace(keyval=ui.Gdk.KEY_Right)))
        self.assertIsNot(self.app.sel, first)
        self.assertTrue(self.canvas.on_key(None, SimpleNamespace(keyval=ui.Gdk.KEY_Left)))
        self.assertIs(self.app.sel, first)
        self.assertFalse(self.canvas.on_key(None, SimpleNamespace(keyval=ui.Gdk.KEY_a)))
        self.app.be.apply.assert_not_called()

    def test_full_label_remains_available_to_tooltip_and_accessibility(self):
        self.app.sel.label = 'Fixture monitor with a long name ' + '長い名前' * 10
        self.canvas.update_accessible()
        tooltip = Mock()
        self.assertTrue(self.canvas.on_tooltip(None, 0, 0, True, tooltip))
        self.assertIn(self.app.sel.label, tooltip.set_text.call_args.args[0])
        self.assertIn(self.app.sel.label, self.canvas.get_accessible().get_description())
        self.assertIn('Left and Right', self.canvas.get_accessible().get_description())

if __name__ == '__main__':
    unittest.main()
