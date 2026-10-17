"""Orchard widgets and theming: CSS, small widget helpers, charts, sidebar rows."""
import re
from collections import deque  # noqa: F401

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
gi.require_version("Graphene", "1.0")
gi.require_version("Granite", "7.0")
from gi.repository import Gdk, Gio, GLib, Granite, Graphene, Gtk, Pango  # noqa: E402,F401

from .backend import (
    PERIOD,
    chart_ready as backend_chart_ready,
    chart_top,
    span_text,
    parse_progress,
    progress_text,  # noqa: E402
    BLUE,
    GREEN,
    HIST,
    MIN_GRAPHIC_CONTRAST,
    PHASES,
    RGB_FALLBACK,
    _lum,
    addrs,
    contrast,
    human,
    state_key,
)

CSS = """
.sidebar-list { background: transparent; }
.inst-row { padding: 10px 12px; border-radius: 10px; margin: 2px 8px; }
.inst-name { font-weight: 700; }
.dim { color: alpha(@theme_fg_color, .78); font-size: 90%; }
entry.error { border-color: @error_color; box-shadow: 0 0 0 1px @error_color; }
.error-text { color: @error_color; font-size: 90%; }
.cmd-block { font-family: monospace; padding: 10px 12px; border-radius: 10px; background: alpha(@theme_fg_color,.08); }
.dot { min-width: 10px; min-height: 10px; border-radius: 5px; background: alpha(@theme_fg_color,.35); }
.dot.running { background: @success_color; box-shadow: 0 0 6px alpha(@success_color,.8); }
.dot.frozen { background: @accent_color; }
.title-big { font-size: 26pt; font-weight: 800; }
.oi-badge { padding: 2px 10px; border-radius: 99px; font-weight: 700; font-size: 85%;
            background: alpha(@theme_fg_color,.12); }
.oi-badge.running { background: alpha(@success_color,.30); }
.oi-badge.vm, .oi-badge.frozen { background: alpha(@accent_color,.30); }
.oi-card { background: alpha(@theme_fg_color,.06); border-radius: 14px; padding: 14px 16px; }
.stat-val { font-size: 18pt; font-weight: 700; }
.pill { border-radius: 99px; padding: 6px 16px; }
.empty-title { font-size: 20pt; font-weight: 700; }
.status-bar { padding: 6px 14px; }
.section-title { font-weight: 800; font-size: 12pt; margin-top: 4px; }
.drop-hover { box-shadow: inset 0 0 0 2px @theme_selected_bg_color; border-radius: 12px; }
.destructive-item { color: @error_color; }
.destructive-item:hover { background: alpha(@error_color,.15); }
.list-card { background: alpha(@theme_fg_color,.06); border-radius: 12px; padding: 12px 14px; margin: 4px 0; }
"""

# ---------------------------------------------------------------- helpers
LIGHT_EXTRA = """
.error-text, .destructive-item { color: mix(@error_color, black, .55); }
entry.error { border-color: mix(@error_color, black, .4); box-shadow: 0 0 0 1px mix(@error_color, black, .4); }
"""


def lbl(text="", css=None, xalign=0.0, **kw):
    l = Gtk.Label(label=text, xalign=xalign, **kw)
    for c in (css or "").split():
        l.add_css_class(c)
    return l


def card(*children, css="oi-card", orientation=Gtk.Orientation.VERTICAL, spacing=4, **kw):
    b = Gtk.Box(orientation=orientation, spacing=spacing, **kw)
    b.add_css_class(css)
    for c in children:
        b.append(c)
    return b


class TileRow(Gtk.FlowBox):
    """Stat tiles that sit in one row when there is room and wrap to two rows when the window is narrow."""

    def __init__(self):
        super().__init__(selection_mode=Gtk.SelectionMode.NONE, homogeneous=True, column_spacing=12, row_spacing=12,
                         min_children_per_line=2, max_children_per_line=4)

    def add(self, child):
        child.set_size_request(190, -1)  # wide enough that a narrow window wraps 2+2 rather than 3+1
        self.append(child)
        child.get_parent().set_focusable(False)


def pill_button(label, icon=None, css=None, fn=None):
    b = Gtk.Button()
    row = Gtk.Box(spacing=6)
    if icon:
        row.append(Gtk.Image(icon_name=icon))
    row.append(Gtk.Label(label=label))
    b.set_child(row)
    b.set_tooltip_text(label)
    b.add_css_class("pill")
    for c in (css or "").split():
        b.add_css_class(c)
    if fn:
        b.connect("clicked", lambda _b: fn())
    return b


