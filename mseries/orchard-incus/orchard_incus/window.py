"""Orchard main window: pages, instance tabs, dialogs, jobs and the Incus event stream."""
import atexit
import csv
import codecs
import json
import os
import posixpath
import re
import signal
import subprocess
import threading
import time
from collections import deque

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
gi.require_version("Graphene", "1.0")
gi.require_version("Granite", "7.0")
from gi.repository import Gdk, Gio, GLib, Granite, Graphene, Gtk, Pango  # noqa: E402,F401

from . import backend  # noqa: E402
from .runtime import LatestRead, OutputMailbox
from .backend import (  # noqa: E402
    ARCH,
    BLUE,
    GREEN,
    HIST,
    IDLE_PERIOD,
    PERIOD,
    PRESETS,
    PROGRESS_RE,
    SAFETY_PERIOD,
    addrs,
    human,
    last,
    state_key,
    valid_name,
)
from .ui import (  # noqa: E402
    CSS,
    DashRow,
    JobRow,
    LIGHT_EXTRA,
    Row,
    Spark,
    TileRow,
    a11y,
    card,
    lbl,
    pill_button,
)

APP_ID = "io.github.techmore.OrchardIncus"

TERMINAL = "io.elementary.terminal"

STATE_FILE = os.path.join(GLib.get_user_state_dir(), "orchard-incus", "state.json")


