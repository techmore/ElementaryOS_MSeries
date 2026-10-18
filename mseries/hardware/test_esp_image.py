"""Read a real FAT ESP using CI's mtools, without mounts or root."""
import importlib.util
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
VERIFY = ROOT / 'mseries/fairydust/debian/verify-m1n1-esp.py'
TOOLS = ('sfdisk', 'mformat', 'mmd', 'mcopy')
AVAILABLE = all(shutil.which(command) for command in TOOLS)


class EspTests(unittest.TestCase):
    def test_required_ci_dependencies(self):
        if os.environ.get('MSERIES_REQUIRE_ESP_TOOLS') == '1':
            self.assertTrue(AVAILABLE, 'CI must install fdisk and mtools')

    @unittest.skipUnless(AVAILABLE, 'real FAT ESP checks require fdisk and mtools (mandatory in CI)')
    def test_real_esp_matches_and_rejects_corruption(self):
        with tempfile.TemporaryDirectory() as t:
            d = Path(t); image = d / 'disk.raw'; expected = d / 'expected.bin'
            with image.open('wb') as f:
                f.truncate(80 * 1024 * 1024)
            subprocess.run(['sfdisk', '--no-reread', '--no-tell-kernel', str(image)],
                           input='label: gpt\nstart=2048,size=131072,type=U\n', text=True,
                           check=True, capture_output=True)
            fat = f'{image}@@1048576'
            subprocess.run(['mformat', '-i', fat, '-T', '131072', '-F', '::'], check=True)
            subprocess.run(['mmd', '-i', fat, '::/m1n1'], check=True)
            expected.write_bytes(b'MSERIES-SYNTHETIC-BOOT-PAYLOAD\0' * 32)
            subprocess.run(['mcopy', '-i', fat, str(expected), '::/m1n1/boot.bin'], check=True)
            command = [sys.executable, str(VERIFY), '--image', str(image), '--expected', str(expected)]
            p = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(p.returncode, 0, p.stderr)
            self.assertIn('PASS:', p.stdout)
            expected.write_bytes(b'wrong bytes')
            p = subprocess.run(command, capture_output=True, text=True)
            self.assertNotEqual(p.returncode, 0)
            self.assertIn('SHA-256 mismatch', p.stderr)
            expected.write_bytes(b'')
            subprocess.run(['mcopy', '-o', '-i', fat, str(expected), '::/m1n1/boot.bin'], check=True)
            p = subprocess.run(command, capture_output=True, text=True)
            self.assertNotEqual(p.returncode, 0)
            self.assertIn('empty', p.stderr)


if __name__ == '__main__':
    unittest.main()
