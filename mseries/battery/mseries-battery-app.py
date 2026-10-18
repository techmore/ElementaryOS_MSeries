#!/usr/bin/python3
"""Battery: elementary-style window over the history that mseries-battery-logger keeps.

Overview (health, runtime by usage), History (power and charge chart with event markers),
Sessions (each unplugged run) and Events (power steps and suspend gaps with the likely cause).
Read-only: it never changes charge limits or any other setting.
"""
import json
import math
import os
import sys
import time
import warnings

sys.path.insert(0, os.path.dirname(os.path.realpath(__file__)))
warnings.filterwarnings("ignore", category=DeprecationWarning)
import gi  # noqa: E402

gi.require_version("Gtk", "4.0")
gi.require_version("Granite", "7.0")
from gi.repository import Gio, GLib, Granite, Gtk  # noqa: E402

import battery_core as core  # noqa: E402

# elementary palette
BLUEBERRY, LIME, ORANGE, STRAWBERRY, GRAPE = (0.21, 0.54, 0.90), (0.41, 0.72, 0.14), (0.95, 0.45, 0.16), (0.78, 0.15, 0.18), (0.65, 0.44, 0.78)
RANGES = [("1 h", 3600), ("6 h", 6 * 3600), ("24 h", 86400), ("7 d", 7 * 86400)]
CSS = b"""
.card-block { padding: 12px 16px; }
.big-number { font-size: 2.6em; font-weight: 800; }
.stat-value { font-size: 1.6em; font-weight: 700; }
.chart-legend { font-size: 0.9em; }
"""


def when(ts, with_date=True):
    return time.strftime("%a %H:%M" if with_date else "%H:%M", time.localtime(ts))


def label(text, *classes, xalign=0.0, wrap=False, hexpand=False):
    widget = Gtk.Label(label=text, xalign=xalign, wrap=wrap, hexpand=hexpand)
    for name in classes:
        widget.add_css_class(name)
    return widget


def card(title, *children):
    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
    box.add_css_class("card")
    box.add_css_class("card-block")
    box.append(label(title, "dim", "caption-heading"))
    for child in children:
        box.append(child)
    return box


def stat(title, value, sub=""):
    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2, hexpand=True)
    box.add_css_class("card")
    box.add_css_class("card-block")
    box.append(label(title, "dim", "caption-heading"))
    box.append(label(value, "stat-value"))
    if sub:
        box.append(label(sub, "dim", wrap=True))
    return box


def empty(title, text):
    placeholder = Granite.Placeholder(title=title, description=text)
    placeholder.set_vexpand(True)
    return placeholder


