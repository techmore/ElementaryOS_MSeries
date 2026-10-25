#!/usr/bin/env python3
"""Unit tests for the size-system planner (no desktop session needed)."""

import importlib.machinery
import importlib.util
import re
import unittest
import tempfile
import configparser
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch
from pathlib import Path

HERE = Path(__file__).resolve().parent
loader = importlib.machinery.SourceFileLoader("mseries_ui_scale", str(HERE / "mseries-ui-scale"))
spec = importlib.util.spec_from_loader(loader.name, loader)
ui = importlib.util.module_from_spec(spec)
loader.exec_module(ui)

TEXT = (ui.INTERFACE, "text-scaling-factor")
ICON = (ui.DOCK, "icon-size")
WORK = {"dock": {"applied": True}}


class Ladder(unittest.TestCase):
    def setUp(self):
        self.system = ui.load_system(HERE / "size-system.json")

    def test_steps_are_increasing_and_tokens_complete(self):
        factors = [s["text"] for s in self.system["steps"]]
        self.assertEqual(factors, sorted(factors))
        for step in self.system["steps"]:
            self.assertEqual(set(step["dock"]), {"native", "work", "work-taskbar"})
            for size in step["dock"].values():
                self.assertEqual(size % 4, 0, step)
        native = [s["dock"]["native"] for s in self.system["steps"]]
        self.assertEqual(native, sorted(native))

    def test_default_step_matches_elementary_defaults(self):
        step = ui.find_step(self.system, self.system["default_step"])
        self.assertEqual(step["text"], 1.0)
        self.assertEqual(step["dock"]["native"], 48)

    def test_owner_drag_value_snaps_to_compact(self):
        self.assertEqual(ui.nearest_step(self.system, 0.85108303249097472)["name"], "compact")
        self.assertFalse(ui.on_ladder(self.system, 0.85108303249097472))

    def test_step_from_off_ladder_value_moves_in_requested_direction(self):
        self.assertEqual(ui.neighbour(self.system, 0.851, 1)["name"], "small")
        self.assertEqual(ui.neighbour(self.system, 0.851, -1)["name"], "compact")
        self.assertEqual(ui.neighbour(self.system, 0.86, 1)["name"], "small")
        self.assertEqual(ui.neighbour(self.system, 0.86, -1)["name"], "compact")
        self.assertEqual(ui.neighbour(self.system, 1.0, 1)["name"], "large")
        self.assertEqual(ui.neighbour(self.system, 1.5, 1)["name"], "largest")
        self.assertEqual(ui.neighbour(self.system, 0.85, -1)["name"], "compact")

    def test_find_step_accepts_names_factors_and_percent(self):
        self.assertEqual(ui.find_step(self.system, "Larger")["text"], 1.25)
        self.assertEqual(ui.find_step(self.system, "1.1")["name"], "large")
        self.assertEqual(ui.find_step(self.system, "92%")["name"], "small")


class Planner(unittest.TestCase):
    def setUp(self):
        self.system = ui.load_system(HERE / "size-system.json")

    def test_unmanaged_desktop_is_never_changed(self):
        self.assertEqual(ui.plan(self.system, {TEXT: 0.851, ICON: 48}, False, {}, False), {})

    def test_managed_snaps_text_and_sets_native_dock(self):
        writes = ui.plan(self.system, {TEXT: 0.851, ICON: 48}, True, {}, False)
        self.assertEqual(writes, {TEXT: 0.85, ICON: 40})

    def test_on_ladder_value_is_not_rewritten(self):
        self.assertEqual(ui.plan(self.system, {TEXT: 1.0, ICON: 48}, True, {}, False), {})

    def test_work_mode_tokens(self):
        self.assertEqual(ui.plan(self.system, {TEXT: 1.0, ICON: 48}, True, WORK, False), {ICON: 40})
        self.assertEqual(ui.plan(self.system, {TEXT: 1.25, ICON: 40}, True, WORK, True), {ICON: 60})
        self.assertEqual(ui.plan(self.system, {TEXT: 1.0, ICON: 40}, True, {"dock": {"applied": False}}, False),
                         {ICON: 48})

    def test_work_mode_status_default_desktop_is_native(self):
        state = {"applied": True, "status": "Default desktop", "dock": {"applied": True}}
        self.assertEqual(ui.dock_mode(state, False), "native")
        state["status"] = "Windows Work Mode · work layout active"
        self.assertEqual(ui.dock_mode(state, False), "work")

    def test_accessibility_sizes_outside_the_ladder_are_left_alone(self):
        writes = ui.plan(self.system, {TEXT: 2.0, ICON: 72}, True, {}, False)
        self.assertNotIn(TEXT, writes)
        self.assertEqual(writes, {})

    def test_missing_dock_schema_only_touches_text(self):
        self.assertEqual(ui.plan(self.system, {TEXT: 1.12}, True, {}, False), {TEXT: 1.1})

    def test_font_policy_only_writes_differences(self):
        values = {ui.FONT_KEYS["ui"]: "Inter 9", ui.FONT_KEYS["titlebar"]: "Adwaita Sans Bold 11"}
        self.assertEqual(ui.font_plan(self.system, values), {ui.FONT_KEYS["titlebar"]: "Inter Bold 9"})


