#!/usr/bin/env python3
"""Tests for the claude-swap bridge. cswap is faked; no real Claude login is touched."""

from contextlib import closing
import datetime as dt
import importlib.util
import pathlib
import sqlite3
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
                   mock.patch.object(MODULE, "app_pids", return_value=[]),
                   mock.patch.dict(MODULE.os.environ, {}, clear=False)]
        for patch in patches:
            patch.start()
            self.addCleanup(patch.stop)
        for name in ("CLAUDE_CONFIG_DIR", "XDG_DATA_HOME", "XDG_CONFIG_HOME"):
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

    def app_session(self, account, cookie):
        self.sign_in_desktop(account)
        config_path = MODULE.app_root() / "config.json"
        config = MODULE.read_json(config_path)
        config.update({"oauth:tokenCacheV2": cookie, "windowBounds": {"width": 900}})
        config_path.write_text(MODULE.json.dumps(config))
        path = MODULE.cookie_path()
        with closing(sqlite3.connect(path)) as db, db:
            db.execute("CREATE TABLE IF NOT EXISTS cookies (name TEXT, host_key TEXT, value TEXT, encrypted_value BLOB)")
            db.execute("DELETE FROM cookies")
            db.execute("INSERT INTO cookies VALUES ('sessionKey', '.claude.ai', '', ?)", (cookie.encode(),))
        with MODULE.app_lock():
            self.assertEqual(MODULE.capture_app(), account["accountUuid"])

    def test_app_snapshot_is_private_atomic_and_includes_committed_wal(self):
        self.app_session(ME, SECRET)
        path = MODULE.cookie_path()
        with closing(sqlite3.connect(path)) as db, db:
            db.execute("PRAGMA journal_mode=WAL")
            db.execute("UPDATE cookies SET encrypted_value=?", (b"updated-encrypted",))
            db.commit()
            with MODULE.app_lock():
                MODULE.capture_app()
            saved = MODULE.load_session("uuid-me")
            with closing(sqlite3.connect(":memory:")) as copy:
                copy.deserialize(saved["cookies"])
                self.assertEqual(copy.execute("SELECT encrypted_value FROM cookies").fetchone()[0], b"updated-encrypted")
        self.assertEqual(MODULE.session_root().stat().st_mode & 0o777, 0o700)
        self.assertEqual(MODULE.session_path("uuid-me").stat().st_mode & 0o777, 0o600)
        self.assertEqual(set(saved["config"]), {"lastKnownAccountUuid", "oauth:tokenCacheV2"})

    def test_app_roundtrip_preserves_preferences_removes_stale_keys_and_restarts(self):
        self.app_session(WORK, "work-encrypted")
        self.app_session(ME, "me-encrypted")
        config_path = MODULE.app_root() / "config.json"
        config = MODULE.read_json(config_path)
        config.update({"oauth:tokenCache": "old-cache", "windowBounds": {"width": 1234}})
        config_path.write_text(MODULE.json.dumps(config))
        with mock.patch.object(MODULE, "stop_app", return_value=True) as stop, \
             mock.patch.object(MODULE, "launch_app") as launch:
            self.assertTrue(MODULE.app_switch("uuid-work")[0])
            self.assertTrue(MODULE.app_switch("uuid-me")[0])
        self.assertEqual(stop.call_count, 2)
        self.assertEqual(launch.call_count, 2)
        config = MODULE.read_json(config_path)
        self.assertEqual(config["windowBounds"], {"width": 1234})
        self.assertEqual(config["oauth:tokenCacheV2"], "me-encrypted")
        with closing(sqlite3.connect(MODULE.cookie_path())) as db, db:
            self.assertEqual(db.execute("SELECT encrypted_value FROM cookies").fetchone()[0], b"me-encrypted")
        self.assertEqual(config_path.stat().st_mode & 0o777, 0o600)

    def test_missing_or_corrupt_app_target_never_stops_app_or_switches_cli(self):
        self.app_session(ME, SECRET)
        for uuid in ("missing", "../escape", "uuid-me"):
            if uuid == "uuid-me":
                bundle = MODULE.read_json(MODULE.session_path(uuid))
                bundle["cookies"] = "bad-data"
                MODULE.session_path(uuid).write_text(MODULE.json.dumps(bundle))
            with mock.patch.object(MODULE, "stop_app") as stop, mock.patch.object(MODULE, "switch") as switch:
                ok, message = MODULE.app_switch(uuid, "cswap", "1")
            self.assertFalse(ok)
            self.assertNotIn(SECRET, message)
            stop.assert_not_called()
            switch.assert_not_called()

    def test_failed_combined_switch_restores_app_session(self):
        self.app_session(WORK, "work-encrypted")
        self.app_session(ME, "me-encrypted")
        with mock.patch.object(MODULE, "stop_app", return_value=True), \
             mock.patch.object(MODULE, "launch_app") as launch, \
             mock.patch.object(MODULE, "switch", return_value=(False, "cswap failed")):
            self.assertEqual(MODULE.app_switch("uuid-work", "cswap", "1"), (False, "cswap failed"))
        launch.assert_called_once()
        self.assertEqual(MODULE.read_json(MODULE.app_root() / "config.json")["lastKnownAccountUuid"], "uuid-me")

    def test_failed_restore_rolls_back_and_reopens_original_app(self):
        self.app_session(WORK, "work-encrypted")
        self.app_session(ME, "me-encrypted")
        restore = MODULE.restore_app
        calls = []
        def fail_first(session):
            calls.append(session)
            if len(calls) == 1:
                raise OSError("disk full")
            restore(session)
        with mock.patch.object(MODULE, "stop_app", return_value=True), \
             mock.patch.object(MODULE, "launch_app") as launch, \
             mock.patch.object(MODULE, "restore_app", side_effect=fail_first):
            self.assertFalse(MODULE.app_switch("uuid-work")[0])
        self.assertEqual(len(calls), 2)
        launch.assert_called_once()
        self.assertEqual(MODULE.read_json(MODULE.app_root() / "config.json")["lastKnownAccountUuid"], "uuid-me")

    def test_no_restore_when_app_will_not_close(self):
        self.app_session(WORK, "work-encrypted")
        self.app_session(ME, "me-encrypted")
        with mock.patch.object(MODULE, "stop_app", side_effect=ValueError("Claude did not quit")), \
             mock.patch.object(MODULE, "restore_app") as restore:
            self.assertEqual(MODULE.app_switch("uuid-work"), (False, "Claude did not quit"))
        restore.assert_not_called()

    def test_logging_out_does_not_overwrite_saved_app_session(self):
        self.app_session(ME, SECRET)
        saved = MODULE.session_path("uuid-me").read_bytes()
        with closing(sqlite3.connect(MODULE.cookie_path())) as db, db:
            db.execute("DELETE FROM cookies")
        with MODULE.app_lock():
            self.assertEqual(MODULE.capture_app(), "")
        self.assertEqual(saved, MODULE.session_path("uuid-me").read_bytes())

    def test_listing_marks_app_ready_and_active_without_leaking_sessions(self):
        self.app_session(ME, SECRET)
        self.save_in_cswap(1, WORK)
        self.save_in_cswap(2, ME)
        with mock.patch.object(MODULE, "run", return_value=LIST):
            data = MODULE.listing("cswap", NOW)
        self.assertEqual([(a["desktopReady"], a["desktopActive"]) for a in data["accounts"]],
                         [(False, False), (True, True)])
        self.assertNotIn(SECRET, MODULE.json.dumps(data))

    def test_switch_from_app_descendant_is_refused(self):
        with mock.patch.object(MODULE, "app_pids", return_value=[MODULE.os.getppid()]):
            with self.assertRaisesRegex(ValueError, "outside the Claude app"):
                MODULE.stop_app()

    def test_native_setup_keeps_previous_session_and_cancel_can_restore_it(self):
        self.save_in_cswap(1, WORK)
        self.app_session(ME, "previous-encrypted")
        saved = MODULE.session_path("uuid-me").read_bytes()
        with mock.patch.object(MODULE, "stop_app", return_value=True), mock.patch.object(MODULE, "launch_app"):
            self.assertTrue(MODULE.app_login("1")[0])
            config = MODULE.read_json(MODULE.app_root() / "config.json")
            self.assertNotIn("lastKnownAccountUuid", config)
            self.assertNotIn("oauth:tokenCacheV2", config)
            with closing(sqlite3.connect(MODULE.cookie_path())) as db:
                self.assertEqual(db.execute("SELECT count(*) FROM cookies").fetchone()[0], 0)
            self.assertEqual(saved, MODULE.session_path("uuid-me").read_bytes())
            self.assertTrue(MODULE.app_switch("uuid-me")[0])
        self.assertEqual(MODULE.read_json(MODULE.app_root() / "config.json")["lastKnownAccountUuid"], "uuid-me")
        self.assertFalse((MODULE.session_root() / "pending-login.json").exists())

    def test_combined_switch_changes_native_and_cli_before_launch(self):
        self.app_session(WORK, "work-encrypted")
        self.app_session(ME, "me-encrypted")
        events = []
        def cli_switch(cli, number):
            self.assertEqual(MODULE.read_json(MODULE.app_root() / "config.json")["lastKnownAccountUuid"], "uuid-work")
            events.append("switch-cli")
            return True, "done"
        with mock.patch.object(MODULE, "stop_app", side_effect=lambda: events.append("stop-app") or True), \
             mock.patch.object(MODULE, "launch_app", side_effect=lambda: events.append("launch-app")), \
             mock.patch.object(MODULE, "switch", side_effect=cli_switch):
            self.assertTrue(MODULE.app_switch("uuid-work", "cswap", "1")[0])
        self.assertEqual(events, ["stop-app", "switch-cli", "launch-app"])

    def test_relaunch_drops_inherited_claude_oauth_environment(self):
        with mock.patch.dict(MODULE.os.environ, {"CLAUDE_CODE_OAUTH_TOKEN": SECRET}), \
             mock.patch.object(MODULE.subprocess, "run", return_value=mock.Mock(returncode=0)) as run, \
             mock.patch.object(MODULE, "app_pids", return_value=[123]):
            MODULE.launch_app()
        self.assertNotIn("CLAUDE_CODE_OAUTH_TOKEN", run.call_args.kwargs["env"])

    def test_app_reopening_during_switch_prevents_file_replacement(self):
        self.app_session(ME, SECRET)
        saved = MODULE.cookie_path().read_bytes()
        with mock.patch.object(MODULE, "app_pids", return_value=[123]):
            with self.assertRaisesRegex(ValueError, "opened again"):
                MODULE.restore_app(MODULE.load_session("uuid-me"))
        self.assertEqual(saved, MODULE.cookie_path().read_bytes())

    def test_restart_failure_is_reported_as_partial_completion(self):
        self.app_session(WORK, "work-encrypted")
        self.app_session(ME, "me-encrypted")
        with mock.patch.object(MODULE, "stop_app", return_value=True), \
             mock.patch.object(MODULE, "launch_app", side_effect=OSError("no launcher")):
            ok, message = MODULE.app_switch("uuid-work")
        self.assertFalse(ok)
        self.assertIn("could not restart", message)
        self.assertEqual(MODULE.read_json(MODULE.app_root() / "config.json")["lastKnownAccountUuid"], "uuid-work")

    def test_failure_during_final_snapshot_reopens_original_app(self):
        self.app_session(WORK, "work-encrypted")
        self.app_session(ME, "me-encrypted")
        with mock.patch.object(MODULE, "capture_app", side_effect=["uuid-me", OSError("disk full")]), \
             mock.patch.object(MODULE, "stop_app", return_value=True), \
             mock.patch.object(MODULE, "launch_app") as launch:
            self.assertFalse(MODULE.app_switch("uuid-work")[0])
        launch.assert_called_once()
        self.assertEqual(MODULE.read_json(MODULE.app_root() / "config.json")["lastKnownAccountUuid"], "uuid-me")


if __name__ == "__main__":
    unittest.main()
