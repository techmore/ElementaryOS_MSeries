#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Assemble an image-local Asahi m1n1 payload without touching an ESP.

The ordering follows Ubuntu Asahi's update-m1n1: m1n1 binary, Apple DTBs,
gzip-compressed U-Boot, then the supported m1n1 config lines. This only writes
the requested output file; it never mounts or discovers a system ESP.
"""

from __future__ import annotations

import argparse
import gzip
import os
from pathlib import Path
import tempfile


FDT_MAGIC = bytes.fromhex("d00dfeed")
CONFIG_PREFIXES = ("chosen.", "display=", "mitigations=")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--m1n1", required=True, type=Path, help="m1n1.bin")
    parser.add_argument("--dtb-dir", required=True, type=Path, help="directory containing Apple t6*.dtb and t81*.dtb")
    parser.add_argument("--u-boot", required=True, type=Path, help="U-Boot nodtb binary")
    parser.add_argument("--output", required=True, type=Path, help="output boot.bin path")
    parser.add_argument("--config", type=Path, help="optional m1n1 config; only supported keys are copied")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    m1n1 = args.m1n1.resolve(strict=True)
    dtb_dir = args.dtb_dir.resolve(strict=True)
    u_boot = args.u_boot.resolve(strict=True)
    output = args.output.resolve()

    if not m1n1.is_file() or not u_boot.is_file() or not dtb_dir.is_dir():
        raise SystemExit("m1n1 and U-Boot must be files; --dtb-dir must be a directory")
    if output in (m1n1, u_boot):
        raise SystemExit("output must not replace an input binary")

    dtbs = sorted(
        path for path in dtb_dir.iterdir()
        if path.is_file() and (path.name.startswith("t6") or path.name.startswith("t81")) and path.suffix == ".dtb"
    )
    if not dtbs:
        raise SystemExit(f"no Apple t6*.dtb or t81*.dtb files found in {dtb_dir}")
    if not any(path.name == "t6000-j314s.dtb" for path in dtbs):
        raise SystemExit("required M1 Pro MacBookPro18,3 DTB t6000-j314s.dtb is missing")
    if output in {path.resolve() for path in dtbs}:
        raise SystemExit("output must not replace an input DTB")
    if args.config and output == args.config.resolve(strict=True):
        raise SystemExit("output must not replace the m1n1 config")
    for dtb in dtbs:
        with dtb.open("rb") as stream:
            header = stream.read(8)
        total_size = int.from_bytes(header[4:8], "big") if len(header) == 8 else 0
        if len(header) != 8 or header[:4] != FDT_MAGIC or not 40 <= total_size <= dtb.stat().st_size:
            raise SystemExit(f"invalid flattened device tree: {dtb}")

    config = b""
    if args.config:
        config_lines = []
        for line in args.config.read_text(encoding="utf-8").splitlines():
            if line.startswith(CONFIG_PREFIXES):
                config_lines.append(line)
        if config_lines:
            config = ("\n".join(config_lines) + "\n").encode()

    output.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary_name = tempfile.mkstemp(prefix=f".{output.name}.", suffix=".tmp", dir=output.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(fd, "wb") as target:
            target.write(m1n1.read_bytes())
            for dtb in dtbs:
                target.write(dtb.read_bytes())
            with u_boot.open("rb") as source:
                with gzip.GzipFile(fileobj=target, mode="wb", filename="", mtime=0) as compressed:
                    while chunk := source.read(1024 * 1024):
                        compressed.write(chunk)
            target.write(config)
            target.flush()
            os.fsync(target.fileno())
        os.replace(temporary, output)
    finally:
        temporary.unlink(missing_ok=True)

    print(f"assembled {output} ({output.stat().st_size} bytes; {len(dtbs)} Apple DTBs)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
