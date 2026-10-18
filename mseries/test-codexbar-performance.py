#!/usr/bin/env python3
"""Synthetic regressions for bounded history reads and the read-only panel watch."""
import importlib.util
import json
import pathlib
import sqlite3
import tempfile
import unittest
from unittest import mock

import codexbar_history
import codexbar_cache

spec = importlib.util.spec_from_file_location("panel_watch", pathlib.Path(__file__).with_name("codexbar-wingpanel-watch.py"))
watch = importlib.util.module_from_spec(spec)
spec.loader.exec_module(watch)


class HistoryTests(unittest.TestCase):
    def test_backoff_arithmetic_is_bounded_even_for_a_corrupt_failure_counter(self):
        self.assertEqual([codexbar_cache.backoff_seconds(i) for i in (0, 1, 2, 3, 7)],
                         [0, 60, 120, 240, 3600])
        self.assertEqual(codexbar_cache.backoff_seconds(10**100), 3600)

    def test_time_bounds_filter_before_python_decoding_and_do_not_write_database(self):
        now = 1_800_000_000_000
        payload = json.dumps({"tokens": {"total": 100}, "cost": 0.25,
                              "model": {"providerID": "opencode-go"}})
        with tempfile.TemporaryDirectory() as directory:
            path = pathlib.Path(directory) / "usage ?#.db"
            with sqlite3.connect(path) as db:
                db.execute("CREATE TABLE session_message(type TEXT, time_created INTEGER, data TEXT)")
                db.executemany("INSERT INTO session_message VALUES ('assistant',?,?)", [
                    (now - codexbar_history.HISTORY_MS - 1, payload), (now + 1, payload),
                    (now - codexbar_history.HISTORY_MS, payload), (now, payload), (now, "[]"),
                    (now, "invalid"), (now, '{"tokens":{"total":true}}')])
            before = path.read_bytes()
            decode = json.loads
            with mock.patch.object(codexbar_history.json, "loads", wraps=decode) as loads:
                records = list(codexbar_history.opencode_records(path, now))
                self.assertEqual(loads.call_count, 4)  # two valid, array and invalid token type
            self.assertEqual([r[1:] for r in records], [(100, .25, "opencode-go")] * 2)
            self.assertEqual(path.read_bytes(), before)
            self.assertEqual(len(list(codexbar_history.opencode_records(path, now, provider="opencode-go", cost_only=True))), 2)

    def test_schema_failure_is_explicit(self):
        with tempfile.TemporaryDirectory() as directory:
            path = pathlib.Path(directory) / "usage.db"
            sqlite3.connect(path).close()
            with self.assertRaisesRegex(sqlite3.OperationalError, "unsupported schema"):
                list(codexbar_history.opencode_records(path, 1))


class WatchTests(unittest.TestCase):
    def snapshot(self, pid=12, start=100, boot="boot", tick=10, clock=1):
        return {"bootId": boot, "monotonic": clock, "checkedAt": clock,
                "panels": [] if pid is None else [{"pid": pid, "startTicks": start, "cpuTicks": tick,
                    "rssKiB": 100, "fds": 20, "launcher": {"pid": 1, "alive": True, "exe": "/bin/gala"}}]}

    def test_baseline_stable_and_restart_are_distinct_from_crash(self):
        previous, report = watch.assess({}, self.snapshot(), [], [])
        self.assertFalse(report["actionable"])
        previous, report = watch.assess(previous, self.snapshot(clock=2), [], [])
        self.assertFalse(report["actionable"])
        _, report = watch.assess(previous, self.snapshot(start=101, clock=3), [], [])
        self.assertEqual(report["events"], [{"category": "panel_restarted_unclassified"}])
        self.assertTrue(report["healthy"])  # PID reuse is a transition, not crash proof.

    def test_core_and_popup_events_are_deduplicated_without_storing_raw_text(self):
        previous, _ = watch.assess({}, self.snapshot(), [], [])
        rows = [{"__CURSOR": "a", "COREDUMP_EXE": watch.PANEL_EXE, "COREDUMP_PID": "12"},
                {"__CURSOR": "b", "MESSAGE": "Finalizing PRIVATE still has children left", "PRIORITY": "4"}]
        state, report = watch.assess(previous, self.snapshot(clock=2), rows, [])
        self.assertTrue(report["actionable"])
        self.assertFalse(report["healthy"])
        self.assertNotIn("PRIVATE", json.dumps([state, report]))
        _, report = watch.assess(state, self.snapshot(clock=3), rows, [])
        self.assertFalse(report["actionable"])

    def test_missing_recovery_duplicate_panels_and_observation_failure(self):
        previous, report = watch.assess({}, self.snapshot(pid=None), [], [])
        self.assertEqual(report["events"][0]["category"], "panel_missing")
        previous, report = watch.assess(previous, self.snapshot(), [], [])
        self.assertEqual(report["events"][0]["category"], "panel_recovered")
        current = self.snapshot()
        current["panels"] += self.snapshot(pid=13)["panels"]
        _, report = watch.assess(previous, current, [], ["Journal unavailable"])
        self.assertIn("multiple_panels", [e["category"] for e in report["events"]])
        self.assertFalse(report["healthy"])

    def test_launcher_core_is_reported_without_attaching_to_the_launcher(self):
        previous, _ = watch.assess({}, self.snapshot(), [], [])
        _, report = watch.assess(previous, self.snapshot(clock=2), [
            {"__CURSOR": "launcher-core", "COREDUMP_EXE": "/bin/gala", "COREDUMP_PID": "1"}], [])
        self.assertEqual(report["events"][0]["category"], "launcher_coredump")
        self.assertFalse(report["healthy"])

    def test_startup_warning_and_new_boot_are_not_crash_alerts(self):
        previous, _ = watch.assess({}, self.snapshot(), [], [])
        _, report = watch.assess(previous, self.snapshot(pid=13, boot="new"), [
            {"__CURSOR": "c", "MESSAGE": "gtk_flow_box_set_max_children_per_line: assertion failed", "PRIORITY": "2"}], [])
        self.assertTrue(report["baseline"])
        self.assertFalse(report["actionable"])


if __name__ == "__main__":
    unittest.main()
