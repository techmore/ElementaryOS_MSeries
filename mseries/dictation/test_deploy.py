import importlib.util
import json
import os
from pathlib import Path
import stat
import subprocess
import tempfile
import unittest
from unittest.mock import patch, Mock


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module


HERE = Path(__file__).resolve().parent
deploy = load('dictation_deploy', HERE.parent / 'install-dictation-input.py')
status = load('dictation_status_test', HERE / 'dictation_status.py')
resources = load('dictation_resources_test', HERE / 'dictation_resources.py')


class DeploymentTests(unittest.TestCase):
    def test_speech_only_panel_launcher_is_explicit_and_default_compatible(self):
        payload = Mock()
        deploy.install_panel(payload)
        normal = payload.install.call_args.args[1].decode()
        self.assertIn('optional transcript review', normal)
        self.assertNotIn('MSERIES_DICTATION_SPEECH_ONLY', normal)
        deploy.install_panel(payload, speech_only=True)
        speech = payload.install.call_args.args[1].decode()
        self.assertIn('Exec="/usr/bin/env" "MSERIES_DICTATION_SPEECH_ONLY=1" "/usr/bin/python3"', speech)
        self.assertNotIn('optional transcript review', speech)
        self.assertNotIn('voice-assistant', speech)
        self.assertEqual(payload.install.call_args.args[2], 0o644)

    def test_browser_override_keeps_actions_and_urls(self):
        text = '[Desktop Entry]\nName=Browser\nExec=/usr/bin/brave-browser-stable %U\n\n[Desktop Action private]\nExec=brave-browser --incognito %U\n'
        result = deploy.brave_override(text)
        self.assertIn('Exec=/usr/bin/brave-browser-stable --force-renderer-accessibility %U', result)
        self.assertIn('Exec=brave-browser --force-renderer-accessibility --incognito %U', result)
        self.assertIn('Name=Browser', result)
        self.assertEqual(deploy.brave_override(result), result)
        with self.assertRaises(ValueError): deploy.brave_override('Exec=custom-wrapper brave-browser %U\n')

    def test_first_baseline_survives_repeated_stage_and_rollback(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); original = root / 'original'; added = root / 'added'
            original.write_bytes(b'owner payload'); original.chmod(0o755)
            payload = deploy.Payload(root / 'state')
            payload.install(original, b'candidate 1', 0o644)
            payload.install(original, b'candidate 2', 0o644)
            payload.install(added, b'new helper', 0o755)
            payload.restore()
            self.assertEqual(original.read_bytes(), b'owner payload')
            self.assertEqual(stat.S_IMODE(original.stat().st_mode), 0o755)
            self.assertFalse(added.exists())
            self.assertEqual(stat.S_IMODE(payload.path.stat().st_mode), 0o600)

    def test_owner_edit_prevents_partial_restore(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); first = root / 'first'; second = root / 'second'
            first.write_bytes(b'old 1'); second.write_bytes(b'old 2')
            payload = deploy.Payload(root / 'state')
            payload.install(first, b'new 1', 0o600); payload.install(second, b'new 2', 0o600)
            second.write_bytes(b'owner edit')
            with self.assertRaises(ValueError): payload.restore()
            self.assertEqual(first.read_bytes(), b'new 1')
            self.assertEqual(second.read_bytes(), b'owner edit')

    def test_remember_only_file_cannot_delete_later_owner_file(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); target = root / 'dropin'; payload = deploy.Payload(root / 'state')
            payload.remember(target); target.write_bytes(b'owner preference')
            with self.assertRaises(ValueError): payload.restore()
            with self.assertRaises(ValueError): payload.install(target, b'candidate', 0o600)
            self.assertEqual(target.read_bytes(), b'owner preference')

    def test_worker_thread_capture_is_detected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); main = root / '12/task/12'; worker = root / '12/task/13'
            main.mkdir(parents=True); worker.mkdir(); (main / 'children').write_text('')
            (worker / 'children').write_text('99')
            (root / '99').mkdir(); (root / '99/stat').write_text('99 (ffmpeg) S 12')
            result = subprocess.CompletedProcess([], 0, '12\n', '')
            with patch.object(deploy, 'systemctl', return_value=result):
                with self.assertRaises(ValueError): deploy.check_idle_capture(root)
                (root / '99/stat').write_text('99 (notify-send) Z 12')
                deploy.check_idle_capture(root)

    def test_rollback_repairs_empty_engine_but_preserves_owner_selection(self):
        for current, restore in [('', True), ('dummy', True), (deploy.ENGINE, True), ('xkb:fr::fra', False)]:
            payload = Mock()
            payload.data = {'metadata': {'engine': 'xkb:us::eng', 'activation_started': False,
                'input_enabled': False, 'stream_active': True, 'input_active': False}}
            result = subprocess.CompletedProcess([], 0, current, '')
            with patch.object(deploy, 'check_idle_capture'), patch.object(deploy, 'systemctl'), patch.object(deploy, 'command', return_value=result) as command:
                deploy.rollback(payload)
                selections = [args[0] for args, _ in command.call_args_list if 'select' in args[0]]
                self.assertEqual(bool(selections), restore)
                if restore: self.assertEqual(selections[0][-1], 'xkb:us::eng')

    def test_provider_stop_clears_engine_before_final_restore(self):
        state = {'engine': deploy.ENGINE}
        events = []
        payload = Mock()
        payload.data = {'metadata': {'engine': 'xkb:us::eng', 'activation_started': False,
            'input_enabled': False, 'stream_active': True, 'input_active': False}}
        def command(args, check=True):
            if args == ['ibus', 'engine']:
                return subprocess.CompletedProcess(args, 0, state['engine'], '')
            if 'select' in args:
                events.append('select'); state['engine'] = args[-1]
            return subprocess.CompletedProcess(args, 0, '', '')
        def systemctl(*args, **kwargs):
            if args == ('stop', deploy.INPUT_SERVICE):
                events.append('stop'); state['engine'] = ''
        with patch.object(deploy, 'check_idle_capture'), patch.object(deploy, 'command', side_effect=command), patch.object(deploy, 'systemctl', side_effect=systemctl), patch.object(deploy.time, 'sleep'):
            deploy.rollback(payload)
        self.assertEqual(state['engine'], 'xkb:us::eng')
        self.assertLess(events.index('stop'), events.index('select'))


