#!/usr/bin/env python3
"""Read OpenCode v2 usage/accounts; activate saved accounts through its official CLI."""

from __future__ import annotations

import datetime as dt
import json
import os
import pathlib
import sqlite3
import shutil
import subprocess
import urllib.request
import urllib.error
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
    """Prefer the v2 credential selection; legacy account_state does not follow auth switch."""
    if not database.is_file():
        return ""
    try:
        with closing(sqlite3.connect(database.as_uri() + "?mode=ro", uri=True, timeout=0.5)) as db:
            try:
                rows = db.execute("SELECT value FROM credential WHERE integration_id='opencode' AND active=1 "
                                  "ORDER BY time_updated DESC").fetchall()
            except sqlite3.Error:
                rows = []
            for (value,) in rows:
                try:
                    credential = json.loads(value)
                    metadata = credential.get("metadata") if isinstance(credential, dict) else None
                    email = metadata.get("email") if isinstance(metadata, dict) else None
                    if isinstance(email, str) and email:
                        return email
                except ValueError:
                    continue
            row = db.execute("""SELECT account.email FROM account
                LEFT JOIN account_state ON account_state.active_account_id = account.id
                ORDER BY (account_state.id IS NOT NULL) DESC, account.time_updated DESC LIMIT 1""").fetchone()
            return row[0] if row and isinstance(row[0], str) else ""
    except (sqlite3.Error, OSError):
        return ""


def opencode_cli() -> str | None:
    local = pathlib.Path.home() / ".opencode/bin/opencode"
    return str(local) if local.is_file() and os.access(local, os.X_OK) else shutil.which("opencode")


def switch_account(database: pathlib.Path, target: str, cli: str | None = None) -> dict[str, Any]:
    """Activate with OpenCode's own service/CLI, then verify its selection read-only."""
    if not target or target.startswith("-"):
        return {"ok": False, "message": "Choose a saved OpenCode account."}
    try:
        with closing(sqlite3.connect(database.as_uri() + "?mode=ro", uri=True, timeout=1)) as db:
            row = db.execute("SELECT integration_id, active, value FROM credential WHERE id=?", (target,)).fetchone()
            selected = db.execute("SELECT id FROM credential WHERE integration_id='opencode' AND active=1").fetchall()
        if not row or row[0] != "opencode":
            return {"ok": False, "message": "That OpenCode account is no longer saved. Refresh the account list."}
        credential = json.loads(row[2])
        metadata = credential.get("metadata") if isinstance(credential, dict) else None
        email = metadata.get("email") if isinstance(metadata, dict) else None
        if not isinstance(credential, dict) or credential.get("type") != "oauth" or not isinstance(email, str) or not email:
            return {"ok": False, "message": "Choose a saved OpenCode browser account."}
        if row[1] and selected == [(target,)]:
            return {"ok": True, "message": "This OpenCode account is already active."}
        expires = credential.get("expires")
        fresh = not isinstance(expires, bool) and isinstance(expires, (int, float)) and expires > (time.time() + 60) * 1000
        refreshable = isinstance(credential.get("refresh"), str) and bool(credential["refresh"])
        if not isinstance(credential.get("access"), str) or not credential["access"] or not (fresh or refreshable):
            return {"ok": False, "message": "Sign in to this account again in OpenCode, then try switching."}
        cli = cli or opencode_cli()
        if not cli:
            return {"ok": False, "message": "OpenCode's command line was not found. Install OpenCode, then try again."}
        result = subprocess.run([cli, "auth", "switch", "opencode", target], stdin=subprocess.DEVNULL,
                                capture_output=True, text=True, timeout=45, check=False,
                                cwd=pathlib.Path.home(), env={**os.environ, "NO_COLOR": "1"})
        if result.returncode:
            return {"ok": False, "message": "OpenCode couldn't switch accounts. Open OpenCode and try again."}
        with closing(sqlite3.connect(database.as_uri() + "?mode=ro", uri=True, timeout=1)) as db:
            active = db.execute("SELECT id FROM credential WHERE integration_id='opencode' AND active=1").fetchall()
        if active != [(target,)]:
            return {"ok": False, "message": "OpenCode did not select the requested account. Refresh and try again."}
        return {"ok": True, "message": f"OpenCode now uses {email}. CodexBar is refreshing its usage."}
    except subprocess.TimeoutExpired:
        return {"ok": False, "message": "The OpenCode switch did not finish in time. Check OpenCode and try again."}
    except (OSError, ValueError, TypeError, sqlite3.Error, subprocess.SubprocessError):
        return {"ok": False, "message": "The OpenCode account could not be switched. Refresh and try again."}