def legible(color, bg, minimum=MIN_GRAPHIC_CONTRAST):
    """Mix `color` toward black (light bg) or white (dark bg) until it reaches `minimum` contrast."""
    if contrast(color, bg) >= minimum:
        return color
    target = 0.0 if _lum(bg) > 0.5 else 1.0
    out = Gdk.RGBA()
    for step in range(1, 11):
        k = step / 10
        out.red, out.green, out.blue, out.alpha = (color.red + (target - color.red) * k, color.green + (target - color.green) * k,
                                                  color.blue + (target - color.blue) * k, 1.0)
        if contrast(out, bg) >= minimum:
            break
    return out


def a11y(widget, label):
    widget.update_property([Gtk.AccessibleProperty.LABEL], [label])


class Spark(Gtk.Widget):
    """Bar sparkline drawn with GTK snapshots (no cairo bridge needed)."""
    __gtype_name__ = "OrchardSpark"

    def __init__(self, color=GREEN, height=56, fixed_max=None, name="Chart", fmt=lambda v: f"{v:.0f}", floor=0.0):
        super().__init__(hexpand=True)
        self.values, self.fixed_max, self.h, self.name, self.fmt, self.floor = [], fixed_max, height, name, fmt, floor
        self.set_accessible_role(Gtk.AccessibleRole.IMG)
        a11y(self, name)
        self.token = color

    def do_measure(self, orientation, for_size):
        return (self.h, self.h, -1, -1) if orientation == Gtk.Orientation.VERTICAL else (60, 60, -1, -1)

    def set(self, values):
        self.values = list(values)
        if self.values:
            text = f"{self.name}: now {self.fmt(self.values[-1])}, peak {self.fmt(max(self.values))}, {span_text(HIST, PERIOD)}"
            self.set_tooltip_text(text)
            a11y(self, text)
        self.queue_draw()

    def text(self, snap, text, x, y, alpha, centre=False, right=False):
        layout = self.create_pango_layout(text)
        attrs = Pango.AttrList()
        attrs.insert(Pango.attr_scale_new(0.85))
        layout.set_attributes(attrs)
        col = self.get_color()
        col.alpha = alpha
        if right:
            x -= layout.get_pixel_size()[0]
        if centre:
            x -= layout.get_pixel_size()[0] / 2
            y -= layout.get_pixel_size()[1] / 2
        snap.save()
        snap.translate(Graphene.Point().init(x, y))
        snap.append_layout(layout, col)
        snap.restore()

    def do_snapshot(self, snap):
        w, h = self.get_width(), self.get_height()
        fg = self.get_color()
        grid = Gdk.RGBA()
        grid.red, grid.green, grid.blue, grid.alpha = fg.red, fg.green, fg.blue, 0.10
        for frac in (0.25, 0.5, 0.75):
            snap.append_color(grid, Graphene.Rect().init(0, h * frac, w, 1))
        v = self.values
        labels = h >= 60  # the small sidebar/dashboard sparklines stay uncluttered
        if not backend_chart_ready(v):
            if labels:
                self.text(snap, "Collecting data…", w / 2, h * 0.38, 0.55, centre=True)
            if not v:
                return
        ctx = self.get_style_context()
        _, bg = ctx.lookup_color("theme_bg_color")
        found, bar = ctx.lookup_color(self.token)
        if not found:
            bar = Gdk.RGBA()
            bar.red, bar.green, bar.blue = RGB_FALLBACK[self.token]
        bar = legible(bar, bg)
        bar.alpha = 0.9
        top = chart_top(v, self.fixed_max, self.floor)
        if labels:
            self.text(snap, self.fmt(top), 4, 2, 0.6)
            if backend_chart_ready(v):
                self.text(snap, span_text(HIST, PERIOD), w - 4, 2, 0.6, right=True)
        step = w / HIST
        bw = max(step - 1, 1)
        x = w - step * len(v)
        for val in v:
            bh = max((h - 2) * min(val / top, 1.0), 1.5 if val > 0 else 0.0)
            if bh:
                snap.append_color(bar, Graphene.Rect().init(x, h - bh, bw, bh))
            x += step


# ---------------------------------------------------------------- instance row


