/* Incus panel: sidebar rows, an instance page, and the New Instance dialog. */
using Gtk;

/* Common base so Machine Lab's own machines and Incus instances can share one sidebar list. */
public class SidebarRow : Gtk.ListBoxRow {
    public virtual int group { get { return 0; } }
    public virtual string sort_key { owned get { return ""; } }
    public virtual string header_title { owned get { return ""; } }
}

public class IncusRow : SidebarRow {
    public IncusInstance instance { get; private set; }
    private Gtk.Label name_label;
    private Gtk.Label sub_label;
    private Gtk.Box dot;
    private Gtk.Image icon;

    public override int group { get { return 2; } }
    public override string sort_key { owned get { return instance.name.down (); } }
    public override string header_title { owned get { return "INCUS · CONTAINERS AND VMS"; } }

    public IncusRow (IncusInstance instance) {
        this.instance = instance;
        var box = new Gtk.Box (Gtk.Orientation.HORIZONTAL, 10);
        box.margin_top = 4;
        box.margin_bottom = 4;
        box.margin_start = 6;
        box.margin_end = 6;

        var overlay = new Gtk.Overlay ();
        icon = new Gtk.Image.from_icon_name (instance.is_vm ? "computer" : "package-x-generic");
        icon.pixel_size = 32;
        icon.add_css_class ("ml-row-icon");
        icon.add_css_class (instance.is_vm ? "ml-c-7" : "ml-c-1");
        overlay.child = icon;
        dot = new Gtk.Box (Gtk.Orientation.HORIZONTAL, 0);
        dot.add_css_class ("ml-dot");
        dot.halign = Gtk.Align.END;
        dot.valign = Gtk.Align.END;
        dot.width_request = 10;
        dot.height_request = 10;
        overlay.add_overlay (dot);
        box.append (overlay);

        var text = new Gtk.Box (Gtk.Orientation.VERTICAL, 0);
        text.valign = Gtk.Align.CENTER;
        name_label = new Gtk.Label ("");
        name_label.xalign = 0;
        name_label.ellipsize = Pango.EllipsizeMode.END;
        name_label.add_css_class ("ml-machine-name");
        sub_label = new Gtk.Label ("");
        sub_label.xalign = 0;
        sub_label.ellipsize = Pango.EllipsizeMode.END;
        sub_label.add_css_class ("ml-machine-sub");
        text.append (name_label);
        text.append (sub_label);
        box.append (text);
        child = box;
        update (instance);
    }

    public void update (IncusInstance inst) {
        instance = inst;
        name_label.label = inst.name;
        string where = inst.first_ip != "" ? " · " + inst.first_ip : "";
        sub_label.label = "%s · %s%s".printf (inst.kind_label, inst.status, where);
        if (inst.running) {
            dot.add_css_class ("running");
        } else {
            dot.remove_css_class ("running");
        }
    }
}

public class IncusPage : Gtk.Box {
    public string instance_name { get; construct; }
    public signal void toast (string message);
    public signal void changed ();                 // an action ran: refresh the list now

    private IncusInstance inst;
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
    private Gtk.Button start_btn;
    private Gtk.Button stop_btn;
    private Gtk.Button restart_btn;
    private Gtk.Button pause_btn;
    private Gtk.Button term_btn;
    private Gtk.Button delete_btn;
    private Gtk.TextView log_view;
    private bool busy = false;

    public IncusPage (IncusInstance inst) {
        Object (instance_name: inst.name, orientation: Gtk.Orientation.VERTICAL, spacing: 0);
        this.inst = inst;
        build ();
        update (inst);
    }

    private void build () {
        hexpand = true;
        stack = new Gtk.Stack ();
        stack.transition_type = Gtk.StackTransitionType.CROSSFADE;
        stack.vexpand = true;
        stack.add_titled (build_overview (), "overview", "Overview");
        stack.add_titled (build_log (), "log", "Log");
        stack.notify["visible-child-name"].connect (() => {
            if (stack.visible_child_name == "log") {
                load_log.begin ();
            }
        });

        var header = new Gtk.HeaderBar ();
        header.add_css_class ("flat");
        header.decoration_layout = ":maximize";
        var switcher = new Gtk.StackSwitcher ();
        switcher.stack = stack;
        header.title_widget = switcher;
        var handle = new Gtk.WindowHandle ();
        handle.child = header;
        append (handle);
        append (stack);
    }

