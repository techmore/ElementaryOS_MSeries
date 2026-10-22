#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Build the pinned Gravity mini research kernel in a new work directory."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tarfile

HERE = Path(__file__).resolve().parent
ARCHIVE_SHA256 = '045c64540fa4210394c899cad6320c5bf9090a66919938d986aeaad0033946e8'
COMMIT = '4fc326f6c25ccceb7515e2635c22e01fde5d3bac'
RELEASE = '7.1.13-elementary-m4-gravity1'


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def packaging_patches():
    directory = HERE / 'gravity/patches'
    manifest = json.loads((directory / 'manifest.json').read_text())
    for name, expected in manifest.items():
        path = directory / name
        if Path(name).name != name or digest(path) != expected:
            raise ValueError('Gravity packaging patch checksum mismatch: ' + name)
    return directory, manifest



def compatibility_patches(version=None):
    directory = HERE / 'gravity/compatibility'
    manifest = (json.loads((directory / 'manifest.json').read_text()) if version is None else
                json.loads((directory / 'package-versions.json').read_text())[version])
    for name, expected in manifest.items():
        if Path(name).name != name or digest(directory / name) != expected:
            raise ValueError('elementary compatibility patch checksum mismatch')
    return directory, manifest


def source_patch_gate(source, compatibility_version=None):
    expected = json.loads((HERE / 'gravity/patches/resulting-files.json').read_text())
    directory = HERE / 'gravity/compatibility'
    compatibility = (json.loads((directory / 'resulting-files.json').read_text()) if compatibility_version is None else
                     json.loads((directory / 'resulting-files-by-version.json').read_text())[compatibility_version])
    expected.update(compatibility)
    for name, value in expected.items():
        if digest(source / name) != value:
            raise ValueError('matched ARM64 packaging exports required: ' + name)


def config_gate(path):
    values = dict(line.split('=', 1) for line in path.read_text().splitlines()
                  if line.startswith('CONFIG_') and '=' in line)
    for key, value in {'CONFIG_ARM64_16K_PAGES': 'y', 'CONFIG_DRM_ASAHI_M4': 'm',
                       'CONFIG_RUST': 'y', 'CONFIG_DRM_APPLE': 'm',
                       'CONFIG_AQTION': 'm', 'CONFIG_TIGON3': 'm',
                       'CONFIG_LOCALVERSION': '"-elementary-m4-gravity1"'}.items():
        if values.get(key) != value:
            raise ValueError(f'resolved configuration must have {key}={value}')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archive', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--rust-library', type=Path, required=True)
    parser.add_argument('--jobs', type=int, default=2)
    args = parser.parse_args()
    if args.jobs < 1 or args.output.exists():
        raise ValueError('positive jobs and a new output directory required')
    if digest(args.archive) != ARCHIVE_SHA256:
        raise ValueError('Gravity source archive checksum mismatch')
    if not (args.rust_library / 'core/src/lib.rs').is_file():
        raise ValueError('matching Rust library sources required')
    root = args.output.resolve()
    root.mkdir(parents=True)
    source, build = root / ('linux-' + COMMIT), root / 'build'
    with tarfile.open(args.archive) as archive:
        if any(Path(member.name).parts[0] != 'linux-' + COMMIT for member in archive):
            raise ValueError('unexpected archive root')
        archive.extractall(root, filter='data')
    patch_directory, patches = packaging_patches()
    for name in patches:
        subprocess.run(['patch', '--batch', '--fuzz=0', '-p1', '-d', str(source),
                        '-i', str(patch_directory / name)], check=True)
    compatibility_directory, compatibility = compatibility_patches()
    for name in compatibility:
        subprocess.run(['patch', '--batch', '--fuzz=0', '-p1', '-d', str(source),
                        '-i', str(compatibility_directory / name)], check=True)
    source_patch_gate(source)
    build.mkdir()
    env = dict(os.environ, RUST_LIB_SRC=str(args.rust_library.resolve()))
    base = ['make', '-C', str(source), f'O={build}', 'ARCH=arm64',
            'CC=clang', 'LD=ld', 'HOSTCC=clang']
    def run(command):
        with (root / 'build.log').open('ab') as log:
            subprocess.run(command, env=env, stdout=log, stderr=subprocess.STDOUT, check=True)
    run(base + ['defconfig', 'asahi.config'])
    run([str(source / 'scripts/kconfig/merge_config.sh'), '-m', '-O', str(build),
         str(build / '.config'), str(HERE / 'gravity/gravity.config'),
         str(HERE / 'gravity/gravity-aarch64.config'),
         str(HERE / 'gravity/elementary-target.config')])
    run([str(source / 'scripts/config'), '--file', str(build / '.config'),
         '--set-str', 'LOCALVERSION', '-elementary-m4-gravity1', '--disable', 'LOCALVERSION_AUTO'])
    run(base + ['olddefconfig'])
    config_gate(build / '.config')
    run(base + [f'-j{args.jobs}', 'Image', 'modules', 'dtbs'])
    artifacts = ['arch/arm64/boot/Image', 'drivers/gpu/drm/asahi/asahi_m4.ko',
                 'arch/arm64/boot/dts/apple/t8132-j773g.dtb',
                 'drivers/net/ethernet/aquantia/atlantic/atlantic.ko',
                 'drivers/net/ethernet/broadcom/tg3.ko']
    hashes = {path: digest(build / path) for path in artifacts}
    receipt = {'repository': 'GravityLinux/linux', 'commit': COMMIT,
               'source_archive_sha256': ARCHIVE_SHA256, 'kernel_release': RELEASE,
               'config_sha256': digest(build / '.config'), 'artifacts': hashes,
               'packaging_patches': patches, 'compatibility_patches': compatibility,
               'status': 'source build only; no installation or J773g hardware qualification'}
    (root / 'receipt.json').write_text(json.dumps(receipt, indent=2) + '\n')


if __name__ == '__main__':
    main()
