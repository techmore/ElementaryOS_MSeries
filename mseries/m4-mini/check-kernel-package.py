#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Inspect a fresh M4 research kernel package against its own build receipts."""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import subprocess
import tempfile

COMMIT = '4fc326f6c25ccceb7515e2635c22e01fde5d3bac'
SOURCE_SHA = '045c64540fa4210394c899cad6320c5bf9090a66919938d986aeaad0033946e8'
RELEASE = '7.1.13-elementary-m4-gravity1'
MODULES = ['drivers/gpu/drm/asahi/asahi_m4.ko', 'drivers/gpu/drm/apple/appledrm.ko',
           'drivers/net/ethernet/aquantia/atlantic/atlantic.ko', 'drivers/net/ethernet/broadcom/tg3.ko']


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--package', type=Path, required=True)
    parser.add_argument('--package-receipt', type=Path, required=True)
    parser.add_argument('--build-receipt', type=Path, required=True)
    parser.add_argument('--receipt', type=Path, required=True)
    args = parser.parse_args()
    if args.receipt.exists():
        raise ValueError('new receipt required')
    build = json.loads(args.build_receipt.read_text())
    package = json.loads(args.package_receipt.read_text())
    if build['commit'] != COMMIT or build['source_archive_sha256'] != SOURCE_SHA:
        raise ValueError('pinned source build receipt required')
    if digest(args.package) != package['package_sha256']:
        raise ValueError('package differs from packaging receipt')
    fields = subprocess.check_output(['dpkg-deb', '-f', str(args.package), 'Package', 'Version', 'Architecture'], text=True)
    rows = fields.splitlines()
    if (len(rows) != 3 or rows[0] != 'Package: linux-image-elementary-m4-gravity1'
            or rows[2] != 'Architecture: arm64' or rows[1] not in [
                'Version: 7.1.13+elementary.m4.gravity1-2', 'Version: 7.1.13+elementary.m4.gravity1-3',
                'Version: 7.1.13+elementary.m4.gravity1-4']):
        raise ValueError('unexpected package identity')
    version = rows[1].removeprefix('Version: ')
    versions = json.loads((Path(__file__).parent / 'gravity/compatibility/package-versions.json').read_text())
    if version in versions and build.get('compatibility_patches') != versions[version]:
        raise ValueError('package version requires its exact reviewed scheduler compatibility patches')
    with tempfile.TemporaryDirectory(prefix='m4-kernel-check-', dir=args.package.resolve().parent) as temp:
        root = Path(temp)
        subprocess.run(['dpkg-deb', '--extract', str(args.package), str(root)], check=True)
        module_root = root / 'usr/lib/modules' / RELEASE
        image = module_root / 'vmlinuz'
        if digest(image) != build['artifacts']['arch/arm64/boot/Image']:
            raise ValueError('Image mismatch')
        with image.open('rb') as stream:
            header = stream.read(64)
        if header[56:60] != b'ARM\x64' or ((struct.unpack_from('<Q', header, 24)[0] >> 1) & 3) != 2:
            raise ValueError('ARM64 16 KiB Image required')
        if digest(module_root / ('config-' + RELEASE)) != build['config_sha256']:
            raise ValueError('kernel config mismatch')
        dtb = module_root / 'dtbs/t8132-j773g.dtb'
        if digest(dtb) != build['artifacts']['arch/arm64/boot/dts/apple/t8132-j773g.dtb']:
            raise ValueError('DTB mismatch')
        compatible = subprocess.check_output(['fdtget', '-t', 's', str(dtb), '/', 'compatible'], text=True)
        if 'apple,j773g' not in compatible.split():
            raise ValueError('J773g board DTB required')
        count = len(list(module_root.rglob('*.ko')))
        if count != 1598:
            raise ValueError('unexpected module count')
        for name in MODULES:
            module = module_root / 'kernel' / name
            with module.open('rb') as stream:
                elf = stream.read(20)
            if elf[:6] != b'\x7fELF\x02\x01' or struct.unpack_from('<H', elf, 18)[0] != 183:
                raise ValueError('AArch64 module required: ' + name)
            vermagic = subprocess.check_output(['modinfo', '-F', 'vermagic', str(module)], text=True)
            if vermagic.split()[0] != RELEASE:
                raise ValueError('module release mismatch')
        for name in ['asahi_m4', 'appledrm', 'atlantic', 'tg3']:
            result = subprocess.check_output(['modprobe', '-d', str(root / 'usr'), '-S', RELEASE,
                                              '--show-depends', name], text=True)
            if 'insmod ' not in result:
                raise ValueError('unresolved module: ' + name)
        subprocess.run(['dpkg-deb', '--control', str(args.package), str(root / 'control')], check=True)
        if {p.name for p in (root / 'control').iterdir()} - {'control', 'md5sums'}:
            raise ValueError('research kernel must have no maintainer scripts or triggers')
    args.receipt.write_text(json.dumps({
        'source_commit': COMMIT, 'package_sha256': package['package_sha256'],
        'package_version': rows[1].removeprefix('Version: '),
        'compatibility_patches': build.get('compatibility_patches', {}),
        'module_count': count, 'checks': 'Image/config/DTB hashes, 16 KiB header, J773g, ELF/vermagic, module dependencies, no package hooks',
        'scope': 'fresh candidate package inspection; no boot or hardware tests',
        'factory_promotion': False, 'hardware_validated': False,
    }, indent=2) + '\n')
    print('M4 candidate package checks passed; no factory promotion or hardware qualification')


if __name__ == '__main__':
    main()
