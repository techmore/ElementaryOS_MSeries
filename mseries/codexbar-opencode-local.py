#!/usr/bin/env python3
"""Read OpenCode Go local usage from the v2 SQLite database, without modifying it."""

from __future__ import annotations

import datetime as dt
import json
import os
import pathlib
import sqlite3
import sys
import time
from typing import Any


def data_directory() -> pathlib.Path:
    configured = os.environ.get("XDG_DATA_HOME")
    base = pathlib.Path(configured) if configured and pathlib.Path(configured).is_absolute() else pathlib.Path.home() / ".local/share"
    return base / "opencode"


def read_usage(database: pathlib.Path, now_ms: int | None = None) -> dict[str, Any]:
    now_ms = int(time.time() * 1000) if now_ms is None else now_ms
    if not database.is_file():
        return {"status": "unavailable", "message": "OpenCode v2 usage database was not found."}

    try:
        connection = sqlite3.connect(f"file:{database}?mode=ro", uri=True, timeout=0.5)
        connection.row_factory = sqlite3.Row
        try:
            columns = {row[1] for row in connection.execute("PRAGMA table_info(session_message)")}
            if not {"type", "time_created", "data"}.issubset(columns):
                return {"status": "unavailable", "message": "OpenCode usage database has an unsupported schema."}
            rows = connection.execute(
                """SELECT time_created, data
                   FROM session_message
                   WHERE type = 'assistant'
                     AND json_valid(data)
                     AND json_extract(data, '$.model.providerID') = 'opencode-go'
                     AND json_type(data, '$.cost') IN ('integer', 'real')"""
            ).fetchall()
        finally:
            connection.close()
    except (sqlite3.Error, OSError) as error:
        return {"status": "unavailable", "message": f"Could not read OpenCode local history: {error}"}

    records: list[tuple[int, float, int]] = []
    for row in rows:
        try:
            data = json.loads(row["data"])
            cost = float(data["cost"])
            created_ms = int(row["time_created"])
            tokens = data.get("tokens")
            total_tokens = 0
            if isinstance(tokens, dict):
                if tokens.get("total") is not None:
                    total_tokens = int(tokens["total"])
                else:
                    cache = tokens.get("cache")
                    components = [tokens.get("input"), tokens.get("output"), tokens.get("reasoning")]
                    components.extend([
                        cache.get("read") if isinstance(cache, dict) else None,
                        cache.get("write") if isinstance(cache, dict) else None,
                    ])
                    if all(value is not None for value in components):
                        total_tokens = sum(int(value) for value in components)
            if created_ms > 0 and cost >= 0 and cost < float("inf") and total_tokens >= 0:
                records.append((created_ms, cost, total_tokens))
        except (TypeError, ValueError, KeyError, json.JSONDecodeError):
            continue

    if not records:
        return {
            "status": "empty",
            "message": "No cost-bearing OpenCode Go assistant records yet.",
            "updatedAt": iso_time(now_ms),
            "periods": [],
        }

    periods = []
    for label, duration_ms in (("5 hours", 5 * 60 * 60 * 1000), ("7 days", 7 * 24 * 60 * 60 * 1000), ("30 days", 30 * 24 * 60 * 60 * 1000)):
        matching = [(cost, tokens) for created, cost, tokens in records if now_ms - duration_ms <= created <= now_ms]
        periods.append({
            "label": label,
            "costUSD": round(sum(cost for cost, _ in matching), 6),
            "requests": len(matching),
            "tokens": sum(tokens for _, tokens in matching),
        })

    return {
        "status": "available",
        "message": "Local usage estimate · not account quota",
        "updatedAt": iso_time(now_ms),
        "periods": periods,
    }


def iso_time(timestamp_ms: int) -> str:
    return dt.datetime.fromtimestamp(timestamp_ms / 1000, dt.timezone.utc).isoformat().replace("+00:00", "Z")


def main() -> int:
    usage = read_usage(data_directory() / "opencode.db")
    print(json.dumps(usage, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
