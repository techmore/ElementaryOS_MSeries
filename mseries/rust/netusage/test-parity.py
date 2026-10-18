#!/usr/bin/env python3
"""Compare Rust and legacy Python socket attribution on identical `ss` fixtures."""

import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[3]
LEGACY = ROOT / "mseries/netspeed/netusage/netusage.py"
CASES = {
    "both counters": 'ESTAB 0 0 10.0.0.2:443 93.184.216.34:443 users:("curl",pid=424242,fd=3) cubic bytes_sent:321 bytes_received:654\n',
    "receive only": 'ESTAB 0 0 10.0.0.2:5000 1.1.1.1:443 users:("browser",pid=424243,fd=3) bytes_received:75\n',
    "send only and unowned socket": "ESTAB 0 0 10.0.0.2:6000 8.8.8.8:53 cubic bytes_sent:9\n",
    "IPv6 peer": 'ESTAB 0 0 [fe80::1%en0]:443 [2001:db8::8]:443 users:("client",pid=424244,fd=3) bytes_sent:17 bytes_received:29\n',
    "loopback and sockets without counters":
        'ESTAB 0 0 127.0.0.1:22 127.0.0.1:443 users:("ssh",pid=424245,fd=1) bytes_sent:1\n'
        'ESTAB 0 0 10.0.0.2:443 93.184.216.34:443 users:("curl",pid=424242,fd=3) cubic\n',
}
BINARY = None


def load_legacy():
    spec = importlib.util.spec_from_file_location("legacy_netusage", LEGACY)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def rust_rows(binary, fixture):
    result = subprocess.run(
        [str(binary), "--parse-ss-json"], input=fixture, text=True,
        capture_output=True, check=True,
    )
    rows = json.loads(result.stdout)
    return {
        (row["local"], row["peer"]):
        (row["proc"], row["host"], row["rx"], row["tx"])
        for row in rows
    }


class SocketParserParity(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.binary = BINARY
        cls.legacy = load_legacy()

    def test_rust_socket_parser_matches_python(self):
        for label, fixture in CASES.items():
            with self.subTest(case=label):
                completed = subprocess.CompletedProcess(["ss"], 0, stdout=fixture, stderr="")
                with mock.patch.object(self.legacy.subprocess, "run", return_value=completed):
                    python_result = self.legacy.read_sockets()
                actual = rust_rows(self.binary, fixture)
                expected = {
                    key: (proc, host, rx, tx)
                    for key, (proc, host, rx, tx) in python_result.items()
                }
                self.assertEqual(actual, expected)


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("usage: test-parity.py /path/to/mseries-netusage-rs")
    BINARY = Path(sys.argv.pop()).resolve()
    unittest.main()
