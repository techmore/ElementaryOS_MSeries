#!/usr/bin/env python3
"""Tests for the claude-swap bridge. cswap is faked; no real Claude login is touched."""

import datetime as dt
import importlib.util
import pathlib
import unittest
from unittest import mock

SCRIPT = pathlib.Path(__file__).with_name("codexbar-claude.py")
SPEC = importlib.util.spec_from_file_location("codexbar_claude", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)

NOW = dt.datetime(2026, 10, 18, 12, 0, tzinfo=dt.timezone.utc)
LIST = {"schemaVersion": 1, "activeAccountNumber": 2, "accounts": [
    {"number": 1, "email": "work@example.com", "active": False, "usageStatus": "ok",
     "usage": {"fiveHour": {"pct": 90.0, "resetsAt": "2026-10-18T13:30:00Z"},
               "sevenDay": {"pct": 40.0, "resetsAt": "2026-10-21T12:00:00Z"}}},
    {"number": 2, "email": "me@example.com", "active": True, "usageStatus": "unavailable", "usage": None}]}


class ClaudeTest(unittest.TestCase):
    def test_no_cswap_is_reported_unavailable(self):
        self.assertEqual(MODULE.listing(None), {"available": False, "accounts": [], "activeEmail": ""})

    def test_accounts_carry_remaining_quota_and_reset_text(self):
        with mock.patch.object(MODULE, "run", return_value=LIST):
            data = MODULE.listing("cswap", NOW)
        self.assertEqual(data["activeEmail"], "me@example.com")
        work = data["accounts"][0]
        self.assertEqual([(w["label"], w["remaining"], w["resetText"]) for w in work["windows"]],
                         [("5 hour", 10.0, "Resets in 1h 30m"), ("7 day", 60.0, "Resets in 3d 0h")])
        self.assertEqual(data["accounts"][1]["windows"], [])
        self.assertNotIn("token", str(data))

    def test_unsaved_login_still_names_the_active_account(self):
        def fake(cli, arguments):
            return {"schemaVersion": 1, "accounts": []} if arguments == ["list"] else \
                {"schemaVersion": 1, "active": {"email": "new@example.com", "managed": False}}
        with mock.patch.object(MODULE, "run", side_effect=fake):
            data = MODULE.listing("cswap", NOW)
        self.assertEqual((data["accounts"], data["activeEmail"]), ([], "new@example.com"))

    def test_switch_validates_input_and_reports_results(self):
        self.assertFalse(MODULE.switch("cswap", "1; rm -rf ~")[0])
        with mock.patch.object(MODULE, "run", return_value={"schemaVersion": 1, "switched": True}):
            self.assertTrue(MODULE.switch("cswap", "1")[0])
        with mock.patch.object(MODULE, "run", return_value={"schemaVersion": 1, "switched": False, "reason": "already active"}):
            self.assertEqual(MODULE.switch("cswap", "1"), (False, "already active"))
        with mock.patch.object(MODULE, "run", return_value=None):
            self.assertFalse(MODULE.switch("cswap", "1")[0])

    def test_add_explains_a_missing_login_and_reports_success(self):
        missing = mock.Mock(stdout="", stderr="Error: No credentials found for current account", returncode=0)
        with mock.patch.object(MODULE.subprocess, "run", return_value=missing):
            ok, message = MODULE.add("cswap")
        self.assertFalse(ok)
        self.assertIn("Sign in with the Claude Code command line", message)
        saved = mock.Mock(stdout="Account 1 saved", stderr="", returncode=0)
        with mock.patch.object(MODULE.subprocess, "run", return_value=saved):
            self.assertEqual(MODULE.add("cswap"), (True, "Account 1 saved"))
        self.assertFalse(MODULE.add(None)[0])

    def test_login_saves_the_current_account_first_then_signs_in_and_saves(self):
        calls = []
        def fake_add(cli):
            calls.append("add")
            return True, "Saved."
        done = mock.Mock(stdout="", stderr="", returncode=0)
        with mock.patch.object(MODULE, "add", side_effect=fake_add), \
             mock.patch.object(MODULE, "logged_in", return_value=True), \
             mock.patch.object(MODULE.subprocess, "run", return_value=done) as run:
            self.assertEqual(MODULE.login("cswap", "claude"), (True, "Saved."))
        self.assertEqual(calls, ["add", "add"])
        self.assertEqual(run.call_args[0][0], ["claude", "auth", "login"])

    def test_login_reports_missing_tools_and_failed_sign_in(self):
        self.assertFalse(MODULE.login(None, "claude")[0])
        self.assertIn("not found", MODULE.login("cswap", None)[1])
        failed = mock.Mock(stdout="", stderr="login cancelled", returncode=1)
        with mock.patch.object(MODULE, "logged_in", return_value=False), \
             mock.patch.object(MODULE.subprocess, "run", return_value=failed):
            self.assertEqual(MODULE.login("cswap", "claude"), (False, "login cancelled"))

    def test_bundled_cli_is_found_newest_first(self):
        import tempfile
        with tempfile.TemporaryDirectory() as home, mock.patch.object(MODULE.shutil, "which", return_value=None), \
             mock.patch.object(MODULE.pathlib.Path, "home", return_value=pathlib.Path(home)):
            for version in ("2.1.9", "2.1.299"):
                binary = pathlib.Path(home) / ".config/Claude/claude-code" / version / "hash" / "claude"
                binary.parent.mkdir(parents=True)
                binary.write_text("")
            self.assertIn("2.1.299", MODULE.claude_cli())

    def test_reset_text_edges(self):
        self.assertEqual(MODULE.reset_text("2026-10-18T11:00:00Z", NOW), "Resetting now")
        self.assertEqual(MODULE.reset_text("2026-10-18T12:20:00Z", NOW), "Resets in 20m")
        self.assertEqual(MODULE.reset_text("garbage", NOW), "")


if __name__ == "__main__":
    unittest.main()
