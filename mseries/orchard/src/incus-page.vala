/* Incus in Orchard: the section's home page (dashboard and tools), one page per instance
 * (Overview / Statistics / Configuration / Logs / Snapshots) and the New Instance dialog.
 * Everything talks to the Incus REST API over the Unix socket through IncusClient. */
using Gtk;

/* Opens a terminal with a shell in the instance, honouring the terminal and shell preferences. */
public class IncusShell : Object {
    public static void open (string name) throws Error {
        var preferences = new Preferences ();
        var terminal = preferences.read ("terminal", "io.elementary.terminal");
        string[] arguments;
        if (terminal == "io.elementary.terminal") arguments = { terminal, "-e", "incus exec %s -- %s".printf (Shell.quote (name), Shell.quote (preferences.shell)) };
        else if (terminal == "xterm") arguments = { terminal, "-e", "incus", "exec", name, "--", preferences.shell };
        else arguments = { terminal, "--", "incus", "exec", name, "--", preferences.shell };
        var environment = Environ.set_variable (Environ.get (), "INCUS_SOCKET", Environment.get_variable ("INCUS_SOCKET") ?? preferences.read ("socket", "/var/lib/incus/unix.socket"), true);
        Process.spawn_async (null, arguments, environment, SpawnFlags.SEARCH_PATH, null, null);
    }
}

/* Shared card helper in the Machines page style. */
namespace OrchardUi {
    public Gtk.Widget spec_card (string icon_name, out Gtk.Label value, string label) {
        var c = new Gtk.Box (Gtk.Orientation.HORIZONTAL, 12);
        c.add_css_class ("ml-card");
        c.add_css_class ("ml-spec");
        var icon = new Gtk.Image.from_icon_name (icon_name);
        icon.pixel_size = 24;
        c.append (icon);
        var t = new Gtk.Box (Gtk.Orientation.VERTICAL, 0);
        t.valign = Gtk.Align.CENTER;
        t.hexpand = true;
        value = new Gtk.Label ("");
        value.xalign = 0;
        value.ellipsize = Pango.EllipsizeMode.END;
        value.add_css_class ("ml-spec-value");
        var l = new Gtk.Label (label);
        l.xalign = 0;
        l.add_css_class ("ml-spec-label");
        t.append (value);
        t.append (l);
        c.append (t);
        return c;
    }

    /* A row inside an ml-card: title, note and a trailing control. */
    public Gtk.Widget action_row (string title, string note, Gtk.Widget? control, bool last = false) {
        var row = new Gtk.Box (Gtk.Orientation.HORIZONTAL, 14);
        row.add_css_class ("ml-form-row");
        if (!last) {
            row.add_css_class ("ml-form-sep");
        }
        var text = new Gtk.Box (Gtk.Orientation.VERTICAL, 2);
        text.hexpand = true;
        var t = new Gtk.Label (title);
        t.xalign = 0;
        t.add_css_class ("ml-spec-value");
        var n = new Gtk.Label (note);
        n.xalign = 0;
        n.wrap = true;
        n.add_css_class ("ml-spec-label");
        text.append (t);
        text.append (n);
        row.append (text);
        if (control != null) {
            control.valign = Gtk.Align.CENTER;
            row.append (control);
        }
        return row;
    }

    public Gtk.Widget page_header (Gtk.Stack stack, Gtk.MenuButton? more) {
        var header = new Gtk.HeaderBar ();
        header.add_css_class ("flat");
        header.decoration_layout = ":maximize";
        var switcher = new Gtk.StackSwitcher ();
        switcher.stack = stack;
        header.title_widget = switcher;
        if (more != null) {
            header.pack_end (more);
        }
        var handle = new Gtk.WindowHandle ();
        handle.child = header;
        return handle;
    }

    public Gtk.Widget console_frame (Gtk.TextView view) {
        view.editable = false;
        view.monospace = true;
        view.wrap_mode = Gtk.WrapMode.WORD_CHAR;
        view.top_margin = 12;
        view.bottom_margin = 12;
        view.left_margin = 14;
        view.right_margin = 14;
        view.add_css_class ("ml-console");
        var scroller = new Gtk.ScrolledWindow ();
        scroller.vexpand = true;
        scroller.add_css_class ("ml-console-frame");
        scroller.child = view;
        return scroller;
    }

    public Gtk.Box scrolled_clamp (out Gtk.ScrolledWindow scroller) {
        scroller = new Gtk.ScrolledWindow ();
        scroller.hscrollbar_policy = Gtk.PolicyType.NEVER;
        var clamp = new Gtk.Box (Gtk.Orientation.VERTICAL, 20);
        clamp.margin_start = 32;
        clamp.margin_end = 32;
        clamp.margin_top = 8;
        clamp.margin_bottom = 28;
        clamp.width_request = 460;
        scroller.child = clamp;
        return clamp;
    }

    public Gtk.Box hero (string icon_name, int color, out Gtk.Image icon, out Gtk.Label title, out Gtk.Label subtitle, out Gtk.Label pill) {
        var hero = new Gtk.Box (Gtk.Orientation.HORIZONTAL, 18);
        icon = new Gtk.Image.from_icon_name (icon_name);
        icon.pixel_size = 64;
        icon.add_css_class ("ml-hero-icon");
        icon.add_css_class ("ml-c-%d".printf (color));
        icon.valign = Gtk.Align.START;
        hero.append (icon);
        var text = new Gtk.Box (Gtk.Orientation.VERTICAL, 4);
        text.hexpand = true;
        text.valign = Gtk.Align.CENTER;
        title = new Gtk.Label ("");
        title.add_css_class ("title-1");
        title.xalign = 0;
        title.ellipsize = Pango.EllipsizeMode.END;
        subtitle = new Gtk.Label ("");
        subtitle.xalign = 0;
        subtitle.wrap = true;
        subtitle.add_css_class ("dim-label");
        pill = new Gtk.Label ("");
        pill.add_css_class ("ml-pill");
        pill.halign = Gtk.Align.START;
        pill.margin_top = 6;
        text.append (title);
        text.append (subtitle);
        text.append (pill);
        hero.append (text);
        return hero;
    }

    public void set_pill (Gtk.Label pill, string text, string? klass) {
        pill.label = text;
        pill.remove_css_class ("running");
        pill.remove_css_class ("paused");
        pill.remove_css_class ("new");
        if (klass != null) {
            pill.add_css_class (klass);
        }
    }

    /* A button inside a FlowBox hides together with its wrapper so no gap is left. */
    public void show (Gtk.Widget b, bool visible) {
        b.visible = visible;
        var wrapper = b.get_parent ();
        if (wrapper != null && wrapper is Gtk.FlowBoxChild) {
            wrapper.visible = visible;
        }
    }

