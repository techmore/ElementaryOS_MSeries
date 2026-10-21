#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Build both pinned Gravity raw bootloader stages; never deploy or authorize them."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess

COMMIT = 'f02d4a52017915febb222539636b5b025a70407a'
ARTWORK = 'e613a87e526f8fec439c4129e69dd2821b38d258'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--cargo-home', type=Path, required=True)
    parser.add_argument('--jobs', type=int, default=1)
    args = parser.parse_args()
    source = args.source.resolve()
    def git(*options):
        return subprocess.check_output(['git', '-C', str(source), *options], text=True).strip()
    if git('rev-parse', 'HEAD') != COMMIT:
        raise ValueError('bootloader source commit mismatch')
    if git('status', '--porcelain', '--untracked-files=no'):
        raise ValueError('tracked bootloader source must be clean')
    submodule = subprocess.check_output(['git', '-C', str(source / 'artwork'), 'rev-parse', 'HEAD'], text=True).strip()
    if submodule != ARTWORK:
        raise ValueError('artwork submodule mismatch')
    if args.output.exists() or args.jobs < 1:
        raise ValueError('new output and positive jobs required')
    args.output.mkdir(parents=True)
    env = dict(os.environ, CARGO_HOME=str(args.cargo_home.resolve()))
    artifacts = {}
    commands = []
    for stage, chainload in [(2, 0), (1, 1)]:
        command = ['make', '-C', str(source), 'ARCH=', 'RELEASE=1', 'LOGO=',
                   f'CHAINLOADING={chainload}', f'-j{args.jobs}']
        commands.append(command)
        with (args.output / f'stage{stage}.log').open('wb') as log:
            subprocess.run(command, env=env, stdout=log, stderr=subprocess.STDOUT, check=True)
        target = args.output / f'm1n1-stage{stage}.bin'
        shutil.copy2(source / 'build/m1n1.bin', target)
        artifacts[target.name] = hashlib.sha256(target.read_bytes()).hexdigest()
    (args.output / 'receipt.json').write_text(json.dumps({
        'repository': 'GravityLinux/bootloader', 'commit': COMMIT, 'artwork_commit': ARTWORK,
        'commands': commands, 'artifacts': artifacts, 'optional_logo': 'omitted; raw binary target',
        'status': 'source compilation only; no boot authorization, installation or J773g runtime test',
    }, indent=2) + '\n')


if __name__ == '__main__':
    main()
