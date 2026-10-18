#!/usr/bin/env python3
"""Frozen release history remains immutable across later release-pin updates."""
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

import check_freezes
import qualification as q
from release import HERE


class FrozenHistoryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self.tmp.name)
        self.root = self.repo / "mseries/aurora"
        self.root.mkdir(parents=True)
        shutil.copy2(HERE / "release.json", self.root / "release.json")
        shutil.copytree(HERE / "frozen", self.root / "frozen")
        shutil.copytree(HERE / "hardware-tests", self.root / "hardware-tests")
        self.git("init", "-q")
        self.git("add", ".")
        self.git("-c", "user.name=Fixture", "-c", "user.email=fixture@localhost", "-c", "commit.gpgsign=false", "-c", "core.hooksPath=/dev/null", "commit", "-qm", "frozen baseline")
        self.base = self.git("rev-parse", "HEAD").strip()

    def tearDown(self):
        self.tmp.cleanup()

    def git(self, *args):
        return subprocess.check_output(["git", *args], cwd=self.repo, text=True)

    def test_committed_frozen_release_and_chain_verify(self):
        self.assertIn("mseries-aurora20-j314s-2026.10.18-exp1", check_freezes.check(self.root, self.base))

    def test_even_a_recomputed_freeze_cannot_replace_an_existing_id(self):
        path = next((self.root / "frozen").glob("*.json"))
        data = json.loads(path.read_text()); data["distinct_boots"] = 99; path.write_text(json.dumps(data))
        with self.assertRaisesRegex(ValueError, "cannot change"):
            check_freezes.check(self.root, self.base)

    def test_deleting_a_frozen_release_is_rejected(self):
        next((self.root / "frozen").glob("*.json")).unlink()
        with self.assertRaisesRegex(ValueError, "cannot change"):
            check_freezes.check(self.root, self.base)

    def test_active_release_pin_updates_leave_old_freezes_verifiable(self):
        path = self.root / "release.json"
        data = json.loads(path.read_text()); data["kernel_source"] = "future kernel"; path.write_text(json.dumps(data))
        self.assertTrue(check_freezes.check(self.root, self.base))

    def test_new_release_id_can_be_added_without_changing_old_release(self):
        evidence = self.root / "hardware-tests/2026-10-18-j314s-aurora20.json"
        q.freeze("mseries-fixture-exp2", self.root / "frozen/pins/aurora20.json", [evidence], self.root / "frozen/mseries-fixture-exp2.json")
        self.assertEqual(len(check_freezes.check(self.root, self.base)), 2)


if __name__ == "__main__":
    unittest.main()
