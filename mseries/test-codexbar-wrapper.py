#!/usr/bin/env python3
"""Tests for the CodexBar wrapper that hands OpenCode Go credentials to upstream."""

import importlib.util
import json
import os
import pathlib
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
