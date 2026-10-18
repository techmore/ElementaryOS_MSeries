#!/usr/bin/env python3
"""Tests for the Codex account switcher. Uses throwaway homes only; never touches ~/.codex."""

import base64
import importlib.util
import json
import os
import pathlib
import stat
import tempfile
import unittest
from unittest import mock

import tempfile as _tempfile

# Helpers cache under XDG_CACHE_HOME; keep the tests away from the real one.
os.environ["XDG_CACHE_HOME"] = _tempfile.mkdtemp(prefix="codexbar-test-cache-")

SCRIPT = pathlib.Path(__file__).with_name("codexbar-accounts.py")
SPEC = importlib.util.spec_from_file_location("codexbar_accounts", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


def auth_for(email, plan="plus", account_id="acct", marker="a"):
    body = {"email": email, "https://api.openai.com/auth": {"chatgpt_plan_type": plan}}
    payload = base64.urlsafe_b64encode(json.dumps(body).encode()).decode().rstrip("=")
    return {"auth_mode": "chatgpt", "tokens": {"id_token": f"h.{payload}.s", "access_token": marker,
                                                 "account_id": account_id}}


class AccountsTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = pathlib.Path(self.tmp.name)
        self.home = root / "codex"
        self.home.mkdir()
        patcher = mock.patch.dict(os.environ, {"CODEX_HOME": str(self.home), "XDG_DATA_HOME": str(root / "data")})
        patcher.start()
        self.addCleanup(patcher.stop)
        self.addCleanup(self.tmp.cleanup)

    def sign_in(self, auth):
        (self.home / "auth.json").write_text(json.dumps(auth))

    def test_list_marks_signed_in_account_and_hides_tokens(self):
        self.sign_in(auth_for("a@example.com", "prolite"))
        accounts = MODULE.list_accounts()
        self.assertEqual([(a["email"], a["plan"], a["active"]) for a in accounts], [("a@example.com", "prolite", True)])
        self.assertNotIn("access_token", json.dumps(accounts))

    def test_api_key_login_is_not_an_account(self):
        self.sign_in({"auth_mode": "apikey", "OPENAI_API_KEY": "sk-x"})
        self.assertEqual(MODULE.list_accounts(), [])
        self.assertIsNone(MODULE.save_current())

    def test_desktop_closes_before_switch_and_launches_selected_account(self):
        first = auth_for("first@example.com", account_id="one")
        second = auth_for("second@example.com", account_id="two")
        self.sign_in(second)
        MODULE.save_current()
        self.sign_in(first)
        events = []
        def stop():
            self.assertEqual(MODULE.identity(MODULE.read_auth(self.home / "auth.json"))["email"], "first@example.com")
            events.append("stop")
        def launch():
            self.assertEqual(MODULE.identity(MODULE.read_auth(self.home / "auth.json"))["email"], "second@example.com")
            events.append("launch")
        with mock.patch.object(MODULE.pathlib.Path, "home", return_value=self.home.parent), \
                mock.patch.object(MODULE, "stop_app", side_effect=stop), \
                mock.patch.object(MODULE, "launch_app", side_effect=launch):
            # The production guard expects the default ~/.codex.
            with mock.patch.object(MODULE.pathlib.Path, "resolve", return_value=self.home):
                ok, message = MODULE.switch_desktop("second@example.com")
        self.assertTrue(ok, message)
        self.assertEqual(events, ["stop", "launch"])
        self.assertEqual(len(MODULE.list_accounts()), 2)

    def test_app_scan_excludes_codexbar_and_other_users(self):
        entries = [mock.MagicMock(), mock.MagicMock(), mock.MagicMock()]
        for entry, pid, uid in zip(entries, (100, 200, 300), (1000, 1000, 2000)):
            entry.name = str(pid)
            entry.stat.return_value.st_uid = uid
        with mock.patch.object(MODULE.pathlib.Path, "iterdir", return_value=iter(entries)), \
                mock.patch.object(MODULE.os, "getuid", return_value=1000), \
                mock.patch.object(MODULE.os, "readlink", side_effect=[MODULE.APP_BINARY, "/home/test/.local/bin/codexbar-linux"]):
            self.assertEqual(MODULE.app_pids(), [100])

    def test_desktop_refuses_unknown_account_without_closing_app(self):
        with mock.patch.object(MODULE, "stop_app") as stop:
            ok, _ = MODULE.switch_desktop("missing")
        self.assertFalse(ok)
        stop.assert_not_called()

    def test_desktop_close_failure_preserves_login(self):
        second = auth_for("second@example.com", account_id="two")
        self.sign_in(second)
        MODULE.save_current()
        first = auth_for("first@example.com", account_id="one")
        self.sign_in(first)
        with mock.patch.object(MODULE.pathlib.Path, "resolve", return_value=self.home), \
                mock.patch.object(MODULE, "stop_app", side_effect=ValueError("still running")), \
                mock.patch.object(MODULE, "launch_app") as launch:
            ok, message = MODULE.switch_desktop("second@example.com")
        self.assertFalse(ok)
        self.assertIn("still running", message)
        self.assertEqual(MODULE.read_auth(self.home / "auth.json"), first)
        launch.assert_not_called()

    def test_switch_preserves_the_account_we_leave(self):
        self.sign_in(auth_for("a@example.com", account_id="1", marker="tok-a"))
        MODULE.save_current()
        self.sign_in(auth_for("b@example.com", account_id="2", marker="tok-b"))
        MODULE.save_current()
        ok, _ = MODULE.switch("a@example.com")
        self.assertTrue(ok)
        self.assertEqual(json.loads((self.home / "auth.json").read_text())["tokens"]["access_token"], "tok-a")
        active = [a["email"] for a in MODULE.list_accounts() if a["active"]]
        self.assertEqual(active, ["a@example.com"])
        ok, _ = MODULE.switch("b@example.com")  # b was preserved when we left it
        self.assertTrue(ok)
        self.assertEqual(json.loads((self.home / "auth.json").read_text())["tokens"]["access_token"], "tok-b")

    def test_switch_unknown_or_active_changes_nothing(self):
        self.sign_in(auth_for("a@example.com", marker="tok-a"))
        before = (self.home / "auth.json").read_text()
        self.assertFalse(MODULE.switch("nobody@example.com")[0])
        self.assertTrue(MODULE.switch("a@example.com")[0])
        self.assertEqual((self.home / "auth.json").read_text(), before)

    def test_save_command_is_human_readable(self):
        import io, contextlib
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            self.assertEqual(MODULE.main(["save"]), 1)
        self.assertIn("Sign in to Codex", err.getvalue())
        self.sign_in(auth_for("a@example.com"))
        with contextlib.redirect_stdout(out):
            self.assertEqual(MODULE.main(["save"]), 0)
        self.assertIn("Saved a@example.com", out.getvalue())

    def test_files_are_private(self):
        self.sign_in(auth_for("a@example.com"))
        MODULE.save_current()
        saved = next(MODULE.store_dir().glob("*/auth.json"))
        self.assertEqual(stat.S_IMODE(saved.stat().st_mode), 0o600)
        self.assertEqual(stat.S_IMODE(saved.parent.stat().st_mode), 0o700)

    def test_same_email_different_workspace_are_separate(self):
        self.sign_in(auth_for("a@example.com", account_id="personal"))
        MODULE.save_current()
        self.sign_in(auth_for("a@example.com", account_id="team"))
        MODULE.save_current()
        self.assertEqual(len(MODULE.list_accounts()), 2)
        self.assertFalse(MODULE.switch("a@example.com")[0])  # ambiguous email needs the exact id

    def test_browser_login_saves_second_account_without_replacing_active_credentials(self):
        self.sign_in(auth_for("a@example.com", account_id="1", marker="active-secret"))
        before = (self.home / "auth.json").read_bytes()
        process = mock.Mock()
        process.wait.return_value = 0
        process.poll.return_value = 0
        def launch(argv, **kwargs):
            isolated = pathlib.Path(kwargs["env"]["CODEX_HOME"])
            self.assertNotEqual(isolated, self.home)
            self.assertIn('cli_auth_credentials_store="file"', argv)
            (isolated / "auth.json").write_text(json.dumps(auth_for("b@example.com", account_id="2", marker="new-secret")))
            return process
        with mock.patch.object(MODULE.subprocess, "Popen", side_effect=launch):
            ok, message = MODULE.login("codex")
        self.assertTrue(ok)
        self.assertIn("b@example.com", message)
        self.assertNotIn("secret", message)
        self.assertEqual((self.home / "auth.json").read_bytes(), before)
        self.assertEqual(len(MODULE.list_accounts()), 2)

    def test_cancelled_browser_login_terminates_child_and_preserves_current_account(self):
        self.sign_in(auth_for("a@example.com", marker="active-secret"))
        before = (self.home / "auth.json").read_bytes()
        process = mock.Mock()
        process.wait.side_effect = [InterruptedError(), 0]
        process.poll.return_value = None
        with mock.patch.object(MODULE.subprocess, "Popen", return_value=process):
            ok, message = MODULE.login("codex")
        self.assertFalse(ok)
        self.assertIn("cancelled", message)
        process.terminate.assert_called_once()
        self.assertEqual((self.home / "auth.json").read_bytes(), before)

    def test_missing_cli_and_failed_login_return_actionable_errors(self):
        self.assertFalse(MODULE.login(None)[0])
        process = mock.Mock()
        process.wait.return_value = 1
        process.poll.return_value = 1
        with mock.patch.object(MODULE.subprocess, "Popen", return_value=process):
            self.assertFalse(MODULE.login("codex")[0])


if __name__ == "__main__":
    unittest.main()
