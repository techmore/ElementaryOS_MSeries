/* One machine's content pane: header with tabs, Overview / Console / Settings. */
using Gtk;

const string[] swatch_names = { "Blueberry", "Mint", "Lime", "Banana", "Orange", "Strawberry", "Bubblegum", "Grape" };

public class MachinePage : Gtk.Box {
    public Machine machine { get; construct; }

    public signal void toast (string message);
    public signal void changed ();          // a persisted setting changed
    public signal void remove_requested ();
    public signal void start_requested ();

    private Gtk.Label title;
    private Gtk.Label status_pill;
    private Gtk.Label uptime;
    private Gtk.Label cpu_v;
    private Gtk.Label mem_v;
    private Gtk.Label disk_v;
    private Gtk.Label net_v;
    private Gtk.Label ssh_cmd;
    private Gtk.Image hero_icon;
    private Gtk.Box ready_card;
    private Gtk.Image ready_icon;
    private Gtk.Label ready_title;
    private Gtk.Label ready_detail;
    private Gtk.ToggleButton[] swatches = {};
    private Gtk.Box drop_zone;
    private Gtk.Label drop_title;
    private Gtk.Label drop_detail;
    private Gtk.Button start_button;
    private Gtk.Button stop_button;
    private Gtk.Stack stack;
    private Gtk.Box settings_form;
    private Gtk.Label settings_note;
    private Gtk.Entry name_entry;
    private Gtk.Scale cpu_scale;
    private Gtk.Scale mem_scale;
    private Gtk.Scale disk_scale;
    private Gtk.SpinButton port_spin;
    private Gtk.Label cpu_scale_v;
    private Gtk.Label mem_scale_v;
    private Gtk.Label disk_scale_v;
    private bool loading = false;
    private uint tick = 0;

    public MachinePage (Machine machine) {
        Object (machine: machine, orientation: Gtk.Orientation.VERTICAL, spacing: 0);
    }

    construct {
        hexpand = true;
        stack = new Gtk.Stack ();
        stack.transition_type = Gtk.StackTransitionType.CROSSFADE;
        stack.vexpand = true;
        stack.add_titled (build_overview (), "overview", "Overview");
        stack.add_titled (build_console (), "console", "Console");
        stack.add_titled (build_settings (), "settings", "Settings");

        var header = new Gtk.HeaderBar ();
        header.add_css_class ("flat");
        header.decoration_layout = ":maximize";
        var switcher = new Gtk.StackSwitcher ();
        switcher.stack = stack;
        header.title_widget = switcher;
        var more = new Gtk.MenuButton ();
        more.icon_name = "view-more-symbolic";
        more.tooltip_text = "More actions";
        var pop = new Gtk.Popover ();
        var remove = new Gtk.Button.with_label ("Remove Machine…");
        remove.add_css_class ("flat");
        remove.clicked.connect (() => { pop.popdown (); remove_requested (); });
        pop.child = remove;
        more.popover = pop;
        header.pack_end (more);
        var handle = new Gtk.WindowHandle ();
        handle.child = header;
        append (handle);
        append (stack);

        machine.state_changed.connect (refresh);
        machine.finished.connect ((code) => {
            toast (code > 0 ? "%s stopped with an error (exit %d)".printf (machine.name, code)
                            : "%s stopped".printf (machine.name));
        });
        tick = Timeout.add_seconds (1, () => { update_uptime (); return Source.CONTINUE; });
        refresh ();
    }

    ~MachinePage () {
        if (tick != 0) {
            Source.remove (tick);
        }
    }

    public void show_tab (string name) {
        stack.visible_child_name = name;
    }

    // ---- Overview ---------------------------------------------------------

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
        hero_icon = new Gtk.Image.from_icon_name ("computer");
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
        text.append (title);
        var sub = new Gtk.Label ("Linux ARM64 · hardware accelerated");
        sub.xalign = 0;
        sub.add_css_class ("dim-label");
        text.append (sub);

