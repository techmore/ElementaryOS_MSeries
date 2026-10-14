#!/usr/bin/env python3
"""Tests for the read-only OpenCode v2 local usage adapter."""

import importlib.util
import pathlib
import sqlite3
import tempfile
import unittest


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


if __name__ == "__main__":
    unittest.main()
