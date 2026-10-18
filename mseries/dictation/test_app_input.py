"""Launcher preparation contracts; no app, user service, input or model runs."""
import contextlib
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch


HERE = Path(__file__).resolve().parent


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


app = load('tested_app_input', HERE / 'enable-app-input.py')
payload_manager = load('tested_app_input_payload', HERE.parent / 'install-dictation-input.py')


class AppInputTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        root = Path(self.temporary.name)
        self.stack = contextlib.ExitStack()
        self.addCleanup(self.stack.close)
        for key, value in {'HOME': root, 'BASE': root / 'runtime with spaces',
                           'USER_ENTRY': root / 'applications/chatgpt.desktop',
                           'SYSTEM_ENTRY': root / 'system/chatgpt.desktop', 'STATE': root / 'private'}.items():
            self.stack.enter_context(patch.object(app, key, value))
        app.BASE.mkdir()
        (app.BASE / 'dictation-launch.py').write_text('# synthetic launcher, never executed\n')
        app.SYSTEM_ENTRY.parent.mkdir()
        app.SYSTEM_ENTRY.write_bytes(b'[Desktop Entry]\nName=ChatGPT\nExec=chatgpt %U\nIcon=chatgpt\nType=Application\nStartupNotify=true\n')
        self.payload = payload_manager.Payload(app.STATE)

    def test_system_entry_creates_same_id_user_override_and_preserves_keys(self):
        original = app.SYSTEM_ENTRY.read_bytes()
        result = app.stage(self.payload)
        raw = app.USER_ENTRY.read_bytes()
        self.assertEqual(app.USER_ENTRY.name, app.SYSTEM_ENTRY.name)
        self.assertIn(('Exec=' + app.prefix() + '"chatgpt" %U\n').encode(), raw)
        self.assertEqual([line for line in raw.splitlines() if not line.startswith(b'Exec=')],
                         [line for line in original.splitlines() if not line.startswith(b'Exec=')])
        self.assertEqual(app.SYSTEM_ENTRY.read_bytes(), original)
        self.assertTrue(result['staged'])
        self.assertEqual(result['running_app_compatibility'], 'not checked')
        self.assertIn('owner-controlled', result['activation'])
        self.assertEqual(app.STATE.stat().st_mode & 0o777, 0o700)
        self.assertEqual(self.payload.path.stat().st_mode & 0o777, 0o600)

    def test_existing_user_entry_and_quoted_argument_tail_survive_exactly(self):
        original = (b'[Desktop Entry]\r\nName=My ChatGPT\r\n'
                    b'Exec="/usr/bin/chatgpt"  --profile "A quoted path/profile" %U\r\n'
                    b'Comment=My description\r\nX-Owner-Setting=leave this intact\r\n')
        app.USER_ENTRY.parent.mkdir()
        app.USER_ENTRY.write_bytes(original)
        app.stage(self.payload)
        changed = app.USER_ENTRY.read_bytes()
        self.assertIn(b'"/usr/bin/chatgpt"  --profile "A quoted path/profile" %U\r\n', changed)
        self.assertTrue(changed.endswith(b'X-Owner-Setting=leave this intact\r\n'))
        app.rollback(self.payload)
        self.assertEqual(app.USER_ENTRY.read_bytes(), original)

    def test_all_desktop_actions_are_wrapped_without_losing_flags_or_field_codes(self):
        raw = (b'[Desktop Entry]\nName=ChatGPT\nExec=chatgpt %U\nActions=New;Private;\n'
               b'\n[Desktop Action New]\nName=New window\nExec=/usr/bin/chatgpt --new-window %U\n'
               b'\n[Desktop Action Private]\nName=Private\nExec=chatgpt --private "literal %%"\n')
        changed = app.rewrite(raw)
        self.assertEqual(changed.count(app.prefix().encode()), 3)
        self.assertIn(b' --new-window %U\n', changed)
        self.assertIn(b' --private "literal %%"\n', changed)
        self.assertEqual([line for line in changed.splitlines() if not line.startswith(b'Exec=')],
                         [line for line in raw.splitlines() if not line.startswith(b'Exec=')])

    def test_unknown_main_or_action_wrapper_is_rejected_before_target_or_backup_write(self):
        for text in ('[Desktop Entry]\nExec=custom-wrapper chatgpt %U\n',
                     '[Desktop Entry]\nExec=chatgpt %U\n[Desktop Action Other]\nExec=/usr/bin/env CHATGPT_FLAGS=foo chatgpt\n',
                     '[Desktop Entry]\nDBusActivatable=true\nExec=chatgpt %U\n'):
            app.SYSTEM_ENTRY.write_text(text)
            with self.subTest(text=text), self.assertRaises(ValueError):
                app.stage(self.payload)
            self.assertFalse(app.USER_ENTRY.exists())
            self.assertFalse(self.payload.path.exists())

    def test_repeat_stage_is_identical_and_keeps_the_original_private_baseline(self):
        app.stage(self.payload)
        first = app.USER_ENTRY.read_bytes()
        baseline = json.loads(self.payload.path.read_text())['files'][str(app.USER_ENTRY)].copy()
        app.stage(self.payload)
        self.assertEqual(app.USER_ENTRY.read_bytes(), first)
        self.assertEqual(json.loads(self.payload.path.read_text())['files'][str(app.USER_ENTRY)], baseline)
        self.assertEqual(first.count(app.prefix().encode()), 1)
        app.rollback(self.payload)
        self.assertFalse(app.USER_ENTRY.exists())

    def test_owner_edit_refuses_repeat_stage_and_rollback(self):
        app.stage(self.payload)
        edited = app.USER_ENTRY.read_bytes() + b'X-Later-Owner-Preference=true\n'
        app.USER_ENTRY.write_bytes(edited)
        result = app.check(self.payload)
        self.assertTrue(result['owner_changed'])
        self.assertFalse(result['staged'])
        for action in (app.stage, app.rollback):
            with self.subTest(action=action.__name__), self.assertRaisesRegex(ValueError, 'Owner changed'):
                action(self.payload)
            self.assertEqual(app.USER_ENTRY.read_bytes(), edited)

    def test_owner_permission_change_is_preserved(self):
        app.stage(self.payload)
        app.USER_ENTRY.chmod(0o600)
        self.assertTrue(app.check(self.payload)['owner_changed'])
        for action in (app.stage, app.rollback):
            with self.subTest(action=action.__name__), self.assertRaisesRegex(ValueError, 'Owner changed'):
                action(self.payload)
        self.assertEqual(app.USER_ENTRY.stat().st_mode & 0o777, 0o600)

    def test_other_checkpoint_target_is_never_restored_or_changed(self):
        self.payload.data['files']['/synthetic/unexpected-owner-path'] = {}
        for action in (app.stage, app.rollback, app.check):
            with self.subTest(action=action.__name__), self.assertRaisesRegex(ValueError, 'unexpected target'):
                action(self.payload)

    def test_check_is_read_only_and_does_not_claim_current_application_support(self):
        result = app.check(self.payload)
        self.assertFalse(app.STATE.exists())
        self.assertFalse(app.USER_ENTRY.exists())
        self.assertFalse(result['staged'])
        self.assertEqual(result['next_launch_flags'], [])
        self.assertEqual(result['running_app_compatibility'], 'not checked')

    def test_symlink_entry_and_oversized_source_are_preserved(self):
        app.USER_ENTRY.parent.mkdir()
        app.USER_ENTRY.symlink_to(app.SYSTEM_ENTRY)
        with self.assertRaisesRegex(ValueError, 'symlink'):
            app.stage(self.payload)
        self.assertTrue(app.USER_ENTRY.is_symlink())
        app.USER_ENTRY.unlink()
        app.SYSTEM_ENTRY.write_bytes(b'X' * (app.MAX_ENTRY_BYTES + 1))
        with self.assertRaisesRegex(ValueError, 'oversized'):
            app.stage(self.payload)
        self.assertFalse(self.payload.path.exists())

    def test_literal_destination_path_escaping_uses_desktop_layers_not_shell_quoting(self):
        value = app.desktop_argument('/synthetic/a path/percent%/dollar$/back\\slash/quote"/tick`')
        self.assertIn('percent%%', value)
        self.assertIn('dollar' + '\\' * 2 + '$', value)
        self.assertIn('back' + '\\' * 4 + 'slash', value)
        self.assertIn('quote' + '\\' * 2 + '"', value)
        with self.assertRaises(ValueError):
            app.desktop_argument('/synthetic/new\nline')

    def test_glib_independently_parses_the_two_desktop_escaping_layers(self):
        try:
            from gi.repository import GLib
        except ImportError:
            self.skipTest('GLib parser is unavailable on this test host')
        destination = Path('/synthetic/A path/dollar$/back\\slash/quote"/tick`')
        with patch.object(app, 'BASE', destination):
            data = app.rewrite(b'[Desktop Entry]\nExec=chatgpt %U\n')
        keyfile = GLib.KeyFile()
        keyfile.load_from_data(data.decode(), len(data), GLib.KeyFileFlags.NONE)
        _success, arguments = GLib.shell_parse_argv(keyfile.get_string('Desktop Entry', 'Exec'))
        self.assertEqual(arguments, ['/usr/bin/python3', str(destination / 'dictation-launch.py'), '--chromium', 'chatgpt', '%U'])

    def test_glib_spaced_main_and_actions_are_wrapped_preserving_layout(self):
        try:
            from gi.repository import GLib
        except ImportError:
            self.skipTest('GLib parser is unavailable on this test host')
        raw = (b'[Desktop Entry]\r\nName=ChatGPT\r\nType=Application\r\n'
               b'Exec \t= \tchatgpt  --profile "owner profile" %U \t\r\n'
               b'DBusActivatable \t= false\r\nActions=New;\r\n'
               b'[Desktop Action New]\r\nName=New\r\nExec = /usr/bin/chatgpt --new-window %U\r\n')
        changed = app.rewrite(raw)
        self.assertIn(('Exec \t= \t' + app.prefix() + '"chatgpt"  --profile "owner profile" %U \t\r\n').encode(), changed)
        self.assertIn(('Exec = ' + app.prefix() + '"/usr/bin/chatgpt" --new-window %U\r\n').encode(), changed)
        self.assertIn(b'DBusActivatable \t= false\r\n', changed)
        self.assertEqual(app.rewrite(changed), changed)
        keyfile = GLib.KeyFile()
        keyfile.load_from_data(changed.decode(), len(changed), GLib.KeyFileFlags.NONE)
        for group in ('Desktop Entry', 'Desktop Action New'):
            _success, arguments = GLib.shell_parse_argv(keyfile.get_string(group, 'Exec'))
            self.assertEqual(arguments[:3], ['/usr/bin/python3', str(app.BASE / 'dictation-launch.py'), '--chromium'])
        self.assertFalse(keyfile.get_boolean('Desktop Entry', 'DBusActivatable'))

    def test_glib_semantic_dbus_activation_is_refused_before_stage(self):
        try:
            from gi.repository import GLib
        except ImportError:
            self.skipTest('GLib parser is unavailable on this test host')
        for control in ('DBusActivatable = true', 'DBusActivatable\t=\ttrue'):
            raw = ('[Desktop Entry]\nName=ChatGPT\nType=Application\n' + control + '\nExec=chatgpt %U\n').encode()
            keyfile = GLib.KeyFile()
            keyfile.load_from_data(raw.decode(), len(raw), GLib.KeyFileFlags.NONE)
            self.assertTrue(keyfile.get_boolean('Desktop Entry', 'DBusActivatable'))
            app.SYSTEM_ENTRY.write_bytes(raw)
            with self.subTest(control=control), self.assertRaisesRegex(ValueError, 'D-Bus'):
                app.stage(self.payload)
            self.assertFalse(app.USER_ENTRY.exists())
            self.assertFalse(self.payload.path.exists())

    def test_duplicate_localized_or_missing_main_control_keys_are_preserved(self):
        for text in (
            '[Desktop Entry]\nExec=chatgpt\nExec = chatgpt --other\n',
            '[Desktop Entry]\nExec=chatgpt\nDBusActivatable=false\nDBusActivatable = true\n',
            '[Desktop Entry]\nExec=chatgpt\nExec[en]=chatgpt --other\n',
            '[Desktop Entry]\nExec=chatgpt\nDBusActivatable[en]=true\n',
            '[Desktop Entry]\nExec=chatgpt\nDBusActivatable=1\n',
            '[Desktop Entry]\nExec=chatgpt\n[Desktop Entry]\nExec=chatgpt\n',
            '[Desktop Entry]\nName=ChatGPT\n[Desktop Action New]\nExec=chatgpt\n',
        ):
            app.SYSTEM_ENTRY.write_text(text)
            with self.subTest(text=text), self.assertRaises(ValueError):
                app.stage(self.payload)
            self.assertFalse(app.USER_ENTRY.exists())
            self.assertFalse(self.payload.path.exists())

    def test_required_action_and_check_cli_perform_no_subprocess_or_app_work(self):
        with patch.object(app, 'manager', return_value=payload_manager), patch.object(app.os, 'geteuid', return_value=1000), patch('sys.argv', ['enable-app-input', '--app', 'chatgpt', '--check']), contextlib.redirect_stdout(io.StringIO()) as output:
            app.main()
        self.assertFalse(json.loads(output.getvalue())['staged'])
        self.assertFalse(app.STATE.exists())
        with patch.object(app.os, 'geteuid', return_value=1000), patch('sys.argv', ['enable-app-input', '--app', 'chatgpt']), contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            app.main()

    def test_mutation_lock_prevents_competing_stage_and_private_state_symlinks(self):
        with app.transaction():
            with self.assertRaises(BlockingIOError):
                with app.transaction():
                    self.fail('overlapping launcher mutation')
        (app.STATE / 'baseline.json').symlink_to(app.SYSTEM_ENTRY)
        with self.assertRaisesRegex(ValueError, 'symlink'):
            with app.transaction():
                self.fail('unsafe state admitted')


if __name__ == '__main__':
    unittest.main()
