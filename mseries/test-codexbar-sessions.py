#!/usr/bin/env python3
"""Tests for the read-only ChatGPT/Claude/OpenCode/Grok session health helper."""

import importlib.util
import json
import pathlib
import sqlite3
import os
import tempfile
import unittest
from unittest import mock

import tempfile as _tempfile

# Helpers cache under XDG_CACHE_HOME; keep the tests away from the real one.
os.environ["XDG_CACHE_HOME"] = _tempfile.mkdtemp(prefix="codexbar-test-cache-")

SCRIPT = pathlib.Path(__file__).with_name("codexbar-sessions.py")
SPEC = importlib.util.spec_from_file_location("codexbar_sessions", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)

NOW = 1_800_000_000_000


def stamp(offset_ms):
    return MODULE.iso_time(NOW - offset_ms)


class SessionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.home = pathlib.Path(self.temp.name)
        patcher = mock.patch.dict(os.environ, {"PATH": "", "XDG_DATA_HOME": "", "GROK_HOME": "", "XAI_API_KEY": ""})
        patcher.start()
        self.addCleanup(patcher.stop)

    def tearDown(self):
        self.temp.cleanup()

    def test_nothing_installed_reports_off_not_crash(self):
        states = {s["id"]: s["state"] for s in MODULE.collect(self.home, NOW)["sessions"]}
        self.assertEqual(states, {"codex": "off", "claude": "off", "opencode": "off", "grok": "off"})

    def test_codex_signed_in_by_auth_file_without_leaking_contents(self):
        (self.home / ".codex").mkdir()
        (self.home / ".codex/auth.json").write_text('{"tokens":{"access_token":"SECRET"}}')
        codex = MODULE.collect(self.home, NOW)["sessions"][0]
        self.assertEqual(codex["state"], "ok")
        self.assertNotIn("SECRET", json.dumps(codex))

    def test_claude_dedupes_streamed_responses_and_windows(self):
        (self.home / ".claude.json").write_text('{"oauthAccount":{"accountUuid":"x"}}')
        project = self.home / ".claude/projects/p"
        project.mkdir(parents=True)
        def line(request, offset, output):
            return json.dumps({"type": "assistant", "requestId": request, "timestamp": stamp(offset),
                               "message": {"usage": {"input_tokens": 2, "output_tokens": output,
                                                     "cache_creation_input_tokens": 8,
                                                     "cache_read_input_tokens": 999}}})
        lines = [line("a", 1000, 5), line("a", 900, 10), line("b", 6 * 3600 * 1000, 20), "not json \"usage\""]
        (project / "s.jsonl").write_text("\n".join(lines) + "\n")
        os.utime(project / "s.jsonl", (NOW / 1000, NOW / 1000))
        claude = MODULE.collect(self.home, NOW)["sessions"][1]
        self.assertEqual(claude["state"], "ok")
        self.assertEqual(claude["periods"][0], {"label": "5 hours", "requests": 1, "tokens": 1019, "costUSD": 0.0})
        self.assertEqual(claude["periods"][1]["requests"], 2)
        self.assertEqual(claude["periods"][1]["tokens"], 1019 + 1029)

    def test_same_processed_total_across_provider_schemas(self):
        tokens = MODULE.codexbar_tokens
        self.assertEqual(tokens.claude_tokens({"input_tokens": 10, "output_tokens": 20,
            "cache_read_input_tokens": 60, "cache_creation_input_tokens": 10,
            "cache_creation": {"one_hour": 10}, "output_tokens_details": {"reasoning": 5}}), 100)
        self.assertEqual(tokens.codex_tokens({"input_tokens": 80, "output_tokens": 20,
            "cached_input_tokens": 60, "reasoning_output_tokens": 5, "total_tokens": 100}), 100)
        self.assertEqual(tokens.opencode_tokens({"input": 10, "output": 15, "reasoning": 5,
            "cache": {"read": 60, "write": 10}}), 100)
        self.assertEqual(tokens.opencode_tokens({"total":100,"input":100,"output":100}), 100)
        for bad in [-1, True, 1.5, float("inf"), "bad"]:
            with self.assertRaises((ValueError, OverflowError)):
                tokens.claude_tokens({"input_tokens": bad})

    def test_codex_recent_calls_not_lifetime_repeated_or_copied_history(self):
        directory = self.home / ".codex/sessions/a"
        directory.mkdir(parents=True)
        def event(offset, total, last=None):
            info = {"total_token_usage": {"total_tokens": total}}
            if last is not None: info["last_token_usage"] = {"total_tokens": last}
            return json.dumps({"type":"event_msg", "timestamp":stamp(offset),
                "payload":{"type":"token_count", "info":info}})
        lines = [event(8*86400*1000, 1000, 1000), event(1000,1100,100),
                 event(900,1100,100), event(800,1150,50), "[]", "bad json"]
        file = directory / "a.jsonl"
        file.write_text("\n".join(lines)+"\n")
        archive = self.home / ".codex/archived_sessions"
        archive.mkdir(parents=True)
        (archive / "copied.jsonl").write_text(file.read_text())
        for path in [file, archive / "copied.jsonl"]: os.utime(path, (NOW/1000,NOW/1000))
        result = MODULE.collect(self.home, NOW)["sessions"][0]
        self.assertEqual(result["periods"][1]["tokens"],150)
        self.assertEqual(result["periods"][1]["requests"],2)
        with mock.patch.object(MODULE.codexbar_tokens,"parse_codex",side_effect=AssertionError("reparsed")):
            self.assertEqual(MODULE.collect(self.home, NOW)["sessions"][0]["periods"],result["periods"])
        with file.open("a") as f: f.write(event(700,1180,30)+"\n")
        os.utime(file,(NOW/1000,NOW/1000))
        self.assertEqual(MODULE.collect(self.home,NOW)["sessions"][0]["periods"][1]["tokens"],180)

    def test_codex_resume_baseline_reset_and_malformed_records(self):
        directory = self.home / ".codex/sessions"
        directory.mkdir(parents=True)
        def event(total,last=None):
            info={"total_token_usage":{"total_tokens":total}}
            if last is not None: info["last_token_usage"]={"total_tokens":last}
            return json.dumps({"type":"event_msg","timestamp":stamp(1000-total),
                "payload":{"type":"token_count","info":info}})
        file=directory/"b.jsonl"
        file.write_text("\n".join([event(500),event(550),event(20,20),event(-1,5),
            '{"type":"event_msg","payload":[]}', '[]'])+"\n")
        os.utime(file,(NOW/1000,NOW/1000))
        result=MODULE.collect(self.home,NOW)["sessions"][0]
        self.assertEqual(result["periods"][1]["tokens"],70)

    def test_opencode_counts_all_providers_read_only(self):
        data = self.home / ".local/share/opencode"
        data.mkdir(parents=True)
        db = data / "opencode.db"
        connection = sqlite3.connect(db)
        connection.execute("CREATE TABLE session_message (id TEXT, session_id TEXT, type TEXT, seq INTEGER, "
                           "time_created INTEGER, time_updated INTEGER, data TEXT)")
        connection.executemany("INSERT INTO session_message VALUES (?,?,?,?,?,?,?)", [
            ("1", "s", "assistant", 1, NOW - 1000, 0, '{"model":{"providerID":"opencode"},"cost":0,"tokens":{"total":50}}'),
            ("2", "s", "assistant", 2, NOW - 2000, 0, '{"model":{"providerID":"opencode-go"},"cost":0.5,"tokens":{"input":1,"output":2}}'),
            ("3", "s", "user", 3, NOW - 3000, 0, '{}'),
        ])
        connection.commit()
        connection.close()
        before = db.read_bytes()
        opencode = MODULE.collect(self.home, NOW)["sessions"][2]
        self.assertEqual(opencode["periods"][0], {"label": "5 hours", "requests": 2, "tokens": 53, "costUSD": 0.5})
        self.assertEqual(set(opencode["providers"]), {"opencode", "opencode-go"})
        self.assertEqual(db.read_bytes(), before)

    # ---- Grok Build -------------------------------------------------------------------

    def grok_session_dir(self, name, workspace="%2Fhome%2Fme"):
        directory = self.home / ".grok/sessions" / workspace / name
        directory.mkdir(parents=True)
        return directory

    def grok_turn(self, number, offset, total, calls=1, **extra):
        turn = {"turnNumber": number, "endedAt": stamp(offset), "inputTokens": total - 10,
                "outputTokens": 10, "cachedReadTokens": total // 2, "reasoningTokens": 4,
                "totalTokens": total, "modelCalls": calls, "costUsdTicks": 6988060000}
        turn.update(extra)
        return turn

    def write_grok_usage(self, directory, turns):
        path = directory / "usage.json"
        path.write_text(json.dumps({"sessionId": directory.name, "updatedAt": stamp(0),
                                    "session": {"turnCount": len(turns)},
                                    "turns": turns}))
        os.utime(path, (NOW / 1000, NOW / 1000))
        return path

    def grok(self):
        return next(s for s in MODULE.collect(self.home, NOW)["sessions"] if s["id"] == "grok")

    def test_grok_windows_count_turns_by_end_time_without_dollars(self):
        self.write_grok_usage(self.grok_session_dir("a"), [
            self.grok_turn(1, 1000, 762841, 14),
            self.grok_turn(2, 6 * 3600 * 1000, 500),
            self.grok_turn(3, 8 * 86400 * 1000, 900),
            self.grok_turn(4, 40 * 86400 * 1000, 7),
        ])
        grok = self.grok()
        self.assertEqual(grok["periods"][0], {"label": "5 hours", "requests": 1, "tokens": 762841, "costUSD": 0.0})
        self.assertEqual(grok["periods"][1]["tokens"], 762841 + 500)
        self.assertEqual(grok["periods"][2]["tokens"], 762841 + 500 + 900)
        self.assertEqual(grok["periods"][2]["requests"], 3)

    def test_grok_total_falls_back_to_input_plus_output(self):
        tokens = MODULE.codexbar_tokens
        self.assertEqual(tokens.grok_tokens({"inputTokens": 90, "outputTokens": 10, "cachedReadTokens": 60,
                                             "reasoningTokens": 5}), 100)
        self.assertEqual(tokens.grok_tokens({"totalTokens": 100, "inputTokens": 1}), 100)
        with self.assertRaises(ValueError):
            tokens.grok_tokens({"totalTokens": -1})

    def test_grok_resumed_or_forked_history_counts_once(self):
        shared = [self.grok_turn(1, 2000, 300, 3), self.grok_turn(2, 1000, 200, 2)]
        self.write_grok_usage(self.grok_session_dir("original"), shared)
        self.write_grok_usage(self.grok_session_dir("fork", "%2Ftmp%2Fwt"), shared + [self.grok_turn(3, 500, 50)])
        self.assertEqual(self.grok()["periods"][1], {"label": "7 days", "requests": 3, "tokens": 550, "costUSD": 0.0})

    def test_grok_reads_only_session_usage_files(self):
        session = self.grok_session_dir("a")
        self.write_grok_usage(session, [self.grok_turn(1, 1000, 10)])
        nested = session / "terminal" / "child"
        nested.mkdir(parents=True)
        self.write_grok_usage(nested, [self.grok_turn(1, 900, 999)])
        (self.home / ".grok/sessions/%2Fhome%2Fme/prompt_history.jsonl").write_text("{}\n")
        outside = self.home / "elsewhere"
        outside.mkdir()
        self.write_grok_usage(outside, [self.grok_turn(1, 800, 5000)])
        (self.home / ".grok/sessions/%2Fhome%2Fme/linked").symlink_to(outside, target_is_directory=True)
        self.assertEqual(self.grok()["periods"][1]["tokens"], 10)

    def test_grok_malformed_and_oversized_files_are_skipped(self):
        bad = self.grok_session_dir("bad") / "usage.json"
        bad.write_text("{not json")
        self.write_grok_usage(self.grok_session_dir("odd"), [
            "turn", {"endedAt": "yesterday", "totalTokens": 5}, self.grok_turn(1, 1000, True),
            self.grok_turn(2, 1000, 40)])
        huge = self.grok_session_dir("huge") / "usage.json"
        huge.write_text(" " * (MODULE.MAX_GROK_USAGE_BYTES + 1))
        os.utime(huge, (NOW / 1000, NOW / 1000))
        self.assertEqual(self.grok()["periods"][1]["tokens"], 40)

    def test_grok_unchanged_files_are_not_reparsed(self):
        path = self.write_grok_usage(self.grok_session_dir("a"), [self.grok_turn(1, 1000, 10)])
        first = self.grok()["periods"]
        with mock.patch.object(MODULE, "parse_grok_usage", side_effect=AssertionError("reparsed")):
            self.assertEqual(self.grok()["periods"], first)
        self.write_grok_usage(path.parent, [self.grok_turn(1, 1000, 10), self.grok_turn(2, 500, 5)])
        os.utime(path, (NOW / 1000 + 1, NOW / 1000 + 1))
        self.assertEqual(self.grok()["periods"][1]["tokens"], 15)

    def test_grok_sign_in_state_never_exposes_credentials(self):
        grok_dir = self.home / ".grok"
        (grok_dir / "bin").mkdir(parents=True)
        binary = grok_dir / "bin/grok"
        binary.write_text("#!/bin/sh\n")
        binary.chmod(0o755)
        self.assertEqual(self.grok()["state"], "warn")
        with mock.patch.dict(os.environ, {"XAI_API_KEY": "xai-SECRETKEY"}):
            api = self.grok()
        self.assertEqual(api["state"], "ok")
        self.assertNotIn("SECRETKEY", json.dumps(api))
        (grok_dir / "auth.json").write_text(json.dumps({
            "https://accounts.x.ai/sign-in": {"key": "LEGACY-SECRET", "email": "legacy@example.com"},
            "https://auth.x.ai::client": {"key": "BEARER-SECRET", "refresh_token": "REFRESH-SECRET",
                                          "email": "me@example.com", "first_name": "Private"}}))
        signed_in = self.grok()
        self.assertEqual(signed_in["state"], "ok")
        # The identity row shows the SuperGrok account's email, as upstream does; nothing else leaves the file.
        self.assertEqual(signed_in["accountEmail"], "me@example.com")
        for secret in ("BEARER-SECRET", "REFRESH-SECRET", "LEGACY-SECRET", "legacy@example.com", "Private"):
            self.assertNotIn(secret, json.dumps(MODULE.collect(self.home, NOW)))
        (grok_dir / "auth.json").write_text(json.dumps({"https://auth.x.ai::c": {"email": ["not", "text"]}}))
        self.assertNotIn("accountEmail", self.grok())

    def test_grok_home_override(self):
        custom = self.home / "custom-grok"
        session = custom / "sessions/w/s"
        session.mkdir(parents=True)
        self.write_grok_usage(session, [self.grok_turn(1, 1000, 77)])
        with mock.patch.dict(os.environ, {"GROK_HOME": str(custom)}):
            self.assertEqual(self.grok()["periods"][1]["tokens"], 77)
        with mock.patch.dict(os.environ, {"GROK_HOME": "relative/path"}):
            self.assertEqual(self.grok()["periods"], [])


if __name__ == "__main__":
    unittest.main()
