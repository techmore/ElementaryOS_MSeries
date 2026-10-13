#!/usr/bin/env python3
"""Small integration checks for the ESP-safe m1n1 payload assembler."""

from __future__ import annotations

import gzip
from pathlib import Path
import struct
import subprocess
import tempfile
import unittest


SCRIPT = Path(__file__).with_name("assemble-m1n1-bootbin.py")


def fdt(payload: bytes = b"") -> bytes:
    total_size = 40 + len(payload)
    return struct.pack(">10I", 0xD00DFEED, total_size, 40, 40, 40, 0, 0, 0, 0, 0) + payload


class AssembleBootbinTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.dtbs = self.root / "dtbs"
        self.dtbs.mkdir()
        self.m1n1 = self.root / "m1n1.bin"
        self.m1n1.write_bytes(b"M1N1-prefix")
        self.u_boot = self.root / "u-boot.bin"
        self.u_boot.write_bytes(b"uboot-payload" * 8)
        (self.dtbs / "t6000-j314s.dtb").write_bytes(fdt(b"M1 Pro"))
        (self.dtbs / "t6020-jxxx.dtb").write_bytes(fdt(b"other Mac"))
        (self.dtbs / "t8112-jxxx.dtb").write_bytes(fdt(b"another Mac"))
        (self.dtbs / "unrelated.dtb").write_bytes(fdt(b"excluded"))
        self.output = self.root / "out" / "boot.bin"

    def tearDown(self) -> None:
        self.temp.cleanup()

    def run_assembler(self, *extra: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [
                "python3", str(SCRIPT), "--m1n1", str(self.m1n1), "--dtb-dir", str(self.dtbs),
                "--u-boot", str(self.u_boot), "--output", str(self.output), *extra,
            ], text=True, capture_output=True, check=False,
        )

    def test_deterministic_layout_and_supported_config_filter(self) -> None:
        config = self.root / "m1n1.conf"
        config.write_text("# comment\nchosen.foo=bar\nunsupported=true\ndisplay=auto\n", encoding="utf-8")
        first = self.run_assembler("--config", str(config))
        self.assertEqual(first.returncode, 0, first.stderr)
        first_bytes = self.output.read_bytes()
        second = self.run_assembler("--config", str(config))
        self.assertEqual(second.returncode, 0, second.stderr)
        self.assertEqual(first_bytes, self.output.read_bytes())

        expected = bytearray(self.m1n1.read_bytes())
        expected.extend((self.dtbs / "t6000-j314s.dtb").read_bytes())
        expected.extend((self.dtbs / "t6020-jxxx.dtb").read_bytes())
        expected.extend((self.dtbs / "t8112-jxxx.dtb").read_bytes())
        expected.extend(gzip.compress(self.u_boot.read_bytes(), mtime=0))
        expected.extend(b"chosen.foo=bar\ndisplay=auto\n")
        self.assertEqual(first_bytes, bytes(expected))
        self.assertIn("3 Apple DTBs", first.stdout)

    def test_bad_dtb_fails_without_replacing_existing_output(self) -> None:
        (self.dtbs / "t6000-j314s.dtb").write_bytes(b"not an FDT")
        self.output.parent.mkdir()
        self.output.write_bytes(b"previous-good-output")
        result = self.run_assembler()
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.output.read_bytes(), b"previous-good-output")

    def test_missing_owner_model_dtb_fails_closed(self) -> None:
        (self.dtbs / "t6000-j314s.dtb").unlink()
        result = self.run_assembler()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("t6000-j314s.dtb", result.stderr)
        self.assertFalse(self.output.exists())

    def test_output_cannot_replace_a_source_dtb(self) -> None:
        owner_dtb = self.dtbs / "t6000-j314s.dtb"
        original = owner_dtb.read_bytes()
        result = subprocess.run(
            [
                "python3", str(SCRIPT), "--m1n1", str(self.m1n1), "--dtb-dir", str(self.dtbs),
                "--u-boot", str(self.u_boot), "--output", str(owner_dtb),
            ], text=True, capture_output=True, check=False,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("must not replace an input DTB", result.stderr)
        self.assertEqual(owner_dtb.read_bytes(), original)


if __name__ == "__main__":
    unittest.main()
