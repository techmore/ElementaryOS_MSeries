#!/usr/bin/env python3
"""Tests for check-ui-sizes.sh / check_ui_sizes.py (no desktop session needed)."""

import contextlib
import io
import json
import subprocess
import tempfile
import unittest
from pathlib import Path

import check_ui_sizes as lint

HERE = Path(__file__).resolve().parent


class Fixture(unittest.TestCase):
    """A scratch repository with one scanned stylesheet and one patch."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.write("mseries/dock-taskbar/start-menu.css", "a { font-size: 1.1em; }\n")
        self.write("mseries/patches/dock-taskbar-x.patch", "--- a\n+++ b\n+.x { font-size: 18pt; }\n")
        self.allowlist = self.root / "allow.json"
        self.allow([("mseries/patches/dock-taskbar-x.patch", "font-abs", "font-size: 18pt", 1)])

    def write(self, relative, text):
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    def allow(self, entries):
        self.allowlist.write_text(json.dumps({"allowed": [
            {"file": f, "rule": r, "match": m, "count": n, "reason": "test"} for f, r, m, n in entries]}))

    def run_check(self, *args):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = lint.main(list(args), root=self.root, allowlist=self.allowlist)
        return code, out.getvalue(), err.getvalue()


class Scanner(Fixture):
    def test_allowlisted_hard_coded_size_passes(self):
        self.assertEqual(self.run_check("--strict")[0], 0)

    def test_relative_sizes_are_fine(self):
        self.assertEqual(lint.scan(self.root).get(("mseries/dock-taskbar/start-menu.css", "font-abs", "font-size: 1.1em")), None)

    def test_new_absolute_font_size_fails(self):
        self.write("mseries/dock-taskbar/start-menu.css", "a { font-size: 14px; }\n")
        code, _, err = self.run_check()
        self.assertEqual(code, 1)
        self.assertIn("font-size: 14px", err)

    def test_more_occurrences_than_allowed_fail(self):
        self.write("mseries/patches/dock-taskbar-x.patch", "+a { font-size: 18pt; }\n+b { font-size: 18pt; }\n")
        self.assertEqual(self.run_check()[0], 1)

    def test_removed_and_context_patch_lines_are_ignored(self):
        self.write("mseries/patches/dock-taskbar-x.patch", "-a { font-size: 30pt; }\n b { font-size: 31pt; }\n+c { font-size: 18pt; }\n")
        self.assertEqual(self.run_check()[0], 0)

    def test_dock_literals_icon_pixels_and_panel_scale_are_found(self):
        self.write("mseries/dock-policy/enable.sh", "gsettings set io.elementary.dock icon-size 52\nicon_size=48\n")
        self.write("mseries/display-space/dock_profile.py", "settings.set_int('icon-size', 40)\nDEFAULT_ICON_SIZE = 40\n")
        self.write("mseries/repobar-wingpanel/Indicator.vala", "new Gtk.Image () { pixel_size = 12 };\n")
        self.write("mseries/patches/wingpanel-content-scale.patch", "+    private const float CONTENT_SCALE = 1.30f;\n")
        found = {(f.rsplit("/", 1)[-1], rule, match) for (f, rule, match) in lint.scan(self.root)}
        for expected in (("enable.sh", "dock-size", "icon-size 52"), ("enable.sh", "dock-size", "icon_size=48"),
                         ("dock_profile.py", "dock-size", "set_int('icon-size', 40"),
                         ("dock_profile.py", "dock-size", "DEFAULT_ICON_SIZE = 40"),
                         ("Indicator.vala", "icon-px", "pixel_size = 12"),
                         ("wingpanel-content-scale.patch", "panel-scale", "CONTENT_SCALE = 1.30f")):
            self.assertIn(expected, found)

    def test_test_and_probe_files_are_not_scanned(self):
        self.write("mseries/codexbar-wingpanel/test-presentation.vala", "font-size: 99pt\n")
        self.write("mseries/repobar-wingpanel/probe/render-probe.vala", "font-size: 99pt\n")
        self.assertEqual(self.run_check()[0], 0)

    def test_unused_allowlist_room_is_a_note_unless_strict(self):
        self.allow([("mseries/patches/dock-taskbar-x.patch", "font-abs", "font-size: 18pt", 3)])
        self.assertEqual(self.run_check()[0], 0)
        self.assertEqual(self.run_check("--strict")[0], 1)

    def test_allowlist_entries_need_a_reason_and_a_known_rule(self):
        self.allowlist.write_text(json.dumps({"allowed": [
            {"file": "f", "rule": "font-abs", "match": "m", "count": 1, "reason": " "}]}))
        with self.assertRaises(ValueError):
            lint.load_allowlist(self.allowlist)
        self.allowlist.write_text(json.dumps({"allowed": [
            {"file": "f", "rule": "nope", "match": "m", "count": 1, "reason": "x"}]}))
        with self.assertRaises(ValueError):
            lint.load_allowlist(self.allowlist)


class Repository(unittest.TestCase):
    def test_repository_passes_strictly(self):
        found = lint.scan()
        violations, slack = lint.compare(found, lint.load_allowlist())
        self.assertEqual(violations, [])
        self.assertEqual(slack, [], "trim ui-size-allowlist.json to what the sources still contain")

    def test_repobar_taskbar_readout_stays_allowlisted_for_the_owner(self):
        entries = json.loads((HERE / "ui-size-allowlist.json").read_text())["allowed"]
        entry = next(e for e in entries if e["file"].endswith("dock-taskbar-repobar.patch") and e["match"] == "font-size: 18pt")
        self.assertEqual(entry["count"], 2)
        self.assertIn("Owner", entry["reason"])

    def test_dock_fallbacks_equal_default_step_tokens(self):
        system = json.loads((HERE / "size-system.json").read_text())
        default = next(s for s in system["steps"] if s["name"] == system["default_step"])["dock"]
        expected = {"mseries/display-space/dock_profile.py": default["work"],
                    "mseries/dock-trial/dock-trial.py": default["native"]}
        for relative, size in expected.items():
            text = (HERE.parent.parent / relative).read_text()
            self.assertIn(f"DEFAULT_ICON_SIZE = {size}\n", text, relative)

    def test_wrapper_script_runs_the_check(self):
        result = subprocess.run(["bash", str(HERE / "check-ui-sizes.sh"), "--strict"], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("check-ui-sizes: ok", result.stdout)


if __name__ == "__main__":
    unittest.main()