    public async bool confirm (Gtk.Widget from, string title, string detail, string verb, bool destructive = true) {
        var dialog = new Gtk.AlertDialog (title);
        dialog.detail = detail;
        dialog.buttons = { "Cancel", verb };
        dialog.cancel_button = 0;
        dialog.default_button = 0;
        try {
            return (yield dialog.choose (from.get_root () as Gtk.Window, null)) == 1;
        } catch (Error e) {
            return false;
        }
    }
}

/* ---- One instance ---- */

public class IncusInstancePage : Gtk.Box {
    public string instance_name { get; construct; }
    public signal void toast (string message);
    public signal void changed ();                 // an action ran: refresh the list now
    public signal void deleted ();

    private IncusClient client;
    private Instance inst;
    private Gtk.Stack stack;
    private Gtk.Label title;
    private Gtk.Label subtitle;
    private Gtk.Label pill;
    private Gtk.Image hero_icon;
    private Gtk.Label ip_v;
    private Gtk.Label mem_v;
    private Gtk.Label disk_v;
    private Gtk.Label cpu_v;
    private Gtk.Label image_v;
    private Gtk.Label snap_v;
    private Gtk.Label note;
    private Gtk.Button start_btn;
    private Gtk.Button stop_btn;
    private Gtk.Button restart_btn;
    private Gtk.Button pause_btn;
    private Gtk.Button term_btn;
    private Gtk.Button delete_btn;
    private Gtk.Label message;
    private bool busy = false;

    // Statistics
    private Dashboard metrics;
    private Gtk.Label metrics_status;
    private uint metrics_timer = 0;
    private bool metrics_busy = false;

    // Configuration
    private Gtk.TextView configuration;
    private Gtk.Label config_message;
    private string etag = "";
    private Json.Object? original_config = null;
    private bool config_busy = false;
    private bool config_loaded = false;

    // Logs
    private Gtk.DropDown log_file;
    private Gtk.TextView logs;
    private bool logs_loaded = false;

    // Snapshots
    private Gtk.Box snapshot_list;
    private Gtk.Label snapshot_status;

    public IncusInstancePage (IncusClient client, Instance inst) {
        Object (instance_name: inst.name, orientation: Gtk.Orientation.VERTICAL, spacing: 0);
        this.client = client;
        this.inst = inst;
        build ();
        apply_state ();
        map.connect (() => { if (stale) apply_state (); });
    }

    private bool stale = false;

    private void build () {
        hexpand = true;
        stack = new Gtk.Stack ();
        stack.transition_type = Gtk.StackTransitionType.CROSSFADE;
        stack.vexpand = true;
        stack.add_titled (build_overview (), "overview", "Overview");
        stack.add_titled (build_statistics (), "stats", "Statistics");
        stack.add_titled (build_configuration (), "config", "Configuration");
        stack.add_titled (build_logs (), "logs", "Logs");
        stack.add_titled (build_snapshots (), "snapshots", "Snapshots");
        stack.notify["visible-child-name"].connect (on_tab);
        map.connect (on_tab);

        var more = new Gtk.MenuButton ();
        more.icon_name = "view-more-symbolic";
        more.tooltip_text = "More actions";
        var pop = new Gtk.Popover ();
        var menu = new Gtk.Box (Gtk.Orientation.VERTICAL, 0);
        menu.append (menu_item (pop, "Clone Instance…", () => clone_dialog ()));
        menu.append (menu_item (pop, "Export Backup…", () => export_dialog ()));
        menu.append (menu_item (pop, "Mount Folder…", () => new DeviceEditor (window (), client, instance_name, "disk").present ()));
        menu.append (menu_item (pop, "Publish Port…", () => new DeviceEditor (window (), client, instance_name, "proxy").present ()));
        menu.append (menu_item (pop, "Attach Network…", () => new DeviceEditor (window (), client, instance_name, "nic").present ()));
        menu.append (menu_item (pop, "Connect Local Model…", () => connect_model_confirm.begin ()));
        pop.child = menu;
        more.popover = pop;

        append (OrchardUi.page_header (stack, more));
        append (stack);
    }

    private delegate void MenuAction ();

    private Gtk.Widget menu_item (Gtk.Popover pop, string label, owned MenuAction action) {
        var b = new Gtk.Button.with_label (label);
        b.add_css_class ("flat");
        ((Gtk.Label) b.child).xalign = 0;
        b.clicked.connect (() => { pop.popdown (); action (); });
        return b;
    }

    private Gtk.Window? window () {
        return get_root () as Gtk.Window;
    }

    private Gtk.Widget build_overview () {
        Gtk.ScrolledWindow scroller;
        var clamp = OrchardUi.scrolled_clamp (out scroller);
        clamp.append (OrchardUi.hero ("package-x-generic", 1, out hero_icon, out title, out subtitle, out pill));

        var grid = new Gtk.Grid ();
        grid.column_homogeneous = true;
        grid.row_homogeneous = true;
        grid.column_spacing = 12;
        grid.row_spacing = 12;
        grid.attach (OrchardUi.spec_card ("network-wired-symbolic", out ip_v, "Address"), 0, 0);
        grid.attach (OrchardUi.spec_card ("media-optical-symbolic", out mem_v, "Memory"), 1, 0);
        grid.attach (OrchardUi.spec_card ("drive-harddisk-symbolic", out disk_v, "Disk in use"), 0, 1);
        grid.attach (OrchardUi.spec_card ("computer-symbolic", out cpu_v, "Processors"), 1, 1);
        grid.attach (OrchardUi.spec_card ("package-x-generic-symbolic", out image_v, "Image"), 0, 2);
        grid.attach (OrchardUi.spec_card ("document-open-recent-symbolic", out snap_v, "Snapshots"), 1, 2);
        clamp.append (grid);

        note = new Gtk.Label ("");
        note.wrap = true;
        note.xalign = 0;
        note.add_css_class ("ml-note");
        note.visible = false;
        clamp.append (note);

        // A FlowBox so the six actions wrap instead of widening the window.
        var actions = new Gtk.FlowBox ();
        actions.halign = Gtk.Align.END;
        actions.selection_mode = Gtk.SelectionMode.NONE;
        actions.homogeneous = false;
        actions.column_spacing = 8;
        actions.row_spacing = 8;
        actions.max_children_per_line = 6;
        actions.min_children_per_line = 1;
        delete_btn = new Gtk.Button.with_label ("Delete…");
        delete_btn.add_css_class ("destructive-action");
        delete_btn.clicked.connect (() => confirm_delete.begin ());
        actions.append (delete_btn);
        pause_btn = new Gtk.Button.with_label ("Pause");
        pause_btn.clicked.connect (() => act.begin (inst.frozen ? "unfreeze" : "freeze", inst.frozen ? "resumed" : "paused"));
        actions.append (pause_btn);
        restart_btn = new Gtk.Button.with_label ("Restart");
        restart_btn.clicked.connect (() => act.begin ("restart", "restarted"));
        actions.append (restart_btn);
        stop_btn = new Gtk.Button.with_label ("Stop");
        stop_btn.clicked.connect (() => stop.begin ());
        actions.append (stop_btn);
        term_btn = new Gtk.Button.with_label ("Open Terminal");
        term_btn.clicked.connect (open_terminal);
        actions.append (term_btn);
        start_btn = new Gtk.Button.with_label ("Start");
        start_btn.add_css_class ("suggested-action");
        start_btn.clicked.connect (() => act.begin ("start", "started"));
        actions.append (start_btn);
        clamp.append (actions);

        message = new Gtk.Label ("");
        message.wrap = true;
        message.xalign = 0;
        message.add_css_class ("ml-fineprint");
        message.visible = false;
        clamp.append (message);

        var fine = new Gtk.Label ("Managed by Incus. Containers share this Mac's kernel and start in seconds; virtual machines run their own kernel under KVM. Configuration changes are checked against the version Incus reported, so concurrent edits are never overwritten.");
        fine.wrap = true;
        fine.xalign = 0;
        fine.add_css_class ("ml-fineprint");
        clamp.append (fine);
        return scroller;
    }

