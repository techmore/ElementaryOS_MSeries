#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Build pinned Gravity M4 U-Boot as a separate research candidate; never deploy."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tarfile

COMMIT = 'a2f6913694ff26908c16948af3f8372429782263'
ARCHIVE_SHA256 = '6adaf60d20f5f53792eefeaf662dbbd481d7d225d5938c80f6379800b685fd6c'


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archive', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--jobs', type=int, default=2)
    args = parser.parse_args()
    if digest(args.archive) != ARCHIVE_SHA256:
        raise ValueError('pinned Gravity U-Boot archive required')
    if args.output.exists() or args.jobs < 1:
        raise ValueError('new output and positive job count required')
    args.output.mkdir(parents=True)
    marker = args.output / 'INCOMPLETE'
    marker.touch()
    with tarfile.open(args.archive) as archive:
        members = archive.getmembers()
        if not members or any(Path(member.name).parts[0] != 'u-boot-' + COMMIT for member in members):
            raise ValueError('unexpected U-Boot source root')
        epoch = int(members[0].mtime)
        archive.extractall(args.output, filter='data')
    source = (args.output / ('u-boot-' + COMMIT)).resolve()
    build = (args.output / 'build').resolve()
    env = dict(os.environ, SOURCE_DATE_EPOCH=str(epoch), TZ='UTC', LC_ALL='C')
    commands = [
        ['make', '-C', str(source), 'O=' + str(build), 'apple_m1_defconfig'],
        ['make', '-C', str(source), 'O=' + str(build), 'LOCALVERSION=-gravity-a2f6913', '-j' + str(args.jobs)],
    ]
    for index, command in enumerate(commands):
        with (args.output / f'{index}.log').open('wb') as log:
            subprocess.run(command, env=env, stdout=log, stderr=subprocess.STDOUT, check=True)
    artifacts = {}
    for name in ['u-boot-nodtb.bin', 'u-boot.bin', '.config']:
        shutil.copy2(build / name, args.output / name)
        artifacts[name] = digest(args.output / name)
    config = (build / '.config').read_text().splitlines()
    for required in ['CONFIG_ARM64=y', 'CONFIG_ARCH_APPLE=y', 'CONFIG_EFI_LOADER=y']:
        if required not in config:
            raise ValueError('required Apple ARM64 EFI setting missing: ' + required)
    elf = subprocess.check_output(['readelf', '-h', str(build / 'u-boot')], text=True)
    if 'AArch64' not in elf:
        raise ValueError('native ARM64 U-Boot artifact required')
    (args.output / 'receipt.json').write_text(json.dumps({
        'repository': 'GravityLinux/u-boot', 'branch': 'gravity-alpha-20260925',
        'commit': COMMIT, 'archive_sha256': ARCHIVE_SHA256,
        'source_date_epoch': epoch, 'configuration': 'apple_m1_defconfig',
        'localversion': '-gravity-a2f6913', 'commands': commands,
        'artifacts': artifacts, 'elf_machine': 'AArch64',
        'compiler': subprocess.check_output(['gcc', '--version'], text=True).splitlines()[0],
        'scope': 'pinned-source candidate compilation/configuration only; no firmware handoff',
        'factory_promotion': False, 'hardware_validated': False}, indent=2) + '\n')
    marker.unlink()
    print('Pinned Gravity M4 U-Boot candidate built; no deployment or hardware qualification')


if __name__ == '__main__':
    main()