def iso_time(timestamp_ms: int) -> str:
    return dt.datetime.fromtimestamp(timestamp_ms / 1000, dt.timezone.utc).isoformat().replace("+00:00", "Z")


class NoPlanRedirect(urllib.request.HTTPRedirectHandler):
    """Never forward an account credential through an HTTP redirect."""

    def redirect_request(self, req: Any, fp: Any, code: int, msg: str, headers: Any, newurl: str) -> None:
        return None


def plan_from_status(data: Any, now_ms: int) -> str:
    """Current Go product, not the renewal product or a tier inferred from usage limits."""
    if not isinstance(data, dict) or not isinstance(data.get("access"), dict):
        return ""
    try:
        ends_at = dt.datetime.fromisoformat(data["access"]["endsAt"].replace("Z", "+00:00"))
        if ends_at.tzinfo is None or ends_at.timestamp() * 1000 <= now_ms:
            return ""
    except (KeyError, TypeError, AttributeError, ValueError, OverflowError):
        return ""
    product = data.get("product")
    if not isinstance(product, str):
        return ""
    product = product.strip().lower().replace("_", "-").replace(" ", "-")
    return {"go": "Go", "go-plus": "Go Plus", "goplus": "Go Plus"}.get(product, "")


def fetch_account_plan(credential: dict[str, Any], now_ms: int) -> str | None:
    """Read the official Console's workspace-scoped subscription; None means unavailable."""
    metadata = credential.get("metadata")
    if not isinstance(metadata, dict):
        return None
    server = metadata.get("server", "https://opencode.ai/console")
    org = metadata.get("orgID")
    access = credential.get("access")
    if not isinstance(server, str) or server.rstrip("/") != "https://opencode.ai/console" \
            or not isinstance(org, str) or not org or len(org) > 512 or "\n" in org or "\r" in org \
            or not isinstance(access, str) or not access:
        return None
    request = urllib.request.Request("https://opencode.ai/console/api/go/status", headers={
        "Authorization": "Bearer " + access, "x-org-id": org,
        "Accept": "application/json", "User-Agent": "CodexBar",
    })
    try:
        with urllib.request.build_opener(NoPlanRedirect()).open(request, timeout=8) as response:
            payload = response.read(131073)
        if len(payload) > 131072:
            return None
        data = json.loads(payload)
        if data is not None and not isinstance(data, dict):
            return None
        return plan_from_status(data, now_ms)
    except urllib.error.HTTPError as error:
        error.close()
        return None
    except (OSError, ValueError, urllib.error.URLError):
        return None


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
            workspace = metadata.get("orgName")
            account = {"id": ident, "email": email, "active": bool(active), "windows": [],
                       "plan": plan if isinstance(plan, str) else "", "switchable": True,
                       "workspace": workspace if isinstance(workspace, str) else ""}
            report.append(account)
            access, expires = credential.get("access"), credential.get("expires")
            if not isinstance(access, str) or not access or isinstance(expires, bool) \
                    or not isinstance(expires, (int, float)) or expires <= now_ms + 60000:
                account["switchable"] = bool(isinstance(access, str) and access and
                    isinstance(credential.get("refresh"), str) and credential["refresh"])
                if not active:
                    account["error"] = "Select this account to refresh its sign-in in OpenCode." if account["switchable"] else \
                        "Sign in to this OpenCode account again to read quota."
                continue
            current_plan = fetch_account_plan(credential, now_ms)
            if current_plan is not None:
                account["plan"] = current_plan
                account["planSource"] = "console"
            if active:
                continue  # upstream's normal snapshot already supplies this account's quota
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
    if len(sys.argv) > 1 and sys.argv[1] == "switch":
        result = switch_account(database, sys.argv[2]) if len(sys.argv) == 3 else {
            "ok": False, "message": "Choose a saved OpenCode account."}
        print(json.dumps(result))
        return 0 if result["ok"] else 1
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
