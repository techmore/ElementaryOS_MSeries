#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Compile captured J773g research DT sources; no installation or boot arming."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess


def build(capture, output, source_name="asahi-mini"):
    receipt = json.loads((capture / 'receipt.json').read_text())
    if (capture / 'INCOMPLETE').exists():
        raise ValueError('incomplete capture')
    expected = json.loads((Path(__file__).parent / 'research.json').read_text())
    if receipt['profile'] != expected:
        raise ValueError('capture does not match the checked-in source profile')
    entries = {item['path']: item for item in receipt['files']}
    source = next(s for s in expected['sources'] if s['name'] == source_name)
    for name in source['files']:
        path = source_name + '/' + name
        if hashlib.sha256((capture / path).read_bytes()).hexdigest() != entries[path]['sha256']:
            raise ValueError('captured source hash mismatch: ' + path)
    if output.exists():
        raise ValueError('output must be new')
    output.mkdir(parents=True)
    root = capture / source_name
    commands = [
        ['cpp', '-nostdinc', '-undef', '-D__DTS__', '-x', 'assembler-with-cpp',
         '-I', str(root / 'include'), str(root / 'arch/arm64/boot/dts/apple/t8132-j773g.dts')],
        ['dtc', '-I', 'dts', '-O', 'dtb', '-o', str(output / 't8132-j773g.dtb'), str(output / 'j773g.dts')],
    ]
    for index, command in enumerate(commands):
        result = subprocess.run(command, capture_output=True)
        (output / f'{index}.stderr').write_bytes(result.stderr)
        if index == 0:
            (output / 'j773g.dts').write_bytes(result.stdout)
        if result.returncode:
            (output / 'INCOMPLETE').write_text('DT compilation failed\n')
            raise RuntimeError(f'command failed: {command[0]}')
    blob = output / 't8132-j773g.dtb'
    (output / 'receipt.json').write_text(json.dumps({
        'source': source, 'commands': commands,
        'capture_receipt_sha256': hashlib.sha256((capture / 'receipt.json').read_bytes()).hexdigest(),
        'dtb_sha256': hashlib.sha256(blob.read_bytes()).hexdigest(),
        'warnings': (output / '1.stderr').read_text(),
        'status': 'DT compilation only; kernel, loader handoff and J773g hardware unqualified',
    }, indent=2) + '\n')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--capture', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--source', choices=['asahi-mini', 'gravity-mini'], default='asahi-mini')
    args = parser.parse_args()
    build(args.capture, args.output, args.source)
    print('Compiled research DTB; consult receipt warnings; do not install as a qualified bundle')
