#!/usr/bin/env python3
"""Keep source inventory roles grounded in file content and format."""

import importlib.util
from pathlib import Path
import tempfile
import unittest

SPEC = importlib.util.spec_from_file_location("inventory", Path(__file__).with_name("inventory.py"))
INVENTORY = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(INVENTORY)


class InventoryRoles(unittest.TestCase):
    def test_known_source_and_build_scripts_are_implementation(self):
        self.assertEqual(INVENTORY.role(Path("helper.py")), "implementation")
        self.assertEqual(INVENTORY.role(Path("Justfile")), "implementation")
        self.assertEqual(INVENTORY.language(Path("Justfile")), "build-recipe")
        with tempfile.TemporaryDirectory() as temporary:
            script = Path(temporary) / "custom-hook"
            script.write_text("#!/bin/sh\nexit 0\n")
            self.assertEqual(INVENTORY.role(script), "implementation")
            self.assertEqual(INVENTORY.language(script), "shell")

    def test_non_code_inputs_are_not_misclassified_as_implementation(self):
        self.assertEqual(INVENTORY.role(Path("settings.yaml")), "configuration-or-data")
        self.assertEqual(INVENTORY.role(Path("README.md")), "documentation-or-record")
        self.assertEqual(INVENTORY.role(Path("change.patch")), "upstream-patch")
        self.assertEqual(INVENTORY.role(Path("tests/mock.c")), "verification")
        self.assertEqual(INVENTORY.role(Path("fixtures/input.py")), "verification")
        with tempfile.TemporaryDirectory() as temporary:
            asset = Path(temporary) / "icon.bin"
            asset.write_bytes(b"\x89PNG\r\n\x1a\n\0\0")
            self.assertEqual(INVENTORY.role(asset), "asset-or-binary-input")


if __name__ == "__main__":
    unittest.main()
