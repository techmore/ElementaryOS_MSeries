#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Exercise M4 boot.bin FAT/GPT placement in a disposable regular image only.

No loop device, mount, real disk or firmware command is used. This is an image
mechanics fixture, not complete mkosi output or M4 boot qualification.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

HERE = Path(__file__).resolve().parent
VERIFIER = HERE.parent / 'fairydust/debian/verify-m1n1-esp.py'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bundle', type=Path, required=True)
    parser.add_argument('--receipt', type=Path, required=True)
    args = parser.parse_args()
    if args.receipt.exists():
        raise ValueError('new receipt required')
    expected = json.loads((HERE / 'receipts/2026-10-21-repeatable-boot-chain.json').read_text())['boot_bin_sha256']
    if hashlib.sha256(args.bundle.read_bytes()).hexdigest() != expected:
        raise ValueError('verified M4 boot bundle required')
    for command in ['sgdisk', 'mkfs.vfat', 'mmd', 'mcopy', 'sfdisk']:
        if shutil.which(command) is None:
            raise ValueError('missing fixture tool: ' + command)
    with tempfile.TemporaryDirectory(prefix='m4-esp-fixture-') as directory:
        root = Path(directory)
        image = root / 'fixture.raw'
        with image.open('xb') as stream:
            stream.truncate(96 * 1024**2)
        subprocess.run(['sgdisk', '--clear', '--new=1:2048:+64M', '--typecode=1:ef00',
                        '--change-name=1:m4-research-fixture', str(image)], check=True, capture_output=True)
        fat = root / 'esp.fat'
        subprocess.run(['mkfs.vfat', '-F', '32', '-C', str(fat), '65536'], check=True, capture_output=True)
        offset = 2048 * 512
        with image.open('r+b') as target, fat.open('rb') as source:
            target.seek(offset)
            shutil.copyfileobj(source, target)
        fat.unlink()
        device = str(image) + '@@' + str(offset)
        # Ignore per-user mtools configuration; all targets name this fixture.
        env = dict(os.environ, MTOOLSRC='/dev/null')
        subprocess.run(['mmd', '-i', device, '::/m1n1'], env=env, check=True)
        subprocess.run(['mcopy', '-i', device, str(args.bundle.resolve()), '::/m1n1/boot.bin'], env=env, check=True)
        command = [sys.executable, str(VERIFIER), '--image', str(image), '--expected', str(args.bundle.resolve())]
        valid = subprocess.run(command, env=env, text=True, capture_output=True, check=True)
        corrupt = root / 'corrupt.bin'
        corrupt.write_bytes(b'incorrect fixture payload')
        subprocess.run(['mcopy', '-o', '-i', device, str(corrupt), '::/m1n1/boot.bin'], env=env, check=True)
        rejected = subprocess.run(command, env=env, text=True, capture_output=True)
        if rejected.returncode == 0 or 'SHA-256 mismatch' not in rejected.stderr:
            raise ValueError('corrupt ESP file was not rejected by readback verifier')
    args.receipt.write_text(json.dumps({
        'scope': 'disposable GPT/FAT regular-image fixture; not complete factory output',
        'bundle_sha256': expected, 'image_bytes': 96 * 1024**2,
        'esp_offset_bytes': offset, 'esp_bytes': 64 * 1024**2,
        'path': '/m1n1/boot.bin', 'matching_payload': valid.stdout.strip(),
        'corrupted_payload_rejected': True, 'temporary_image_removed': True,
        'block_devices_opened': False, 'host_esp_modified': False,
        'hardware_validated': False, 'complete_factory_image_built': False,
    }, indent=2) + '\n')
    print('M4 FAT/GPT fixture placement/readback passed; corrupt payload rejected')


if __name__ == '__main__':
    main()
