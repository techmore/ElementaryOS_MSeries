#!/usr/bin/env python3
"""Sign in to OpenCode Go for CodexBar's quota.

Upstream CodexBar reads OpenCode Go quota with an API key (usage API) or an opencode.ai web session, but it
only imports browser cookies on macOS. The Connect window takes an API key copied after signing in in the
real browser (passkeys work there) and stores it with `codexbar config set-api-key`. As a fallback it signs
in inside a built-in window and saves only the session cookies upstream forwards as a manual Cookie header
(providers[opencodego]: cookieSource "manual", cookieHeader).

  codexbar-opencode-login.py login     connect, then check that quota now loads
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
    return any(isinstance(p, dict) and p.get("id") == PROVIDER and (p.get("apiKey") or (
        p.get("cookieSource") == "manual" and p.get("cookieHeader"))) for p in config.get("providers", []))


def cli() -> str:
    return str(pathlib.Path.home() / ".local/bin/codexbar")


def quota_error(source: str, extra_env: dict[str, str] | None = None) -> str | None:
    """None when upstream reads OpenCode Go quota from this source, else its error in words."""
    env = dict(os.environ, **(extra_env or {}))
    try:
        result = subprocess.run([cli(), "usage", "--provider", PROVIDER, "--source", source, "--format", "json"],
                                capture_output=True, text=True, timeout=90, check=False, env=env)
        rows = json.loads(result.stdout or "[]")
    except (OSError, ValueError, subprocess.TimeoutExpired) as error:
        return f"CodexBar couldn't be asked for quota: {error}"
    row = rows[0] if isinstance(rows, list) and rows else {}
    if isinstance(row.get("error"), dict):
        return str(row["error"].get("message", "")) or "opencode.ai returned an error."
    return None if row else "CodexBar returned no OpenCode Go data."


def save_api_key(key: str) -> str | None:
    """Store the key with upstream's own command (it lands in CodexBar's config, not on a command line)."""
    try:
        result = subprocess.run([cli(), "config", "set-api-key", "--provider", PROVIDER, "--stdin"],
                                input=key, capture_output=True, text=True, timeout=60, check=False)
    except (OSError, subprocess.TimeoutExpired) as error:
        return str(error)
    return None if result.returncode == 0 else (result.stderr.strip() or result.stdout.strip() or "Saving failed.")


def profile_session() -> Any:
    from gi.repository import WebKit
    # A private, persistent profile: a later re-sign-in after the session expires is usually one click.
    data = pathlib.Path(os.environ.get("XDG_DATA_HOME") or pathlib.Path.home() / ".local/share") / "codexbar-opencode-login"
    cache = pathlib.Path(os.environ.get("XDG_CACHE_HOME") or pathlib.Path.home() / ".cache") / "codexbar-opencode-login"
    for directory in (data, cache):
        directory.mkdir(parents=True, exist_ok=True)
        directory.chmod(0o700)
    session = WebKit.NetworkSession.new(str(data), str(cache))
    session.get_cookie_manager().set_persistent_storage(str(data / "cookies.sqlite"),
                                                       WebKit.CookiePersistentStorage.SQLITE)
    return session


def connect() -> str | None:
    """The Connect window. Returns the success message, or None if it was closed without connecting.

    Passkeys need the real browser (WebKitGTK has no WebAuthn on Linux), so the main path is: sign in to
    opencode.ai in the default browser, copy an API key, paste it here. Email and GitHub sign-ins can
    still finish in the built-in window, which saves the web session instead.
    """
    import threading

    import gi
    gi.require_version("Gtk", "4.0")
    gi.require_version("WebKit", "6.0")
    from gi.repository import Gio, GLib, Gtk, WebKit

    outcome: dict[str, str | None] = {"message": None}
    app = Gtk.Application(application_id="io.github.mseries.CodexBarOpenCodeLogin")

    def activate(application: Gtk.Application) -> None:
        window = Gtk.ApplicationWindow(application=application, title="Connect OpenCode Go",
                                       default_width=420, resizable=False)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12, margin_top=18, margin_bottom=18,
                      margin_start=18, margin_end=18)
        window.set_child(box)
        title = Gtk.Label(label="Connect OpenCode Go", xalign=0)
        title.add_css_class("title-3")
        box.append(title)
        steps = Gtk.Label(xalign=0, wrap=True, max_width_chars=48, label=(
            "1. Sign in to opencode.ai in your browser (passkeys work there).\n"
            "2. In the console, create an API key and copy it.\n"
            "3. Paste it below. CodexBar checks it before saving."))
        box.append(steps)
        open_site = Gtk.Button(label="Open opencode.ai", halign=Gtk.Align.START)
        open_site.connect("clicked", lambda *_: Gio.AppInfo.launch_default_for_uri(SIGN_IN_URL, None))
        box.append(open_site)
        entry = Gtk.PasswordEntry(show_peek_icon=True, placeholder_text="OpenCode API key")
        box.append(entry)
        status = Gtk.Label(xalign=0, wrap=True, max_width_chars=48, visible=False)
        status.add_css_class("dim-label")
        box.append(status)
        buttons = Gtk.Box(spacing=6)
        here = Gtk.Button(label="Sign in here instead", hexpand=True, halign=Gtk.Align.START,
                          tooltip_text="Email or GitHub sign-in in a built-in window (no passkeys)")
        here.add_css_class("flat")
        save = Gtk.Button(label="Connect", sensitive=False)
        save.add_css_class("suggested-action")
        buttons.append(here)
        buttons.append(save)
        box.append(buttons)
        entry.connect("changed", lambda e: save.set_sensitive(bool(e.get_text().strip())))

        def show(text: str, error: bool) -> None:
            status.set_label(text)
            status.set_visible(True)
            for css in ("error", "dim-label"):
                status.remove_css_class(css)
            status.add_css_class("error" if error else "dim-label")

        def finish(message: str) -> None:
            outcome["message"] = message
            application.quit()

        def check_key(*_args: Any) -> None:
            key = entry.get_text().strip().strip('"\'')
            if not key or any(ch.isspace() for ch in key):
                show("That doesn't look like an API key.", True)
                return
            save.set_sensitive(False)
            entry.set_sensitive(False)
            show("Checking the key with opencode.ai…", False)

            def work() -> None:
                problem = quota_error("api", {"OPENCODE_API_KEY": key}) or save_api_key(key)

                def done() -> bool:
                    if problem:
                        save.set_sensitive(True)
                        entry.set_sensitive(True)
                        show(problem, True)
                    else:
                        finish("OpenCode Go quota is now read with your API key.")
                    return False
                GLib.idle_add(done)
            threading.Thread(target=work, daemon=True).start()

        save.connect("clicked", check_key)
        entry.connect("activate", lambda *_: save.get_sensitive() and check_key())

        def sign_in_here(*_args: Any) -> None:
            session = profile_session()
            view = WebKit.WebView(network_session=session)
            web = Gtk.Window(title="Sign in to OpenCode", transient_for=window, default_width=480, default_height=720)
            web.set_child(view)
            taken = {"done": False}

            def collect(*_a: Any) -> None:
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
                    if not header or taken["done"]:
                        return
                    taken["done"] = True
                    web.close()
                    save_session(header)
                    show("Signed in. Checking quota…", False)

                    def work() -> None:
                        problem = quota_error("web")
                        GLib.idle_add(lambda: (show("Saved the sign-in, but opencode.ai rejected it: " + problem, True)
                                               if problem else finish("OpenCode Go quota is now read from your "
                                                                      "opencode.ai sign-in.")) and False)
                    threading.Thread(target=work, daemon=True).start()

                session.get_cookie_manager().get_cookies("https://opencode.ai/", None, got)

            view.connect("load-changed", lambda v, event: event == WebKit.LoadEvent.FINISHED and collect())
            view.load_uri(SIGN_IN_URL)
            web.present()

        here.connect("clicked", sign_in_here)
        window.present()

    app.connect("activate", activate)
    app.run([])
    return outcome["message"]


def main(arguments: list[str]) -> int:
    command = arguments[0] if arguments else ""
    if command == "status":
        print(json.dumps({"signedIn": signed_in()}))
        return 0
    if command == "login":
        message = connect()
        if not message:
            print("Closed before OpenCode Go was connected.")
            return 1
        print(message)
        return 0
    print("usage: codexbar-opencode-login.py login | status", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
