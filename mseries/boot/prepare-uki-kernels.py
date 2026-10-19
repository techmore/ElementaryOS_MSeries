#!/usr/bin/env python3
"""Unwrap distribution EFI kernel containers before mkosi builds the factory UKI.

Ubuntu ARM64's vmlinuz may itself contain a .linux section and relocatable EFI
wrapper. A systemd UKI must embed the actual Linux EFI payload, not that wrapper.
Run only inside the image tree; retain the original bytes and provenance.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import struct


def pe_sections(data):
    if not data.startswith(b'MZ'):
        return None
    if len(data) < 64:
        raise ValueError('Truncated EFI kernel header')
    offset = struct.unpack_from('<I', data, 60)[0]
    if offset + 24 > len(data) or data[offset:offset + 4] != b'PE\0\0':
        raise ValueError('Invalid EFI kernel PE header')
    machine, count = struct.unpack_from('<HH', data, offset + 4)
    opt_size = struct.unpack_from('<H', data, offset + 20)[0]
    opt = offset + 24
    if machine != 0xAA64 or opt_size < 160 or opt + opt_size + 40 * count > len(data):
        raise ValueError('Expected a complete ARM64 PE kernel')
    if struct.unpack_from('<H', data, opt)[0] != 0x20B:
        raise ValueError('Expected PE32+ kernel')
    sections = {}
    for index in range(count):
        section = opt + opt_size + index * 40
        name = data[section:section + 8].rstrip(b'\0').decode('ascii')
        virtual_size, _, raw_size, raw_offset = struct.unpack_from('<IIII', data, section + 8)
        if raw_offset + raw_size > len(data) or virtual_size > raw_size:
            # BSS is permitted, but cannot be used as an embedded file.
            if name == '.linux':
                raise ValueError('Truncated embedded Linux payload')
            continue
        sections[name] = data[raw_offset:raw_offset + virtual_size]
    relocation_size = struct.unpack_from('<I', data, opt + 112 + 5 * 8 + 4)[0]
    return sections, relocation_size


def inner_kernel(data):
    parsed = pe_sections(data)
    if parsed is None or '.linux' not in parsed[0] or '.osrel' in parsed[0]:
        return None
    sections, _ = parsed
    if any(sections.get(name, b'').rstrip(b'\0') for name in ('.initrd', '.cmdline')):
        raise ValueError('Refusing to discard a distribution initrd or command line')
    inner = sections['.linux']
    parsed_inner = pe_sections(inner)
    if parsed_inner is None or '.linux' in parsed_inner[0] or parsed_inner[1] != 0:
        raise ValueError('Embedded kernel is not a directly loadable ARM64 Linux EFI image')
    return inner


def prepare(root):
    root = Path(root).resolve()
    for candidate in sorted((root / 'usr/lib/modules').glob('*/vmlinuz*')):
        path = candidate
        for _ in range(8):
            if not path.is_symlink():
                break
            target = path.readlink()
            path = root / str(target).lstrip('/') if target.is_absolute() else path.parent / target
        path = path.resolve()
        if not path.is_relative_to(root):
            raise ValueError('Kernel symlink escapes image root')
        data = path.read_bytes()
        inner = inner_kernel(data)
        if inner is None:
            continue
        version = candidate.parent.name
        doc = root / 'usr/share/doc/mseries-kernel-inputs' / version
        doc.mkdir(parents=True, exist_ok=True)
        original = doc / 'distribution-wrapper.efi'
        if original.exists() and original.read_bytes() != data:
            raise ValueError('Conflicting original kernel wrapper')
        original.write_bytes(data)
        (doc / 'SOURCE.json').write_text(json.dumps({
            'input': '/' + str(candidate.relative_to(root)),
            'original_sha256': hashlib.sha256(data).hexdigest(),
            'linux_sha256': hashlib.sha256(inner).hexdigest(),
            'operation': 'Embed the .linux EFI payload in the factory UKI; original wrapper retained.'
        }, indent=2) + '\n')
        temp = path.with_name(path.name + '.mseries-inner')
        temp.write_bytes(inner)
        temp.chmod(path.stat().st_mode & 0o777)
        os.replace(temp, path)
        print(f'Factory UKI: unwrapped {version} ({len(data)} -> {len(inner)} bytes)')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', default='/')
    prepare(parser.parse_args().root)
