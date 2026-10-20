#!/usr/bin/env python3
"""Keep source inventory roles grounded in file content and format."""

import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

SPEC = importlib.util.spec_from_file_location("inventory", Path(__file__).with_name("inventory.py"))
INVENTORY = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(INVENTORY)


class InventoryRoles(unittest.TestCase):
    def test_rust_iso_label_is_joined_to_its_reference_and_in_use(self):
        document = json.loads(INVENTORY.render())
        project = next(item for item in document["projects"] if item["id"] == "mseries/iso-label")
        self.assertIn("mseries/iso-label.sh", project["items"])
        self.assertIn("mseries/test-iso-label.sh", project["items"])
        self.assertIn("mseries/rust/iso-label/src/main.rs", project["items"])
        item = next(item for item in document["items"] if item["path"] == "mseries/rust/iso-label/src/main.rs")
        self.assertEqual(item["rust_status"], "candidate-parity-verified-in-use")
        manifest = next(item for item in document["items"] if item["path"] == "mseries/rust/iso-label/Cargo.toml")
        self.assertEqual(manifest["rust_status"], "recorded-non-code-input")
        reference_test = next(item for item in document["items"] if item["path"] == "mseries/rust/iso-label/test-parity.py")
        self.assertEqual(reference_test["rust_status"], "candidate-parity-verified-not-installed")

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
