#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Inspect and software-test an unpromoted private Mesa candidate; never install."""
import argparse
import importlib.util
import hashlib
import json
from pathlib import Path
import struct
import subprocess
import tempfile

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('mesa_compatibility', HERE / 'mesa-compatibility.py')
compatibility = importlib.util.module_from_spec(spec)
spec.loader.exec_module(compatibility)

COMMIT = '87ac51d411f0e58a9433567ec2666f457be89e1d'
SOURCE_SHA = '1195f212bcf5816b8b893113b0b5dc578ce744d420856b6ad4f42008889e231e'
LIBRARIES = {'lib/libvulkan_asahi.so', 'lib/libgallium-26.3.0-devel.so',
             'lib/libEGL_mesa.so.0.0.0', 'lib/libGLX_mesa.so.0.0.0'}


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--package', type=Path, required=True)
    parser.add_argument('--package-receipt', type=Path, required=True)
    parser.add_argument('--build-receipt', type=Path, required=True)
    parser.add_argument('--smoke', type=Path, required=True)
    parser.add_argument('--receipt', type=Path, required=True)
    args = parser.parse_args()
    if args.receipt.exists():
        raise ValueError('new receipt required')
    build = json.loads(args.build_receipt.read_text())
    package = json.loads(args.package_receipt.read_text())
    source_sha = build.get('archive_sha256', build.get('source_archive_sha256'))
    if (build['commit'] != COMMIT or source_sha != SOURCE_SHA or build['build'] != 'passed'
            or build['tests']['meson_groups'] != 5 or build['tests']['failed_groups']):
        raise ValueError('matching source build and five passing test groups required')
    if package['source_archive_sha256'] != SOURCE_SHA or digest(args.package) != package['package_sha256']:
        raise ValueError('package/source receipt mismatch')
    if set(build['artifacts']) != LIBRARIES:
        raise ValueError('all four validated graphics libraries required')
    fields = subprocess.check_output(['dpkg-deb', '-f', str(args.package), 'Package', 'Version', 'Architecture'], text=True)
    rows = fields.splitlines()
    if len(rows) != 3 or rows[0] != 'Package: elementary-m4-gravity-mesa1' or rows[2] != 'Architecture: arm64':
        raise ValueError('unexpected package identity')
    version = rows[1].removeprefix('Version: ')
    selected = compatibility.metadata(version, build, package)
    if package['package'] != args.package.name:
        raise ValueError('package basename differs from receipt')
    bundle = package.get('compatibility_source_archive')
    if selected['patches']:
        if (not isinstance(bundle, dict) or bundle.get('file') != compatibility.BUNDLE_NAME or
                digest(args.package.parent / bundle['file']) != bundle['sha256']):
            raise ValueError('compatibility corresponding source missing or changed')
        compatibility.verify_source_bundle(args.package.parent / bundle['file'], version)
    elif bundle is not None:
        raise ValueError('unexpected compatibility sources for historical package')
    with tempfile.TemporaryDirectory(prefix='m4-mesa-check-', dir=args.package.resolve().parent) as temp:
        root = Path(temp)
        subprocess.run(['dpkg-deb', '--extract', str(args.package), str(root)], check=True)
        prefix = root / 'usr/lib/elementary-m4-gravity1'
        if bundle:
            docs = root / 'usr/share/doc/elementary-m4-gravity-mesa1'
            if digest(docs / bundle['file']) != bundle['sha256']:
                raise ValueError('installed corresponding-source bundle differs')
            if set(build['supplemental_test_receipts']) != {'helper-divergence', 'rodata-upload'}:
                raise ValueError('supplemental test provenance missing')
            for name, expected in build['supplemental_test_receipts'].items():
                if digest(docs / 'supplemental-tests' / (name + '.json')) != expected:
                    raise ValueError('installed supplemental test receipt differs')
        for name, expected in build['artifacts'].items():
            library = prefix / name
            if digest(library) != expected:
                raise ValueError('library differs from build: ' + name)
            with library.open('rb') as stream:
                elf = stream.read(20)
            if elf[:6] != b'\x7fELF\x02\x01' or struct.unpack_from('<H', elf, 18)[0] != 183:
                raise ValueError('AArch64 library required')
        if (root / 'opt/elementary-m4-gravity1').readlink() != Path('/usr/lib/elementary-m4-gravity1'):
            raise ValueError('persistent prefix compatibility link required')
        policy = (root / 'usr/lib/tmpfiles.d/elementary-m4-mesa.conf').read_text()
        if 'L /opt/elementary-m4-gravity1 - - - - /usr/lib/elementary-m4-gravity1' not in policy:
            raise ValueError('factory /usr retention policy missing')
        subprocess.run(['dpkg-deb', '--control', str(args.package), str(root / 'control')], check=True)
        if {p.name for p in (root / 'control').iterdir()} - {'control', 'md5sums'}:
            raise ValueError('research Mesa must have no maintainer scripts or triggers')
        smoke = subprocess.check_output([str(prefix / 'bin/run-mesa'), '--software', '--',
                                         str(args.smoke.resolve())], text=True, stderr=subprocess.STDOUT)
        if 'llvmpipe' not in smoke or 'Mesa 26.3.0-devel' not in smoke:
            raise ValueError('matched private software renderer was not selected: ' + smoke)
    args.receipt.write_text(json.dumps({
        'source_commit': COMMIT, 'package_sha256': package['package_sha256'],
        'package_version': version, 'compatibility_patches': selected['patches'],
        'patched_sources_sha256': selected['patched_sources_sha256'], 'corresponding_compatibility_source': bundle,
        'libraries': 'four hashes/ARM64 ELF checks pass', 'test_groups': 5,
        'persistent_prefix': 'usr payload, compatibility symlink and vendor tmpfiles verified',
        'software_rendering': smoke.strip(), 'package_hooks': 'absent',
        'factory_promotion': False, 'hardware_validated': False, 'vulkan_conformance_tested': False,
    }, indent=2) + '\n')
    print('Mesa candidate package/hash/retention/software checks passed; no factory promotion or GPU qualification')


if __name__ == '__main__':
    main()