        var pills = new Gtk.Box (Gtk.Orientation.HORIZONTAL, 8);
        pills.margin_top = 6;
        status_pill = new Gtk.Label ("");
        status_pill.add_css_class ("ml-pill");
        pills.append (status_pill);
        uptime = new Gtk.Label ("");
        uptime.add_css_class ("ml-fineprint");
        pills.append (uptime);
        text.append (pills);
        hero.append (text);
        clamp.append (hero);

        var specs = new Gtk.Grid ();
        specs.column_homogeneous = true;
        specs.row_homogeneous = true;
        specs.column_spacing = 12;
        specs.row_spacing = 12;
        specs.attach (spec_card ("computer-symbolic", out cpu_v, "Processor"), 0, 0);
        specs.attach (spec_card ("media-optical-symbolic", out mem_v, "Memory"), 1, 0);
        specs.attach (spec_card ("drive-harddisk-symbolic", out disk_v, "Disk, grows as used"), 0, 1);
        specs.attach (spec_card ("network-wired-symbolic", out net_v, "Network"), 1, 1);
        clamp.append (specs);

        // Readiness
        ready_card = new Gtk.Box (Gtk.Orientation.HORIZONTAL, 12);
        ready_card.add_css_class ("ml-card");
        ready_card.add_css_class ("ml-spec");
        ready_icon = new Gtk.Image ();
        ready_icon.pixel_size = 24;
        ready_icon.valign = Gtk.Align.START;
        ready_card.append (ready_icon);
        var rt = new Gtk.Box (Gtk.Orientation.VERTICAL, 2);
        rt.hexpand = true;
        ready_title = new Gtk.Label ("");
        ready_title.xalign = 0;
        ready_title.add_css_class ("ml-spec-value");
        ready_detail = new Gtk.Label ("");
        ready_detail.xalign = 0;
        ready_detail.wrap = true;
        ready_detail.add_css_class ("ml-spec-label");
        rt.append (ready_title);
        rt.append (ready_detail);
        ready_card.append (rt);
        clamp.append (ready_card);

        // Connect row
        var connect = new Gtk.Box (Gtk.Orientation.HORIZONTAL, 12);
        connect.add_css_class ("ml-card");
        connect.add_css_class ("ml-spec");
        var term = new Gtk.Image.from_icon_name ("utilities-terminal-symbolic");
        term.pixel_size = 24;
        connect.append (term);
        var ct = new Gtk.Box (Gtk.Orientation.VERTICAL, 0);
        ct.hexpand = true;
        ct.valign = Gtk.Align.CENTER;
        ssh_cmd = new Gtk.Label ("");
        ssh_cmd.xalign = 0;
        ssh_cmd.selectable = true;
        ssh_cmd.add_css_class ("ml-mono");
        var cl = new Gtk.Label ("Connect once the guest is running");
        cl.xalign = 0;
        cl.add_css_class ("ml-spec-label");
        ct.append (ssh_cmd);
        ct.append (cl);
        connect.append (ct);
        var copy = new Gtk.Button.from_icon_name ("edit-copy-symbolic");
        copy.valign = Gtk.Align.CENTER;
        copy.add_css_class ("flat");
        copy.tooltip_text = "Copy command";
        copy.clicked.connect (() => {
            Gdk.Display.get_default ().get_clipboard ().set_text (ssh_cmd.label);
            toast ("Copied SSH command");
        });
        connect.append (copy);
        clamp.append (connect);

