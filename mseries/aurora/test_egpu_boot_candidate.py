"""Safety checks for the uninstalled eGPU boot payload builder."""
import importlib.util
from pathlib import Path
import struct
import unittest

path = Path(__file__).parent / 'unified72/prepare-egpu-boot-candidate.py'
spec = importlib.util.spec_from_file_location('egpu_boot', path)
egpu = importlib.util.module_from_spec(spec)
spec.loader.exec_module(egpu)


def tree(payload):
    size = 40 + len(payload)
    return b'\xd0\x0d\xfe\xed' + struct.pack('>I', size) + bytes(32) + payload


def fixture():
    ranges = b''.join(struct.pack('>7I', 0x43000000, 8, 0, h, 0, 2, 0)
                      for h in (12, 16, 20))
    return b'loader' + tree(b'apple,j314s\0' + ranges) + b''.join(tree(bytes([i])) for i in range(8)) + b'payload'


class CandidateTest(unittest.TestCase):
    def test_only_three_expected_bytes_change(self):
        data = fixture()
        new, receipt = egpu.compose(data)
        self.assertEqual(len(data), len(new))
        self.assertEqual(sum(a != b for a, b in zip(data, new)), 3)
        self.assertEqual(receipt['dtb_count'], 9)
        self.assertTrue(new.endswith(b'payload'))

    def test_missing_or_duplicate_ranges_are_refused(self):
        data = fixture()
        needle = struct.pack('>7I', 0x43000000, 8, 0, 12, 0, 2, 0)
        with self.assertRaisesRegex(ValueError, 'unexpected or ambiguous'):
            egpu.compose(data.replace(needle, bytes(len(needle))))
        with self.assertRaisesRegex(ValueError, 'unexpected or ambiguous'):
            egpu.compose(data.replace(bytes(32), needle + bytes(4), 1))


if __name__ == '__main__':
    unittest.main()
