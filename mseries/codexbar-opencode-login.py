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


def build_connect_window(application: Any) -> Any:
    """Build the native sheet independently of authentication (also used by the render probe)."""
    import gi
    gi.require_version("Gtk", "4.0")
    gi.require_version("Granite", "7.0")
    from gi.repository import Granite, Gtk, Pango

    Granite.init()

    class ConnectWindow(Granite.Dialog):
        def __init__(self) -> None:
            super().__init__(application=application, title="Connect OpenCode Go",
                             default_width=440, resizable=False)
            self.add_css_class("cb-opencode-connect")
            css = Gtk.CssProvider()
            css.load_from_string("""
                .cb-opencode-connect .account-emblem {
                    background: linear-gradient(to bottom, @theme_base_color, @theme_bg_color);
                    border: 1px solid alpha(currentColor, 0.12); border-radius: 22px;
                    box-shadow: 0 3px 6px alpha(black, 0.08), inset 0 1px alpha(white, 0.5);
                    padding: 20px; margin: 4px 0 8px;
                }
                .cb-opencode-connect .account-heading {
                    font-size: 1.65em; font-weight: 700; letter-spacing: -0.4px;
                }
                .cb-opencode-connect .account-steps {
                    background: @theme_base_color; border: 1px solid alpha(currentColor, 0.14);
                    border-radius: 9px; box-shadow: 0 1px 2px alpha(black, 0.04);
                }
                .cb-opencode-connect .account-step { padding: 14px 16px; }
                .cb-opencode-connect .account-step-icon {
                    color: @accent_color; background: alpha(@accent_color, 0.09);
                    border-radius: 50%; padding: 9px;
                }
                .cb-opencode-connect .account-step-title { font-weight: 600; }
                .cb-opencode-connect .account-caption { font-size: 0.92em; }
                .cb-opencode-connect .account-note { font-size: 0.85em; }
            """)
            Gtk.StyleContext.add_provider_for_display(self.get_display(), css,
                                                      Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
            body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12, margin_top=24,
                           margin_bottom=18, margin_start=30, margin_end=30)
            self.get_content_area().append(body)
            emblem = Gtk.Box(halign=Gtk.Align.CENTER)
            emblem.add_css_class("account-emblem")
            emblem.append(Gtk.Image(icon_name="mseries-codexbar-opencode-symbolic", pixel_size=40))
            body.append(emblem)
            title = Gtk.Label(label="Connect OpenCode Go", justify=Gtk.Justification.CENTER, wrap=True)
            title.add_css_class("account-heading")
            body.append(title)
            subtitle = Gtk.Label(label="Bring your OpenCode usage into CodexBar.",
                                 justify=Gtk.Justification.CENTER, wrap=True, max_width_chars=40)
            subtitle.add_css_class("dim-label")
            body.append(subtitle)
            steps = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, margin_top=12, margin_bottom=4)
            steps.add_css_class("account-steps")
            body.append(steps)

            browser_row = Gtk.Box(spacing=12)
            browser_row.add_css_class("account-step")
            icon = Gtk.Image(icon_name="web-browser-symbolic", pixel_size=18, valign=Gtk.Align.START)
            icon.add_css_class("account-step-icon")
            browser_row.append(icon)
            browser_copy = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6, hexpand=True)
            label = Gtk.Label(label="Sign in with your browser", xalign=0)
            label.add_css_class("account-step-title")
            browser_copy.append(label)
            caption = Gtk.Label(label="Create an API key in the console. Passkeys work in your browser.",
                                xalign=0, wrap=True, max_width_chars=30)
            caption.add_css_class("dim-label")
            caption.add_css_class("account-caption")
            browser_copy.append(caption)
            self.open_site = Gtk.Button(label="Open opencode.ai", halign=Gtk.Align.START)
            browser_copy.append(self.open_site)
            browser_row.append(browser_copy)
            steps.append(browser_row)
            steps.append(Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL))
            key_row = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
            key_row.add_css_class("account-step")
            self.entry = Gtk.PasswordEntry(show_peek_icon=True, placeholder_text="Paste your API key",
                                          hexpand=True)
            label = Gtk.Label(label="_API key", use_underline=True, mnemonic_widget=self.entry, xalign=0)
            label.add_css_class("account-step-title")
            key_row.append(label)
            key_row.append(self.entry)
            caption = Gtk.Label(label="We'll check your key before saving it.", xalign=0, wrap=True)
            caption.add_css_class("dim-label")
            caption.add_css_class("account-caption")
            key_row.append(caption)
            steps.append(key_row)
            self.status_row = Gtk.Box(spacing=8, visible=False)
            self.spinner = Gtk.Spinner(visible=False, valign=Gtk.Align.CENTER)
            self.status_row.append(self.spinner)
            self.status = Gtk.Label(xalign=0, wrap=True, max_width_chars=40, lines=3,
                                    ellipsize=Pango.EllipsizeMode.END, selectable=True, hexpand=True)
            self.status_row.append(self.status)
            body.append(self.status_row)
            note = Gtk.Label(label="Your API key is saved on this computer.",
                             justify=Gtk.Justification.CENTER, wrap=True, max_width_chars=44)
            note.add_css_class("dim-label")
            note.add_css_class("account-note")
            body.append(note)
            self.here = Gtk.Button(label="Use built-in sign-in instead", halign=Gtk.Align.CENTER,
                                   tooltip_text="Email or GitHub sign-in in a built-in window (no passkeys)")
            self.here.add_css_class("flat")
            body.append(self.here)
            self.add_button("Cancel", Gtk.ResponseType.CANCEL)
            self.save = self.add_button("Connect", Gtk.ResponseType.ACCEPT)
            self.save.set_sensitive(False)
            self.save.add_css_class("suggested-action")
            self.set_default_response(Gtk.ResponseType.ACCEPT)
            self.entry.connect("changed", lambda e: self.save.set_sensitive(bool(e.get_text().strip())))

        def show_status(self, text: str, error: bool) -> None:
            self.status.set_label(text)
            self.status.set_tooltip_text(text)
            self.status_row.set_visible(True)
            for css in ("error", "dim-label"):
                self.status.remove_css_class(css)
            self.status.add_css_class("error" if error else "dim-label")

        def set_busy(self, busy: bool) -> None:
            self.entry.set_sensitive(not busy)
            self.here.set_sensitive(not busy)
            self.open_site.set_sensitive(not busy)
            self.save.set_sensitive(not busy and bool(self.entry.get_text().strip()))
            self.spinner.set_visible(busy)
            self.spinner.set_spinning(busy)

    return ConnectWindow()


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
        window = build_connect_window(application)
        entry, save = window.entry, window.save
        window.open_site.connect("clicked", lambda *_: Gio.AppInfo.launch_default_for_uri(SIGN_IN_URL, None))

        def show(text: str, error: bool) -> None:
            window.show_status(text, error)

        def finish(message: str) -> None:
            outcome["message"] = message
            application.quit()

        def check_key(*_args: Any) -> None:
            key = entry.get_text().strip().strip('"\'')
            if not key or any(ch.isspace() for ch in key):
                show("That doesn't look like an API key.", True)
                return
            window.set_busy(True)
            show("Checking the key with opencode.ai…", False)

            def work() -> None:
                problem = quota_error("api", {"OPENCODE_API_KEY": key}) or save_api_key(key)

                def done() -> bool:
                    if problem:
                        window.set_busy(False)
                        show(problem, True)
                        entry.grab_focus()
                    else:
                        finish("OpenCode Go quota is now read with your API key.")
                    return False
                GLib.idle_add(done)
            threading.Thread(target=work, daemon=True).start()

        def respond(_window: Any, response: int) -> None:
            if response == Gtk.ResponseType.ACCEPT:
                if save.get_sensitive():
                    check_key()
            else:
                window.close()

        window.connect("response", respond)
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

        window.here.connect("clicked", sign_in_here)
        window.present()
        entry.grab_focus()

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
