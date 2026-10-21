#!/usr/bin/env python3
"""Offline provenance checks; no VM, packages, sudo or host install."""
import pathlib
import subprocess
import tempfile
import unittest

HELPER = pathlib.Path(__file__).with_name('muvm-source.sh')


def git(root, *args):
    return subprocess.check_output(['git', '-C', str(root), *args], stderr=subprocess.DEVNULL).decode().strip()


class SourceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='muvm source ')
        self.addCleanup(self.tmp.cleanup)
        self.root = pathlib.Path(self.tmp.name)
        self.upstream = self.root / 'upstream'
        self.upstream.mkdir()
        git(self.upstream, 'init', '-q')
        git(self.upstream, 'config', 'user.name', 'Fixture')
        git(self.upstream, 'config', 'user.email', 'fixture@example.invalid')
        (self.upstream / 'source').write_text('original\n')
        (self.upstream / '.gitignore').write_text('build/\n')
        git(self.upstream, 'add', '.')
        git(self.upstream, 'commit', '-qm', 'fixture')
        git(self.upstream, 'tag', 'v1')
        self.commit = git(self.upstream, 'rev-parse', 'HEAD')
        self.url = self.upstream.as_uri()
        self.cache = self.root / 'cache'

    def run_helper(self, commit=None, success=True):
        result = subprocess.run(['bash', '-c', 'source "$1"; mseries_muvm_source "$2" "$3" v1 "$4"',
                                 'fixture', str(HELPER), self.url, str(self.cache), commit or self.commit],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode == 0, success, result.stderr)
        return result

    def test_new_clone_and_unchanged_cache(self):
        self.run_helper()
        self.assertEqual(git(self.cache, 'rev-parse', 'HEAD'), self.commit)
        self.run_helper()

    def test_ignored_build_outputs_preserved(self):
        self.run_helper()
        (self.cache / 'build').mkdir()
        output = self.cache / 'build' / 'object'
        output.write_text('built')
        self.run_helper()
        self.assertEqual(output.read_text(), 'built')

    def test_dirty_tracked_cache_refused_and_preserved(self):
        self.run_helper()
        (self.cache / 'source').write_text('owner edits')
        self.run_helper(success=False)
        self.assertEqual((self.cache / 'source').read_text(), 'owner edits')

    def test_untracked_source_refused(self):
        self.run_helper()
        (self.cache / 'new-source').write_text('unreviewed')
        self.run_helper(success=False)
        self.assertTrue((self.cache / 'new-source').exists())

    def test_wrong_origin_refused(self):
        self.run_helper()
        git(self.cache, 'remote', 'set-url', 'origin', 'https://example.invalid/other.git')
        self.run_helper(success=False)

    def test_wrong_head_refused(self):
        self.run_helper()
        self.run_helper(commit='0' * 40, success=False)
        self.assertEqual(git(self.cache, 'rev-parse', 'HEAD'), self.commit)

    def test_tag_mismatch_does_not_publish_cache(self):
        self.run_helper(commit='0' * 40, success=False)
        self.assertFalse(self.cache.exists())
        self.assertEqual(list(self.root.glob('cache.download.*')), [])

    def test_unrelated_directory_refused(self):
        self.cache.mkdir()
        (self.cache / 'keep').write_text('owner')
        self.run_helper(success=False)
        self.assertEqual((self.cache / 'keep').read_text(), 'owner')

    def test_symlink_cache_refused(self):
        self.cache.symlink_to(self.upstream, target_is_directory=True)
        self.run_helper(success=False)
        self.assertTrue(self.cache.is_symlink())

    def test_invalid_pin_refused(self):
        self.run_helper(commit='v1', success=False)
        self.assertFalse(self.cache.exists())

    def test_installer_verifies_before_privileged_work(self):
        text = HELPER.with_name('install-muvm.sh').read_text()
        start = text.index('mseries_muvm_source ')
        self.assertLess(start, text.index('sudo install -Dm644'))
        self.assertLess(start, text.index('sudo apt-get install'))
        self.assertNotIn('clone() {', text)


if __name__ == '__main__':
    unittest.main()
