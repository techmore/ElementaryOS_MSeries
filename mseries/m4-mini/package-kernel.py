#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Package a completed Gravity research kernel as a Debian payload; never install."""
import argparse
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import tempfile

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('m4_kernel', HERE / 'build-kernel.py')
kernel = importlib.util.module_from_spec(spec)
spec.loader.exec_module(kernel)
NAME = 'linux-image-elementary-m4-gravity1'
VERSION = '7.1.13+elementary.m4.gravity1-4'


def check(build, archive):
    if kernel.digest(archive) != kernel.ARCHIVE_SHA256:
        raise ValueError('corresponding source archive mismatch')
    kernel.config_gate(build / '.config')
    release = (build / 'include/config/kernel.release').read_text().strip()
    if release != kernel.RELEASE:
        raise ValueError('unexpected module release: ' + release)
    required = ['arch/arm64/boot/Image', 'arch/arm64/boot/dts/apple/t8132-j773g.dtb',
                'drivers/gpu/drm/asahi/asahi_m4.ko', 'Module.symvers', 'modules.order',
                'drivers/net/ethernet/aquantia/atlantic/atlantic.ko',
                'drivers/net/ethernet/broadcom/tg3.ko']
    for path in required:
        if not (build / path).is_file():
            raise ValueError('build incomplete: missing ' + path)
    modules = (build / 'modules.order').read_text().splitlines()
    if not modules:
        raise ValueError('empty module inventory')
    for name in modules:
        if Path(name).is_absolute() or '..' in Path(name).parts or not (build / name).is_file():
            raise ValueError('missing or invalid module: ' + name)
    for name in ['drivers/gpu/drm/asahi/asahi_m4.ko', 'drivers/gpu/drm/apple/appledrm.ko',
                 'drivers/net/ethernet/aquantia/atlantic/atlantic.ko',
                 'drivers/net/ethernet/broadcom/tg3.ko']:
        version = subprocess.check_output(['modinfo', '-F', 'vermagic', str(build / name)], text=True)
        if version.split()[0] != release:
            raise ValueError('module vermagic mismatch: ' + name)
    return release


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--build', type=Path, required=True)
    parser.add_argument('--archive', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    kernel.source_patch_gate(args.source)
    release = check(args.build, args.archive)
    if args.output.exists():
        raise ValueError('output must be a new directory')
    args.output.mkdir(parents=True)
    with tempfile.TemporaryDirectory(prefix='m4-kernel-package-') as temp:
        payload = Path(temp) / 'payload'
        subprocess.run(['make', '-C', str(args.source.resolve()), f'O={args.build.resolve()}',
                        'ARCH=arm64', 'CC=clang', 'LD=ld', 'HOSTCC=clang',
                        f'INSTALL_MOD_PATH={payload / "usr"}', 'INSTALL_MOD_STRIP=1',
                        'modules_install'], check=True)
        modules = payload / 'usr/lib/modules' / release
        for name in ['build', 'source']:
            (modules / name).unlink(missing_ok=True)
        shutil.copy2(args.build / 'arch/arm64/boot/Image', modules / 'vmlinuz')
        shutil.copy2(args.build / '.config', modules / ('config-' + release))
        (modules / 'dtbs').mkdir()
        shutil.copy2(args.build / 'arch/arm64/boot/dts/apple/t8132-j773g.dtb', modules / 'dtbs')
        subprocess.run(['depmod', '-b', str(payload / 'usr'), release], check=True)
        docs = payload / 'usr/share/doc' / NAME
        docs.mkdir(parents=True)
        shutil.copy2(args.source / 'COPYING', docs)
        shutil.copytree(args.source / 'LICENSES', docs / 'LICENSES')
        shutil.copy2(args.build / '.config', docs / 'build.config')
        shutil.copy2(HERE / 'research.json', docs)
        shutil.copytree(HERE / 'gravity', docs / 'configuration-provenance')
        (docs / 'README').write_text('Research payload only. Matched Gravity bootloader, firmware and Mesa required.\nNo maintainer scripts, boot entries or boot partition writes. No J773g qualification.\n')
        control = payload / 'DEBIAN'
        control.mkdir()
        (control / 'control').write_text(f'Package: {NAME}\nVersion: {VERSION}\nArchitecture: arm64\nMaintainer: ElementaryOS MSeries contributors <builder@localhost>\nDepends: kmod\nSection: kernel\nPriority: optional\nDescription: Experimental M4 Mac mini kernel payload\n No boot hooks; hardware qualification remains open.\n')
        package = args.output / f'{NAME}_{VERSION}_arm64.deb'
        subprocess.run(['dpkg-deb', '-Zzstd', '-z3', '--threads-max=2', '--root-owner-group',
                        '--build', str(payload), str(package)], check=True)
    source_copy = args.output / 'gravity-linux-corresponding-source.tar.gz'
    shutil.copy2(args.archive, source_copy)
    receipt = {'kernel_release': release, 'package': package.name,
               'package_sha256': kernel.digest(package), 'source_sha256': kernel.digest(source_copy),
               'status': 'payload packaged only; not installed or hardware-qualified'}
    (args.output / 'receipt.json').write_text(json.dumps(receipt, indent=2) + '\n')


if __name__ == '__main__':
    main()
