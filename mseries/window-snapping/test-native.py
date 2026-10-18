#!/usr/bin/python3
"""Integration checks against a separate headless Gala, with native Wayland clients."""
import os
import time
import gi

assert os.environ.get("MSERIES_SNAPPING_TEST_BUS") == "1" and os.environ.get("GSETTINGS_BACKEND") == "memory", "Use test-nested.sh to isolate the desktop first"

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


app = Gtk.Application(application_id="org.techmore.SnappingTest")
app.register(None)
window = Gtk.ApplicationWindow(application=app, title="Snapping Test", default_width=600, default_height=400)
window.set_child(Gtk.Label(label="Native Wayland quarter snapping check"))
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
    return next(props for _, props in windows if props.get("title") == "Snapping Test")


def check_quarter():
    props = geometry()
    assert (props["width"], props["height"]) == (800, 500), props


def motion(dx, dy):
    notify("NotifyPointerMotionRelative", "(dd)", (float(dx), float(dy)))
    pump(0.08)


def drag_to(x, y, cancel=False):
    # Test always starts with the window at top left. Super+button moves it
    # from its interior, independently of toolkit titlebar decorations.
    motion(-10000, -10000)
    motion(300, 200)
    key(0xFFEB, True)
    notify("NotifyPointerButton", "(ib)", (272, True))
    pump(0.1)
    motion(x - 300, y - 200)
    if cancel:
        chord([0xFF1B])
    notify("NotifyPointerButton", "(ib)", (272, False))
    key(0xFFEB, False)
    pump(0.35)


notify("Start")
try:
    for corner, symbol in enumerate("uijk"):
        chord([0xFFEB, 0xFFE9, ord(symbol)])
        check_quarter()
        print(f"PASS: quarter shortcut {corner + 1}", flush=True)
    # Reset to a smaller window so a successful drag must actually resize it.
    for x, y in [(5, 5), (1595, 5), (5, 995), (1595, 995)]:
        chord([0xFFEB, 0xFFE9, ord("u")])
        window.set_default_size(600, 400)
        pump()
        assert geometry()["width"] == 600
        drag_to(x, y)
        check_quarter()
        print(f"PASS: corner drag to {x},{y}", flush=True)
    chord([0xFFEB, 0xFFE9, ord("u")])
    window.set_default_size(600, 400)
    pump()
    drag_to(1595, 995, cancel=True)
    assert geometry()["width"] == 600, geometry()
    print("PASS: Escape cancels a corner drag", flush=True)
finally:
    notify("Stop")
    window.destroy()
    app.quit()