class StatusTests(unittest.TestCase):
    def test_private_bounded_status_and_no_transcript_fields(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {'XDG_RUNTIME_DIR': directory}):
            status.write_status('ready', 'ibus', 'cpu')
            row = status.read_status()
            self.assertEqual(row['phase'], 'ready')
            self.assertEqual(set(row), {'pid', 'phase', 'output', 'backend', 'updated_at'})
            self.assertEqual(stat.S_IMODE(status.status_path().stat().st_mode), 0o600)
            row['transcript'] = 'synthetic private text'
            status.status_path().write_text(json.dumps(row))
            self.assertIsNone(status.read_status())

    def test_resource_guard_preserves_desktop_reserve_and_telemetry(self):
        policy = {'reserve_gib': 6, 'max_fan_rpm': 3500, 'max_temp_c': 80}
        sample = {'available_bytes': 7 * 1024 ** 3, 'fans_rpm': {'fan': 2500}, 'temperatures_c': {'temp': 50}}
        self.assertEqual(resources.reasons(policy, sample=sample), [])
        self.assertTrue(resources.reasons(policy, 2 * 1024 ** 3, sample))
        self.assertTrue(resources.reasons(policy, sample=sample | {'fans_rpm': {'fan': 3501}}))
        self.assertTrue(resources.reasons(policy, sample=sample | {'temperatures_c': {'temp': 81}}))
        self.assertTrue(resources.reasons(policy, sample=sample | {'fans_rpm': {}}))


if __name__ == '__main__': unittest.main()
