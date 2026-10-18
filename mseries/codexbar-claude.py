#!/usr/bin/env python3
"""Claude account list and switching for the M-series CodexBar port, via claude-swap (cswap).

Upstream CodexBar drives the same tool on macOS; here we call it ourselves so the Wingpanel card can
show every saved Claude login with its quota and switch between them.

  codexbar-claude.py list             accounts as JSON (no tokens)
  codexbar-claude.py login            browser sign-in with Claude Code's CLI, then save it
  codexbar-claude.py add              save the signed-in Claude Code login
  codexbar-claude.py switch <number> [--desktop]  switch CLI, optionally the native app too
  codexbar-claude.py app-save          remember the app's current session
  codexbar-claude.py app-switch <uuid> switch only the native app

claude-swap (MIT, realiti4/claude-swap) lives in ~/.local/share/claude-swap-venv; cswap is linked into ~/.local/bin.

What a switch changes: claude-swap rewrites Claude Code's own login (~/.claude/.credentials.json and the
oauthAccount block of ~/.claude.json), so the `claude` command line uses the new account. The Claude desktop app
does NOT read those files: it keeps its own sign-in in encrypted Electron storage and hands every Code session it
starts that login through CLAUDE_CODE_OAUTH_TOKEN, which wins over the file. So we also report which account the
desktop app is on (its config.json `lastKnownAccountUuid`, matched against the identity in claude-swap's saved
configs) and say plainly when the two differ. App sessions are copied as encrypted bytes into a private,
atomic bundle on this machine; tokens are never decrypted or included in list/switch output.
"""

from __future__ import annotations

import datetime as dt
import base64
import contextlib
import fcntl
import json
import os
import pathlib
import re
import signal
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
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


def account_plan(number: int, email: str, active: bool = False) -> str:
    """Read subscription metadata only; never return credentials or change a saved login."""
    xdg = os.environ.get("XDG_DATA_HOME", "")
    root = pathlib.Path(xdg) if xdg and os.path.isabs(xdg) else pathlib.Path.home() / ".local/share"
    paths = (root / "claude-swap" / "credentials").glob(f".creds-{number}-*.enc")
    saved = next((p for p in paths if p.name == f".creds-{number}-{email}.enc"), None)
    credentials: list[dict[str, Any]] = []
    if active:
        home = pathlib.Path(os.environ.get("CLAUDE_CONFIG_DIR") or pathlib.Path.home() / ".claude")
        credentials.append(read_json(home / ".credentials.json"))
    if saved is not None:
        try:
            data = json.loads(base64.b64decode(saved.read_bytes(), validate=True))
            if isinstance(data, dict):
                credentials.append(data)
        except (OSError, ValueError):
            pass
    for data in credentials:
        oauth = data.get("claudeAiOauth")
        plan = oauth.get("subscriptionType") if isinstance(oauth, dict) else None
        if isinstance(plan, str) and plan.lower() in {"free", "pro", "max", "team", "enterprise"}:
            return plan.lower()
    return ""


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


APP_KEYS = ("lastKnownAccountUuid", "oauth:tokenCache", "oauth:tokenCacheV2")
APP_EXECUTABLE = "/usr/lib/claude-desktop/claude-desktop"


def data_root() -> pathlib.Path:
    xdg = os.environ.get("XDG_DATA_HOME", "")
    return pathlib.Path(xdg) if os.path.isabs(xdg) else pathlib.Path.home() / ".local/share"


def app_root() -> pathlib.Path:
    xdg = os.environ.get("XDG_CONFIG_HOME", "")
    return (pathlib.Path(xdg) if os.path.isabs(xdg) else pathlib.Path.home() / ".config") / "Claude"


def session_root() -> pathlib.Path:
    path = data_root() / "codexbar-claude-app"
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    path.chmod(0o700)
    return path


def session_path(uuid: str) -> pathlib.Path:
    if not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9-]{0,127}", uuid):
        raise ValueError("Invalid Claude account identifier.")
    return session_root() / (uuid + ".json")


