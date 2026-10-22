#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Pass receipt-selected hosted package names to the existing semantic checker.

The retrieved workspace must already pass fetch-hosted-candidates.py provenance
and payload checks. This does not select a run or relax package/version gates.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys

HERE = Path(__file__).resolve().parent
PREFIXES = {'kernel': 'linux-image-elementary-m4-gravity1_',
            'mesa': 'elementary-m4-gravity-mesa1_'}


def package(directory, kind):
    receipt = json.loads((directory / 'receipt.json').read_text())
    name = receipt['package']
    if (not isinstance(name, str) or Path(name).name != name or
            not name.startswith(PREFIXES[kind]) or not name.endswith('_arm64.deb') or
            '\\' in name):
        raise ValueError('expected component package basename required: ' + kind)
    if {p.name for p in directory.glob('*.deb')} != {name}:
        raise ValueError('exactly the receipt-selected component package required: ' + kind)
    path = directory / name
    if path.is_symlink() or not path.is_file():
        raise ValueError('regular component package required')
    with path.open('rb') as stream:
        if hashlib.file_digest(stream, 'sha256').hexdigest() != receipt['package_sha256']:
            raise ValueError('receipt-selected package hash mismatch: ' + kind)
    return path


def command(retrieved, output):
    kernel = retrieved / 'kernel'
    mesa = retrieved / 'mesa'
    return [sys.executable, str(HERE / 'prepare-image-inputs.py'),
            '--kernel', str(package(kernel, 'kernel')),
            '--kernel-package-receipt', str(kernel / 'receipt.json'),
            '--kernel-build-receipt', str(kernel / 'build-receipt.json'),
            '--mesa', str(package(mesa, 'mesa')),
            '--mesa-package-receipt', str(mesa / 'receipt.json'),
            '--mesa-build-receipt', str(mesa / 'build-receipt.json'),
            '--smoke', str(mesa / 'mesa-software'), '--output', str(output)]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--retrieved', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    subprocess.run(command(args.retrieved.resolve(), args.output.resolve()), check=True)


if __name__ == '__main__':
    main()
