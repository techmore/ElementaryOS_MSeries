#!/usr/bin/env python3
"""Offline regressions for release admission, boot preservation and installer boundaries."""
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import tarfile
import tempfile
import unittest
from unittest import mock

from release import HERE, PINS, asset, extract


def load(name, filename):
    spec = importlib.util.spec_from_file_location(name, HERE / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


grub = load("aurora_grub", "grub-entry.py")
stage = load("aurora_stage", "stage-boot.py")
package = load("aurora_package", "package-release.py")


def tree(compatible):
    return subprocess.check_output(["dtc", "-I", "dts", "-O", "dtb"],
                                   input=f'/dts-v1/; / {{ compatible = "{compatible}"; }};'.encode())


class PortTests(unittest.TestCase):
    def test_corrupt_cached_package_is_refused_without_network(self):
        with tempfile.TemporaryDirectory() as temporary:
            cached = Path(temporary) / PINS["assets"]["kernel"]["name"]
            cached.write_bytes(b"damaged download")
            with mock.patch("urllib.request.urlopen", side_effect=AssertionError("unexpected network")):
                with self.assertRaisesRegex(ValueError, "checksum mismatch"):
                    asset(temporary, "kernel", offline=True)

    def test_archive_cannot_escape_extraction_root(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            archive = root / "bad.tar"
            with tarfile.open(archive, "w") as stream:
                entry = tarfile.TarInfo("usr/lib/modules/../../../../escape")
                entry.size = 3
                stream.addfile(entry, io.BytesIO(b"bad"))
            with self.assertRaises(tarfile.FilterError):
                extract(archive, root / "dest", ("usr/lib/modules",))
            self.assertFalse((root / "escape").exists())

    def test_versioned_grub_update_retains_old_kernel_and_unrelated_entries(self):
        legacy = "# BEGIN elementary aurora-sep\nmenuentry old19 {}\n# END elementary aurora-sep\nmenuentry fairydust {}\n"
        block = grub.BEGIN + "\nmenuentry aurora20 {}\n" + grub.END
        result = grub.update(legacy, block)
        self.assertIn(legacy.rstrip(), result)
        replacement = block.replace("aurora20 {}", "new20 {}")
        replaced = grub.update(result, replacement)
        self.assertEqual(replaced.count(grub.BEGIN), 1)
        self.assertIn("new20 {}", replaced)
        self.assertEqual(grub.update(replaced, "").strip(), legacy.strip())

    def test_malformed_grub_block_is_refused(self):
        for text in (grub.BEGIN, grub.END, grub.BEGIN + grub.BEGIN + grub.END):
            with self.assertRaises(ValueError):
                grub.update(text, "")

    def test_boot_candidate_changes_only_m1n1_and_selected_board(self):
        trees = [tree("apple,j314s" if i == 3 else f"apple,fixture{i}") for i in range(8)]
        prefix, replacement = b"M1N1 old loader", b"M1N1 new loader"
        tail = b"\x1f\x8bfixture U-Boot and chosen configuration\n"
        original = prefix + b"".join(trees) + tail
        new_tree = tree("apple,j314s") + b""  # A real FDT produced by dtc.
        result, report = stage.compose(original, replacement, new_tree)
        self.assertEqual(result, replacement + b"".join(trees[:3]) + new_tree + b"".join(trees[4:]) + tail)
        self.assertTrue(report["other_dtbs_identical"])
        self.assertTrue(report["uboot_and_config_identical"])
        self.assertEqual(report["replaced_index"], 3)

    def test_boot_candidate_refuses_ambiguous_or_wrong_board(self):
        trees = [tree("apple,j314s") for _ in range(8)]
        with self.assertRaises(ValueError):
            stage.compose(b"M1N1" + b"".join(trees) + b"tail", b"M1N1new", trees[0])

    def test_debian_envelope_contains_only_control_and_payload(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            control, payload = root / "control", root / "payload"
            control.mkdir()
            payload.mkdir()
            (control / "control").write_text("Package: fixture\nArchitecture: arm64\n")
            (payload / "fixture").write_bytes(b"payload")
            output = root / "fixture.deb"
            package.write_deb(output, control, payload)
            data = output.read_bytes()
            self.assertEqual(data[:8], b"!<arch>\n")
            offset, names = 8, []
            while offset < len(data):
                header = data[offset:offset + 60]
                self.assertEqual(header[58:], b"`\n")
                names.append(header[:16].decode().strip().rstrip("/"))
                size = int(header[48:58])
                offset += 60 + size + size % 2
            self.assertEqual(offset, len(data))
            self.assertEqual(names, ["debian-binary", "control.tar.gz", "data.tar.gz"])

    def test_installer_dry_run_keeps_download_logs_out_of_package_filename(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            custom = root / "custom.cfg"
            original = "menuentry legacy19 {}\nmenuentry fairydust {}\n"
            custom.write_text(original)
            env = dict(os.environ, ROOT_UUID="fixture-root", CRYPTDEVICE="UUID=fixture:cryptroot",
                       CMDLINE_FILE=str(root / "missing"), GRUB_CUSTOM=str(custom),
                       DOWNLOAD_DIR=str(root / "downloads"), INITRAMFS_TOOL="mkinitcpio")
            script = HERE.parent / "aurora-sep/install-aurora-sep.sh"
            result = subprocess.run(["bash", str(script)], env=env, capture_output=True, text=True, check=True)
            package_path = root / "downloads" / PINS["assets"]["kernel"]["name"]
            self.assertIn(f"-xpf '{package_path}'", result.stdout)
            self.assertNotIn("[dry-run] curl", result.stdout)
            self.assertIn("elementary-aurora20", result.stdout)
            self.assertIn("mkinitcpio", result.stdout)
            self.assertNotIn("user4k=on", result.stdout)
            self.assertNotIn("install the Aurora libfprint", result.stdout)
            self.assertEqual(custom.read_text(), original)
            self.assertFalse((root / "downloads").exists())

    def test_installer_and_shared_pins_agree(self):
        script = (HERE.parent / "aurora-sep/install-aurora-sep.sh").read_text()
        self.assertIn("KVER=" + PINS["kernel_release"], script)
        self.assertIn("AURORA_RELEASE=" + PINS["release"], script)
        for kind, prefix in (("kernel", "KERNEL"), ("touchid", "TOUCHID")):
            self.assertIn(prefix + "_PKG=" + PINS["assets"][kind]["name"], script)
            self.assertIn(prefix + "_SHA=" + PINS["assets"][kind]["sha256"], script)


if __name__ == "__main__":
    unittest.main()