    private Gtk.Widget build_overview () {
        var scroller = new Gtk.ScrolledWindow ();
        scroller.hscrollbar_policy = Gtk.PolicyType.NEVER;
        var clamp = new Gtk.Box (Gtk.Orientation.VERTICAL, 20);
        clamp.margin_start = 32;
        clamp.margin_end = 32;
        clamp.margin_top = 8;
        clamp.margin_bottom = 28;
        clamp.width_request = 460;
        scroller.child = clamp;

        var hero = new Gtk.Box (Gtk.Orientation.HORIZONTAL, 18);
        hero_icon = new Gtk.Image.from_icon_name ("package-x-generic");
        hero_icon.pixel_size = 64;
        hero_icon.add_css_class ("ml-hero-icon");
        hero_icon.valign = Gtk.Align.START;
        hero.append (hero_icon);
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
        clamp.append (hero);

        var grid = new Gtk.Grid ();
        grid.column_homogeneous = true;
        grid.row_homogeneous = true;
        grid.column_spacing = 12;
        grid.row_spacing = 12;
        grid.attach (card ("network-wired-symbolic", out ip_v, "Address"), 0, 0);
        grid.attach (card ("media-optical-symbolic", out mem_v, "Memory"), 1, 0);
        grid.attach (card ("drive-harddisk-symbolic", out disk_v, "Disk in use"), 0, 1);
        grid.attach (card ("computer-symbolic", out cpu_v, "Processors"), 1, 1);
        grid.attach (card ("package-x-generic-symbolic", out image_v, "Image"), 0, 2);
        grid.attach (card ("document-open-recent-symbolic", out snap_v, "Snapshots"), 1, 2);
        clamp.append (grid);

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
        pause_btn.clicked.connect (() => act.begin (inst.frozen ? "start" : "pause", inst.frozen ? "Resumed" : "Paused"));
        actions.append (pause_btn);
        restart_btn = new Gtk.Button.with_label ("Restart");
        restart_btn.clicked.connect (() => act.begin ("restart", "Restarted"));
        actions.append (restart_btn);
        stop_btn = new Gtk.Button.with_label ("Stop");
        stop_btn.clicked.connect (() => stop.begin ());
        actions.append (stop_btn);
        term_btn = new Gtk.Button.with_label ("Open Terminal");
        term_btn.clicked.connect (open_terminal);
        actions.append (term_btn);
        start_btn = new Gtk.Button.with_label ("Start");
        start_btn.add_css_class ("suggested-action");
        start_btn.clicked.connect (() => act.begin ("start", "Started"));
        actions.append (start_btn);
        clamp.append (actions);

        var fine = new Gtk.Label ("Managed by Incus. Containers share this Mac's kernel and start in seconds; virtual machines run their own kernel under KVM.");
        fine.wrap = true;
        fine.xalign = 0;
        fine.add_css_class ("ml-fineprint");
        clamp.append (fine);
        return scroller;
    }

