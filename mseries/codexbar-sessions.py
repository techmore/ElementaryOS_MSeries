#!/usr/bin/env python3
"""Read-only health and local activity for the ChatGPT/Codex, Claude Code, OpenCode and Grok Build sessions.

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

import codexbar_cache
import codexbar_tokens
import codexbar_history

WINDOWS = codexbar_history.WINDOWS
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


def codex_session(home: pathlib.Path, now_ms: int) -> dict[str, Any]:
    auth = load_json_object(home / ".codex/auth.json")
    entry: dict[str, Any] = {"id": "codex", "name": "ChatGPT · Codex"}
    if auth is None:
        entry.update(state="off", detail="Not signed in. Open the ChatGPT desktop app or run codex login.")
    else:
        entry.update(state="ok", detail="Signed in · account quota comes from CodexBar.")
    records = codexbar_tokens.read_codex(home, now_ms, parse_timestamp)
    entry["periods"] = summarize(records, now_ms) if records else []
    entry["note"] = "Local Codex activity · all local accounts · includes cache reads/writes · not account quota"
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


def parse_transcript(path: pathlib.Path) -> dict[str, list[int]]:
    """Assistant responses in one transcript as {request id: [created ms, tokens]}."""
    responses: dict[str, list[int]] = {}
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
                if not isinstance(record, dict) or record.get("type") != "assistant" or not isinstance(message, dict):
                    continue
                usage = message.get("usage")
                created = parse_timestamp(record.get("timestamp"))
                if not isinstance(usage, dict) or created is None:
                    continue
                try:
                    tokens = codexbar_tokens.claude_tokens(usage)
                except (TypeError, ValueError, OverflowError):
                    continue
                key = str(record.get("requestId") or message.get("id") or record.get("uuid") or f"{path}:{len(responses)}")
                responses[key] = [created, tokens]  # streaming repeats a response; the last copy wins
    except OSError:
        pass
    return responses


def read_claude_records(projects: pathlib.Path, now_ms: int) -> list[tuple[int, int, float]]:
    """Token records from recent transcripts. Only files whose size or mtime changed are parsed again; the
    per-file results live in the cache so a repeat scan costs one stat per file."""
    oldest = (now_ms - WINDOWS[-1][1]) / 1000
    index = codexbar_cache.load("claude-transcripts-v2").get("files")
    index = index if isinstance(index, dict) else {}
    kept: dict[str, Any] = {}
    count = 0
    for path in projects.glob("**/*.jsonl"):
        try:
            info = path.stat()
        except OSError:
            continue
        if info.st_mtime < oldest:
            continue
        count += 1
        if count > MAX_TRANSCRIPT_FILES:
            break
        known = index.get(str(path))
        if isinstance(known, dict) and isinstance(known.get("responses"), dict) and known.get("size") == info.st_size and known.get("mtime") == info.st_mtime_ns:
            kept[str(path)] = known
        else:
            kept[str(path)] = {"size": info.st_size, "mtime": info.st_mtime_ns, "responses": parse_transcript(path)}
    if kept.keys() != index.keys() or any(kept[k] is not index.get(k) for k in kept):
        codexbar_cache.store("claude-transcripts-v2", {"files": kept})
    # A response can appear in several transcripts (resumed sessions); count it once.
    responses: dict[str, tuple[int, int]] = {}
    for entry in kept.values():
        for key, (created, tokens) in entry["responses"].items():
            responses[key] = (created, tokens)
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
    entry["note"] = "Local activity from Claude Code transcripts · all local accounts · includes cache reads/writes · not account quota"
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
    entry["note"] = "Local activity from OpenCode history · all local accounts/providers · includes cache reads/writes · not account quota"
    periods: list[dict[str, Any]] = []
    providers: dict[str, int] = {}
    problem = ""
    if database.is_file():
        try:
            periods, providers = codexbar_history.opencode_summary(database, now_ms)
        except (sqlite3.Error, OSError) as error:
            problem = f"Could not read OpenCode history: {error}"
    entry["periods"] = periods if providers else []
    if providers:
        entry["providers"] = sorted(providers, key=providers.get, reverse=True)
    auth = load_json_object(data_home(home) / "opencode/auth.json")
    has_keys = bool(auth)
    if problem:
        entry.update(state="warn", detail=problem)
    elif binary and (providers or has_keys):
        entry.update(state="ok", detail="Ready" + (" · signed-in providers: " + ", ".join(sorted(auth)) if has_keys else
                                                   " · using built-in free models"))
    elif binary:
        entry.update(state="ok", detail="Installed · no activity in the last 30 days.")
    else:
        entry.update(state="off", detail="OpenCode is not installed.")
    return entry


MAX_GROK_USAGE_BYTES = 8 * 1024 * 1024


def grok_home(home: pathlib.Path) -> pathlib.Path:
    configured = os.environ.get("GROK_HOME")
    if configured and pathlib.Path(configured).is_absolute():
        return pathlib.Path(configured)
    return home / ".grok"


def parse_grok_usage(path: pathlib.Path) -> dict[str, list[int]]:
    """Completed turns in one session's usage.json as {fingerprint: [ended ms, tokens]}.

    This is the documented `grok usage <session-id>` envelope that Grok Build persists per
    session. A resumed or forked session inherits earlier turns, so fingerprints are
    content-based (end time, tokens, model calls) and deduplicate across sessions."""
    turns: dict[str, list[int]] = {}
    try:
        if path.stat().st_size > MAX_GROK_USAGE_BYTES:
            return turns
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return turns
    recorded = document.get("turns") if isinstance(document, dict) else None
    for turn in recorded if isinstance(recorded, list) else []:
        if not isinstance(turn, dict):
            continue
        ended = parse_timestamp(turn.get("endedAt"))
        if ended is None:
            continue
        try:
            tokens = codexbar_tokens.grok_tokens(turn)
            calls = codexbar_tokens.count(turn.get("modelCalls"))
        except (TypeError, ValueError, OverflowError):
            continue
        turns[f"{ended}:{tokens}:{calls}"] = [ended, tokens]
    return turns


def read_grok_records(sessions: pathlib.Path, now_ms: int) -> list[tuple[int, int, float]]:
    """Token records from Grok session usage files changed in the last 30 days.

    Only `<encoded cwd>/<session id>/usage.json` is read: artifact and terminal trees
    are never walked, symlinked directories are skipped, and unchanged files reuse
    the cached parse. Dollar figures are omitted: subscription credits are not spend."""
    oldest = (now_ms - WINDOWS[-1][1]) / 1000
    index = codexbar_cache.load("grok-usage-v1").get("files")
    index = index if isinstance(index, dict) else {}
    kept: dict[str, Any] = {}
    count = 0
    try:
        workspaces = [entry for entry in os.scandir(sessions) if entry.is_dir(follow_symlinks=False)]
    except OSError:
        workspaces = []
    for workspace in workspaces:
        try:
            session_dirs = [entry for entry in os.scandir(workspace.path) if entry.is_dir(follow_symlinks=False)]
        except OSError:
            continue
        for session_dir in session_dirs:
            path = pathlib.Path(session_dir.path) / "usage.json"
            try:
                info = path.lstat()
            except OSError:
                continue
            if not path.is_file() or path.is_symlink() or info.st_mtime < oldest:
                continue
            count += 1
            if count > MAX_TRANSCRIPT_FILES:
                break
            known = index.get(str(path))
            if (isinstance(known, dict) and isinstance(known.get("turns"), dict)
                    and known.get("size") == info.st_size and known.get("mtime") == info.st_mtime_ns):
                kept[str(path)] = known
            else:
                kept[str(path)] = {"size": info.st_size, "mtime": info.st_mtime_ns, "turns": parse_grok_usage(path)}
    if kept.keys() != index.keys() or any(kept[k] is not index.get(k) for k in kept):
        codexbar_cache.store("grok-usage-v1", {"files": kept})
    turns: dict[str, tuple[int, int]] = {}
    for entry in kept.values():
        for key, value in entry["turns"].items():
            if isinstance(value, list) and len(value) == 2:
                turns[key] = (value[0], value[1])
    return [(ended, tokens, 0.0) for ended, tokens in turns.values()]


GROK_IDENTITY_SCOPES = ("https://auth.x.ai", "https://accounts.x.ai/sign-in")


def grok_account_email(auth: dict[str, Any] | None) -> str:
    """The signed-in email, chosen as upstream does (SuperGrok OIDC entry, then the legacy session).

    Only `email` is read from the matching entry; bearer and refresh tokens are never touched."""
    for prefix in GROK_IDENTITY_SCOPES:
        for scope, value in sorted((auth or {}).items()):
            if isinstance(scope, str) and scope.startswith(prefix) and isinstance(value, dict):
                email = value.get("email")
                if isinstance(email, str) and "@" in email and len(email) <= 320:
                    return email.strip()
    return ""


def grok_session(home: pathlib.Path, now_ms: int) -> dict[str, Any]:
    entry: dict[str, Any] = {"id": "grok", "name": "Grok Build"}
    root = grok_home(home)
    binary = find_binary("grok", home, (".grok/bin/grok", ".local/bin/grok"))
    sessions = root / "sessions"
    records = read_grok_records(sessions, now_ms) if sessions.is_dir() else []
    entry["periods"] = summarize(records, now_ms) if records else []
    entry["note"] = ("Local activity from Grok Build session usage · includes cached input and reasoning · "
                     "not account quota")
    # Sign-in is judged from the credential file's presence and shape only; its values are never read out.
    auth = load_json_object(root / "auth.json")
    signed_in = bool(auth)
    email = grok_account_email(auth)
    if email:
        entry["accountEmail"] = email
    api_key = bool(os.environ.get("XAI_API_KEY", "").strip())
    if signed_in:
        entry.update(state="ok", detail="Signed in · account credits come from CodexBar.")
    elif api_key and binary:
        entry.update(state="ok", detail="Using XAI_API_KEY · run grok login for SuperGrok credits in CodexBar.")
    elif binary:
        entry.update(state="warn", detail="grok found but not signed in. Run grok login.")
    else:
        entry.update(state="off", detail="Grok Build is not installed.")
    return entry


def collect(home: pathlib.Path | None = None, now_ms: int | None = None) -> dict[str, Any]:
    home = home or pathlib.Path.home()
    now_ms = int(time.time() * 1000) if now_ms is None else now_ms
    return {
        "updatedAt": iso_time(now_ms),
        "sessions": [codex_session(home, now_ms), claude_session(home, now_ms), opencode_session(home, now_ms),
                     grok_session(home, now_ms)],
    }


def main() -> int:
    print(json.dumps(collect(), separators=(",", ":")))
    return 0


if __name__ == "__main__":
    sys.exit(main())
