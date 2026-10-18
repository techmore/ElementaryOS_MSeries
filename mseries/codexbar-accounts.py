#!/usr/bin/env python3
"""Codex account switching for the M-series CodexBar port.

Upstream CodexBar's managed Codex accounts are macOS-only, so on Linux we keep
one saved Codex home per account and swap ~/.codex/auth.json atomically.

  codexbar-accounts.py list [--json]      accounts (no tokens), active one marked
  codexbar-accounts.py save               remember the signed-in account
  codexbar-accounts.py switch <email|id>  make a saved account the active one
  codexbar-accounts.py usage [--force]    list plus each saved account's quota (cached 15 min; --force refetches)
  codexbar-accounts.py app-running        exit 0 when the ChatGPT desktop app is open
  codexbar-accounts.py restart-app        close and reopen the ChatGPT desktop app

Running Codex sessions keep the account they started with; restart them.
"""

from __future__ import annotations

import base64
import json
import os
import pathlib
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any

import codexbar_cache


def codex_home() -> pathlib.Path:
    configured = os.environ.get("CODEX_HOME")
    return pathlib.Path(configured) if configured else pathlib.Path.home() / ".codex"


def store_dir() -> pathlib.Path:
    configured = os.environ.get("XDG_DATA_HOME")
    base = pathlib.Path(configured) if configured and pathlib.Path(configured).is_absolute() else pathlib.Path.home() / ".local/share"
    return base / "codexbar-mseries" / "codex-accounts"


def read_auth(path: pathlib.Path) -> dict[str, Any] | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def claims(auth: dict[str, Any]) -> dict[str, Any]:
    tokens = auth.get("tokens")
    token = tokens.get("id_token") if isinstance(tokens, dict) else None
    if not isinstance(token, str) or token.count(".") != 2:
        return {}
    payload = token.split(".")[1]
    try:
        decoded = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
    except (ValueError, UnicodeError):
        return {}
    return decoded if isinstance(decoded, dict) else {}


def identity(auth: dict[str, Any]) -> dict[str, str] | None:
    """Email, plan and a stable id, or None for API-key logins and unreadable files."""
    if auth.get("auth_mode") not in (None, "chatgpt"):
        return None
    tokens = auth.get("tokens")
    if not isinstance(tokens, dict):
        return None
    token_claims = claims(auth)
    namespace = token_claims.get("https://api.openai.com/auth")
    namespace = namespace if isinstance(namespace, dict) else {}
    email = token_claims.get("email")
    account_id = tokens.get("account_id") or namespace.get("chatgpt_account_id")
    if not isinstance(email, str) or not email:
        return None
    ident = account_id if isinstance(account_id, str) and account_id else email
    plan = namespace.get("chatgpt_plan_type")
    return {"email": email, "plan": plan if isinstance(plan, str) else "", "id": f"{email}|{ident}"}


def slug(account_id: str) -> str:
    return base64.urlsafe_b64encode(account_id.encode()).decode().rstrip("=")


def write_private(path: pathlib.Path, auth: dict[str, Any]) -> None:
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(dir=path.parent, prefix=".auth-")
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(auth, handle, indent=2)
        os.chmod(temporary, 0o600)
        os.replace(temporary, path)
    except BaseException:
        pathlib.Path(temporary).unlink(missing_ok=True)
        raise


def saved_homes() -> dict[str, pathlib.Path]:
    homes: dict[str, pathlib.Path] = {}
    root = store_dir()
    if root.is_dir():
        for entry in sorted(root.iterdir()):
            auth = read_auth(entry / "auth.json")
            ident = identity(auth) if auth else None
            if ident:
                homes[ident["id"]] = entry
    return homes


def state_lock() -> Any:
    """Serialises every write to the saved sign-ins and to the live auth.json."""
    return codexbar_cache.locked(store_dir().parent / "codex-accounts.state")


def _save_current() -> dict[str, str] | None:
    auth = read_auth(codex_home() / "auth.json")
    ident = identity(auth) if auth else None
    if not auth or not ident:
        return None
    for directory in (store_dir().parent, store_dir()):
        codexbar_cache.private_dir(directory)
    write_private(store_dir() / slug(ident["id"]) / "auth.json", auth)
    return ident


def save_current() -> dict[str, str] | None:
    with state_lock():
        return _save_current()


def list_accounts() -> list[dict[str, Any]]:
    current_auth = read_auth(codex_home() / "auth.json")
    current = identity(current_auth) if current_auth else None
    accounts: dict[str, dict[str, Any]] = {}
    for account_id, home in saved_homes().items():
        ident = identity(read_auth(home / "auth.json") or {})
        if ident:
            accounts[account_id] = {**ident, "active": False}
    if current:
        accounts[current["id"]] = {**current, "active": True}
    return sorted(accounts.values(), key=lambda a: (not a["active"], a["email"].lower()))