    private Gtk.Widget card (string icon_name, out Gtk.Label value, string label) {
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

    private Gtk.Widget build_log () {
        var box = new Gtk.Box (Gtk.Orientation.VERTICAL, 10);
        box.margin_start = 24;
        box.margin_end = 24;
        box.margin_bottom = 20;
        box.margin_top = 4;
        log_view = new Gtk.TextView ();
        log_view.editable = false;
        log_view.monospace = true;
        log_view.wrap_mode = Gtk.WrapMode.WORD_CHAR;
        log_view.top_margin = 12;
        log_view.bottom_margin = 12;
        log_view.left_margin = 14;
        log_view.right_margin = 14;
        log_view.add_css_class ("ml-console");
        var scroller = new Gtk.ScrolledWindow ();
        scroller.vexpand = true;
        scroller.add_css_class ("ml-console-frame");
        scroller.child = log_view;
        box.append (scroller);
        var bar = new Gtk.Box (Gtk.Orientation.HORIZONTAL, 8);
        var hint = new Gtk.Label ("Console log from Incus");
        hint.hexpand = true;
        hint.xalign = 0;
        hint.add_css_class ("ml-fineprint");
        bar.append (hint);
        var refresh = new Gtk.Button.with_label ("Refresh");
        refresh.clicked.connect (() => load_log.begin ());
        bar.append (refresh);
        box.append (bar);
        return box;
    }

    // ---- state ----

    public void update (IncusInstance next) {
        inst = next;
        title.label = inst.name;
        string arch = inst.arch == "aarch64" ? "ARM64 (native)" : (inst.arch == "x86_64" ? "x86-64" : inst.arch);
        subtitle.label = "%s · %s%s".printf (inst.kind_label, arch, inst.image != "" ? " · " + inst.image : "");
        hero_icon.icon_name = inst.is_vm ? "computer" : "package-x-generic";
        hero_icon.remove_css_class ("ml-c-1");
        hero_icon.remove_css_class ("ml-c-7");
        hero_icon.add_css_class (inst.is_vm ? "ml-c-7" : "ml-c-1");
        pill.label = inst.status;
        pill.remove_css_class ("running");
        pill.remove_css_class ("paused");
        if (inst.running) {
            pill.add_css_class ("running");
        } else if (inst.frozen) {
            pill.add_css_class ("paused");
        }

        ip_v.label = inst.ipv4.length > 0 ? string.joinv (", ", inst.ipv4) : (inst.running ? "No address yet" : "Not running");
        mem_v.label = inst.running ? format_size (inst.memory_usage) + (inst.limit_memory != "" ? " of " + inst.limit_memory : " used") : (inst.limit_memory != "" ? "Limit " + inst.limit_memory : "No limit");
        disk_v.label = inst.disk_usage > 0 ? format_size (inst.disk_usage) : "Not reported";
        cpu_v.label = inst.limit_cpu != "" ? "Limited to %s".printf (inst.limit_cpu) : "All cores";
        image_v.label = inst.image != "" ? inst.image : "Unknown";
        snap_v.label = inst.snapshots == 1 ? "1 snapshot" : "%d snapshots".printf (inst.snapshots);

        bool up = inst.running || inst.frozen;
        show (start_btn, !inst.running && !inst.frozen);
        show (stop_btn, up);
        show (restart_btn, inst.running);
        show (pause_btn, up);
        pause_btn.label = inst.frozen ? "Resume" : "Pause";
        show (term_btn, inst.running);
        set_busy (busy);
    }

    /* A button inside a FlowBox hides together with its wrapper so no gap is left. */
    private static void show (Gtk.Button b, bool visible) {
        b.visible = visible;
        var wrapper = b.get_parent ();
        if (wrapper != null) {
            wrapper.visible = visible;
        }
    }

    private void set_busy (bool b) {
        busy = b;
        foreach (var w in new Gtk.Button[] { start_btn, stop_btn, restart_btn, pause_btn, term_btn, delete_btn }) {
            w.sensitive = !b;
        }
    }

    private async void act (string verb, string done) {
        set_busy (true);
        string output;
        int code = yield IncusClient.run ({ verb, inst.name }, out output);
        set_busy (false);
        if (code == 0) {
            toast ("%s %s".printf (inst.name, done.down ()));
        } else {
            toast ("Couldn't %s %s: %s".printf (verb, inst.name, last_line (output)));
        }
        changed ();
    }

    private async void stop () {
        set_busy (true);
        string output;
        int code = yield IncusClient.run ({ "stop", inst.name, "--timeout", "20" }, out output);
        if (code != 0) {
            // A guest that ignores the shutdown request: offer the hard stop.
            code = yield IncusClient.run ({ "stop", inst.name, "--force" }, out output);
        }
        set_busy (false);
        toast (code == 0 ? "%s stopped".printf (inst.name) : "Couldn't stop %s: %s".printf (inst.name, last_line (output)));
        changed ();
    }

    private async void confirm_delete () {
        var dialog = new Gtk.AlertDialog ("Delete “%s”?".printf (inst.name));
        dialog.detail = "This permanently removes the %s and its data, including its snapshots.".printf (inst.kind_label.down ());
        dialog.buttons = { "Cancel", "Delete" };
        dialog.cancel_button = 0;
        dialog.default_button = 0;
        try {
            int choice = yield dialog.choose ((Gtk.Window) get_root (), null);
            if (choice != 1) {
                return;
            }
        } catch (Error e) {
            return;
        }
        set_busy (true);
        string output;
        int code = yield IncusClient.run ({ "delete", inst.name, "--force" }, out output);
        set_busy (false);
        toast (code == 0 ? "Deleted %s".printf (inst.name) : "Couldn't delete %s: %s".printf (inst.name, last_line (output)));
        changed ();
    }

    private void open_terminal () {
        // Names are validated DNS labels, so quoting them is safe.
        string cmd = "incus exec '%s' -- sh -lc 'command -v bash >/dev/null && exec bash -l || exec sh -l'".printf (inst.name);
        try {
            Process.spawn_async (null, { "io.elementary.terminal", "-e", cmd }, null, SpawnFlags.SEARCH_PATH, null, null);
        } catch (Error e) {
            toast ("Couldn't open Terminal: " + e.message);
        }
    }

    private async void load_log () {
        string output;
        int code = yield IncusClient.run ({ "console", inst.name, "--show-log" }, out output);
        log_view.buffer.text = code == 0 ? (output.strip () == "" ? "(the console log is empty)" : output) : "Couldn't read the log: " + output.strip ();
    }

    private static string last_line (string text) {
        var lines = text.strip ().split ("\n");
        return lines.length > 0 ? lines[lines.length - 1] : "";
    }
}

/* New Incus container or virtual machine. */
public class IncusCreateDialog : Gtk.Window {
    public signal void created (string name);

