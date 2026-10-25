#!/usr/bin/env python3
"""Exercise the Rust CLI against the established atomic-app Python behavior."""

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[3]
REFERENCE = ROOT / "mseries/atomic-app.py"


class Backend:
    def __init__(self, command):
        self.command = command

    def run(self, *args, check=True):
        return subprocess.run(
            [*self.command, *map(str, args)],
            check=check,
            capture_output=True,
            text=True,
            env=os.environ | {"LC_ALL": "C"},
        )

    def json(self, *args):
        return json.loads(self.run(*args).stdout)


class AtomicAppParity(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if len(sys.argv) != 2:
            raise RuntimeError("usage: test-parity.py PATH_TO_RUST_BINARY")
        cls.rust = Backend([str(Path(sys.argv[1]).resolve())])
        cls.python = Backend([sys.executable, str(REFERENCE)])

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.sources = []
        for name in ("old", "new"):
            source = self.base / name
            source.mkdir()
            (source / "start").write_text(f"#!/bin/sh\nprintf '{name}\\n'\n")
            (source / "start").chmod(0o755)
            (source / "resource.txt").write_text(name)
            os.utime(source / "resource.txt", (1_700_000_000, 1_700_000_000))
            (source / "resource-link").symlink_to("resource.txt")
            self.sources.append(source)

    def deploy(self, backend, root, source, digest):
        return backend.json(
            "--root", root, "--app", "demo", "deploy",
            "--source", source, "--entrypoint", "start",
            "--artifact-sha256", digest * 64,
            "--publisher-fingerprint", "test-publisher",
        )

    def launch(self, backend, root):
        return backend.run("--root", root, "--app", "demo", "run", "--", "--fixture-arg")

    def test_two_releases_status_launch_rollback_and_history_match(self):
        roots = {"python": self.base / "python-store", "rust": self.base / "rust-store"}
        backends = {"python": self.python, "rust": self.rust}
        for name, backend in backends.items():
            with self.subTest(backend=name):
                first = self.deploy(backend, roots[name], self.sources[0], "a")
                second = self.deploy(backend, roots[name], self.sources[1], "b")
                self.assertEqual(first["current"], second["previous"])
                self.assertEqual("new", self.launch(backend, roots[name]).stdout.strip())
                status = backend.json("--root", roots[name], "--app", "demo", "status")
                self.assertEqual("b" * 64, status["artifact_sha256"])
                self.assertEqual("test-publisher", status["publisher_fingerprint"])
                self.assertEqual("new", (Path(status["launch_root"]) / "resource.txt").read_text())
                self.assertTrue((Path(status["launch_root"]) / "resource-link").is_symlink())
                self.assertEqual(
                    (self.sources[1] / "resource.txt").stat().st_mtime_ns,
                    (Path(status["launch_root"]) / "resource.txt").stat().st_mtime_ns,
                )
                rolled = backend.json("--root", roots[name], "--app", "demo", "rollback")
                self.assertEqual(first["current"], rolled["current"])
                self.assertEqual("old", self.launch(backend, roots[name]).stdout.strip())
                self.assertEqual(2, len(list((roots[name] / "demo/releases").iterdir())))

    def test_failed_validation_leaves_previous_release_active(self):
        for name, backend in (("python", self.python), ("rust", self.rust)):
            with self.subTest(backend=name):
                root = self.base / f"{name}-failure-store"
                first = self.deploy(backend, root, self.sources[0], "a")
                unsafe = self.base / f"{name}-unsafe"
                unsafe.mkdir()
                (unsafe / "start").write_text("#!/bin/sh\nexit 0\n")
                (unsafe / "start").chmod(0o755)
                (unsafe / "escape").symlink_to("/etc/passwd")
                failed = backend.run(
                    "--root", root, "--app", "demo", "deploy",
                    "--source", unsafe, "--entrypoint", "start",
                    "--artifact-sha256", "c" * 64,
                    "--publisher-fingerprint", "test-publisher",
                    check=False,
                )
                self.assertNotEqual(0, failed.returncode)
                status = backend.json("--root", root, "--app", "demo", "status")
                self.assertEqual(first["current"], status["current"])
                self.assertEqual("old", self.launch(backend, root).stdout.strip())
                self.assertFalse(list((root / "demo").glob(".staging-*")))

    def test_prepared_launch_path_stays_on_its_original_release(self):
        for name, backend in (("python", self.python), ("rust", self.rust)):
            with self.subTest(backend=name):
                root = self.base / f"{name}-pinned-store"
                self.deploy(backend, root, self.sources[0], "a")
                old_launch = (root / "demo/current/app/start").resolve(strict=True)
                self.deploy(backend, root, self.sources[1], "b")
                self.assertEqual("old", subprocess.check_output([old_launch], text=True).strip())
                self.assertEqual("new", self.launch(backend, root).stdout.strip())

    def test_unsupported_source_object_never_changes_selector(self):
        for name, backend in (("python", self.python), ("rust", self.rust)):
            with self.subTest(backend=name):
                root = self.base / f"{name}-partial-store"
                first = self.deploy(backend, root, self.sources[0], "a")
                partial = self.base / f"{name}-partial-source"
                partial.mkdir()
                (partial / "start").write_text("#!/bin/sh\nexit 0\n")
                (partial / "start").chmod(0o755)
                os.mkfifo(partial / "unsupported")
                result = backend.run(
                    "--root", root, "--app", "demo", "deploy",
                    "--source", partial, "--entrypoint", "start",
                    "--artifact-sha256", "c" * 64,
                    "--publisher-fingerprint", "test-publisher",
                    check=False,
                )
                self.assertNotEqual(0, result.returncode)
                self.assertEqual(first["current"], backend.json("--root", root, "--app", "demo", "status")["current"])
                self.assertFalse(list((root / "demo").glob(".staging-*")))

    def test_external_current_selector_is_rejected(self):
        for name, backend in (("python", self.python), ("rust", self.rust)):
            with self.subTest(backend=name):
                root = self.base / f"{name}-escape-store"
                self.deploy(backend, root, self.sources[0], "a")
                current = root / "demo/current"
                current.unlink()
                outside = self.base / f"{name}-outside-generation"
                outside.mkdir()
                current.symlink_to(outside)
                result = backend.run("--root", root, "--app", "demo", "status", check=False)
                self.assertNotEqual(0, result.returncode)

    def test_missing_entrypoint_and_unavailable_rollback_fail_closed(self):
        for name, backend in (("python", self.python), ("rust", self.rust)):
            with self.subTest(backend=name):
                root = self.base / f"{name}-missing-store"
                no_previous = backend.run("--root", root, "--app", "demo", "rollback", check=False)
                self.assertNotEqual(0, no_previous.returncode)
                missing = backend.run(
                    "--root", root, "--app", "demo", "deploy",
                    "--source", self.sources[0], "--entrypoint", "absent",
                    "--artifact-sha256", "a" * 64,
                    "--publisher-fingerprint", "test-publisher",
                    check=False,
                )
                self.assertNotEqual(0, missing.returncode)
                status = backend.json("--root", root, "--app", "demo", "status")
                self.assertIsNone(status["current"])

    def test_concurrent_updates_serialize_previous_generation(self):
        for name, backend in (("python", self.python), ("rust", self.rust)):
            with self.subTest(backend=name):
                root = self.base / f"{name}-concurrent-store"
                first = self.deploy(backend, root, self.sources[0], "a")
                self.assertIsNotNone(first["current"])
                processes = [
                    subprocess.Popen(
                        [*backend.command, "--root", str(root), "--app", "demo", "deploy",
                         "--source", str(source), "--entrypoint", "start",
                         "--artifact-sha256", str(index + 2) * 64,
                         "--publisher-fingerprint", "concurrent"],
                        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                    )
                    for index, source in enumerate(self.sources)
                ]
                for process in processes:
                    stdout, stderr = process.communicate(timeout=15)
                    self.assertEqual(0, process.returncode, stdout + stderr)
                status = backend.json("--root", root, "--app", "demo", "status")
                self.assertIsNotNone(status["previous"])
                active = self.launch(backend, root).stdout.strip()
                backend.json("--root", root, "--app", "demo", "rollback")
                self.assertNotEqual(active, self.launch(backend, root).stdout.strip())

    def test_invalid_digest_and_app_name_are_rejected(self):
        bad_digest = self.rust.run(
            "--root", self.base / "bad-digest", "--app", "demo", "deploy",
            "--source", self.sources[0], "--entrypoint", "start",
            "--artifact-sha256", "F" * 64,
            "--publisher-fingerprint", "test", check=False,
        )
        self.assertNotEqual(0, bad_digest.returncode)
        bad_app = self.rust.run("--root", self.base / "bad-app", "--app", "../escape", "status", check=False)
        self.assertNotEqual(0, bad_app.returncode)


if __name__ == "__main__":
    unittest.main(argv=[sys.argv[0]])
