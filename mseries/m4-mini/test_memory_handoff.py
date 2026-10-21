#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
import importlib.util
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

spec = importlib.util.spec_from_file_location('handoff', Path(__file__).with_name('check-memory-handoff.py'))
handoff = importlib.util.module_from_spec(spec)
spec.loader.exec_module(handoff)


@unittest.skipUnless(shutil.which('dtc') and shutil.which('fdtget'), 'dtc/fdtget required')
class MemoryBounds(unittest.TestCase):
    def check_map(self, size=4, extra='', board='apple,j773g'):
        source = ('/dts-v1/; / { #address-cells=<2>; #size-cells=<2>; compatible="' + board + '"; '
                  'memory@10000000000 { device_type="memory"; reg=<0x100 0 ' + str(size) + ' 0>; }; '
                  'reserved-memory { #address-cells=<2>; #size-cells=<2>; ranges; '
                  'ramoops@103e0000000 { compatible="ramoops"; reg=<0x103 0xe0000000 0 0x200000>; }; '
                  + extra + ' }; };')
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / 'input.dts').write_text(source)
            subprocess.run(['dtc', '-I', 'dts', '-O', 'dtb', '-o', str(root / 'input.dtb'),
                            str(root / 'input.dts')], capture_output=True, check=True)
            return handoff.check(root / 'input.dtb')

    def test_declared_16g_contains_ramoops(self):
        self.assertFalse(self.check_map()['hardware_validated'])

    def test_undersized_ram_rejected(self):
        with self.assertRaisesRegex(ValueError, 'outside declared'):
            self.check_map(size=2)

    def test_unfixed_zero_ram_rejected(self):
        with self.assertRaisesRegex(ValueError, 'zero'):
            self.check_map(size=0)

    def test_firmware_collision_rejected(self):
        with self.assertRaisesRegex(ValueError, 'overlaps another'):
            self.check_map(extra='fw@103e0010000 { reg=<0x103 0xe0010000 0 0x10000>; };')

    def test_other_board_rejected(self):
        with self.assertRaisesRegex(ValueError, 'J773g'):
            self.check_map(board='apple,j713')

    def test_unrelated_small_reservation_is_not_ram_alignment_gate(self):
        self.check_map(extra='fw@10000100000 { reg=<0x100 0x100000 0 0x1000>; };')


if __name__ == '__main__':
    unittest.main()