def atomic_private(path: pathlib.Path, content: bytes) -> None:
    fd, name = tempfile.mkstemp(prefix=".codexbar-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, path)
    finally:
        pathlib.Path(name).unlink(missing_ok=True)


@contextlib.contextmanager
def app_lock(blocking: bool = True):
    fd = os.open(session_root() / "lock", os.O_CREAT | os.O_RDWR, 0o600)
    with os.fdopen(fd, "w") as stream:
        fcntl.flock(stream, fcntl.LOCK_EX | (0 if blocking else fcntl.LOCK_NB))
        yield


def cookie_path() -> pathlib.Path:
    modern = app_root() / "Network/Cookies"
    return modern if modern.exists() else app_root() / "Cookies"


def has_session(db: sqlite3.Connection) -> bool:
    return bool(db.execute("SELECT 1 FROM cookies WHERE name='sessionKey' "
                           "AND (host_key='claude.ai' OR host_key='.claude.ai') "
                           "AND (length(encrypted_value)>0 OR length(value)>0)").fetchone())


def has_app_auth(config: dict[str, Any], db: sqlite3.Connection) -> bool:
    # OAuth caches alone do not sign the native chat surface in. Chromium may take
    # 30 seconds to flush newly created cookies; don't label such an account ready.
    return has_session(db)


def capture_app() -> str:
    """Copy encrypted session material, never decrypt it. Caller holds app_lock.

    One atomic bundle avoids pairing one account's cookies with another account's token cache.
    SQLite backup includes committed WAL data even while Electron is running.
    """
    config = read_json(app_root() / "config.json")
    uuid = config.get("lastKnownAccountUuid", "")
    if not isinstance(uuid, str) or not uuid or not cookie_path().is_file():
        return ""
    destination = session_path(uuid)
    fd, name = tempfile.mkstemp(dir=session_root(), prefix=".cookies-")
    os.close(fd)
    try:
        deadline = time.monotonic() + 3
        def progress(*unused):
            if time.monotonic() > deadline:
                raise TimeoutError("Claude session database is busy.")
        with contextlib.closing(sqlite3.connect(cookie_path().as_uri() + "?mode=ro", uri=True, timeout=1)) as source, \
                contextlib.closing(sqlite3.connect(name)) as target:
            if not has_app_auth(config, source):
                return ""  # lastKnownAccountUuid survives signing out; don't overwrite a good snapshot.
            source.backup(target, pages=64, progress=progress)
            target.execute("PRAGMA journal_mode=DELETE")  # a portable, self-contained database, no WAL dependency
        latest = read_json(app_root() / "config.json")
        if any(latest.get(k) != config.get(k) for k in APP_KEYS):
            return ""  # sign-in changed during the copy; retry at the next poll
        bundle = {"schemaVersion": 1, "accountUuid": uuid,
                  "config": {k: config[k] for k in APP_KEYS if k in config},
                  "cookies": base64.b64encode(pathlib.Path(name).read_bytes()).decode("ascii")}
        atomic_private(destination, json.dumps(bundle).encode())
        return uuid
    finally:
        pathlib.Path(name).unlink(missing_ok=True)


def load_session(uuid: str) -> dict[str, Any]:
    bundle = read_json(session_path(uuid))
    config = bundle.get("config")
    if bundle.get("schemaVersion") != 1 or bundle.get("accountUuid") != uuid or not isinstance(config, dict) \
            or config.get("lastKnownAccountUuid") != uuid:
        raise ValueError("Sign in to this account once in the Claude app, then reopen CodexBar to save its app session.")
    try:
        cookies = base64.b64decode(bundle["cookies"], validate=True)
        with contextlib.closing(sqlite3.connect(":memory:")) as db:
            db.deserialize(cookies)
            if db.execute("PRAGMA quick_check").fetchone() != ("ok",) or not has_app_auth(config, db):
                raise ValueError()
    except (KeyError, TypeError, ValueError, sqlite3.Error):
        raise ValueError("The saved Claude app session is damaged. Sign in to that account in the app again.") from None
    return {"config": config, "cookies": cookies}


def restore_app(session: dict[str, Any]) -> None:
    # Must only run after Electron has exited; remove old journal/WAL files so they cannot replay old cookies.
    if app_pids():
        raise ValueError("Claude opened again before the switch finished. Close it and try again.")
    path = cookie_path()
    config_path = app_root() / "config.json"
    config = json.loads(config_path.read_text())
    if not isinstance(config, dict):
        raise ValueError("Claude's configuration is invalid.")
    for key in APP_KEYS:
        config.pop(key, None)
    config.update({k: v for k, v in session["config"].items() if k in APP_KEYS})
    atomic_private(path, session["cookies"])
    for suffix in ("-journal", "-wal", "-shm"):
        pathlib.Path(str(path) + suffix).unlink(missing_ok=True)
    atomic_private(config_path, json.dumps(config, indent=2).encode())


def app_pids() -> list[int]:
    found = []
    for entry in pathlib.Path("/proc").iterdir():
        if not entry.name.isdigit():
            continue
        try:
            if entry.stat().st_uid == os.getuid() and os.readlink(entry / "exe") == APP_EXECUTABLE:
                found.append(int(entry.name))
        except OSError:
            pass
    return found


def stop_app() -> bool:
    pids = app_pids()
    # A switch launched from a Claude Code session inside the app would kill its own coordinator.
    parent = os.getppid()
    while parent > 1:
        if parent in pids:
            raise ValueError("Switch the Claude app from the CodexBar panel, outside the Claude app.")
        try:
            parent = int(pathlib.Path(f"/proc/{parent}/stat").read_text().rsplit(")", 1)[1].split()[1])
        except (OSError, ValueError, IndexError):
            break
    for pid in pids:
        try:
            # Chromium rewrites argv[0] to contain its entire command line on Linux;
            # looking for a separate --type= argument misidentifies utility children.
            parent_pid = int(pathlib.Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()[1])
            if parent_pid not in pids:
                os.kill(pid, signal.SIGTERM)
        except (FileNotFoundError, ProcessLookupError):
            pass
    deadline = time.monotonic() + 20
    while app_pids():
        if time.monotonic() >= deadline:
            raise ValueError("Claude did not quit. Close the app and try again; no session files were replaced.")
        time.sleep(0.1)
    return bool(pids)


def launch_app() -> None:
    # Don't let a calling Claude session inject the old account's token into the relaunched app.
    env = {k: v for k, v in os.environ.items() if not k.startswith("CLAUDE_CODE_")}
    # Electron can retain inherited output pipes after gtk-launch has exited. Detach it
    # and observe the app process instead of waiting on communicate() until the GUI quits.
    launcher = subprocess.Popen(["gtk-launch", "com.anthropic.Claude"], env=env,
                                stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                stderr=subprocess.DEVNULL, start_new_session=True)
    deadline = time.monotonic() + 10
    while not app_pids():
        if launcher.poll() not in (None, 0):
            raise ValueError("The Claude app could not restart. Open Claude from the dock.")
        if time.monotonic() >= deadline:
            raise ValueError("The Claude app did not start. Open Claude from the dock.")
        time.sleep(0.1)
    launcher.poll()


def app_switch(uuid: str, cli: str | None = None, number: str | None = None) -> tuple[bool, str]:
    """Switch the app, optionally together with the CLI. No app credentials are ever printed."""
    try:
        with app_lock():
            target = load_session(uuid)  # validate before stopping the app or changing the CLI
            current = read_json(app_root() / "config.json").get("lastKnownAccountUuid", "")
            captured = capture_app()
            if current == uuid and captured == uuid:
                return switch(cli, number) if number else (True, "The Claude app already uses this account.")
            if not captured:
                current = read_json(session_root() / "pending-login.json").get("previous", "")
            if not current:
                raise ValueError("The current Claude app sign-in could not be saved. Sign in in the app before switching.")
            original = load_session(current)
            was_running = stop_app()
            try:
                # Electron may flush new credentials as it exits. Preserve them before replacing anything.
                if capture_app():
                    original = load_session(current)
                restore_app(target)
                if number:
                    ok, message = switch(cli, number)
                    if not ok:
                        raise ValueError(message)
            except (OSError, ValueError, sqlite3.Error, TimeoutError, subprocess.SubprocessError):
                restore_app(original)
                if was_running:
                    launch_app()
                raise
            try:
                launch_app()
            except (ValueError, OSError, subprocess.SubprocessError):
                return False, "The account was saved for the Claude app, but it could not restart. Open Claude from the dock."
            (session_root() / "pending-login.json").unlink(missing_ok=True)
            return True, "Claude's app session was switched and the app restarted." + (" Claude Code's command line uses the same account." if number else "")
    except (OSError, ValueError, sqlite3.Error, TimeoutError, subprocess.SubprocessError) as error:
        # Never echo raw config, cookie data, or subprocess output on failure.
        return False, str(error) if isinstance(error, ValueError) else "Claude's app session could not be switched; try again after closing Claude."


def app_login(number: str) -> tuple[bool, str]:
    """Open a locally signed-out app without revoking the session we just saved on the server."""
    if not account_uuid(number):
        return False, "Save this Claude Code account first, then set up its app login."
    try:
        with app_lock():
            current = capture_app() or read_json(session_root() / "pending-login.json").get("previous", "")
            if not current:
                raise ValueError("Sign in to the Claude app first so its current session can be saved.")
            original = load_session(current)
            was_running = stop_app()
            try:
                if capture_app():
                    original = load_session(current)
                with contextlib.closing(sqlite3.connect(":memory:")) as db:
                    db.deserialize(original["cookies"])
                    db.execute("DELETE FROM cookies")
                    db.commit()
                    empty_cookies = db.serialize()
                atomic_private(session_root() / "pending-login.json", json.dumps({"previous": current}).encode())
                restore_app({"config": {}, "cookies": empty_cookies})
            except (OSError, ValueError, sqlite3.Error, TimeoutError):
                restore_app(original)
                if was_running:
                    launch_app()
                raise
            launch_app()
            return True, ("Sign in to the selected account in the Claude app, then choose Save app login in CodexBar. "
                          "Your previous app login is saved; choose Switch both on that account to return to it.")
    except (OSError, ValueError, sqlite3.Error, TimeoutError, subprocess.SubprocessError) as error:
        return False, str(error) if isinstance(error, ValueError) else "The Claude app login could not start. Reopen Claude and try again."


def account_uuid(number: str) -> str:
    if not number.isdigit():
        return ""
    matches = list((data_root() / "claude-swap/configs").glob(f".claude-config-{number}-*.json"))
    return identity(read_json(matches[0]))[1] if len(matches) == 1 else ""


def desktop_account(known: dict[str, str]) -> dict[str, Any]:
    """Which account the Claude desktop app is signed in to, as far as its plain config says."""
    config = app_root() / "config.json"
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
    for account in accounts:
        account["plan"] = account_plan(account["number"], account["email"],
            active=bool(cli_email and account["active"]))
    active_plan = next((a["plan"] for a in accounts if a["active"]), "")
    if not active_plan and cli_email and cli_email.lower() == active_email.lower():
        active_plan = account_plan(0, cli_email, active=True)
    snapshot_error = ""
    try:
        with app_lock(blocking=False):
            capture_app()
    except BlockingIOError:
        pass  # another switch owns the store; don't race its session copy
    except (OSError, ValueError, sqlite3.Error, TimeoutError):
        snapshot_error = "The Claude app session could not be saved. Close and reopen Claude, then try again."
    desktop = desktop_account(saved_identities())
    for account in accounts:
        uuid = account_uuid(str(account["number"]))
        account["desktopActive"] = bool(uuid and uuid == desktop["accountUuid"])
        try:
            load_session(uuid)
            account["desktopReady"] = True
        except (OSError, ValueError):
            account["desktopReady"] = False
    note = desktop_note(desktop, active_email, cli_uuid)
    return {"available": True, "accounts": accounts, "activeEmail": active_email, "activePlan": active_plan,
            "desktop": {"installed": desktop["installed"], "email": desktop["email"], "differs": bool(note)},
            "desktopNote": note, "desktopSnapshotError": snapshot_error}


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
    if command == "app-login" and len(arguments) == 2:
        ok, message = app_login(arguments[1])
        print(message, file=sys.stdout if ok else sys.stderr)
        return 0 if ok else 1
    if command == "app-save":
        try:
            with app_lock():
                deadline = time.monotonic() + 35
                uuid = capture_app()
                while not uuid and time.monotonic() < deadline:
                    time.sleep(1)
                    uuid = capture_app()
            if not uuid:
                raise ValueError("Sign in to the Claude app first, then save its login here.")
            print("The Claude app's current login is saved for fast switching on this computer.")
            return 0
        except (OSError, ValueError, sqlite3.Error, TimeoutError):
            print("The app login could not be saved. Sign in to Claude, then try again.", file=sys.stderr)
            return 1
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
    if command == "app-switch" and len(arguments) == 2:
        ok, message = app_switch(arguments[1])
        print(json.dumps({"ok": ok, "message": message}))
        return 0 if ok else 1
    if command == "switch" and len(arguments) > 1:
        if "--desktop" in arguments:
            uuid = account_uuid(arguments[1])
            ok, message = app_switch(uuid, cli, arguments[1]) if uuid else (False, "This saved account has no app identity. Sign in to it in Claude and save the login again.")
        else:
            ok, message = switch(cli, arguments[1])
        print(json.dumps({"ok": ok, "message": message}))
        return 0 if ok else 1
    print("usage: codexbar-claude.py list | login | add | app-save | switch <number> [--desktop] | app-switch <uuid>", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