    private Gtk.Widget build_statistics () {
        var scroller = new Gtk.ScrolledWindow ();
        scroller.hscrollbar_policy = Gtk.PolicyType.NEVER;
        var box = new Gtk.Box (Gtk.Orientation.VERTICAL, 8);
        metrics = new Dashboard ("instance-" + instance_name, false);
        metrics.set_storage ("Root disk measurements belong to this instance. Image and pool accounting is on the Incus page.");
        box.append (metrics);
        metrics_status = new Gtk.Label ("Live statistics are sampled every 3 s while this tab is open.");
        metrics_status.xalign = 0;
        metrics_status.wrap = true;
        metrics_status.margin_start = 32;
        metrics_status.margin_end = 32;
        metrics_status.margin_bottom = 20;
        metrics_status.add_css_class ("ml-fineprint");
        box.append (metrics_status);
        scroller.child = box;
        return scroller;
    }

    private Gtk.Widget build_configuration () {
        var box = new Gtk.Box (Gtk.Orientation.VERTICAL, 10);
        box.margin_start = 24;
        box.margin_end = 24;
        box.margin_bottom = 20;
        box.margin_top = 4;
        var hint = new Gtk.Label ("Instance settings, one key=value per line. Empty values remove a local override; inherited profile settings are preserved. Quoted values use JSON escapes for newlines and quotes.");
        hint.wrap = true;
        hint.xalign = 0;
        hint.add_css_class ("ml-fineprint");
        box.append (hint);
        configuration = new Gtk.TextView ();
        var frame = OrchardUi.console_frame (configuration);
        configuration.editable = true;
        box.append (frame);
        config_message = new Gtk.Label ("");
        config_message.wrap = true;
        config_message.xalign = 0;
        config_message.add_css_class ("ml-fineprint");
        box.append (config_message);
        var bar = new Gtk.Box (Gtk.Orientation.HORIZONTAL, 8);
        bar.halign = Gtk.Align.END;
        var reload = new Gtk.Button.with_label ("Reload");
        reload.clicked.connect (() => load_config.begin ());
        bar.append (reload);
        var apply_restart = new Gtk.Button.with_label ("Stop, Apply and Start");
        apply_restart.clicked.connect (() => {
            OrchardUi.confirm.begin (this, "Apply settings with a restart?", "The instance stops before the changes are applied and starts afterwards. If applying fails it stays stopped so you can review the error.", "Apply and Start", false, (o, r) => {
                if (OrchardUi.confirm.end (r)) apply.begin (true);
            });
        });
        bar.append (apply_restart);
        var apply_btn = new Gtk.Button.with_label ("Apply");
        apply_btn.add_css_class ("suggested-action");
        apply_btn.clicked.connect (() => apply.begin (false));
        bar.append (apply_btn);
        box.append (bar);
        return box;
    }

    private Gtk.Widget build_logs () {
        var box = new Gtk.Box (Gtk.Orientation.VERTICAL, 10);
        box.margin_start = 24;
        box.margin_end = 24;
        box.margin_bottom = 20;
        box.margin_top = 4;
        logs = new Gtk.TextView ();
        box.append (OrchardUi.console_frame (logs));
        var bar = new Gtk.Box (Gtk.Orientation.HORIZONTAL, 8);
        var hint = new Gtk.Label ("The last 1 MiB of the file, read from Incus");
        hint.hexpand = true;
        hint.xalign = 0;
        hint.add_css_class ("ml-fineprint");
        bar.append (hint);
        log_file = new Gtk.DropDown.from_strings ({ "lxc.log", "console.log", "qemu.log", "System journal" });
        log_file.notify["selected"].connect (() => read_log.begin ());
        bar.append (log_file);
        var refresh = new Gtk.Button.with_label ("Refresh");
        refresh.clicked.connect (() => read_log.begin ());
        bar.append (refresh);
        var all = new Gtk.Button.with_label ("Side by Side…");
        all.tooltip_text = "Open the log viewer with several instances";
        all.clicked.connect (() => new LogViewer (window (), client, instance_name).present ());
        bar.append (all);
        box.append (bar);
        return box;
    }

    private Gtk.Widget build_snapshots () {
        Gtk.ScrolledWindow scroller;
        var clamp = OrchardUi.scrolled_clamp (out scroller);
        var card = new Gtk.Box (Gtk.Orientation.VERTICAL, 0);
        card.add_css_class ("ml-card");
        var head = new Gtk.Label ("Snapshots");
        head.xalign = 0;
        head.add_css_class ("title-4");
        head.margin_top = 14;
        head.margin_start = 16;
        head.margin_bottom = 4;
        card.append (head);
        snapshot_list = new Gtk.Box (Gtk.Orientation.VERTICAL, 0);
        card.append (snapshot_list);
        clamp.append (card);
        var actions = new Gtk.Box (Gtk.Orientation.HORIZONTAL, 8);
        actions.halign = Gtk.Align.END;
        var take = new Gtk.Button.with_label ("Take Snapshot");
        take.add_css_class ("suggested-action");
        take.clicked.connect (() => take_snapshot.begin ());
        actions.append (take);
        clamp.append (actions);
        snapshot_status = new Gtk.Label ("A snapshot records the instance's disk. Restoring discards everything changed since.");
        snapshot_status.wrap = true;
        snapshot_status.xalign = 0;
        snapshot_status.add_css_class ("ml-fineprint");
        clamp.append (snapshot_status);
        return scroller;
    }

