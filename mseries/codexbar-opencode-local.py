#!/usr/bin/env python3
"""Read OpenCode Go local usage from the v2 SQLite database, without modifying it."""

from __future__ import annotations

import datetime as dt
import json
import os
import pathlib
import sqlite3
import subprocess
from contextlib import closing
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


def read_account(database: pathlib.Path) -> str:
    """The signed-in OpenCode account's email, read-only; never the tokens stored beside it."""
    if not database.is_file():
        return ""
    try:
        connection = sqlite3.connect(f"file:{database}?mode=ro", uri=True, timeout=0.5)
        try:
            row = connection.execute(
                """SELECT account.email FROM account
                   LEFT JOIN account_state ON account_state.active_account_id = account.id
                   ORDER BY (account_state.id IS NOT NULL) DESC, account.time_updated DESC LIMIT 1"""
            ).fetchone()
        finally:
            connection.close()
    except (sqlite3.Error, OSError):
        return ""
    return row[0] if row and isinstance(row[0], str) else ""


def iso_time(timestamp_ms: int) -> str:
    return dt.datetime.fromtimestamp(timestamp_ms / 1000, dt.timezone.utc).isoformat().replace("+00:00", "Z")


def saved_accounts(database: pathlib.Path, cli: str, now_ms: int | None = None) -> list[dict[str, Any]]:
    """Quota for saved distinct OAuth accounts, without activating one or exporting its credentials."""
    now_ms = int(time.time() * 1000) if now_ms is None else now_ms
    try:
        with closing(sqlite3.connect(database.as_uri() + "?mode=ro", uri=True, timeout=0.5)) as db:
            rows = db.execute("SELECT id, active, value FROM credential WHERE integration_id='opencode' "
                              "ORDER BY active DESC, time_updated DESC").fetchall()
    except (sqlite3.Error, OSError):
        return []
    report, seen = [], set()
    for ident, active, value in rows:
        try:
            credential = json.loads(value)
            if not isinstance(credential, dict) or credential.get("type") != "oauth":
                continue
            metadata = credential.get("metadata")
            if not isinstance(metadata, dict):
                continue
            email = metadata.get("email")
            if not isinstance(email, str) or not email:
                continue
            key = (metadata.get("accountID") or email.lower(), metadata.get("orgID") or "")
            if key in seen:
                continue
            seen.add(key)
            plan = metadata.get("plan")
            account = {"id": ident, "email": email, "active": bool(active), "windows": [],
                       "plan": plan if isinstance(plan, str) else ""}
            report.append(account)
            if active:
                continue  # upstream's normal snapshot already supplies this account's quota
            access, expires = credential.get("access"), credential.get("expires")
            if not isinstance(access, str) or not access or isinstance(expires, bool) \
                    or not isinstance(expires, (int, float)) or expires <= now_ms + 60000:
                account["error"] = "Sign in to this OpenCode account again to read quota."
                continue
            result = subprocess.run([cli, "usage", "--provider", "opencodego", "--source", "api", "--format", "json"],
                                    env={**os.environ, "OPENCODE_API_KEY": access}, capture_output=True,
                                    text=True, timeout=20, check=False)
            data = json.loads(result.stdout)
            row = data[0] if isinstance(data, list) and data else {}
            usage = row.get("usage") or {}
            if result.returncode or row.get("error") or not isinstance(usage, dict):
                account["error"] = "Quota unavailable for this saved account."
                continue
            for field, label, minutes in (("primary", "5 hour", 300), ("secondary", "7 day", 10080),
                                           ("tertiary", "30 day", 43200)):
                window = usage.get(field)
                if isinstance(window, dict) and isinstance(window.get("usedPercent"), (int, float)):
                    account["windows"].append({"key": field, "label": label, "minutes": minutes,
                        "remaining": max(0, min(100, 100 - window["usedPercent"])), "resetsAt": window.get("resetsAt", "")})
        except (ValueError, TypeError, OSError, subprocess.SubprocessError):
            if report and report[-1].get("id") == ident:
                report[-1]["error"] = "Quota unavailable for this saved account."
    return report


def main() -> int:
    database = data_directory() / "opencode.db"
    if sys.argv[1:] == ["accounts"]:
        cli = str(pathlib.Path.home() / ".local/lib/codexbar-cli/codexbar-upstream")
        print(json.dumps({"accounts": saved_accounts(database, cli)}))
        return 0
    usage = read_usage(database)
    email = read_account(database)
    if email:
        usage["accountEmail"] = email
    print(json.dumps(usage, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
