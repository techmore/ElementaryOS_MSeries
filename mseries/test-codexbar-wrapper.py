#!/usr/bin/env python3
"""Tests for the CodexBar wrapper that hands OpenCode Go credentials to upstream."""

from contextlib import closing
import importlib.util
import json
import os
import pathlib
import sqlite3
import tempfile
import unittest
from unittest import mock


SCRIPT = pathlib.Path(__file__).with_name("codexbar-opencode-wrapper.py")
SPEC = importlib.util.spec_from_file_location("codexbar_wrapper", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


class WrapperTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.home = pathlib.Path(self.temp.name)
        (self.home / ".local/share/opencode").mkdir(parents=True)
        self.auth = self.home / ".local/share/opencode/auth.json"

    def environment(self, **extra):
        return {"HOME": str(self.home), **extra}

    def run_main(self, arguments, environment):
        """Run main() with exec replaced; return (executed argv, environment) or the exit code."""
        executed = {}

        def fake_exec(path, argv, env):
            executed.update(path=path, argv=argv, env=dict(env))
            raise SystemExit(0)

        with mock.patch.dict(os.environ, environment, clear=True), \
                mock.patch.object(MODULE.os, "execvpe", fake_exec), \
                mock.patch.object(MODULE.pathlib.Path, "home", return_value=self.home):
            (self.home / ".local/lib/codexbar-cli").mkdir(parents=True, exist_ok=True)
            (self.home / ".local/lib/codexbar-cli/codexbar-upstream").write_text("#!/bin/sh\n")
            with self.assertRaises(SystemExit):
                MODULE.main(arguments)
        return executed

    def test_provider_selection(self):
        self.assertEqual(MODULE.selected_provider(["usage", "--provider", "opencodego"]), "opencodego")
        self.assertEqual(MODULE.selected_provider(["usage", "--provider=all"]), "all")
        self.assertIsNone(MODULE.selected_provider(["usage", "--provider"]))
        self.assertIsNone(MODULE.selected_provider(["usage"]))

    def test_key_is_read_from_opencode_go_entry_only(self):
        self.auth.write_text(json.dumps({"opencode-go": {"key": " abc "}, "openai": {"key": "other"}}))
        with mock.patch.dict(os.environ, self.environment(), clear=True):
            self.assertEqual(MODULE.opencode_go_key(), "abc")

    def test_missing_or_malformed_credentials_give_no_key(self):
        with mock.patch.dict(os.environ, self.environment(), clear=True):
            self.assertIsNone(MODULE.opencode_go_key())
            for content in ("not json", "[]", '{"opencode-go": "x"}', '{"opencode-go": {"key": "  "}}'):
                self.auth.write_text(content)
                self.assertIsNone(MODULE.opencode_go_key(), content)

    def test_relative_xdg_data_home_is_ignored(self):
        self.auth.write_text(json.dumps({"opencode-go": {"key": "abc"}}))
        with mock.patch.dict(os.environ, self.environment(XDG_DATA_HOME="relative/dir"), clear=True):
            self.assertEqual(MODULE.opencode_go_key(), "abc")

    def test_key_is_injected_for_usage_of_opencodego_and_all(self):
        self.auth.write_text(json.dumps({"opencode-go": {"key": "abc"}}))
        for provider in ("opencodego", "all"):
            run = self.run_main(["usage", "--provider", provider], self.environment())
            self.assertEqual(run["env"]["OPENCODE_API_KEY"], "abc", provider)
            self.assertEqual(run["argv"][1:], ["usage", "--provider", provider])

    def test_key_is_not_injected_elsewhere(self):
        self.auth.write_text(json.dumps({"opencode-go": {"key": "abc"}}))
        for arguments in (["usage", "--provider", "codex"], ["--snapshot"], ["config", "--provider", "all"]):
            self.assertNotIn("OPENCODE_API_KEY", self.run_main(arguments, self.environment())["env"], arguments)

    def test_existing_environment_key_wins(self):
        self.auth.write_text(json.dumps({"opencode-go": {"key": "from-file"}}))
        run = self.run_main(["usage", "--provider", "opencodego"], self.environment(OPENCODE_API_KEY="from-env"))
        self.assertEqual(run["env"]["OPENCODE_API_KEY"], "from-env")

    def oauth_database(self, credentials):
        with closing(sqlite3.connect(self.auth.with_name("opencode.db"))) as db, db:
            db.execute("CREATE TABLE credential (integration_id TEXT, active INTEGER, value TEXT, time_updated INTEGER)")
            db.executemany("INSERT INTO credential VALUES (?, ?, ?, ?)", credentials)

    def test_active_v2_oauth_selection_takes_precedence_over_legacy_key(self):
        token = json.dumps({"type": "oauth", "access": "oauth-token", "expires": 2000000000000})
        self.oauth_database([("opencode", 1, token, 1)])
        with mock.patch.object(MODULE.time, "time", return_value=1900000000):
            result = self.run_main(["usage", "--provider", "opencodego"], self.environment())
            self.assertEqual(result["env"]["OPENCODE_API_KEY"], "oauth-token")
            self.auth.write_text(json.dumps({"opencode-go": {"key": "explicit-key"}}))
            result = self.run_main(["usage", "--provider", "opencodego"], self.environment())
            self.assertEqual(result["env"]["OPENCODE_API_KEY"], "oauth-token")

    def test_active_account_change_updates_quota_token_without_rewriting_legacy_key(self):
        value = lambda token: json.dumps({"type": "oauth", "access": token, "expires": 2000000000000})
        self.oauth_database([("opencode", 1, value("account-a"), 1), ("opencode", 0, value("account-b"), 2)])
        self.auth.write_text(json.dumps({"opencode-go": {"key": "legacy"}}))
        before = self.auth.read_bytes()
        with mock.patch.object(MODULE.time, "time", return_value=1900000000):
            self.assertEqual(self.run_main(["usage", "--provider", "opencodego"], self.environment())["env"]["OPENCODE_API_KEY"], "account-a")
            with closing(sqlite3.connect(self.auth.with_name("opencode.db"))) as db, db:
                db.execute("UPDATE credential SET active=(time_updated=2) WHERE integration_id='opencode'")
            self.assertEqual(self.run_main(["usage", "--provider", "opencodego"], self.environment())["env"]["OPENCODE_API_KEY"], "account-b")
        self.assertEqual(self.auth.read_bytes(), before)

    def test_refreshable_selected_account_does_not_fall_back_to_legacy_identity(self):
        value = json.dumps({"type": "oauth", "access": "selected-access", "refresh": "NEVER-USE-REFRESH", "expires": 1})
        self.oauth_database([("opencode", 1, value, 1)])
        self.auth.write_text(json.dumps({"opencode-go": {"key": "different-legacy-account"}}))
        result = self.run_main(["usage", "--provider", "opencodego"], self.environment())
        self.assertEqual(result["env"]["OPENCODE_API_KEY"], "selected-access")

    def test_expired_wrong_provider_inactive_and_malformed_oauth_are_ignored(self):
        def value(expires, **extra):
            return json.dumps({"type": "oauth", "access": "secret", "expires": expires, **extra})
        self.oauth_database([("opencode", 1, value(1899999999000), 1),
                             ("opencode", 1, value(1900000020000), 2),
                             ("opencode", 0, value(2000000000000), 3),
                             ("openai", 1, value(2000000000000), 4),
                             ("opencode", 1, "not json", 5),
                             ("opencode", 1, "[]", 6),
                             ("opencode", 1, value(True), 7),
                             ("opencode", 1, value(2000000000000, access=""), 8)])
        before = self.auth.with_name("opencode.db").read_bytes()
        with mock.patch.object(MODULE.time, "time", return_value=1900000000):
            result = self.run_main(["usage", "--provider", "opencodego"], self.environment())
        self.assertNotIn("OPENCODE_API_KEY", result["env"])
        self.assertEqual(before, self.auth.with_name("opencode.db").read_bytes())

    def test_malformed_auth_json_still_falls_back_to_oauth(self):
        self.auth.write_text("invalid")
        self.oauth_database([("opencode", 1, json.dumps({"type": "oauth", "access": "fresh", "expires": 2000000000000}), 1)])
        with mock.patch.object(MODULE.time, "time", return_value=1900000000):
            result = self.run_main(["usage", "--provider=all"], self.environment())
        self.assertEqual(result["env"]["OPENCODE_API_KEY"], "fresh")

    def test_missing_upstream_reports_a_clear_error(self):
        with mock.patch.dict(os.environ, self.environment(), clear=True), \
                mock.patch.object(MODULE.pathlib.Path, "home", return_value=self.home), \
                mock.patch("sys.stderr") as stderr:
            with self.assertRaises(SystemExit) as raised:
                MODULE.main(["usage"])
        self.assertEqual(raised.exception.code, 127)
        written = "".join(call.args[0] for call in stderr.write.call_args_list)
        self.assertIn("codexbar-upstream", written)


if __name__ == "__main__":
    unittest.main()