    // ---- state ----

    /* A hidden page only remembers the newest state; its widgets change once it is on screen. */
    public void update (Instance next) {
        inst = next;
        if (!get_mapped ()) { stale = true; return; }
        apply_state ();
    }

    private void apply_state () {
        stale = false;
        title.label = inst.name;
        string arch = inst.arch == "aarch64" ? "ARM64 (native)" : (inst.arch == "x86_64" ? "x86-64" : inst.arch);
        subtitle.label = "%s%s%s%s".printf (inst.kind_label, arch != "" ? " · " + arch : "", inst.image != "" ? " · " + inst.image : "", inst.ephemeral ? " · ephemeral" : "");
        hero_icon.icon_name = inst.is_vm ? "computer" : "package-x-generic";
        hero_icon.remove_css_class ("ml-c-1");
        hero_icon.remove_css_class ("ml-c-7");
        hero_icon.add_css_class (inst.is_vm ? "ml-c-7" : "ml-c-1");
        OrchardUi.set_pill (pill, inst.status, inst.running ? "running" : (inst.frozen ? "paused" : null));

        ip_v.label = inst.ipv4 != "" ? inst.ipv4 : (inst.running ? "No address yet" : "Not running");
        mem_v.label = inst.running && inst.memory_available ? format_size ((uint64) inst.memory_bytes) + (inst.limit_memory != "" ? " of " + inst.limit_memory : " used") : (inst.limit_memory != "" ? "Limit " + inst.limit_memory : "No limit");
        disk_v.label = inst.disk_available && inst.disk_bytes > 0 ? format_size ((uint64) inst.disk_bytes) : "Not reported";
        cpu_v.label = inst.limit_cpu != "" ? "Limited to %s".printf (inst.limit_cpu) : "All cores";
        image_v.label = inst.image != "" ? inst.image : "Unknown";
        snap_v.label = inst.snapshots == 1 ? "1 snapshot" : "%d snapshots".printf (inst.snapshots);
        note.visible = inst.ephemeral;
        note.label = "This instance is ephemeral: stopping it deletes it. Clone it to keep its data.";

        bool up = inst.running || inst.frozen;
        OrchardUi.show (start_btn, !up);
        OrchardUi.show (stop_btn, up);
        OrchardUi.show (restart_btn, inst.running);
        OrchardUi.show (pause_btn, up);
        pause_btn.label = inst.frozen ? "Resume" : "Pause";
        OrchardUi.show (term_btn, inst.running);
        set_busy (busy);
    }

    private void set_busy (bool b) {
        busy = b;
        foreach (var w in new Gtk.Button[] { start_btn, stop_btn, restart_btn, pause_btn, term_btn, delete_btn }) {
            w.sensitive = !b;
        }
    }

    private void say (string text) {
        message.label = text;
        message.visible = text != "";
    }

    /* start | stop | restart from the command palette. */
    public async void perform (string action) {
        if (action == "stop") yield stop ();
        else yield act (action, action == "start" ? "started" : "restarted");
    }

    private async void act (string action, string done) {
        if (busy) return;
        set_busy (true);
        say ("%s…".printf (action));
        try {
            yield client.change_state (inst.name, action);
            toast ("%s %s".printf (inst.name, done));
            say ("");
        } catch (Error e) {
            toast ("Couldn't %s %s: %s".printf (action, inst.name, e.message));
            say (e.message);
        }
        set_busy (false);
        changed ();
    }

    private async void stop () {
        if (busy) return;
        set_busy (true);
        say ("Stopping…");
        try {
            yield client.change_state (inst.name, "stop");
            toast ("%s stopped".printf (inst.name));
            say ("");
        } catch (Error e) {
            // A guest that ignores the shutdown request: offer the hard stop.
            var force = yield OrchardUi.confirm (this, "Force stop %s?".printf (inst.name), "It did not shut down on its own: " + e.message + "\n\nUnsaved work in the instance may be lost.", "Force Stop");
            if (force) {
                try {
                    yield client.change_state (inst.name, "stop", true);
                    toast ("%s stopped".printf (inst.name));
                    say ("");
                } catch (Error e2) {
                    toast ("Couldn't stop %s: %s".printf (inst.name, e2.message));
                    say (e2.message);
                }
            } else {
                say (e.message);
            }
        }
        set_busy (false);
        changed ();
    }

    private async void confirm_delete () {
        var ok = yield OrchardUi.confirm (this, "Delete “%s”?".printf (inst.name), "This permanently removes the %s and its data, including its snapshots.".printf (inst.kind_label.down ()), "Delete");
        if (!ok) return;
        set_busy (true);
        try {
            var current = yield client.inspect_instance (inst.name);
            var meta = current.get_object_member ("metadata");
            bool ephemeral = meta.get_boolean_member_with_default ("ephemeral", false);
            if (meta.get_string_member ("status") != "Stopped") {
                yield client.change_state (inst.name, "stop", true);
            }
            // An ephemeral instance is gone once stopped.
            if (!ephemeral || meta.get_string_member ("status") == "Stopped") {
                yield client.delete_instance (inst.name);
            }
            toast ("Deleted %s".printf (inst.name));
            deleted ();
        } catch (Error e) {
            toast ("Couldn't delete %s: %s".printf (inst.name, e.message));
            say (e.message);
        }
        set_busy (false);
        changed ();
    }

    private void open_terminal () {
        try {
            IncusShell.open (inst.name);
        } catch (Error e) {
            toast ("Couldn't open Terminal: " + e.message);
        }
    }

    // ---- tabs ----

    private void on_tab () {
        if (!get_mapped ()) return;
        switch (stack.visible_child_name) {
        case "stats":
            refresh_metrics.begin ();
            if (metrics_timer == 0) {
                metrics_timer = Timeout.add_seconds (3, () => {
                    // Stops itself as soon as the tab or the page is out of sight.
                    if (!get_mapped () || stack.visible_child_name != "stats") {
                        metrics_timer = 0;
                        return Source.REMOVE;
                    }
                    refresh_metrics.begin ();
                    return Source.CONTINUE;
                });
            }
            break;
        case "config":
            if (!config_loaded) load_config.begin ();
            break;
        case "logs":
            if (!logs_loaded) read_log.begin ();
            break;
        case "snapshots":
            fill_snapshots.begin ();
            break;
        }
    }

