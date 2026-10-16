#!/usr/bin/env python3
"""Read-only health and local activity for the ChatGPT/Codex, Claude Code and OpenCode sessions.

Nothing here reads, prints or copies credentials: sign-in is judged from the
presence and shape of each tool's own files. Activity comes from their local
history (Claude Code transcripts, OpenCode's SQLite database) and is an
estimate of local use, not account quota.
"""

from __future__ import annotations

import datetime as dt
import json
import os
import pathlib
import shutil
import sqlite3
import sys
import time
from typing import Any

WINDOWS = (
    ("5 hours", 5 * 3600 * 1000),
    ("7 days", 7 * 24 * 3600 * 1000),
    ("30 days", 30 * 24 * 3600 * 1000),
)
MAX_TRANSCRIPT_FILES = 4000


def iso_time(timestamp_ms: int) -> str:
    return dt.datetime.fromtimestamp(timestamp_ms / 1000, dt.timezone.utc).isoformat().replace("+00:00", "Z")


def data_home(home: pathlib.Path) -> pathlib.Path:
    configured = os.environ.get("XDG_DATA_HOME")
    if configured and pathlib.Path(configured).is_absolute():
        return pathlib.Path(configured)
    return home / ".local/share"


def find_binary(name: str, home: pathlib.Path, extra: tuple[str, ...] = ()) -> str | None:
    found = shutil.which(name)
    if found:
        return found
    for relative in extra:
        candidate = home / relative
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return str(candidate)
    return None


def load_json_object(path: pathlib.Path) -> dict[str, Any] | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def summarize(records: list[tuple[int, int, float]], now_ms: int) -> list[dict[str, Any]]:
    periods = []
    for label, duration in WINDOWS:
        matching = [(tokens, cost) for created, tokens, cost in records if now_ms - duration <= created <= now_ms]
        periods.append({
            "label": label,
            "requests": len(matching),
            "tokens": sum(tokens for tokens, _ in matching),
            "costUSD": round(sum(cost for _, cost in matching), 6),
        })
    return periods


def codex_session(home: pathlib.Path) -> dict[str, Any]:
    auth = load_json_object(home / ".codex/auth.json")
    entry: dict[str, Any] = {"id": "codex", "name": "ChatGPT · Codex"}
    if auth is None:
        entry.update(state="off", detail="Not signed in. Open the ChatGPT desktop app or run codex login.")
    else:
        entry.update(state="ok", detail="Signed in · account quota comes from CodexBar.")
    return entry


def parse_timestamp(value: Any) -> int | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.timezone.utc)
    return int(parsed.timestamp() * 1000)


def read_claude_records(projects: pathlib.Path, now_ms: int) -> list[tuple[int, int, float]]:
    oldest = (now_ms - WINDOWS[-1][1]) / 1000
    files = []
    for path in projects.glob("**/*.jsonl"):
        try:
            if path.stat().st_mtime >= oldest:
                files.append(path)
        except OSError:
            continue
        if len(files) >= MAX_TRANSCRIPT_FILES:
            break
    # Streaming writes the same API response several times; keep the last copy of each.
    responses: dict[str, tuple[int, int]] = {}
    for path in files:
        try:
            with path.open(encoding="utf-8", errors="replace") as handle:
                for line in handle:
                    if '"usage"' not in line:
                        continue
                    try:
                        record = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    message = record.get("message") if isinstance(record, dict) else None
                    if record.get("type") != "assistant" or not isinstance(message, dict):
                        continue
                    usage = message.get("usage")
                    created = parse_timestamp(record.get("timestamp"))
                    if not isinstance(usage, dict) or created is None:
                        continue
                    try:
                        tokens = sum(int(usage.get(key) or 0) for key in
                                     ("input_tokens", "output_tokens", "cache_creation_input_tokens"))
                    except (TypeError, ValueError):
                        continue
                    key = str(record.get("requestId") or message.get("id") or record.get("uuid") or id(record))
                    responses[key] = (created, tokens)
        except OSError:
            continue
    return [(created, tokens, 0.0) for created, tokens in responses.values()]


