#!/usr/bin/env python3
"""Check raw capture survives a decoder failure and preserves delegation."""
from pathlib import Path
import runpy
import unittest

install = runpy.run_path(str(Path(__file__).with_name("trace-dcp-raw.py")))["install_raw_dptx"]


class RawTests(unittest.TestCase):
    def service(self, fail=False):
        class Service:
            def __init__(self):
                self.logs = []
                self.calls = []

            def log(self, line):
                self.logs.append(line)

            def handle_cmd(self, group, command, data):
                self.calls.append((group, command, data))
                if fail:
                    raise ValueError("Unknown firmware encoding")
                return 42

            handle_reply = handle_cmd
            handle_notify = handle_cmd
            handle_notify_ack = handle_cmd
        return Service

    def test_exact_bytes_and_all_directions_are_preserved(self):
        cls = self.service()
        dumped = []
        install(cls, lambda data, print_fn: dumped.append(data))
        svc = cls()
        for method in ("handle_cmd", "handle_reply", "handle_notify", "handle_notify_ack"):
            self.assertEqual(getattr(svc, method)(0, 12, b"\x00\xff\x01"), 42)
        self.assertEqual(dumped, [b"\x00\xff\x01"] * 4)
        self.assertEqual(len(svc.calls), 4)

    def test_bytes_captured_before_decoder_raises(self):
        cls = self.service(fail=True)
        dumped = []
        install(cls, lambda data, print_fn: dumped.append(data))
        with self.assertRaises(ValueError):
            cls().handle_cmd(0, 12, b"\xab")
        self.assertEqual(dumped, [b"\xab"])

    def test_repeat_install_rejected(self):
        cls = self.service()
        install(cls, lambda *args, **kwargs: None)
        with self.assertRaises(ValueError):
            install(cls, lambda *args, **kwargs: None)


if __name__ == "__main__":
    unittest.main()
