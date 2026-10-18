#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Build a J314S Aurora boot.bin candidate from an explicit existing copy; never deploy it."""
import argparse
import importlib.util
import json
from pathlib import Path
import tempfile

from release import HERE, PINS, asset, extract, sha256, validate_kernel

spec = importlib.util.spec_from_file_location("swap_dtb", HERE.parent / "fairydust/usb4/swap-dtb.py")
swap_dtb = importlib.util.module_from_spec(spec)
spec.loader.exec_module(swap_dtb)


def compose(original, m1n1, dtb):
    start, run, end = swap_dtb.split(original)
    key = b"apple,j314s\0"
    hits = [i for i, (offset, size) in enumerate(run) if key in original[offset:offset + size]]
    if len(hits) != 1 or key not in dtb:
        raise ValueError("expected exactly one J314S DTB in the input and candidate")
    if m1n1[:4] != original[:4]:
        raise ValueError("input does not start with the expected raw m1n1 signature")
    index = hits[0]
    trees = [original[offset:offset + size] for offset, size in run]
    trees[index] = dtb
    candidate = m1n1 + b"".join(trees) + original[end:]
    new_start, new_run, new_end = swap_dtb.split(candidate)
    if new_start != len(m1n1) or len(new_run) != len(run) or candidate[new_end:] != original[end:]:
        raise ValueError("candidate failed structural/unchanged-tail verification")
    if any(candidate[offset:offset + size] != tree for (offset, size), tree in zip(new_run, trees)):
        raise ValueError("candidate DTB run differs from the expected trees")
    return candidate, {"dtb_count": len(run), "replaced_index": index,
                       "other_dtbs_identical": True, "uboot_and_config_identical": True}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache", type=Path, required=True)
    parser.add_argument("--existing-boot", type=Path, required=True, help="explicit copy of current boot.bin")
    parser.add_argument("--output", type=Path, required=True, help="new, uninstalled candidate directory")
    parser.add_argument("--offline", action="store_true")
    args = parser.parse_args()
    if args.output.exists():
        raise ValueError("output directory must be new; existing candidates are not overwritten")
    # No discovery of an ESP, no in-place edits, and no boot arming.
    if args.output.resolve().is_relative_to(Path("/boot")) or args.output.resolve().is_relative_to(Path("/Volumes")):
        raise ValueError("stage the candidate in a work directory, not on a mounted boot volume")
    kernel = asset(args.cache, "kernel", offline=args.offline)
    bootloader = asset(args.cache, "m1n1", offline=args.offline)
    source = asset(args.cache, "m1n1_source", offline=args.offline)
    with tempfile.TemporaryDirectory(prefix="aurora-boot-") as temporary:
        work = Path(temporary)
        extract(kernel, work, ("usr/lib/modules",))
        modules = validate_kernel(work)
        extract(bootloader, work, ("usr/lib/asahi-boot/m1n1.bin", "usr/share/licenses/m1n1-aurora"))
        m1n1 = work / "usr/lib/asahi-boot/m1n1.bin"
        dtb = modules / "dtbs/t6000-j314s.dtb"
        original = args.existing_boot.read_bytes()
        candidate, report = compose(original, m1n1.read_bytes(), dtb.read_bytes())
        args.output.mkdir(parents=True)
        (args.output / "boot.bin.candidate").write_bytes(candidate)
        (args.output / "boot.bin.rollback").write_bytes(original)
        report.update(pins=PINS, original_sha256=sha256(args.existing_boot),
                      candidate_sha256=sha256(args.output / "boot.bin.candidate"),
                      m1n1_sha256=sha256(m1n1), dtb_sha256=sha256(dtb),
                      m1n1_source_archive=str(source),
                      status="STAGED ONLY; fallback-kernel compatibility and J314S/WD22TB4 boot unqualified")
        (args.output / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    print(f"Staged {args.output}; installed boot chain and reboot selection were not changed")


if __name__ == "__main__":
    main()