    private async void refresh_metrics () {
        if (metrics_busy) return;
        metrics_busy = true;
        try {
            var response = yield client.call ("GET", "/1.0/instances/" + Uri.escape_string (inst.name, null, false) + "/state");
            var state = response.get_object_member ("metadata");
            var data = new Json.Object ();
            data.set_string_member ("name", inst.name);
            data.set_string_member ("status", state.get_string_member ("status"));
            data.set_object_member ("state", state);
            metrics.update ({ Instance.from_json (data) });
            metrics_status.label = "Live statistics, sampled every 3 s while this tab is open. Updated " + new DateTime.now_local ().format ("%H:%M:%S") + ".";
        } catch (Error e) {
            metrics_status.label = "Statistics are stale: " + e.message;
        }
        metrics_busy = false;
    }

    private async void load_config () {
        config_message.label = "Loading…";
        try {
            var response = yield client.inspect_instance (inst.name);
            var data = response.get_object_member ("metadata");
            etag = response.get_string_member_with_default ("_orchard_etag", "");
            original_config = data.get_object_member ("config");
            configuration.buffer.text = ConfigText.render (original_config, true);
            config_message.label = "Loaded. Changes use Incus version checks so concurrent edits are not overwritten.";
            config_loaded = true;
        } catch (Error e) {
            config_message.label = e.message;
        }
    }

    private async void apply (bool restart) {
        if (config_busy) return;
        config_busy = true;
        try {
            if (original_config == null || etag == "") throw new IOError.FAILED ("Reload the configuration before applying changes.");
            var config = ConfigText.parse (configuration.buffer.text, true);
            if (restart) yield client.update_with_restart (inst.name, config, etag);
            else yield client.update_instance (inst.name, config, etag);
            yield load_config ();
            config_message.label = restart ? "Configuration applied and the instance started." : "Configuration applied. Incus reports if a setting needs a restart.";
            toast ("Applied the configuration of %s".printf (inst.name));
        } catch (Error e) {
            config_message.label = e.message;
        }
        config_busy = false;
        changed ();
    }

    private async void read_log () {
        logs_loaded = true;
        try {
            var item = (Gtk.StringObject) log_file.selected_item;
            var text = item.string == "System journal" ? yield client.journal (inst.name) : yield client.read_log (inst.name, item.string);
            logs.buffer.text = text.strip () == "" ? "(the log is empty)" : text;
        } catch (Error e) {
            logs.buffer.text = "Couldn't read the log: " + e.message;
        }
    }

    // ---- snapshots ----

    private async void fill_snapshots () {
        Gtk.Widget? w;
        while ((w = snapshot_list.get_first_child ()) != null) snapshot_list.remove (w);
        try {
            var snaps = yield client.list_snapshots (inst.name);
            if (snaps.length == 0) {
                var empty = new Gtk.Label ("No snapshots yet.");
                empty.xalign = 0;
                empty.add_css_class ("ml-form-row");
                empty.add_css_class ("dim-label");
                snapshot_list.append (empty);
            }
            for (int i = 0; i < snaps.length; i++) {
                var s = snaps[i];
                var buttons = new Gtk.Box (Gtk.Orientation.HORIZONTAL, 6);
                var restore = new Gtk.Button.with_label ("Restore");
                restore.clicked.connect (() => confirm_restore.begin (s));
                buttons.append (restore);
                var remove = new Gtk.Button.from_icon_name ("edit-delete-symbolic");
                remove.tooltip_text = "Delete snapshot";
                remove.add_css_class ("flat");
                remove.clicked.connect (() => confirm_delete_snapshot.begin (s));
                buttons.append (remove);
                snapshot_list.append (OrchardUi.action_row (s, "Disk snapshot", buttons, i == snaps.length - 1));
            }
        } catch (Error e) {
            var err = new Gtk.Label (e.message);
            err.wrap = true;
            err.xalign = 0;
            err.add_css_class ("ml-form-row");
            snapshot_list.append (err);
        }
    }

    private async void take_snapshot () {
        var snap = "snap-" + new DateTime.now_local ().format ("%Y%m%d-%H%M%S");
        snapshot_status.label = "Taking %s…".printf (snap);
        try {
            yield client.create_snapshot (inst.name, snap);
            toast ("Created %s on %s".printf (snap, inst.name));
            snapshot_status.label = "Created %s.".printf (snap);
        } catch (Error e) {
            toast (e.message);
            snapshot_status.label = e.message;
        }
        yield fill_snapshots ();
        changed ();
    }

    private async void confirm_restore (string snap) {
        var ok = yield OrchardUi.confirm (this, "Restore %s to %s?".printf (inst.name, snap), "Changes made after this snapshot will be lost.", "Restore");
        if (!ok) return;
        try {
            yield client.restore_snapshot (inst.name, snap);
            toast ("Restored %s to %s".printf (inst.name, snap));
        } catch (Error e) {
            toast (e.message);
            snapshot_status.label = e.message;
        }
        changed ();
    }

    private async void confirm_delete_snapshot (string snap) {
        var ok = yield OrchardUi.confirm (this, "Delete snapshot %s?".printf (snap), "The snapshot is permanently removed.", "Delete");
        if (!ok) return;
        try {
            yield client.delete_snapshot (inst.name, snap);
            toast ("Deleted snapshot %s".printf (snap));
        } catch (Error e) {
            toast (e.message);
        }
        yield fill_snapshots ();
        changed ();
    }

    // ---- menu actions ----

    private void clone_dialog () {
        var dialog = new Gtk.Window ();
        dialog.transient_for = window ();
        dialog.modal = true;
        dialog.title = "Clone " + inst.name;
        dialog.default_width = 400;
        dialog.resizable = false;
        var box = new Gtk.Box (Gtk.Orientation.VERTICAL, 14);
        box.margin_top = 20;
        box.margin_bottom = 20;
        box.margin_start = 24;
        box.margin_end = 24;
        var heading = new Gtk.Label ("Clone Instance");
        heading.add_css_class ("title-2");
        heading.xalign = 0;
        box.append (heading);
        var name = new Gtk.Entry ();
        name.placeholder_text = "New instance name";
        name.text = inst.name + "-copy";
        box.append (name);
        var error_label = new Gtk.Label ("");
        error_label.wrap = true;
        error_label.xalign = 0;
        error_label.visible = false;
        error_label.add_css_class ("error");
        box.append (error_label);
        var buttons = new Gtk.Box (Gtk.Orientation.HORIZONTAL, 8);
        buttons.halign = Gtk.Align.END;
        var cancel = new Gtk.Button.with_label ("Cancel");
        cancel.clicked.connect (() => dialog.close ());
        buttons.append (cancel);
        var create = new Gtk.Button.with_label ("Clone");
        create.add_css_class ("suggested-action");
        create.clicked.connect (() => {
            var n = name.text.strip ();
            if (!IncusClient.valid_name (n)) {
                error_label.label = "Use lower-case letters, digits and hyphens, starting with a letter (up to 63 characters).";
                error_label.visible = true;
                return;
            }
            create.sensitive = false;
            toast ("Cloning %s to %s…".printf (inst.name, n));
            client.clone_instance.begin (inst.name, n, (o, r) => {
                try {
                    client.clone_instance.end (r);
                    dialog.close ();
                    toast ("Cloned %s to %s".printf (inst.name, n));
                    changed ();
                } catch (Error e) {
                    error_label.label = e.message;
                    error_label.visible = true;
                    create.sensitive = true;
                }
            });
        });
        buttons.append (create);
        box.append (buttons);
        dialog.child = box;
        dialog.present ();
    }

