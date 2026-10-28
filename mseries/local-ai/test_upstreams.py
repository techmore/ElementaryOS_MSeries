#!/usr/bin/env python3
"""upstreams.json stays the one list of pins and patches, and upstream-step.py sorts patches right."""
import importlib.util
import json
import re
import subprocess
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("upstream_step", HERE / "upstream-step.py")
step = importlib.util.module_from_spec(spec)
spec.loader.exec_module(step)
DATA = json.loads((HERE / "upstreams.json").read_text())["upstreams"]


class ManifestTests(unittest.TestCase):
    def test_every_patch_is_listed_once_and_exists(self):
        listed = [p["file"] for up in DATA.values() for p in up["patches"]]
        self.assertEqual(len(listed), len(set(listed)))
        for f in listed:
            self.assertTrue((HERE / f).is_file(), f)
        on_disk = {str(p.relative_to(HERE)) for p in (HERE / "patches").glob("*.patch")}
        on_disk |= {p.name for p in HERE.glob("*.patch")}
        self.assertEqual(on_disk, set(listed), "a .patch file is not in upstreams.json (or the reverse)")

    def test_patch_kinds(self):
        for up in DATA.values():
            for p in up["patches"]:
                self.assertIn(p["kind"], ("ours", "port", "vendored"), p["file"])
                if p["kind"] == "ours":
                    self.assertIn("upstream_pr", p, p["file"])

    def test_install_checkouts_match_pins(self):
        text = (HERE / "install.sh").read_text()
        for name, up in DATA.items():
            if "install_checkout" in up:
                lines = re.findall(rf"^checkout {re.escape(up['install_checkout'])} \S+ (\S+)$", text, re.M)
                self.assertEqual(lines, [up["pin"]], name)

    def test_serve_patch_reads_the_manifest(self):
        text = (HERE / "serve-patch.sh").read_text()
        self.assertIn("upstreams.json", text)
        self.assertNotRegex(text, r"mlx-lm-[0-9.]+-[a-z-]+\.patch", "serve-patch.sh hard-codes a patch again")


class ClassifyTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(dir=Path.home() / ".cache") if (Path.home() / ".cache").is_dir() \
            else tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.tree = self.root / "tree"
        self.tree.mkdir()
        subprocess.run(["git", "init", "-q", str(self.tree)], check=True)
        (self.tree / "a.txt").write_text("one\ntwo\nthree\n")

    def tearDown(self):
        self.tmp.cleanup()

    def patch(self, before, after):
        (self.root / "x").mkdir(exist_ok=True)
        (self.root / "y").mkdir(exist_ok=True)
        (self.root / "x/a.txt").write_text(before)
        (self.root / "y/a.txt").write_text(after)
        diff = subprocess.run(["git", "diff", "--no-index", "x/a.txt", "y/a.txt"], cwd=self.root,
                              text=True, capture_output=True).stdout
        diff = diff.replace("a/x/a.txt", "a/a.txt").replace("b/y/a.txt", "b/a.txt")
        path = self.root / "p.patch"
        path.write_text(diff)
        return path

    def test_keep_absorbed_conflict(self):
        base = "one\ntwo\nthree\n"
        p = self.patch(base, "one\nTWO\nthree\n")
        self.assertEqual(step.classify(self.tree, p), "keep")
        (self.tree / "a.txt").write_text("one\nTWO\nthree\n")
        self.assertEqual(step.classify(self.tree, p), "absorbed")
        (self.tree / "a.txt").write_text("one\nzwei\nthree\n")
        self.assertEqual(step.classify(self.tree, p), "conflict")

    def test_versioned_rename(self):
        self.assertEqual(step.versioned("mlx-lm", "v0.31.3", "v0.32.0", "patches/mlx-lm-0.31.3-x.patch"),
                         "patches/mlx-lm-0.32.0-x.patch")
        self.assertEqual(step.versioned("coreglass", "abc", "def", "coreglass-local.patch"),
                         "coreglass-local.patch")


if __name__ == "__main__":
    unittest.main()
