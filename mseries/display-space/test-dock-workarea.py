#!/usr/bin/python3
"""Integration checks against a separate headless Gala, with native Wayland clients."""
import os
import time
import subprocess
import gi

assert (os.environ.get("MSERIES_DOCK_TEST_BUS") == "1" and
        os.environ.get("GSETTINGS_BACKEND") == "keyfile"), "Use test-dock-workarea.sh first"

gi.require_version("Gtk", "4.0")
from gi.repository import Gio, GLib, Gtk

connection = Gio.bus_get_sync(Gio.BusType.SESSION, None)


def call(dest, path, interface, method, signature=None, args=None):
    params = GLib.Variant(signature, args) if signature else None
    return connection.call_sync(dest, path, interface, method, params, None, 0, 5000, None).unpack()


def pump(seconds=0.25):
    deadline = time.monotonic() + seconds
    context = GLib.MainContext.default()
    while time.monotonic() < deadline:
        while context.pending():
            context.iteration(False)
        time.sleep(0.005)


app = Gtk.Application(application_id="org.techmore.DockWorkareaTest")
app.register(None)
window = Gtk.ApplicationWindow(application=app, title="Dock Workarea Test", default_width=600, default_height=400)
entry = Gtk.Entry(placeholder_text="Focus must stay here during dock reactivation")
window.set_child(entry)
window.present()
pump(0.6)
remote = "org.gnome.Mutter.RemoteDesktop"
remote_interface = remote + ".Session"
remote_path = call(remote, "/org/gnome/Mutter/RemoteDesktop", remote, "CreateSession")[0]


def notify(method, signature=None, args=None):
    return call(remote, remote_path, remote_interface, method, signature, args)


def key(symbol, down):
    notify("NotifyKeyboardKeysym", "(ub)", (symbol, down))


def chord(symbols):
    for symbol in symbols:
        key(symbol, True)
    for symbol in reversed(symbols):
        key(symbol, False)
    pump()


def geometry():
    windows = call("org.pantheon.gala", "/org/pantheon/gala/DesktopInterface",
                   "org.pantheon.gala.DesktopIntegration", "GetWindows")[0]
    return next(props for _, props in windows if props.get("title") == "Dock Workarea Test")


def motion(dx, dy):
    notify("NotifyPointerMotionRelative", "(dd)", (float(dx), float(dy)))
    pump(0.08)


notify("Start")
try:
    entry.grab_focus()
    pump()
    assert window.is_active(), "The private typing client must start focused"
    dock_prefix = os.environ.get("MSERIES_TEST_DOCK_PREFIX", os.path.expanduser("~/.local/lib/mseries/dock"))
    for _ in range(3):
        subprocess.run([os.path.join(dock_prefix, "bin/io.elementary.dock")], check=True, timeout=5)
        pump()
        assert window.is_active(), "Dock reactivation took focus from the typing client"
        chord([ord("a")])
    assert entry.get_text() == "aaa", entry.get_text()
    print("PASS: repeated dock activation preserves keyboard focus and typed input", flush=True)
    def mode(value):
        subprocess.run(["gsettings", "set", "io.elementary.dock", "autohide-mode", value], check=True)
        pump(1.2)
    def height():
        return geometry()["height"]
    def reveal():
        motion(-10000, -10000)
        motion(800, 999)
        for i in range(15):
            motion(0, 30)
        pump(.7)
    def leave():
        motion(0, -500)
        pump(1.5)
    window.maximize()
    pump(1)
    mode("never")
    reserved = height()
    assert 850 < reserved < 1000, geometry()
    mode("always")
    assert height() == 1000, geometry()
    for i in range(3):
        reveal()
        assert height() == reserved, geometry()
        leave()
        assert height() == 1000, geometry()
    print("PASS: maximized reveal/hide repeated three times", flush=True)
    mode("overlapping-window")
    assert height() == 1000, geometry()
    reveal()
    assert height() == reserved, geometry()
    leave()
    assert height() == 1000, geometry()
    print("PASS: overlap hiding remains stable after reveal resize", flush=True)
    mode("always")
    chord([0xFFEB, 0xFF53])  # Super+Right: native half snap
    assert (geometry()["width"], height()) == (800, 1000), geometry()
    reveal()
    assert (geometry()["width"], height()) == (800, reserved), geometry()
    leave()
    assert (geometry()["width"], height()) == (800, 1000), geometry()
    print("PASS: native half snap follows visible and hidden dock", flush=True)
    for corner in range(4):
        chord([0xFFEB, [0xFF95, 0xFF9A, 0xFF9C, 0xFF9B][corner]])
        assert height() == 500, geometry()
        reveal()
        assert height() in (reserved // 2, reserved - reserved // 2), geometry()
        leave()
        assert height() == 500, geometry()
        print(f"PASS: quarter {corner + 1} follows visible and hidden dock", flush=True)
    # An app-requested resize ends the managed quarter placement.
    window.set_default_size(600, 400)
    pump()
    reveal()
    assert geometry()["width"] == 600, geometry()
    leave()
    assert geometry()["width"] == 600, geometry()
    print("PASS: manual window size is preserved", flush=True)
    window.maximize()
    pump(1)
    window.fullscreen()
    pump(1)
    mode("never")
    assert height() == 1000, geometry()
    window.unfullscreen()
    pump(1)
    assert height() == reserved, geometry()
    print("PASS: fullscreen retains the full monitor", flush=True)
    chord([0xFFEB, 0xFFE1, 0xFF53])  # Super+Shift+Right: secondary monitor
    pump()
    assert (geometry()["width"], height()) == (1200, 800), geometry()
    mode("always")
    assert height() == 800, geometry()
    reveal()
    assert height() == 800, geometry()
    leave()
    assert height() == 800, geometry()
    print("PASS: dock reserves only its monitor", flush=True)
finally:
    notify("Stop")
    window.destroy()
    app.quit()