def switch(target: str) -> tuple[bool, str]:
    matches = [a for a in list_accounts() if target in (a["email"], a["id"])]
    if not matches:
        return False, f"No saved Codex account matches {target}."
    if len(matches) > 1:
        return False, f"{target} matches several accounts; use the exact id."
    wanted = matches[0]
    if wanted["active"]:
        return True, f"{wanted['email']} is already the active Codex account."
    try:
        with state_lock():
            homes = saved_homes()
            if wanted["id"] not in homes:
                return False, f"{wanted['email']} has no saved sign-in."
            saved = read_auth(homes[wanted["id"]] / "auth.json")
            if not saved:
                return False, f"{wanted['email']}'s saved sign-in could not be read."
            _save_current()  # never lose the account we are leaving
            write_private(codex_home() / "auth.json", saved)
    except TimeoutError:
        return False, "Another CodexBar action is changing the Codex sign-in. Try again in a moment."
    return True, f"Switched Codex to {wanted['email']}. Restart running Codex sessions to use it."


APP_BINARY = "/usr/lib/chatgpt/ChatGPT"


def app_pids() -> list[int]:
    """Main process of the ChatGPT desktop app (children carry --type=)."""
    pids = []
    for entry in pathlib.Path("/proc").iterdir():
        if not entry.name.isdigit():
            continue
        try:
            argv = (entry / "cmdline").read_bytes().split(b"\0")
        except OSError:
            continue
        if argv and argv[0].decode(errors="replace") == APP_BINARY and not any(a.startswith(b"--type=") for a in argv):
            pids.append(int(entry.name))
    return pids


def restart_app() -> tuple[bool, str]:
    """The desktop app keeps the account it started with, so a switch needs a relaunch."""
    pids = app_pids()
    for pid in pids:
        try:
            os.kill(pid, signal.SIGTERM)
        except OSError:
            pass
    deadline = time.monotonic() + 10
    while app_pids() and time.monotonic() < deadline:
        time.sleep(0.2)
    if app_pids():
        return False, "ChatGPT did not close; quit it and open it again."
    subprocess.Popen(["chatgpt"], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                     stderr=subprocess.DEVNULL, start_new_session=True)
    return True, "ChatGPT restarted." if pids else "ChatGPT opened."


def usage_for(home: pathlib.Path, cli: str) -> dict[str, Any]:
    environment = {**os.environ, "CODEX_HOME": str(home)}
    try:
        result = subprocess.run([cli, "usage", "--provider", "codex", "--format", "json"], capture_output=True,
                                text=True, timeout=45, env=environment, check=False)
        rows = json.loads(result.stdout)
        row = rows[0] if isinstance(rows, list) and rows else {}
    except (OSError, subprocess.SubprocessError, json.JSONDecodeError):
        return {"error": "Usage could not be read."}
    if row.get("error"):
        return {"error": str(row["error"].get("message", "Usage unavailable."))}
    windows = []
    usage = row.get("usage") or {}
    for key, label in (("primary", "5 hours"), ("secondary", "7 day")):
        window = usage.get(key)
        if isinstance(window, dict) and window.get("usedPercent") is not None:
            windows.append({"key": key, "label": label, "remaining": max(0.0, 100.0 - float(window["usedPercent"])),
                            "resetsAt": window.get("resetsAt", "")})
    return {"windows": windows, "resetCredits": reset_credits(row)}


def reset_credits(row: dict[str, Any]) -> dict[str, Any] | None:
    """Available rate-limit resets and when the first one expires, or None when the CLI does not report them."""
    summary = row.get("resetCredits")
    if not isinstance(summary, dict) or not isinstance(summary.get("available"), int):
        return None
    expires = summary.get("nextExpiresAt") if isinstance(summary.get("nextExpiresAt"), str) else ""
    if not expires:  # older summaries carry only the count; fall back to the credit list
        detail = (row.get("usage") or {}).get("codexResetCredits") or {}
        dates = [c.get("expiresAt") for c in detail.get("credits", []) if isinstance(c, dict) and isinstance(c.get("expiresAt"), str)]
        expires = min(dates) if dates else ""
    return {"available": summary["available"], "nextExpiresAt": expires}


USAGE_TTL_SECONDS = 900


def usage_report(cli: str, force: bool = False, now: float | None = None) -> list[dict[str, Any]]:
    """Per-account quota. The active account is skipped: CodexBar's own snapshot already carries it, and running
    the CLI against the live home could rewrite auth.json while a switch is replacing it. Saved accounts are served
    from the cache while fresh or backing off, and fetched in parallel otherwise."""
    now = time.time() if now is None else now
    homes = saved_homes()
    accounts = list_accounts()
    cache = codexbar_cache.load("codex-usage")
    identities = {a["id"]: {k: a[k] for k in ("email", "plan", "id", "active")} for a in accounts}
    details: dict[str, dict[str, Any]] = {}
    pending: list[str] = []
    for account in accounts:
        account_id = account["id"]
        entry = cache.get(account_id) if isinstance(cache.get(account_id), dict) else None
        if account["active"]:
            details[account_id] = {"source": "snapshot"}
        elif account_id not in homes:
            details[account_id] = {"error": "No saved sign-in."}
        elif not force and (codexbar_cache.is_fresh(entry, USAGE_TTL_SECONDS, now) or codexbar_cache.in_backoff(entry, now)):
            details[account_id] = cached_details(entry)
        else:
            pending.append(account_id)
    if pending:
        with ThreadPoolExecutor(max_workers=min(4, len(pending))) as pool:
            fetched = dict(zip(pending, pool.map(lambda account_id: usage_for(homes[account_id], cli), pending)))
        for account_id, result in fetched.items():
            previous = cache.get(account_id) if isinstance(cache.get(account_id), dict) else None
            if "error" in result:
                entry = codexbar_cache.failed(previous, now)
                entry["error"] = result["error"]
            else:
                entry = codexbar_cache.succeeded(result, now)
            cache[account_id] = entry
            details[account_id] = cached_details(entry)
    codexbar_cache.store("codex-usage", {k: v for k, v in cache.items() if k in identities})
    return [identities[a["id"]] | details[a["id"]] for a in accounts]


