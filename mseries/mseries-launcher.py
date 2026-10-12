#!/usr/bin/python3
"""Command+Space app launcher: a small centered search box that filters apps as you type.

Run it again while it is open to close it. Enter launches the highlighted app;
Esc or clicking away closes it.
"""
import ctypes
import warnings
import os

# Wayland clients cannot choose their position, so run through XWayland and place the window.
# Launched apps must not inherit the XWayland settings below, so remember the originals.
ORIGINAL_ENV = {name: os.environ.get(name) for name in ("GDK_BACKEND", "GDK_SCALE")}
os.environ["GDK_BACKEND"] = "x11"
warnings.filterwarnings("ignore", category=DeprecationWarning)


def display_scale():
    """XWayland windows are unscaled, so GTK needs the compositor's integer scale."""
    try:
        from gi.repository import Gio
        reply = Gio.DBusProxy.new_for_bus_sync(
            Gio.BusType.SESSION, Gio.DBusProxyFlags.NONE, None, "org.gnome.Mutter.DisplayConfig",
            "/org/gnome/Mutter/DisplayConfig", "org.gnome.Mutter.DisplayConfig", None
        ).call_sync("GetCurrentState", None, Gio.DBusCallFlags.NONE, 1000, None).unpack()
        logical = reply[2]
        primary = next((m for m in logical if m[4]), logical[0])
        return max(1, round(primary[2]))
    except Exception:
        return 1


os.environ.setdefault("GDK_SCALE", str(display_scale()))

import gi
gi.require_version("Gdk", "4.0")
gi.require_version("GdkX11", "4.0")
gi.require_version("Gtk", "4.0")
from gi.repository import Gdk, GdkX11, Gio, GLib, Gtk

MAX_RESULTS = 8
LOG = os.path.expanduser("~/.cache/mseries-launcher.log")


def log(message):
    """Append a timestamped line so an unexpected close can be explained afterwards."""
    try:
        os.makedirs(os.path.dirname(LOG), exist_ok=True)
        if os.path.exists(LOG) and os.path.getsize(LOG) > 100_000:
            os.remove(LOG)
        with open(LOG, "a") as f:
            f.write(f"{GLib.DateTime.new_now_local().format('%H:%M:%S.%f')} pid={os.getpid()} {message}\n")
    except OSError:
        pass

DOUBLE_PRESS_MS = 400  # activations closer together than this are one key press
HEIGHT_FROM_BOTTOM = 0.80  # window top edge sits this fraction of the screen height above the bottom

CSS = b"""
window.mseries { background: transparent; box-shadow: none; }
.mseries-card { background: #1c1c20; color: #f2f2f5; border-radius: 18px; padding: 12px;
                border: 1px solid rgba(255,255,255,0.08); }
.mseries-card entry { background: rgba(255,255,255,0.07); color: #f2f2f5; border: none;
                      border-radius: 12px; min-height: 40px; font-size: 16px; box-shadow: none; }
.mseries-card list { background: transparent; }
.mseries-card row { border-radius: 10px; padding: 6px 8px; margin-top: 2px; color: #f2f2f5; }
.mseries-card row:selected { background: rgba(255,255,255,0.14); }
"""


def score(app, query):
    name = (app.get_name() or "").lower()
    if name.startswith(query):
        return 0
    if any(word.startswith(query) for word in name.split()):
        return 1
    if query in name:
        return 2
    extra = " ".join(filter(None, [app.get_generic_name(), app.get_description(),
                                  " ".join(app.get_keywords() or []),
                                  app.get_executable()])).lower()
    return 3 if query in extra else None


