#!/usr/bin/env python3
"""Read OpenCode v2 usage/accounts; activate saved accounts through its official CLI."""

from __future__ import annotations

import hashlib
import math
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

import codexbar_cache
import codexbar_history


def data_directory() -> pathlib.Path:
    configured = os.environ.get("XDG_DATA_HOME")
    base = pathlib.Path(configured) if configured and pathlib.Path(configured).is_absolute() else pathlib.Path.home() / ".local/share"
    return base / "opencode"


def read_usage(database: pathlib.Path, now_ms: int | None = None) -> dict[str, Any]:
    now_ms = int(time.time() * 1000) if now_ms is None else now_ms
    if not database.is_file():
        return {"status": "unavailable", "message": "OpenCode v2 usage database was not found."}

    try:
        periods, providers = codexbar_history.opencode_summary(
            database, now_ms, provider="opencode-go", cost_only=True)
    except (sqlite3.Error, OSError) as error:
        return {"status": "unavailable", "message": f"Could not read OpenCode local history: {error}"}

    if not providers:
        return {
            "status": "empty",
            "message": "No cost-bearing OpenCode Go records in the last 30 days.",
            "updatedAt": iso_time(now_ms),
            "periods": [],
        }

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


PLAN_TTL = 3600
QUOTA_TTL = 300


def valid_cached_value(value: Any, kind: str) -> bool:
    if kind == "plan":
        return isinstance(value, str) and value in ("", "Go", "Go Plus")
    return isinstance(value, list) and 0 < len(value) <= 3 and all(
        isinstance(window, dict) and window.get("key") in ("primary", "secondary", "tertiary")
        and isinstance(window.get("label"), str) and type(window.get("minutes")) is int
        and type(window.get("remaining")) in (int, float) and math.isfinite(window["remaining"])
        and 0 <= window["remaining"] <= 100 and isinstance(window.get("resetsAt"), str)
        for window in value)


def account_cache_entry(name: str, kind: str) -> dict[str, Any]:
    raw = codexbar_cache.load(name).get("entry", {})
    if not isinstance(raw, dict):
        return {}
    entry = {k: v for k, v in raw.items() if
             k in ("fetchedAt", "retryAt") and type(v) in (int, float) and math.isfinite(v) or
             k == "failures" and type(v) is int and v >= 0}
    value = raw.get("data")
    if valid_cached_value(value, kind):
        entry["data"] = value if kind == "plan" else [
            {key: window[key] for key in ("key", "label", "minutes", "remaining", "resetsAt")}
            for window in value]
    return entry


def cached_account_value(scope: str, kind: str, now: float, force: bool, fetch):
    """Only allowlisted plan/quota data is persisted, never provider replies or secrets."""
    name = "opencode-" + kind + "-" + scope
    entry = account_cache_entry(name, kind)
    try:
        with codexbar_cache.locked(codexbar_cache.cache_dir() / (name + ".json"), timeout=1):
            # A concurrent helper may have populated the same endpoint while we waited.
            entry = account_cache_entry(name, kind)
            ttl = PLAN_TTL if kind == "plan" else QUOTA_TTL
            crossed_reset = False
            if kind == "quota" and isinstance(entry.get("data"), list):
                for window in entry["data"]:
                    try:
                        reset = dt.datetime.fromisoformat(window["resetsAt"].replace("Z", "+00:00")).timestamp()
                        crossed_reset |= entry.get("fetchedAt", now) < reset <= now
                    except (ValueError, OverflowError, OSError):
                        pass
            if not force and (codexbar_cache.in_backoff(entry, now) or
                              not crossed_reset and codexbar_cache.is_fresh(entry, ttl, now)):
                return entry.get("data"), bool(entry.get("failures"))
            try:
                value = fetch()
                if not valid_cached_value(value, kind):
                    raise ValueError("Invalid account answer")
                if kind == "quota":
                    value = [{key: window[key] for key in ("key", "label", "minutes", "remaining", "resetsAt")}
                             for window in value]
                entry = codexbar_cache.succeeded(value, now)
            except (ValueError, TypeError, OSError, subprocess.SubprocessError):
                entry = codexbar_cache.failed(entry, now)
            codexbar_cache.store(name, {"entry": entry})
            return entry.get("data"), bool(entry.get("failures"))
    except (TimeoutError, OSError):
        return entry.get("data"), True


def fetch_saved_quota(credential: dict[str, Any], cli: str) -> list[dict[str, Any]]:
    result = subprocess.run([cli, "usage", "--provider", "opencodego", "--source", "api", "--format", "json"],
                            env={**os.environ, "OPENCODE_API_KEY": credential["access"]}, capture_output=True,
                            text=True, timeout=20, check=False)
    data = json.loads(result.stdout)
    row = data[0] if isinstance(data, list) and data and isinstance(data[0], dict) else {}
    usage = row.get("usage")
    if result.returncode or row.get("error") or not isinstance(usage, dict):
        raise ValueError("Quota unavailable")
    windows = []
    for field, label, minutes in (("primary", "5 hour", 300), ("secondary", "7 day", 10080),
                                   ("tertiary", "30 day", 43200)):
        window = usage.get(field)
        if isinstance(window, dict) and type(window.get("usedPercent")) in (int, float) and math.isfinite(window["usedPercent"]):
            windows.append({"key": field, "label": label, "minutes": minutes,
                "remaining": max(0, min(100, 100 - window["usedPercent"])),
                "resetsAt": window.get("resetsAt") if isinstance(window.get("resetsAt"), str) else ""})
    return windows


def saved_accounts(database: pathlib.Path, cli: str, now_ms: int | None = None, *, force: bool = False) -> list[dict[str, Any]]:
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
                    or not isinstance(expires, (int, float)) or not math.isfinite(expires) or expires <= now_ms + 60000:
                account["switchable"] = bool(isinstance(access, str) and access and
                    isinstance(credential.get("refresh"), str) and credential["refresh"])
                if not active:
                    account["error"] = "Select this account to refresh its sign-in in OpenCode." if account["switchable"] else \
                        "Sign in to this OpenCode account again to read quota."
                continue
            # An opaque scope fingerprint invalidates results on sign-in/identity changes.
            # Neither its preimage nor credentials are written to the cache.
            scope = hashlib.sha256(json.dumps([str(database.resolve()), ident, email.lower(),
                metadata.get("accountID"), metadata.get("orgID"), metadata.get("server"), access, expires],
                sort_keys=True).encode()).hexdigest()
            current_plan, plan_stale = cached_account_value(scope, "plan", now_ms / 1000, force,
                lambda: fetch_account_plan(credential, now_ms))
            if current_plan is not None:
                account["plan"] = current_plan
                account["planSource"] = "console"
                if plan_stale: account["planStale"] = True
            if active:
                continue  # Active account quota is owned by upstream's snapshot, never this cache.
            windows, stale = cached_account_value(scope, "quota", now_ms / 1000, force,
                lambda: fetch_saved_quota(credential, cli))
            account["windows"] = windows if windows is not None else []
            if stale or windows is None:
                account["stale"] = True
                account["error"] = "Quota unavailable for this saved account." + (
                    " Showing cached usage." if windows else "")
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
    if sys.argv[1:] in (["accounts"], ["accounts", "--force"]):
        cli = str(pathlib.Path.home() / ".local/lib/codexbar-cli/codexbar-upstream")
        print(json.dumps({"accounts": saved_accounts(database, cli, force="--force" in sys.argv[2:])}))
        return 0
    usage = read_usage(database)
    email = read_account(database)
    if email:
        usage["accountEmail"] = email
    print(json.dumps(usage, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
