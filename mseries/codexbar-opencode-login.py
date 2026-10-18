#!/usr/bin/env python3
"""Sign in to OpenCode Go for CodexBar's quota.

Upstream CodexBar reads OpenCode Go quota from an opencode.ai web session, but it only imports browser
cookies on macOS. On Linux it accepts the same session as a manual Cookie header, so this opens a small
native sign-in window, keeps only the opencode.ai session cookies upstream forwards, and saves them to
CodexBar's config (providers[opencodego]: cookieSource "manual", cookieHeader).

  codexbar-opencode-login.py login     sign in, save the session, and check that quota now loads
  codexbar-opencode-login.py status    JSON: {"signedIn": bool}
"""

from __future__ import annotations

import contextlib
import fcntl
import json
import os
import pathlib
import subprocess
import sys
import tempfile
from typing import Any

SIGN_IN_URL = "https://opencode.ai/auth"
# The cookies upstream forwards (OpenCodeWebCookieSupport.requestCookieNames); nothing else is kept.
SESSION_COOKIES = ("auth", "__Host-auth", "__Host-console_session")
PROVIDER = "opencodego"


def config_path() -> pathlib.Path:
    """Same resolution as upstream's CodexBarConfigStore.defaultURL."""
    override = os.environ.get("CODEXBAR_CONFIG", "").strip()
    if override:
        return pathlib.Path(override).expanduser()
    xdg = os.environ.get("XDG_CONFIG_HOME", "").strip()
    if xdg and pathlib.Path(xdg).expanduser().is_absolute():
        return pathlib.Path(xdg).expanduser() / "codexbar" / "config.json"
    home = pathlib.Path.home()
    xdg_default = home / ".config" / "codexbar" / "config.json"
    legacy = home / ".codexbar" / "config.json"
    if not xdg_default.exists() and legacy.exists():
        return legacy
    return xdg_default


def cookie_header(cookies: dict[str, str]) -> str:
    return "; ".join(f"{name}={cookies[name]}" for name in SESSION_COOKIES if cookies.get(name))


@contextlib.contextmanager
def locked(path: pathlib.Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path.with_name(path.name + ".lock"), "a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(lock, fcntl.LOCK_UN)


def save_session(header: str, path: pathlib.Path | None = None) -> None:
    path = path or config_path()
    with locked(path):
        try:
            config: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            config = {"version": 1, "providers": []}
        providers = config.setdefault("providers", [])
        entry = next((p for p in providers if isinstance(p, dict) and p.get("id") == PROVIDER), None)
        if entry is None:
            entry = {"id": PROVIDER}
            providers.append(entry)
        entry.update({"enabled": True, "cookieSource": "manual", "cookieHeader": header})
        with tempfile.NamedTemporaryFile("w", dir=path.parent, prefix=".config.", delete=False,
                                         encoding="utf-8") as handle:
            os.fchmod(handle.fileno(), 0o600)
            json.dump(config, handle, indent=2)
            handle.write("\n")
        os.replace(handle.name, path)


def signed_in(path: pathlib.Path | None = None) -> bool:
    try:
        config = json.loads((path or config_path()).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    return any(isinstance(p, dict) and p.get("id") == PROVIDER and p.get("cookieSource") == "manual"
               and p.get("cookieHeader") for p in config.get("providers", []))


def check_quota() -> tuple[bool, str]:
    cli = pathlib.Path.home() / ".local/bin/codexbar"
    try:
        result = subprocess.run([str(cli), "usage", "--provider", PROVIDER, "--source", "web", "--format", "json"],
                                capture_output=True, text=True, timeout=90, check=False)
        rows = json.loads(result.stdout or "[]")
    except (OSError, ValueError, subprocess.TimeoutExpired) as error:
        return False, f"Saved, but CodexBar couldn't be asked for quota: {error}"
    row = rows[0] if isinstance(rows, list) and rows else {}
    if isinstance(row.get("error"), dict):
        return False, "Saved the sign-in, but opencode.ai rejected it: " + str(row["error"].get("message", ""))
    return True, "OpenCode Go quota is now read from your opencode.ai account."


def sign_in() -> str | None:
    """Show the opencode.ai sign-in page; return the session Cookie header once the user is signed in."""
    import gi
    gi.require_version("Gtk", "4.0")
    gi.require_version("WebKit", "6.0")
    from gi.repository import GLib, Gtk, WebKit

    # A private, persistent profile: a later re-sign-in after the session expires is usually one click.
    data = pathlib.Path(os.environ.get("XDG_DATA_HOME") or pathlib.Path.home() / ".local/share") / "codexbar-opencode-login"
    cache = pathlib.Path(os.environ.get("XDG_CACHE_HOME") or pathlib.Path.home() / ".cache") / "codexbar-opencode-login"
    for directory in (data, cache):
        directory.mkdir(parents=True, exist_ok=True)
        directory.chmod(0o700)
    session = WebKit.NetworkSession.new(str(data), str(cache))
    session.get_cookie_manager().set_persistent_storage(str(data / "cookies.sqlite"),
                                                       WebKit.CookiePersistentStorage.SQLITE)
    result: dict[str, str | None] = {"header": None}
    app = Gtk.Application(application_id="io.github.mseries.CodexBarOpenCodeLogin")

    def activate(application: Gtk.Application) -> None:
        view = WebKit.WebView(network_session=session)
        window = Gtk.ApplicationWindow(application=application, title="Sign in to OpenCode",
                                       default_width=480, default_height=720)
        window.set_child(view)

        def collect(*_args: Any) -> None:
            uri = view.get_uri() or ""
            # Still on the sign-in or an identity-provider page: nothing to collect yet.
            if (not uri.startswith("https://opencode.ai/") or uri.startswith(SIGN_IN_URL)
                    or "/login" in uri.split("?")[0]):
                return

            def got(manager: Any, task: Any) -> None:
                try:
                    cookies = {c.get_name(): c.get_value() for c in manager.get_cookies_finish(task)}
                except GLib.Error:
                    return
                header = cookie_header(cookies)
                if header and result["header"] is None:
                    result["header"] = header
                    window.close()

            session.get_cookie_manager().get_cookies("https://opencode.ai/", None, got)

        view.connect("load-changed", lambda v, event: event == WebKit.LoadEvent.FINISHED and collect())
        view.load_uri(SIGN_IN_URL)
        window.present()

    app.connect("activate", activate)
    app.run([])
    return result["header"]


def main(arguments: list[str]) -> int:
    command = arguments[0] if arguments else ""
    if command == "status":
        print(json.dumps({"signedIn": signed_in()}))
        return 0
    if command == "login":
        header = sign_in()
        if not header:
            print("Sign-in was closed before opencode.ai finished signing you in.")
            return 1
        save_session(header)
        ok, message = check_quota()
        print(message)
        return 0 if ok else 1
    print("usage: codexbar-opencode-login.py login | status", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