        // Installer
        drop_zone = new Gtk.Box (Gtk.Orientation.HORIZONTAL, 14);
        drop_zone.add_css_class ("ml-drop");
        var di = new Gtk.Image.from_icon_name ("media-optical");
        di.pixel_size = 48;
        drop_zone.append (di);
        var dt = new Gtk.Box (Gtk.Orientation.VERTICAL, 2);
        dt.hexpand = true;
        dt.valign = Gtk.Align.CENTER;
        drop_title = new Gtk.Label ("");
        drop_title.xalign = 0;
        drop_title.add_css_class ("title-4");
        drop_detail = new Gtk.Label ("");
        drop_detail.xalign = 0;
        drop_detail.ellipsize = Pango.EllipsizeMode.MIDDLE;
        drop_detail.add_css_class ("dim-label");
        dt.append (drop_title);
        dt.append (drop_detail);
        drop_zone.append (dt);
        var browse = new Gtk.Button.with_label ("Browse…");
        browse.valign = Gtk.Align.CENTER;
        browse.clicked.connect (() => choose_installer.begin ());
        drop_zone.append (browse);
        var eject = new Gtk.Button.from_icon_name ("media-eject-symbolic");
        eject.valign = Gtk.Align.CENTER;
        eject.add_css_class ("flat");
        eject.tooltip_text = "Boot from disk only";
        eject.clicked.connect (() => { machine.installer = null; changed (); refresh (); });
        drop_zone.append (eject);
        clamp.append (drop_zone);

        var target = new Gtk.DropTarget (typeof (Gdk.FileList), Gdk.DragAction.COPY);
        target.enter.connect (() => { drop_zone.add_css_class ("hover"); return Gdk.DragAction.COPY; });
        target.leave.connect (() => drop_zone.remove_css_class ("hover"));
        target.drop.connect ((value) => {
            drop_zone.remove_css_class ("hover");
            foreach (var f in ((Gdk.FileList) value.get_boxed ()).get_files ()) {
                set_installer (f.get_path ());
                return true;
            }
            return false;
        });
        drop_zone.add_controller (target);

        var actions = new Gtk.Box (Gtk.Orientation.HORIZONTAL, 8);
        actions.halign = Gtk.Align.END;
        stop_button = new Gtk.Button.with_label ("Force Stop");
        stop_button.add_css_class ("destructive-action");
        stop_button.clicked.connect (() => machine.stop ());
        actions.append (stop_button);
        start_button = new Gtk.Button.with_label ("Start Machine");
        start_button.add_css_class ("suggested-action");
        start_button.clicked.connect (() => start_requested ());
        actions.append (start_button);
        clamp.append (actions);

