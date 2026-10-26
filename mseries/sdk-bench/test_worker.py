import importlib.util
from pathlib import Path
import tempfile
import unittest

spec = importlib.util.spec_from_file_location('sdk_bench_worker', Path(__file__).with_name('worker.py'))
worker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(worker)

class WorkerBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.old_root, self.old_sdk, self.old_mode = worker.ROOT, worker.SDK, worker.MODE
        worker.ROOT = self.root / 'project'
        worker.SDK = self.root / 'sdk'
        worker.ROOT.mkdir()
        worker.SDK.mkdir()
        worker.MODE = 'sdk'

    def tearDown(self):
        worker.ROOT, worker.SDK, worker.MODE = self.old_root, self.old_sdk, self.old_mode
        self.temporary.cleanup()

    def test_model_paths_cannot_leave_project_or_change_runner_evidence(self):
        for path in ['/etc/passwd', '../outside.rs', 'src/../../outside.rs', '.cargo/config.toml', 'evidence/fake.json', 'target/main.rs']:
            with self.assertRaises(ValueError, msg=path):
                worker.project_path(path, write=True)
        (worker.ROOT / 'escape').symlink_to(worker.SDK, target_is_directory=True)
        with self.assertRaises(ValueError):
            worker.project_path('escape/overwritten.rs', write=True)

    def test_whole_write_batch_is_validated_before_any_file_is_written(self):
        with self.assertRaises(ValueError):
            worker.execute({'action': 'write', 'files': {'src/main.rs': 'fn main() {}', '../escape.rs': 'bad'}})
        self.assertFalse((worker.ROOT / 'src').exists())
        worker.execute({'action': 'write', 'files': {'src/main.rs': 'fn main() {}'}})
        self.assertEqual((worker.ROOT / 'src/main.rs').read_text(), 'fn main() {}')

    def test_sdk_reads_are_confined_and_baseline_cannot_use_sdk_tools(self):
        (worker.SDK / 'README.md').write_text('public SDK fixture')
        self.assertIn('public SDK fixture', worker.execute({'action': 'read', 'path': 'sdk/README.md'})['text'])
        with self.assertRaises(ValueError):
            worker.execute({'action': 'read', 'path': 'sdk/../outside'})
        worker.MODE = 'baseline'
        with self.assertRaises(ValueError):
            worker.execute({'action': 'read', 'path': 'sdk/README.md'})
        with self.assertRaises(ValueError):
            worker.execute({'action': 'run', 'command': 'describe'})

    def test_unknown_commands_and_large_files_are_refused(self):
        with self.assertRaises(ValueError):
            worker.execute({'action': 'run', 'command': 'sh -c dangerous'})
        with self.assertRaises(ValueError):
            worker.execute({'action': 'write', 'files': {'src/main.rs': 'x' * 100001}})

if __name__ == '__main__':
    unittest.main()
