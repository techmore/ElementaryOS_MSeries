import contextlib
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('trial_capture', Path(__file__).parent / 'trial/capture-session.py')
trial = importlib.util.module_from_spec(spec); spec.loader.exec_module(trial)


class TrialCaptureTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.root = Path(self.tmp.name)
        self.image = self.root / 'Image'; self.image.write_bytes(b'image')
        self.boot = self.root / 'boot.bin'; self.boot.write_bytes(b'boot')
        self.output = self.root / 'records'
        self.config = self.root / 'config.json'
        self.data = {'output': str(self.output), 'boot_image': str(self.boot), 'boot_image_sha256': trial.q.digest(self.boot),
                     'profiles': {'test-kernel': {'role': 'candidate', 'kernel_image': str(self.image),
                                                'kernel_image_sha256': trial.q.digest(self.image), 'module_hashes': {}}}}
        self.config.write_text(json.dumps(self.data))

    def tearDown(self):
        self.tmp.cleanup()

    def read(self, path):
        return 'test-kernel' if str(path).endswith('osrelease') else 'boot-fixture'

    def test_unlisted_kernel_is_not_tested_or_marked(self):
        with patch.object(trial.q, 'read', return_value='other-kernel'), patch.object(trial.q, 'collect') as collect, contextlib.redirect_stdout(io.StringIO()):
            trial.capture(self.config)
        collect.assert_not_called(); self.assertFalse(self.output.exists())

    def test_changed_image_fails_before_any_hardware_capture(self):
        self.image.write_bytes(b'replaced')
        with patch.object(trial.q, 'read', side_effect=self.read), patch.object(trial.q, 'collect') as collect:
            with self.assertRaisesRegex(ValueError, 'identity changed'):
                trial.capture(self.config)
        collect.assert_not_called()
        status = json.loads((self.output / 'test-kernel/boot-fixture/status.json').read_text())
        self.assertEqual(status['status'], 'failed-scoped-capture')
        self.assertFalse(status['full_hardware_qualification'])

    def test_wrong_live_build_id_is_refused_before_capture(self):
        with patch.object(trial.q, 'read', side_effect=self.read), patch.object(trial.q, 'live_kernel_identity', return_value={'kernel_image_matches_live_build_id': False}), patch.object(trial.q, 'collect') as collect:
            with self.assertRaisesRegex(ValueError, 'running build ID'):
                trial.capture(self.config)
        collect.assert_not_called()

    def test_failed_kernel_health_retains_evidence_and_skips_gpu_smoke(self):
        original_read = Path.read_text
        def read_text(path, *args, **kwargs):
            return '600 900' if str(path) == '/proc/uptime' else original_read(path, *args, **kwargs)
        with patch.object(trial.q, 'read', side_effect=self.read), patch.object(trial.q, 'live_kernel_identity', return_value={'kernel_image_matches_live_build_id': True}), patch.object(trial.q, 'read_active', return_value={'available': True}), patch.object(trial, 'cpu', return_value=[0] * 8), patch.object(trial, 'inventory', return_value={}), patch.object(Path, 'read_text', read_text), patch.object(trial.subprocess, 'run') as run:
            def failed_record(*args):
                record = {'checks': {'kernel_severe_log': {'result': 'fail'}}}
                (self.output / 'test-kernel/boot-fixture/hardware.json').write_text(json.dumps(record))
                return record
            with patch.object(trial.q, 'collect', side_effect=failed_record):
                with self.assertRaisesRegex(ValueError, 'skipped GPU'):
                    trial.capture(self.config)
        self.assertEqual(run.call_count, 1)  # journal read only; no active smoke subprocess
        self.assertEqual(run.call_args.args[0][0], 'journalctl')
        self.assertTrue((self.output / 'test-kernel/boot-fixture/hardware.json').exists())
        self.assertFalse((self.output / 'test-kernel/boot-fixture/complete.json').exists())

    def test_timer_cannot_duplicate_a_completed_boot_capture(self):
        output = self.output / 'test-kernel/boot-fixture'; output.mkdir(parents=True)
        (output / 'complete.json').write_text('original completed receipt')
        with patch.object(trial.q, 'read', side_effect=self.read), patch.object(trial.q, 'collect') as collect, contextlib.redirect_stdout(io.StringIO()):
            trial.capture(self.config)
        collect.assert_not_called()
        self.assertEqual((output / 'complete.json').read_text(), 'original completed receipt')