    private Gtk.Entry name_entry;
    private Gtk.ToggleButton vm_toggle;
    private Gtk.DropDown image_drop;
    private Gtk.Entry custom_entry;
    private Gtk.SpinButton cpu_spin;
    private Gtk.SpinButton mem_spin;
    private Gtk.Button create_btn;
    private Gtk.Label problem_label;
    private Gtk.Label error_label;
    private Gtk.TextView log_view;
    private Gtk.ScrolledWindow log_scroll;

    private const string[] IMAGE_NAMES = { "Ubuntu 24.04 LTS", "Debian 12", "Alpine Linux 3.21", "Fedora 43", "Arch Linux" };
    private const string[] IMAGE_ALIASES = { "images:ubuntu/24.04", "images:debian/12", "images:alpine/3.21", "images:fedora/43", "images:archlinux" };

    public IncusCreateDialog (Gtk.Window parent, string suggested_name) {
        Object (transient_for: parent, modal: true, title: "New Incus Instance", default_width: 460, resizable: false);
        var box = new Gtk.Box (Gtk.Orientation.VERTICAL, 14);
        box.margin_start = 24;
        box.margin_end = 24;
        box.margin_top = 20;
        box.margin_bottom = 20;
        child = box;

        var heading = new Gtk.Label ("New Incus Instance");
        heading.add_css_class ("title-2");
        heading.xalign = 0;
        box.append (heading);

        problem_label = new Gtk.Label ("");
        problem_label.wrap = true;
        problem_label.xalign = 0;
        problem_label.add_css_class ("ml-warn");
        problem_label.visible = false;
        box.append (problem_label);

        box.append (field ("Name", name_entry = new Gtk.Entry ()));
        name_entry.text = suggested_name;
        name_entry.max_length = 63;

        var kind = new Gtk.Box (Gtk.Orientation.HORIZONTAL, 0);
        kind.add_css_class ("linked");
        var cont = new Gtk.ToggleButton.with_label ("Container");
        cont.active = true;
        vm_toggle = new Gtk.ToggleButton.with_label ("Virtual machine");
        vm_toggle.group = cont;
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
        custom_entry.placeholder_text = "or an image alias, for example images:alpine/edge";
        box.append (custom_entry);

        cpu_spin = new Gtk.SpinButton.with_range (0, 64, 1);
        box.append (field ("Processor limit (0 = all)", cpu_spin));
        mem_spin = new Gtk.SpinButton.with_range (0, 256, 1);
        box.append (field ("Memory limit in GiB (0 = none)", mem_spin));

        error_label = new Gtk.Label ("");
        error_label.wrap = true;
        error_label.xalign = 0;
        error_label.visible = false;
        error_label.add_css_class ("error");
        box.append (error_label);

        log_view = new Gtk.TextView ();
        log_view.editable = false;
        log_view.monospace = true;
        log_view.add_css_class ("ml-console");
        log_scroll = new Gtk.ScrolledWindow ();
        log_scroll.min_content_height = 110;
        log_scroll.add_css_class ("ml-console-frame");
        log_scroll.child = log_view;
        log_scroll.visible = false;
        box.append (log_scroll);

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

        check_incus.begin ();
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

    private async void check_incus () {
        string? why = yield IncusClient.problem ();
        if (why != null) {
            problem_label.label = why;
            problem_label.visible = true;
            create_btn.sensitive = false;
        }
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
        string[] argv = { "incus", "launch", image, name };
        if (vm_toggle.active) {
            argv += "--vm";
        }
        if (cpu_spin.get_value_as_int () > 0) {
            argv += "-c";
            argv += "limits.cpu=%d".printf (cpu_spin.get_value_as_int ());
        }
        if (mem_spin.get_value_as_int () > 0) {
            argv += "-c";
            argv += "limits.memory=%dGiB".printf (mem_spin.get_value_as_int ());
        }
        error_label.visible = false;
        create_btn.sensitive = false;
        log_scroll.visible = true;
        log_view.buffer.text = "$ " + string.joinv (" ", argv) + "\n";
        try {
            var p = new Subprocess.newv (argv, SubprocessFlags.STDOUT_PIPE | SubprocessFlags.STDERR_MERGE);
            var stream = new DataInputStream (p.get_stdout_pipe ());
            string? line;
            while ((line = yield stream.read_line_async ()) != null) {
                Gtk.TextIter end;
                log_view.buffer.get_end_iter (out end);
                log_view.buffer.insert (ref end, line + "\n", -1);
            }
            yield p.wait_async ();
            if (p.get_if_exited () && p.get_exit_status () == 0) {
                created (name);
                close ();
                return;
            }
            show_error ("Incus could not create the instance. See the log above.");
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
