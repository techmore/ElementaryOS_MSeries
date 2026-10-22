#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Independent sgdisk fixtures for copy-only import; never opens a disk device."""
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import struct
import sys
import tempfile
import unittest
import zlib

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('import_regular', HERE / 'import-partitions-regular.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
USR = 'b0e01050-ee5f-4390-949a-9101b17104e9'
VERITY = 'df3300ce-d69f-4c92-978c-9bfb0f38d820'
APFS = '7c3457ef-0000-11aa-aa11-00306543ecac'


class ImportTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='m4-import-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / 'source.raw'
        self.template = self.root / 'template.raw'
        for p in [self.source, self.template]:
            with p.open('wb') as f:
                f.truncate(32 * 1024**2)
        self.gpt(self.source, '--clear', '--new=1:2048:+2M', '--typecode=1:' + USR,
                 '--change-name=1:elementary_試験_usr', '--attributes=1:set:60',
                 '--new=2:8192:+2M', '--typecode=2:' + VERITY,
                 '--change-name=2:reserved_verity', '--attributes=2:set:63',
                 '--attributes=2:set:59', '--attributes=2:set:0')
        self.gpt(self.template, '--clear', '--new=1:2048:+2M', '--typecode=1:' + APFS,
                 '--change-name=1:macOS_fixture', '--new=2:8192:+2M', '--typecode=2:' + APFS,
                 '--change-name=2:Recovery_fixture', '--new=3:14336:+2M',
                 '--typecode=3:' + module.EMPTY_TYPE, '--change-name=3:' + module.EMPTY_LABEL,
                 '--new=4:20480:+2M', '--typecode=4:' + module.EMPTY_TYPE,
                 '--change-name=4:' + module.EMPTY_LABEL)
        with self.source.open('r+b') as f:
            f.seek(2048 * 512)
            f.write(b'active-system-content')
        with self.template.open('r+b') as f:
            for lba, value in [(2048, b'preserved-macOS'), (8192, b'preserved-Recovery')]:
                f.seek(lba * 512)
                f.write(value)
        self.export = self.root / 'export'
        subprocess.run([sys.executable, str(HERE / 'export-partitions.py'), '--image',
                        str(self.source), '--output', str(self.export), '--extract=1', '--extract=2'],
                       check=True, capture_output=True)
        self.output = self.root / 'output'

    def gpt(self, image, *options):
        return subprocess.check_output(['sgdisk', *options, str(image)], text=True, stderr=subprocess.STDOUT)

    def run_import(self, mapping=None, template=None):
        command = [sys.executable, str(HERE / 'import-partitions-regular.py'), '--export', str(self.export),
                   '--template', str(template or self.template), '--output', str(self.output)]
        for value in mapping or ['1:3', '2:4']:
            command += ['--map', value]
        return subprocess.run(command, capture_output=True, text=True)

    def assert_rejected(self, **kwargs):
        before = hashlib.sha256(self.template.read_bytes()).hexdigest()
        result = self.run_import(**kwargs)
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertFalse(self.output.exists(), result.stderr)
        self.assertEqual(hashlib.sha256(self.template.read_bytes()).hexdigest(), before)

    def test_relocated_payloads_metadata_and_existing_os_preserved(self):
        before = self.template.read_bytes()
        result = self.run_import()
        self.assertEqual(result.returncode, 0, result.stderr)
        target = self.output / 'image.raw'
        after = target.read_bytes()
        self.assertEqual(self.template.read_bytes(), before)
        for index in [1, 2]:
            self.assertEqual(self.gpt(self.template, '--info=' + str(index)), self.gpt(target, '--info=' + str(index)))
        for src, dst in [(1, 3), (2, 4)]:
            a = self.gpt(self.source, '--info=' + str(src)).splitlines()
            b = self.gpt(target, '--info=' + str(dst)).splitlines()
            for prefix in ['Partition GUID code:', 'Partition unique GUID:', 'Attribute flags:', 'Partition name:']:
                self.assertEqual(next(x for x in a if x.startswith(prefix)), next(x for x in b if x.startswith(prefix)))
        self.assertEqual(after[2048 * 512:12288 * 512], before[2048 * 512:12288 * 512])
        self.assertEqual(after[14336 * 512:18432 * 512], (self.export / 'partition-1.img').read_bytes())
        self.assertEqual(after[20480 * 512:24576 * 512], (self.export / 'partition-2.img').read_bytes())
        self.gpt(target, '--verify')
        receipt = json.loads((self.output / 'receipt.json').read_text())
        self.assertTrue(receipt['unselected_bytes_preserved'])
        self.assertFalse(receipt['installer_admission'])
        self.assertFalse(receipt['hardware_validated'])

    def test_nonzero_slot_rejected(self):
        with self.template.open('r+b') as f:
            f.seek(14336 * 512)
            f.write(b'existing-data')
        self.assert_rejected()

    def test_size_mismatch_rejected(self):
        self.gpt(self.template, '--delete=3', '--new=3:14336:+1M',
                 '--typecode=3:' + module.EMPTY_TYPE, '--change-name=3:' + module.EMPTY_LABEL)
        self.assert_rejected()

    def test_4096_destination_geometry_preserved(self):
        original = self.template.read_bytes()
        entries = bytearray(original[1024:1024 + 128 * 128])
        for index in range(4):
            start, end = struct.unpack_from('<QQ', entries, index * 128 + 32)
            struct.pack_into('<QQ', entries, index * 128 + 32, start // 8, (end + 1) // 8 - 1)
        sector = 4096
        last = len(original) // sector - 1
        data = bytearray(original)
        data[:32768] = bytes(32768)
        data[-32768:] = bytes(32768)
        data[:512] = original[:512]
        struct.pack_into('<I', data, 458, last)
        for current, backup, table in [(1, last, 2), (last, 1, last - 4)]:
            header = bytearray(original[512:1024]) + bytearray(sector - 512)
            struct.pack_into('<QQQQ', header, 24, current, backup, 6, last - 5)
            struct.pack_into('<Q', header, 72, table)
            struct.pack_into('<I', header, 88, zlib.crc32(entries))
            struct.pack_into('<I', header, 16, 0)
            struct.pack_into('<I', header, 16, zlib.crc32(header[:92]))
            data[current * sector:(current + 1) * sector] = header
            data[table * sector:table * sector + len(entries)] = entries
        self.template.write_bytes(data)
        result = self.run_import()
        self.assertEqual(result.returncode, 0, result.stderr)
        after = (self.output / 'image.raw').read_bytes()
        self.assertEqual(self.template.read_bytes(), data)
        for current, table in [(1, 2), (last, last - 4)]:
            header = bytearray(after[current * sector:current * sector + 92])
            crc = struct.unpack_from('<I', header, 16)[0]
            struct.pack_into('<I', header, 16, 0)
            self.assertEqual(zlib.crc32(header), crc)
            actual = after[table * sector:table * sector + len(entries)]
            self.assertEqual(zlib.crc32(actual), struct.unpack_from('<I', header, 88)[0])
            # Destination LBAs remain in 4 KiB units, not source-image units.
            self.assertEqual(actual[2 * 128 + 32:2 * 128 + 48], entries[2 * 128 + 32:2 * 128 + 48])
            self.assertEqual(actual[:2 * 128], entries[:2 * 128])
        self.assertEqual(after[14336 * 512:18432 * 512], (self.export / 'partition-1.img').read_bytes())
        self.assertEqual(after[2048 * 512:12288 * 512], data[2048 * 512:12288 * 512])

    def test_os_partition_mapping_rejected(self):
        self.assert_rejected(mapping=['1:1'])

    def test_duplicate_mapping_rejected(self):
        self.assert_rejected(mapping=['1:3', '1:4'])

    def test_payload_corruption_rejected(self):
        with (self.export / 'partition-1.img').open('r+b') as f:
            f.write(b'corrupt')
        self.assert_rejected()

    def test_metadata_manifest_disagreement_rejected(self):
        p = self.export / 'manifest.json'
        m = json.loads(p.read_text())
        m['partitions'][0]['attributes_hex'] = '0x0000000000000000'
        p.write_text(json.dumps(m))
        self.assert_rejected()

    def test_guid_collision_rejected(self):
        m = json.loads((self.export / 'manifest.json').read_text())
        self.gpt(self.template, '--partition-guid=1:' + m['partitions'][0]['unique_guid'])
        self.assert_rejected()

    def test_device_and_symlink_rejected(self):
        link = self.root / 'link'
        link.symlink_to(self.template)
        self.assert_rejected(template=link)
        self.assert_rejected(template=Path('/dev/null'))


if __name__ == '__main__':
    unittest.main()
