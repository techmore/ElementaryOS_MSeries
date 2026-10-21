#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Check J773g final-DT RAM/ramoops bounds; does not prove physical RAM or boot."""
import argparse
import json
from pathlib import Path
import subprocess


def read(dtb, node, prop, kind='x'):
    return subprocess.check_output(['fdtget', '-t', kind, str(dtb), node, prop], text=True).split()


def ranges(dtb, node, strict=False):
    cells = [int(value, 16) for value in read(dtb, node, 'reg')]
    if len(cells) % 4:
        raise ValueError('expected 64-bit address/size tuples: ' + node)
    result = []
    for i in range(0, len(cells), 4):
        base = (cells[i] << 32) | cells[i + 1]
        size = (cells[i + 2] << 32) | cells[i + 3]
        if base + size > 1 << 64 or (strict and (not size or (base | size) & 0x3fff)):
            raise ValueError('zero, overflowing or non-16-KiB-aligned range: ' + node)
        if not size:
            continue
        result.append((base, base + size))
    return result


def children(dtb, node):
    return subprocess.check_output(['fdtget', '-l', str(dtb), node], text=True).split()


def overlap(a, b):
    return a[0] < b[1] and b[0] < a[1]


def check(dtb):
    if 'apple,j773g' not in read(dtb, '/', 'compatible', 's'):
        raise ValueError('J773g DT required')
    for node in ['/', '/reserved-memory']:
        if read(dtb, node, '#address-cells') != ['2'] or read(dtb, node, '#size-cells') != ['2']:
            raise ValueError('64-bit address and size cells required')
    memory = []
    for child in children(dtb, '/'):
        if child == 'memory' or child.startswith('memory@'):
            memory.extend(ranges(dtb, '/' + child, strict=True))
    if not memory:
        raise ValueError('final loader RAM map required')
    for i, region in enumerate(memory):
        if any(overlap(region, other) for other in memory[:i]):
            raise ValueError('overlapping RAM ranges')
    reserved = {}
    ramoops = []
    for child in children(dtb, '/reserved-memory'):
        node = '/reserved-memory/' + child
        properties = subprocess.check_output(['fdtget', '-p', str(dtb), node], text=True).split()
        if 'status' in properties and read(dtb, node, 'status', 's') == ['disabled']:
            continue
        if 'reg' in properties:
            reserved[node] = ranges(dtb, node)
            if 'compatible' in properties and 'ramoops' in read(dtb, node, 'compatible', 's'):
                reserved[node] = ranges(dtb, node, strict=True)
                ramoops.append(node)
    if len(ramoops) != 1:
        raise ValueError('one active ramoops reservation required')
    name = ramoops[0]
    for region in reserved[name]:
        if not any(region[0] >= ram[0] and region[1] <= ram[1] for ram in memory):
            raise ValueError('ramoops lies outside declared final RAM')
        if any(overlap(region, other) for node, regions in reserved.items() if node != name for other in regions):
            raise ValueError('ramoops overlaps another reservation')
    return {'ram_ranges': memory, 'ramoops_ranges': reserved[name],
            'scope': 'DT-declared RAM and ramoops only; not physical capacity, GPU/DCP firmware or boot qualification',
            'hardware_validated': False}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dtb', type=Path, required=True)
    print(json.dumps(check(parser.parse_args().dtb), indent=2))
