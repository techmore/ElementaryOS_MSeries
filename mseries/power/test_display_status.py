#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Capability tests for optional Mutter DisplayConfig properties."""
import importlib.util
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import patch


MODULE = Path(__file__).with_name("display_status.py")
SPEC = importlib.util.spec_from_file_location("display_status", MODULE)
display_status = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(display_status)


class FakeBus:
    def __init__(self, *, power_save_mode=0, fail_power_save_mode=False, fail_state=False):
        self.power_save_mode = power_save_mode
        self.fail_power_save_mode = fail_power_save_mode
        self.fail_state = fail_state

    def call_sync(self, _dest, _path, _interface, method, *_args):
        if method == "GetCurrentState":
            if self.fail_state:
                raise RuntimeError("DisplayConfig unavailable")
            monitor = ("eDP-1", "Apple", "test", "test")
            modes = [("3024x1964@120", 3024, 1964, 120.0, True, [1.0], {"is-current": True})]
            logical = [(0, 0, 1.0, 0, True, [monitor], {})]
            return types.SimpleNamespace(unpack=lambda: (1, [(monitor, modes, {})], logical, {}))
        if self.fail_power_save_mode:
            raise RuntimeError("Unknown property PowerSaveMode")
        return types.SimpleNamespace(unpack=lambda: (self.power_save_mode,))


class DisplayStatusTests(unittest.TestCase):
    def read_with_bus(self, bus):
        repository = types.ModuleType("gi.repository")
        repository.Gio = types.SimpleNamespace(
            BusType=types.SimpleNamespace(SESSION="session"),
            DBusCallFlags=types.SimpleNamespace(NONE=0),
            bus_get_sync=lambda *_args: bus,
        )
        repository.GLib = types.SimpleNamespace(Variant=lambda *_args: object())
        gi = types.ModuleType("gi")
        gi.repository = repository
        with patch.dict(sys.modules, {"gi": gi, "gi.repository": repository}):
            return display_status.read_active()

    def test_complete_context_reports_all_capabilities(self):
        result = self.read_with_bus(FakeBus(power_save_mode=0))
        self.assertTrue(result["available"])
        self.assertTrue(result["modes_available"])
        self.assertTrue(result["layout_available"])
        self.assertTrue(result["power_save_mode_available"])
        self.assertEqual(result["monitors"][0]["connector"], "eDP-1")
        self.assertEqual(result["power_save_mode"], 0)

    def test_missing_optional_power_property_preserves_modes_and_layout(self):
        result = self.read_with_bus(FakeBus(fail_power_save_mode=True))
        self.assertFalse(result["available"])
        self.assertTrue(result["modes_available"])
        self.assertTrue(result["layout_available"])
        self.assertFalse(result["power_save_mode_available"])
        self.assertIsNone(result["power_save_mode"])
        self.assertEqual(result["monitors"][0]["refresh_hz"], 120.0)
        self.assertEqual(result["layout"][0]["connectors"], ["eDP-1"])

    def test_failed_display_state_does_not_claim_any_capability(self):
        result = self.read_with_bus(FakeBus(fail_state=True))
        self.assertFalse(result["available"])
        self.assertFalse(result["modes_available"])
        self.assertFalse(result["layout_available"])
        self.assertFalse(result["power_save_mode_available"])
        self.assertEqual(result["reason"], "RuntimeError")


if __name__ == "__main__":
    unittest.main()
