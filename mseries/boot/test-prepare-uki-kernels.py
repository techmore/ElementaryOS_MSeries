#!/usr/bin/env python3
import importlib.util
import json
from pathlib import Path
import struct
import tempfile
import unittest

spec = importlib.util.spec_from_file_location('prepare', Path(__file__).with_name('prepare-uki-kernels.py'))
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def pe(sections, relocations=0):
    header = bytearray(512)
    header[:2] = b'MZ'
    struct.pack_into('<I', header, 60, 64)
    header[64:68] = b'PE\0\0'
    struct.pack_into('<HH', header, 68, 0xAA64, len(sections))
    struct.pack_into('<H', header, 84, 160)
    struct.pack_into('<H', header, 88, 0x20B)
    struct.pack_into('<I', header, 88 + 112 + 5 * 8 + 4, relocations)
    data = header
    for index, (name, content) in enumerate(sections.items()):
        section = 88 + 160 + 40 * index
        header[section:section + 8] = name.encode().ljust(8, b'\0')
        struct.pack_into('<IIII', header, section + 8, len(content), 4096, len(content), len(data))
        data += content
    return bytes(data)


class KernelInputTests(unittest.TestCase):
    def test_plain_kernel_unchanged(self):
        self.assertIsNone(module.inner_kernel(pe({'.text': b'plain'})))
        self.assertIsNone(module.inner_kernel(b'uncompressed Linux Image'))

    def test_wrapper_extracts_exact_inner_image(self):
        inner = pe({'.text': b'actual kernel'})
        outer = pe({'.linux': inner, '.uname': b'7.0-test'}, relocations=144)
        self.assertEqual(inner, module.inner_kernel(outer))

    def test_relocatable_inner_image_rejected(self):
        inner = pe({'.text': b'kernel'}, relocations=144)
        with self.assertRaisesRegex(ValueError, 'directly loadable'):
            module.inner_kernel(pe({'.linux': inner}))

    def test_cannot_drop_distribution_initrd_or_commandline(self):
        inner = pe({'.text': b'kernel'})
        for section in ('.initrd', '.cmdline'):
            with self.assertRaisesRegex(ValueError, 'Refusing to discard'):
                module.inner_kernel(pe({'.linux': inner, section: b'must retain'}))

    def test_truncated_inner_payload_rejected(self):
        data = bytearray(pe({'.linux': pe({'.text': b'kernel'})}))
        struct.pack_into('<I', data, 88 + 160 + 20, len(data) + 100)
        with self.assertRaisesRegex(ValueError, 'Truncated'):
            module.inner_kernel(bytes(data))

    def test_image_symlink_backup_and_idempotence(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            kernel = root / 'boot/vmlinuz-test'
            kernel.parent.mkdir()
            inner = pe({'.text': b'kernel'})
            outer = pe({'.linux': inner}, relocations=144)
            kernel.write_bytes(outer)
            entry = root / 'usr/lib/modules/test/vmlinuz'
            entry.parent.mkdir(parents=True)
            entry.symlink_to('/boot/vmlinuz-test')
            module.prepare(root)
            self.assertEqual(inner, kernel.read_bytes())
            backup = root / 'usr/share/doc/mseries-kernel-inputs/test/distribution-wrapper.efi'
            self.assertEqual(outer, backup.read_bytes())
            record = json.loads(backup.with_name('SOURCE.json').read_text())
            self.assertEqual(record['linux_sha256'], module.hashlib.sha256(inner).hexdigest())
            module.prepare(root)
            self.assertEqual(outer, backup.read_bytes())


if __name__ == '__main__':
    unittest.main()
