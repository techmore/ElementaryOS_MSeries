#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Read back and verify m1n1/boot.bin in a disposable systemd-repart image."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tempfile


ESP_GUID = "c12a7328-f81f-11d2-ba4b-00a0c93ec93b"


def esp_byte_offset(layout: dict) -> int:
    table = layout.get("partitiontable", {})
    sector_size = table.get("sectorsize", 512)
    partitions = table.get("partitions", [])
    matches = [p for p in partitions if str(p.get("type", "")).lower() == ESP_GUID]
    if len(matches) != 1:
        raise ValueError(f"expected exactly one GPT ESP partition, found {len(matches)}")
    offset = matches[0].get("start")
    if not isinstance(offset, int) or offset <= 0 or not isinstance(sector_size, int) or sector_size <= 0:
        raise ValueError("invalid ESP partition offset or sector size")
    return offset * sector_size


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", required=True, type=Path, help="disposable systemd-repart disk image")
    parser.add_argument("--expected", required=True, type=Path, help="source boot.bin to compare against")
    args = parser.parse_args()
    image = args.image.resolve(strict=True)
    expected = args.expected.resolve(strict=True)
    for command in ("sfdisk", "mcopy"):
        if shutil.which(command) is None:
            parser.error(f"required command not found: {command}")

    layout_text = subprocess.run(
        ["sfdisk", "--json", str(image)], check=True, capture_output=True, text=True
    ).stdout
    offset = esp_byte_offset(json.loads(layout_text))
    with tempfile.TemporaryDirectory(prefix="fairydust-esp-verify-") as directory:
        extracted = Path(directory) / "boot.bin"
        subprocess.run(
            ["mcopy", "-i", f"{image}@@{offset}", "::/m1n1/boot.bin", str(extracted)],
            check=True,
        )
        actual_hash = hashlib.sha256(extracted.read_bytes()).hexdigest()
        expected_hash = hashlib.sha256(expected.read_bytes()).hexdigest()
        if actual_hash != expected_hash:
            raise SystemExit(
                f"ESP m1n1/boot.bin SHA-256 mismatch: expected {expected_hash}, got {actual_hash}"
            )
        if extracted.stat().st_size == 0:
            raise SystemExit("ESP m1n1/boot.bin is empty")
        print(
            f"PASS: ESP m1n1/boot.bin matches {expected_hash} "
            f"({extracted.stat().st_size} bytes; partition offset {offset})"
        )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
        raise SystemExit(f"Cannot verify m1n1 payload in image: {error}") from error
