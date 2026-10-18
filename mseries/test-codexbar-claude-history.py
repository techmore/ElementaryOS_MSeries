#!/usr/bin/env python3
"""Private local-history transfer tests; never read real conversations or accounts."""
import hashlib
import json
import os
import pathlib
import tempfile
import unittest
from unittest import mock

import codexbar_claude_history as history

SOURCE = "11111111-1111-4111-8111-111111111111"
TARGET = "22222222-2222-4222-8222-222222222222"
ORG = "33333333-3333-4333-8333-333333333333"
OTHER_ORG = "44444444-4444-4444-8444-444444444444"
SID = "local_55555555-5555-4555-8555-555555555555"
CLI = "66666666-6666-4666-8666-666666666666"
SID2 = "local_77777777-7777-4777-8777-777777777777"
CLI2 = "88888888-8888-4888-8888-888888888888"


class HistoryTest(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = pathlib.Path(temp.name)
        self.app = self.root / "Claude"
        self.projects = self.root / "projects"
        self.workspace = self.root / "worktree"
        self.workspace.mkdir()
        self.store = self.root / "archive"
        self.source = self.app / "claude-code-sessions" / SOURCE / ORG
        self.source.mkdir(parents=True)
        self.destination = self.app / "claude-code-sessions" / TARGET / ORG
        self.transcript = self.projects / "worktree" / (CLI + ".jsonl")
        self.transcript.parent.mkdir(parents=True)
        self.transcript.write_text('{"type":"user","message":{"content":"Resume this fixture"}}\n')
        self.record = {"sessionId": SID, "cliSessionId": CLI, "cwd": str(self.workspace),
                       "originCwd": str(self.workspace), "title": "Work in progress", "createdAt": 100,
                       "lastActivityAt": 200, "gitAnchors": [{"gitRoot": str(self.workspace)}],
                       "permissionMode": "bypassPermissions", "autoChosenInApp": True,
                       "sessionPermissionUpdates": [{"type": "allowEverything"}],
                       "enabledMcpTools": {"private-server:secret": True}, "remoteMcpServersConfig": ["secret"],
                       "alwaysAllowedReasons": ["old-account"], "cloudSessionId": None}
        self.write(self.source / (SID + ".json"), self.record)

    def write(self, path, data):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data))

    def plan(self, organization=ORG):
        return history.plan_transfer(self.app, self.projects, SOURCE, TARGET, organization)

    def export(self):
        plan = self.plan()
        return plan, history.export_history(plan, self.store)

    def test_preview_is_read_only_and_counts_missing(self):
        before = sorted(p.relative_to(self.root) for p in self.root.rglob("*"))
        self.assertEqual(self.plan().summary(), {"exportable": 1, "missing": 1, "existing": 0, "unavailable": 0})
        self.assertEqual(before, sorted(p.relative_to(self.root) for p in self.root.rglob("*")))

    def test_export_is_private_and_complete(self):
        original = self.transcript.read_bytes()
        _, snapshot = self.export()
        manifest = json.loads((snapshot / "manifest.json").read_text())
        item = manifest["sessions"][0]
        digest = hashlib.sha256(original).hexdigest()
        blob = self.store / "transcripts" / (digest + ".jsonl")
        self.assertEqual(blob.read_bytes(), original)
        self.assertEqual(item["sha256"], digest)
        self.assertEqual(item["record"]["cwd"], str(self.workspace))
        for path in (snapshot / "manifest.json", blob):
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
        self.assertEqual(self.store.stat().st_mode & 0o777, 0o700)

    def test_import_is_idempotent_and_resets_account_specific_permissions(self):
        original_index = (self.source / (SID + ".json")).read_bytes()
        original_transcript = self.transcript.read_bytes()
        plan, snapshot = self.export()
        self.assertEqual(history.import_missing(plan, snapshot)["imported"], 1)
        copied = json.loads((self.destination / (SID + ".json")).read_text())
        self.assertEqual(copied["sessionId"], SID)
        self.assertEqual(copied["cliSessionId"], CLI)
        self.assertEqual(copied["gitAnchors"], self.record["gitAnchors"])
        self.assertEqual(copied["permissionMode"], "default")
        self.assertEqual(copied["sessionPermissionUpdates"], [])
        for key in ("autoChosenInApp", "enabledMcpTools", "remoteMcpServersConfig", "cloudSessionId"):
            self.assertNotIn(key, copied)
        self.assertEqual(history.import_missing(plan, snapshot)["existing"], 1)
        self.assertEqual(self.transcript.read_bytes(), original_transcript)
        self.assertEqual((self.source / (SID + ".json")).read_bytes(), original_index)

    def test_existing_destination_is_not_overwritten_even_when_older(self):
        self.write(self.destination / (SID + ".json"), self.record | {"title": "Keep my destination title", "lastActivityAt": 1})
        original = (self.destination / (SID + ".json")).read_bytes()
        plan, snapshot = self.export()
        self.assertEqual(plan.summary()["existing"], 1)
        self.assertEqual(history.import_missing(plan, snapshot)["imported"], 0)
        self.assertEqual((self.destination / (SID + ".json")).read_bytes(), original)

    def test_duplicate_cli_with_different_sidebar_id_is_not_added_twice(self):
        self.write(self.destination / (SID2 + ".json"), self.record | {"sessionId": SID2})
        plan, snapshot = self.export()
        self.assertEqual(history.import_missing(plan, snapshot)["existing"], 1)
        self.assertFalse((self.destination / (SID + ".json")).exists())

    def test_missing_transcript_after_export_is_restored_exactly(self):
        original = self.transcript.read_bytes()
        plan, snapshot = self.export()
        self.transcript.unlink()
        self.assertEqual(history.import_missing(plan, snapshot)["imported"], 1)
        self.assertEqual(self.transcript.read_bytes(), original)

    def test_newer_transcript_is_never_replaced_by_archive(self):
        plan, snapshot = self.export()
        with self.transcript.open("a") as handle:
            handle.write('{"new":"turn from the new account"}\n')
        newer = self.transcript.read_bytes()
        history.import_missing(plan, snapshot)
        self.assertEqual(self.transcript.read_bytes(), newer)

    def test_no_transcript_or_missing_workspace_does_not_fabricate_a_chat(self):
        self.transcript.unlink()
        plan = self.plan()
        self.assertEqual(plan.summary()["unavailable"], 1)
        self.assertIsNone(history.export_history(plan, self.store))
        self.assertFalse(self.store.exists())
        self.transcript.write_text('{}\n')
        self.workspace.rmdir()
        self.assertEqual(self.plan().summary()["unavailable"], 1)

    def test_cloud_and_remote_sessions_are_skipped(self):
        for binding in ({"cloudSessionId": "cloud"}, {"sshConfig": {"host": "remote"}}, {"stagedTranscriptPath": "/remote"}):
            self.write(self.source / (SID + ".json"), self.record | binding)
            self.assertEqual(self.plan().summary()["exportable"], 0)

    def test_import_uses_only_the_selected_target_organization(self):
        other = self.destination.parent / OTHER_ORG
        self.write(other / (SID + ".json"), self.record)
        plan, snapshot = self.export()
        self.assertEqual(history.import_missing(plan, snapshot)["imported"], 1)
        self.assertEqual(len(list(other.iterdir())), 1)
        self.assertTrue((self.destination / (SID + ".json")).exists())

    def test_unknown_org_is_not_guessed_when_multiple_exist(self):
        self.destination.mkdir(parents=True)
        (self.destination.parent / OTHER_ORG).mkdir()
        with self.assertRaises(history.HistoryError):
            self.plan(organization="")
        self.assertEqual(self.plan().organization, ORG)

    def test_path_traversal_and_symlink_sources_are_rejected(self):
        with self.assertRaises(history.HistoryError):
            history.plan_transfer(self.app, self.projects, SOURCE, "../escape", ORG)
        original = self.source / (SID + ".json")
        original.unlink()
        original.symlink_to(self.root / "private")
        self.assertEqual(self.plan().summary()["exportable"], 0)
        original.unlink()
        self.write(original, self.record)
        self.transcript.unlink()
        self.transcript.symlink_to(original)
        self.assertEqual(self.plan().summary()["exportable"], 0)

    def test_corrupt_export_does_not_register_an_empty_session(self):
        plan, snapshot = self.export()
        blob = next((self.store / "transcripts").iterdir())
        blob.write_text("corrupt")
        with self.assertRaises(history.HistoryError):
            history.import_missing(plan, snapshot)
        self.assertFalse((self.destination / (SID + ".json")).exists())

    def test_failure_rolls_back_only_entries_created_by_this_import(self):
        self.write(self.source / (SID2 + ".json"), self.record | {"sessionId": SID2, "cliSessionId": CLI2})
        (self.transcript.parent / (CLI2 + ".jsonl")).write_text('{"different":"transcript"}\n')
        plan, snapshot = self.export()
        original_create = history.create_private
        calls = []
        def fail_second(path, data):
            if path.parent == self.destination:
                calls.append(path)
                if len(calls) == 2:
                    raise OSError("fixture disk full")
            return original_create(path, data)
        with mock.patch.object(history, "create_private", side_effect=fail_second):
            with self.assertRaises(OSError):
                history.import_missing(plan, snapshot)
        self.assertEqual(list(self.destination.glob("local_*.json")), [])
        self.assertTrue((self.source / (SID + ".json")).exists())
        self.assertTrue((snapshot / "manifest.json").exists())

    def test_second_export_reuses_unchanged_transcript_blob(self):
        self.export()
        blob = next((self.store / "transcripts").iterdir())
        before = blob.stat().st_mtime_ns
        self.export()
        self.assertEqual(len(list((self.store / "transcripts").iterdir())), 1)
        self.assertEqual(blob.stat().st_mtime_ns, before)


if __name__ == "__main__":
    unittest.main()
