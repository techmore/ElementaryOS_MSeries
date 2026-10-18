#!/usr/bin/env python3
"""Claude account list and switching for the M-series CodexBar port, via claude-swap (cswap).

Upstream CodexBar drives the same tool on macOS; here we call it ourselves so the Wingpanel card can
show every saved Claude login with its quota and switch between them.

  codexbar-claude.py list             accounts as JSON (no tokens)
  codexbar-claude.py login            browser sign-in with Claude Code's CLI, then save it
  codexbar-claude.py add              save the signed-in Claude Code login
  codexbar-claude.py switch <number>  make a saved account the active one

claude-swap (MIT, realiti4/claude-swap) lives in ~/.local/share/claude-swap-venv; cswap is linked into ~/.local/bin.
"""

from __future__ import annotations

import datetime as dt
import json
import os
import pathlib
import shutil
import subprocess
import sys
from typing import Any


def cswap_path() -> str | None:
    local = pathlib.Path.home() / ".local/bin/cswap"
    return str(local) if local.exists() else shutil.which("cswap")


def run(cli: str, arguments: list[str]) -> dict[str, Any] | None:
    try:
        result = subprocess.run([cli, *arguments, "--json"], capture_output=True, text=True, timeout=60,
                                env={**os.environ, "NO_COLOR": "1"}, check=False)
        data = json.loads(result.stdout)
    except (OSError, subprocess.SubprocessError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) and data.get("schemaVersion") == 1 else None


def reset_text(resets_at: str, now: dt.datetime) -> str:
    try:
        target = dt.datetime.fromisoformat(resets_at.replace("Z", "+00:00"))
    except ValueError:
        return ""
    seconds = int((target - now).total_seconds())
    if seconds <= 0:
        return "Resetting now"
    days, rest = divmod(seconds, 86400)
    hours, rest = divmod(rest, 3600)
    minutes = rest // 60
    if days:
        return f"Resets in {days}d {hours}h"
    return f"Resets in {hours}h {minutes}m" if hours else f"Resets in {minutes}m"


def window(key: str, label: str, minutes: int, usage: Any, now: dt.datetime) -> dict[str, Any] | None:
    if not isinstance(usage, dict) or not isinstance(usage.get("pct"), (int, float)):
        return None
    remaining = round(max(0.0, min(100.0, 100.0 - float(usage["pct"]))), 1)
    resets_at = usage.get("resetsAt") if isinstance(usage.get("resetsAt"), str) else ""
    return {"key": key, "label": label, "minutes": minutes, "remaining": remaining, "displayValue": remaining,
            "displaySuffix": "left", "resetsAt": resets_at, "resetText": reset_text(resets_at, now) if resets_at else "",
            "pace": "", "paceDelta": None, "paceExpected": None, "warning": False}


def account_row(row: dict[str, Any], now: dt.datetime) -> dict[str, Any] | None:
    email = row.get("email")
    number = row.get("number")
    if not isinstance(email, str) or not isinstance(number, int):
        return None
    usage = row.get("usage") if isinstance(row.get("usage"), dict) else {}
    windows = [w for w in (window("primary", "5 hour", 300, usage.get("fiveHour"), now),
                           window("secondary", "7 day", 10080, usage.get("sevenDay"), now)) if w]
    return {"number": number, "email": email, "active": bool(row.get("active")), "windows": windows,
            "status": row.get("usageStatus") if isinstance(row.get("usageStatus"), str) else ""}


def listing(cli: str | None, now: dt.datetime | None = None) -> dict[str, Any]:
    if not cli:
        return {"available": False, "accounts": [], "activeEmail": ""}
    now = now or dt.datetime.now(dt.timezone.utc)
    listed = run(cli, ["list"])
    accounts = [a for a in (account_row(r, now) for r in (listed or {}).get("accounts", []) if isinstance(r, dict)) if a]
    active_email = next((a["email"] for a in accounts if a["active"]), "")
    if not active_email:  # a login that has not been saved into claude-swap yet
        status = run(cli, ["status"])
        active = (status or {}).get("active")
        active_email = active.get("email", "") if isinstance(active, dict) and isinstance(active.get("email"), str) else ""
    return {"available": True, "accounts": accounts, "activeEmail": active_email}


