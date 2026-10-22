#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Prototype metadata-preserving import into a COPY of a preallocated regular GPT image.

Linux regular files only. Never updates a device, macOS GPT or original template.
Mapped destination slots must have the reserved type, exact empty-import label,
exact payload size and all-zero contents. This is not a native installer.
"""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import stat
import struct
import tempfile
import uuid
import zlib

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('gpt_export', HERE / 'export-partitions.py')
gpt = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gpt)
EMPTY_TYPE = '8da63339-0007-60c0-c436-083ac8230908'
EMPTY_LABEL = 'elementary_m4_import_empty'


def regular(path):
    fd = os.open(path, os.O_PATH | os.O_NOFOLLOW)
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            raise ValueError('regular file without symlinks required')
        opened = os.open('/proc/self/fd/' + str(fd), os.O_RDONLY)
    finally:
        os.close(fd)
    return os.fdopen(opened, 'rb')


def digest_file(path):
    with regular(path) as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def source_metadata(directory):
    if (directory / 'INCOMPLETE').exists():
        raise ValueError('incomplete source export')
    with regular(directory / 'manifest.json') as f:
        manifest = json.load(f)
    if manifest['schema'] != 1 or not 0 < manifest['source_size_bytes'] <= 2**43:
        raise ValueError('unsupported export')
    expected = {'protective-mbr.bin', 'gpt-primary-header.bin',
                'gpt-backup-header.bin', 'gpt-partition-entries.bin'}
    if set(manifest['metadata_sha256']) != expected:
        raise ValueError('complete exported GPT metadata required')
    data = {}
    for name in expected:
        if digest_file(directory / name) != manifest['metadata_sha256'][name]:
            raise ValueError('export metadata hash mismatch')
        with regular(directory / name) as f:
            data[name] = f.read()
    sector = manifest['logical_sector_size']
    if sector not in (512, 4096):
        raise ValueError('unsupported source logical sector size')
    # Reconstruct metadata only in a sparse anonymous regular file. inspect()
    # independently verifies both CRCs, bounds and mirrored entry arrays.
    with tempfile.TemporaryFile() as stream:
        stream.truncate(manifest['source_size_bytes'])
        for header_name in ['gpt-primary-header.bin', 'gpt-backup-header.bin']:
            header = data[header_name]
            values = gpt.HEADER.unpack_from(header)
            stream.seek(values[5] * sector)
            stream.write(header)
            stream.seek(values[10] * sector)
            stream.write(data['gpt-partition-entries.bin'])
        stream.seek(0)
        stream.write(data['protective-mbr.bin'])
        found_sector, primary, _, parts = gpt.inspect(stream, manifest['source_size_bytes'])
    keys = ['index', 'type_guid', 'unique_guid', 'first_lba', 'last_lba', 'offset_bytes',
            'size_bytes', 'label', 'attributes_hex', 'no_auto', 'read_only', 'growfs']
    claimed = [{k: p[k] for k in keys} for p in manifest['partitions']]
    if (found_sector != sector or parts != claimed or primary['disk'] != manifest['disk_guid'] or
            primary['count'] != manifest['entry_count'] or primary['width'] != manifest['entry_size'] or
            primary['first'] != manifest['first_usable_lba'] or primary['last'] != manifest['last_usable_lba']):
        raise ValueError('manifest differs from independently parsed source GPT')
    return manifest


def stable(before, after):
    return (before.st_size, before.st_mtime_ns, before.st_ctime_ns) == (after.st_size, after.st_mtime_ns, after.st_ctime_ns)


def unchanged_hash(stream, size, excluded):
    digest = hashlib.sha256()
    position = 0
    for start, end in sorted(excluded) + [(size, size)]:
        if start < position:
            raise ValueError('overlapping write ranges')
        stream.seek(position)
        remaining = start - position
        while remaining:
            block = stream.read(min(remaining, 1024**2))
            if not block:
                raise ValueError('truncated preserved range')
            digest.update(block)
            remaining -= len(block)
        position = end
    return digest.hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--export', dest='source', type=Path, required=True)
    parser.add_argument('--template', type=Path, required=True)
    parser.add_argument('--map', action='append', required=True, metavar='SOURCE_INDEX:EMPTY_DEST_INDEX')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    pairs = [tuple(map(int, value.split(':'))) for value in args.map]
    if (any(len(pair) != 2 for pair in pairs) or len({p[0] for p in pairs}) != len(pairs) or
            len({p[1] for p in pairs}) != len(pairs)):
        raise ValueError('unique source and destination mapping required')
    manifest = source_metadata(args.source)
    sources = {p['index']: p for p in manifest['partitions']}
    with regular(args.template) as template:
        before = os.fstat(template.fileno())
        sector, primary, backup, parts = gpt.inspect(template, before.st_size)
        destinations = {p['index']: p for p in parts}
        kept_guids = {p['unique_guid'] for p in parts if p['index'] not in {b for _, b in pairs}}
        writes = []
        for src_index, dst_index in pairs:
            source, dest = sources[src_index], destinations[dst_index]
            if dest['type_guid'] != EMPTY_TYPE or dest['label'] != EMPTY_LABEL or dest['attributes_hex'] != '0x0000000000000000':
                raise ValueError('destination is not an explicitly reserved empty import slot')
            if source['size_bytes'] != dest['size_bytes'] or source['unique_guid'] in kept_guids:
                raise ValueError('destination size mismatch or partition GUID collision')
            kept_guids.add(source['unique_guid'])
            payload = source['payload']
            name = payload['file']
            if name != f'partition-{src_index}.img':
                raise ValueError('unexpected payload filename')
            with regular(args.source / name) as stream:
                if os.fstat(stream.fileno()).st_size != source['size_bytes'] or hashlib.file_digest(stream, 'sha256').hexdigest() != payload['sha256']:
                    raise ValueError('source payload size/hash mismatch')
            template.seek(dest['offset_bytes'])
            left = dest['size_bytes']
            while left:
                block = template.read(min(left, 1024**2))
                if not block or any(block):
                    raise ValueError('destination slot contains existing data')
                left -= len(block)
            writes.append((source, dest))
        if args.output.exists():
            raise ValueError('new output directory required')
        args.output.mkdir(parents=True)
        marker = args.output / 'INCOMPLETE'
        marker.touch()
        target_path = args.output / 'image.raw'
        source_hash = gpt.copy_range(template, 0, before.st_size)
        with target_path.open('x+b') as target:
            # Preserve holes without modifying any logical bytes.
            template.seek(0)
            while block := template.read(1024**2):
                if any(block):
                    target.write(block)
                else:
                    target.seek(len(block), os.SEEK_CUR)
            target.truncate(before.st_size)
            entries = bytearray(primary['entries'])
            excluded = []
            for source, dest in writes:
                position = (dest['index'] - 1) * primary['width']
                entry = bytearray(entries[position:position + primary['width']])
                entry[:16] = uuid.UUID(source['type_guid']).bytes_le
                entry[16:32] = uuid.UUID(source['unique_guid']).bytes_le
                struct.pack_into('<Q', entry, 48, int(source['attributes_hex'], 16))
                entry[56:128] = source['label'].encode('utf-16-le').ljust(72, b'\0')
                entries[position:position + primary['width']] = entry
                with regular(args.source / source['payload']['file']) as payload:
                    target.seek(dest['offset_bytes'])
                    got = gpt.copy_range(payload, 0, source['size_bytes'], target)
                if got != source['payload']['sha256']:
                    raise ValueError('payload changed while copying')
                excluded.append((dest['offset_bytes'], dest['offset_bytes'] + dest['size_bytes']))
            for header in [primary, backup]:
                target.seek(header['table'] * sector)
                target.write(entries)
                raw = bytearray(header['raw'])
                struct.pack_into('<I', raw, 88, zlib.crc32(entries))
                struct.pack_into('<I', raw, 16, 0)
                struct.pack_into('<I', raw, 16, zlib.crc32(raw[:struct.unpack_from('<I', raw, 12)[0]]))
                target.seek(header['current'] * sector)
                target.write(raw)
                excluded += [(header['current'] * sector, (header['current'] + 1) * sector),
                             (header['table'] * sector, header['table'] * sector + len(entries))]
            target.flush()
            os.fsync(target.fileno())
            _, check, _, result = gpt.inspect(target, before.st_size)
            expected = {p['index']: dict(p) for p in parts}
            for source, dest in writes:
                for key in ['type_guid', 'unique_guid', 'label', 'attributes_hex', 'no_auto', 'read_only', 'growfs']:
                    expected[dest['index']][key] = source[key]
                if gpt.copy_range(target, dest['offset_bytes'], dest['size_bytes']) != source['payload']['sha256']:
                    raise ValueError('destination payload readback mismatch')
            if result != list(expected.values()) or check['disk'] != primary['disk']:
                raise ValueError('destination GPT metadata readback mismatch')
            preserved = unchanged_hash(template, before.st_size, excluded)
            if unchanged_hash(target, before.st_size, excluded) != preserved:
                raise ValueError('unselected destination bytes changed')
            output_hash = gpt.copy_range(target, 0, before.st_size)
        if not stable(before, os.fstat(template.fileno())) or gpt.copy_range(template, 0, before.st_size) != source_hash:
            raise ValueError('original template changed')
        (args.output / 'receipt.json').write_text(json.dumps({
            'scope': 'regular-image COPY prototype; no native disk/Apple installer integration',
            'template_sha256': source_hash, 'output_sha256': output_hash,
            'source_image_sha256': manifest['source_sha256'], 'disk_guid_preserved': primary['disk'],
            'mapping': pairs, 'unselected_bytes_sha256': preserved, 'unselected_bytes_preserved': True,
            'metadata_and_payload_readback': True, 'template_unchanged': True,
            'importer_sha256': digest_file(Path(__file__)), 'installer_admission': False,
            'hardware_validated': False}, indent=2) + '\n')
        marker.unlink()
    print('Regular-image copy imported and verified; no native installer admission')


if __name__ == '__main__':
    main()
