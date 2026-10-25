#!/usr/bin/env python3
"""Compare the Rust ISO-label command with the legacy shell contract."""

import os
from pathlib import Path
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[3]
REFERENCE = ROOT / "mseries/iso-label.sh"
CASES = [
    ("daily", "arm64"),
    ("daily-proposed", "x86-64"),
    ("abcdefghijklmnopqrstuvwx", "arm64"),
    ("é A.b", "arm-64"),
    ("", ""),
    ("a\nb", "a\tb"),
]


class IsoLabelParity(unittest.TestCase):
    def test_rust_cli_matches_legacy_shell_for_normalization_cases(self):
        if len(sys.argv) != 2:
            self.fail("usage: test-parity.py PATH_TO_RELEASE_BINARY")
        binary = Path(sys.argv[1]).resolve()
        env = os.environ | {"LC_ALL": "C"}
        for profile, arch in CASES:
            with self.subTest(profile=profile, arch=arch):
                legacy = subprocess.run(
                    ["bash", "-c", 'source "$1"; value=$(iso_volume_label "$2" "$3"); printf "%s" "$value"',
                     "iso-label-parity", str(REFERENCE), profile, arch],
                    check=True,
                    capture_output=True,
                    text=True,
                    env=env,
                ).stdout
                rust = subprocess.run(
                    [str(binary), profile, arch],
                    check=True,
                    capture_output=True,
                    text=True,
                    env=env,
                ).stdout
                self.assertEqual(rust.removesuffix("\n"), legacy)


if __name__ == "__main__":
    unittest.main(argv=[sys.argv[0]])