def claude_session(home: pathlib.Path, now_ms: int) -> dict[str, Any]:
    entry: dict[str, Any] = {"id": "claude", "name": "Claude Code"}
    binary = find_binary("claude", home, (".local/bin/claude", ".claude/local/claude"))
    account = load_json_object(home / ".claude.json")
    profile = account.get("oauthAccount") if account else None
    signed_in = isinstance(profile, dict) and bool(profile.get("accountUuid"))
    projects = home / ".claude/projects"
    records = read_claude_records(projects, now_ms) if projects.is_dir() else []
    entry["periods"] = summarize(records, now_ms) if records else []
    entry["note"] = "Local activity from Claude Code transcripts · not account quota (tokens exclude cache reads)"
    if signed_in:
        where = "" if binary else " · desktop app session (no claude CLI on PATH)"
        entry.update(state="ok", detail="Signed in" + where)
    elif binary:
        entry.update(state="warn", detail="claude CLI found but not signed in. Run claude, then /login.")
    else:
        entry.update(state="off", detail="Claude Code is not installed or signed in.")
    return entry


def opencode_session(home: pathlib.Path, now_ms: int) -> dict[str, Any]:
    entry: dict[str, Any] = {"id": "opencode", "name": "OpenCode"}
    binary = find_binary("opencode", home, (".opencode/bin/opencode",))
    database = data_home(home) / "opencode/opencode.db"
    entry["note"] = "Local activity from OpenCode history · OpenCode Go account quota needs its web session"
    records: list[tuple[int, int, float]] = []
    providers: dict[str, int] = {}
    problem = ""
    if database.is_file():
        try:
            connection = sqlite3.connect(f"file:{database}?mode=ro", uri=True, timeout=0.5)
            try:
                columns = {row[1] for row in connection.execute("PRAGMA table_info(session_message)")}
                if {"type", "time_created", "data"}.issubset(columns):
                    for created, data in connection.execute(
                        "SELECT time_created, data FROM session_message WHERE type = 'assistant' AND json_valid(data)"
                    ):
                        try:
                            payload = json.loads(data)
                            tokens_info = payload.get("tokens") or {}
                            if tokens_info.get("total") is not None:
                                tokens = int(tokens_info["total"])
                            else:
                                cache = tokens_info.get("cache") or {}
                                tokens = sum(int(value or 0) for value in (
                                    tokens_info.get("input"), tokens_info.get("output"),
                                    tokens_info.get("reasoning"), cache.get("read"), cache.get("write")))
                            cost = payload.get("cost")
                            cost = float(cost) if isinstance(cost, (int, float)) and cost >= 0 else 0.0
                            provider = str((payload.get("model") or {}).get("providerID") or "unknown")
                            records.append((int(created), tokens, cost))
                            providers[provider] = providers.get(provider, 0) + 1
                        except (TypeError, ValueError, AttributeError):
                            continue
                else:
                    problem = "OpenCode history uses an unsupported schema."
            finally:
                connection.close()
        except (sqlite3.Error, OSError) as error:
            problem = f"Could not read OpenCode history: {error}"
    entry["periods"] = summarize(records, now_ms) if records else []
    if providers:
        entry["providers"] = sorted(providers, key=providers.get, reverse=True)
    auth = load_json_object(data_home(home) / "opencode/auth.json")
    has_keys = bool(auth)
    if problem:
        entry.update(state="warn", detail=problem)
    elif binary and (records or has_keys):
        entry.update(state="ok", detail="Ready" + (" · signed-in providers: " + ", ".join(sorted(auth)) if has_keys else
                                                   " · using built-in free models"))
    elif binary:
        entry.update(state="ok", detail="Installed · no sessions yet.")
    else:
        entry.update(state="off", detail="OpenCode is not installed.")
    return entry


def collect(home: pathlib.Path | None = None, now_ms: int | None = None) -> dict[str, Any]:
    home = home or pathlib.Path.home()
    now_ms = int(time.time() * 1000) if now_ms is None else now_ms
    return {
        "updatedAt": iso_time(now_ms),
        "sessions": [codex_session(home), claude_session(home, now_ms), opencode_session(home, now_ms)],
    }


def main() -> int:
    print(json.dumps(collect(), separators=(",", ":")))
    return 0


if __name__ == "__main__":
    sys.exit(main())
