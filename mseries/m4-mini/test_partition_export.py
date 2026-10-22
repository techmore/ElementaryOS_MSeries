#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Exercise GPT export against sgdisk-produced regular-file fixtures, no devices."""
import hashlib
import json
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest
import zlib

HERE = Path(__file__).resolve().parent
TYPE = 'b0e01050-ee5f-4390-949a-9101b17104e9'
UNIQUE = '11223344-5566-7788-99aa-bbccddeeff00'


class PartitionExportTests(unittest.TestCase):
    def setUp(self):
        if not shutil.which('sgdisk'):
            self.fail('sgdisk is required to produce an independent GPT fixture')
        scratch = HERE.parents[1] / 'work'
        scratch.mkdir(exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(prefix='m4-gpt-', dir=scratch)
        self.addCleanup(self.temp.cleanup)
        self.dir = Path(self.temp.name)
        self.image = self.dir / 'source.raw'
        with self.image.open('wb') as stream:
            stream.truncate(64 * 1024**2)
        subprocess.run(['sgdisk', '--clear', '--new=1:2048:+8M', '--typecode=1:' + TYPE,
                        '--partition-guid=1:' + UNIQUE, '--change-name=1:elementary_contract_usr',
                        '--attributes=1:set:60', '--new=2:20480:+8M', '--typecode=2:' + TYPE,
                        '--change-name=2:spare', '--attributes=2:set:63', str(self.image)],
                       check=True, capture_output=True)
        with self.image.open('r+b') as stream:
            stream.seek(2048 * 512)
            stream.write(b'partition-payload-fixture')

    def run_export(self, image=None, *options):
        out = self.dir / 'export'
        command = [sys.executable, str(HERE / 'export-partitions.py'), '--image',
                   str(image or self.image), '--output', str(out), *options]
        return subprocess.run(command, capture_output=True, text=True), out

    def test_metadata_payload_and_source_unchanged(self):
        before = hashlib.sha256(self.image.read_bytes()).hexdigest()
        result, out = self.run_export(None, '--extract=1')
        self.assertEqual(result.returncode, 0, result.stderr)
        manifest = json.loads((out / 'manifest.json').read_text())
        self.assertEqual(manifest['source_sha256'], before)
        self.assertEqual(hashlib.sha256(self.image.read_bytes()).hexdigest(), before)
        first, spare = manifest['partitions']
        self.assertEqual((first['type_guid'], first['unique_guid'], first['label']),
                         (TYPE, UNIQUE, 'elementary_contract_usr'))
        self.assertEqual(first['attributes_hex'], '0x1000000000000000')
        self.assertTrue(first['read_only'])
        self.assertTrue(spare['no_auto'])
        self.assertNotIn('payload', spare)
        payload = out / first['payload']['file']
        self.assertEqual(payload.stat().st_size, 8 * 1024**2)
        self.assertEqual(payload.read_bytes()[:25], b'partition-payload-fixture')
        self.assertEqual(hashlib.sha256(payload.read_bytes()).hexdigest(), first['payload']['sha256'])
        for name, digest in manifest['metadata_sha256'].items():
            self.assertEqual(hashlib.sha256((out / name).read_bytes()).hexdigest(), digest)
        self.assertFalse(manifest['installer_ready'])
        self.assertFalse((out / 'INCOMPLETE').exists())

    def test_4096_sector_metadata(self):
        original = self.image.read_bytes()
        entries = bytearray(original[1024:1024 + 128 * 128])
        for index in [0, 1]:
            start, end = struct.unpack_from('<QQ', entries, index * 128 + 32)
            struct.pack_into('<QQ', entries, index * 128 + 32, start // 8, (end + 1) // 8 - 1)
        sector = 4096
        last = len(original) // sector - 1
        image = self.dir / '4096.raw'
        with image.open('wb') as stream:
            stream.truncate(len(original))
            mbr = bytearray(original[:512])
            struct.pack_into('<I', mbr, 458, last)
            stream.write(mbr)
            for current, backup, table in [(1, last, 2), (last, 1, last - 4)]:
                header = bytearray(original[512:1024]) + bytearray(sector - 512)
                struct.pack_into('<QQQQ', header, 24, current, backup, 6, last - 5)
                struct.pack_into('<Q', header, 72, table)
                struct.pack_into('<I', header, 88, zlib.crc32(entries))
                struct.pack_into('<I', header, 16, 0)
                struct.pack_into('<I', header, 16, zlib.crc32(header[:92]))
                stream.seek(current * sector)
                stream.write(header)
                stream.seek(table * sector)
                stream.write(entries)
        result, out = self.run_export(image)
        self.assertEqual(result.returncode, 0, result.stderr)
        manifest = json.loads((out / 'manifest.json').read_text())
        self.assertEqual(manifest['logical_sector_size'], 4096)
        self.assertEqual(manifest['partitions'][0]['offset_bytes'], 1048576)
        self.assertEqual(manifest['partitions'][0]['unique_guid'], UNIQUE)
        self.assertEqual((out / 'gpt-primary-header.bin').stat().st_size, 4096)

    def test_corrupt_primary_and_backup_rejected_before_output(self):
        original = self.image.read_bytes()
        end = len(original) - 512
        for offset in [512 + 24, 2 * 512, end + 24, end - 32 * 512]:
            with self.subTest(offset=offset):
                data = bytearray(original)
                data[offset] ^= 1
                self.image.write_bytes(data)
                result, out = self.run_export()
                self.assertNotEqual(result.returncode, 0)
                self.assertIn('CRC', result.stderr)
                self.assertFalse(out.exists())

    def test_overlap_with_valid_crcs_rejected(self):
        data = bytearray(self.image.read_bytes())
        end = len(data) - 512
        entries = bytearray(data[1024:1024 + 128 * 128])
        # Give entry two the same start as entry one, retaining distinct UUIDs.
        entries[128 + 32:128 + 40] = entries[32:40]
        for header in [512, end]:
            table_lba = struct.unpack_from('<Q', data, header + 72)[0]
            data[table_lba * 512:table_lba * 512 + len(entries)] = entries
            struct.pack_into('<I', data, header + 88, zlib.crc32(entries))
            struct.pack_into('<I', data, header + 16, 0)
            struct.pack_into('<I', data, header + 16, zlib.crc32(data[header:header + 92]))
        self.image.write_bytes(data)
        result, out = self.run_export()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('overlapping partitions', result.stderr)
        self.assertFalse(out.exists())

    def test_symlink_and_character_device_rejected(self):
        link = self.dir / 'link.raw'
        link.symlink_to(self.image)
        for image in [link, Path('/dev/null')]:
            result, out = self.run_export(image)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('regular image', result.stderr)
            self.assertFalse(out.exists())

    def test_missing_index_rejected_before_output(self):
        result, out = self.run_export(None, '--extract=12')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('does not exist', result.stderr)
        self.assertFalse(out.exists())


if __name__ == '__main__':
    unittest.main()
