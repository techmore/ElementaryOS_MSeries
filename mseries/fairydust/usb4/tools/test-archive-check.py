#!/usr/bin/env python3
"""validate-dock-patches.py accepts the codeload tarball by hash and a git-archive copy only of the pinned commit."""
import importlib.util
import subprocess
import tempfile
import unittest
from pathlib import Path

spec = importlib.util.spec_from_file_location('vdp', Path(__file__).with_name('validate-dock-patches.py'))
vdp = importlib.util.module_from_spec(spec)
spec.loader.exec_module(vdp)


def git_archive(root):
    repo = root / 'repo'
    subprocess.run(['git', 'init', '-q', str(repo)], check=True)
    (repo / 'Makefile').write_text('all:\n')
    subprocess.run(['git', '-C', str(repo), 'add', '.'], check=True)
    subprocess.run(['git', '-C', str(repo), '-c', 'user.name=t', '-c', 'user.email=t@t', 'commit', '-qm', 'm'],
                   check=True)
    commit = subprocess.run(['git', '-C', str(repo), 'rev-parse', 'HEAD'], check=True, capture_output=True,
                            text=True).stdout.strip()
    out = root / 'src.tar.gz'
    subprocess.run(['git', '-C', str(repo), 'archive', '--format=tar.gz', f'--prefix=linux-{commit}/', '-o',
                    str(out), 'HEAD'], check=True)
    return out, commit


class ArchiveCheck(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_git_archive_of_the_pin_passes(self):
        out, commit = git_archive(self.root)
        real = vdp.PIN
        vdp.PIN = commit
        try:
            self.assertEqual(vdp.verify_archive(out, git_archive=True), {'archive_git_commit': commit})
        finally:
            vdp.PIN = real

    def test_git_archive_of_another_commit_fails(self):
        out, _ = git_archive(self.root)
        with self.assertRaises(ValueError):
            vdp.verify_archive(out, git_archive=True)

    def test_codeload_path_still_checks_the_hash(self):
        out, _ = git_archive(self.root)
        with self.assertRaises(ValueError):
            vdp.verify_archive(out)


if __name__ == '__main__':
    unittest.main()