class NativePolicy(unittest.TestCase):
    def test_adoption_publishes_before_dock_signal_and_applies_font_policy(self):
        system = ui.load_system(HERE / "size-system.json")
        with tempfile.TemporaryDirectory() as temporary, patch.object(ui, "state_dir", return_value=Path(temporary)):
            class Desktop:
                def __init__(self):
                    self.current = {TEXT: 0.85, ICON: 48, ui.FONT_KEYS["titlebar"]: "Old Font 11"}
                def values(self):
                    return self.current.copy()
                def taskbar(self):
                    return False
                def write(self, writes):
                    policy = configparser.ConfigParser()
                    policy.read(Path(temporary) / "ui-scale-policy.ini")
                    # Simulates a synchronous GSettings icon-size observer.
                    assert policy.getboolean("SizeSystem", "managed")
                    self.current.update(writes)
            desktop = Desktop()
            ui.reconcile(system, desktop, managed=True)
            self.assertEqual(desktop.current[ICON], 40)
            self.assertEqual(desktop.current[ui.FONT_KEYS["titlebar"]], "Inter Bold 9")

    def test_concurrent_cli_and_watcher_writers_use_owned_temporaries(self):
        system = ui.load_system(HERE / "size-system.json")
        with tempfile.TemporaryDirectory() as temporary, patch.object(ui, "state_dir", return_value=Path(temporary)):
            def write(index):
                ui.set_managed(bool(index % 2))
                ui.publish_policy(True)
            with ThreadPoolExecutor(max_workers=4) as executor:
                list(executor.map(write, range(100)))
            self.assertIsInstance(ui.is_managed(), bool)
            config = configparser.ConfigParser()
            config.read(Path(temporary) / "ui-scale-policy.ini")
            self.assertTrue(config.getboolean("SizeSystem", "managed"))
            self.assertEqual(config.getint("SizeSystem", "version"), 1)
            self.assertEqual(sorted(path.name for path in Path(temporary).iterdir()),
                             ["ui-scale-policy.ini", "ui-scale.json"])

    def test_installer_copies_policy_producer_and_token_payload(self):
        installer = (HERE.parent / "install-ui-scale.sh").read_text()
        self.assertIn('"$src/mseries-ui-scale" "$bin"', installer)
        self.assertIn('"$src/size-system.json" "$data/size-system.json"', installer)

    def test_managed_policy_atomic_replacements_and_unmanage(self):
        with tempfile.TemporaryDirectory() as temporary, patch.object(ui, "state_dir", return_value=Path(temporary)):
            policy_path = Path(temporary) / "ui-scale-policy.ini"
            for managed in [True, False, True]:
                ui.publish_policy(managed)
                config = configparser.ConfigParser()
                config.read(policy_path)
                self.assertEqual(config.getboolean("SizeSystem", "managed"), managed)
                self.assertEqual(config.getint("SizeSystem", "version"), 1)
                before = policy_path.stat().st_mtime_ns
                ui.publish_policy(managed)
                self.assertEqual(policy_path.stat().st_mtime_ns, before)
                self.assertFalse(policy_path.with_suffix(".ini.tmp").exists())


class QuickSettingsLadder(unittest.TestCase):
    """The Quick Settings widget embeds the ladder; it must match size-system.json."""

    def test_vala_ladder_matches_json(self):
        system = ui.load_system(HERE / "size-system.json")
        source = (HERE.parent / "quick-settings" / "TextScale.vala").read_text(encoding="utf-8")
        factors = re.search(r"STEPS\s*=\s*\{([^}]*)\}", source).group(1)
        names = re.search(r"NAMES\s*=\s*\{([^}]*)\}", source, re.S).group(1)
        self.assertEqual([float(v) for v in factors.split(",")], [s["text"] for s in system["steps"]])
        self.assertEqual(re.findall(r'N_\("([^"]+)"\)', names), [s["label"] for s in system["steps"]])


if __name__ == "__main__":
    unittest.main()
