#!/usr/bin/env python3
"""Unit tests for locating the unique ESP in a systemd-repart GPT report."""

from __future__ import annotations

import importlib.util
from pathlib import Path
import unittest


SCRIPT = Path(__file__).with_name("verify-m1n1-esp.py")
SPEC = importlib.util.spec_from_file_location("verify_m1n1_esp", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


class EspOffsetTest(unittest.TestCase):
    def test_selects_esp_and_converts_sector_to_byte_offset(self) -> None:
        layout = {"partitiontable": {"sectorsize": 4096, "partitions": [
            {"start": 256, "type": "c12a7328-f81f-11d2-ba4b-00a0c93ec93b"},
            {"start": 2048, "type": "4f68bce3-e8cd-4db1-96e7-fbcaf984b709"},
        ]}}
        self.assertEqual(MODULE.esp_byte_offset(layout), 1_048_576)

    def test_rejects_missing_or_multiple_esps(self) -> None:
        guid = "c12a7328-f81f-11d2-ba4b-00a0c93ec93b"
        with self.assertRaisesRegex(ValueError, "found 0"):
            MODULE.esp_byte_offset({"partitiontable": {"partitions": []}})
        with self.assertRaisesRegex(ValueError, "found 2"):
            MODULE.esp_byte_offset({"partitiontable": {"partitions": [
                {"start": 1, "type": guid}, {"start": 2, "type": guid},
            ]}})

    def test_rejects_bad_geometry(self) -> None:
        guid = "c12a7328-f81f-11d2-ba4b-00a0c93ec93b"
        with self.assertRaisesRegex(ValueError, "offset or sector size"):
            MODULE.esp_byte_offset({"partitiontable": {
                "sectorsize": 0, "partitions": [{"start": 1, "type": guid}],
            }})


if __name__ == "__main__":
    unittest.main()
