#!/usr/bin/env python3
"""Candidate admission checks: config resolution, input integrity and output isolation."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

import candidate
from release import PINS


class CandidateTests(unittest.TestCase):
    def test_rebased_series_is_hashed_and_separate_from_release(self):
        data = candidate.series()
        self.assertEqual(len(data["patches"]), 6)
        self.assertEqual(sum(patch["profile"] == "candidate" for patch in data["patches"]), 5)
        for version in data["kernel_release"].values():
            self.assertNotEqual(version, PINS["kernel_release"])

    def test_corrupt_patch_is_refused(self):
        with mock.patch.object(candidate, "sha256", return_value="corrupt"):
            with self.assertRaisesRegex(ValueError, "patch checksum"):
                candidate.series()

    def test_release_update_requires_explicit_rebase(self):
        data = candidate.series()
        data["base_source"] = "wrong"
        with mock.patch.object(candidate.json, "loads", return_value=data):
            with self.assertRaisesRegex(ValueError, "rebase"):
                candidate.series()

    def test_actual_config_is_updated_and_egpu_is_explicit(self):
        data = candidate.series()
        original = 'CONFIG_LOCALVERSION="-ARCH"\n# CONFIG_UDMABUF is not set\nCONFIG_DRM_AMDGPU=m\n'
        config = candidate.configure(original, candidate.settings(data, "candidate"))
        values = candidate.config_values(config)
        self.assertEqual(values["UDMABUF"], "y")
        self.assertEqual(values["DRM_AMDGPU"], "n")
        self.assertEqual(values["DRM_NOUVEAU"], "n")
        self.assertEqual(values["LOCALVERSION"], '""')
        egpu = candidate.configure(original, candidate.settings(data, "egpu"))
        self.assertEqual(candidate.config_values(egpu)["DRM_AMDGPU"], "m")

    def test_kconfig_silently_disabling_rust_or_an_enhancement_is_rejected(self):
        data = candidate.series()
        options = candidate.settings(data, "candidate")
        options.update(ARM64_16K_PAGES="y", RUST="y", DRM_ASAHI="y", DRM_APPLE="m",
                       DRM_APPLE_FABRIC_CORE="m", APPLE_SEP="m", USB4="m", USB4_APPLE_SOC="m")
        config = candidate.configure("", options)
        candidate.config_gate(config, data, "candidate")
        for key in ("RUST", "UDMABUF", "DRM_APPLE", "ARM64_16K_PAGES"):
            broken = candidate.configure(config, {key: "n"})
            with self.assertRaisesRegex(ValueError, key):
                candidate.config_gate(broken, data, "candidate")

    def test_prepared_source_or_config_changes_are_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "source").mkdir()
            (root / "build").mkdir()
            (root / "source/fixture").write_text("original")
            (root / "build/.config").write_text("original config")
            receipt = dict(series_sha256=candidate.sha256(candidate.MANIFEST), base_pins=PINS,
                           source_tree_sha256=candidate.tree_digest(root / "source"),
                           modified_files={"fixture": candidate.sha256(root / "source/fixture")},
                           prepared_config_sha256=candidate.sha256(root / "build/.config"))
            (root / "candidate.json").write_text(json.dumps(receipt))
            candidate.verify(root)
            (root / "build/.config").write_text("changed config")
            with self.assertRaisesRegex(ValueError, "configuration changed"):
                candidate.verify(root)
            (root / "build/.config").write_text("original config")
            (root / "source/fixture").write_text("changed source")
            with self.assertRaisesRegex(ValueError, "source changed"):
                candidate.verify(root)

    def test_full_tree_binding_detects_an_edit_outside_the_patch_series(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "untouched.c").write_text("original kernel file")
            before = candidate.tree_digest(root)
            (root / "untouched.c").write_text("unrecorded change")
            self.assertNotEqual(candidate.tree_digest(root), before)

    def test_existing_output_and_boot_directories_are_refused(self):
        with tempfile.TemporaryDirectory() as temporary:
            with self.assertRaisesRegex(ValueError, "must not exist"):
                candidate.fresh(temporary)
        for path in ("/boot/candidate", "/Volumes/fixture/candidate"):
            with self.assertRaisesRegex(ValueError, "private build directory"):
                candidate.fresh(path)

    def test_artifacts_cannot_be_archived_into_their_own_source(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            with self.assertRaisesRegex(ValueError, "outside the prepared"):
                candidate.fresh(root / "source/artifacts", outside=root)
            self.assertFalse((root / "source/artifacts").exists())


if __name__ == "__main__":
    unittest.main()
