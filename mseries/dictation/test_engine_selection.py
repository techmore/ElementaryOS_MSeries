"""Engine deployment/rollback contracts with fake services; no native inference."""
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
import contextlib
import sys
from unittest.mock import Mock, patch


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


HERE = Path(__file__).parent
engine = load("tested_engine_selection", HERE / "dictation-engine.py")
installer = load("tested_english_installer", HERE.parent / "install-dictation-english.py")
manager = load("tested_input_payload", HERE.parent / "install-dictation-input.py")


class EngineSelection(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        home = Path(self.temporary.name)
        for name, value in {"HOME": home, "BASE": home / "runtime", "STATE": home / "private",
                            "DROPIN": home / "units/mseries-stream-dictate.service.d/90-english-engine.conf"}.items():
            item = patch.object(engine, name, value)
            item.start()
            self.addCleanup(item.stop)
        self.calls = []
        for name, value in {
            "idle_capture": Mock(), "quiet_admission": Mock(), "bridge_ready": Mock(),
            "environment": Mock(return_value={"STREAM_ENGINE": "ane", "STREAM_MODE": "toggle"}),
            "check_runtime": Mock(return_value={"STREAM_MODEL": "/pinned/model"}),
            "active": Mock(return_value=True), "wait_ready": Mock(),
            "systemctl": Mock(side_effect=lambda *args, **kwargs: self.calls.append(args)),
        }.items():
            item = patch.object(engine, name, value)
            item.start()
            self.addCleanup(item.stop)
        engine.DROPIN.parent.mkdir(parents=True)
        self.other = engine.DROPIN.with_name("50-ane.conf")
        self.other.write_text("Owner ANE preferences\n")

    def select(self, **kwargs):
        with engine.transaction_lock():
            engine.select("nemotron", **kwargs)

    def test_stage_preserves_mode_strict_output_and_other_dropins_without_services(self):
        self.select(stage_only=True)
        data = engine.DROPIN.read_text()
        self.assertIn('"STREAM_MODE=toggle"', data)
        self.assertIn('"STREAM_THREADS=4"', data)
        self.assertIn('"STREAM_UNVERIFIED_FALLBACK=0"', data)
        self.assertIn('"STREAM_OUTPUT=ibus"', data)
        self.assertEqual(self.calls, [])
        self.assertEqual(self.other.read_text(), "Owner ANE preferences\n")
        self.assertEqual(engine.STATE.stat().st_mode & 0o777, 0o700)
        path, change = engine.latest_change()
        self.assertEqual(path.stat().st_mode & 0o777, 0o600)
        self.assertTrue(change["stage_only"])

    def test_explicit_hold_and_resident_lifetime_are_bounded_and_preserved(self):
        self.select(mode="hold", warm_seconds=600, stage_only=True)
        self.assertIn('"STREAM_MODE=hold"', engine.DROPIN.read_text())
        self.assertIn('"STREAM_IDLE_SECONDS=600"', engine.DROPIN.read_text())
        with self.assertRaisesRegex(ValueError, "warm lifetime"):
            self.select(warm_seconds=901, stage_only=True)

    def test_desktop_activation_clears_inherited_capture_and_test_modes(self):
        engine.environment.return_value.update(STREAM_KEEP="1", STREAM_DRY="1", STREAM_TEST_WAV="/old/test.wav")
        self.select(stage_only=True)
        data = engine.DROPIN.read_text()
        cleared = next(line.split("=", 1)[1].split() for line in data.splitlines() if line.startswith("UnsetEnvironment="))
        self.assertEqual(set(cleared), {"STREAM_KEEP", "STREAM_DRY", "STREAM_TEST_WAV", "STREAM_TEST_RAW",
                                        "STREAM_TEST_INSERT", "STREAM_FORCE_FALLBACK", "MSERIES_INPUT_TEST_SESSION"})
        self.assertEqual(self.other.read_text(), "Owner ANE preferences\n")
        path, change = engine.latest_change()
        engine.restore_change(path, change)
        self.assertFalse(engine.DROPIN.exists())
        self.assertEqual(self.calls, [])

    def test_stage_rollback_does_not_stop_or_reload_running_services(self):
        original = b"[Service]\nEnvironment=OLD=value\n"
        engine.DROPIN.write_bytes(original)
        self.select(stage_only=True)
        path, change = engine.latest_change()
        engine.restore_change(path, change)
        self.assertEqual(engine.DROPIN.read_bytes(), original)
        self.assertEqual(self.calls, [])

    def test_health_failure_restores_original_config_and_only_owned_service(self):
        original = b"Original managed engine\n"
        engine.DROPIN.write_bytes(original)
        engine.wait_ready.side_effect = ValueError("not ready")
        with self.assertRaisesRegex(ValueError, "not ready"):
            self.select()
        self.assertEqual(engine.DROPIN.read_bytes(), original)
        self.assertTrue(engine.latest_change()[1]["rolled_back"])
        self.assertEqual(self.other.read_text(), "Owner ANE preferences\n")
        self.assertTrue(all(args in [("daemon-reload",), ("stop", engine.SERVICE), ("start", engine.SERVICE)] for args in self.calls))

    def test_rollback_refuses_owner_edit_without_touching_services(self):
        self.select(stage_only=True)
        engine.DROPIN.write_text("New owner changes\n")
        path, change = engine.latest_change()
        with self.assertRaisesRegex(ValueError, "Owner changed"):
            engine.restore_change(path, change)
        self.assertEqual(engine.DROPIN.read_text(), "New owner changes\n")
        self.assertEqual(self.calls, [])

    def test_cooling_change_before_stop_restores_config_without_service_mutation(self):
        engine.quiet_admission.side_effect = [None, ValueError("hot now")]
        with self.assertRaisesRegex(ValueError, "hot now"):
            self.select()
        self.assertFalse(engine.DROPIN.exists())
        self.assertEqual(self.calls, [])

    def test_active_utterance_prevents_even_staging(self):
        engine.idle_capture.side_effect = ValueError("Listening")
        with self.assertRaisesRegex(ValueError, "Listening"):
            self.select(stage_only=True)
        self.assertFalse(engine.DROPIN.exists())

    def test_digest_and_corrupted_backup_rejection(self):
        model = Path(self.temporary.name) / "wrong.gguf"
        model.write_bytes(b"wrong")
        with self.assertRaisesRegex(ValueError, "digest mismatch"):
            engine.verify_file(model, engine.NEMOTRON_SHA256)
        engine.DROPIN.write_bytes(b"Original")
        self.select(stage_only=True)
        path, change = engine.latest_change()
        change["before_sha256"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "backup digest mismatch"):
            engine.restore_change(path, change)
        self.assertIn("STREAM_ENGINE", engine.DROPIN.read_text())


class InstallerContracts(unittest.TestCase):
    def test_streamed_model_install_round_trip_and_owner_edit_protection(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            target, source = root / "model.gguf", root / "source.gguf"
            target.write_bytes(b"previous weights")
            source.write_bytes(b"new weights")
            payload = manager.Payload(root / "private")
            installer.install_file(payload, target, source)
            self.assertEqual(target.read_bytes(), b"new weights")
            target.write_bytes(b"owner modification")
            with self.assertRaisesRegex(ValueError, "Owner changed"):
                installer.install_file(payload, target, source)
            with self.assertRaisesRegex(ValueError, "Owner changed"):
                payload.restore()
            target.write_bytes(b"new weights")
            # No model validation/rollback path may materialize an entire weight
            # file, even when restoring an existing pre-upgrade model.
            with patch.object(Path, "read_bytes", side_effect=AssertionError("unbounded file read")):
                installer.restore_files(payload)
            self.assertEqual(target.read_bytes(), b"previous weights")

    def test_stage_refuses_an_active_listener_before_any_payload_write(self):
        fake_engine, fake_payload = Mock(), Mock()
        fake_engine.active.return_value = True
        with self.assertRaisesRegex(ValueError, "before staging"):
            installer.stage(fake_payload, Mock(), fake_engine)
        fake_payload.install.assert_not_called()

    def test_stage_only_rollback_restores_files_without_services(self):
        fake_payload, fake_engine = Mock(), Mock()
        fake_payload.data = {"metadata": {"activation_started": False}}
        with patch.object(installer, "validate_restore"), patch.object(installer, "restore_files") as restore:
            installer.restore_payload(fake_payload, fake_engine)
            restore.assert_called_once_with(fake_payload)
        fake_engine.systemctl.assert_not_called()
        fake_engine.quiet_admission.assert_not_called()

    def test_activation_stops_owned_asr_before_first_stage_write(self):
        with tempfile.TemporaryDirectory() as directory:
            payload = manager.Payload(Path(directory) / "private")
            fake_manager = Mock()
            fake_manager.Payload.return_value = payload
            fake_engine = Mock()
            state = {"active": True}
            calls = []
            fake_engine.SERVICE = "owned-asr"
            fake_engine.INPUT_SERVICE = "owned-input"
            fake_engine.DROPIN = Path(directory) / "90-english-engine.conf"
            fake_engine.latest_change.return_value = (None, None)
            fake_engine.active.side_effect = lambda: state["active"]
            fake_engine.transaction_lock.return_value = contextlib.nullcontext()
            def service(*args, **kwargs):
                calls.append(args)
                if args == ("stop", "owned-asr"):
                    state["active"] = False
                return subprocess.CompletedProcess([], 0)
            fake_engine.systemctl.side_effect = service
            def staged(*args, **kwargs):
                self.assertFalse(state["active"])
                self.assertIn(("stop", "owned-asr"), calls)
            with patch.object(installer, "helper", return_value=fake_manager), patch.object(installer, "selector", return_value=fake_engine), patch.object(installer, "stage", side_effect=staged), patch.object(installer, "input_engine", return_value="xkb:us::eng"), patch.object(installer, "restart_bridge"), patch.object(installer.os, "geteuid", return_value=1000), patch.object(sys, "argv", ["installer", "--activate", "nemotron"]):
                installer.main()
            self.assertTrue(payload.data["metadata"]["stream_active"])
            self.assertTrue(fake_engine.select.call_args.kwargs["was_active"])

    def test_speech_only_uses_separate_immediate_preupdate_baseline(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(installer, 'HOME', Path(directory)):
            root = Path(directory)
            target = root / 'existing-payload.py'
            target.write_bytes(b'original before earlier full installer')
            old = manager.Payload(root / 'legacy-state')
            old.install(target, b'working full installation immediately before v0.0.1', 0o600)
            old_bytes = old.path.read_bytes()
            state = installer.state_directory(True)
            self.assertEqual(state, root / '.local/state/mseries-dictation-stt-v0.0.1')
            update = manager.Payload(state)
            update.install(target, b'v0.0.1 STT update', 0o600)
            installer.restore_files(update)
            self.assertEqual(target.read_bytes(), b'working full installation immediately before v0.0.1')
            self.assertEqual(old.path.read_bytes(), old_bytes)

    def test_speech_only_stage_excludes_voice_and_optional_copy(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(installer, 'HOME', Path(directory)), patch.object(installer, 'BASE', Path(directory) / 'runtime'):
            base = installer.BASE
            (base / 'venv/bin').mkdir(parents=True)
            (base / 'venv/bin/python').touch()
            fake = Mock()
            fake.active.return_value = False
            fake.NEMOTRON = engine.NEMOTRON
            fake.INPUT_SERVICE = engine.INPUT_SERVICE
            fake.SERVICE = engine.SERVICE
            fake.systemctl.return_value = subprocess.CompletedProcess([], 0)
            panel = Mock()
            payload = manager.Payload(Path(directory) / 'checkpoint')
            with patch.object(installer, 'fetch_model', return_value=base / 'models' / engine.NEMOTRON), patch.object(installer, 'input_engine', return_value='xkb:us::eng'), patch.object(installer, 'optional_mlx') as optional:
                installer.stage(payload, panel, fake, speech_only=True)
            optional.assert_not_called()
            panel.install_panel.assert_called_once_with(payload, speech_only=True)
            names = set(Path(name).name for name in payload.data['files'])
            self.assertFalse({'voice-assistant.py', 'dictation_voice.py', 'org.techmore.VoiceAssistant.desktop'} & names)
            self.assertTrue({'stream-dictate.py', 'dictation-panel.py', 'dictation-input.py'} <= names)
            # The English update path must also ship unit ordering fixes (#614).
            self.assertIn(engine.SERVICE, names)

    def test_speech_only_rejects_non_cpu_and_optional_asset_arguments(self):
        for args in (['--activate', 'mlx'], ['--mlx-model-dir', '/synthetic/assets'], ['--mlx-modules', '/synthetic/modules']):
            with self.subTest(args=args), patch.object(installer.os, 'geteuid', return_value=1000), patch.object(installer, 'helper') as helper, patch.object(sys, 'argv', ['installer', '--speech-only', *args]), contextlib.redirect_stderr(__import__('io').StringIO()), self.assertRaises(SystemExit):
                installer.main()
            helper.assert_not_called()

    def test_bridge_restart_keeps_valid_owner_input_selection(self):
        fake = Mock()
        with patch.object(installer, "input_engine", return_value="xkb:us::eng"), patch.object(installer.subprocess, "run") as run:
            installer.restart_bridge(fake, "xkb:fr::fra")
            run.assert_not_called()
            fake.systemctl.assert_called_once_with("restart", fake.INPUT_SERVICE)
            fake.bridge_ready.assert_called_once()

    def test_bridge_empty_selection_restores_safe_previous_engine(self):
        with patch.object(installer, "input_engine", return_value=""), patch.object(installer.subprocess, "run") as run:
            installer.restore_input_engine("xkb:us::eng")
            self.assertEqual(run.call_args.args[0][-2:], ["select", "xkb:us::eng"])

    def test_bridge_unknown_baseline_uses_native_repair_without_pref_changes(self):
        with patch.object(installer, "input_engine", return_value="dummy"), patch.object(installer.subprocess, "run") as run:
            installer.restore_input_engine("mseries-dictation")
            self.assertEqual(run.call_args.args[0][-1], "repair-native")


class ActivationHealth(unittest.TestCase):
    def test_ready_before_keyboard_failure_is_not_deployment_success(self):
        with patch.object(engine, "active", return_value=True), patch.object(engine, "systemctl", side_effect=[subprocess.CompletedProcess([], 0, "123\n"), subprocess.CompletedProcess([], 0, "124\n")]), patch.object(engine, "lifecycle", return_value={"pid": 123, "phase": "ready", "output": "ibus"}), patch.object(engine, "environment", return_value={"STREAM_ENGINE": "nemotron", "STREAM_UNVERIFIED_FALLBACK": "0"}), patch.object(engine, "bridge_ready"), patch.object(engine.time, "sleep"):
            with self.assertRaisesRegex(ValueError, "opening its keyboard"):
                engine.wait_ready("nemotron")


class InstallerSelectorOwnership(unittest.TestCase):
    def setUp(self):
        EngineSelection.setUp(self)
        self.payload = manager.Payload(Path(self.temporary.name) / 'stt-checkpoint')
        self.payload.data['metadata'] = {'stream_active': True, 'input_active': False, 'activation_started': False}
        self.input = patch.object(installer, 'input_engine', return_value='xkb:us::eng')
        self.input.start(); self.addCleanup(self.input.stop)
        engine.DROPIN.write_bytes(b'Original owner engine configuration\n')
        with engine.transaction_lock():
            engine.select('nemotron', stage_only=True)
        self.previous_path, _ = engine.latest_change()
        self.previous_bytes = self.previous_path.read_bytes()
        self.previous_dropin = engine.DROPIN.read_bytes()
        installer.remember_selector(self.payload, engine)
        self.payload.data['metadata']['activation_started'] = True
        self.payload.save()

    def new_selection(self):
        with engine.transaction_lock():
            engine.select('nemotron', stage_only=True)

    def test_failure_before_select_preserves_previous_successful_selection(self):
        installer.capture_selector(self.payload, engine)
        with patch.object(engine, 'restore_change', wraps=engine.restore_change) as restore:
            installer.restore_payload(self.payload, engine)
        restore.assert_not_called()
        self.assertEqual(engine.DROPIN.read_bytes(), self.previous_dropin)
        self.assertEqual(self.previous_path.read_bytes(), self.previous_bytes)

    def test_failure_after_select_rolls_back_only_this_updates_selection(self):
        self.new_selection()
        owned_path, _ = engine.latest_change()
        installer.capture_selector(self.payload, engine)
        installer.restore_payload(self.payload, engine)
        self.assertTrue(json.loads(owned_path.read_text())['rolled_back'])
        self.assertEqual(self.previous_path.read_bytes(), self.previous_bytes)
        self.assertEqual(engine.DROPIN.read_bytes(), self.previous_dropin)

    def test_selectors_own_failure_rollback_is_not_repeated(self):
        engine.wait_ready.side_effect = ValueError('synthetic failed health')
        with engine.transaction_lock(), self.assertRaisesRegex(ValueError, 'synthetic failed health'):
            engine.select('nemotron')
        installer.capture_selector(self.payload, engine)
        self.calls.clear()
        with patch.object(engine, 'restore_change', wraps=engine.restore_change) as restore:
            installer.restore_payload(self.payload, engine)
        restore.assert_not_called()
        self.assertEqual(engine.DROPIN.read_bytes(), self.previous_dropin)

    def test_later_owner_selection_refuses_rollback_before_any_service_stop(self):
        self.new_selection()
        installer.capture_selector(self.payload, engine)
        self.new_selection()  # A later independently selected engine, even if bytes happen to match.
        self.calls.clear()
        with self.assertRaisesRegex(ValueError, 'Owner selected'):
            installer.restore_payload(self.payload, engine)
        self.assertEqual(self.calls, [])

    def test_edited_owned_dropin_refuses_rollback_before_any_service_stop(self):
        self.new_selection()
        installer.capture_selector(self.payload, engine)
        engine.DROPIN.write_text('later owner configuration\n')
        self.calls.clear()
        with self.assertRaisesRegex(ValueError, 'Owner changed'):
            installer.restore_payload(self.payload, engine)
        self.assertEqual(self.calls, [])

    def test_legacy_ambiguous_checkpoint_refuses_before_any_service_stop(self):
        self.payload.data['metadata'].pop('selector_schema')
        self.calls.clear()
        with self.assertRaisesRegex(ValueError, 'Legacy ambiguous'):
            installer.restore_payload(self.payload, engine)
        self.assertEqual(self.calls, [])


if __name__ == "__main__":
    unittest.main()