    private void export_dialog () {
        var chooser = new Gtk.FileDialog ();
        chooser.title = "Export Incus backup";
        chooser.initial_name = inst.name + ".tar.gz";
        chooser.save.begin (window (), null, (o, r) => {
            try {
                var file = chooser.save.end (r);
                export_backup.begin (file);
            } catch (Error e) {
                // cancelled
            }
        });
    }

    private async void export_backup (File destination) {
        toast ("Exporting a backup of %s…".printf (inst.name));
        say ("Exporting backup…");
        try {
            yield client.export_instance (inst.name, destination);
            toast ("Saved backup to " + destination.get_parse_name ());
            say ("");
        } catch (Error e) {
            toast (e.message);
            say (e.message);
        }
    }

    private async void connect_model_confirm () {
        var ok = yield OrchardUi.confirm (this, "Connect this instance to your model endpoint?", "Orchard replaces localhost with the Incus bridge gateway. The model server must listen on that bridge address. Only the endpoint is injected; desktop API keys stay in the keyring.", "Connect", false);
        if (!ok) return;
        try {
            var preferences = new Preferences ();
            if (preferences.read ("model-enabled", "true") != "true") throw new IOError.FAILED ("Enable and save a model endpoint first (Incus › Local AI Models).");
            var url = yield ModelBridge.attach (client, inst.name, preferences.read ("model-endpoint", "http://127.0.0.1:11434/v1"));
            config_loaded = false;
            toast ("Model endpoint configured: " + url);
            say ("Model endpoint configured: " + url + ". Server binding and guest access must be verified; no API key was injected.");
        } catch (Error e) {
            toast (e.message);
            say (e.message);
        }
    }

    public override void dispose () {
        if (metrics_timer != 0) {
            Source.remove (metrics_timer);
            metrics_timer = 0;
        }
        base.dispose ();
    }
}

/* ---- The Incus section's home page ---- */

public class IncusHomePage : Gtk.Box {
    public signal void toast (string message);
    public signal void create_requested ();
    public signal void tool_requested (string action);   // resources, image-pull, mounts, system, models, sandboxes, logs, preferences

    private IncusClient client;
    private Gtk.Stack stack;
    private Gtk.Label title;
    private Gtk.Label subtitle;
    private Gtk.Label pill;
    private Gtk.Image hero_icon;
    private Gtk.Label running_v;
    private Gtk.Label total_v;
    private Gtk.Label memory_v;
    private Gtk.Label version_v;
    private Gtk.Label problem;
    private Dashboard dashboard;
    private int64 last_storage_refresh = 0;
    private bool storage_busy = false;
    private bool version_known = false;
    private string memory_text = "";
    private string? last_error = null;

    public IncusHomePage (IncusClient client) {
        Object (orientation: Gtk.Orientation.VERTICAL, spacing: 0);
        this.client = client;
        map.connect (() => { if (memory_text != "") memory_v.label = memory_text; });
        hexpand = true;
        stack = new Gtk.Stack ();
        stack.transition_type = Gtk.StackTransitionType.CROSSFADE;
        stack.vexpand = true;
        stack.add_titled (build_overview (), "overview", "Overview");
        stack.add_titled (build_statistics (), "stats", "Statistics");
        append (OrchardUi.page_header (stack, null));
        append (stack);
        title.label = "Incus";
        subtitle.label = "Containers and virtual machines on this Mac";
        OrchardUi.set_pill (pill, "Connecting…", null);
    }

    private Gtk.Widget build_overview () {
        Gtk.ScrolledWindow scroller;
        var clamp = OrchardUi.scrolled_clamp (out scroller);
        clamp.append (OrchardUi.hero ("orchard-incus-symbolic", 2, out hero_icon, out title, out subtitle, out pill));

        problem = new Gtk.Label ("");
        problem.wrap = true;
        problem.xalign = 0;
        problem.add_css_class ("ml-warn");
        problem.visible = false;
        clamp.append (problem);

        var grid = new Gtk.Grid ();
        grid.column_homogeneous = true;
        grid.row_homogeneous = true;
        grid.column_spacing = 12;
        grid.row_spacing = 12;
        grid.attach (OrchardUi.spec_card ("media-playback-start-symbolic", out running_v, "Running"), 0, 0);
        grid.attach (OrchardUi.spec_card ("package-x-generic-symbolic", out total_v, "Instances"), 1, 0);
        grid.attach (OrchardUi.spec_card ("media-optical-symbolic", out memory_v, "Memory in use"), 0, 1);
        grid.attach (OrchardUi.spec_card ("applications-system-symbolic", out version_v, "Incus"), 1, 1);
        clamp.append (grid);

        var manage = new Gtk.Box (Gtk.Orientation.VERTICAL, 0);
        manage.add_css_class ("ml-card");
        var head = new Gtk.Label ("Manage");
        head.xalign = 0;
        head.add_css_class ("title-4");
        head.margin_top = 14;
        head.margin_start = 16;
        head.margin_bottom = 4;
        manage.append (head);
        manage.append (tool_row ("Images, networks and profiles", "Browse and edit Incus resources, pull images and launch from them.", "Open…", "resources"));
        manage.append (tool_row ("Download an image", "Fetch a system image from a simplestreams server ahead of time.", "Download…", "image-pull"));
        manage.append (tool_row ("Instance mounts", "Every folder and volume mounted into an instance, with removal.", "Open…", "mounts"));
        manage.append (tool_row ("Logs side by side", "Runtime, console and journal logs of several instances at once.", "Open…", "logs"));
        manage.append (tool_row ("Local AI models", "Bookmark OpenAI-compatible model endpoints and chat with them.", "Open…", "models"));
        manage.append (tool_row ("Model sandboxes", "Isolated containers or VMs wired to a local model endpoint.", "Open…", "sandboxes"));
        manage.append (tool_row ("Incus system", "Server properties, host resources and the daemon journal.", "Open…", "system"));
        manage.append (tool_row ("Preferences", "Shell, terminal application and the Incus socket.", "Open…", "preferences", true));
        clamp.append (manage);

        var actions = new Gtk.Box (Gtk.Orientation.HORIZONTAL, 8);
        actions.halign = Gtk.Align.END;
        var refresh = new Gtk.Button.with_label ("Refresh");
        refresh.clicked.connect (() => refresh_requested ());
        actions.append (refresh);
        var create = new Gtk.Button.with_label ("New Instance…");
        create.add_css_class ("suggested-action");
        create.clicked.connect (() => create_requested ());
        actions.append (create);
        clamp.append (actions);

        var fine = new Gtk.Label ("Press Ctrl+K for the command palette: search instances, images, networks and profiles, or type an action such as “stop web” or “shell api”.");
        fine.wrap = true;
        fine.xalign = 0;
        fine.add_css_class ("ml-fineprint");
        clamp.append (fine);
        return scroller;
    }

