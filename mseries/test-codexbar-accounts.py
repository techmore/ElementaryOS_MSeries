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


if __name__ == "__main__":
    unittest.main()
