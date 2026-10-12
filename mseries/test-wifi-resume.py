#!/usr/bin/python3
"""Exercise recovery policy with mock commands; never touch real hardware."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / "mkosi.images/apple-silicon/mkosi.extra/usr/sbin/mseries-wifi-resume-fix"


class RecoveryTests(unittest.TestCase):
    def run_case(self, radio, state, unload_fails=False):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            commands = {
                "uname": "echo aarch64",
                "lspci": "echo 'Network controller [14e4:4425]'",
                "nmcli": f'if [ "$1" = radio ]; then echo {radio}; else echo "ethernet:connected"; echo "wifi:{state}"; fi',
                "journalctl": "exit 0",
                "sleep": "exit 0",
                "logger": "exit 0",
                # brcmfmac is held by its vendor module, which must be removed and loaded back too
                "lsmod": "echo 'Module Size Used by'; echo 'brcmfmac_wcc 1 0'; echo 'brcmfmac 1 1 brcmfmac_wcc'",
                "modprobe": 'echo "$*" >> "$CALLS"\n' + ('exit 1' if unload_fails else 'exit 0'),
            }
            for name, body in commands.items():
                file = root / name
                file.write_text("#!/bin/sh\n" + body + "\n")
                file.chmod(0o755)
            calls = root / "calls"
            result = subprocess.run(["/bin/bash", str(SCRIPT)], env={**os.environ,
                "PATH": f"{root}:/usr/bin:/bin", "CALLS": str(calls)}, capture_output=True, text=True)
            return result.returncode, calls.read_text() if calls.exists() else ""

    def test_disabled_radio_is_respected(self):
        self.assertEqual(self.run_case("disabled", "disconnected"), (0, ""))

    def test_connected_wifi_is_untouched(self):
        self.assertEqual(self.run_case("enabled", "connected"), (0, ""))

    def test_ethernet_does_not_hide_disconnected_wifi(self):
        self.assertEqual(self.run_case("enabled", "disconnected"), (0, "-r --remove-holders brcmfmac\nbrcmfmac\nbrcmfmac_wcc\n"))

    def test_failed_unload_stops_recovery(self):
        self.assertEqual(self.run_case("enabled", "disconnected", True), (1, "-r --remove-holders brcmfmac\n"))


if __name__ == "__main__":
    unittest.main()
