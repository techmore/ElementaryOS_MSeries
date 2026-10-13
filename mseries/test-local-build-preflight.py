import importlib.util
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('preflight', Path(__file__).with_name('local-build-preflight.py'))
p = importlib.util.module_from_spec(spec)
spec.loader.exec_module(p)


class PreflightTests(unittest.TestCase):
    @patch.object(p.platform, 'machine', return_value='aarch64')
    @patch.object(p.shutil, 'which', return_value='/usr/bin/tool')
    def test_disk_guard_boundary(self, *_):
        with tempfile.TemporaryDirectory() as directory:
            for free, ready in [(p.MIN_FREE-1, False), (p.MIN_FREE, True)]:
                with self.subTest(free=free), patch.object(p.shutil, 'disk_usage', return_value=SimpleNamespace(free=free)):
                    self.assertEqual(p.report(directory)['ready'], ready)

    def test_new_build_directory_checks_existing_filesystem(self):
        with tempfile.TemporaryDirectory() as directory:
            nested = Path(directory) / 'new' / 'build'
            self.assertEqual(p.existing_parent(nested), Path(directory).resolve())
            self.assertFalse(nested.exists())

    @patch.object(p.platform, 'machine', return_value='x86_64')
    @patch.object(p.shutil, 'which', return_value=None)
    @patch.object(p.shutil, 'disk_usage', return_value=SimpleNamespace(free=p.MIN_FREE))
    def test_tools_and_architecture_block_independently(self, *_):
        result = p.report(Path(__file__).parent)
        self.assertFalse(result['ready'])
        self.assertEqual(result['missing_tools'], list(p.TOOLS))
        self.assertEqual(len(result['blockers']), 2)


if __name__ == '__main__':
    unittest.main()
