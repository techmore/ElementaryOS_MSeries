#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Build an M4 initramfs inside a configured candidate root; no host boot writes."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tempfile

HERE = Path(__file__).resolve().parent
RELEASE = '7.1.13-elementary-m4-gravity1'
EARLY = {'nvme_apple', 'pcie_apple', 'hid_apple', 'hid_magicmouse'}


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    root = args.root.resolve()
    if root == Path('/') or args.output.exists():
        raise ValueError('isolated root and new output required')
    build = json.loads((HERE / 'receipts/2026-10-21-gravity-kernel-build.json').read_text())
    modules = root / 'usr/lib/modules' / RELEASE
    if digest(modules / 'vmlinuz') != build['artifacts']['arch/arm64/boot/Image']:
        raise ValueError('verified M4 Image required')
    if digest(modules / ('config-' + RELEASE)) != build['config_sha256']:
        raise ValueError('module-local M4 kernel config required')
    early = root / 'usr/share/initramfs-tools/modules.d/elementary-m4'
    if {line.strip() for line in early.read_text().splitlines() if line and not line.startswith('#')} != EARLY:
        raise ValueError('M4 early module policy required')
    args.output.mkdir(parents=True)
    marker = args.output / 'INCOMPLETE'
    marker.touch()
    with tempfile.TemporaryDirectory(prefix='m4-initrd-', dir=root / 'tmp') as scratch:
        inside = '/' + str(Path(scratch).relative_to(root) / 'initrd.img')
        script = ('set -eu\nmount --bind /dev/null "$1/dev/null"\n'
                  'mount -t proc -o ro,nosuid,nodev,noexec proc "$1/proc"\n'
                  'exec chroot "$1" /usr/bin/env -i PATH=/usr/sbin:/usr/bin:/sbin:/bin LC_ALL=C '
                  'mkinitramfs -o "$2" "$3"')
        command = ['unshare', '--user', '--map-auto', '--map-root-user', '--mount', '--pid', '--fork',
                   '/bin/sh', '-c', script, 'm4-initrd', str(root), inside, RELEASE]
        log = args.output / 'build.log'
        with log.open('wb') as stream:
            subprocess.run(command, stdout=stream, stderr=subprocess.STDOUT, check=True)
        image = args.output / ('initrd-' + RELEASE + '.img')
        shutil.copy2(Path(scratch) / 'initrd.img', image)
    inventory = subprocess.check_output(['lsinitramfs', str(image)], text=True).splitlines()
    required = ['init', 'conf/modules'] + ['usr/lib/modules/' + RELEASE + '/kernel/' + path for path in [
        'drivers/nvme/host/nvme-apple.ko', 'drivers/pci/controller/pcie-apple.ko',
        'drivers/hid/hid-apple.ko', 'drivers/hid/hid-magicmouse.ko']]
    if not set(required).issubset(inventory):
        raise ValueError('required initramfs contents missing')
    with tempfile.TemporaryDirectory(prefix='m4-initrd-inspect-') as temp:
        subprocess.run(['unmkinitramfs', str(image), temp], check=True)
        candidates = list(Path(temp).rglob('conf/modules'))
        if len(candidates) != 1 or not EARLY.issubset({line.strip() for line in candidates[0].read_text().splitlines()}):
            raise ValueError('early module load list missing')
    warnings = [line for line in log.read_text().splitlines() if line.startswith('W:')]
    (args.output / 'receipt.json').write_text(json.dumps({
        'kernel_release': RELEASE, 'initramfs_sha256': digest(image), 'members': len(inventory),
        'early_modules': sorted(EARLY), 'required_contents': required, 'warnings': warnings,
        'status': 'configured-root initramfs built and inspected; missing firmware/runtime qualification remain',
        'hardware_validated': False,
    }, indent=2) + '\n')
    marker.unlink()


if __name__ == '__main__':
    main()