class Chart(Gtk.DrawingArea):
    """System power (filled line, W) and charge (line, %) over a time range, with event markers."""

    def __init__(self):
        super().__init__(hexpand=True, vexpand=True, content_height=260)
        self.rows, self.events, self.start, self.end = [], [], 0, 1
        self.set_draw_func(self.draw)

    def set_data(self, rows, events, start, end):
        self.rows, self.events, self.start, self.end = rows, events, start, end
        self.queue_draw()

    def draw(self, _area, cr, width, height):
        fg = self.get_color()
        left, right, top, bottom = 44, 44, 12, 26
        plot_w, plot_h = width - left - right, height - top - bottom
        span = max(1, self.end - self.start)
        points = [r for r in self.rows if r["sys_w"] is not None]
        peak = max([12.0] + [r["sys_w"] for r in points])
        peak = math.ceil(peak / 10.0) * 10.0

        def x_of(ts):
            return left + plot_w * (ts - self.start) / span

        def y_power(watts):
            return top + plot_h * (1 - min(watts, peak) / peak)

        def y_pct(pct):
            return top + plot_h * (1 - pct / 100.0)

        cr.set_font_size(11)
        cr.set_line_width(1)
        for step in range(5):  # horizontal grid with both axes
            y = top + plot_h * step / 4
            cr.set_source_rgba(fg.red, fg.green, fg.blue, 0.12)
            cr.move_to(left, y)
            cr.line_to(left + plot_w, y)
            cr.stroke()
            cr.set_source_rgba(*BLUEBERRY, 0.9)
            cr.move_to(4, y + 4)
            cr.show_text("%d W" % (peak * (1 - step / 4)))
            cr.set_source_rgba(*LIME, 0.9)
            cr.move_to(left + plot_w + 6, y + 4)
            cr.show_text("%d%%" % (100 * (1 - step / 4)))
        cr.set_source_rgba(fg.red, fg.green, fg.blue, 0.7)  # time labels
        for step in range(5):
            ts = self.start + span * step / 4
            text = when(ts, span > 86400)
            cr.move_to(left + plot_w * step / 4 - 14, height - 6)
            cr.show_text(text)

        # shade time spent on the charger
        cr.set_source_rgba(*LIME, 0.07)
        run_start = None
        for r in self.rows + [None]:
            if r is not None and r["ac"] and run_start is None:
                run_start = r["ts"]
            elif (r is None or not r["ac"]) and run_start is not None:
                end = self.rows[-1]["ts"] if r is None else r["ts"]
                cr.rectangle(x_of(run_start), top, max(1, x_of(end) - x_of(run_start)), plot_h)
                cr.fill()
                run_start = None

        def trace(series, y_of, colour, fill):
            segment = []
            def flush():
                if len(segment) < 2:
                    segment.clear()
                    return
                cr.new_path()
                cr.move_to(x_of(segment[0][0]), y_of(segment[0][1]))
                for ts, value in segment[1:]:
                    cr.line_to(x_of(ts), y_of(value))
                cr.set_source_rgba(*colour, 1)
                cr.set_line_width(1.6)
                cr.stroke_preserve() if fill else cr.stroke()
                if fill:
                    cr.line_to(x_of(segment[-1][0]), top + plot_h)
                    cr.line_to(x_of(segment[0][0]), top + plot_h)
                    cr.close_path()
                    cr.set_source_rgba(*colour, 0.16)
                    cr.fill()
                segment.clear()
            last = None
            for ts, value in series:
                if last is not None and ts - last > core.GAP_SECONDS:
                    flush()  # asleep: do not draw a line across the gap
                segment.append((ts, value))
                last = ts
            flush()

        trace([(r["ts"], r["sys_w"]) for r in points], y_power, BLUEBERRY, True)
        trace([(r["ts"], r["pct"]) for r in self.rows if r["pct"] is not None], y_pct, LIME, False)

        for ev in self.events:  # triangles on the power line: rises in orange, drops in grape
            if ev["kind"] not in ("rise", "drop") or not self.start <= ev["ts"] <= self.end:
                continue
            x, y = x_of(ev["ts"]), y_power(ev["after_w"])
            cr.set_source_rgba(*(ORANGE if ev["kind"] == "rise" else GRAPE), 1)
            cr.move_to(x, y - 7)
            cr.line_to(x - 4, y - 1)
            cr.line_to(x + 4, y - 1)
            cr.close_path()
            cr.fill()
        if not points:
            cr.set_source_rgba(fg.red, fg.green, fg.blue, 0.6)
            cr.move_to(left + 20, top + plot_h / 2)
            cr.show_text("No samples in this range yet")