class JobRow(Gtk.Box):
    """Sidebar card for an instance being created: determinate progress while an image downloads, pulsing otherwise."""

    def __init__(self, name, on_cancel):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=6, margin_start=8, margin_end=8, margin_bottom=6)
        self.add_css_class("list-card")
        top = Gtk.Box(spacing=8)
        self.title = lbl(f"Creating {name}", "inst-name", hexpand=True, ellipsize=Pango.EllipsizeMode.END)
        self.cancel = Gtk.Button(icon_name="window-close-symbolic", tooltip_text="Cancel creation", has_frame=False)
        a11y(self.cancel, f"Cancel creating {name}")
        self.cancel.connect("clicked", lambda *_: on_cancel())
        top.append(self.title)
        top.append(self.cancel)
        self.bar = Gtk.ProgressBar(hexpand=True)
        a11y(self.bar, f"Creating {name}")
        self.sub = lbl("Starting…", "dim", ellipsize=Pango.EllipsizeMode.END)
        for w in (top, self.bar, self.sub):
            self.append(w)
        self.indeterminate = True
        GLib.timeout_add(220, self._pulse)

    def _pulse(self):
        if self.get_parent() is None:
            return False
        if self.indeterminate:
            self.bar.pulse()
        return True

    def feed(self, text):
        prog = parse_progress(text)
        if prog:
            label, pct, speed = prog
            self.indeterminate = False
            self.bar.set_fraction(pct / 100)
            self.sub.set_text(progress_text(label, pct, speed))
        elif text.startswith(("Launching", "Creating", "Starting")):
            self.indeterminate = True
            self.sub.set_text(text.split(" ")[0] + "…")

    def cancelling(self):
        self.cancel.set_sensitive(False)
        self.indeterminate = True
        self.sub.set_text("Cancelling…")


class Row(Gtk.ListBoxRow):
    def __init__(self, inst):
        super().__init__()
        self.name = inst["name"]
        box = Gtk.Box(spacing=12)
        box.add_css_class("inst-row")
        self.dot = Gtk.Box(valign=Gtk.Align.CENTER)
        self.dot.add_css_class("dot")
        col = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, hexpand=True)
        col.append(lbl(self.name, "inst-name", ellipsize=Pango.EllipsizeMode.END))
        self.sub = lbl("", "dim", ellipsize=Pango.EllipsizeMode.END)
        col.append(self.sub)
        self.kind = lbl("", "dim", valign=Gtk.Align.CENTER)
        box.append(self.dot)
        box.append(col)
        box.append(self.kind)
        self.set_child(box)
        self.update(inst)

    def update(self, inst):
        k = state_key(inst["status"])
        for c in ("running", "frozen"):
            self.dot.remove_css_class(c)
        if k != "stopped":
            self.dot.add_css_class(k)
        ip = (addrs(inst.get("state"), "inet") or ["—"])[0]
        self.sub.set_text(f"{inst['config'].get('image.os', inst['type'])} · {inst['status']}" + (f" · {ip}" if k == "running" else ""))
        a11y(self, f"{self.name}, {inst['status']}")
        self.kind.set_text("VM" if inst["type"] == "virtual-machine" else "")


class DashRow(Gtk.Box):
    def __init__(self, name, on_open):
        super().__init__(spacing=14)
        self.add_css_class("list-card")
        self.name = name
        self.dot = Gtk.Box(valign=Gtk.Align.CENTER)
        self.dot.add_css_class("dot")
        t = lbl(name, "inst-name", width_chars=16, max_width_chars=16, ellipsize=Pango.EllipsizeMode.END)
        self.cpu_l, self.mem_l = lbl("", "dim", xalign=1.0, width_chars=9), lbl("", "dim", xalign=1.0, width_chars=11)
        self.cpu, self.mem = Spark(GREEN, 34, floor=10, name=f"{name} CPU", fmt=lambda v: f"{v:.0f}%"), Spark(BLUE, 34, name=f"{name} memory", fmt=human)
        self.cpu.set_size_request(160, -1); self.mem.set_size_request(160, -1)
        for w in (self.dot, t, self.cpu, self.cpu_l, self.mem, self.mem_l):
            self.append(w)
        g = Gtk.GestureClick()
        g.connect("released", lambda *_: on_open(name))
        self.add_controller(g)


# ---------------------------------------------------------------- main window