def switch(cli: str | None, number: str) -> tuple[bool, str]:
    if not cli:
        return False, "claude-swap is not installed."
    if not number.isdigit():
        return False, "Pick a saved account by number."
    result = run(cli, ["switch", number])
    if not result:
        return False, "claude-swap could not switch accounts."
    if result.get("error"):
        return False, str(result["error"].get("message", "claude-swap reported an error."))
    if result.get("switched"):
        return True, "Switched Claude. A running Claude Code session picks it up on its next message."
    return False, str(result.get("reason") or "Nothing was switched.")


def claude_cli() -> str | None:
    """Claude Code's own CLI: on PATH, else the copy the Claude desktop app bundles (newest version)."""
    found = shutil.which("claude")
    if found:
        return found
    bundled = sorted((pathlib.Path.home() / ".config/Claude/claude-code").glob("*/*/claude"),
                     key=lambda p: [int(x) if x.isdigit() else 0 for x in p.parts[-3].split(".")])
    return str(bundled[-1]) if bundled else None


def logged_in(claude: str) -> bool:
    try:
        result = subprocess.run([claude, "auth", "status"], capture_output=True, text=True, timeout=30, check=False)
        return bool(json.loads(result.stdout).get("loggedIn"))
    except (OSError, subprocess.SubprocessError, json.JSONDecodeError, AttributeError):
        return False


def login(cli: str | None, claude: str | None) -> tuple[bool, str]:
    """Browser sign-in with Claude Code's CLI, then save the login. A login already present is saved first."""
    if not cli:
        return False, "claude-swap is not installed."
    if not claude:
        return False, "Claude Code's command line was not found. Install Claude Code, then try again."
    if logged_in(claude):
        add(cli)  # keep the account we are about to sign out of
    try:
        result = subprocess.run([claude, "auth", "login"], capture_output=True, text=True, timeout=600, check=False)
    except subprocess.TimeoutExpired:
        return False, "The browser sign-in was not completed in time."
    except (OSError, subprocess.SubprocessError):
        return False, "Claude Code's sign-in could not start."
    if result.returncode != 0:
        text = (result.stdout + result.stderr).strip()
        return False, text.splitlines()[-1] if text else "The Claude sign-in did not finish."
    return add(cli)


def add(cli: str | None) -> tuple[bool, str]:
    """Save the signed-in Claude Code login into claude-swap, with a message a person can act on."""
    if not cli:
        return False, "claude-swap is not installed."
    try:
        result = subprocess.run([cli, "add"], capture_output=True, text=True, timeout=60,
                                env={**os.environ, "NO_COLOR": "1"}, check=False)
    except (OSError, subprocess.SubprocessError):
        return False, "claude-swap could not run."
    text = (result.stdout + result.stderr).strip()
    if "No credentials found" in text:
        return False, ("Claude Code has no saved sign-in on this computer yet. Sign in with the Claude Code "
                       "command line (run `claude` and log in), then try again.")
    if result.returncode != 0:
        return False, text.splitlines()[-1] if text else "claude-swap could not save the login."
    return True, text.splitlines()[-1] if text else "Saved."


def main(arguments: list[str]) -> int:
    command = arguments[0] if arguments else "list"
    cli = cswap_path()
    if command == "list":
        print(json.dumps(listing(cli)))
        return 0
    if command == "login":
        ok, message = login(cli, claude_cli())
        print(message, file=sys.stdout if ok else sys.stderr)
        return 0 if ok else 1
    if command == "add":
        ok, message = add(cli)
        print(message, file=sys.stdout if ok else sys.stderr)
        return 0 if ok else 1
    if command == "switch" and len(arguments) > 1:
        ok, message = switch(cli, arguments[1])
        print(json.dumps({"ok": ok, "message": message}))
        return 0 if ok else 1
    print("usage: codexbar-claude.py list | login | add | switch <number>", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
