#!/usr/bin/env python3
"""Keep source inventory roles grounded in file content and format."""

import importlib.util
import json
from pathlib import Path
import tempfile
import tomllib
import unittest

SPEC = importlib.util.spec_from_file_location("inventory", Path(__file__).with_name("inventory.py"))
INVENTORY = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(INVENTORY)


class InventoryRoles(unittest.TestCase):
    def test_root_workspace_members_have_independent_project_records(self):
        document = json.loads(INVENTORY.render())
        projects = {project["id"]: project for project in document["projects"]}
        workspace = tomllib.loads((INVENTORY.ROOT / "rust/Cargo.toml").read_text())
        for member in workspace["workspace"]["members"]:
            project = "mseries/power" if member == "mseries-power" else f"rust/{member}"
            with self.subTest(member=member):
                self.assertIn(f"rust/{member}/Cargo.toml", projects[project]["items"])
        messages = projects["rust/mseries-messages"]
        self.assertEqual("owner-deferred-incomplete", messages["migration_status"])

    def test_elementary_seed_compiler_is_a_separate_unverified_project(self):
        document = json.loads(INVENTORY.render())
        project = next(
            item for item in document["projects"]
            if item["id"] == "elementary/package-generator"
        )
        self.assertIn("mseries/rust/seed-compiler/src/lib.rs", project["items"])
        self.assertIn("mseries/rust/seed-compiler/src/main.rs", project["items"])
        self.assertEqual("candidate-implemented-unverified", project["migration_status"])
        self.assertEqual("implementation-present-unverified", project["parity_contract_status"])

    def test_atomic_app_reference_and_rust_cli_share_one_project_record(self):
        document = json.loads(INVENTORY.render())
        project = next(item for item in document["projects"] if item["id"] == "mseries/atomic-app")
        self.assertIn("mseries/atomic-app.py", project["items"])
        self.assertIn("mseries/rust/atomic-app/src/main.rs", project["items"])
        self.assertIn("mseries/rust/atomic-app/test-parity.py", project["items"])
        self.assertEqual("candidate-parity-verified-not-installed", project["migration_status"])
        self.assertEqual("candidate-parity-evidence-present", project["parity_contract_status"])

    def test_every_project_has_a_separate_migration_and_parity_record(self):
        document = json.loads(INVENTORY.render())
        projects = document["projects"]
        self.assertEqual(len(projects), document["project_count"])
        for project in projects:
            with self.subTest(project=project["id"]):
                self.assertTrue(project["items"])
                self.assertTrue(project["rust_target"])
                self.assertTrue(project["migration_status"])
                self.assertTrue(project["parity_contract_status"])
                self.assertTrue(project["parity_contract"])
                self.assertTrue(project["enhancement_review_status"])
                self.assertIsInstance(project["intentional_enhancements"], list)

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
