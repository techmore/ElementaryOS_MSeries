#!/usr/bin/env python3
"""Headless screenshots of every Orchard page (read-only; nothing is shown on a real display).

  xvfb-run -a -s "-screen 0 1400x900x24" env GSK_RENDERER=cairo XDG_STATE_HOME=$(mktemp -d) \
      python3 tools/shoot.py OUTDIR [WIDTHxHEIGHT] [dark]
"""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from orchard_incus.app import App  # noqa: E402
from gi.repository import GLib, Gtk, Gdk, Graphene  # noqa: E402

out = sys.argv[1]
w, h = (map(int, sys.argv[2].split("x")) if len(sys.argv) > 2 else (1180, 740))
dark = "dark" in sys.argv[3:]
os.makedirs(out, exist_ok=True)


def shoot(win, name):
    p = Gtk.WidgetPaintable.new(win)
    snap = Gtk.Snapshot()
    p.snapshot(snap, win.get_width(), win.get_height())
    node = snap.to_node()
    tex = win.get_native().get_renderer().render_texture(node, Graphene.Rect().init(0, 0, win.get_width(), win.get_height()))
    tex.save_to_png(os.path.join(out, name + ".png"))


def run(app):
    app.hold()
    win = app.props.active_window or None
    if win is None:
        app.activate(); win = app.props.active_window
    win.set_default_size(w, h)
    Gtk.Settings.get_default().props.gtk_application_prefer_dark_theme = dark
    steps = [("dash", None), ("inst", None), ("images", None), ("nets", None), ("pools", None), ("profiles", None)]
    def go(i=0):
        if i >= len(steps):
            if "--instance" in sys.argv:
                pass
            app.quit(); return False
        page, _ = steps[i]
        win.pages.set_visible_child_name(page)
        if page == "inst":
            rows = list(win.rows.values())
            if rows:
                win.list.select_row(rows[0]) if hasattr(win.list, "select_row") else None
        GLib.timeout_add(1800, lambda: (shoot(win, f"{i}-{page}"), go(i + 1), False)[2])
        return False
    GLib.timeout_add(2500, go)

a = App()
a.connect("activate", lambda *_: None)
a.connect("startup", lambda *_: None)
def on_act(app):
    pass
a.connect_after("activate", lambda app: run(app))
sys.exit(a.run([]))