        var fine = new Gtk.Label ("Needs QEMU, UEFI firmware and access to /dev/kvm. With an installer attached the machine boots it; remove it with the eject button once the system is installed.");
        fine.wrap = true;
        fine.xalign = 0;
        fine.add_css_class ("ml-fineprint");
        clamp.append (fine);
        return scroller;
    }

    private Gtk.Widget spec_card (string icon_name, out Gtk.Label value, string label) {
        var card = new Gtk.Box (Gtk.Orientation.HORIZONTAL, 12);
        card.add_css_class ("ml-card");
        card.add_css_class ("ml-spec");
        var icon = new Gtk.Image.from_icon_name (icon_name);
        icon.pixel_size = 24;
        card.append (icon);
        var t = new Gtk.Box (Gtk.Orientation.VERTICAL, 0);
        t.valign = Gtk.Align.CENTER;
        value = new Gtk.Label ("");
        value.xalign = 0;
        value.add_css_class ("ml-spec-value");
        var l = new Gtk.Label (label);
        l.xalign = 0;
        l.add_css_class ("ml-spec-label");
        t.append (value);
        t.append (l);
        card.append (t);
        return card;
    }

    // ---- Console ----------------------------------------------------------

    private Gtk.Widget build_console () {
        var box = new Gtk.Box (Gtk.Orientation.VERTICAL, 10);
        box.margin_start = 24;
        box.margin_end = 24;
        box.margin_bottom = 20;
        box.margin_top = 4;

        var view = new Gtk.TextView.with_buffer (machine.log);
        view.editable = false;
        view.cursor_visible = false;
        view.monospace = true;
        view.wrap_mode = Gtk.WrapMode.WORD_CHAR;
        view.top_margin = 12;
        view.bottom_margin = 12;
        view.left_margin = 14;
        view.right_margin = 14;
        view.add_css_class ("ml-console");

        var scroller = new Gtk.ScrolledWindow ();
        scroller.vexpand = true;
        scroller.child = view;
        scroller.add_css_class ("ml-console-frame");
        machine.log.changed.connect (() => {
            Gtk.TextIter end;
            machine.log.get_end_iter (out end);
            var mark = machine.log.create_mark (null, end, false);
            view.scroll_to_mark (mark, 0.0, false, 0, 0);
            machine.log.delete_mark (mark);
        });
        box.append (scroller);

        var bar = new Gtk.Box (Gtk.Orientation.HORIZONTAL, 8);
        var hint = new Gtk.Label ("Launcher and QEMU output");
        hint.hexpand = true;
        hint.xalign = 0;
        hint.add_css_class ("ml-fineprint");
        bar.append (hint);
        var copy = new Gtk.Button.with_label ("Copy");
        copy.clicked.connect (() => {
            Gtk.TextIter s, e;
            machine.log.get_bounds (out s, out e);
            Gdk.Display.get_default ().get_clipboard ().set_text (machine.log.get_text (s, e, false));
            toast ("Console copied");
        });
        bar.append (copy);
        var clear = new Gtk.Button.with_label ("Clear");
        clear.clicked.connect (() => machine.log.text = "");
        bar.append (clear);
        box.append (bar);
        return box;
    }

    // ---- Settings ---------------------------------------------------------

    private Gtk.Widget build_settings () {
        var scroller = new Gtk.ScrolledWindow ();
        scroller.hscrollbar_policy = Gtk.PolicyType.NEVER;
        var clamp = new Gtk.Box (Gtk.Orientation.VERTICAL, 16);
        clamp.margin_start = 32;
        clamp.margin_end = 32;
        clamp.margin_top = 8;
        clamp.margin_bottom = 28;
        clamp.width_request = 460;
        scroller.child = clamp;

        settings_note = new Gtk.Label ("");
        settings_note.wrap = true;
        settings_note.xalign = 0;
        settings_note.add_css_class ("ml-note");
        clamp.append (settings_note);

        settings_form = new Gtk.Box (Gtk.Orientation.VERTICAL, 0);
        settings_form.add_css_class ("ml-card");
        clamp.append (settings_form);

        int cores = (int) get_num_processors ();
        int host_gib = host_memory_gib ();

        name_entry = new Gtk.Entry ();
        name_entry.hexpand = true;
        name_entry.max_length = 40;
        name_entry.changed.connect (() => {
            if (loading) return;
            var n = name_entry.text.strip ();
            machine.name = n == "" ? "Untitled" : n;
            title.label = machine.name;
            changed ();
        });
        settings_form.append (form_row ("Name", null, name_entry));

        var sw_box = new Gtk.Box (Gtk.Orientation.HORIZONTAL, 8);
        for (int i = 0; i < 8; i++) {
            var b = new Gtk.ToggleButton ();
            b.add_css_class ("ml-swatch");
            b.add_css_class ("ml-s-%d".printf (i));
            b.tooltip_text = swatch_names[i];
            int idx = i;
            b.toggled.connect (() => {
                if (loading || !b.active) return;
                machine.color = idx;
                changed (); refresh ();
            });
            if (swatches.length > 0) {
                b.group = swatches[0];
            }
            swatches += b;
            sw_box.append (b);
        }
        settings_form.append (form_row ("Color", null, sw_box));

        cpu_scale = new Gtk.Scale.with_range (Gtk.Orientation.HORIZONTAL, 1, cores, 1);
        cpu_scale_v = new Gtk.Label ("");
        settings_form.append (form_row ("Processors", cpu_scale_v, cpu_scale));
        cpu_scale.value_changed.connect (() => {
            if (loading) return;
            machine.cpus = (int) cpu_scale.get_value ();
            changed (); refresh ();
        });

        mem_scale = new Gtk.Scale.with_range (Gtk.Orientation.HORIZONTAL, 1, int.max (2, host_gib - 2), 1);
        mem_scale_v = new Gtk.Label ("");
        settings_form.append (form_row ("Memory", mem_scale_v, mem_scale));
        mem_scale.value_changed.connect (() => {
            if (loading) return;
            machine.mem_gib = (int) mem_scale.get_value ();
            changed (); refresh ();
        });

        disk_scale = new Gtk.Scale.with_range (Gtk.Orientation.HORIZONTAL, 8, 512, 8);
        disk_scale_v = new Gtk.Label ("");
        settings_form.append (form_row ("Disk size", disk_scale_v, disk_scale));
        disk_scale.value_changed.connect (() => {
            if (loading) return;
            machine.disk_gib = (int) disk_scale.get_value ();
            changed (); refresh ();
        });

        port_spin = new Gtk.SpinButton.with_range (1024, 65535, 1);
        port_spin.value_changed.connect (() => {
            if (loading) return;
            machine.ssh_port = (int) port_spin.get_value ();
            changed (); refresh ();
        });
        settings_form.append (form_row ("SSH port on this Mac", null, port_spin, true));

        foreach (var s in new Gtk.Scale[] { cpu_scale, mem_scale, disk_scale }) {
            s.draw_value = false;
        }
        return scroller;
    }

    private Gtk.Widget form_row (string label, Gtk.Label? value, Gtk.Widget control, bool last = false) {
        var row = new Gtk.Box (Gtk.Orientation.VERTICAL, 6);
        row.add_css_class ("ml-form-row");
        if (!last) {
            row.add_css_class ("ml-form-sep");
        }
        var top = new Gtk.Box (Gtk.Orientation.HORIZONTAL, 12);
        var l = new Gtk.Label (label);
        l.xalign = 0;
        l.hexpand = true;
        top.append (l);
        if (value != null) {
            value.add_css_class ("ml-spec-value");
            top.append (value);
            row.append (top);
            row.append (control);
        } else {
            control.halign = Gtk.Align.END;
            control.hexpand = false;
            if (control is Gtk.Entry) {
                control.hexpand = true;
                control.halign = Gtk.Align.FILL;
                ((Gtk.Entry) control).width_chars = 24;
            }
            top.append (control);
            row.append (top);
        }
        return row;
    }

    private static int host_memory_gib () {
        try {
            string contents;
            FileUtils.get_contents ("/proc/meminfo", out contents);
            foreach (var line in contents.split ("\n")) {
                if (line.has_prefix ("MemTotal:")) {
                    var kb = int64.parse (line.substring (9).strip ().split (" ")[0]);
                    return (int) (kb / 1024 / 1024);
                }
            }
        } catch (Error e) {}
        return 16;
    }

    // ---- State ------------------------------------------------------------

    public void refresh () {
        bool running = machine.running;
        title.label = machine.name;
        cpu_v.label = machine.cpus == 1 ? "1 virtual CPU" : "%d virtual CPUs".printf (machine.cpus);
        mem_v.label = "%d GiB".printf (machine.mem_gib);
        disk_v.label = "%d GiB".printf (machine.disk_gib);
        net_v.label = "Shared (NAT)";
        ssh_cmd.label = "ssh -p %d localhost".printf (machine.ssh_port);

        start_button.visible = !running;
        stop_button.visible = running;
        start_button.sensitive = true;
        start_button.label = machine.installer != null ? "Start Installer" : "Start Machine";

        status_pill.label = running ? "Running" : "Stopped";
        if (running) {
            status_pill.add_css_class ("running");
        } else {
            status_pill.remove_css_class ("running");
        }

        if (machine.installer != null) {
            drop_zone.add_css_class ("chosen");
            drop_title.label = Path.get_basename (machine.installer);
            drop_detail.label = machine.installer;
        } else {
            drop_zone.remove_css_class ("chosen");
            drop_title.label = machine.has_disk () ? "Boots from its disk" : "Choose an installer";
            drop_detail.label = "Drop an ARM64 .iso here, or browse for one.";
        }

        for (int i = 0; i < 8; i++) {
            hero_icon.remove_css_class ("ml-c-%d".printf (i));
        }
        hero_icon.add_css_class ("ml-c-%d".printf (machine.color));
        int64 used = machine.disk_used_bytes ();
        if (used > 0) {
            disk_v.label = "%.1f of %d GiB".printf (used / 1073741824.0, machine.disk_gib);
        }

        var problems = Readiness.problems ();
        ready_card.remove_css_class ("bad");
        if (problems.length == 0) {
            ready_icon.icon_name = "emblem-default-symbolic";
            ready_icon.add_css_class ("ml-ok");
            ready_title.label = "Ready to run";
            ready_detail.label = "QEMU, UEFI firmware and hardware acceleration are available.";
        } else {
            ready_icon.icon_name = "dialog-warning-symbolic";
            ready_icon.remove_css_class ("ml-ok");
            ready_card.add_css_class ("bad");
            ready_title.label = problems.length == 1 ? "One thing to fix" : "%d things to fix".printf (problems.length);
            ready_detail.label = string.joinv ("\n", problems);
        }

        loading = true;
        if (swatches.length == 8) swatches[machine.color.clamp (0, 7)].active = true;
        if (name_entry.text != machine.name) name_entry.text = machine.name;
        cpu_scale.set_value (machine.cpus);
        mem_scale.set_value (machine.mem_gib);
        disk_scale.set_value (machine.disk_gib);
        port_spin.set_value (machine.ssh_port);
        cpu_scale_v.label = "%d".printf (machine.cpus);
        mem_scale_v.label = "%d GiB".printf (machine.mem_gib);
        disk_scale_v.label = "%d GiB".printf (machine.disk_gib);
        loading = false;

        settings_form.sensitive = !running;
        disk_scale.sensitive = !running && !machine.has_disk ();
        settings_note.visible = running || machine.has_disk ();
        settings_note.label = running
            ? "Stop the machine to change its settings."
            : "The disk already exists, so its size is fixed. Other settings apply the next time you start.";
        update_uptime ();
    }

    private void update_uptime () {
        if (machine.running) {
            int64 used = machine.disk_used_bytes ();
            if (used > 0) {
                disk_v.label = "%.1f of %d GiB".printf (used / 1073741824.0, machine.disk_gib);
            }
        }
        if (machine.started == null) {
            uptime.label = "";
            return;
        }
        int64 secs = new DateTime.now_local ().difference (machine.started) / 1000000;
        uptime.label = "Up %02d:%02d:%02d".printf ((int) (secs / 3600), (int) (secs / 60 % 60), (int) (secs % 60));
    }

    private void set_installer (string? path) {
        if (path == null) return;
        machine.installer = path;
        changed ();
        refresh ();
    }

    private async void choose_installer () {
        var chooser = new Gtk.FileDialog ();
        chooser.title = "Choose an ARM64 installer image";
        chooser.accept_label = "Choose";
        var filter = new Gtk.FileFilter ();
        filter.name = "Installer images";
        filter.add_mime_type ("application/x-iso9660-image");
        filter.add_pattern ("*.iso");
        filter.add_pattern ("*.img");
        var filters = new GLib.ListStore (typeof (Gtk.FileFilter));
        filters.append (filter);
        chooser.filters = filters;
        try {
            var file = yield chooser.open ((Gtk.Window) get_root (), null);
            set_installer (file.get_path ());
        } catch (GLib.Error error) {
            // Cancelling the dialog lands here too.
        }
    }
}
