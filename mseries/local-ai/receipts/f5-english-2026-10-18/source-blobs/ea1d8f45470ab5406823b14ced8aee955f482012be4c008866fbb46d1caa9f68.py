"""Exercise the real controller with blocked factories/RPCs; no native model/audio."""
import importlib.util
from pathlib import Path
import sys
import threading
import unittest
from unittest.mock import MagicMock, Mock, patch

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
spec = importlib.util.spec_from_file_location('dictation_stream_lifecycle', HERE / 'stream-dictate.py')
stream = importlib.util.module_from_spec(spec)
# None of these lifecycle tests use NumPy or load a native SDK.
with patch.dict(sys.modules, {'numpy': Mock()}): spec.loader.exec_module(stream)


class StreamTests(unittest.TestCase):
    def setUp(self):
        self.stack = []
        for name, value in [('Typer', Mock()), ('load_policy', Mock(return_value={})),
                            ('resource_reasons', Mock(return_value=[])), ('status', Mock()),
                            ('notify', Mock()), ('tone', Mock()), ('input_call', Mock(return_value='token')),
                            ('ENGINE', 'stream'), ('OUTPUT', 'ibus'), ('TEST_INSERT', False), ('DRY', False)]:
            p = patch.object(stream, name, value)
            self.stack.append(p); p.start()
        stream.Typer.return_value.q.unfinished_tasks = 0
        self.model = Mock()
        self.factory = patch.object(stream.Dictation, 'load_model', Mock(return_value=self.model))
        self.factory.start()
        self.d = stream.Dictation()
        self.d.run = Mock()

    def tearDown(self):
        self.d.stop_evt.set()
        if self.d.worker: self.d.worker.join(3)
        self.factory.stop()
        for p in reversed(self.stack): p.stop()

    def finish(self):
        self.d.worker.join(3)
        self.assertFalse(self.d.worker.is_alive())
        self.assertFalse(self.d.active)

    def test_idle_start_does_not_load_then_explicit_start_checks_original_field(self):
        stream.Dictation.load_model.assert_not_called()
        self.d.start(); self.finish()
        self.assertEqual([x.args[0] for x in stream.input_call.call_args_list], ['begin', 'check'])
        self.d.run.assert_called_once_with(self.model)
        self.d.typer.finish.assert_called_once_with('token')

    def test_ready_waits_for_final_field_output(self):
        entered, release = threading.Event(), threading.Event()
        def drain():
            entered.set();self.assertTrue(release.wait(3));return True
        self.d.typer.drain.side_effect=drain
        self.d.start();self.assertTrue(entered.wait(2))
        self.assertTrue(self.d.active)
        self.assertEqual(stream.status.call_args.args,('finishing',))
        release.set();self.finish()
        self.assertEqual(stream.status.call_args.args,('ready',))

    def test_drain_timeout_refuses_ready_and_revokes_field_lease(self):
        self.d.typer.drain.return_value=False
        self.d.start();self.finish()
        self.assertEqual(self.d.error,'InputDrainTimeout')
        self.assertEqual(stream.status.call_args.args,('error',))
        self.assertEqual(stream.input_call.call_args.args,('cancel',))

    def test_cancel_is_distinct_from_success_for_live_review(self):
        self.d.run.side_effect=lambda _:self.d.cancel()
        self.d.start();self.finish()
        self.d.typer.finish.assert_not_called()
        self.assertEqual(stream.status.call_args.args,('cancelled',))

    def test_release_during_load_does_not_open_capture(self):
        entered, release = threading.Event(), threading.Event()
        def slow():
            entered.set(); self.assertTrue(release.wait(3)); return self.model
        stream.Dictation.load_model.side_effect = slow
        self.d.start(); self.assertTrue(entered.wait(2))
        self.d.start()  # Holding/repeating must not create another worker.
        self.d.stop(); release.set(); self.finish()
        self.d.run.assert_not_called()
        stream.tone.assert_not_called()
        self.model.close.assert_called_once()
        self.assertEqual(stream.Dictation.load_model.call_count, 1)
        self.d.typer.finish.assert_called_once_with('token')

    def test_release_during_begin_does_not_load_or_capture(self):
        entered, release = threading.Event(), threading.Event()
        def slow(*_):
            entered.set(); self.assertTrue(release.wait(3)); return 'token'
        stream.input_call.side_effect = slow
        self.d.start(); self.assertTrue(entered.wait(2))
        self.d.stop(); release.set(); self.finish()
        stream.Dictation.load_model.assert_not_called()
        self.d.run.assert_not_called()
        self.d.typer.finish.assert_called_once_with('token')

    def test_focus_loss_after_load_prevents_capture_and_releases_unused_model(self):
        import subprocess
        stream.input_call.side_effect = ['token', subprocess.TimeoutExpired('check', 4)]
        self.d.start(); self.finish()
        self.d.run.assert_not_called()
        self.model.close.assert_called_once()
        self.assertEqual(self.d.error, 'InputUnavailable')

    def test_headroom_refusal_leaves_listener_usable_and_does_not_load(self):
        stream.resource_reasons.return_value = ['memory']
        self.d.start(); self.finish()
        self.d.run.assert_not_called(); stream.Dictation.load_model.assert_not_called()
        stream.input_call.assert_not_called()
        self.assertEqual(self.d.error, 'ResourceGuard')
        stream.resource_reasons.return_value = []
        self.d.start(); self.finish()
        self.d.run.assert_called_once()

    def test_headroom_lost_during_load_prevents_capture(self):
        stream.resource_reasons.side_effect = [[], [], ['memory']]
        self.d.start(); self.finish()
        self.d.run.assert_not_called(); self.model.close.assert_called_once()
        self.assertEqual(self.d.error, 'ResourceGuard')

    def test_idle_pressure_releases_model(self):
        self.d.start(); self.finish()
        stream.resource_reasons.return_value = ['memory']
        self.d.idle_tick()
        self.model.close.assert_called_once()
        self.assertFalse(self.d.models.loaded)

    def test_waiting_status_recovers_without_starting_capture(self):
        stream.resource_reasons.return_value = ['memory']
        self.d.start(); self.finish()
        self.assertEqual(self.d.error, 'ResourceGuard')
        stream.resource_reasons.return_value = []
        self.d.idle_tick()
        self.assertIsNone(self.d.error)
        self.assertEqual(stream.status.call_args.args, ('ready',))
        self.d.run.assert_not_called()
        stream.Dictation.load_model.assert_not_called()

    def test_release_before_device_retry_prevents_open(self):
        self.d.stop_evt.set()
        with patch.object(stream.subprocess, 'Popen') as capture:
            stream.Dictation.run(self.d, self.model)
        capture.assert_not_called()

    def test_release_while_waiting_for_first_samples_closes_child(self):
        capture = Mock()
        def waiting(*_):
            self.d.stop_evt.set()
            return [], [], []
        with patch.object(stream.subprocess, 'Popen', return_value=capture) as factory, patch.object(stream.select, 'select', side_effect=waiting):
            self.assertEqual(self.d.open_capture(['synthetic-capture']), (None, None))
        factory.assert_called_once()
        capture.terminate.assert_called_once(); capture.wait.assert_called_once()
        capture.stdout.close.assert_called_once()

    def test_failed_first_read_closes_child_before_reporting_error(self):
        capture = Mock(); capture.stdout.read1.side_effect = OSError('synthetic pipe failure')
        with patch.object(stream.subprocess, 'Popen', return_value=capture), patch.object(stream.select, 'select', return_value=([capture.stdout], [], [])):
            with self.assertRaises(OSError): self.d.open_capture(['synthetic-capture'])
        capture.terminate.assert_called_once(); capture.wait.assert_called_once()
        capture.stdout.close.assert_called_once()

    def test_stalled_active_pipe_still_observes_release_and_closes(self):
        model = MagicMock(); capture = Mock(); self.d.policy = {}
        session = model.session.return_value.__enter__.return_value
        decoder = session.stream.return_value.__enter__.return_value
        decoder.text.return_value.display = ''
        def waiting(*_):
            self.d.stop_evt.set()
            return [], [], []
        with patch.object(self.d, 'open_capture', return_value=(capture, b'\x00\x00')), \
             patch.object(stream.select, 'select', side_effect=waiting), \
             patch.object(stream.time, 'time', side_effect=[.2, .4, .6, .8]), \
             patch.object(stream, 'np', MagicMock()), \
             patch.object(stream, 'speech_stats', return_value=(0, 0, 0)), \
             patch.object(self.d, 'close_capture') as closed:
            stream.Dictation.run(self.d, model)
        self.assertIsNone(self.d.error)
        capture.stdout.read1.assert_not_called()
        decoder.finalize.assert_called_once()
        closed.assert_called_once_with(capture)


if __name__ == '__main__': unittest.main()
