#!/usr/bin/env python3
"""Isolated checks for the Windows Work Mode helper: keyfile GSettings, fake IP service, no services."""

import http.server
import os
import runpy
import shutil
import subprocess
import tempfile
import threading
import unittest
from unittest.mock import MagicMock, patch
from pathlib import Path

HERE = Path(__file__).resolve().parent
HELPER = HERE / "mseries-work-mode"
SCHEMA = "io.elementary.mseries.work-mode"


class FakeIpService(http.server.BaseHTTPRequestHandler):
    address = "203.0.113.7"
    hits = 0

    def do_GET(self):
        type(self).hits += 1
        body = self.address.encode()
        self.send_response(200)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


class WorkModeTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = http.server.HTTPServer(("127.0.0.1", 0), FakeIpService)
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()

    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        schemas = self.root / "schemas"
        schemas.mkdir()
        shutil.copy(HERE / f"{SCHEMA}.gschema.xml", schemas)
        subprocess.run(["glib-compile-schemas", str(schemas)], check=True)
        self.wallpaper = self.root / "work.png"
        self.wallpaper.write_bytes(b"png")
        self.env = {
            **os.environ,
            "GSETTINGS_BACKEND": "keyfile",
            "GSETTINGS_SCHEMA_DIR": str(schemas),
            "XDG_CONFIG_HOME": str(self.root / "config"),
            "XDG_STATE_HOME": str(self.root / "state"),
            "XDG_DATA_HOME": str(self.root / "data"),
            "MSERIES_WORK_MODE_NO_SERVICES": "1",
        }
        self.gset(SCHEMA, "work-wallpaper", str(self.wallpaper))
        self.gset(SCHEMA, "public-ip-service", f"http://127.0.0.1:{self.server.server_port}/")
        self.gset("org.gnome.desktop.background", "picture-uri", "file:///original.png")
        self.gset("org.gnome.desktop.interface", "icon-theme", "elementary")
        FakeIpService.address = "203.0.113.7"
        FakeIpService.hits = 0

    def tearDown(self):
        shutil.rmtree(self.root)

    def gset(self, schema, key, value):
        if isinstance(value, bool):
            value = str(value).lower()
        subprocess.run(["gsettings", "set", schema, key, value], env=self.env, check=True)

    def gget(self, schema, key):
        return subprocess.run(["gsettings", "get", schema, key], env=self.env, check=True,
                              capture_output=True, text=True).stdout.strip()

    def helper(self, *args):
        return subprocess.run([str(HELPER), *args], env=self.env, check=False, capture_output=True, text=True)

    def wallpaper_applied(self):
        return self.wallpaper.as_uri() in self.gget("org.gnome.desktop.background", "picture-uri")

    def test_dock_modes_use_adopted_size_tokens_and_keep_legacy_fallbacks(self):
        helper = runpy.run_path(str(HELPER))
        activate = helper["activate_dock"]
        namespace = activate.__globals__
        tool = self.root / "size-tool"
        tool.write_text("#!/bin/sh\ncase \"$2\" in work-taskbar) echo 60;; work) echo 44;; *) exit 1;; esac\n")
        tool.chmod(0o755)
        for taskbar in (False, True):
            schema = MagicMock()
            schema.has_key.side_effect = lambda key: key in {"icon-size", "autohide-mode"} or (taskbar and key == "taskbar-mode")
            settings = MagicMock()
            settings.get_value.return_value.print_.return_value = "24"
            for adopted in (False, True):
                settings.reset_mock()
                with patch.dict(namespace, {
                    "dock_settings": lambda: (settings, schema),
                    "dock_running": lambda: True,
                    "which": lambda name: str(tool) if adopted else str(self.root / "missing-tool"),
                }):
                    activate({})
                expected = (60 if taskbar else 44) if adopted else (48 if taskbar else 40)
                settings.set_int.assert_called_once_with("icon-size", expected)
                if taskbar:
                    settings.set_boolean.assert_called_once_with("taskbar-mode", True)
                else:
                    settings.set_boolean.assert_not_called()

    def test_manual_on_and_restore(self):
        self.gset(SCHEMA, "enabled", True)
        self.helper("--tick")
        self.assertTrue(self.wallpaper_applied())
        self.assertIn("Active", self.helper("--status").stdout)
        self.gset(SCHEMA, "enabled", False)
        self.helper("--tick")
        self.assertEqual(self.gget("org.gnome.desktop.background", "picture-uri"), "'file:///original.png'")

    def install_icon_theme(self, name):
        theme = self.root / "data" / "icons" / name
        theme.mkdir(parents=True)
        (theme / "index.theme").write_text(f"[Icon Theme]\nName={name}\nInherits=hicolor\n", encoding="utf-8")

    def test_icon_theme_applied_and_restored(self):
        self.install_icon_theme("TestWin11")
        self.gset(SCHEMA, "icon-theme", "TestWin11")
        self.gset(SCHEMA, "enabled", True)
        self.helper("--tick")
        self.assertEqual(self.gget("org.gnome.desktop.interface", "icon-theme"), "'TestWin11'")
        self.helper("--tick")  # a second tick must keep the first snapshot
        self.gset(SCHEMA, "enabled", False)
        self.helper("--tick")
        self.assertEqual(self.gget("org.gnome.desktop.interface", "icon-theme"), "'elementary'")

        self.gset(SCHEMA, "enabled", True)
        self.helper("--tick")
        self.assertEqual(self.gget("org.gnome.desktop.interface", "icon-theme"), "'TestWin11'")
        self.helper("--restore")
        self.assertEqual(self.gget("org.gnome.desktop.interface", "icon-theme"), "'elementary'")

    def test_missing_icon_theme_changes_nothing(self):
        self.gset(SCHEMA, "icon-theme", "NotInstalledTheme")
        self.gset(SCHEMA, "enabled", True)
        self.helper("--tick")
        self.assertTrue(self.wallpaper_applied())
        self.assertEqual(self.gget("org.gnome.desktop.interface", "icon-theme"), "'elementary'")
        self.gset(SCHEMA, "enabled", False)
        self.helper("--tick")
        self.assertEqual(self.gget("org.gnome.desktop.interface", "icon-theme"), "'elementary'")

    def test_default_icon_theme_key_changes_nothing(self):
        self.gset("org.gnome.desktop.interface", "icon-theme", "Adwaita")
        self.gset(SCHEMA, "enabled", True)
        self.helper("--tick")
        self.gset(SCHEMA, "enabled", False)
        self.helper("--tick")
        self.assertEqual(self.gget("org.gnome.desktop.interface", "icon-theme"), "'Adwaita'")

    def test_window_buttons_windows_layout_applied_and_restored(self):
        wm = "org.gnome.desktop.wm.preferences"
        self.gset(wm, "button-layout", "close,minimize,maximize:")
        self.gset(SCHEMA, "enabled", True)
        self.helper("--tick")
        self.assertEqual(self.gget(wm, "button-layout"), "':minimize,maximize,close'")
        self.helper("--tick")  # a second tick must keep the first snapshot
        self.gset(SCHEMA, "enabled", False)
        self.helper("--tick")
        self.assertEqual(self.gget(wm, "button-layout"), "'close,minimize,maximize:'")

        self.gset(SCHEMA, "enabled", True)
        self.helper("--tick")
        self.helper("--restore")
        self.assertEqual(self.gget(wm, "button-layout"), "'close,minimize,maximize:'")

    def test_window_buttons_unchanged_keeps_user_layout(self):
        wm = "org.gnome.desktop.wm.preferences"
        self.gset(wm, "button-layout", "close,minimize,maximize:")
        self.gset(SCHEMA, "window-buttons", "unchanged")
        self.gset(SCHEMA, "enabled", True)
        self.helper("--tick")
        self.assertEqual(self.gget(wm, "button-layout"), "'close,minimize,maximize:'")

    def test_window_buttons_choice_switched_while_active_restores(self):
        wm = "org.gnome.desktop.wm.preferences"
        self.gset(wm, "button-layout", "close,minimize,maximize:")
        self.gset(SCHEMA, "enabled", True)
        self.helper("--tick")
        self.gset(SCHEMA, "window-buttons", "unchanged")
        self.helper("--tick")
        self.assertEqual(self.gget(wm, "button-layout"), "'close,minimize,maximize:'")

    def test_network_rule_matches_cidr(self):
        self.gset(SCHEMA, "enabled", True)
        self.gset(SCHEMA, "network-trigger", True)
        self.helper("--tick")
        self.assertFalse(self.wallpaper_applied())
        self.assertIn("add a work public IP", self.helper("--status").stdout)

        self.gset(SCHEMA, "work-public-ips", "['198.51.100.0/24', 'not-an-ip']")
        self.helper("--tick")
        self.assertFalse(self.wallpaper_applied())
        self.assertIn("not on a work network (public IP 203.0.113.7)", self.helper("--status").stdout)

        self.gset(SCHEMA, "work-public-ips", "['198.51.100.0/24', '203.0.113.0/28']")
        self.helper("--tick")
        self.assertTrue(self.wallpaper_applied())

    def test_public_ip_is_cached_and_status_never_queries(self):
        self.gset(SCHEMA, "enabled", True)
        self.gset(SCHEMA, "network-trigger", True)
        self.gset(SCHEMA, "work-public-ips", "['203.0.113.7']")
        self.helper("--status")
        self.assertEqual(FakeIpService.hits, 0)
        self.helper("--tick")
        self.helper("--tick")
        self.assertEqual(FakeIpService.hits, 1)
        self.assertEqual(self.helper("--public-ip").stdout.strip(), "203.0.113.7")
        self.assertEqual(FakeIpService.hits, 2)

    def test_leaving_work_network_restores(self):
        self.gset(SCHEMA, "enabled", True)
        self.gset(SCHEMA, "network-trigger", True)
        self.gset(SCHEMA, "work-public-ips", "['203.0.113.7']")
        self.helper("--tick")
        self.assertTrue(self.wallpaper_applied())
        FakeIpService.address = "192.0.2.50"
        self.helper("--public-ip")
        self.helper("--tick")
        self.assertEqual(self.gget("org.gnome.desktop.background", "picture-uri"), "'file:///original.png'")

    def test_network_rule_skips_lookup_outside_hours(self):
        self.gset(SCHEMA, "enabled", True)
        self.gset(SCHEMA, "network-trigger", True)
        self.gset(SCHEMA, "work-public-ips", "['203.0.113.7']")
        self.gset(SCHEMA, "scheduled", True)
        self.gset(SCHEMA, "weekdays-only", False)
        self.gset(SCHEMA, "start-time", "00:00")
        self.gset(SCHEMA, "end-time", "00:00")
        self.helper("--tick")
        self.assertFalse(self.wallpaper_applied())
        self.assertEqual(FakeIpService.hits, 0)

    def test_mode_choice_never_reads_display_or_dock_hardware(self):
        """Owner rule: work/home comes only from the switch, the schedule and the public IP."""
        source = HELPER.read_text()
        for needle in ("/sys/class/drm", "boltctl", "thunderbolt", "DisplayConfig", "xrandr", "wlr-randr"):
            self.assertNotIn(needle, source, f"{needle} must not influence Work Mode")


if __name__ == "__main__":
    unittest.main()