class Window(Gtk.ApplicationWindow):
    def __init__(self, app):
        self.state = self.load_state()
        super().__init__(application=app, title="Orchard", default_width=self.state.get("w", 1180), default_height=self.state.get("h", 740))
        self.set_size_request(780, 480)
        if self.state.get("max"):
            self.maximize()
        self.data, self.rows, self.dash_rows = {}, {}, {}
        self._dashboard_rendering = False
        self.select_after_refresh = None
        self.rename_output = None
        self.hist, self.cur, self.busy = {}, None, set()
        self.ok, self.fails, self.last_refresh, self.restored = True, 0, 0.0, False
        self.monitor_ok, self.mon_proc, self.mon_thread, self.closing = False, None, None, False
        self.last_sample, self.jobs, self._rf_pending, self.cleaning = 0.0, {}, False, set()
        self.sources = set()
        self.reads = {}
        self.instance_writes = {}
        self.output = {}
        self.monitor_lock = threading.Lock()
        self._listing = self._refresh_again = self._checking = False
        self._address_followups = set()
        atexit.register(self.stop_monitor)
        css, gtk_settings = Gtk.CssProvider(), Gtk.Settings.get_default()
        def load_css(*_):
            dark = gtk_settings.props.gtk_application_prefer_dark_theme
            css.load_from_string(CSS + ("" if dark else LIGHT_EXTRA))
        load_css()
        self._theme_handler = gtk_settings.connect("notify::gtk-application-prefer-dark-theme", load_css)
        self._css = css
        Gtk.StyleContext.add_provider_for_display(Gdk.Display.get_default(), css, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)

        # header
        hb = Gtk.HeaderBar()
        self.set_titlebar(hb)
        new = Gtk.Button(label="New Instance")
        new.add_css_class("suggested-action")
        new.connect("clicked", self.on_new)
        self.new_btn = new
        hb.pack_start(new)
        self.pages = Gtk.Stack(transition_type=Gtk.StackTransitionType.CROSSFADE, vexpand=True)
        sw = Gtk.StackSwitcher(stack=self.pages)
        self.switcher = sw
        hb.set_title_widget(sw)
        refresh = Gtk.Button(icon_name="view-refresh-symbolic", tooltip_text="Refresh (F5)")
        a11y(refresh, "Refresh")
        refresh.connect("clicked", lambda *_: self.refresh_all())
        hb.pack_end(refresh)
        self.refresh_spinner = Gtk.Spinner(tooltip_text="Refreshing Incus", visible=False)
        hb.pack_end(self.refresh_spinner)
        menu = Gtk.MenuButton(icon_name="open-menu-symbolic", tooltip_text="Application menu")
        a11y(menu, "Application menu")
        menu_model = Gio.Menu()
        menu_model.append("Keyboard shortcuts", "win.shortcuts")
        menu.set_menu_model(menu_model)
        hb.pack_end(menu)
        self.search = Gtk.SearchEntry(placeholder_text="Find instance…", tooltip_text="Search names, images, status and IPv4 (Ctrl+F)", width_chars=11)
        a11y(self.search, "Filter instances")
        self.search.connect("search-changed", lambda *_: self.filter_instances())
        self.search.connect("stop-search", lambda *_: (self.search.set_text(""), self.list.grab_focus()))

        self.pages.add_titled(self.build_dashboard(), "dash", "Dashboard")
        self.pages.add_titled(self.build_instances(), "inst", "Instances")
        self.lists = {}
        for key, title, fn in [("images", "Images", self.fill_images), ("nets", "Networks", self.fill_nets),
                               ("pools", "Storage", self.fill_pools), ("profiles", "Profiles", self.fill_profiles)]:
            lb = Gtk.ListBox(selection_mode=Gtk.SelectionMode.NONE)
            lb.add_css_class("sidebar-list")
            sc = Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.NEVER)
            inner = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, margin_top=18, margin_bottom=18, margin_start=28, margin_end=28)
            inner.append(lbl(title, "title-big", margin_bottom=10))
            inner.append(lb)
            sc.set_child(inner)
            self.lists[key] = (lb, fn)
            self.pages.add_titled(sc, key, title)
        self.pages.connect("notify::visible-child-name", lambda *_: (self.load_page(), self.sync_search(), self.render_dashboard()))

        self.status = lbl("", "dim status-bar", wrap=True, selectable=True)
        self.status.set_accessible_role(Gtk.AccessibleRole.STATUS)
        main = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        main.append(self.pages)
        main.append(self.status)
        self.toast = Granite.Toast(title="", halign=Gtk.Align.CENTER, valign=Gtk.Align.END, margin_bottom=36)
        ov = Gtk.Overlay(child=main)
        ov.add_overlay(self.toast)
        self.root = Gtk.Stack(transition_type=Gtk.StackTransitionType.CROSSFADE)
        self.root.add_named(ov, "app")
        self.root.add_named(self.build_problem(), "problem")
        self.set_child(self.root)
        if not Gtk.Settings.get_default().props.gtk_enable_animations:
            for st in (self.root, self.pages):
                st.set_transition_type(Gtk.StackTransitionType.NONE)
        self.connect("close-request", self.on_close)
        self.connect("notify::is-active", lambda *_: self.is_active() and self.ok and self.refresh())
        saved = self.state.get("page")
        if saved in ("dash", "inst", "images", "nets", "pools", "profiles"):
            self.pages.set_visible_child_name(saved)
        self.pages.connect("notify::visible-child-name", lambda *_: self.save_state())

        for name, fn, accel in [("new", self.on_new, "<primary>n"), ("refresh", lambda *_: self.refresh_all(), "F5"),
                                ("search", lambda *_: self.focus_search(), "<primary>f"),
                                ("instances", lambda *_: self.pages.set_visible_child_name("inst"), "<primary>2"),
                                ("dashboard", lambda *_: self.pages.set_visible_child_name("dash"), "<primary>1"),
                                ("shortcuts", self.show_shortcuts, "<primary>question")]:
            a = Gio.SimpleAction.new(name, None)
            a.connect("activate", lambda _a, _p, f=fn: f())
            self.add_action(a)
            app.set_accels_for_action(f"win.{name}", [accel])

        self.name_controls()
        self.sync_search()
        self.check_incus()
        self.later(PERIOD, self.tick, repeat=True, seconds=True)
        self.later(10, lambda: self.ok and self.is_active() and self.load_page(auto=True), repeat=True, seconds=True)

    def later(self, delay, fn, repeat=False, seconds=False):
        """Own every window timer so closing the window stops all polling."""
        if self.closing:
            return 0
        source = 0
        def fire():
            if not repeat:
                self.sources.discard(source)
            if self.closing:
                return False
            fn()
            return repeat
        add = GLib.timeout_add_seconds if seconds else GLib.timeout_add
        source = add(delay, fire)
        self.sources.add(source)
        return source

    def show_shortcuts(self, *_):
        dialog, box = self.dialog("Keyboard shortcuts")
        for title, key in (("New instance", "Ctrl+N"), ("Find instance", "Ctrl+F"),
                           ("Dashboard", "Ctrl+1"), ("Instances", "Ctrl+2"),
                           ("Refresh", "F5"), ("Clear search", "Esc"),
                           ("Instance actions", "Menu / Shift+F10"), ("Keyboard shortcuts", "Ctrl+?")):
            row = Gtk.Box(spacing=24)
            row.append(lbl(title, hexpand=True))
            row.append(lbl(key, "dim"))
            box.append(row)
        dialog.add_button("Close", Gtk.ResponseType.CLOSE)
        dialog.connect("response", lambda d, _r: d.destroy())
        dialog.present()

    # ------------------------------------------------------ dashboard
    def sync_search(self):
        """The filter only filters instances, so it only shows on the Instances page."""
        self.search.set_visible(self.pages.get_visible_child_name() == "inst")

    def focus_search(self):
        self.pages.set_visible_child_name("inst")
        self.search.grab_focus()

    def name_controls(self):
        """Explicit accessible names: placeholder text alone isn't reliably announced, and some controls have none."""
        for widget, name in ((self.fentry, "Folder path"), (self.fw_listen, "Host port"), (self.fw_connect, "Instance port"),
                             (self.fw_proto, "Protocol"), (self.sh_host, "Host folder to share"), (self.sh_path, "Mount path inside the instance"),
                             (self.cmd, "Command to run in the instance"), (self.snap_name, "Snapshot name, optional"),
                             (self.set_cpu, "CPU limit in cores"), (self.set_mem, "Memory limit"), (self.set_auto, "Start on boot")):
            a11y(widget, name)

    def build_dashboard(self):
        sc = self.dash_scroller = Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.NEVER)
        sc.get_vadjustment().connect("value-changed", lambda *_: self.render_dashboard())
        d = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16, margin_top=22, margin_bottom=22, margin_start=28, margin_end=28)
        d.append(lbl("Dashboard", "title-big"))
        tiles = TileRow()
        self.tile = {}
        for k, t in [("run", "Running"), ("cpu", "CPU"), ("mem", "Memory"), ("proc", "Processes")]:
            self.tile[k] = lbl("—", "stat-val")
            tiles.add(card(lbl(t, "dim"), self.tile[k]))
        d.append(tiles)
        charts = Gtk.Box(spacing=12, homogeneous=True)
        self.tot_cpu, self.tot_mem = Spark(GREEN, 90, floor=10, name="Total CPU", fmt=lambda v: f"{v:.0f}%"), Spark(BLUE, 90, name="Total memory", fmt=human)
        charts.append(card(lbl("Total CPU % (all instances)", "dim"), self.tot_cpu))
        charts.append(card(lbl("Total memory", "dim"), self.tot_mem))
        d.append(charts)
        d.append(lbl("Instances", "section-title"))
        self.dash_list = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        d.append(self.dash_list)
        self.dash_empty = Granite.Placeholder(title="No instances yet", description="Create a container or VM to see live CPU and memory here.",
                                              icon=Gio.ThemedIcon.new("utilities-terminal-symbolic"), visible=False)
        self.dash_empty.append_button(Gio.ThemedIcon.new("list-add-symbolic"), "New Instance", "Launch a container or VM from an image").connect("clicked", self.on_new)
        d.append(self.dash_empty)
        sc.set_child(d)
        self.tot = {"cpu": deque(maxlen=HIST), "mem": deque(maxlen=HIST)}
        return sc

    # ------------------------------------------------------ instances page
    def build_instances(self):
        self.list = Gtk.ListBox(selection_mode=Gtk.SelectionMode.SINGLE)
        self.list.add_css_class("sidebar-list")
        self.list.set_filter_func(lambda r: self.search.get_text().casefold().strip() in r.search_text)
        self.list.set_sort_func(lambda a, b: (a.name > b.name) - (a.name < b.name))
        self.list.connect("row-selected", self.on_select)
        self.list.connect("row-activated", self.on_select)
        a11y(self.list, "Instances")
        rc = Gtk.GestureClick(button=3)
        rc.connect("pressed", self.on_row_menu)
        self.list.add_controller(rc)
        kc = Gtk.EventControllerKey()
        kc.connect("key-pressed", self.on_list_key)
        self.list.add_controller(kc)
        self.summary = lbl("", "dim", margin_start=16, margin_top=10, margin_bottom=6)
        side = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, width_request=240)
        self.search.set_margin_start(12)
        self.search.set_margin_end(12)
        self.search.set_margin_top(10)
        side.append(self.search)
        side.append(self.summary)
        self.job_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        side.append(self.job_box)
        sc = Gtk.ScrolledWindow(vexpand=True, hscrollbar_policy=Gtk.PolicyType.NEVER)
        sc.set_child(self.list)
        self.no_matches = lbl("No matching instances", "dim", wrap=True, margin_start=16, margin_end=16, margin_top=12)
        self.no_matches.set_visible(False)
        side.append(self.no_matches)
        side.append(sc)

        self.stack = Gtk.Stack(hexpand=True, transition_type=Gtk.StackTransitionType.CROSSFADE)
        empty = Granite.Placeholder(title="No instance selected", description="Pick one on the left, or create a container or VM (Ctrl+N).",
                                    icon=Gio.ThemedIcon.new("utilities-terminal-symbolic"))
        self.stack.add_named(empty, "empty")
        self.stack.add_named(self.build_detail(), "detail")
        return Gtk.Paned(start_child=side, end_child=self.stack, shrink_start_child=False, resize_start_child=False)

    def filter_instances(self):
        self.list.invalidate_filter()
        q = self.search.get_text().casefold().strip()
        visible = [r for r in self.rows.values() if q in r.search_text]
        self.no_matches.set_visible(bool(self.data) and not visible)
        # Keep the detail aligned with what keyboard and screen-reader users see.
        selected = self.list.get_selected_row()
        if q and (selected is None or selected not in visible):
            self.list.select_row(visible[0] if visible else None)

    def build_detail(self):
        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14, margin_top=22, margin_bottom=14, margin_start=20, margin_end=20)
        top = Gtk.Box(spacing=12)
        self.d_title = lbl("", "title-big", ellipsize=Pango.EllipsizeMode.END)
        self.d_state = lbl("", "oi-badge", valign=Gtk.Align.CENTER)
        self.d_type = lbl("", "oi-badge", valign=Gtk.Align.CENTER)
        for w in (self.d_title, self.d_state, self.d_type):
            top.append(w)
        outer.append(top)
        self.d_sub = lbl("", "dim")
        outer.append(self.d_sub)

        actions = Gtk.FlowBox(selection_mode=Gtk.SelectionMode.NONE, column_spacing=8, row_spacing=8, max_children_per_line=12,
                              homogeneous=False, halign=Gtk.Align.START)
        self.btn = {}
        for key, label, icon, fn, css in [
            ("start", "Start", "media-playback-start-symbolic", lambda: self.act("start"), ""),
            ("stop", "Stop", "media-playback-stop-symbolic", lambda: self.act("stop"), ""),
            ("restart", "Restart", "view-refresh-symbolic", lambda: self.act("restart"), ""),
            ("pause", "Pause", "media-playback-pause-symbolic", self.toggle_pause, ""),
            ("shell", "Shell", "utilities-terminal-symbolic", self.shell, ""),
            ("snap", "Snapshot", "camera-photo-symbolic", self.snapshot, ""),
        ]:
            self.btn[key] = pill_button(label, icon, css, fn)
            actions.append(self.btn[key])
            self.btn[key].get_parent().set_focusable(False)
        more = Gtk.MenuButton(icon_name="view-more-symbolic", tooltip_text="More actions")
        a11y(more, "More actions")
        more.add_css_class("pill")
        pop = Gtk.Popover()
        pb = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        for t, fn in [("Console…", self.console), ("Clone…", self.clone), ("Rename…", self.rename), ("Copy IPv4 address", self.copy_ip), ("Export backup…", self.export_backup)]:
            b = Gtk.Button(label=t, has_frame=False, halign=Gtk.Align.FILL)
            b.get_child().set_halign(Gtk.Align.START)
            b.connect("clicked", lambda _b, f=fn: (pop.popdown(), f()))
            pb.append(b)
            if t == "Console…":
                self.console_button = b
        pb.append(Gtk.Separator(margin_top=4, margin_bottom=4))
        dele = Gtk.Button(label="Delete…", has_frame=False, halign=Gtk.Align.FILL)
        dele.get_child().set_halign(Gtk.Align.START)
        dele.add_css_class("destructive-item")
        dele.connect("clicked", lambda _b: (pop.popdown(), self.delete()))
        self.btn["delete"] = dele
        pb.append(dele)
        pop.set_child(pb)
        more.set_popover(pop)
        self.btn["more"] = more
        actions.append(more)
        more.get_parent().set_focusable(False)
        outer.append(actions)

        self.tabs = Gtk.Stack(vexpand=True, transition_type=Gtk.StackTransitionType.CROSSFADE)
        ts = Gtk.StackSwitcher(stack=self.tabs, halign=Gtk.Align.START)
        outer.append(ts)
        outer.append(self.tabs)
        self.tabs.add_titled(self.build_overview(), "ov", "Overview")
        self.tabs.add_titled(self.build_snapshots(), "sn", "Snapshots")
        self.tabs.add_titled(self.build_exec(), "ex", "Run")
        self.tabs.add_titled(self.build_files(), "fi", "Files")
        self.tabs.add_titled(self.build_devices(), "de", "Devices")
        self.tabs.add_titled(self.build_settings(), "se", "Settings")
        self.tabs.connect("notify::visible-child-name", lambda *_: (self.load_tab(), self.save_state()))
        if not Gtk.Settings.get_default().props.gtk_enable_animations:
            self.tabs.set_transition_type(Gtk.StackTransitionType.NONE)
        return outer

    def build_overview(self):
        sc = Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.NEVER, vexpand=True)
        d = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14, margin_end=6)
        stats = TileRow()
        self.stat = {}
        for k, t in [("mem", "Memory"), ("cpu", "CPU"), ("disk", "Disk"), ("proc", "Processes")]:
            self.stat[k] = lbl("—", "stat-val")
            stats.add(card(lbl(t, "dim"), self.stat[k]))
        d.append(stats)
        charts = Gtk.Box(spacing=12, homogeneous=True)
        self.d_cpu, self.d_mem = Spark(GREEN, 70, floor=10, name="CPU", fmt=lambda v: f"{v:.0f}%"), Spark(BLUE, 70, name="Memory", fmt=human)
        charts.append(card(lbl("CPU %", "dim"), self.d_cpu))
        charts.append(card(lbl("Memory", "dim"), self.d_mem))
        d.append(charts)
        grid = Gtk.Grid(row_spacing=8, column_spacing=24)
        grid.add_css_class("oi-card")
        self.info = {}
        for i, (k, t) in enumerate([("image", "Image"), ("ipv4", "IPv4"), ("ipv6", "IPv6"), ("mac", "MAC"),
                                    ("arch", "Architecture"), ("created", "Created"), ("pid", "PID")]):
            grid.attach(lbl(t, "dim"), 0, i, 1, 1)
            self.info[k] = lbl("—", selectable=True, hexpand=True, wrap=True)
            grid.attach(self.info[k], 1, i, 1, 1)
        d.append(grid)
        d.append(lbl("Recent log", "dim"))
        self.log = Gtk.TextView(editable=False, monospace=True, left_margin=10, top_margin=8, bottom_margin=8, wrap_mode=Gtk.WrapMode.WORD_CHAR)
        self.log.add_css_class("oi-card")
        d.append(self.log)
        sc.set_child(d)
        return sc

    def build_snapshots(self):
        d = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        bar = Gtk.Box(spacing=8)
        self.snap_name = Gtk.Entry(placeholder_text="Snapshot name (optional)", hexpand=True)
        bar.append(self.snap_name)
        bar.append(pill_button("Create snapshot", "camera-photo-symbolic", "suggested-action", self.snapshot))
        d.append(bar)
        sc = Gtk.ScrolledWindow(vexpand=True, hscrollbar_policy=Gtk.PolicyType.NEVER)
        self.snap_list = Gtk.ListBox(selection_mode=Gtk.SelectionMode.NONE)
        self.snap_list.add_css_class("sidebar-list")
        sc.set_child(self.snap_list)
        d.append(sc)
        return d

    def build_exec(self):
        d = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        self.vm_agent_hint = lbl("VM commands and file access require the Incus guest agent. Initial boot may take a moment; Console in More actions works without the agent.",
                                 "dim", wrap=True, visible=False)
        d.append(self.vm_agent_hint)
        bar = Gtk.Box(spacing=8)
        self.cmd = Gtk.Entry(placeholder_text="Command to run inside the instance, e.g. uname -a", hexpand=True)
        self.cmd.connect("activate", lambda *_: self.run_cmd())
        bar.append(self.cmd)
        bar.append(pill_button("Run", "media-playback-start-symbolic", "suggested-action", self.run_cmd))
        self.cmd_stop = pill_button("Stop", "media-playback-stop-symbolic", None, self.stop_cmd)
        self.cmd_stop.set_sensitive(False)
        bar.append(self.cmd_stop)
        bar.append(pill_button("Clear", None, None, lambda: self.exec_out.get_buffer().set_text("")))
        d.append(bar)
        self.exec_out = Gtk.TextView(editable=False, monospace=True, left_margin=10, top_margin=8, bottom_margin=8, wrap_mode=Gtk.WrapMode.WORD_CHAR)
        # Output is read-only: GTK's default undo log would retain trimmed text.
        self.empty_exec_buf = Gtk.TextBuffer(enable_undo=False)
        self.exec_out.set_buffer(self.empty_exec_buf)
        self.exec_out.add_css_class("oi-card")
        sc = Gtk.ScrolledWindow(vexpand=True)
        sc.set_child(self.exec_out)
        self.exec_sc = sc
        d.append(sc)
        self.exec_bufs, self.exec_proc = {}, {}
        return d

    def build_files(self):
        d = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        bar = Gtk.Box(spacing=8)
        up = Gtk.Button(icon_name="go-up-symbolic", tooltip_text="Parent folder")
        a11y(up, "Parent folder")
        up.connect("clicked", lambda *_: self.go_path(posixpath.dirname(self.fpath.rstrip("/")) or "/"))
        bar.append(up)
        self.fentry = Gtk.Entry(hexpand=True, text="/")
        self.fentry.connect("activate", lambda *_: self.go_path(self.fentry.get_text().strip() or "/"))
        bar.append(self.fentry)
        bar.append(pill_button("Download", "document-save-symbolic", None, self.pull_selected))
        bar.append(pill_button("Upload", "document-open-symbolic", None, self.push_file))
        d.append(bar)
        self.fpath, self.fnames = "/", {}
        self.flist = Gtk.ListBox(selection_mode=Gtk.SelectionMode.SINGLE)
        self.flist.add_css_class("sidebar-list")
        self.flist.connect("row-activated", self.on_file_activate)
        sc = Gtk.ScrolledWindow(vexpand=True, hscrollbar_policy=Gtk.PolicyType.NEVER)
        sc.set_child(self.flist)
        d.append(sc)
        target = Gtk.DropTarget.new(Gdk.FileList, Gdk.DragAction.COPY)
        target.connect("drop", self.on_files_dropped)
        target.connect("enter", lambda t, x, y: (self.flist.add_css_class("drop-hover"), Gdk.DragAction.COPY)[1])
        target.connect("leave", lambda t: self.flist.remove_css_class("drop-hover"))
        d.add_controller(target)
        return d

    def build_devices(self):
        d = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        self.dev_list = Gtk.ListBox(selection_mode=Gtk.SelectionMode.NONE)
        self.dev_list.add_css_class("sidebar-list")
        d.append(self.dev_list)
        fw = Gtk.Box(spacing=8)
        self.fw_listen = Gtk.Entry(placeholder_text="Host port", width_chars=7, hexpand=True)
        self.fw_connect = Gtk.Entry(placeholder_text="Instance port", width_chars=7, hexpand=True)
        self.fw_proto = Gtk.DropDown.new_from_strings(["tcp", "udp"])
        for w in (self.fw_listen, lbl("→", "dim"), self.fw_connect, self.fw_proto):
            fw.append(w)
        forward = pill_button("Add forward", "network-transmit-symbolic", "suggested-action", self.add_forward)
        forward.set_halign(Gtk.Align.END)
        sh = Gtk.Box(spacing=8)
        self.sh_host = Gtk.Entry(placeholder_text="Host folder", hexpand=True, width_chars=10)
        pick = Gtk.Button(icon_name="folder-open-symbolic", tooltip_text="Choose folder")
        a11y(pick, "Choose folder")
        pick.connect("clicked", lambda *_: self.pick_folder())
        self.sh_path = Gtk.Entry(placeholder_text="Mount path, e.g. /mnt/data", hexpand=True, width_chars=10)
        sh.append(self.sh_host)
        sh.append(pick)
        share = pill_button("Add share", "folder-symbolic", "suggested-action", self.add_share)
        share.set_halign(Gtk.Align.END)
        d.append(card(lbl("Port forwarding", "section-title"), fw, forward,
                      Gtk.Separator(margin_top=6, margin_bottom=6),
                      lbl("Folder sharing", "section-title"), sh, self.sh_path, share, spacing=8))
        return Gtk.ScrolledWindow(child=d, hscrollbar_policy=Gtk.PolicyType.NEVER)

    def build_settings(self):
        d = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        g = Gtk.Grid(row_spacing=12, column_spacing=16)
        g.add_css_class("oi-card")
        self.set_cpu = Gtk.Entry(placeholder_text="e.g. 2 (empty = unlimited)", hexpand=True)
        self.set_mem = Gtk.Entry(placeholder_text="e.g. 1GiB (empty = unlimited)", hexpand=True)
        self.set_auto = Gtk.Switch(halign=Gtk.Align.START)
        for r, (t, w) in enumerate([("CPU limit (cores)", self.set_cpu), ("Memory limit", self.set_mem), ("Start on boot", self.set_auto)]):
            g.attach(lbl(t, "dim"), 0, r, 1, 1)
            g.attach(w, 1, r, 1, 1)
        d.append(g)
        row = Gtk.Box(halign=Gtk.Align.START, spacing=8)
        self.settings_owner = None
        self.settings_pending = set()
        self.settings_apply = pill_button("Apply", None, "suggested-action", self.apply_settings)
        self.settings_apply.set_sensitive(False)
        row.append(self.settings_apply)
        row.append(pill_button("Reload", None, None, self.load_tab))
        d.append(row)
        self.cfg_view = Gtk.TextView(editable=False, monospace=True, left_margin=10, top_margin=8, bottom_margin=8, wrap_mode=Gtk.WrapMode.WORD_CHAR)
        self.cfg_view.add_css_class("oi-card")
        d.append(lbl("Full configuration", "dim"))
        sc = Gtk.ScrolledWindow(vexpand=True)
        sc.set_child(self.cfg_view)
        d.append(sc)
        return d

    # ------------------------------------------------------ plumbing
    def bg(self, fn, done=None, fail=None):
        def run():
            try:
                r, e = fn(), None
            except Exception as ex:  # noqa: BLE001
                r, e = None, ex
            GLib.idle_add(self.finish, r, e, done, fail)
        threading.Thread(target=run, daemon=True).start()

    def finish(self, r, e, done, fail, what=None):
        if self.closing:
            return False
        if e:
            if what:
                self.error_dialog(what, e)
            else:
                self.status.set_text(f"⚠ {str(e)[:240]}")
            if fail:
                fail()
        elif done:
            done(r)

    def read(self, slot, fn, done):
        """Coalesce repeated reads and ignore superseded responses."""
        def launch(work, complete):
            def run():
                try:
                    result, error = work(), None
                except Exception as ex:
                    result, error = None, ex
                GLib.idle_add(deliver, result, error)
            def deliver(result, error):
                if not self.closing:
                    complete(result, error)
                return False
            threading.Thread(target=run, daemon=True).start()
        task = self.reads.setdefault(slot, LatestRead(launch))
        task.submit(fn, done, lambda e: self.status.set_text(f"Could not refresh: {str(e)[:240]}"))

    def edit_instance(self, name, fn, done=None, fail=None, what="Update instance", key=None):
        """Serialize metadata edits per instance; preserve external ETag conflicts."""
        queue = self.instance_writes.setdefault(name, deque())
        if key is not None and any(item[4] == key for item in queue):
            self.flash("This change is already in progress")
            return False
        if len(queue) >= 16:
            self.flash("Wait for pending changes to finish")
            return False
        queue.append((fn, done, fail, what, key))
        if len(queue) == 1:
            self.next_instance_edit(name)
        return True

    def next_instance_edit(self, name):
        queue = self.instance_writes[name]
        fn, done, fail, what, key = queue[0]
        def advance():
            queue.popleft()
            if queue and not self.closing:
                self.next_instance_edit(name)
            else:
                self.instance_writes.pop(name, None)
        def completed(result):
            try:
                if done:
                    done(result)
            finally:
                advance()
        def failed():
            try:
                if fail:
                    fail()
            finally:
                advance()
        self.bgl(fn, done=completed, fail=failed, what=what)

    def bgl(self, fn, done=None, fail=None, what="Action"):
        """Like bg(), but a failure opens a dialog (used for anything the user asked for)."""
        def run():
            try:
                r, e = fn(), None
            except Exception as ex:  # noqa: BLE001
                r, e = None, ex
            GLib.idle_add(self.finish, r, e, done, fail, what)
        threading.Thread(target=run, daemon=True).start()

    def error_dialog(self, what, err):
        detail = str(err).strip() or "Unknown error"
        d = Granite.MessageDialog.with_image_from_icon_name(f"{what} failed", "Incus reported an error.", "dialog-error", Gtk.ButtonsType.CLOSE)
        d.set_transient_for(self)
        d.set_modal(True)
        d.show_error_details(detail[:3000])
        d.add_button("Copy details", Gtk.ResponseType.APPLY)
        def resp(dlg, r):
            if r == Gtk.ResponseType.APPLY:
                self.get_clipboard().set(detail)
                self.flash("Copied error details")
            dlg.destroy()
        d.connect("response", resp)
        d.present()
        d.get_widget_for_response(Gtk.ResponseType.CLOSE).grab_focus()

    def confirm(self, title, detail, verb, on_yes, destructive=True):
        d = Granite.MessageDialog.with_image_from_icon_name(title, detail, "dialog-warning" if destructive else "dialog-question", Gtk.ButtonsType.CANCEL)
        d.set_transient_for(self)
        d.set_modal(True)
        b = d.add_button(verb, Gtk.ResponseType.ACCEPT)
        b.add_css_class("destructive-action" if destructive else "suggested-action")
        d.set_default_response(Gtk.ResponseType.CANCEL)
        def resp(dlg, r):
            dlg.destroy()
            if r == Gtk.ResponseType.ACCEPT:
                on_yes()
        d.connect("response", resp)
        d.present()

    def dialog(self, title, parent=None, width=440, height=-1):
        # an explicit height avoids GTK's "measure ... needs at least" warning from the default-size guess
        d = Granite.Dialog(modal=True, transient_for=parent or self, title=title, default_width=width, default_height=height)
        connections = []
        def connect_owned(widget, signal_name, callback):
            handler = widget.connect(signal_name, callback)
            connections.append((widget, handler))
            return handler
        def release(*_):
            # Native signal closures are not ordinary Python GC edges. A form
            # callback capturing its own Entry otherwise keeps the form alive.
            owned = connections[:]
            connections.clear()
            for widget, handler in owned:
                if widget.handler_is_connected(handler):
                    widget.disconnect(handler)
        d.connect_owned = connect_owned
        d.connect_after("response", release)
        d.connect("unrealize", release)
        return d, d.get_content_area()

    def notify(self, title, body=""):
        """Desktop notification, only when the window isn't in front."""
        if self.is_active():
            return
        n = Gio.Notification.new(title)
        n.set_body(body)
        n.set_icon(Gio.ThemedIcon.new(APP_ID))
        self.get_application().send_notification(None, n)

    # -- persisted UI state
    def load_state(self):
        try:
            with open(STATE_FILE) as f:
                return json.load(f)
        except (OSError, ValueError):
            return {}

    def save_state(self):
        st = {"w": self.get_width() or self.state.get("w", 1180), "h": self.get_height() or self.state.get("h", 740),
              "max": self.is_maximized(), "page": self.pages.get_visible_child_name(), "tab": self.tabs.get_visible_child_name(),
              "cur": self.cur or self.state.get("cur")}
        if self.is_maximized():
            st["w"], st["h"] = self.state.get("w", 1180), self.state.get("h", 740)
        self.state = st
        try:
            os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
            with open(STATE_FILE, "w") as f:
                json.dump(st, f)
        except OSError:
            pass

    def on_close(self, *_):
        if self.closing:
            return False
        self.save_state()
        self.stop_monitor()
        for source in self.sources:
            GLib.source_remove(source)
        self.sources.clear()
        for task in self.reads.values():
            task.invalidate()
        for job in self.jobs.values():
            job["row"].stop_pulse()
        for proc in self.exec_proc.values():
            if proc.poll() is None:
                proc.terminate()
        Gtk.Settings.get_default().disconnect(self._theme_handler)
        Gtk.StyleContext.remove_provider_for_display(self.get_display(), self._css)
        atexit.unregister(self.stop_monitor)
        return False

    # -- first run / failure page
    def build_problem(self):
        self.pb = Granite.Placeholder(title="", description="", icon=Gio.ThemedIcon.new("dialog-warning-symbolic"))
        self.pb.append_button(Gio.ThemedIcon.new("view-refresh-symbolic"), "Try again", "Check Incus again").connect("clicked", lambda *_: self.check_incus())
        self.pb_cmd = lbl("", "cmd-block", selectable=True, wrap=True, focusable=False)
        row = Gtk.Box(spacing=8, halign=Gtk.Align.CENTER, margin_bottom=24)
        row.append(self.pb_cmd)
        cp = Gtk.Button(icon_name="edit-copy-symbolic", tooltip_text="Copy command", valign=Gtk.Align.CENTER)
        a11y(cp, "Copy command")
        cp.connect("clicked", lambda *_: (self.get_clipboard().set(self.pb_cmd.get_text()), self.flash("Copied")))
        row.append(cp)
        b = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, valign=Gtk.Align.CENTER, vexpand=True)
        b.append(self.pb)
        b.append(row)
        return b

    def check_incus(self):
        if self.closing or self._checking:
            return
        self._checking = True
        def done(problem):
            self._checking = False
            if problem:
                title, detail, cmd = problem
                self.pb.set_title(title)
                self.pb.set_description(detail)
                self.pb_cmd.set_text(cmd)
                self.ok = False
                self.root.set_visible_child_name("problem")
                for wdg in (self.new_btn, self.switcher, self.search):
                    wdg.set_sensitive(False)
            else:
                self.ok, self.fails = True, 0
                for wdg in (self.new_btn, self.switcher, self.search):
                    wdg.set_sensitive(True)
                self.root.set_visible_child_name("app")
                self.refresh()
                self.start_monitor()
        self.bg(backend.preflight, done, lambda: setattr(self, "_checking", False))

    def sampling_wanted(self):
        """Charts are only on screen for the Dashboard and an instance's Overview tab."""
        if not any(i["status"] == "Running" for i in self.data.values()):
            return False
        page = self.pages.get_visible_child_name()
        if page == "dash":
            return True
        cur = self.data.get(self.cur or "")
        return page == "inst" and bool(cur) and cur["status"] == "Running" and self.tabs.get_visible_child_name() == "ov"

    def tick(self):
        if not self.ok:
            return True
        surf = self.get_surface()
        minimized = bool(surf and surf.get_state() & Gdk.ToplevelState.MINIMIZED)
        due = time.monotonic() - self.last_refresh
        if self.monitor_ok:
            # events drive list updates; poll only to feed a visible chart, plus a slow resync
            if not minimized and self.is_active() and self.sampling_wanted() and due >= PERIOD - 0.5:
                self.refresh()
            elif due >= SAFETY_PERIOD:
                self.refresh()
        elif not minimized and (self.is_active() or due >= IDLE_PERIOD):
            self.refresh()  # no event stream: fall back to polling
        return True

    # -- lifecycle events from `incus monitor`
    def start_monitor(self):
        if self.mon_thread:
            return
        def run():
            while not self.closing:
                try:
                    proc = subprocess.Popen(["incus", "monitor", "--type=lifecycle", "--format", "json"],
                                            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
                except OSError:
                    return
                with self.monitor_lock:
                    self.mon_proc = proc
                    if self.closing:
                        proc.terminate()
                # Starting the client is not evidence the event stream connected.
                # Polling remains available until the first real lifecycle event.
                for line in proc.stdout:
                    if line.strip() and not self.closing:
                        GLib.idle_add(self.on_event, line)
                proc.wait()
                proc.stdout.close()
                if self.closing:
                    return
                GLib.idle_add(self.set_monitor, False)
                for _ in range(10):
                    if self.closing:
                        return
                    time.sleep(0.5)
        self.mon_thread = threading.Thread(target=run, daemon=True)
        self.mon_thread.start()

    def stop_monitor(self):
        self.closing = True
        with self.monitor_lock:
            p = self.mon_proc
            if p and p.poll() is None:
                p.terminate()

    def set_monitor(self, ok):
        if self.closing:
            return False
        self.monitor_ok = ok
        if ok:
            self.refresh()  # resync anything missed while disconnected
        return False

    def schedule_refresh(self, delay=250):
        if self._rf_pending:
            return
        self._rf_pending = True
        def fire():
            self._rf_pending = False
            self.refresh()
            return False
        self.later(delay, fire)

    def on_event(self, line):
        if self.closing:
            return False
        ev = backend.parse_event(line)
        if not ev:
            return False
        if not self.monitor_ok:
            self.set_monitor(True)
        action, source = ev
        if action.startswith("instance-"):
            self.schedule_refresh()
            if action in backend.STARTED_ACTIONS:
                for secs in (3, 8):  # Address discovery has no lifecycle event.
                    if secs in self._address_followups:
                        continue
                    self._address_followups.add(secs)
                    def followup(delay=secs):
                        self._address_followups.discard(delay)
                        self.schedule_refresh()
                    self.later(secs, followup, seconds=True)
            if "snapshot" in action and self.cur and f"/instances/{self.cur}/" in source and self.tabs.get_visible_child_name() == "sn":
                self.load_tab()
        return False

    def flash(self, text):
        """Transient confirmation as a Granite toast."""
        self.toast.set_title(text)
        self.toast.send_notification()

    def refresh_all(self):
        if not self.ok:
            self.check_incus()
            return
        self.refresh()
        self.load_page()
        self.load_tab()

    def refresh(self):
        if self.closing:
            return
        if self._listing:
            self._refresh_again = True
            return
        self._listing = True
        self.refresh_spinner.set_visible(True)
        self.refresh_spinner.start()
        self.last_refresh = time.monotonic()
        def fail():
            self._listing = False
            self.refresh_spinner.stop()
            self.refresh_spinner.set_visible(False)
            self._refresh_again = False
            self.fails += 1
            if self.fails >= 2:
                self.check_incus()
        def done(d):
            self._listing = False
            self.refresh_spinner.stop()
            self.refresh_spinner.set_visible(False)
            self.fails = 0
            self.show(d)
            if self._refresh_again:
                self._refresh_again = False
                self.schedule_refresh()
        self.bg(lambda: backend.ijson("list", timeout=backend.POLL_TIMEOUT), done, fail)

    def sample(self, data):
        """Totals always; history only at chart cadence so bursty event-driven refreshes don't skew the charts."""
        now = time.monotonic()
        record = now - self.last_sample >= PERIOD * 0.8
        if record:
            self.last_sample = now
        tc = tm = tp = 0.0
        for i in data:
            n, st = i["name"], i.get("state") or {}
            h = self.hist.setdefault(n, {"cpu": deque(maxlen=HIST), "mem": deque(maxlen=HIST), "t": None, "ns": None})
            if i["status"] != "Running":
                h["t"] = h["ns"] = None
                if record:
                    h["cpu"].append(0.0)
                    h["mem"].append(0.0)
                continue
            ns, mem = (st.get("cpu") or {}).get("usage", 0), (st.get("memory") or {}).get("usage", 0)
            if record:
                pct = backend.cpu_percent(h["ns"], h["t"], ns, now)
                h["t"], h["ns"] = now, ns
                h["cpu"].append(pct)
                h["mem"].append(mem)
            tc += last(h['cpu']) if h["cpu"] else 0.0
            tm += mem
            tp += st.get("processes", 0)
        live_names = {i["name"] for i in data}
        for n in list(self.hist):
            if n not in live_names:
                del self.hist[n]
        if record:
            self.tot["cpu"].append(tc)
            self.tot["mem"].append(tm)
        return tc, tm, tp

    def show(self, data):
        data = [i for i in data if i["name"] not in self.cleaning]
        for i in data:  # instances mid-creation can report null config/state
            i["config"] = i.get("config") or {}
            i["state"] = i.get("state") or {}
        self.data = {i["name"]: i for i in data}
        if self.rename_output:
            old, new = self.rename_output
            if new in self.data:
                if old in self.exec_bufs and old not in self.exec_proc:
                    self.exec_bufs[new] = self.exec_bufs.pop(old)
                self.rename_output = None
            elif old not in self.data:
                self.rename_output = None
        self.prune_instance_views()
        tc, tm, tp = self.sample(data)
        # sidebar
        for n in list(self.rows):
            if n not in self.data:
                self.list.remove(self.rows.pop(n))
        for n, i in self.data.items():
            if n in self.rows:
                self.rows[n].update(i)
            else:
                self.rows[n] = Row(i)
                self.list.append(self.rows[n])
        self.filter_instances()
        run = sum(1 for i in data if i["status"] == "Running")
        self.summary.set_text(f"{len(data)} INSTANCES · {run} RUNNING" if data else "NO INSTANCES YET")
        self.dash_empty.set_visible(not data)
        if not self.restored:
            self.restored = True
            want = self.state.get("cur")
            if want in self.rows:
                self.list.select_row(self.rows[want])
            if self.state.get("tab") in ("ov", "sn", "ex", "fi", "de", "se"):
                self.tabs.set_visible_child_name(self.state["tab"])
        # dashboard
        self.tile["run"].set_text(f"{run} / {len(data)}")
        self.tile["cpu"].set_text(f"{tc:.0f}%")
        self.tile["mem"].set_text(human(tm))
        self.tile["proc"].set_text(f"{tp:.0f}")
        self.tot_cpu.set(self.tot["cpu"])
        self.tot_mem.set(self.tot["mem"])
        self.render_dashboard()
        # Resolve rename selection only after the new inventory and rows agree.
        target = self.select_after_refresh
        if target in self.rows:
            self.select_after_refresh = None
            self.open_instance(target)
        # detail
        if self.cur not in self.data:
            self.cur = None
        if self.cur:
            self.fill(self.data[self.cur])
        else:
            self.stack.set_visible_child_name("empty")

    def render_dashboard(self):
        if self.pages.get_visible_child_name() != "dash" or self._dashboard_rendering:
            return
        for n in list(self.dash_rows):
            if n not in self.data:
                self.dash_list.remove(self.dash_rows.pop(n))
        missing = deque()
        for n in sorted(self.data):
            if n in self.dash_rows:
                self.update_dashboard_row(n)
            else:
                missing.append(n)
        if not missing:
            return
        self._dashboard_rendering = True
        def batch():
            if self.pages.get_visible_child_name() != "dash":
                self._dashboard_rendering = False
                return
            # Populate over successive main-loop turns so input stays responsive.
            for _ in range(min(16, len(missing))):
                n = missing.popleft()
                if n not in self.data:
                    continue
                row = self.dash_rows[n] = DashRow(n, self.open_instance)
                self.dash_list.append(row)
                self.update_dashboard_row(n, force=True)
            if missing:
                self.later(1, batch)
            else:
                self._dashboard_rendering = False
        self.later(0, batch)

    def prune_instance_views(self):
        """Release deleted guests even when their last page is hidden."""
        for n in list(self.dash_rows):
            if n not in self.data:
                self.dash_list.remove(self.dash_rows.pop(n))
        for n in list(self.exec_bufs):
            if n not in self.data and n not in self.exec_proc:
                buffer = self.exec_bufs.pop(n)
                if self.exec_out.get_buffer() is buffer:
                    self.exec_out.set_buffer(self.empty_exec_buf)

    def update_dashboard_row(self, n, force=False):
        r, i, h = self.dash_rows[n], self.data[n], self.hist[n]
        if not force:
            valid, bounds = r.compute_bounds(self.dash_scroller)
            if valid and (bounds.get_y() + bounds.get_height() < 0 or bounds.get_y() > self.dash_scroller.get_height()):
                return  # Refresh offscreen charts when scrolling brings them into view.
        for c in ("running", "frozen"):
            r.dot.remove_css_class(c)
        if state_key(i["status"]) != "stopped":
            r.dot.add_css_class(state_key(i["status"]))
        r.cpu.set(h["cpu"])
        r.mem.set(h["mem"])
        on = i["status"] == "Running"
        r.cpu_l.set_text(f"{last(h['cpu']):.0f}%" if on else "—")
        r.mem_l.set_text(human(last(h['mem'])) if on else "—")

    def open_instance(self, name):
        self.pages.set_visible_child_name("inst")
        if name in self.rows:
            row = self.rows[name]
            query = self.search.get_text().casefold().strip()
            if query not in row.search_text:
                self.search.set_text("")
                self.filter_instances()
            self.list.select_row(row)
            if self.cur != name:
                self.on_select(self.list, row)

    def on_select(self, _l, row):
        self.cur = row.name if row else None
        self.settings_owner = None
        self.settings_apply.set_sensitive(False)
        if "tab" in self.reads:
            self.reads["tab"].invalidate()
        if self.cur:
            self.fpath = "/"
            self.show_exec_buf(self.cur)
            self.fill(self.data[self.cur], reload=True)
            self.load_tab()
        else:
            self.stack.set_visible_child_name("empty")

    def fill(self, i, reload=False):
        st = i.get("state") or {}
        k = state_key(i["status"])
        run = k == "running"
        n = i["name"]
        self.stack.set_visible_child_name("detail")
        self.d_title.set_text(n)
        self.d_title.set_tooltip_text(n)
        self.d_state.set_text(i["status"])
        vm = i["type"] == "virtual-machine"
        self.console_button.set_visible(vm)
        self.console_button.set_sensitive(vm and run)
        self.vm_agent_hint.set_visible(vm)
        for w, c in ((self.d_state, k), (self.d_type, "vm" if vm else "")):
            for x in ("running", "vm", "frozen"):
                w.remove_css_class(x)
            if c and c != "stopped":
                w.add_css_class(c)
        self.d_type.set_text("VM" if vm else "Container")
        cfg = i["config"]
        self.d_sub.set_text(" ".join(x for x in (cfg.get("image.os"), cfg.get("image.release")) if x) or i["type"])
        h = self.hist.get(n)
        mem = (st.get("memory") or {}).get("usage", 0)
        live = run or k == "frozen"
        self.stat["mem"].set_text(human(mem) if live else "—")
        self.stat["cpu"].set_text(f"{last(h['cpu']):.0f}%" if (run and h) else "—")
        self.stat["disk"].set_text(human(((st.get("disk") or {}).get("root") or {}).get("usage", 0)) if live else "—")
        self.stat["proc"].set_text(str(st.get("processes", 0)) if live else "—")
        if h:
            self.d_cpu.set(h["cpu"]); self.d_mem.set(h["mem"])
        net = next((v for k2, v in ((st.get("network") or {}).items()) if k2 != "lo"), {}) or {}
        self.info["image"].set_text(cfg.get("image.description", "—"))
        self.info["ipv4"].set_text(", ".join(addrs(st, "inet")) or "—")
        self.info["ipv6"].set_text(", ".join(addrs(st, "inet6")) or "—")
        self.info["mac"].set_text(net.get("hwaddr") or cfg.get("volatile.eth0.hwaddr", "—"))
        self.info["arch"].set_text(i.get("architecture", "—"))
        self.info["created"].set_text(i.get("created_at", "—")[:19].replace("T", " "))
        self.info["pid"].set_text(str(st.get("pid") or "—"))
        busy = n in self.busy
        show = backend.visible_actions(k)
        for key in ("start", "stop", "restart", "pause", "shell", "snap"):
            self.btn[key].set_visible(key in show)
            self.btn[key].get_parent().set_visible(key in show)  # the FlowBoxChild, so hidden buttons leave no gap
        self.btn["start"].set_sensitive(k == "stopped" and not busy)
        for key in ("stop", "restart"):
            self.btn[key].set_sensitive(live and not busy)
        self.btn["shell"].set_sensitive(run and not busy)
        self.btn["pause"].set_sensitive(live and not busy)
        self.btn["pause"].get_child().get_last_child().set_label("Resume" if k == "frozen" else "Pause")
        self.btn["snap"].set_sensitive(not busy)
        self.btn["delete"].set_sensitive(not busy)
        if reload:
            self.log.get_buffer().set_text("loading…")
            self.read("log", lambda: backend.incus("info", n, "--show-log", timeout=backend.POLL_TIMEOUT),
                    lambda t: n == self.cur and self.log.get_buffer().set_text(t.split("Log:")[-1].strip() or t))

    # ------------------------------------------------------ tab content
    def load_tab(self):
        if "tab" in self.reads:
            self.reads["tab"].invalidate()
        n = self.cur
        if not n or n not in self.data:
            return
        t = self.tabs.get_visible_child_name()
        if t == "sn":
            self.put(self.snap_list, [lbl("Loading snapshots…", "dim")])
            self.read("tab", lambda: backend.ijson("snapshot", "list", n), lambda d: n == self.cur and self.fill_snaps(n, d))
        elif t == "fi":
            self.list_files()
        elif t == "de":
            self.put(self.dev_list, [lbl("Loading devices…", "dim")])
            self.read("tab", lambda: json.loads(backend.incus("query", f"/1.0/instances/{n}", timeout=backend.POLL_TIMEOUT)), lambda d: n == self.cur and self.fill_devices(n, d))
        elif t == "ex":
            self.show_exec_buf(n)
        elif t == "se":
            self.settings_owner = None
            self.settings_apply.set_sensitive(False)
            self.read("tab", lambda: (backend.incus("config", "show", n, timeout=backend.POLL_TIMEOUT)),
                    lambda txt: n == self.cur and self.fill_settings(n, txt))

    def fill_snaps(self, n, snaps):
        self.snap_list.remove_all()
        if not snaps:
            self.snap_list.append(lbl("No snapshots yet.", "dim", margin_top=12))
        for s in sorted(snaps, key=lambda s: s.get("created_at", ""), reverse=True):
            name = s["name"].split("/")[-1]
            row = Gtk.Box(spacing=10)
            row.add_css_class("list-card")
            col = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, hexpand=True)
            col.append(lbl(name, "inst-name"))
            col.append(lbl(s.get("created_at", "")[:19].replace("T", " ") + ("  ·  stateful" if s.get("stateful") else ""), "dim"))
            row.append(col)
            row.append(pill_button("Restore", "document-revert-symbolic", None, lambda nm=name: self.snap_op(n, "restore", nm, True)))
            row.append(pill_button("Delete", "user-trash-symbolic", "destructive-action", lambda nm=name: self.snap_op(n, "delete", nm, True)))
            self.snap_list.append(row)

    def snap_op(self, n, verb, snap, confirm):
        if verb == "restore":
            title, detail = f"Restore “{n}” to “{snap}”?", "The current state is replaced by the snapshot."
        else:
            title, detail = f"Delete snapshot “{snap}”?", "This cannot be undone."
        go = lambda: self.bgl(lambda: backend.incus("snapshot", verb, n, snap), what=f"{verb.capitalize()} snapshot",
                              done=lambda _: (self.flash(f"{verb.capitalize()}d {snap}"), self.load_tab(), self.refresh()))
        self.confirm(title, detail, verb.capitalize(), go) if confirm else go()

    def fill_settings(self, n, txt):
        self.cfg_view.get_buffer().set_text(txt)
        cfg = {}
        for line in txt.splitlines():
            if line.startswith("  ") and ": " in line and not line.startswith("    "):
                k, v = line.strip().split(": ", 1)
                cfg[k] = v.strip("'\"")
        self.set_cpu.set_text(cfg.get("limits.cpu", ""))
        self.set_mem.set_text(cfg.get("limits.memory", ""))
        self.set_auto.set_active(cfg.get("boot.autostart") == "true")
        self.settings_owner = n
        self.settings_apply.set_sensitive(n not in self.settings_pending)

    def apply_settings(self):
        n = self.cur
        if not n or self.settings_owner != n or n in self.settings_pending:
            return
        vals = {"limits.cpu": self.set_cpu.get_text().strip(), "limits.memory": self.set_mem.get_text().strip(),
                "boot.autostart": "true" if self.set_auto.get_active() else ""}
        self.settings_pending.add(n)
        self.settings_apply.set_sensitive(False)
        def go():
            # Incus accepts empty values as removal, including already absent keys.
            # One bulk set validates/applies all three values in one update.
            backend.incus("config", "set", n, *(f"{k}={v}" for k, v in vals.items()))
        def finished(_=None):
            self.settings_pending.discard(n)
            if n == self.cur:
                self.settings_apply.set_sensitive(self.settings_owner == n)
            self.refresh()
        def done(_):
            finished()
            self.flash(f"Updated {n}")
            if n == self.cur:
                self.load_tab()
        if not self.edit_instance(n, go, what="Apply settings", done=done, fail=finished, key="settings"):
            finished()

    # ------------------------------------------------------ other pages
    def load_page(self, auto=False):
        key = self.pages.get_visible_child_name()
        if key not in self.lists:
            if "page" in self.reads:
                self.reads["page"].invalidate()
            return
        if key in self.lists:
            lb, fn = self.lists[key]
            fn(lb)

    def put(self, lb, rows):
        lb.remove_all()
        if not rows:
            lb.append(lbl("Nothing here.", "dim", margin_top=8))
        for r in rows:
            lb.append(r)

    def item(self, title, subtitle, *extra, badges=()):
        row = Gtk.Box(spacing=12)
        row.add_css_class("list-card")
        col = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, hexpand=True)
        col.append(lbl(title, "inst-name", selectable=True))
        col.append(lbl(subtitle, "dim", wrap=True, selectable=True))
        row.append(col)
        for b in badges:
            row.append(lbl(b, "oi-badge", valign=Gtk.Align.CENTER))
        for e in extra:
            row.append(e)
        return row

    def fill_images(self, lb):
        def show(imgs):
            rows = []
            for im in sorted(imgs, key=lambda x: x.get("uploaded_at", ""), reverse=True):
                fp = im["fingerprint"]
                lab = backend.image_label(im)
                title = lab["title"]
                sub = " · ".join(x for x in (lab["alias"], fp[:12], human(im.get("size", 0)), im.get("uploaded_at", "")[:10]) if x)
                launch = pill_button("Launch", "media-playback-start-symbolic", None, lambda f=fp: self.launch_from(f))
                rm = Gtk.Button(icon_name="user-trash-symbolic", has_frame=False, valign=Gtk.Align.CENTER,
                                tooltip_text=f"Delete cached image “{title}”")
                rm.add_css_class("destructive-item")
                a11y(rm, f"Delete image {title}")
                rm.connect("clicked", lambda _b, f=fp, t=title: self.del_image(f, t))
                rows.append(self.item(title, sub, launch, rm, badges=(lab["kind"],)))
            self.put(lb, rows)
        self.read("page", lambda: backend.ijson("image", "list"), show)

    def launch_from(self, fp):
        self.flash(f"Launching from {fp[:12]}…")
        self.bgl(lambda: backend.incus("launch", fp), what="Launch", done=lambda _: (self.flash("Launched"), self.refresh()))

    def del_image(self, fp, title):
        self.confirm(f"Delete cached image “{title}”?", "It can be downloaded again when needed.", "Delete",
                     lambda: self.bgl(lambda: backend.incus("image", "delete", fp), what="Delete image",
                                      done=lambda _: (self.flash("Image deleted"), self.load_page())))

    def fill_nets(self, lb):
        def show(nets):
            rows = []
            for n in nets:
                c = n.get("config", {})
                sub = " · ".join(x for x in (f"IPv4 {c['ipv4.address']}" if c.get("ipv4.address") else "",
                                             f"IPv6 {c['ipv6.address']}" if c.get("ipv6.address") else "",
                                             f"NAT {c['ipv4.nat']}" if c.get("ipv4.nat") else "",
                                             f"{len(n.get('used_by') or [])} users") if x) or "—"
                rows.append(self.item(n["name"], sub, badges=(n["type"], "managed" if n.get("managed") else "external")))
            self.put(lb, rows)
        self.read("page", lambda: backend.ijson("network", "list"), show)

    def fill_pools(self, lb):
        def get():
            out = []
            for p in backend.ijson("storage", "list"):
                out.append((p, backend.incus("storage", "info", p["name"], timeout=backend.POLL_TIMEOUT)))
            return out
        def show(pools):
            rows = []
            for p, info in pools:
                used, total, frac = backend.parse_space(info)
                gauge = None
                if frac is not None:
                    pct = round(frac * 100)
                    sub = f"{p['config'].get('source', '')} · {human(used)} used of {human(total)} ({pct}%) · {len(p.get('used_by') or [])} users"
                    gauge = Gtk.LevelBar(min_value=0, max_value=1, value=frac, valign=Gtk.Align.CENTER, width_request=160)
                    gauge.add_offset_value("low", 0.0)
                    gauge.add_offset_value("high", 0.85)
                    gauge.add_offset_value("full", 0.95)
                    a11y(gauge, f"{p['name']} storage {pct}% full")
                else:
                    sub = f"{p['config'].get('source', '')} · usage unknown · {len(p.get('used_by') or [])} users"
                rows.append(self.item(p["name"], sub, *([gauge] if gauge else []), badges=(p["driver"],)))
            self.put(lb, rows)
        self.read("page", get, show)

    def fill_profiles(self, lb):
        def show(profs):
            rows = []
            for p in profs:
                sub = f"devices: {', '.join(p.get('devices', {})) or 'none'} · used by {len(p.get('used_by') or [])}"
                if p.get("config"):
                    sub += " · config: " + ", ".join(f"{k}={v}" for k, v in p["config"].items())[:120]
                rows.append(self.item(p["name"], sub, badges=()))
            self.put(lb, rows)
        self.read("page", lambda: backend.ijson("profile", "list"), show)

    # ------------------------------------------------------ actions
    def run_op(self, name, text, fn, after=None):
        if name in self.busy:
            self.flash(f"{name} already has an operation in progress")
            return
        t0 = time.monotonic()
        self.busy.add(name)
        self.status.set_text(text)
        if name == self.cur and name in self.data:
            self.fill(self.data[name])
        def done(_):
            self.busy.discard(name)
            self.status.set_text("")
            self.refresh()
            if time.monotonic() - t0 > 8:
                self.notify("Orchard", f"{text.rstrip('…')} finished")
            if after:
                after()
        def fail():
            self.busy.discard(name)
            self.refresh()
        self.bgl(fn, done, fail, what=text.rstrip("…"))

    def act(self, verb):
        n = self.cur
        if not n:
            return
        fn = (lambda: backend.stop_or_force(verb, n)) if verb in ("stop", "restart") else (lambda: backend.incus(verb, n))
        self.run_op(n, f"{verb.capitalize()}ing {n}…".replace("eing", "ing"), fn)

    def toggle_pause(self):
        n = self.cur
        if n and n in self.data:
            frozen = self.data[n]["status"] == "Frozen"
            self.run_op(n, f"{'Resuming' if frozen else 'Pausing'} {n}…", lambda: backend.incus("start" if frozen else "pause", n))

    def snapshot(self):
        n = self.cur
        if not n:
            return
        nm = self.snap_name.get_text().strip()
        self.snap_name.set_text("")
        self.run_op(n, f"Snapshotting {n}…", lambda: backend.incus("snapshot", "create", n, *([nm] if nm else [])), after=self.load_tab)

    def shell(self):
        n = self.cur
        if n:
            try:
                subprocess.Popen([TERMINAL, "-e", f"incus exec {n} -- sh -c 'exec $(command -v bash || echo sh) -l'"])
            except OSError as e:
                self.error_dialog("Open shell", e)

    def console(self):
        n = self.cur
        if n:
            try:
                subprocess.Popen([TERMINAL, "-e", f"incus console {n} --type=console"])
            except OSError as e:
                self.error_dialog("Open console", e)

    def copy_ip(self):
        n = self.cur
        ips = addrs((self.data.get(n) or {}).get("state"), "inet") if n else []
        if ips:
            self.get_clipboard().set(ips[0])
            self.flash(f"Copied {ips[0]}")
        else:
            self.flash("No IPv4 address")

    # ------------------------------------------------------ run / files / devices
    def exec_buf(self, n):
        if n not in self.exec_bufs:
            self.exec_bufs[n] = Gtk.TextBuffer(enable_undo=False)
        return self.exec_bufs[n]

    def show_exec_buf(self, n):
        self.exec_out.set_buffer(self.exec_buf(n))
        self.cmd_stop.set_sensitive(n in self.exec_proc)

    def append_out(self, n, text):
        if self.closing:
            return False
        b = self.exec_buf(n)
        adj = self.exec_sc.get_vadjustment()
        following = adj.get_value() >= adj.get_upper() - adj.get_page_size() - 24
        b.insert(b.get_end_iter(), text)
        # A noisy command must never grow GTK's text buffer without bound.
        extra = b.get_char_count() - 262144
        if extra > 0:
            b.delete(b.get_start_iter(), b.get_iter_at_offset(extra))
        if n == self.cur and following:
            self.later(0, lambda: adj.set_value(adj.get_upper()))
        return False

    def drain_output(self, n):
        mailbox = self.output.get(n)
        if mailbox:
            text = mailbox.take()
            if text:
                self.append_out(n, text)
        return False

    def run_cmd(self):
        n, cmd = self.cur, self.cmd.get_text().strip()
        if not n or not cmd:
            return
        if self.data[n]["status"] != "Running":
            self.flash("Start the instance first")
            return
        if n in self.exec_proc:
            self.flash("A command is already running here")
            return
        try:
            proc = subprocess.Popen(["incus", "exec", n, "--", "sh", "-c", cmd], stdout=subprocess.PIPE,
                                    stderr=subprocess.STDOUT)
        except OSError as e:
            self.error_dialog("Run command", e)
            return
        self.cmd.set_text("")
        self.append_out(n, f"$ {cmd}\n")
        self.exec_proc[n] = proc
        # A producer schedules one delivery per burst, never one idle per line.
        mailbox = OutputMailbox(lambda: GLib.timeout_add(50, self.drain_output, n))
        self.output[n] = mailbox
        self.cmd_stop.set_sensitive(True)
        def pump():
            decoder = codecs.getincrementaldecoder("utf-8")("replace")
            try:
                while True:
                    chunk = os.read(proc.stdout.fileno(), 16384)
                    if not chunk:
                        break
                    if not self.closing:
                        mailbox.put(decoder.decode(chunk))
                mailbox.put(decoder.decode(b"", final=True))
            finally:
                proc.stdout.close()
            rc = proc.wait()
            def end():
                self.drain_output(n)
                self.output.pop(n, None)
                self.exec_proc.pop(n, None)
                self.append_out(n, f"[exit {rc}]\n\n")
                if not self.closing:
                    self.prune_instance_views()
                if not self.closing and n == self.cur:
                    self.cmd_stop.set_sensitive(False)
                return False
            GLib.idle_add(end)
        threading.Thread(target=pump, daemon=True).start()

    def stop_cmd(self):
        p = self.exec_proc.get(self.cur)
        if p:
            p.terminate()

    def go_path(self, path):
        self.fpath = posixpath.normpath(path) if path else "/"
        self.list_files()

    def list_files(self):
        n, path = self.cur, self.fpath
        if not n:
            return
        self.fentry.set_text(path)
        if self.data[n]["status"] != "Running":
            self.flist.remove_all()
            self.flist.append(lbl("Start the instance to browse its files.", "dim", margin_top=12))
            return
        self.put(self.flist, [lbl("Loading files…", "dim")])
        self.fnames = {}
        def done(out):
            if n != self.cur or path != self.fpath:
                return
            self.flist.remove_all()
            self.fnames = {}
            items = sorted(out.split("\n"), key=lambda x: (not x.endswith("/"), x.lower()))
            for it in items:
                if not it:
                    continue
                isdir = it.endswith("/")
                name = it.rstrip("/*@")
                row = Gtk.ListBoxRow()
                b = Gtk.Box(spacing=10, margin_top=6, margin_bottom=6, margin_start=10)
                b.append(Gtk.Image(icon_name="folder-symbolic" if isdir else "text-x-generic-symbolic"))
                b.append(lbl(name, "inst-name" if isdir else ""))
                row.set_child(b)
                row.fname, row.isdir = name, isdir
                self.flist.append(row)
        self.read("tab", lambda: backend.incus("exec", n, "--", "ls", "-1Ap", path, timeout=backend.POLL_TIMEOUT), done)

    def on_files_dropped(self, _target, value, _x, _y):
        """Files or folders dragged from the file manager onto the Files tab are uploaded to the current folder."""
        self.flist.remove_css_class("drop-hover")
        n = self.cur
        paths = [f.get_path() for f in value.get_files() if f.get_path()]
        if not n or not paths:
            return False
        if self.data[n]["status"] != "Running":
            self.flash("Start the instance to upload files")
            return False
        dest = self.fpath.rstrip("/") + "/"
        def go():
            for path in paths:
                backend.incus("file", "push", "-r", path, f"{n}{dest}")
        self.bgl(go, what="Upload", done=lambda _: (self.flash(f"Uploaded {len(paths)} item{'s' if len(paths) != 1 else ''}"), self.list_files()))
        return True

    def on_file_activate(self, _l, row):
        if getattr(row, "isdir", False):
            self.go_path(posixpath.join(self.fpath, row.fname))

    def pull_selected(self):
        n, row = self.cur, self.flist.get_selected_row()
        if not n or not row or not hasattr(row, "fname"):
            self.flash("Select a file or folder first")
            return
        src = posixpath.join(self.fpath, row.fname)
        dlg = Gtk.FileDialog(title="Save to…", initial_name=row.fname)
        def chosen(d, res):
            try:
                f = d.save_finish(res)
            except GLib.Error:
                return
            dest = f.get_path()
            self.flash(f"Downloading {src}…")
            self.bgl(lambda: backend.incus("file", "pull", "-r", f"{n}{src}", dest), what="Download", done=lambda _: self.flash(f"Saved {dest}"))
        dlg.save(self, None, chosen)

    def push_file(self):
        n = self.cur
        if not n:
            return
        dir_ = self.fpath
        dlg = Gtk.FileDialog(title="Upload a file")
        def chosen(d, res):
            try:
                f = d.open_finish(res)
            except GLib.Error:
                return
            src = f.get_path()
            self.flash(f"Uploading {os.path.basename(src)}…")
            self.bgl(lambda: backend.incus("file", "push", src, f"{n}{dir_.rstrip('/')}/"), what="Upload", done=lambda _: (self.flash("Uploaded"), self.list_files()))
        dlg.open(self, None, chosen)

    def fill_devices(self, n, inst):
        own, exp = inst.get("devices") or {}, inst.get("expanded_devices") or {}
        self.dev_list.remove_all()
        for name, dev in sorted(exp.items()):
            mine = name in own
            t = dev.get("type", "?")
            if t == "proxy":
                sub = f"{dev.get('listen', '')}  →  {dev.get('connect', '')}"
            elif t == "disk":
                sub = f"{dev.get('source', dev.get('pool', ''))}  →  {dev.get('path', '')}" + ("  (read-only)" if dev.get("readonly") == "true" else "")
            else:
                sub = ", ".join(f"{k}={v}" for k, v in dev.items() if k != "type")[:110] or "—"
            row = self.item(name, sub, badges=(t, "instance" if mine else "profile"))
            if mine:
                row.append(pill_button("Remove", "user-trash-symbolic", "destructive-action", lambda nm=name: self.remove_device(n, nm)))
            self.dev_list.append(row)

    def devices_changed(self, n, message):
        self.flash(message)
        if n == self.cur and self.tabs.get_visible_child_name() == "de":
            self.load_tab()

    def remove_device(self, n, name):
        self.edit_instance(n, lambda: backend.incus("config", "device", "remove", n, name),
                           what="Remove device", key=("remove", name),
                           done=lambda _: self.devices_changed(n, f"Removed {name}"))

    def add_forward(self):
        n = self.cur
        a, b = self.fw_listen.get_text().strip(), self.fw_connect.get_text().strip()
        if not (n and a.isdigit() and b.isdigit() and 0 < int(a) < 65536 and 0 < int(b) < 65536):
            self.flash("Ports must be numbers from 1 to 65535")
            return
        proto = ["tcp", "udp"][self.fw_proto.get_selected()]
        name = f"fwd-{proto}-{a}"
        args = ["config", "device", "add", n, name, "proxy", f"listen={proto}:0.0.0.0:{a}", f"connect={proto}:127.0.0.1:{b}"]
        self.fw_listen.set_text(""); self.fw_connect.set_text("")
        self.edit_instance(n, lambda: backend.incus(*args), what="Add port forward", key=("add", name),
                           done=lambda _: self.devices_changed(n, f"Forwarding host :{a} → {n}:{b}"))

    def pick_folder(self):
        dlg = Gtk.FileDialog(title="Choose a host folder")
        def chosen(d, res):
            try:
                self.sh_host.set_text(d.select_folder_finish(res).get_path())
            except GLib.Error:
                pass
        dlg.select_folder(self, None, chosen)

    def add_share(self):
        n, host, path = self.cur, self.sh_host.get_text().strip(), self.sh_path.get_text().strip()
        if not (n and os.path.isabs(host) and path.startswith("/")):
            self.flash("Use absolute paths for the host folder and the instance mount")
            return
        name = "share-" + "".join(c if c.isalnum() else "-" for c in path.strip("/"))[:30]
        args = ["config", "device", "add", n, name, "disk", f"source={host}", f"path={path}", "shift=true"]
        self.sh_host.set_text(""); self.sh_path.set_text("")
        self.edit_instance(n, lambda: backend.incus(*args), what="Share folder", key=("add", name),
                           done=lambda _: self.devices_changed(n, f"Shared {host} at {path}"))

    def export_backup(self):
        n = self.cur
        if not n:
            return
        dlg = Gtk.FileDialog(title="Export backup", initial_name=f"{n}.tar.gz")
        def chosen(d, res):
            try:
                dest = d.save_finish(res).get_path()
            except GLib.Error:
                return
            self.run_op(n, f"Exporting {n} to {dest}…", lambda: backend.incus("export", n, dest), after=lambda: self.flash(f"Backup saved: {dest}"))
        dlg.save(self, None, chosen)

    def on_row_menu(self, gesture, _n, x, y):
        row = self.list.get_row_at_y(int(y))
        if not row:
            return
        self.list.select_row(row)
        i = self.data.get(row.name, {})
        k = state_key(i.get("status", ""))
        pop = Gtk.Popover(has_arrow=False)
        pop.set_parent(row)
        pb = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        for label, fn, on in [("Start", lambda: self.act("start"), k == "stopped"), ("Stop", lambda: self.act("stop"), k != "stopped"),
                              ("Open shell", self.shell, k == "running"), ("Clone…", self.clone, True),
                              ("Rename…", self.rename, True), ("Delete…", self.delete, True)]:
            b = Gtk.Button(label=label, has_frame=False, sensitive=on)
            b.get_child().set_halign(Gtk.Align.START)
            b.connect("clicked", lambda _b, f=fn: (pop.popdown(), f()))
            pb.append(b)
        pop.set_child(pb)
        pop.connect("closed", lambda p: GLib.idle_add(p.unparent))
        rect = Gdk.Rectangle()
        rect.x, rect.y, rect.width, rect.height = int(x - row.get_allocation().x), int(y - row.get_allocation().y), 1, 1
        pop.set_pointing_to(rect)
        pop.popup()

    def on_list_key(self, _c, keyval, _code, _state):
        if keyval == Gdk.KEY_Menu or (keyval == Gdk.KEY_F10 and _state & Gdk.ModifierType.SHIFT_MASK):
            row = self.list.get_selected_row()
            if row:
                area = row.get_allocation()
                self.on_row_menu(None, 1, area.x + 16, area.y + 16)
                return True
        if keyval == Gdk.KEY_Delete and self.cur:
            self.delete()
            return True
        if keyval == Gdk.KEY_F2 and self.cur:
            self.rename()
            return True
        return False

    def ask_name(self, title, hint, preset, ok_label, fn):
        d, area = self.dialog(title, width=400, height=330)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8, margin_top=6, margin_bottom=6, margin_start=12, margin_end=12)
        e = Gtk.Entry(text=preset, placeholder_text=hint, activates_default=True)
        a11y(e, hint)
        err = lbl("", "error-text", max_width_chars=48, ellipsize=Pango.EllipsizeMode.END)
        box.append(Granite.HeaderLabel(label="Name"))
        box.append(e)
        box.append(err)
        area.append(box)
        d.add_button("Cancel", Gtk.ResponseType.CANCEL)
        ok = d.add_button(ok_label, Gtk.ResponseType.ACCEPT)
        ok.add_css_class("suggested-action")
        d.set_default_response(Gtk.ResponseType.ACCEPT)
        def check(*_):
            v = e.get_text().strip()
            bad = bool(v) and not valid_name(v)
            (e.add_css_class if bad else e.remove_css_class)("error")
            err.set_text("Letters, digits and hyphens only; max 63." if bad else "")
            ok.set_sensitive(bool(v) and not bad)
        d.connect_owned(e, "changed", check)
        def resp(dlg, r):
            v = e.get_text().strip()
            dlg.destroy()
            if r == Gtk.ResponseType.ACCEPT and v and valid_name(v):
                fn(v)
        d.connect_owned(d, "response", resp)
        check()
        d.present()
        e.grab_focus()

    def clone(self):
        n = self.cur
        if n:
            self.ask_name(f"Clone {n}", "new name", f"{n}-copy", "Clone",
                          lambda v: (self.flash(f"Cloning {n} → {v}…"), self.bgl(lambda: backend.incus("copy", n, v), what="Clone", done=lambda _: (self.flash("Cloned"), self.refresh()))))

    def rename(self):
        n = self.cur
        if not n:
            return
        if self.data[n]["status"] != "Stopped":
            self.flash("Stop the instance before renaming it")
            return
        def go(v):
            def done(_):
                self.rename_output = (n, v)
                self.select_after_refresh = v
                self.flash(f"Renamed to {v}")
                self.refresh()
            self.bgl(lambda: backend.incus("rename", n, v), what="Rename", done=done)
        self.ask_name(f"Rename {n}", "new name", n, "Rename", go)

    def delete(self):
        n = self.cur
        if n:
            self.confirm(f"Delete “{n}”?", "The instance and its snapshots are permanently removed.", "Delete",
                         lambda: self.run_op(n, f"Deleting {n}…", lambda: backend.incus("delete", "--force", n)))

    def browse_images(self, on_pick, parent=None):
        d, area = self.dialog("Browse images", parent=parent, width=640)
        d.set_default_size(640, 520)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10, margin_start=12, margin_end=12, margin_bottom=6, vexpand=True)
        se = Gtk.SearchEntry(placeholder_text=f"Search images:  alpine, debian, ubuntu, arch…  ({ARCH})")
        a11y(se, "Search images")
        box.append(se)
        lb = Gtk.ListBox(selection_mode=Gtk.SelectionMode.NONE)
        lb.add_css_class("sidebar-list")
        sc = Gtk.ScrolledWindow(vexpand=True, hscrollbar_policy=Gtk.PolicyType.NEVER, min_content_height=380)
        sc.set_child(lb)
        box.append(sc)
        area.append(box)
        d.add_button("Close", Gtk.ResponseType.CLOSE)
        slot = ("image-search", id(d))
        def close(dlg, _r):
            task = self.reads.pop(slot, None)
            if task:
                task.invalidate()
            dlg.destroy()
        d.connect_owned(d, "response", close)
        def search(*_):
            term = se.get_text().strip()
            lb.remove_all()
            lb.append(lbl("Searching…", "dim", margin_top=8))
            def done(out):
                lb.remove_all()
                rows = backend.parse_images_csv(out)
                for alias, desc, vm in rows:
                    r = self.item(alias, desc, badges=("VM" if vm else "container",))
                    r.append(pill_button("Select", None, "suggested-action", lambda a=alias, v=vm: (on_pick(f"images:{a}", v), d.response(Gtk.ResponseType.CLOSE))))
                    lb.append(r)
                if not rows:
                    lb.append(lbl("No matches.", "dim", margin_top=8))
            self.read(slot, lambda: backend.incus("image", "list", "images:", term, ARCH, "-c", "ldt", "--format", "csv", timeout=backend.POLL_TIMEOUT), done)
        d.connect_owned(se, "activate", search)
        d.present()
        search()



    def start_create(self, name, img, extra):
        """Run `incus launch` as a cancellable job with a progress card in the sidebar."""
        if name in self.jobs or name in self.data or name in self.cleaning:
            self.flash(f"An instance or creation job named {name} already exists")
            return
        row = JobRow(name, lambda: self.cancel_create(name))
        self.job_box.append(row)
        job = {"row": row, "proc": None, "cancelled": False, "t0": time.monotonic(), "tail": [], "token": os.urandom(16).hex()}
        self.jobs[name] = job
        def pump():
            try:
                proc = subprocess.Popen(["incus", "launch", img, name, *extra, "-c", f"{backend.CREATION_TOKEN_KEY}={job['token']}"], stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
            except OSError as e:
                GLib.idle_add(self.create_done, name, 127, str(e))
                return
            job["proc"] = proc
            if job["cancelled"]:
                proc.send_signal(signal.SIGINT)
            buf = b""
            while True:
                chunk = os.read(proc.stdout.fileno(), 4096)
                if not chunk:
                    break
                parts = re.split(rb"[\r\n]", buf + chunk)
                buf = parts.pop()[-65536:]
                for seg in parts:
                    txt = seg.decode(errors="replace").strip()
                    if not txt:
                        continue
                    if not PROGRESS_RE.search(txt):
                        job["tail"] = (job["tail"] + [txt])[-4:]
                    GLib.idle_add(row.feed, txt)
            GLib.idle_add(self.create_done, name, proc.wait(), "")
        threading.Thread(target=pump, daemon=True).start()

    def cancel_create(self, name):
        job = self.jobs.get(name)
        if not job or job["cancelled"]:
            return
        job["cancelled"] = True
        job["row"].cancelling()
        if job["proc"] and job["proc"].poll() is None:
            job["proc"].send_signal(signal.SIGINT)  # what Ctrl-C does: the client cancels its operation and exits
        self.cleaning.add(name)

    def create_done(self, name, rc, err=""):
        job = self.jobs.pop(name, None)
        if not job:
            return False
        self.job_box.remove(job["row"])
        if job["cancelled"] or rc != 0:
            self.cleanup_instance(name, job["token"], patience=120 if job["cancelled"] else 10)
        if self.closing:
            return False
        if job["cancelled"]:
            self.flash("Creation cancelled")
        elif rc != 0:
            self.error_dialog("Create instance", err or "\n".join(job["tail"]) or f"incus launch exited with status {rc}")
        else:
            self.refresh()
            if time.monotonic() - job["t0"] > 8:
                self.notify("Orchard", f"{name} is ready")
        return False

    def cleanup_instance(self, name, token, patience=120):
        """Never remove a same-named guest unless this job's marker matches."""
        def run(args):
            try:
                r = subprocess.run(args, capture_output=True, text=True, timeout=backend.POLL_TIMEOUT)
                return r.returncode, r.stdout, r.stderr
            except subprocess.TimeoutExpired:
                return 1, "", "Incus cleanup request timed out"
        def work():
            try:
                backend.cleanup_loop(name, run, patience=patience, token=token)
            finally:
                GLib.idle_add(lambda: (self.cleaning.discard(name), self.refresh(), False)[2])
        threading.Thread(target=work, daemon=True).start()

    def on_new(self, *_):
        d, area = self.dialog("New Instance", width=540, height=540)
        g = Gtk.Grid(row_spacing=10, column_spacing=14, margin_top=6, margin_bottom=6, margin_start=12, margin_end=12)
        name = Gtk.Entry(placeholder_text="auto-generated if empty", hexpand=True, activates_default=True)
        preset = Gtk.DropDown.new_from_strings([p[0] for p in PRESETS])
        image = Gtk.Entry(placeholder_text="remote:alias, e.g. images:debian/trixie", sensitive=False, hexpand=True)
        vm = Gtk.Switch(halign=Gtk.Align.START)
        secure_boot = Gtk.Switch(halign=Gtk.Align.START, active=True, sensitive=False,
                                 tooltip_text="Disable only for VM images that do not support Secure Boot.")
        d.connect_owned(vm, "notify::active", lambda *_: secure_boot.set_sensitive(vm.get_active()))
        cpu = Gtk.Entry(placeholder_text="optional, e.g. 2")
        mem = Gtk.Entry(placeholder_text="optional, e.g. 1GiB")
        for wdg, nm in ((name, "Instance name"), (preset, "Distribution"), (image, "Image"), (vm, "Virtual machine"), (secure_boot, "Secure Boot"), (cpu, "CPU limit"), (mem, "Memory limit")):
            a11y(wdg, nm)
        def pick(*_):
            p = PRESETS[preset.get_selected()][1]
            image.set_sensitive(not p)
            image.set_text(p)
        d.connect_owned(preset, "notify::selected", pick)
        pick()
        fields = [("Name", name), ("Distribution", preset), ("Image", image), ("Virtual machine", vm), ("Secure Boot", secure_boot), ("CPU limit", cpu), ("Memory limit", mem)]
        for r, (t, wd) in enumerate(fields):
            g.attach(Granite.HeaderLabel(label=t, mnemonic_widget=wd, valign=Gtk.Align.CENTER), 0, r, 1, 1)
            g.attach(wd, 1, r, 1, 1)
        bb = Gtk.Button(label="Browse…", tooltip_text="Search the image server")
        d.connect_owned(bb, "clicked", lambda *_: self.browse_images(
            lambda img, is_vm: (preset.set_selected(len(PRESETS) - 1), image.set_text(img), vm.set_active(is_vm)), parent=d))
        g.attach(bb, 2, 2, 1, 1)
        err = lbl("", "error-text", max_width_chars=48, ellipsize=Pango.EllipsizeMode.END)
        g.attach(err, 0, len(fields), 3, 1)
        area.append(Gtk.ScrolledWindow(child=g, vexpand=True,
                                       hscrollbar_policy=Gtk.PolicyType.NEVER,
                                       propagate_natural_height=True,
                                       min_content_height=300, max_content_height=500))
        d.add_button("Cancel", Gtk.ResponseType.CANCEL)
        ok = d.add_button("Create", Gtk.ResponseType.ACCEPT)
        ok.add_css_class("suggested-action")
        d.set_default_response(Gtk.ResponseType.ACCEPT)

        def problems():
            messages = backend.validate_new(name.get_text(), image.get_text(), cpu.get_text(), mem.get_text())
            if name.get_text().strip() in self.data or name.get_text().strip() in self.jobs:
                messages.append("An instance or creation job with this name already exists.")
            return messages
        def validate(*_):
            msgs = problems()
            nm = name.get_text().strip()
            (name.add_css_class if nm and not valid_name(nm) else name.remove_css_class)("error")
            err.set_text("  ".join(msgs))
            err.set_tooltip_text(" ".join(msgs) or None)
            ok.set_sensitive(not msgs)
        for e_ in (name, image, cpu, mem):
            d.connect_owned(e_, "changed", validate)
        validate()

        def resp(dlg, r):
            if r != Gtk.ResponseType.ACCEPT or problems():
                dlg.destroy()
                return
            img = image.get_text().strip()
            given = name.get_text().strip()
            extra = backend.create_args(vm.get_active(), cpu.get_text(), mem.get_text(), secure_boot.get_active())
            dlg.destroy()
            self.start_create(given or backend.auto_name(img), img, extra)
        d.connect_owned(d, "response", resp)
        d.present()
        name.grab_focus()
