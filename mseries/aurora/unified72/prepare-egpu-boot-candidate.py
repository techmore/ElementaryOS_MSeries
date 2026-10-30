#!/usr/bin/env python3
"""Create an uninstalled J314S boot candidate with only #188's PCI range changes.

This does not establish fallback compatibility, replace /boot, or arm a boot.
"""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import struct

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('swap_dtb', HERE.parents[1] / 'fairydust/usb4/swap-dtb.py')
swap = importlib.util.module_from_spec(spec)
spec.loader.exec_module(swap)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def compose(original):
    start, trees, end = swap.split(original)
    matches = [(off, size) for off, size in trees if b'apple,j314s\0' in original[off:off + size]]
    if len(matches) != 1:
        raise ValueError('expected exactly one J314S DTB')
    offset, size = matches[0]
    old = original[offset:offset + size]
    new = old
    for high in (12, 16, 20):
        before = struct.pack('>7I', 0x43000000, 8, 0, high, 0, 2, 0)
        after = struct.pack('>7I', 0x43000000, high, 0, high, 0, 2, 0)
        if new.count(before) != 1 or new.count(after):
            raise ValueError(f'unexpected or ambiguous tunnel range {high:#x}')
        new = new.replace(before, after)
    if len(new) != len(old) or sum(a != b for a, b in zip(old, new)) != 3:
        raise ValueError('unexpected change to device tree')
    candidate = original[:offset] + new + original[offset + size:]
    new_start, new_trees, new_end = swap.split(candidate)
    if (new_start, new_trees, new_end) != (start, trees, end):
        raise ValueError('candidate boot structure differs')
    if candidate[:offset] != original[:offset] or candidate[offset + size:] != original[offset + size:]:
        raise ValueError('candidate changed data outside target DTB')
    return candidate, {'input_sha256': digest(original), 'candidate_sha256': digest(candidate),
                       'old_dtb_sha256': digest(old), 'candidate_dtb_sha256': digest(new),
                       'dtb_count': len(trees), 'changed_dtb_bytes': 3,
                       'status': 'uninstalled, unbooted; shared fallback compatibility unverified'}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--input', required=True, type=Path)
    p.add_argument('--expected-sha256', required=True)
    p.add_argument('--output', required=True, type=Path, help='new file outside /boot')
    a = p.parse_args()
    dest = a.output.resolve()
    if dest == Path('/boot') or Path('/boot') in dest.parents:
        p.error('output must be outside /boot')
    original = a.input.read_bytes()
    if digest(original) != a.expected_sha256:
        p.error('input checksum differs from expected')
    candidate, receipt = compose(original)
    with dest.open('xb') as f:
        f.write(candidate)
    print(json.dumps(receipt, indent=2))


if __name__ == '__main__':
    main()
