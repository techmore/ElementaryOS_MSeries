#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Assemble pinned J773g research boot artifacts in a new directory; never deploy.

Format reference: GravityLinux/scripts@12418e50125a72749a75917db578db55ea42704c,
update-m1n1. Stage 2 + board DTB + gzip(U-Boot); stage 1 remains separate.
Loader firmware/memory fixups and macOS authorization remain untested.
"""
import argparse
import gzip
import hashlib
import json
from pathlib import Path
import subprocess

HERE = Path(__file__).resolve().parent
DTB_KEY = 'arch/arm64/boot/dts/apple/t8132-j773g.dtb'


def sha(data):
    return hashlib.sha256(data).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bootloader', type=Path, required=True, help='corrected verified stage output directory')
    parser.add_argument('--u-boot', type=Path, required=True)
    parser.add_argument('--dtb', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise ValueError('new output directory required')
    loader = json.loads((HERE / 'receipts/2026-10-21-gravity-bootloader-nodisplay.json').read_text())
    uboot = json.loads((HERE / 'receipts/2026-10-21-gravity-uboot-wrapper.json').read_text())
    kernel = json.loads((HERE / 'receipts/2026-10-21-gravity-kernel-build.json').read_text())
    inputs = {
        'stage1': (args.bootloader / 'm1n1-stage1.bin', loader['artifacts']['m1n1-stage1.bin']),
        'stage2': (args.bootloader / 'm1n1-stage2.bin', loader['artifacts']['m1n1-stage2.bin']),
        'dtb': (args.dtb, kernel['artifacts'][DTB_KEY]),
        'u-boot': (args.u_boot, uboot['artifacts']['u-boot-nodtb.bin']),
    }
    payloads = {}
    for name, (path, expected) in inputs.items():
        data = path.read_bytes()
        if sha(data) != expected:
            raise ValueError('verified pinned artifact required: ' + name)
        payloads[name] = data
    dtb = payloads['dtb']
    if dtb[:4] != bytes.fromhex('d00dfeed') or int.from_bytes(dtb[4:8], 'big') != len(dtb):
        raise ValueError('exact complete flattened board tree required')
    compatible = subprocess.check_output(['fdtget', '-t', 's', str(args.dtb), '/', 'compatible'], text=True).split()
    if compatible != ['apple,j773g', 'apple,t8132', 'apple,arm-platform']:
        raise ValueError('J773g board identity mismatch')
    # mtime=0 and filename absent make gzip metadata deterministic.
    compressed = gzip.compress(payloads['u-boot'], mtime=0)
    bundle = payloads['stage2'] + dtb + compressed
    args.output.mkdir(parents=True)
    marker = args.output / 'INCOMPLETE'
    marker.touch()
    (args.output / 'boot.bin').write_bytes(bundle)
    (args.output / 'm1n1-stage1.bin').write_bytes(payloads['stage1'])
    # Read back component boundaries, not only the final aggregate hash.
    actual = (args.output / 'boot.bin').read_bytes()
    boundary = len(payloads['stage2'])
    end = boundary + len(dtb)
    if (actual[:boundary] != payloads['stage2'] or actual[boundary:end] != dtb
            or gzip.decompress(actual[end:]) != payloads['u-boot']):
        raise ValueError('assembled component readback mismatch')
    receipt = {
        'scope': 'pinned J773g boot-chain byte assembly and readback only',
        'format_reference': 'GravityLinux/scripts@12418e50125a72749a75917db578db55ea42704c:update-m1n1',
        'inputs': {name: {'sha256': sha(data), 'bytes': len(data)} for name, data in payloads.items()},
        'boot_bin_sha256': sha(actual), 'boot_bin_bytes': len(actual),
        'offsets': {'stage2': 0, 'j773g_dtb': boundary, 'gzip_uboot': end},
        'component_readback': 'exact stage2/DTB bytes and decompressed U-Boot match',
        'configuration': 'NO_DISPLAY; no appended config overrides',
        'stage1': 'separate artifact; not concatenated or authorized',
        'source_dtb': 'loader fixups still required; not an observed firmware/memory map',
        'factory_promotion': False, 'installer_admission': False,
        'esp_written': False, 'hardware_validated': False,
    }
    (args.output / 'receipt.json').write_text(json.dumps(receipt, indent=2) + '\n')
    marker.unlink()
    print('Pinned research boot-chain assembled and read back; no ESP or macOS boot changes')


if __name__ == '__main__':
    main()
