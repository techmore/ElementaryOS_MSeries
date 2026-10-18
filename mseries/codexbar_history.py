"""Read-only, window-bounded OpenCode usage. Shared by the panel's local readers."""
from __future__ import annotations

import json
import math
import pathlib
import sqlite3
from collections.abc import Iterator

import codexbar_tokens

WINDOWS = (("5 hours", 5 * 3600 * 1000), ("7 days", 7 * 24 * 3600 * 1000),
           ("30 days", 30 * 24 * 3600 * 1000))
HISTORY_MS = WINDOWS[-1][1]


def opencode_records(database: pathlib.Path, now_ms: int, *, provider: str | None = None,
                     cost_only: bool = False) -> Iterator[tuple[int, int, float, str]]:
    """Stream recent usage metadata, never auth/message bodies into a cache.

    Apply time bounds before JSON decoding and avoid fetchall's second copy of
    the history. Use existing indexes if available; never change the app's DB.
    """
    connection = sqlite3.connect(database.resolve().as_uri() + "?mode=ro", uri=True, timeout=0.5)
    try:
        columns = {row[1] for row in connection.execute("PRAGMA table_info(session_message)")}
        if not {"type", "time_created", "data"}.issubset(columns):
            raise sqlite3.OperationalError("OpenCode history uses an unsupported schema")
        query = ("SELECT time_created, data FROM session_message WHERE type = 'assistant' "
                 "AND time_created BETWEEN ? AND ? AND json_valid(data)")
        parameters: list[int | str] = [now_ms - HISTORY_MS, now_ms]
        if provider is not None:
            query += " AND json_extract(data, '$.model.providerID') = ?"
            parameters.append(provider)
        if cost_only:
            query += " AND json_type(data, '$.cost') IN ('integer', 'real')"
        for created, raw in connection.execute(query, parameters):
            try:
                payload = json.loads(raw)
                if not isinstance(payload, dict):
                    continue
                tokens = codexbar_tokens.opencode_tokens(payload.get("tokens"))
                cost = payload.get("cost")
                valid_cost = type(cost) in (int, float) and math.isfinite(cost) and cost >= 0
                if cost_only and not valid_cost:
                    continue
                model = payload.get("model")
                provider_id = str(model.get("providerID") or "unknown") if isinstance(model, dict) else "unknown"
                yield int(created), tokens, float(cost) if valid_cost else 0.0, provider_id
            except (TypeError, ValueError, OverflowError):
                continue
    finally:
        connection.close()


def opencode_summary(database: pathlib.Path, now_ms: int, *, provider: str | None = None,
                     cost_only: bool = False) -> tuple[list[dict], dict[str, int]]:
    """Aggregate a stream without retaining messages (memory scales with providers)."""
    periods = [{"label": label, "requests": 0, "tokens": 0, "costUSD": 0.0} for label, _ in WINDOWS]
    providers: dict[str, int] = {}
    for created, tokens, cost, provider_id in opencode_records(database, now_ms, provider=provider, cost_only=cost_only):
        providers[provider_id] = providers.get(provider_id, 0) + 1
        age = now_ms - created
        for period, (_, duration) in zip(periods, WINDOWS):
            if 0 <= age <= duration:
                period["requests"] += 1
                period["tokens"] += tokens
                period["costUSD"] += cost
    for period in periods:
        period["costUSD"] = round(period["costUSD"], 6)
    return periods, providers
