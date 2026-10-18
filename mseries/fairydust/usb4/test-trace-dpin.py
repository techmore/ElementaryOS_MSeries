#!/usr/bin/env python3
"""Offline checks that trace preparation includes DP-IN and fails atomically."""
import runpy
from pathlib import Path
import unittest

install = runpy.run_path(str(Path(__file__).with_name("trace-dpin.py")))["install_dpin_trace"]


class FakeNode:
    def __init__(self, name, address):
        self.name = name
        self.reg = [(address, 0x4000)]

    def get_reg(self, index):
        return self.reg[index]


class FakeADT(dict):
    def __getitem__(self, path):
        if path == "/arm-io":
            return list(self.values())
        return super().__getitem__(path)


class FakeHV:
    def __init__(self):
        self.adt = FakeADT({"/arm-io/atc1-" + suffix: FakeNode("atc1-" + suffix, address)
                            for suffix, address in (("dpxbar", 0xb0304c000),
                                                    ("dpin0", 0xb01e50000),
                                                    ("dpin1", 0xb01e58000))})
        self.traced = []

    def trace_device(self, path, mode):
        self.traced.append((path, mode))


class TraceTests(unittest.TestCase):
    def test_captures_crossbar_and_both_dpin_blocks(self):
        hv = FakeHV()
        install(hv, 0xb0304c000)
        self.assertEqual([p.rsplit("-", 1)[1] for p, _ in hv.traced],
                         ["dpxbar", "dpin0", "dpin1"])

    def test_wrong_or_removed_target_fails_without_partial_capture(self):
        hv = FakeHV()
        with self.assertRaises(ValueError):
            install(hv, 0x50304c000)
        self.assertEqual(hv.traced, [])

    def test_missing_dpin_fails_without_partial_capture(self):
        hv = FakeHV()
        del hv.adt["/arm-io/atc1-dpin1"]
        with self.assertRaises(ValueError):
            install(hv, 0xb0304c000)
        self.assertEqual(hv.traced, [])


if __name__ == "__main__":
    unittest.main()
