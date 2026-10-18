#!/usr/bin/env python3
"""Tests for the read-only OpenCode v2 local usage adapter."""

import importlib.util
import json
import pathlib
import sqlite3
import tempfile
import unittest
from unittest import mock
from contextlib import closing


SCRIPT = pathlib.Path(__file__).with_name("codexbar-opencode-local.py")
SPEC = importlib.util.spec_from_file_location("codexbar_opencode_local", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


class OpenCodeLocalUsageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.database = pathlib.Path(self.temp.name) / "opencode.db"
        connection = sqlite3.connect(self.database)
        connection.execute(
            "CREATE TABLE session_message (id TEXT PRIMARY KEY, session_id TEXT, type TEXT, "
            "seq INTEGER, time_created INTEGER, time_updated INTEGER, data TEXT)"
        )
        connection.executemany(
            "INSERT INTO session_message VALUES (?, ?, ?, ?, ?, ?, ?)",
            [
                ("in-window", "s1", "assistant", 1, 4_999_000_000, 4_999_000_000,
                 '{"model":{"providerID":"opencode-go","id":"model-a"},"cost":0.125,"tokens":{"input":100,"output":10,"reasoning":5,"cache":{"read":3,"write":2}}}'),
                ("old", "s1", "assistant", 2, 2_000_000_000, 2_000_000_000,
                 '{"model":{"providerID":"opencode-go"},"cost":1.0,"tokens":{"total":20}}'),
                ("other-provider", "s1", "assistant", 3, 4_999_000_000, 4_999_000_000,
                 '{"model":{"providerID":"openai"},"cost":7.0}'),
                ("user", "s1", "user", 4, 4_999_000_000, 4_999_000_000,
                 '{"model":{"providerID":"opencode-go"},"cost":4.0}'),
                ("no-cost", "s1", "assistant", 5, 4_999_000_000, 4_999_000_000,
                 '{"model":{"providerID":"opencode-go"},"tokens":{"total":9}}'),
                ("bad-cost", "s1", "assistant", 6, 4_999_000_000, 4_999_000_000,
                 '{"model":{"providerID":"opencode-go"},"cost":"unknown"}'),
            ],
        )
        connection.commit()
        connection.close()

    def tearDown(self):
        self.temp.cleanup()

    def test_reads_v2_go_usage_windows_without_modifying_database(self):
        before = self.database.read_bytes()
        usage = MODULE.read_usage(self.database, now_ms=5_000_000_000)
        self.assertEqual(usage["status"], "available")
        self.assertEqual(usage["message"], "Local usage estimate · not account quota")
        self.assertEqual(usage["periods"][0], {
            "label": "5 hours", "costUSD": 0.125, "requests": 1, "tokens": 120,
        })
        self.assertEqual(usage["periods"][1]["requests"], 1)
        self.assertEqual(usage["periods"][2]["requests"], 1)
        self.assertEqual(self.database.read_bytes(), before)
        with sqlite3.connect(f"file:{self.database}?mode=ro", uri=True) as connection:
            with self.assertRaises(sqlite3.OperationalError):
                connection.execute("DELETE FROM session_message")

    def test_missing_database_returns_actionable_status(self):
        missing = pathlib.Path(self.temp.name) / "missing.db"
        self.assertEqual(MODULE.read_usage(missing)["status"], "unavailable")

    def test_unsupported_database_schema_is_not_misreported_as_usage(self):
        connection = sqlite3.connect(self.database)
        connection.execute("DROP TABLE session_message")
        connection.execute("CREATE TABLE message (id TEXT, data TEXT)")
        connection.commit()
        connection.close()
        usage = MODULE.read_usage(self.database, now_ms=5_000_000_000)
        self.assertEqual(usage["status"], "unavailable")
        self.assertIn("unsupported schema", usage["message"])


class AccountTest(unittest.TestCase):
    def credential_database(self, rows):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        path = pathlib.Path(temp.name) / "opencode.db"
        with closing(sqlite3.connect(path)) as db, db:
            db.execute("CREATE TABLE credential (id TEXT, integration_id TEXT, active INTEGER, value TEXT, time_updated INTEGER)")
            db.executemany("INSERT INTO credential VALUES (?, 'opencode', ?, ?, ?)", rows)
        return path

    def credential(self, email, org="workspace", expires=2000000000000):
        return json.dumps({"type": "oauth", "access": "NEVER-PRINT-ACCESS", "refresh": "NEVER-PRINT-REFRESH",
                           "expires": expires, "metadata": {"email": email, "orgID": org}})

    def test_duplicate_login_records_do_not_invent_another_account(self):
        path = self.credential_database([("old", 0, self.credential("me@example.com"), 2),
                                         ("active", 1, self.credential("me@example.com"), 1)])
        before = path.read_bytes()
        with mock.patch.object(MODULE.subprocess, "run") as run:
            accounts = MODULE.saved_accounts(path, "codexbar", now_ms=1900000000000)
        self.assertEqual(len(accounts), 1)
        self.assertEqual(accounts[0]["id"], "active")
        run.assert_not_called()
        self.assertNotIn("NEVER-PRINT", json.dumps(accounts))
        self.assertEqual(path.read_bytes(), before)

    def test_alternate_account_keeps_short_weekly_and_monthly_quota(self):
        path = self.credential_database([("active", 1, self.credential("me@example.com"), 1),
                                         ("other", 0, self.credential("other@example.com"), 2)])
        response = [{"usage": {"primary": {"usedPercent": 100, "resetsAt": "2026-10-18T13:30:00Z"},
                               "secondary": {"usedPercent": 28}, "tertiary": {"usedPercent": 9}}}]
        with mock.patch.object(MODULE.subprocess, "run", return_value=mock.Mock(returncode=0, stdout=json.dumps(response))) as run:
            accounts = MODULE.saved_accounts(path, "codexbar", now_ms=1900000000000)
        self.assertEqual([w["remaining"] for w in accounts[1]["windows"]], [0, 72, 91])
        self.assertEqual([w["minutes"] for w in accounts[1]["windows"]], [300, 10080, 43200])
        self.assertEqual(run.call_args.kwargs["env"]["OPENCODE_API_KEY"], "NEVER-PRINT-ACCESS")
        self.assertNotIn("NEVER-PRINT", json.dumps(accounts))

    def test_plan_is_account_metadata_and_missing_is_unknown(self):
        credential = json.loads(self.credential("me@example.com"))
        credential["metadata"]["plan"] = "go"
        path = self.credential_database([("active", 1, json.dumps(credential), 1)])
        accounts = MODULE.saved_accounts(path, "codexbar", now_ms=1900000000000)
        self.assertEqual(accounts[0]["plan"], "go")
        self.assertNotIn("NEVER-PRINT", json.dumps(accounts))
        path = self.credential_database([("active", 1, self.credential("me@example.com"), 1)])
        self.assertEqual(MODULE.saved_accounts(path, "codexbar")[0]["plan"], "")

    def test_expired_alternate_login_is_labelled_without_querying_quota(self):
        path = self.credential_database([("old", 0, self.credential("other@example.com", expires=1800000000000), 1)])
        with mock.patch.object(MODULE.subprocess, "run") as run:
            accounts = MODULE.saved_accounts(path, "codexbar", now_ms=1900000000000)
        run.assert_not_called()
        self.assertEqual(accounts[0]["windows"], [])
        self.assertIn("Sign in", accounts[0]["error"])

    def test_reads_active_account_email_only(self):
        with tempfile.TemporaryDirectory() as directory:
            database = pathlib.Path(directory) / "opencode.db"
            connection = sqlite3.connect(database)
            connection.execute("CREATE TABLE account (id TEXT PRIMARY KEY, email TEXT, access_token TEXT, time_updated INTEGER)")
            connection.execute("CREATE TABLE account_state (id INTEGER PRIMARY KEY, active_account_id TEXT)")
            connection.executemany("INSERT INTO account VALUES (?,?,?,?)",
                                   [("a", "old@example.com", "secret-a", 9), ("b", "me@example.com", "secret-b", 1)])
            connection.execute("INSERT INTO account_state VALUES (1, 'b')")
            connection.commit()
            connection.close()
            self.assertEqual(MODULE.read_account(database), "me@example.com")

    def test_missing_or_unsupported_database_gives_no_account(self):
        with tempfile.TemporaryDirectory() as directory:
            self.assertEqual(MODULE.read_account(pathlib.Path(directory) / "none.db"), "")
            database = pathlib.Path(directory) / "x.db"
            sqlite3.connect(database).close()
            self.assertEqual(MODULE.read_account(database), "")


if __name__ == "__main__":
    unittest.main()
