#!/usr/bin/env python3
"""Offline fixtures: address translation, privacy filtering, malformed ADTs."""
import importlib.util
from pathlib import Path
import plistlib
import struct
import sys
import unittest

spec = importlib.util.spec_from_file_location("dpin_adt", Path(__file__).with_name("inspect-dpin-adt.py"))
adt = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = adt
spec.loader.exec_module(adt)


def integer(value):
    return struct.pack("<I", value)


def packed(props, children=()):
    data = struct.pack("<II", len(props), len(children))
    for name, value in props.items():
        data += name.encode().ljust(32, b"\0") + integer(len(value))
        data += value + b"\0" * (-len(value) % 4)
    return data + b"".join(children)


def fixture():
    dpin = packed({"name": b"atc1-dpin0\0", "compatible": b"atc-dpin,t6000\0",
                   "reg": struct.pack("<QQ", 0x1e50000, 0x4000),
                   "acio-parent": integer(7), "transport-index": integer(0),
                   "interrupts": integer(1357), "clock-ids": integer(3) + integer(8)})
    acio = packed({"name": b"acio1\0", "AAPL,phandle": integer(7)})
    unrelated = packed({"name": b"chosen\0", "serial-number": b"PRIVATE-SERIAL\0"})
    armio = packed({"name": b"arm-io\0", "#address-cells": integer(2),
                    "#size-cells": integer(2),
                    "ranges": struct.pack("<QQQ", 0, 0xb00000000, 0x40000000)},
                   [dpin, acio])
    return packed({"name": b"device-tree\0"}, [armio, unrelated])


class InspectionTests(unittest.TestCase):
    def test_ioreg_archive_preserves_ranges_and_phandles(self):
        archive = [{"IORegistryEntryName": "Root", "IOPlatformSerialNumber": "PRIVATE",
                    "IORegistryEntryChildren": [{"name": b"arm-io\0",
                        "ranges": struct.pack("<QQQ", 0, 0xb00000000, 0x40000000),
                        "IORegistryEntryChildren": [
                            {"IORegistryEntryName": "atc1-dpin0@1e50000",
                             "reg": struct.pack("<QQ", 0x1e50000, 0x4000),
                             "acio-parent": integer(7)},
                            {"name": b"acio1\0", "AAPL,phandle": integer(7)}]}]}]
        nodes = adt.summarize(adt.parse_ioreg(plistlib.dumps(archive)))
        self.assertEqual(nodes[0]["registers"][0]["address"], "0xb01e50000")
        self.assertEqual(nodes[0]["acio-parent"]["path"], "/arm-io/acio1")
        self.assertNotIn("PRIVATE", str(nodes))

    def test_ioreg_rejects_ambiguous_archive(self):
        for archive in ([], [{}, {}], [{"IORegistryEntryName": "Root",
                                         "IORegistryEntryChildren": "bad"}]):
            with self.subTest(archive=archive), self.assertRaises(ValueError):
                adt.parse_ioreg(plistlib.dumps(archive))

    def test_translates_bus_address_and_resolves_relationship(self):
        nodes = adt.summarize(adt.parse_adt(fixture()))
        self.assertEqual(len(nodes), 1)
        self.assertEqual(nodes[0]["registers"][0]["address"], "0xb01e50000")
        self.assertEqual(nodes[0]["acio-parent"]["path"], "/arm-io/acio1")
        self.assertEqual(nodes[0]["transport-index"], 0)
        self.assertEqual(nodes[0]["interrupts"], [1357])
        self.assertEqual(nodes[0]["clock-ids"], [3, 8])

    def test_omits_unrelated_identity_properties(self):
        text = str(adt.summarize(adt.parse_adt(fixture())))
        self.assertNotIn("PRIVATE-SERIAL", text)
        self.assertNotIn("chosen", text)

    def test_rejects_truncated_property_and_children(self):
        for size in (0, 7, 60, len(fixture()) - 1):
            with self.subTest(size=size), self.assertRaises(ValueError):
                adt.parse_adt(fixture()[:size])

    def test_rejects_wrong_input_and_missing_nodes(self):
        with self.assertRaises(ValueError):
            adt.parse_adt(struct.pack("<II", 0xffffffff, 0))
        with self.assertRaises(ValueError):
            adt.summarize(adt.parse_adt(packed({"name": b"root\0"})))


if __name__ == "__main__":
    unittest.main()
