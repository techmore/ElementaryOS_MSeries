#!/usr/bin/env python3
"""Offline validation only: no I2C device is opened."""
import ctypes
import errno
import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location(
    "inspector", Path(__file__).with_name("inspect-cd321x-io.py"))
inspector = importlib.util.module_from_spec(spec)
spec.loader.exec_module(inspector)


class CombinedReadTests(unittest.TestCase):
    def fake(self, responses):
        calls = []

        def ioctl(fd, operation, argument):
            self.assertEqual(operation, 0x0707)
            request = ctypes.cast(argument, ctypes.POINTER(inspector.I2CRdwr)).contents
            self.assertEqual(request.nmsgs, 2)
            address, read = request.msgs[0], request.msgs[1]
            self.assertEqual((address.addr, address.flags, address.len), (0x3F, 0, 1))
            self.assertEqual((read.addr, read.flags), (0x3F, 1))
            reg = address.buf[0]
            calls.append(reg)
            response = responses[reg]
            if isinstance(response, int):
                ctypes.set_errno(response)
                return -1
            self.assertEqual(len(response), read.len)
            for i, byte in enumerate(response):
                read.buf[i] = byte
            return 2

        return ioctl, calls

    def test_idle_reads_fixed_plan(self):
        inspector.validate_layout()
        ioctl, calls = self.fake({8: b"\x04\0\0\0\0", 26: b"\x08\x01\0\0\0",
                                  9: b"\x40\0"})
        records = inspector.snapshot(99, ioctl)
        self.assertEqual(calls, [8, 26, 9])
        self.assertEqual(records[1]["raw_hex"], "0801000000")
        self.assertEqual(records[1]["length_prefix"], 8)
        self.assertEqual(records[1]["value_le"], 1)

    def test_busy_or_short_command_skips_data(self):
        for cmd in (b"\x04SWDF", b"\x00\0\0\0\0"):
            ioctl, calls = self.fake({8: cmd, 26: b"\x04\0\0\0\0"})
            result = inspector.snapshot(99, ioctl)
            self.assertEqual(calls, [8, 26])
            self.assertTrue(result[2]["skipped"])

    def test_transport_errno_preserved(self):
        ioctl, calls = self.fake({8: errno.EIO, 26: errno.ETIMEDOUT})
        result = inspector.snapshot(99, ioctl)
        self.assertEqual([item["errno"] for item in result[:2]],
                         [errno.EIO, errno.ETIMEDOUT])
        self.assertEqual(calls, [8, 26])
        self.assertTrue(result[2]["skipped"])

    def test_partial_transfer_and_whitelist(self):
        with self.assertRaises(OSError):
            inspector.combined_read(99, 8, 5, lambda *args: 1)
        for reg, length in ((7, 5), (8, 6), (9, 5)):
            with self.assertRaises(ValueError):
                inspector.combined_read(99, reg, length, lambda *args: self.fail())

    def test_dry_run_never_opens_device(self):
        with patch.object(inspector, "validate_mapping", return_value={}), \
             patch("sys.argv", ["inspect-cd321x-io.py", "--dry-run"]), \
             patch.object(inspector.os, "open", side_effect=AssertionError("opened device")), \
             patch("builtins.print"):
            self.assertEqual(inspector.main(), 0)

    def test_mapping_rejects_wrong_driver_and_port(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            device = root / "bus/i2c/devices/0-003f"
            device.mkdir(parents=True)
            port = device / "typec/port2"
            port.mkdir(parents=True)
            (root / "class/typec").mkdir(parents=True)
            link = root / "class/typec/port2"
            link.symlink_to(port)
            driver = root / "bus/i2c/drivers/tps6598x"
            driver.mkdir(parents=True)
            driver_link = device / "driver"
            driver_link.symlink_to(driver)
            bus = root / "firmware/devicetree/base/soc/i2c@39b040000"
            pd = bus / "usb-pd@3f"
            pd.mkdir(parents=True)
            (device / "of_node").symlink_to(pd)
            (root / "bus/i2c/devices/i2c-0").mkdir()
            (root / "bus/i2c/devices/i2c-0/of_node").symlink_to(bus)
            self.assertEqual(inspector.validate_mapping(root)["typec_port"], "port2")
            wrong_driver = driver.parent / "wrong"
            wrong_driver.mkdir()
            driver_link.unlink()
            driver_link.symlink_to(wrong_driver)
            with self.assertRaises(RuntimeError):
                inspector.validate_mapping(root)
            driver_link.unlink()
            driver_link.symlink_to(driver)
            link.unlink()
            link.symlink_to(root)
            with self.assertRaises(RuntimeError):
                inspector.validate_mapping(root)


if __name__ == "__main__":
    unittest.main()
