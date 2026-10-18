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
    def setUp(self):
        patch = mock.patch.object(MODULE, "fetch_account_plan", return_value=None)
        self.plan_fetch = patch.start()
        self.addCleanup(patch.stop)

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

    def test_console_plan_is_scoped_to_each_workspace_without_switching(self):
        path = self.credential_database([("active", 1, self.credential("me@example.com", org="personal"), 1),
            ("other", 0, self.credential("me@example.com", org="work"), 2)])
        before = path.read_bytes()
        self.plan_fetch.side_effect = lambda credential, now: (
            "Go" if credential["metadata"]["orgID"] == "personal" else "Go Plus")
        response = mock.Mock(returncode=0, stdout='[{"usage":{"primary":{"usedPercent":10}}}]')
        with mock.patch.object(MODULE.subprocess, "run", return_value=response) as run:
            accounts = MODULE.saved_accounts(path, "codexbar", now_ms=1900000000000)
        self.assertEqual([a["plan"] for a in accounts], ["Go", "Go Plus"])
        self.assertEqual([a["planSource"] for a in accounts], ["console", "console"])
        self.assertEqual(self.plan_fetch.call_count, 2)
        run.assert_called_once()  # only inactive quota, not an account switch
        self.assertNotIn("NEVER-PRINT", json.dumps(accounts))
        self.assertEqual(path.read_bytes(), before)

    def test_console_without_current_access_clears_cached_paid_label(self):
        credential = json.loads(self.credential("me@example.com"))
        credential["metadata"]["plan"] = "Go Plus"
        path = self.credential_database([("active", 1, json.dumps(credential), 1)])
        self.plan_fetch.return_value = ""
        account = MODULE.saved_accounts(path, "codexbar", now_ms=1900000000000)[0]
        self.assertEqual(account["plan"], "")
        self.assertEqual(account["planSource"], "console")

    def test_expired_active_account_does_not_request_plan(self):
        path = self.credential_database([("active", 1, self.credential("me@example.com", expires=1000), 1)])
        accounts = MODULE.saved_accounts(path, "codexbar", now_ms=1900000000000)
        self.plan_fetch.assert_not_called()
        self.assertEqual(accounts[0]["plan"], "")

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


class OpenCodePlanTests(unittest.TestCase):
    NOW = 1900000000000

    def status(self, product="go", end="2031-01-01T00:00:00Z"):
        return {"product": product, "renewalProduct": "go-plus", "paymentMethodId": "PRIVATE-BILLING-ID",
                "cancelAtPeriodEnd": True, "access": {"endsAt": end, "meters": {}}}

    def credential(self):
        return {"access": "NEVER-PRINT-ACCESS", "metadata": {
            "server": "https://opencode.ai/console", "orgID": "workspace-a"}}

    def test_current_product_is_used_instead_of_scheduled_renewal(self):
        self.assertEqual(MODULE.plan_from_status(self.status(), self.NOW), "Go")
        self.assertEqual(MODULE.plan_from_status(self.status("go-plus"), self.NOW), "Go Plus")
        self.assertEqual(MODULE.plan_from_status(self.status("go_plus"), self.NOW), "Go Plus")

    def test_expired_missing_and_unrecognized_subscriptions_remain_unknown(self):
        for data in (None, [], {}, {"product": "go", "access": None},
                     self.status(end="2020-01-01T00:00:00Z"), self.status(end="bad-date"),
                     self.status(end="2031-01-01T00:00:00"), self.status("future-unknown-product")):
            with self.subTest(data=data):
                self.assertEqual(MODULE.plan_from_status(data, self.NOW), "")
        data = self.status()
        data.pop("product")
        data["access"]["meters"] = {"fiveHour": {"limitMicroCents": "9999999999"}}
        self.assertEqual(MODULE.plan_from_status(data, self.NOW), "")

    def test_fetch_uses_official_host_and_workspace_and_returns_only_label(self):
        response = mock.MagicMock()
        response.__enter__.return_value.read.return_value = json.dumps(self.status()).encode()
        opener = mock.Mock()
        opener.open.return_value = response
        with mock.patch.object(MODULE.urllib.request, "build_opener", return_value=opener) as build:
            result = MODULE.fetch_account_plan(self.credential(), self.NOW)
        self.assertEqual(result, "Go")
        self.assertIsInstance(build.call_args.args[0], MODULE.NoPlanRedirect)
        request = opener.open.call_args.args[0]
        self.assertEqual(request.full_url, "https://opencode.ai/console/api/go/status")
        headers = {k.lower(): v for k, v in request.header_items()}
        self.assertEqual(headers["authorization"], "Bearer NEVER-PRINT-ACCESS")
        self.assertEqual(headers["x-org-id"], "workspace-a")
        self.assertEqual(opener.open.call_args.kwargs["timeout"], 8)
        self.assertNotIn("PRIVATE", result)
        self.assertNotIn("NEVER-PRINT", result)

    def test_foreign_server_and_missing_workspace_never_receive_credentials(self):
        for field, value in (("server", "https://untrusted.example/console"), ("orgID", ""),
                             ("orgID", "workspace\nInjected: value")):
            credential = self.credential()
            credential["metadata"][field] = value
            with mock.patch.object(MODULE.urllib.request, "build_opener") as build:
                self.assertIsNone(MODULE.fetch_account_plan(credential, self.NOW))
                build.assert_not_called()

    def test_failures_malformed_and_oversized_responses_are_unavailable(self):
        with mock.patch.object(MODULE.urllib.request, "build_opener") as build:
            build.return_value.open.side_effect = OSError("offline")
            self.assertIsNone(MODULE.fetch_account_plan(self.credential(), self.NOW))
        for payload in (b"bad-json", b"[]", b"x" * 131073):
            response = mock.MagicMock()
            response.__enter__.return_value.read.return_value = payload
            with mock.patch.object(MODULE.urllib.request, "build_opener") as build:
                build.return_value.open.return_value = response
                self.assertIsNone(MODULE.fetch_account_plan(self.credential(), self.NOW))


if __name__ == "__main__":
    unittest.main()
