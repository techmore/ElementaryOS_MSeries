#!/usr/bin/env python3
"""Codex account switching for the M-series CodexBar port.

Upstream CodexBar's managed Codex accounts are macOS-only, so on Linux we keep
one saved Codex home per account and swap ~/.codex/auth.json atomically.

  codexbar-accounts.py list [--json]      accounts (no tokens), active one marked
  codexbar-accounts.py save               remember the signed-in account
  codexbar-accounts.py switch <email|id>  make a saved account the active one
  codexbar-accounts.py usage              list plus each account's weekly quota

Running Codex sessions keep the account they started with; restart them.
"""

from __future__ import annotations

import base64
import json
import os
import pathlib
import subprocess
import sys
import tempfile
from typing import Any


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


def save_current() -> dict[str, str] | None:
    auth = read_auth(codex_home() / "auth.json")
    ident = identity(auth) if auth else None
    if not auth or not ident:
        return None
    write_private(store_dir() / slug(ident["id"]) / "auth.json", auth)
    return ident


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
    homes = saved_homes()
    if wanted["id"] not in homes:
        return False, f"{wanted['email']} has no saved sign-in."
    saved = read_auth(homes[wanted["id"]] / "auth.json")
    if not saved:
        return False, f"{wanted['email']}'s saved sign-in could not be read."
    save_current()  # never lose the account we are leaving
    write_private(codex_home() / "auth.json", saved)
    return True, f"Switched Codex to {wanted['email']}. Restart running Codex sessions to use it."


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
    return {"windows": windows}


def usage_report(cli: str) -> list[dict[str, Any]]:
    homes = saved_homes()
    report = []
    for account in list_accounts():
        home = codex_home() if account["active"] else homes.get(account["id"])
        details = usage_for(home, cli) if home else {"error": "No saved sign-in."}
        report.append({k: account[k] for k in ("email", "plan", "id", "active")} | details)
    return report


def main(arguments: list[str]) -> int:
    command = arguments[0] if arguments else "list"
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
    if command == "usage":
        cli = str(pathlib.Path.home() / ".local/bin/codexbar")
        print(json.dumps({"accounts": usage_report(cli)}))
        return 0
    if command == "list":
        save_current()
        print(json.dumps({"accounts": list_accounts()}))
        return 0
    print(f"unknown command {command}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
