"""Real controller cancellation boundaries; synthetic native SDK/audio only."""
import importlib.util
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import MagicMock, Mock, patch

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))


class PCM:
    """Numeric stand-in keeps these control-flow regressions NumPy-independent."""
    def __init__(self, n): self.n = n
    def astype(self, *_): return self
    def __truediv__(self, _): return self
    def __pow__(self, _): return self
    def __len__(self): return self.n
    def max(self): return .5
    def sum(self): return self.n * .25


numpy = types.SimpleNamespace(frombuffer=lambda value, *_: PCM(len(value) // 2),
                              float32=float, int16=int, abs=lambda value: value)
spec = importlib.util.spec_from_file_location('stream_f5_races', HERE / 'stream-dictate.py')
stream = importlib.util.module_from_spec(spec)
with patch.dict(sys.modules, {'numpy': numpy}): spec.loader.exec_module(stream)


class CancellationRaces(unittest.TestCase):
    def setUp(self):
        self.patches = []
        for name, value in [('ENGINE', 'stream'), ('OUTPUT', 'ibus'), ('DRY', False),
                            ('KEEP', False), ('TEST_INSERT', False), ('np', numpy),
                            ('Typer', Mock()), ('resource_reasons', Mock(return_value=[])),
                            ('status', Mock()), ('notify', Mock()), ('tone', Mock()),
                            ('input_call', Mock(return_value='owned-token')), ('log', Mock()),
                            ('speech_stats', Mock(return_value=(12, 4, .1))),
                            ('whisper_fallback', Mock(return_value=''))]:
            p = patch.object(stream, name, value); self.patches.append(p); p.start()
        self.environment = patch.dict(stream.os.environ, {}, clear=True); self.environment.start()
        self.addCleanup(self.environment.stop)
        self.d = stream.Dictation()
        self.d.active = True; self.d.input_token = 'owned-token'; self.d.policy = {}
        self.model = MagicMock()
        self.d.models.model = self.model
        self.decoder = self.model.session.return_value.__enter__.return_value.stream.return_value.__enter__.return_value
        self.decoder.feed.return_value = types.SimpleNamespace(committed_changed=False)
        self.decoder.text.return_value = types.SimpleNamespace(committed='', display='')
        self.capture = Mock()
        # Twelve100ms chunks meet fallback's >1second speech predicate.
        self.capture.stdout.read1.side_effect = [b'\1\0' * (stream.CHUNK * 12), b'']
        self.d.open_capture = Mock(return_value=(self.capture, b''))
        self.d.close_capture = Mock()
        self.select = patch.object(stream.select, 'select', return_value=([self.capture.stdout], [], []))
        self.select.start(); self.addCleanup(self.select.stop)

    def tearDown(self):
        for p in reversed(self.patches): p.stop()

    def run_controller(self):
        self.d.run(self.model)
        self.d.close_capture.assert_called_once_with(self.capture)

    def test_typing_interrupt_inside_native_feed_discards_commit_and_preview(self):
        def feed(_):
            self.d.interrupt()
            self.decoder.text.return_value = types.SimpleNamespace(committed='obsolete words', display='obsolete words plus draft')
            return types.SimpleNamespace(committed_changed=True)
        self.decoder.feed.side_effect = feed
        self.run_controller()
        self.assertTrue(self.d.interrupted)
        self.d.typer.submit.assert_not_called(); self.d.typer.preview.assert_not_called()
        self.decoder.finalize.assert_not_called(); stream.whisper_fallback.assert_not_called()
        self.d.typer.discard.assert_called_once(); self.model.cancel.assert_called_once()

    def test_escape_inside_native_feed_discards_commit_and_preview(self):
        def feed(_):
            self.d.cancel()
            self.decoder.text.return_value = types.SimpleNamespace(committed='obsolete words', display='obsolete draft')
            return types.SimpleNamespace(committed_changed=True)
        self.decoder.feed.side_effect = feed
        self.run_controller()
        self.assertTrue(self.d.cancelled)
        self.d.typer.submit.assert_not_called(); self.d.typer.preview.assert_not_called()
        self.decoder.finalize.assert_not_called(); stream.whisper_fallback.assert_not_called()

    def test_escape_during_fallback_discards_returned_transcript(self):
        def fallback(_): self.d.cancel(); return 'obsolete fallback transcript'
        stream.whisper_fallback.side_effect = fallback
        self.run_controller()
        stream.whisper_fallback.assert_called_once()
        self.d.typer.submit.assert_not_called()
        self.assertTrue(self.d.cancelled)

    def test_typing_during_fallback_discards_returned_transcript(self):
        def fallback(_): self.d.interrupt(); return 'obsolete fallback transcript'
        stream.whisper_fallback.side_effect = fallback
        self.run_controller()
        stream.whisper_fallback.assert_called_once()
        self.d.typer.submit.assert_not_called()
        self.assertTrue(self.d.interrupted)

    def test_guard_during_fallback_discards_returned_transcript(self):
        def fallback(_): self.d.error = 'ResourceGuard'; return 'obsolete fallback transcript'
        stream.whisper_fallback.side_effect = fallback
        self.run_controller()
        stream.whisper_fallback.assert_called_once()
        self.d.typer.submit.assert_not_called()
        self.assertEqual(self.d.error, 'ResourceGuard')

    def test_escape_during_final_native_decode_discards_final_tail(self):
        def finalize():
            self.d.cancel()
            self.decoder.text.return_value = types.SimpleNamespace(committed='', display='obsolete final transcript')
        self.decoder.finalize.side_effect = finalize
        self.run_controller()
        self.decoder.finalize.assert_called_once()
        self.d.typer.submit.assert_not_called()
        stream.whisper_fallback.assert_not_called()


if __name__ == '__main__': unittest.main()
