"""GTK checks; run on a private display with temporary XDG config/data directories."""
import importlib.util
import os
from pathlib import Path
import unittest
from unittest.mock import patch


@unittest.skipUnless(os.environ.get("DISPLAY"), "Run GTK checks under xvfb-run")
class ColorSchemeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        spec = importlib.util.spec_from_file_location(
            "battery_ui", Path(__file__).with_name("mseries-battery-app.py"))
        cls.ui = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.ui)
        cls.app = cls.ui.BatteryApp()
        cls.app.set_application_id("org.mseries.Battery.ThemeTest")
        with patch.object(cls.ui.Granite.Settings, "get_prefers_color_scheme",
                          return_value=cls.ui.Granite.SettingsColorScheme.DARK):
            cls.app.register()
        cls.initial_dark = cls.ui.Gtk.Settings.get_default().props.gtk_application_prefer_dark_theme

    @classmethod
    def tearDownClass(cls):
        cls.app.quit()

    def test_desktop_preference_at_startup_and_live_changes(self):
        self.assertTrue(self.initial_dark)
        for preference, expected in ((self.ui.Granite.SettingsColorScheme.NO_PREFERENCE, False),
                                     (self.ui.Granite.SettingsColorScheme.DARK, True)):
            with patch.object(self.ui.Granite.Settings, "get_prefers_color_scheme", return_value=preference):
                self.app.desktop_settings.notify("prefers-color-scheme")
                self.assertEqual(self.ui.Gtk.Settings.get_default().props.gtk_application_prefer_dark_theme,
                                 expected)


if __name__ == "__main__":
    unittest.main()
