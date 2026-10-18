#!/usr/bin/env python3
"""Reject incomplete factory browser payloads before publishing an image."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess


def verify(root, check_libraries=False):
    root = Path(root)
    runtime = root / 'usr/lib/mseries-brave'
    doc = root / 'usr/share/doc/mseries-brave'
    pin = json.loads((doc / 'pin.json').read_text())
    files = json.loads((doc / 'files.json').read_text())
    required = {'brave', 'chrome-sandbox', 'icudtl.dat', 'resources.pak',
                'brave_resources.pak', 'v8_context_snapshot.bin', 'locales/en-US.pak', 'LICENSE'}
    if not required <= files.keys() or pin['architecture'] != 'arm64':
        raise ValueError('Incomplete ARM64 Brave manifest')
    for name, expected in files.items():
        path = runtime / name
        if Path(name).is_absolute() or '..' in Path(name).parts:
            raise ValueError('Invalid Brave manifest path')
        with path.open('rb') as stream:
            actual = hashlib.file_digest(stream, 'sha256').hexdigest()
        if actual != expected:
            raise ValueError('Brave payload changed: ' + name)
    with (runtime / 'brave').open('rb') as stream:
        elf = stream.read(20)
    if elf[:6] != b'\x7fELF\x02\x01' or int.from_bytes(elf[18:20], 'little') != 183:
        raise ValueError('Brave binary is not ARM64 ELF')
    if not (runtime / 'brave').stat().st_mode & 0o111:
        raise ValueError('Brave binary is not executable')
    if check_libraries:
        output = subprocess.check_output(['ldd', str(runtime / 'brave')], text=True, stderr=subprocess.STDOUT)
        if 'not found' in output:
            raise ValueError('Brave runtime library missing:\n' + output)
    print('Factory Brave ' + pin['version'] + ': payload verified')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', default='/')
    parser.add_argument('--ldd', action='store_true')
    args = parser.parse_args()
    verify(args.root, args.ldd)
