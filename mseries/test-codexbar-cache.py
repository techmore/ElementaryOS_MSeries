#!/usr/bin/env python3
"""Tests for the shared helper cache and the polling limits built on it. Throwaway homes only."""

import base64
import importlib.util
import json
import os
import pathlib
import stat
import sys
import tempfile
import unittest
from unittest import mock

HERE = pathlib.Path(__file__).parent
sys.path.insert(0, str(HERE))
import codexbar_cache as cache  # noqa: E402


def load(name, filename):
    spec = importlib.util.spec_from_file_location(name, HERE / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def auth_for(email, account_id):
    body = {"email": email, "https://api.openai.com/auth": {"chatgpt_plan_type": "plus"}}
    payload = base64.urlsafe_b64encode(json.dumps(body).encode()).decode().rstrip("=")
    return {"auth_mode": "chatgpt", "tokens": {"id_token": f"h.{payload}.s", "account_id": account_id}}


class Sandbox(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = pathlib.Path(self.tmp.name)
        self.root = root
        env = {"XDG_CACHE_HOME": str(root / "cache"), "XDG_DATA_HOME": str(root / "data"),
               "CODEX_HOME": str(root / "codex")}
        patcher = mock.patch.dict(os.environ, env)
        patcher.start()
        self.addCleanup(patcher.stop)
        (root / "codex").mkdir()


class CacheTest(Sandbox):
    def test_store_is_private_and_round_trips(self):
        cache.store("x", {"a": 1})
        self.assertEqual(cache.load("x"), {"a": 1})
        self.assertEqual(stat.S_IMODE((cache.cache_dir() / "x.json").stat().st_mode), 0o600)
        self.assertEqual(stat.S_IMODE(cache.cache_dir().stat().st_mode), 0o700)

    def test_corrupt_or_missing_cache_is_empty(self):
        self.assertEqual(cache.load("none"), {})
        cache.private_dir(cache.cache_dir())
        (cache.cache_dir() / "bad.json").write_text("{nope")
        self.assertEqual(cache.load("bad"), {})

    def test_backoff_doubles_and_caps(self):
        self.assertEqual([cache.backoff_seconds(n) for n in (0, 1, 2, 3)], [0, 60, 120, 240])
        self.assertEqual(cache.backoff_seconds(40), cache.MAX_BACKOFF_SECONDS)

    def test_freshness_and_backoff_windows(self):
        good = cache.succeeded({"v": 1}, 1000)
        self.assertTrue(cache.is_fresh(good, 100, 1050))
        self.assertFalse(cache.is_fresh(good, 100, 1100))
        self.assertFalse(cache.is_fresh(good, 100, 900), "a clock that went backwards is stale")
        bad = cache.failed(good, 1000)
        self.assertEqual(bad["data"], {"v": 1}, "the last good answer is kept")
        self.assertTrue(cache.in_backoff(bad, 1030))
        self.assertFalse(cache.in_backoff(bad, 1061))
        self.assertFalse(cache.is_fresh(bad, 100, 1010), "a failing entry is never fresh")

    def test_status_reports_age_and_failures(self):
        cache.store("claude-list", {"entry": cache.failed(cache.succeeded({"v": 1}, 1000), 1100)})
        cache.store("codex-usage", {"a@x.com|1": cache.succeeded({"v": 1}, 1000)})
        lines = cache.status_lines(now=1130)
        self.assertIn("claude-list: 130s old, 1 failures, retry in 30s", lines)
        self.assertIn("codex-usage a@x.com: 130s old", lines)

    def test_lock_is_exclusive(self):
        target = self.root / "state" / "thing"
        with cache.locked(target):
            with self.assertRaises(TimeoutError):
                with cache.locked(target, timeout=0.2):
                    pass
        with cache.locked(target, timeout=0.2):
            pass


class AccountsPollingTest(Sandbox):
    def setUp(self):
        super().setUp()
        self.mod = load("accounts_under_test", "codexbar-accounts.py")
        live = auth_for("live@example.com", "live")
        (self.root / "codex" / "auth.json").write_text(json.dumps(live))
        self.mod.save_current()
        other = auth_for("other@example.com", "other")
        self.mod.write_private(self.mod.store_dir() / self.mod.slug("other@example.com|other") / "auth.json", other)
        third = auth_for("third@example.com", "third")
        self.mod.write_private(self.mod.store_dir() / self.mod.slug("third@example.com|third") / "auth.json", third)
        self.good = {"windows": [{"key": "primary", "label": "5 hours", "remaining": 80.0, "resetsAt": ""}],
                     "resetCredits": None}

    def test_active_account_is_never_fetched_and_others_are_fetched_once(self):
        with mock.patch.object(self.mod, "usage_for", return_value=self.good) as fetch:
            first = self.mod.usage_report("codexbar", now=1000)
            second = self.mod.usage_report("codexbar", now=1100)
        self.assertEqual(fetch.call_count, 2, "two saved accounts fetched once; the cache serves the second report")
        live = next(a for a in first if a["email"] == "live@example.com")
        self.assertEqual(live.get("source"), "snapshot")
        self.assertNotIn("windows", live)
        other = next(a for a in second if a["email"] == "other@example.com")
        self.assertEqual(other["windows"], self.good["windows"])

    def test_cache_expires_and_force_bypasses_it(self):
        with mock.patch.object(self.mod, "usage_for", return_value=self.good) as fetch:
            self.mod.usage_report("codexbar", now=1000)
            self.mod.usage_report("codexbar", now=1000 + self.mod.USAGE_TTL_SECONDS + 1)
            self.assertEqual(fetch.call_count, 4)
            self.mod.usage_report("codexbar", now=1000 + self.mod.USAGE_TTL_SECONDS + 2, force=True)
            self.assertEqual(fetch.call_count, 6)

    def test_failure_keeps_last_quota_marks_it_stale_and_backs_off(self):
        with mock.patch.object(self.mod, "usage_for", return_value=self.good):
            self.mod.usage_report("codexbar", now=1000)
        later = 1000 + self.mod.USAGE_TTL_SECONDS + 1
        with mock.patch.object(self.mod, "usage_for", return_value={"error": "offline"}) as fetch:
            report = self.mod.usage_report("codexbar", now=later)
            self.assertEqual(fetch.call_count, 2)
            other = next(a for a in report if a["email"] == "other@example.com")
            self.assertTrue(other["stale"])
            self.assertEqual(other["windows"], self.good["windows"])
            self.mod.usage_report("codexbar", now=later + 30)
            self.assertEqual(fetch.call_count, 2, "inside the backoff window nothing is retried")
            self.mod.usage_report("codexbar", now=later + 61)
            self.assertEqual(fetch.call_count, 4)

    def test_saved_accounts_are_fetched_in_parallel(self):
        import threading
        seen = []
        both = threading.Barrier(2, timeout=5)

        def slow(home, cli):
            both.wait()  # only passes when both fetches are in flight at once
            seen.append(home)
            return self.good

        with mock.patch.object(self.mod, "usage_for", side_effect=slow):
            self.mod.usage_report("codexbar", now=1000)
        self.assertEqual(len(seen), 2)

    def test_forget_usage_drops_only_that_account(self):
        with mock.patch.object(self.mod, "usage_for", return_value=self.good):
            self.mod.usage_report("codexbar", now=1000)
        ids = set(cache.load("codex-usage"))
        self.assertEqual(len(ids), 2)
        self.mod.forget_usage(sorted(ids)[0])
        self.assertEqual(set(cache.load("codex-usage")), {sorted(ids)[1]})

    def test_credential_store_is_private(self):
        self.assertEqual(stat.S_IMODE(self.mod.store_dir().stat().st_mode), 0o700)
        self.assertEqual(stat.S_IMODE(self.mod.store_dir().parent.stat().st_mode), 0o700)


class TranscriptIndexTest(Sandbox):
    def setUp(self):
        super().setUp()
        self.mod = load("sessions_under_test", "codexbar-sessions.py")
        self.projects = self.root / "projects"
        (self.projects / "p").mkdir(parents=True)
        self.file = self.projects / "p" / "a.jsonl"
        self.now_ms = 1_800_000_000_000
        self.line = json.dumps({"type": "assistant", "requestId": "r1", "timestamp": "2027-01-15T08:00:00Z",
                                "message": {"usage": {"input_tokens": 5, "output_tokens": 7}}})
        self.file.write_text(self.line + "\n")
        os.utime(self.file, (self.now_ms / 1000, self.now_ms / 1000))

    def test_unchanged_transcripts_are_not_parsed_again(self):
        first = self.mod.read_claude_records(self.projects, self.now_ms)
        self.assertEqual([t for _, t, _ in first], [12])
        with mock.patch.object(self.mod, "parse_transcript", side_effect=AssertionError("reparsed")):
            again = self.mod.read_claude_records(self.projects, self.now_ms)
        self.assertEqual(again, first)

    def test_changed_transcript_is_parsed_and_removed_ones_dropped(self):
        self.mod.read_claude_records(self.projects, self.now_ms)
        more = json.dumps({"type": "assistant", "requestId": "r2", "timestamp": "2027-01-15T09:00:00Z",
                           "message": {"usage": {"input_tokens": 1, "output_tokens": 1}}})
        with self.file.open("a") as handle:
            handle.write(more + "\n")
        os.utime(self.file, (self.now_ms / 1000, self.now_ms / 1000))
        self.assertEqual(sorted(t for _, t, _ in self.mod.read_claude_records(self.projects, self.now_ms)), [2, 12])
        self.file.unlink()
        self.assertEqual(self.mod.read_claude_records(self.projects, self.now_ms), [])
        self.assertEqual(cache.load("claude-transcripts-v2")["files"], {})


class ClaudeListingTest(Sandbox):
    def setUp(self):
        super().setUp()
        self.mod = load("claude_under_test", "codexbar-claude.py")
        self.ok = {"available": True, "accounts": [{"number": "1", "email": "a@x.com", "active": True, "windows": []}],
                   "activeEmail": "a@x.com"}

    def test_list_is_cached_then_expires(self):
        with mock.patch.object(self.mod, "listing", return_value=self.ok) as call:
            self.mod.cached_listing("cswap", now=1000)
            self.assertEqual(self.mod.cached_listing("cswap", now=1050), self.ok)
            self.assertEqual(call.call_count, 1)
            self.mod.cached_listing("cswap", now=1000 + self.mod.LIST_TTL_SECONDS + 1)
            self.assertEqual(call.call_count, 2)
            self.mod.cached_listing("cswap", now=1050, force=True)
            self.assertEqual(call.call_count, 3)

    def test_failure_serves_last_good_list_flagged_stale_and_backs_off(self):
        with mock.patch.object(self.mod, "listing", return_value=self.ok):
            self.mod.cached_listing("cswap", now=1000)
        down = {"available": True, "accounts": [], "activeEmail": "", "failed": True}
        later = 1000 + self.mod.LIST_TTL_SECONDS + 1
        with mock.patch.object(self.mod, "listing", return_value=down) as call:
            result = self.mod.cached_listing("cswap", now=later)
            self.assertTrue(result["stale"])
            self.assertEqual(result["accounts"], self.ok["accounts"])
            self.mod.cached_listing("cswap", now=later + 10)
            self.assertEqual(call.call_count, 1, "backing off")

    def test_any_other_command_clears_the_cached_list(self):
        with mock.patch.object(self.mod, "listing", return_value=self.ok):
            self.mod.cached_listing("cswap", now=1000)
        self.assertTrue(cache.load("claude-list"))
        with mock.patch.object(self.mod, "cswap_path", return_value=None), mock.patch.object(self.mod, "switch", return_value=(True, "ok")):
            self.mod.main(["switch", "2"])
        self.assertFalse(cache.load("claude-list"))


if __name__ == "__main__":
    unittest.main()