    public signal void refresh_requested ();

    private Gtk.Widget tool_row (string t, string n, string label, string action, bool last = false) {
        var b = new Gtk.Button.with_label (label);
        b.clicked.connect (() => tool_requested (action));
        return OrchardUi.action_row (t, n, b, last);
    }

    private Gtk.Widget build_statistics () {
        var scroller = new Gtk.ScrolledWindow ();
        scroller.hscrollbar_policy = Gtk.PolicyType.NEVER;
        dashboard = new Dashboard ("aggregate", false);
        scroller.child = dashboard;
        return scroller;
    }

    /* Called after every successful listing. */
    public void update (Instance[] items) {
        int running = 0;
        int64 memory = 0;
        foreach (var i in items) {
            if (i.running) running++;
            if (i.running && i.memory_available) memory += i.memory_bytes;
        }
        problem.visible = false;
        last_error = null;
        OrchardUi.set_pill (pill, running > 0 ? "%d running".printf (running) : (items.length == 0 ? "Empty" : "All stopped"), running > 0 ? "running" : null);
        running_v.label = running == 1 ? "1 instance" : "%d instances".printf (running);
        total_v.label = "%d container%s · %d VM%s".printf (count (items, false), count (items, false) == 1 ? "" : "s", count (items, true), count (items, true) == 1 ? "" : "s");
        memory_text = running > 0 ? format_size ((uint64) memory) : "Nothing running";
        if (get_mapped ()) memory_v.label = memory_text;
        dashboard.update (items);
        if (!version_known) read_version.begin ();
        if (get_monotonic_time () - last_storage_refresh > 60000000) refresh_storage.begin ();
    }

    private static int count (Instance[] items, bool vm) {
        int n = 0;
        foreach (var i in items) if (i.is_vm == vm) n++;
        return n;
    }

    public void set_error (string error) {
        if (last_error == error) return;   // the same failure every poll must not relayout every poll
        last_error = error;
        problem.label = "Incus is not reachable: " + error + "\n\nInstall the incus package, start it with “sudo systemctl start incus” and add your user to the incus-admin group. The socket path can be changed in Preferences.";
        problem.visible = true;
        OrchardUi.set_pill (pill, "Not reachable", null);
        running_v.label = "—";
        total_v.label = "—";
        memory_v.label = "—";
        dashboard.set_error (error);
    }

    private async void read_version () {
        try {
            var response = yield client.call ("GET", "/1.0");
            var env = response.get_object_member ("metadata").get_object_member ("environment");
            version_v.label = "Incus %s".printf (env.get_string_member_with_default ("server_version", "?"));
            version_known = true;
        } catch (Error e) {
            version_v.label = "Version unknown";
        }
    }

    private async void refresh_storage () {
        if (storage_busy) return;
        storage_busy = true;
        try {
            var text = new StringBuilder ();
            var images = yield client.call ("GET", "/1.0/images?recursion=1");
            int64 sizes = 0;
            foreach (var node in images.get_array_member ("metadata").get_elements ()) sizes += node.get_object ().get_int_member_with_default ("size", 0);
            text.append ("Cached images · " + format_size ((uint64) sizes) + " (reported image sizes)\n");
            var pools = yield client.call ("GET", "/1.0/storage-pools?recursion=1");
            foreach (var node in pools.get_array_member ("metadata").get_elements ()) {
                var name = node.get_object ().get_string_member ("name");
                var resources = yield client.call ("GET", "/1.0/storage-pools/" + Uri.escape_string (name, null, false) + "/resources");
                var space = resources.get_object_member ("metadata").get_object_member ("space");
                text.append ("Pool " + name + " · " + format_size ((uint64) space.get_int_member_with_default ("used", 0)) + " used of " + format_size ((uint64) space.get_int_member_with_default ("total", 0)) + "\n");
            }
            dashboard.set_storage (text.str);
        } catch (Error e) {
            dashboard.set_storage ("Storage accounting unavailable: " + e.message);
        }
        last_storage_refresh = get_monotonic_time ();
        storage_busy = false;
    }
}

/* ---- New Incus container or virtual machine ---- */

public class IncusCreateDialog : Gtk.Window {
    public signal void created (string name);

    private IncusClient client;
    private Gtk.Entry name_entry;
    private Gtk.ToggleButton vm_toggle;
    private Gtk.DropDown image_drop;
    private Gtk.Entry custom_entry;
    private Gtk.SpinButton cpu_spin;
    private Gtk.SpinButton mem_spin;
    private Gtk.CheckButton ephemeral;
    private Gtk.TextView environment;
    private Gtk.TextView labels;
    private Gtk.Button create_btn;
    private Gtk.Label error_label;
    private Gtk.Label progress;

    private const string[] IMAGE_NAMES = { "Ubuntu 24.04 LTS", "Debian 12", "Alpine Linux 3.21", "Fedora 43", "Arch Linux" };
    private const string[] IMAGE_ALIASES = { "ubuntu/24.04", "debian/12", "alpine/3.21", "fedora/43", "archlinux" };

