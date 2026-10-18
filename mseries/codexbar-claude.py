#!/usr/bin/env python3
"""Claude account list and switching for the M-series CodexBar port, via claude-swap (cswap).

Upstream CodexBar drives the same tool on macOS; here we call it ourselves so the Wingpanel card can
show every saved Claude login with its quota and switch between them.

  codexbar-claude.py list             accounts as JSON (no tokens)
  codexbar-claude.py login            browser sign-in with Claude Code's CLI, then save it
  codexbar-claude.py add              save the signed-in Claude Code login
  codexbar-claude.py switch <number>  make a saved account the active one

claude-swap (MIT, realiti4/claude-swap) lives in ~/.local/share/claude-swap-venv; cswap is linked into ~/.local/bin.

What a switch changes: claude-swap rewrites Claude Code's own login (~/.claude/.credentials.json and the
oauthAccount block of ~/.claude.json), so the `claude` command line uses the new account. The Claude desktop app
does NOT read those files: it keeps its own sign-in in encrypted Electron storage and hands every Code session it
starts that login through CLAUDE_CODE_OAUTH_TOKEN, which wins over the file. So we also report which account the
desktop app is on (its config.json `lastKnownAccountUuid`, matched against the identity in claude-swap's saved
configs) and say plainly when the two differ. We never read or decrypt the app's tokens.
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


def read_json(path: pathlib.Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def identity(config: dict[str, Any]) -> tuple[str, str]:
    """(email, accountUuid) from a ~/.claude.json-shaped dict; identity fields only, never tokens."""
    account = config.get("oauthAccount")
    if not isinstance(account, dict):
        return "", ""
    email = account.get("emailAddress")
    uuid = account.get("accountUuid")
    return (email if isinstance(email, str) else "", uuid if isinstance(uuid, str) else "")


def cli_identity() -> tuple[str, str]:
    """The account Claude Code's command line is signed in as right now (~/.claude.json)."""
    base = os.environ.get("CLAUDE_CONFIG_DIR") or str(pathlib.Path.home())
    return identity(read_json(pathlib.Path(base) / ".claude.json"))


def saved_identities() -> dict[str, str]:
    """accountUuid -> email for every login saved in claude-swap (its per-account ~/.claude.json copies)."""
    xdg = os.environ.get("XDG_DATA_HOME", "")
    root = pathlib.Path(xdg) if xdg and os.path.isabs(xdg) else pathlib.Path.home() / ".local/share"
    found: dict[str, str] = {}
    for path in sorted((root / "claude-swap" / "configs").glob(".claude-config-*.json")):
        email, uuid = identity(read_json(path))
        if email and uuid:
            found[uuid] = email
    return found


def desktop_account(known: dict[str, str]) -> dict[str, Any]:
    """Which account the Claude desktop app is signed in to, as far as its plain config says."""
    config = pathlib.Path.home() / ".config/Claude/config.json"
    if not config.exists():
        return {"installed": False, "email": "", "accountUuid": ""}
    uuid = read_json(config).get("lastKnownAccountUuid")
    uuid = uuid if isinstance(uuid, str) else ""
    return {"installed": True, "email": known.get(uuid, ""), "accountUuid": uuid}


def desktop_note(desktop: dict[str, Any], email: str, uuid: str) -> str:
    """One sentence about the desktop app, or "" when it is absent or already on the same account."""
    if not desktop.get("installed") or not desktop.get("accountUuid"):
        return ""
    if uuid and desktop["accountUuid"] == uuid:
        return ""
    there = desktop.get("email") or "a different account"
    return (f"The Claude app is still signed in as {there}: its Code sessions use the app's own sign-in, not this "
            f"one. To use {email or 'this account'} there, sign out of the Claude app and sign in as that account.")


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
    cli_email, cli_uuid = cli_identity()
    if cli_email:  # the live login is what `claude` uses; claude-swap's record can lag behind it
        active_email = cli_email
        for account in accounts:
            account["active"] = account["email"].lower() == cli_email.lower()
    desktop = desktop_account(saved_identities())
    note = desktop_note(desktop, active_email, cli_uuid)
    return {"available": True, "accounts": accounts, "activeEmail": active_email,
            "desktop": {"installed": desktop["installed"], "email": desktop["email"], "differs": bool(note)},
            "desktopNote": note}


def switch(cli: str | None, number: str) -> tuple[bool, str]:
    if not cli:
        return False, "claude-swap is not installed."
    if not number.isdigit():
        return False, "Pick a saved account by number."
    result = run(cli, ["switch", number])
    if not result:
        return False, "claude-swap could not switch accounts."
    error = result.get("error")
    if error:
        return False, str(error.get("message", "claude-swap reported an error.") if isinstance(error, dict) else error)
    target = result.get("to") if isinstance(result.get("to"), dict) else {}
    wanted = target.get("email") if isinstance(target.get("email"), str) else ""
    if not result.get("switched") and result.get("reason") != "already-active":
        return False, str(result.get("message") or result.get("reason") or "Nothing was switched.")
    email, uuid = cli_identity()  # check the login Claude Code will actually read, not just claude-swap's word
    if wanted and email.lower() != wanted.lower():
        return False, (f"claude-swap reported a switch to {wanted}, but Claude Code is still signed in as "
                       f"{email or 'no account'}.")
    who = email or wanted or "the selected account"
    head = (f"Claude Code's command line now uses {who}; a running session picks it up on its next message."
            if result.get("switched") else f"Claude Code's command line already uses {who}.")
    note = desktop_note(desktop_account(saved_identities()), who, uuid)
    return True, f"{head} {note}".strip()


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
