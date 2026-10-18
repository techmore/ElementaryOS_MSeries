import hashlib
import json
from pathlib import Path
import tempfile
import importlib.util
import io
import unittest
from unittest.mock import MagicMock, patch
from urllib.parse import parse_qs, unquote, urlsplit
from urllib.error import HTTPError

import app_adapters as apps
import runtime_recovery as recovery

spec = importlib.util.spec_from_file_location('app_branch_watch', Path(__file__).with_name('branch-watch.py'))
branch_watch = importlib.util.module_from_spec(spec); spec.loader.exec_module(branch_watch)


class AppContracts(unittest.TestCase):
    def test_deleted_named_ref_keeps_personal_branch_and_pr_discovery(self):
        def get(path):
            if path.endswith('/commits/gone'):
                raise HTTPError(path, 422, 'Unprocessable', {}, io.BytesIO(b'{"message":"No commit found for SHA: gone"}'))
            if '/branches?' in path: return [{'name': 'experiment', 'commit': {'sha': 'tip'}}]
            if '/pulls?' in path: return [{'number': 1, 'head': {'repo': {'full_name': 'fork/repo'}, 'ref': 'new', 'sha': 'tip'}, 'html_url': 'https://example.invalid/pr'}]
            if '/compare/' in path: return {'ahead_by': 1, 'behind_by': 0, 'status': 'ahead', 'html_url': 'https://example.invalid/compare'}
            return {'private': False, 'sha': 'base'}
        raw = {}
        rows, errors = branch_watch.collect(get, [{'repo': 'a/b', 'base': 'main', 'branches': ['gone'], 'discover_branches': True, 'open_prs': True}], raw)
        self.assertFalse(errors)
        self.assertEqual(rows['branch:a/b:gone']['status'], 'named ref absent')
        self.assertEqual(rows['branch:fork/repo:new']['ahead'], 1)
        self.assertEqual(raw['a/b'][0]['branch'], 'experiment')

    def test_other_http_422_is_still_an_error(self):
        def get(path):
            raise HTTPError(path, 422, 'Unprocessable', {}, io.BytesIO(b'{"message":"Validation Failed"}'))
        with self.assertRaises(HTTPError): branch_watch.tracked_tip(get, 'a/b', 'gone')

    def test_event_offsets_preserve_instants_and_dst(self):
        self.assertEqual(apps.event_time('2026-10-23T14:30:00-04:00'), apps.event_time('2026-10-23T18:30:00Z'))
        self.assertNotEqual(apps.event_time('2026-11-01T01:30:00-04:00'), apps.event_time('2026-11-01T01:30:00-05:00'))
        for value in ['2026-10-23T14:30:00', '2026-02-30T14:30:00Z', '2026-10-23T14:30:00-00:00', '2026-10-23T14:30:00+04:60']:
            with self.assertRaises(ValueError): apps.event_time(value)

    def test_event_invalid_inputs_never_create_state_or_connect(self):
        with tempfile.TemporaryDirectory() as folder:
            state = Path(folder) / 'state'
            data = {'title': 'Fixture', 'request_id': 'event-fixture-1', 'start': '2026-10-23T18:30:00Z', 'end': '2026-10-23T19:30:00Z'}
            for change in [{'title': 'x\nBEGIN:VEVENT'}, {'request_id': '../personal'}, {'end': '2026-10-23T17:30:00Z'}]:
                with self.assertRaises(ValueError): apps.create_event(state, data | change)
            self.assertFalse(state.exists())

    def test_calendar_marker_is_private_and_does_not_select_a_personal_source(self):
        with tempfile.TemporaryDirectory() as folder:
            state = Path(folder)
            self.assertIsNone(apps.calendar_uid(state))
            uid = apps.calendar_uid(state, True)
            self.assertEqual(apps.calendar_uid(state), uid)
            marker = state / 'calendar-source.json'
            self.assertEqual(marker.stat().st_mode & 0o777, 0o600)
            marker.write_text(json.dumps({'schema': 1, 'source_uid': 'user-calendar'}))
            with self.assertRaises(ValueError): apps.calendar_uid(state)

    def test_calendar_refuses_nonlocal_sources(self):
        source = MagicMock(); source.get_parent.return_value = 'local-stub'
        source.has_extension.return_value = True
        source.get_extension.return_value.get_backend_name.return_value = 'local'
        apps.calendar_source(source, 'Calendar')
        source.get_extension.return_value.get_backend_name.return_value = 'caldav'
        with self.assertRaises(ValueError): apps.calendar_source(source, 'Calendar')

    def test_draft_retries_do_not_duplicate_or_overwrite(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            data = {'to': 'review@example.invalid', 'subject': 'R&D + café', 'body': 'Hello,\nA + B = C & D.', 'request_id': 'mail-fixture-1'}
            first = apps.create_draft(root, data); path = root / first['path']; original = path.read_bytes()
            second = apps.create_draft(root, data)
            self.assertTrue(first['created']); self.assertFalse(second['created'])
            self.assertEqual(first['draft_id'], second['draft_id'])
            self.assertEqual(apps.read_draft(root, first['draft_id'])['body'], data['body'])
            with self.assertRaises(ValueError): apps.create_draft(root, data | {'subject': 'Replacement'})
            self.assertEqual(path.read_bytes(), original)
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            self.assertEqual(len(list((root / 'Mail Drafts').glob('*.eml'))), 1)

    def test_draft_recovery_after_message_write_and_metadata_tampering(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); data = {'to': 'review@example.invalid', 'subject': 'Fixture', 'body': 'Literal text', 'request_id': 'mail-recover-1'}
            first = apps.create_draft(root, data); marker = root / 'Mail Drafts' / (first['draft_id'] + '.json')
            marker.unlink(); apps.create_draft(root, data)
            value = json.loads(marker.read_text()); value['body'] = 'tampered'; marker.write_text(json.dumps(value))
            with self.assertRaises(ValueError): apps.read_draft(root, first['draft_id'])

    def test_mail_headers_and_recipient_lists_are_rejected_before_writes(self):
        data = {'to': 'review@example.invalid', 'subject': 'Fixture', 'body': 'Text', 'request_id': 'mail-validate-1'}
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder) / 'workspace'
            for change in [{'to': 'a@example.invalid,b@example.invalid'}, {'to': 'a..b@example.invalid'},
                           {'to': 'a@example.invalid\r\nBcc: b@example.invalid'}, {'subject': 'Hi\nBcc: other'}, {'body': 'x\x00y'}]:
                with self.assertRaises(ValueError): apps.create_draft(root, data | change)
            self.assertFalse(root.exists())

    def test_draft_folder_and_id_cannot_escape_workspace(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder) / 'workspace'; root.mkdir(); outside = Path(folder) / 'outside'; outside.mkdir()
            (root / 'Mail Drafts').symlink_to(outside)
            with self.assertRaises(ValueError): apps.drafts_dir(root)
            with self.assertRaises(ValueError): apps.draft_id('../private')

    def test_mailto_roundtrip_uses_percent_encoding_not_plus_for_spaces(self):
        value = {'to': 'person+tag@example.invalid', 'subject': 'R&D + café', 'body': 'One\nA=B & C'}
        uri = urlsplit(apps.mailto(value))
        self.assertEqual(unquote(uri.path), value['to'])
        self.assertEqual(parse_qs(uri.query)['subject'][0], value['subject'])
        self.assertEqual(parse_qs(uri.query)['body'][0], 'One\r\nA=B & C')
        # Match Mail 8: GUri decodes once, Composer splits fields and decodes again.
        compat = urlsplit(apps.elementary_mailto(value))
        decoded = unquote(compat.query)
        fields = {k: unquote(v) for k, v in (part.split('=', 1) for part in decoded.split('&'))}
        self.assertEqual(unquote(unquote(compat.path)), value['to'])
        self.assertEqual(fields['subject'], value['subject'])

    def test_browser_never_falls_back_to_an_unowned_process(self):
        with tempfile.TemporaryDirectory() as folder:
            state = Path(folder)
            self.assertFalse(apps.browser_tabs(state)['available'])
            (state / 'browser-session.json').write_text(json.dumps({'pid': 1, 'port': 9222, 'start_ticks': 'wrong'}))
            with self.assertRaises(ValueError): apps.browser_endpoint(state)
            for url in ['file:///etc/passwd', 'javascript:alert(1)', 'chrome://settings']:
                with self.assertRaises(ValueError): apps.start_browser(state, url)

    def test_recovery_preserves_live_unknown_and_pair_leases(self):
        owner = 'pid1234-0123456789ab'; name = 'mlx-lm-launch-' + owner
        row = {'owner': owner, 'bytes': 1}
        self.assertEqual(recovery.stale_cli_entries({name: row}, dead=lambda p: p == 1234), [(name, owner)])
        self.assertEqual(recovery.stale_cli_entries({name: row}, dead=lambda p: False), [])
        for extra in [{'pair_id': 'managed'}, {'claimed': {'pid': 2222}}, {'parent': {'pid': 3333}}]:
            self.assertEqual(recovery.stale_cli_entries({name: row | extra}, dead=lambda p: True), [])
        self.assertEqual(recovery.stale_cli_entries({'different': row}, dead=lambda p: True), [])

    def test_recovery_requires_both_process_and_group_absent(self):
        with patch.object(recovery.os, 'kill', side_effect=ProcessLookupError), patch.object(recovery.os, 'killpg'):
            self.assertFalse(recovery.dead_process_group(1234))
        with patch.object(recovery.os, 'kill', side_effect=ProcessLookupError), patch.object(recovery.os, 'killpg', side_effect=ProcessLookupError):
            self.assertTrue(recovery.dead_process_group(1234))


if __name__ == '__main__': unittest.main()