def cached_details(entry: dict[str, Any] | None) -> dict[str, Any]:
    """What the panel shows for a cached answer: the last good quota, flagged stale when the latest try failed."""
    entry = entry or {}
    data = entry.get("data")
    if not isinstance(data, dict):
        return {"error": str(entry.get("error") or "Usage unavailable.")}
    result = dict(data) | {"fetchedAt": entry.get("fetchedAt")}
    if entry.get("failures"):
        result["stale"] = True
        result["error"] = str(entry.get("error") or "Usage unavailable.")
    return result


def codex_cli() -> str | None:
    candidates = [shutil.which("codex"), "/usr/lib/chatgpt/resources/codex", "/opt/Codex/resources/codex"]
    return next((p for p in candidates if p and os.path.isfile(p) and os.access(p, os.X_OK)), None)


def login(cli: str | None) -> tuple[bool, str]:
    """Browser sign-in in an isolated Codex home; the live app's auth.json is never replaced."""
    if not cli:
        return False, "Codex was not found. Install or open the Codex app, then try again."
    save_current()
    root = store_dir().parent
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    previous_handler = signal.getsignal(signal.SIGTERM)
    def cancelled(*unused):
        raise InterruptedError()
    signal.signal(signal.SIGTERM, cancelled)
    try:
        with tempfile.TemporaryDirectory(prefix=".codex-login-", dir=root) as directory:
            environment = {k: v for k, v in os.environ.items()
                           if k not in {"OPENAI_API_KEY", "CODEX_API_KEY", "CODEX_ACCESS_TOKEN"}}
            environment["CODEX_HOME"] = directory
            process = subprocess.Popen([cli, "login", "-c", 'cli_auth_credentials_store="file"'],
                env=environment, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            try:
                code = process.wait(timeout=600)
            finally:
                if process.poll() is None:
                    process.terminate()
                    try:
                        process.wait(timeout=3)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait()
            if code:
                return False, "Sign-in did not finish. Close any previous Codex sign-in and try again."
            auth = read_auth(pathlib.Path(directory) / "auth.json")
            ident = identity(auth) if auth else None
            if not auth or not ident:
                return False, "No ChatGPT account was returned. Sign in with ChatGPT and try again."
            write_private(store_dir() / slug(ident["id"]) / "auth.json", auth)
            return True, f"Added {ident['email']}. Your current Codex account is unchanged; choose Switch when you're ready."
    except InterruptedError:
        return False, "Sign-in cancelled. Your current account is unchanged."
    except subprocess.TimeoutExpired:
        return False, "Sign-in timed out. Your current account is unchanged; try again."
    except OSError:
        return False, "Codex sign-in could not start. Open the Codex app, then try again."
    finally:
        signal.signal(signal.SIGTERM, previous_handler)


def main(arguments: list[str]) -> int:
    command = arguments[0] if arguments else "list"
    if command == "login":
        ok, message = login(codex_cli())
        print(message, file=sys.stdout if ok else sys.stderr)
        return 0 if ok else 1
    if command == "save":
        ident = save_current()
        if ident:
            print(f"Saved {ident['email']}.")
            return 0
        print("No ChatGPT sign-in found in Codex. Sign in to Codex with the account you want to add, then try again.",
              file=sys.stderr)
        return 1
    if command == "switch":
        if len(arguments) < 2:
            print("usage: codexbar-accounts.py switch <email|id>", file=sys.stderr)
            return 2
        ok, message = switch(arguments[1])
        print(json.dumps({"ok": ok, "message": message}))
        return 0 if ok else 1
    if command == "app-running":
        return 0 if app_pids() else 1
    if command == "restart-app":
        ok, message = restart_app()
        print(message)
        return 0 if ok else 1
    if command == "usage":
        cli = str(pathlib.Path.home() / ".local/bin/codexbar")
        print(json.dumps({"accounts": usage_report(cli, force="--force" in arguments)}))
        return 0
    if command == "list":
        save_current()
        print(json.dumps({"accounts": list_accounts()}))
        return 0
    print(f"unknown command {command}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
