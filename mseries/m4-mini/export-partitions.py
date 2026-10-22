#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Linux build-side export of GPT metadata and optional partition payloads from a regular image only.

This prepares an installer adapter input; it never imports a GPT, opens a block
device, changes installer admission, or qualifies the image for M4 hardware.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import stat
import struct
import uuid
import zlib

HEADER = struct.Struct('<8sIIIIQQQQ16sQIII')


def exact(stream, offset, size):
    stream.seek(offset)
    data = stream.read(size)
    if len(data) != size:
        raise ValueError('truncated image')
    return data


def read_header(stream, sector, lba):
    raw = exact(stream, sector * lba, sector)
    values = HEADER.unpack_from(raw)
    sig, revision, length, crc, reserved, current, backup, first, last, disk, table, count, width, table_crc = values
    if sig != b'EFI PART' or revision != 0x10000 or not HEADER.size <= length <= sector or reserved:
        raise ValueError('unsupported GPT header')
    body = bytearray(raw[:length])
    body[16:20] = b'\0' * 4
    if zlib.crc32(body) != crc or current != lba:
        raise ValueError('GPT header CRC or LBA mismatch')
    if not count or width < 128 or width % 8 or count * width > 64 * 1024**2:
        raise ValueError('unsupported GPT entry dimensions')
    entries = exact(stream, table * sector, count * width)
    if zlib.crc32(entries) != table_crc:
        raise ValueError('GPT entry-array CRC mismatch')
    return {'current': current, 'backup': backup, 'first': first, 'last': last,
            'disk': str(uuid.UUID(bytes_le=disk)), 'table': table, 'count': count,
            'width': width, 'raw': raw, 'entries': entries}


def inspect(stream, size):
    mbr = exact(stream, 0, 512)
    if mbr[510:] != b'\x55\xaa' or not any(mbr[446 + i * 16 + 4] == 0xee for i in range(4)):
        raise ValueError('protective MBR missing')
    sectors = [s for s in (512, 4096) if size >= 3 * s and exact(stream, s, 8) == b'EFI PART']
    if len(sectors) != 1 or size % sectors[0]:
        raise ValueError('unsupported or ambiguous logical sector size')
    sector = sectors[0]
    end = size // sector - 1
    primary = read_header(stream, sector, 1)
    backup = read_header(stream, sector, end)
    if primary['backup'] != end or backup['backup'] != 1:
        raise ValueError('GPT headers do not reference each other')
    if any(primary[k] != backup[k] for k in ['disk', 'first', 'last', 'count', 'width', 'entries']):
        raise ValueError('primary and backup GPT disagree')
    first, last = primary['first'], primary['last']
    length = len(primary['entries'])
    if not (primary['table'] >= 2 and primary['table'] * sector + length <= first * sector
            and first <= last < end and backup['table'] > last
            and backup['table'] * sector + length <= end * sector):
        raise ValueError('GPT tables overlap usable space or headers')
    partitions = []
    identifiers = set()
    for index in range(primary['count']):
        raw = primary['entries'][index * primary['width']:(index + 1) * primary['width']]
        if raw[:16] == bytes(16):
            continue
        unique = str(uuid.UUID(bytes_le=raw[16:32]))
        start, stop, flags = struct.unpack_from('<QQQ', raw, 32)
        if unique == str(uuid.UUID(int=0)) or unique in identifiers or not first <= start <= stop <= last:
            raise ValueError('invalid, duplicate or out-of-bounds partition')
        identifiers.add(unique)
        partitions.append({'index': index + 1, 'type_guid': str(uuid.UUID(bytes_le=raw[:16])),
                           'unique_guid': unique, 'first_lba': start, 'last_lba': stop,
                           'offset_bytes': start * sector, 'size_bytes': (stop - start + 1) * sector,
                           'label': raw[56:128].decode('utf-16-le').rstrip('\0'),
                           'attributes_hex': f'0x{flags:016x}', 'no_auto': bool(flags & (1 << 63)),
                           'read_only': bool(flags & (1 << 60)), 'growfs': bool(flags & (1 << 59))})
    ordered = sorted(partitions, key=lambda p: p['first_lba'])
    if any(a['last_lba'] >= b['first_lba'] for a, b in zip(ordered, ordered[1:])):
        raise ValueError('overlapping partitions')
    return sector, primary, backup, partitions


def copy_range(stream, offset, size, output=None):
    stream.seek(offset)
    digest = hashlib.sha256()
    while size:
        block = stream.read(min(size, 1024**2))
        if not block:
            raise ValueError('source truncated during export')
        digest.update(block)
        if output is not None:
            output.write(block)
        size -= len(block)
    return digest.hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--image', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--extract', type=int, action='append', default=[], metavar='PARTITION_INDEX')
    args = parser.parse_args()
    # Linux O_PATH inspects the inode without invoking a device's open method.
    # Reopen only this proven regular inode; path replacement cannot redirect it.
    path_fd = os.open(args.image, os.O_PATH | os.O_NOFOLLOW)
    try:
        if not stat.S_ISREG(os.fstat(path_fd).st_mode):
            raise ValueError('regular image without symlinks required')
        descriptor = os.open('/proc/self/fd/' + str(path_fd), os.O_RDONLY)
    finally:
        os.close(path_fd)
    with os.fdopen(descriptor, 'rb') as stream:
        before = os.fstat(stream.fileno())
        if not stat.S_ISREG(before.st_mode) or args.output.exists():
            raise ValueError('regular image and new output directory required')
        sector, primary, backup, partitions = inspect(stream, before.st_size)
        wanted = set(args.extract)
        if not wanted <= {p['index'] for p in partitions}:
            raise ValueError('requested partition does not exist')
        args.output.mkdir(parents=True)
        marker = args.output / 'INCOMPLETE'
        marker.touch()
        metadata = {'protective-mbr.bin': exact(stream, 0, sector),
                    'gpt-primary-header.bin': primary['raw'], 'gpt-backup-header.bin': backup['raw'],
                    'gpt-partition-entries.bin': primary['entries']}
        hashes = {}
        for name, data in metadata.items():
            (args.output / name).write_bytes(data)
            hashes[name] = hashlib.sha256(data).hexdigest()
        for partition in partitions:
            if partition['index'] in wanted:
                name = f"partition-{partition['index']}.img"
                with (args.output / name).open('xb') as target:
                    digest = copy_range(stream, partition['offset_bytes'], partition['size_bytes'], target)
                partition['payload'] = {'file': name, 'sha256': digest}
        source_hash = copy_range(stream, 0, before.st_size)
        after = os.fstat(stream.fileno())
        if (before.st_size, before.st_mtime_ns, before.st_ctime_ns) != (after.st_size, after.st_mtime_ns, after.st_ctime_ns):
            raise ValueError('source changed during export')
        (args.output / 'manifest.json').write_text(json.dumps({
            'schema': 1, 'scope': 'GPT metadata/selected payload export only; no import or boot validation',
            'source_sha256': source_hash, 'source_size_bytes': before.st_size, 'logical_sector_size': sector,
            'disk_guid': primary['disk'], 'first_usable_lba': primary['first'], 'last_usable_lba': primary['last'],
            'entry_count': primary['count'], 'entry_size': primary['width'],
            'metadata_sha256': hashes, 'partitions': partitions,
            'installer_ready': False, 'hardware_validated': False,
        }, indent=2) + '\n')
        marker.unlink()
    print('GPT metadata and requested payloads exported; installer import remains unqualified')


if __name__ == '__main__':
    main()
