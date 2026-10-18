#!/usr/bin/env python3
"""Browser onboarding tests: fake CLI/accounts only; never sign in or write real credentials."""
import contextlib
import importlib.util
import io
import json
import pathlib
import sqlite3
import tempfile
import unittest
from unittest import mock

SPEC = importlib.util.spec_from_file_location("opencode_login", pathlib.Path(__file__).with_name("codexbar-opencode-login.py"))
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)
URL = "https://opencode.ai/console/device?user_code=TEST-CODE"
SECRET = "NEVER-PRINT-REFRESH-OR-ACCESS"


def account(ident, email="one@example.com", org="personal", active=True):
    return {"id": ident, "email": email, "orgID": org, "accountID": email, "active": active}


class BrowserLoginTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.home = pathlib.Path(self.temp.name)
        for patch in (mock.patch.object(MODULE.pathlib.Path, "home", return_value=self.home),
                      mock.patch.object(MODULE.shutil, "which", return_value="/fixture/opencode"),
                      mock.patch.object(MODULE.threading, "Timer")):
            patch.start()
            self.addCleanup(patch.stop)

    def process(self, output=URL + "\n", code=0):
        process = mock.Mock()
        process.stdout = io.StringIO(output)
        process.wait.return_value = code
        process.poll.return_value = code
        return process

    def run_login(self, before, after, process=None, callback=None):
        process = process or self.process()
        seen = []
        with mock.patch.object(MODULE, "browser_accounts", side_effect=[before, after]), \
             mock.patch.object(MODULE.subprocess, "Popen", return_value=process) as popen:
            attempt = MODULE.BrowserLogin(callback or seen.append)
            result = attempt.run()
        return result, seen, popen

    def test_new_account_is_verified_and_previous_accounts_preserved(self):
        before = [account("a")]
        after = [account("a", active=False), account("b", "two@example.com")]
        result, urls, popen = self.run_login(before, after, self.process(SECRET + "\n" + URL + "\n"))
        self.assertTrue(result[0], result)
        self.assertIn("two@example.com", result[1])
        self.assertNotIn(SECRET, result[1])
        self.assertEqual(urls, [URL])
        args, kwargs = popen.call_args
        self.assertEqual(args[0], ["/fixture/opencode", "auth", "login", "opencode", "--method", "device",
                                  "--answer", "server=https://opencode.ai/console"])
        self.assertEqual(kwargs["stdin"], MODULE.subprocess.DEVNULL)
        self.assertEqual(kwargs["stdout"], MODULE.subprocess.PIPE)
        self.assertEqual(kwargs["cwd"], self.home)
        self.assertNotIn(SECRET, str(args))

    def test_same_account_session_does_not_claim_a_second_account_was_added(self):
        result, _, _ = self.run_login([account("a")], [account("a", active=False), account("b")])
        self.assertFalse(result[0])
        self.assertIn("already saved", result[1])
        self.assertIn("other account", result[1])

    def test_different_workspace_is_a_distinct_switchable_choice(self):
        before = [account("a")]
        result, _, _ = self.run_login(before, [account("a", active=False), account("b", org="work")])
        self.assertTrue(result[0])

    def test_missing_or_ambiguous_active_account_and_removed_old_account_fail_verification(self):
        for after in ([], [account("a", active=False)], [account("a"), account("b", "two@example.com")],
                      [account("b", "two@example.com")]):
            with self.subTest(after=after):
                result, _, _ = self.run_login([account("a")], after)
                self.assertFalse(result[0])
                self.assertIn("could not be verified", result[1])

    def test_cli_failure_does_not_expose_output_and_does_not_verify_success(self):
        result, _, _ = self.run_login([], [], self.process(SECRET, code=1))
        self.assertFalse(result[0])
        self.assertNotIn(SECRET, result[1])

    def test_unsafe_urls_are_not_opened(self):
        for url in ("https://evil.example/console/device?user_code=TEST-CODE",
                    "https://opencode.ai.evil.example/console/device?user_code=TEST-CODE",
                    "https://opencode.ai/console/device?access_token=" + SECRET,
                    "https://opencode.ai/console/device?user_code=TEST-CODE&user_code=OTHER",
                    "https://opencode.ai@evil.example/console/device?user_code=TEST-CODE",
                    "http://opencode.ai/console/device?user_code=TEST-CODE"):
            with self.subTest(url=url):
                result, urls, _ = self.run_login([], [], self.process(url + "\n"))
                self.assertFalse(result[0])
                self.assertEqual(urls, [])

    def test_ansi_and_duplicate_cli_lines_open_one_approval_page(self):
        result, urls, _ = self.run_login([], [account("a")], self.process(
            "│  \x1b[34m" + URL + "\x1b[0m\n" + URL + "\n"))
        self.assertTrue(result[0])
        self.assertEqual(urls, [URL])

    def test_cancellation_interrupts_cli_without_printing_output(self):
        process = self.process(URL + "\n" + SECRET)
        process.poll.return_value = None
        process.send_signal.side_effect = lambda sig: setattr(process.poll, "return_value", -2)
        with mock.patch.object(MODULE, "browser_accounts", return_value=[]), \
             mock.patch.object(MODULE.subprocess, "Popen", return_value=process):
            attempt = MODULE.BrowserLogin(lambda url: attempt.cancel())
            result = attempt.run()
        self.assertFalse(result[0])
        self.assertIn("cancelled", result[1])
        self.assertNotIn(SECRET, result[1])
        process.send_signal.assert_called_once_with(MODULE.signal.SIGINT)

    def test_early_cancel_and_missing_executable_never_start_authentication(self):
        with mock.patch.object(MODULE, "browser_accounts", return_value=[]), \
             mock.patch.object(MODULE.subprocess, "Popen") as popen:
            attempt = MODULE.BrowserLogin(lambda url: None)
            attempt.cancel()
            self.assertFalse(attempt.run()[0])
            popen.assert_not_called()
        with mock.patch.object(MODULE.shutil, "which", return_value=None):
            result = MODULE.BrowserLogin(lambda url: None).run()
        self.assertFalse(result[0])
        self.assertIn("not found", result[1])

    def test_identity_reader_projects_only_metadata_and_handles_malformed_rows(self):
        data = self.home / "opencode"
        data.mkdir()
        db_path = data / "opencode.db"
        with contextlib.closing(sqlite3.connect(db_path)) as db, db:
            db.execute("CREATE TABLE credential (id TEXT, integration_id TEXT, active INTEGER, value TEXT)")
            db.executemany("INSERT INTO credential VALUES (?, 'opencode', 1, ?)", [
                ("a", json.dumps({"type": "oauth", "access": SECRET, "refresh": SECRET,
                                  "metadata": {"email": "one@example.com", "accountID": "acct", "orgID": "personal"}})),
                ("b", "not-json"), ("c", "[]"), ("d", json.dumps({"type": "key", "key": SECRET})),
                ("e", json.dumps({"type": "oauth", "metadata": {"email": "two@example.com", "accountID": {}, "orgID": []}}))])
        before = db_path.read_bytes()
        with mock.patch.dict(MODULE.os.environ, {"XDG_DATA_HOME": str(self.home)}):
            result = MODULE.browser_accounts()
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0]["orgID"], "personal")
        self.assertEqual(result[1]["accountID"], "two@example.com")
        self.assertNotIn(SECRET, json.dumps(result))
        self.assertEqual(db_path.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
