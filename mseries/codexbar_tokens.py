"""Local processed-token accounting. No credentials, prompts, network requests or quota estimates."""
from __future__ import annotations

import hashlib
import json
import pathlib
from typing import Any

import codexbar_cache


def count(value: Any) -> int:
    if value is None:
        return 0
    if isinstance(value, bool):
        raise ValueError("boolean token count")
    result = int(value)
    if result < 0 or result > 2**63 - 1 or isinstance(value, float) and value != result:
        raise ValueError("invalid token count")
    return result


def claude_tokens(usage: dict[str, Any]) -> int:
    # Claude reports cache reads/writes separately from ordinary input. Nested
    # cache_creation and output details are breakdowns, not extra tokens.
    return sum(count(usage.get(key)) for key in (
        "input_tokens", "output_tokens", "cache_creation_input_tokens", "cache_read_input_tokens"))


def codex_tokens(usage: dict[str, Any]) -> int:
    # Cached input/reasoning output are subsets of input/output in Codex.
    if usage.get("total_tokens") is not None:
        return count(usage["total_tokens"])
    return count(usage.get("input_tokens")) + count(usage.get("output_tokens"))


def opencode_tokens(usage: Any) -> int:
    if not isinstance(usage, dict):
        return 0
    if usage.get("total") is not None:
        return count(usage["total"])
    # OpenCode's fallback components are disjoint, unlike Codex's subtotals.
    cache = usage.get("cache")
    cache = cache if isinstance(cache, dict) else {}
    return sum(count(value) for value in (usage.get("input"), usage.get("output"),
               usage.get("reasoning"), cache.get("read"), cache.get("write")))


def parse_codex(path: pathlib.Path, parse_timestamp) -> dict[str, list[int]]:
    """Deduplicated usage observations, not a sum of cumulative thread counters.

    The first counter is a baseline when last-call usage is absent. This avoids
    assigning an old thread's entire lifetime to a recent resume. Copied history
    shares the same timestamp/counter fingerprint across forks and archives.
    """
    records: dict[str, list[int]] = {}
    previous: int | None = None
    try:
        with path.open(encoding="utf-8", errors="replace") as handle:
            for line in handle:
                if '"token_count"' not in line:
                    continue
                try:
                    record = json.loads(line)
                    if not isinstance(record, dict) or record.get("type") != "event_msg":
                        continue
                    payload = record.get("payload")
                    if not isinstance(payload, dict) or payload.get("type") != "token_count":
                        continue
                    info = payload.get("info")
                    if not isinstance(info, dict) or not isinstance(info.get("total_token_usage"), dict):
                        continue
                    total = codex_tokens(info["total_token_usage"])
                    created = parse_timestamp(record.get("timestamp"))
                    if created is None:
                        continue
                    if total == previous:
                        continue  # rate-limit/status events repeat the same last-call usage
                    last = info.get("last_token_usage")
                    tokens = codex_tokens(last) if isinstance(last, dict) else (
                        total - previous if previous is not None and total > previous else 0)
                    previous = total
                    if tokens == 0:
                        continue
                    identity = json.dumps([record["timestamp"], info["total_token_usage"], last], sort_keys=True)
                    key = hashlib.sha256(identity.encode()).hexdigest()
                    records[key] = [created, tokens]
                except (TypeError, ValueError, OverflowError):
                    continue
    except OSError:
        pass
    return records


def read_codex(home: pathlib.Path, now_ms: int, parse_timestamp) -> list[tuple[int, int, float]]:
    cached = codexbar_cache.load("codex-transcripts-v1").get("files")
    cached = cached if isinstance(cached, dict) else {}
    kept: dict[str, Any] = {}
    oldest = (now_ms - 30 * 86400 * 1000) / 1000
    # Limit disk traversal to the existing local session stores. No auth files are used.
    for directory in (home / ".codex/sessions", home / ".codex/archived_sessions"):
        for path in directory.glob("**/*.jsonl"):
            if len(kept) >= 4000:
                break
            try:
                stat = path.stat()
            except OSError:
                continue
            if stat.st_mtime < oldest:
                continue
            known = cached.get(str(path))
            if (isinstance(known, dict) and isinstance(known.get("records"), dict)
                    and known.get("size") == stat.st_size and known.get("mtime") == stat.st_mtime_ns):
                kept[str(path)] = known
            else:
                records = parse_codex(path, parse_timestamp)
                kept[str(path)] = {"size": stat.st_size, "mtime": stat.st_mtime_ns,
                                  "records": {k: v for k, v in records.items() if v[0] >= oldest * 1000}}
    if kept != cached:
        codexbar_cache.store("codex-transcripts-v1", {"files": kept})
    records: dict[str, list[int]] = {}
    for entry in kept.values():
        for key, value in entry["records"].items():
            if (isinstance(value, list) and len(value) == 2 and all(type(x) is int and x >= 0 for x in value)):
                records[key] = value
    return [(created, tokens, 0.0) for created, tokens in records.values()]