class Launcher(Gtk.Application):
    def __init__(self):
        super().__init__(application_id="org.mseries.Launcher")
        self.win = None

    def do_activate(self):
        if self.win:
            # One key press can start the launcher twice within milliseconds (both bindings
            # fire), so only a later press counts as "toggle closed".
            if (GLib.get_monotonic_time() - self.opened_at) / 1000 < DOUBLE_PRESS_MS:
                log("ignored: duplicate activation right after opening")
                return
            log("quit: second activation toggled it closed")
            self.quit()
            return
        log("opened")
        self.opened_at = GLib.get_monotonic_time()
        self.apps = [a for a in Gio.AppInfo.get_all() if a.should_show()]
        self.win = win = Gtk.ApplicationWindow(application=self, title="Launcher")
        win.set_decorated(False)
        win.add_css_class("mseries")
        provider = Gtk.CssProvider()
        provider.load_from_data(CSS)
        Gtk.StyleContext.add_provider_for_display(Gdk.Display.get_default(), provider,
                                                  Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        win.set_resizable(False)
        win.set_default_size(620, -1)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        box.add_css_class("mseries-card")
        box.set_spacing(6)
        self.entry = Gtk.SearchEntry(placeholder_text="Search apps", hexpand=True)
        self.entry.connect("search-changed", self.refilter)
        self.entry.connect("activate", lambda *_: self.launch(self.list.get_selected_row()))
        self.list = Gtk.ListBox(selection_mode=Gtk.SelectionMode.SINGLE)
        self.list.connect("row-activated", lambda _l, row: self.launch(row))
        box.append(self.entry)
        box.append(self.list)
        win.set_child(box)

        keys = Gtk.EventControllerKey()
        keys.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
        keys.connect("key-pressed", self.on_key)
        win.add_controller(keys)
        win.connect("notify::is-active", self.on_active)
        self.refilter()
        win.present()
        self.entry.grab_focus()
        GLib.timeout_add(60, self.place)

    def place(self):
        """Center horizontally and put the top edge HEIGHT_FROM_BOTTOM up from the bottom."""
        surface = self.win.get_surface()
        if not isinstance(surface, GdkX11.X11Surface):
            return False
        monitor = self.win.get_display().get_monitor_at_surface(surface)
        geo, scale = monitor.get_geometry(), monitor.get_scale_factor()
        x = geo.x + (geo.width - self.win.get_width()) // 2
        y = geo.y + int(geo.height * (1 - HEIGHT_FROM_BOTTOM))
        xlib = ctypes.CDLL("libX11.so.6")
        xlib.XOpenDisplay.restype = ctypes.c_void_p
        display = xlib.XOpenDisplay(None)
        if display:
            xlib.XMoveWindow(ctypes.c_void_p(display), ctypes.c_ulong(surface.get_xid()),
                             x * scale, y * scale)
            xlib.XFlush(ctypes.c_void_p(display))
            xlib.XCloseDisplay(ctypes.c_void_p(display))
        return False

    def on_active(self, win, _pspec):
        # Debounce: the compositor can briefly flip focus while mapping the window.
        log(f"focus active={win.is_active()}")
        if win.is_active():
            self.ready = True
        elif self.ready:
            GLib.timeout_add(250, self.close_if_inactive)

    def close_if_inactive(self):
        if not self.win.is_active():
            log("quit: lost focus")
            self.quit()
        return False

    ready = False
    opened_at = 0

    def on_key(self, _ctl, keyval, _code, _state):
        if keyval == Gdk.KEY_Escape:
            log("quit: Escape")
            self.quit()
        elif keyval in (Gdk.KEY_Down, Gdk.KEY_Up):
            row = self.list.get_selected_row()
            index = (row.get_index() if row else -1) + (1 if keyval == Gdk.KEY_Down else -1)
            target = self.list.get_row_at_index(max(index, 0))
            if target:
                self.list.select_row(target)
            return True
        return False

    def refilter(self, *_):
        query = self.entry.get_text().strip().lower()
        while (child := self.list.get_first_child()):
            self.list.remove(child)
        if query:
            ranked = sorted(((s, a.get_name().lower(), a) for a in self.apps
                             if (s := score(a, query)) is not None), key=lambda t: t[:2])
            matches = [a for _s, _n, a in ranked[:MAX_RESULTS]]
        else:
            matches = []
        for app in matches:
            row = Gtk.ListBoxRow()
            row.app = app
            line = Gtk.Box(spacing=10)
            icon = Gtk.Image.new_from_gicon(app.get_icon() or Gio.ThemedIcon.new("application-default-icon"))
            icon.set_pixel_size(32)
            line.append(icon)
            line.append(Gtk.Label(label=app.get_name(), xalign=0))
            row.set_child(line)
            self.list.append(row)
        first = self.list.get_row_at_index(0)
        if first:
            self.list.select_row(first)

    def launch(self, row):
        if row is None:
            return
        try:
            context = Gdk.Display.get_default().get_app_launch_context()
            for name, value in ORIGINAL_ENV.items():
                if value is None:
                    context.unsetenv(name)
                else:
                    context.setenv(name, value)
            row.app.launch([], context)
        except GLib.Error as err:
            print(f"Could not launch {row.app.get_name()}: {err.message}")
        log(f"quit: launched {row.app.get_name()}")
        self.quit()


raise SystemExit(Launcher().run())
