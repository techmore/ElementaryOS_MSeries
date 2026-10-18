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


ME = {"emailAddress": "me@example.com", "accountUuid": "uuid-me"}
WORK = {"emailAddress": "work@example.com", "accountUuid": "uuid-work"}
SECRET = "sk-ant-oat01-NEVER-PRINT-ME"


class ClaudeTest(unittest.TestCase):
    """Every test runs against a fake HOME: the helper reads ~/.claude.json and the desktop app's config."""

    def setUp(self):
        import tempfile
        self._home = tempfile.TemporaryDirectory()
        self.home = pathlib.Path(self._home.name)
        patches = [mock.patch.object(MODULE.pathlib.Path, "home", return_value=self.home),
                   mock.patch.dict(MODULE.os.environ, {}, clear=False)]
        for patch in patches:
            patch.start()
            self.addCleanup(patch.stop)
        for name in ("CLAUDE_CONFIG_DIR", "XDG_DATA_HOME"):
            MODULE.os.environ.pop(name, None)
        self.addCleanup(self._home.cleanup)

    def write(self, relative, data):
        path = self.home / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(MODULE.json.dumps(data))

    def sign_in_cli(self, account):
        self.write(".claude.json", {"oauthAccount": account, "projects": {}})

    def save_in_cswap(self, number, account):
        self.write(f".local/share/claude-swap/configs/.claude-config-{number}-{account['emailAddress']}.json",
                   {"oauthAccount": account})

    def sign_in_desktop(self, account):
        self.write(".config/Claude/config.json", {"lastKnownAccountUuid": account["accountUuid"],
                                                  "oauth:tokenCacheV2": SECRET})

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
        with mock.patch.object(MODULE, "run", return_value={"schemaVersion": 1, "switched": False, "reason": "locked"}):
            self.assertEqual(MODULE.switch("cswap", "1"), (False, "locked"))
        with mock.patch.object(MODULE, "run", return_value={"schemaVersion": 1, "error": {"message": "boom"}}):
            self.assertEqual(MODULE.switch("cswap", "1"), (False, "boom"))
        with mock.patch.object(MODULE, "run", return_value=None):
            self.assertFalse(MODULE.switch("cswap", "1")[0])

    def test_switch_is_checked_against_the_login_claude_code_reads(self):
        switched = {"schemaVersion": 1, "switched": True, "reason": "switched",
                    "to": {"number": 1, "email": "work@example.com"}}
        self.sign_in_cli(ME)  # claude-swap says yes, but the live login did not change
        with mock.patch.object(MODULE, "run", return_value=switched):
            ok, message = MODULE.switch("cswap", "1")
        self.assertFalse(ok)
        self.assertIn("still signed in as me@example.com", message)
        self.sign_in_cli(WORK)
        with mock.patch.object(MODULE, "run", return_value=switched):
            ok, message = MODULE.switch("cswap", "1")
        self.assertTrue(ok)
        self.assertIn("command line now uses work@example.com", message)
        self.assertNotIn("Claude app", message)  # no desktop app installed in this HOME

    def test_switch_says_the_desktop_app_keeps_its_own_sign_in(self):
        """The owner's report: the switch 'did nothing' because Code sessions in the Claude app ignore it."""
        self.save_in_cswap(1, WORK)
        self.save_in_cswap(2, ME)
        self.sign_in_desktop(ME)
        self.sign_in_cli(WORK)
        switched = {"schemaVersion": 1, "switched": True, "to": {"number": 1, "email": "work@example.com"}}
        with mock.patch.object(MODULE, "run", return_value=switched):
            ok, message = MODULE.switch("cswap", "1")
        self.assertTrue(ok)
        self.assertIn("Claude app is still signed in as me@example.com", message)
        self.assertIn("sign in as that account", message)
        self.assertNotIn(SECRET, message)
        self.sign_in_desktop(WORK)  # app on the same account: no note
        with mock.patch.object(MODULE, "run", return_value=switched):
            self.assertNotIn("Claude app", MODULE.switch("cswap", "1")[1])

    def test_already_active_is_not_a_failure(self):
        self.sign_in_cli(WORK)
        result = {"schemaVersion": 1, "switched": False, "reason": "already-active",
                  "to": {"number": 1, "email": "work@example.com"}}
        with mock.patch.object(MODULE, "run", return_value=result):
            self.assertEqual(MODULE.switch("cswap", "1"),
                             (True, "Claude Code's command line already uses work@example.com."))

    def test_listing_follows_the_live_login_and_reports_the_desktop_app(self):
        self.save_in_cswap(1, WORK)
        self.save_in_cswap(2, ME)
        self.sign_in_cli(WORK)  # claude-swap's record (LIST says #2 active) lags the live login
        self.sign_in_desktop(ME)
        with mock.patch.object(MODULE, "run", return_value=LIST):
            data = MODULE.listing("cswap", NOW)
        self.assertEqual(data["activeEmail"], "work@example.com")
        self.assertEqual([a["active"] for a in data["accounts"]], [True, False])
        self.assertEqual(data["desktop"], {"installed": True, "email": "me@example.com", "differs": True})
        self.assertIn("me@example.com", data["desktopNote"])
        self.assertNotIn(SECRET, MODULE.json.dumps(data))
        self.assertNotIn("uuid-", MODULE.json.dumps(data))

    def test_desktop_on_an_unsaved_account_is_still_flagged(self):
        self.sign_in_cli(WORK)
        self.write(".config/Claude/config.json", {"lastKnownAccountUuid": "uuid-unknown"})
        with mock.patch.object(MODULE, "run", return_value=LIST):
            data = MODULE.listing("cswap", NOW)
        self.assertEqual(data["desktop"], {"installed": True, "email": "", "differs": True})
        self.assertIn("a different account", data["desktopNote"])

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