    public IncusCreateDialog (Gtk.Window parent, IncusClient client, string suggested_name, string initial_image = "", bool initial_vm = false) {
        Object (transient_for: parent, modal: true, title: "New Incus Instance", default_width: 480, resizable: false);
        this.client = client;
        var scroller = new Gtk.ScrolledWindow ();
        scroller.propagate_natural_height = true;
        scroller.max_content_height = 700;
        scroller.hscrollbar_policy = Gtk.PolicyType.NEVER;
        var box = new Gtk.Box (Gtk.Orientation.VERTICAL, 14);
        box.margin_start = 24;
        box.margin_end = 24;
        box.margin_top = 20;
        box.margin_bottom = 20;
        scroller.child = box;
        child = scroller;

        var heading = new Gtk.Label ("New Incus Instance");
        heading.add_css_class ("title-2");
        heading.xalign = 0;
        box.append (heading);

        box.append (field ("Name", name_entry = new Gtk.Entry ()));
        name_entry.text = suggested_name;
        name_entry.max_length = 63;

        var kind = new Gtk.Box (Gtk.Orientation.HORIZONTAL, 0);
        kind.add_css_class ("linked");
        var cont = new Gtk.ToggleButton.with_label ("Container");
        cont.active = !initial_vm;
        vm_toggle = new Gtk.ToggleButton.with_label ("Virtual machine");
        vm_toggle.group = cont;
        vm_toggle.active = initial_vm;
        kind.append (cont);
        kind.append (vm_toggle);
        box.append (field ("Type", kind));

        // Built by hand: from_strings() expects a NULL-terminated array, which a const array is not.
        var names = new Gtk.StringList (null);
        foreach (var n in IMAGE_NAMES) {
            names.append (n);
        }
        image_drop = new Gtk.DropDown (names, null);
        box.append (field ("Image", image_drop));
        custom_entry = new Gtk.Entry ();
        custom_entry.placeholder_text = "or an alias from images.linuxcontainers.org, or local:<fingerprint>";
        custom_entry.text = initial_image;
        box.append (custom_entry);

        cpu_spin = new Gtk.SpinButton.with_range (0, 64, 1);
        box.append (field ("Processor limit (0 = all)", cpu_spin));
        mem_spin = new Gtk.SpinButton.with_range (0, 256, 1);
        box.append (field ("Memory limit in GiB (0 = none)", mem_spin));
        ephemeral = new Gtk.CheckButton.with_label ("Delete automatically after stopping (ephemeral)");
        box.append (ephemeral);

        var advanced = new Gtk.Expander ("Environment and labels");
        var adv = new Gtk.Box (Gtk.Orientation.VERTICAL, 8);
        adv.margin_top = 8;
        var env_label = new Gtk.Label ("Environment variables, KEY=value per line");
        env_label.xalign = 0;
        env_label.add_css_class ("ml-spec-label");
        adv.append (env_label);
        environment = new Gtk.TextView ();
        environment.monospace = true;
        var env_scroll = new Gtk.ScrolledWindow ();
        env_scroll.min_content_height = 60;
        env_scroll.add_css_class ("ml-console-frame");
        env_scroll.child = environment;
        adv.append (env_scroll);
        var lab_label = new Gtk.Label ("Labels, key=value per line (stored as user.key)");
        lab_label.xalign = 0;
        lab_label.add_css_class ("ml-spec-label");
        adv.append (lab_label);
        labels = new Gtk.TextView ();
        labels.monospace = true;
        var lab_scroll = new Gtk.ScrolledWindow ();
        lab_scroll.min_content_height = 60;
        lab_scroll.add_css_class ("ml-console-frame");
        lab_scroll.child = labels;
        adv.append (lab_scroll);
        advanced.child = adv;
        box.append (advanced);

        error_label = new Gtk.Label ("");
        error_label.wrap = true;
        error_label.xalign = 0;
        error_label.visible = false;
        error_label.add_css_class ("error");
        box.append (error_label);

        progress = new Gtk.Label ("Images come from images.linuxcontainers.org; the first launch of an image downloads it, which can take a few minutes.");
        progress.wrap = true;
        progress.xalign = 0;
        progress.add_css_class ("ml-fineprint");
        box.append (progress);

        var buttons = new Gtk.Box (Gtk.Orientation.HORIZONTAL, 8);
        buttons.halign = Gtk.Align.END;
        var cancel = new Gtk.Button.with_label ("Cancel");
        cancel.clicked.connect (() => close ());
        buttons.append (cancel);
        create_btn = new Gtk.Button.with_label ("Create");
        create_btn.add_css_class ("suggested-action");
        create_btn.clicked.connect (() => create.begin ());
        buttons.append (create_btn);
        box.append (buttons);
    }

    private Gtk.Widget field (string label, Gtk.Widget control) {
        var row = new Gtk.Box (Gtk.Orientation.HORIZONTAL, 12);
        var l = new Gtk.Label (label);
        l.xalign = 0;
        l.hexpand = true;
        row.append (l);
        control.halign = Gtk.Align.END;
        control.hexpand = false;
        if (control is Gtk.Entry) {
            control.hexpand = true;
            control.halign = Gtk.Align.FILL;
        }
        row.append (control);
        return row;
    }

    private bool lines_into (Gtk.TextView view, string prefix, Json.Object config, string what, bool user_prefix = false) {
        foreach (var line in view.buffer.text.split ("\n")) {
            if (line.strip () == "") continue;
            int separator = line.index_of_char ('=');
            if (separator <= 0) {
                show_error ("Use KEY=value for each %s.".printf (what));
                return false;
            }
            var key = line.substring (0, separator).strip ();
            if (user_prefix && !key.has_prefix ("user.")) key = "user." + key;
            config.set_string_member (prefix + key, line.substring (separator + 1));
        }
        return true;
    }

    private async void create () {
        string name = name_entry.text.strip ();
        if (!IncusClient.valid_name (name)) {
            show_error ("Use lower-case letters, digits and hyphens, starting with a letter (up to 63 characters).");
            return;
        }
        string image = custom_entry.text.strip ();
        if (image == "") {
            image = IMAGE_ALIASES[image_drop.selected];
        }
        var config = new Json.Object ();
        if (!lines_into (environment, "environment.", config, "environment variable")) return;
        if (!lines_into (labels, "", config, "label", true)) return;
        if (cpu_spin.get_value_as_int () > 0) config.set_string_member ("limits.cpu", cpu_spin.get_value_as_int ().to_string ());
        if (mem_spin.get_value_as_int () > 0) config.set_string_member ("limits.memory", "%dGiB".printf (mem_spin.get_value_as_int ()));
        error_label.visible = false;
        create_btn.sensitive = false;
        progress.label = "Creating %s from %s… The first launch of an image downloads it.".printf (name, image);
        try {
            yield client.create_instance (name, image, vm_toggle.active, config, ephemeral.active);
            created (name);
            close ();
            return;
        } catch (Error e) {
            show_error (e.message);
        }
        create_btn.sensitive = true;
    }

    private void show_error (string message) {
        error_label.label = message;
        error_label.visible = true;
    }
}
