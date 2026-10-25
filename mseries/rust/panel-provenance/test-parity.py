#!/usr/bin/env python3
"""Compare Rust panel provenance commands with the shipped Python tools."""

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[3]
PINS = ROOT / "mseries/panel-factory-pins.json"
PY_VERIFY = ROOT / "mseries/panel/verify-package-versions"
PY_RECORD = ROOT / "mseries/panel/record-artifact"
BINARY = None


def run(command, env=None):
    return subprocess.run(command, text=True, capture_output=True, env=env)


class PanelProvenanceParity(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pins = json.loads(PINS.read_text())
        cls.temp = tempfile.TemporaryDirectory(prefix="panel-parity-")
        cls.base = Path(cls.temp.name)
        cls.mockbin = cls.base / "mock-bin"
        cls.mockbin.mkdir()
        query = cls.mockbin / "dpkg-query"
        query.write_text(
            "#!/bin/sh\n"
            "case \"$4\" in\n"
            "  io.elementary.panel.network) version=8.0.1-1;;\n"
            "  io.elementary.quick-settings) version=1.4.0-1;;\n"
            "  io.elementary.panel.sound) version=8.0.3-1;;\n"
            "  io.elementary.panel.keyboard) version=2.4.2-1;;\n"
            "  *) exit 1;;\n"
            "esac\n"
            "if [ \"${BAD_DPKG_PACKAGE:-}\" = \"$4\" ]; then version=99.0; fi\n"
            "printf 'installed\\t%s\\n' \"$version\"\n"
        )
        query.chmod(0o755)
        cls.env = {**os.environ, "PATH": f"{cls.mockbin}:{os.environ.get('PATH', '')}"}

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def make_root(self, label):
        root = self.base / label
        shutil.rmtree(root, ignore_errors=True)
        root.mkdir()
        for entry in self.pins["indicators"]:
            plugin = root / entry["plugin"]
            plugin.parent.mkdir(parents=True, exist_ok=True)
            plugin.write_bytes((entry["name"] + " plugin fixture\n").encode())
        return root

    def record_python_all(self, root):
        for entry in self.pins["indicators"]:
            result = run([
                sys.executable, str(PY_RECORD), "--root", str(root), "--pins", str(PINS),
                "--name", entry["name"], "--commit", entry["commit"],
            ])
            self.assertEqual(result.returncode, 0, result.stderr)

    def test_record_artifact_output_matches(self):
        python_root = self.make_root("record-python")
        rust_root = self.make_root("record-rust")
        entry = self.pins["indicators"][0]
        python = run([
            sys.executable, str(PY_RECORD), "--root", str(python_root), "--pins", str(PINS),
            "--name", entry["name"], "--commit", entry["commit"],
        ])
        rust = run([
            str(BINARY), "record", "--root", str(rust_root), "--pins", str(PINS),
            "--name", entry["name"], "--commit", entry["commit"],
        ])
        self.assertEqual((python.returncode, rust.returncode), (0, 0), rust.stderr)
        output = Path("usr/share/mseries/panel-artifacts") / f"{entry['name']}.json"
        self.assertEqual(json.loads((python_root / output).read_text()), json.loads((rust_root / output).read_text()))

    def test_verification_and_only_filter_match(self):
        root = self.make_root("verify-valid")
        self.record_python_all(root)
        python = run([sys.executable, str(PY_VERIFY), "--root", str(root), "--pins", str(PINS)], self.env)
        rust = run([str(BINARY), "verify", "--root", str(root), "--pins", str(PINS)], self.env)
        self.assertEqual((python.returncode, python.stdout, python.stderr), (rust.returncode, rust.stdout, rust.stderr))

        alias = self.base / "verify-panel-packages"
        alias.unlink(missing_ok=True)
        alias.symlink_to(BINARY)
        rust = run([str(alias), "--root", str(root), "--pins", str(PINS)], self.env)
        self.assertEqual((python.returncode, python.stdout, python.stderr), (rust.returncode, rust.stdout, rust.stderr))

        python = run([sys.executable, str(PY_VERIFY), "--root", str(root), "--pins", str(PINS), "--only", "network"], self.env)
        rust = run([str(BINARY), "verify", "--root", str(root), "--pins", str(PINS), "--only", "network"], self.env)
        self.assertEqual((python.returncode, python.stdout, python.stderr), (rust.returncode, rust.stdout, rust.stderr))

    def test_skip_plugins_and_package_version_failure_match(self):
        root = self.make_root("verify-skipped")
        python = run([sys.executable, str(PY_VERIFY), "--root", str(root), "--pins", str(PINS), "--skip-plugins"], self.env)
        rust = run([str(BINARY), "verify", "--root", str(root), "--pins", str(PINS), "--skip-plugins"], self.env)
        self.assertEqual((python.returncode, python.stdout, python.stderr), (rust.returncode, rust.stdout, rust.stderr))

        self.record_python_all(root)
        bad_env = {**self.env, "BAD_DPKG_PACKAGE": "io.elementary.panel.sound"}
        python = run([sys.executable, str(PY_VERIFY), "--root", str(root), "--pins", str(PINS)], bad_env)
        rust = run([str(BINARY), "verify", "--root", str(root), "--pins", str(PINS)], bad_env)
        self.assertEqual((python.returncode, python.stdout, python.stderr), (rust.returncode, rust.stdout, rust.stderr))

    def test_missing_plugin_and_bad_digest_fail_with_same_contract(self):
        root = self.make_root("verify-bad-artifact")
        self.record_python_all(root)
        entry = self.pins["indicators"][1]
        artifact = root / entry["plugin"]
        original = artifact.read_bytes()
        artifact.unlink()
        python = run([sys.executable, str(PY_VERIFY), "--root", str(root), "--pins", str(PINS)], self.env)
        rust = run([str(BINARY), "verify", "--root", str(root), "--pins", str(PINS)], self.env)
        self.assertEqual((python.returncode, python.stdout, python.stderr), (rust.returncode, rust.stdout, rust.stderr))

        artifact.write_bytes(original)
        artifact.write_text("tampered plugin\n")
        python = run([sys.executable, str(PY_VERIFY), "--root", str(root), "--pins", str(PINS)], self.env)
        rust = run([str(BINARY), "verify", "--root", str(root), "--pins", str(PINS)], self.env)
        self.assertEqual((python.returncode, python.stdout, python.stderr), (rust.returncode, rust.stdout, rust.stderr))

    def test_usage_errors_keep_argparse_exit_status(self):
        root = self.make_root("usage-errors")
        python = run([sys.executable, str(PY_VERIFY), "--root", str(root), "--pins", str(PINS), "--only", "unknown"], self.env)
        rust = run([str(BINARY), "verify", "--root", str(root), "--pins", str(PINS), "--only", "unknown"], self.env)
        self.assertEqual((python.returncode, rust.returncode), (2, 2))
        self.assertIn("Unknown indicators", python.stderr)
        self.assertIn("Unknown indicators", rust.stderr)

        entry = self.pins["indicators"][0]
        python = run([sys.executable, str(PY_RECORD), "--root", str(root), "--pins", str(PINS), "--name", entry["name"], "--commit", "wrong"], self.env)
        rust = run([str(BINARY), "record", "--root", str(root), "--pins", str(PINS), "--name", entry["name"], "--commit", "wrong"], self.env)
        self.assertEqual((python.returncode, rust.returncode), (2, 2))

if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("usage: test-parity.py /path/to/mseries-panel-provenance-rs")
    BINARY = Path(sys.argv.pop()).resolve()
    unittest.main()