class BatteryWindow(Gtk.ApplicationWindow):
    def __init__(self, app):
        super().__init__(application=app, title="Battery", default_width=860, default_height=640)
        self.range_seconds = RANGES[1][1]
        self.conn = None
        self.stack = Gtk.Stack(transition_type=Gtk.StackTransitionType.CROSSFADE, vexpand=True)
        switcher = Gtk.StackSwitcher(stack=self.stack)
        header = Gtk.HeaderBar()
        header.set_title_widget(switcher)
        self.set_titlebar(header)
        self.overview, self.history, self.runs, self.events_box = (
            Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12) for _ in range(4))
        for box in (self.overview, self.history, self.runs, self.events_box):
            box.set_margin_top(16)
            box.set_margin_bottom(16)
            box.set_margin_start(16)
            box.set_margin_end(16)
        for name, title, box in (("overview", "Overview", self.overview), ("history", "History", self.history),
                                 ("sessions", "Sessions", self.runs), ("events", "Power events", self.events_box)):
            scroller = Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.NEVER, child=box)
            self.stack.add_titled(scroller, name, title)
        self.set_child(self.stack)

        self.chart = Chart()
        self.range_buttons = []
        self.refresh()
        GLib.timeout_add_seconds(core.SAMPLE_SECONDS, self.refresh)

    # ---- data -------------------------------------------------------------------------------
    def open(self):
        if self.conn is None:
            try:
                self.conn = core.connect(readonly=True)
            except Exception:
                return None
        return self.conn

    @staticmethod
    def clear(box):
        child = box.get_first_child()
        while child:
            nxt = child.get_next_sibling()
            box.remove(child)
            child = nxt

    def refresh(self):
        for box in (self.overview, self.history, self.runs, self.events_box):
            self.clear(box)
        conn = self.open()
        if conn is None:
            for box in (self.overview, self.history, self.runs, self.events_box):
                box.append(empty("No battery history yet", "Start the logger: systemctl --user enable --now mseries-battery-logger"))
            return True
        now = int(time.time())
        week = core.fetch(conn, now - 14 * 86400)
        self.build_overview(week, now)
        self.build_history(conn, now)
        self.build_sessions(week)
        self.build_events(conn, now)
        return True

    # ---- pages ------------------------------------------------------------------------------
    def build_overview(self, rows, now):
        health = core.battery_health()
        last = rows[-1] if rows else None
        hero = Gtk.Box(spacing=18)
        hero.add_css_class("card")
        hero.add_css_class("card-block")
        left = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2, hexpand=True)
        left.append(label("%.0f%%" % (last["pct"] if last and last["pct"] is not None else 0), "big-number"))
        state = {"Discharging": "On battery", "Charging": "Charging", "Full": "Fully charged"}.get(
            last["status"] if last else "", "Plugged in, holding charge" if last and last["ac"] else "—")
        left.append(label(state, "dim"))
        hero.append(left)
        right = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2, halign=Gtk.Align.END)
        est = core.estimate_runtime(rows)
        if est:
            right.append(label(core.fmt_hours(est["hours_left"]), "stat-value", xalign=1.0))
            right.append(label("left at %.1f W" % est["avg_w"], "dim", xalign=1.0))
        elif last and last["sys_w"] is not None:
            right.append(label("%.1f W" % last["sys_w"], "stat-value", xalign=1.0))
            right.append(label("system draw on the charger", "dim", xalign=1.0))
        hero.append(right)
        self.overview.append(hero)

        runs = core.sessions(rows)
        recent = [r for r in runs if r["avg_w"] and r["seconds"] >= 1800]
        typical = sum(r["projected_hours"] for r in recent if r["projected_hours"]) / len(recent) if recent else None
        total_h = sum(r["seconds"] for r in runs) / 3600
        row = Gtk.Box(spacing=12, homogeneous=True)
        row.append(stat("Typical full-charge runtime", core.fmt_hours(typical), "average of %d recent unplugged runs" % len(recent) if recent else "needs a 30 min unplugged run"))
        row.append(stat("Battery health", "%s%%" % health.get("health_pct", "—"),
                        "%.1f of %.1f Wh, %d cycles" % (health.get("full_wh") or 0, health.get("design_wh") or 0, health.get("cycles") or 0)))
        row.append(stat("Unplugged, 14 days", core.fmt_hours(total_h), "%d runs" % len(runs)))
        self.overview.append(row)
        if health.get("limit_pct") is not None:
            self.overview.append(label("Charging stops at %d%% (battery longevity limit)." % health["limit_pct"], "dim"))

        profile = core.usage_profile(rows)
        grid = Gtk.Grid(column_spacing=24, row_spacing=6)
        for col, head in enumerate(("Usage", "CPU load", "Time on battery", "Average draw", "Full-charge runtime")):
            grid.attach(label(head, "dim", "caption-heading"), col, 0, 1, 1)
        for i, band in enumerate(profile, start=1):
            cells = (band["band"], band["cpu_range"], core.fmt_hours(band["hours"]) if band["hours"] else "—",
                     "%.1f W" % band["avg_w"] if band["avg_w"] is not None else "—", core.fmt_hours(band["runtime_h"]))
            for col, text in enumerate(cells):
                grid.attach(label(text, "numeric" if col else "heading"), col, i, 1, 1)
        self.overview.append(card("Runtime by usage", grid))

        culprits = core.top_culprits(rows)
        if culprits:
            lines = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
            for item in culprits:
                line = Gtk.Box(spacing=12)
                line.append(label(item["name"], hexpand=True))
                line.append(label("%.1f%% of CPU" % item["avg_cpu"], "dim", "numeric"))
                lines.append(line)
            self.overview.append(card("Biggest CPU users on battery", lines))

    def build_history(self, conn, now):
        bar = Gtk.Box(spacing=0, halign=Gtk.Align.CENTER)
        bar.add_css_class("linked")
        first = None
        for text, seconds in RANGES:
            button = Gtk.ToggleButton(label=text, active=seconds == self.range_seconds)
            if first:
                button.set_group(first)
            first = first or button
            button.connect("toggled", self.on_range, seconds)
            bar.append(button)
        self.history.append(bar)
        start = now - self.range_seconds
        rows = core.fetch(conn, start, now)
        if self.range_seconds > 86400:  # thin out long ranges so drawing stays quick
            step = max(1, len(rows) // 1500)
            rows = rows[::step]
        evs = core.events(conn, start)
        self.chart.set_data(rows, evs, start, now)
        parent = self.chart.get_parent()
        if parent:
            parent.remove(self.chart)
        self.history.append(self.chart)
        legend = Gtk.Box(spacing=18, halign=Gtk.Align.CENTER)
        for text, colour in (("System power (W)", BLUEBERRY), ("Charge (%)", LIME), ("Power rise", ORANGE), ("Power drop", GRAPE)):
            item = label("● " + text, "chart-legend")
            item.set_markup('<span foreground="#%02x%02x%02x">●</span> %s' % (*[int(c * 255) for c in colour], text))
            legend.append(item)
        self.history.append(legend)
        self.history.append(label("Green shading marks time on the charger. Triangles mark sudden power changes; see Power events.", "dim", wrap=True, xalign=0.5))

    def on_range(self, button, seconds):
        if button.get_active() and seconds != self.range_seconds:
            self.range_seconds = seconds
            GLib.idle_add(self.refresh)

    def build_sessions(self, rows):
        runs = list(reversed(core.sessions(rows)))
        if not runs:
            self.runs.append(empty("No unplugged runs yet", "Unplug the charger and the app records each run on battery."))
            return
        listing = Gtk.ListBox(selection_mode=Gtk.SelectionMode.NONE)
        listing.add_css_class("boxed-list")
        for run in runs:
            line = Gtk.Box(spacing=16)
            line.set_margin_top(8)
            line.set_margin_bottom(8)
            line.set_margin_start(12)
            line.set_margin_end(12)
            when_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, hexpand=True)
            when_box.append(label(time.strftime("%a %d %b, %H:%M", time.localtime(run["start"])), "heading"))
            when_box.append(label("%s on battery · %.0f%% → %.0f%%" % (core.fmt_hours(run["seconds"] / 3600), run["pct_start"] or 0, run["pct_end"] or 0), "dim"))
            line.append(when_box)
            for value, sub in (("%.1f Wh" % run["wh_used"], "used"),
                               ("%s W" % (run["avg_w"] if run["avg_w"] is not None else "—"), "average"),
                               (core.fmt_hours(run["projected_hours"]), "full-charge runtime")):
                col = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, halign=Gtk.Align.END)
                col.append(label(value, "numeric", xalign=1.0))
                col.append(label(sub, "dim", "caption", xalign=1.0))
                line.append(col)
            listing.append(line)
        self.runs.append(listing)

    def build_events(self, conn, now):
        found = core.events(conn, now - 2 * 86400)
        if not found:
            self.events_box.append(empty("No power events", "Sudden changes in power use and sleep gaps appear here with their likely cause."))
            return
        listing = Gtk.ListBox(selection_mode=Gtk.SelectionMode.NONE)
        listing.add_css_class("boxed-list")
        for ev in found:
            if ev["kind"] == "gap":
                info = json.loads(ev["detail"])
                title = "Asleep or off for %s" % core.fmt_hours(info["seconds"] / 3600)
                sub = "Charge %.0f%% → %.0f%%%s" % (info["pct_from"] or 0, info["pct_to"] or 0,
                                                    " (standby drain)" if info["on_battery"] and (info["pct_from"] or 0) > (info["pct_to"] or 0) else "")
                trailing = ""
            else:
                title = "Power %s %.1f W → %.1f W" % ("rose" if ev["kind"] == "rise" else "dropped", ev["before_w"], ev["after_w"])
                sub = "%s · top process: %s" % (ev["detail"], ev["culprit"] or "—")
                trailing = "%+.1f W" % ev["delta_w"]
            line = Gtk.Box(spacing=12)
            line.set_margin_top(8)
            line.set_margin_bottom(8)
            line.set_margin_start(12)
            line.set_margin_end(12)
            text = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, hexpand=True)
            text.append(label(title, "heading"))
            text.append(label(sub, "dim", wrap=True))
            line.append(text)
            line.append(label(trailing or when(ev["ts"]), "numeric"))
            if trailing:
                line.append(label(when(ev["ts"]), "dim"))
            listing.append(line)
        self.events_box.append(listing)


class BatteryApp(Gtk.Application):
    def __init__(self):
        super().__init__(application_id="org.mseries.Battery", flags=Gio.ApplicationFlags.DEFAULT_FLAGS)

    def do_startup(self):
        Gtk.Application.do_startup(self)
        if hasattr(Granite, "init"):
            Granite.init()
        provider = Gtk.CssProvider()
        provider.load_from_data(CSS)
        from gi.repository import Gdk
        Gtk.StyleContext.add_provider_for_display(Gdk.Display.get_default(), provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)

    def do_activate(self):
        window = self.props.active_window or BatteryWindow(self)
        window.present()


if __name__ == "__main__":
    sys.exit(BatteryApp().run(sys.argv))
