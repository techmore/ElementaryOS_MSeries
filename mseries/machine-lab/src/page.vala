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
    private Gtk.Label arch_v;
    private Gtk.Label ssh_cmd;
    private Gtk.Image hero_icon;
    private Gtk.Label hero_sub;
    private Gtk.Box setup_card;
    private Gtk.Box connect_card;
    private Gtk.Box ssh_row;
    private Gtk.Label display_detail;
    private Gtk.MenuButton more_button;
    private Gtk.Label[] step_badges = {};
    private Gtk.Label step2_detail;
    private Gtk.Label step1_detail;
    private Gtk.Label step3_detail;
    private Gtk.Button get_button;
    private Gtk.Button pause_button;
    private Gtk.Label step1_title;
    private Gtk.Label step2_title;
    private Gtk.Label strip;
    private Gtk.Box creds_card;
    private Gtk.Label creds_label;
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
    private Viewer viewer;
    private bool was_running = false;
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
        viewer = new Viewer (machine);
        viewer.toast.connect ((m) => toast (m));
        stack.add_titled (viewer, "display", "Display");
        stack.add_titled (build_console (), "console", "Console");
        stack.add_titled (build_settings (), "settings", "Settings");

        var header = new Gtk.HeaderBar ();
        header.add_css_class ("flat");
        header.decoration_layout = ":maximize";
        var switcher = new Gtk.StackSwitcher ();
        switcher.stack = stack;
        header.title_widget = switcher;
        var more = new Gtk.MenuButton ();
        more_button = more;
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

        stack.notify["visible-child-name"].connect (() => {
            viewer.set_active (stack.visible_child_name == "display");
        });
        machine.state_changed.connect (refresh);
        machine.state_changed.connect (() => {
            // Take the user to the screen as soon as a machine starts.
            if (machine.running && !was_running) {
                show_tab ("display");
            }
            was_running = machine.running;
        });
        machine.finished.connect ((code) => {
            if (code > 0) {
                show_tab ("console");
            }
            toast (code > 0 ? "%s stopped with an error (exit %d)".printf (machine.name, code)
                            : "%s stopped".printf (machine.name));
        });
        if (machine.recipe != null && machine.is_fresh ()) {
            machine.check_latest.begin ();
        }
        uint ticks = 0;
        tick = Timeout.add_seconds (1, () => {
            update_uptime ();
            // Keep free-space and requirement checks current without a click.
            if (++ticks % 15 == 0 && !machine.running) {
                refresh ();
            }
            return Source.CONTINUE;
        });
        refresh ();
    }

    ~MachinePage () {
        if (tick != 0) {
            Source.remove (tick);
        }
    }

    /* Re-read free space and host requirements (and Omarchy's latest nightly). */
    public void recheck () {
        if (machine.recipe != null && machine.is_fresh ()) {
            machine.check_latest.begin ();
        }
        refresh ();
        int64 free = Readiness.free_gib ();
        toast (free >= 0 ? "Checked again: %d GiB free".printf ((int) free) : "Checked again");
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
        hero_sub = new Gtk.Label ("");
        hero_sub.xalign = 0;
        hero_sub.wrap = true;
        hero_sub.add_css_class ("dim-label");
        text.append (hero_sub);

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

        // Guided first run: shown only for a machine that has never been installed.
        setup_card = new Gtk.Box (Gtk.Orientation.VERTICAL, 0);
        setup_card.add_css_class ("ml-card");
        var setup_head = new Gtk.Label ("Set up in three steps");
        setup_head.xalign = 0;
        setup_head.add_css_class ("title-4");
        setup_head.margin_top = 14;
        setup_head.margin_start = 16;
        setup_head.margin_bottom = 4;
        setup_card.append (setup_head);

        get_button = new Gtk.Button.with_label ("Get ISO");
        get_button.valign = Gtk.Align.CENTER;
        get_button.clicked.connect (() => {
            if (machine.recipe != null) {
                machine.check_latest.begin ();
            } else if (machine.url != null) {
                new Gtk.UriLauncher (machine.url).launch.begin ((Gtk.Window) get_root (), null);
            }
        });
        setup_card.append (step_row (1, "Get an ARM64 installer",
            "Download a Linux ARM64 .iso, or use one you already have.", get_button, out step1_detail));
        var pick = new Gtk.Button.with_label ("Choose…");
        pick.valign = Gtk.Align.CENTER;
        pick.clicked.connect (() => choose_installer.begin ());
        setup_card.append (step_row (2, "Choose the installer file",
            "Pick it here, or drop it on the box below.", pick, out step2_detail));
        setup_card.append (step_row (3, "Start the installer",
            "Install inside the window. Shut the guest down when it finishes and Machine Lab boots the new disk from then on.", null, out step3_detail, true));
        clamp.append (setup_card);

        strip = new Gtk.Label ("");
        strip.wrap = true;
        strip.xalign = 0;
        strip.add_css_class ("ml-note");
        clamp.append (strip);

        creds_card = new Gtk.Box (Gtk.Orientation.HORIZONTAL, 12);
        creds_card.add_css_class ("ml-card");
        creds_card.add_css_class ("ml-spec");
        var key = new Gtk.Image.from_icon_name ("dialog-password-symbolic");
        key.pixel_size = 24;
        creds_card.append (key);
        var ctext = new Gtk.Box (Gtk.Orientation.VERTICAL, 0);
        ctext.hexpand = true;
        ctext.valign = Gtk.Align.CENTER;
        creds_label = new Gtk.Label ("");
        creds_label.xalign = 0;
        creds_label.wrap = true;
        creds_label.selectable = true;
        creds_label.add_css_class ("ml-mono");
        var cl2 = new Gtk.Label ("Sign-in for this machine, saved with its files");
        cl2.xalign = 0;
        cl2.add_css_class ("ml-spec-label");
        ctext.append (creds_label);
        ctext.append (cl2);
        creds_card.append (ctext);
        var ccopy = new Gtk.Button.from_icon_name ("edit-copy-symbolic");
        ccopy.add_css_class ("flat");
        ccopy.valign = Gtk.Align.CENTER;
        ccopy.tooltip_text = "Copy sign-in";
        ccopy.clicked.connect (() => {
            Gdk.Display.get_default ().get_clipboard ().set_text (creds_label.label);
            toast ("Copied sign-in");
        });
        creds_card.append (ccopy);
        clamp.append (creds_card);

        var specs = new Gtk.Grid ();
        specs.column_homogeneous = true;
        specs.row_homogeneous = true;
        specs.column_spacing = 12;
        specs.row_spacing = 12;
        specs.attach (spec_card ("computer-symbolic", out cpu_v, "Processor"), 0, 0);
        specs.attach (spec_card ("media-optical-symbolic", out mem_v, "Memory"), 1, 0);
        specs.attach (spec_card ("drive-harddisk-symbolic", out disk_v, "Disk, grows as used"), 0, 1);
        specs.attach (spec_card ("network-wired-symbolic", out net_v, "Network"), 1, 1);
        specs.attach (spec_card ("applications-system-symbolic", out arch_v, "Architecture · native ARM64, not x86-64 / amd64"), 0, 2, 2, 1);
        arch_v.label = "ARM64 (aarch64)";
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
        var recheck_btn = new Gtk.Button.from_icon_name ("view-refresh-symbolic");
        recheck_btn.valign = Gtk.Align.CENTER;
        recheck_btn.add_css_class ("flat");
        recheck_btn.tooltip_markup = Granite.markup_accel_tooltip ({ "F5", "<Control>r" }, "Check disk space and requirements again");
        recheck_btn.clicked.connect (() => recheck ());
        ready_card.append (recheck_btn);
        clamp.append (ready_card);

        // Connect: the clear way into a running machine.
        var connect = new Gtk.Box (Gtk.Orientation.VERTICAL, 0);
        connect_card = connect;
        connect.add_css_class ("ml-card");
        var chead = new Gtk.Label ("Connect");
        chead.xalign = 0;
        chead.margin_top = 14;
        chead.margin_start = 16;
        chead.margin_bottom = 4;
        chead.add_css_class ("title-4");
        connect.append (chead);

        // Display
        var drow = new Gtk.Box (Gtk.Orientation.HORIZONTAL, 14);
        drow.add_css_class ("ml-form-row");
        drow.add_css_class ("ml-form-sep");
        var dicon = new Gtk.Image.from_icon_name ("video-display-symbolic");
        dicon.pixel_size = 24;
        drow.append (dicon);
        var dtext = new Gtk.Box (Gtk.Orientation.VERTICAL, 2);
        dtext.hexpand = true;
        var dtitle = new Gtk.Label ("Display");
        dtitle.xalign = 0;
        dtitle.add_css_class ("ml-spec-value");
        display_detail = new Gtk.Label ("");
        display_detail.xalign = 0;
        display_detail.wrap = true;
        display_detail.add_css_class ("ml-spec-label");
        dtext.append (dtitle);
        dtext.append (display_detail);
        drow.append (dtext);
        var console_btn = new Gtk.Button.with_label ("Open Console");
        console_btn.valign = Gtk.Align.CENTER;
        console_btn.tooltip_text = "Show the machine's console output";
        console_btn.clicked.connect (() => show_tab ("console"));
        drow.append (console_btn);
        connect.append (drow);

        // SSH terminal
        ssh_row = new Gtk.Box (Gtk.Orientation.HORIZONTAL, 14);
        ssh_row.add_css_class ("ml-form-row");
        var term = new Gtk.Image.from_icon_name ("utilities-terminal-symbolic");
        term.pixel_size = 24;
        ssh_row.append (term);
        var ct = new Gtk.Box (Gtk.Orientation.VERTICAL, 2);
        ct.hexpand = true;
        var ttitle = new Gtk.Label ("Terminal (SSH)");
        ttitle.xalign = 0;
        ttitle.add_css_class ("ml-spec-value");
        ssh_cmd = new Gtk.Label ("");
        ssh_cmd.xalign = 0;
        ssh_cmd.selectable = true;
        ssh_cmd.add_css_class ("ml-mono");
        ct.append (ttitle);
        ct.append (ssh_cmd);
        ssh_row.append (ct);
        var open_term = new Gtk.Button.with_label ("Open Terminal");
        open_term.valign = Gtk.Align.CENTER;
        open_term.clicked.connect (() => {
            try {
                Process.spawn_async (null, { "io.elementary.terminal", "-e",
                    "ssh -p %d -o StrictHostKeyChecking=accept-new localhost".printf (machine.ssh_port) },
                    null, SpawnFlags.SEARCH_PATH, null, null);
            } catch (Error e) {
                toast ("Couldn't open Terminal: " + e.message);
            }
        });
        ssh_row.append (open_term);
        var copy = new Gtk.Button.from_icon_name ("edit-copy-symbolic");
        copy.valign = Gtk.Align.CENTER;
        copy.add_css_class ("flat");
        copy.tooltip_text = "Copy command";
        copy.clicked.connect (() => {
            Gdk.Display.get_default ().get_clipboard ().set_text (ssh_cmd.label);
            toast ("Copied SSH command");
        });
        ssh_row.append (copy);
        connect.append (ssh_row);
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
        pause_button = new Gtk.Button.with_label ("Pause");
        pause_button.clicked.connect (() => {
            if (machine.paused) machine.resume (); else machine.pause ();
            refresh ();
        });
        actions.append (pause_button);
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

    private Gtk.Widget step_row (int n, string title, string detail, Gtk.Widget? action,
                                 out Gtk.Label? detail_label, bool last = false) {
        var row = new Gtk.Box (Gtk.Orientation.HORIZONTAL, 14);
        row.add_css_class ("ml-form-row");
        if (!last) {
            row.add_css_class ("ml-form-sep");
        }
        var badge = new Gtk.Label ("%d".printf (n));
        badge.add_css_class ("ml-step-badge");
        badge.valign = Gtk.Align.START;
        step_badges += badge;
        row.append (badge);
        var t = new Gtk.Box (Gtk.Orientation.VERTICAL, 2);
        t.hexpand = true;
        var tl = new Gtk.Label (title);
        if (n == 1) step1_title = tl;
        if (n == 2) step2_title = tl;
        tl.xalign = 0;
        tl.add_css_class ("ml-spec-value");
        var dl = new Gtk.Label (detail);
        dl.xalign = 0;
        dl.wrap = true;
        dl.ellipsize = Pango.EllipsizeMode.NONE;
        dl.add_css_class ("ml-spec-label");
        t.append (tl);
        t.append (dl);
        row.append (t);
        detail_label = dl;
        if (action != null) {
            row.append (action);
        }
        return row;
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
        bool managed = machine.managed;
        bool fresh = machine.is_fresh ();
        title.label = machine.name;
        cpu_v.label = machine.cpus == 1 ? "1 virtual CPU" : "%d virtual CPUs".printf (machine.cpus);
        mem_v.label = "%d GiB".printf (machine.mem_gib);
        disk_v.label = machine.disk_gib > 0 ? "%d GiB".printf (machine.disk_gib) : "Disk";
        net_v.label = "Shared (NAT)";
        ssh_cmd.label = "ssh -p %d localhost".printf (machine.ssh_port);

        setup_card.visible = fresh && !managed;
        connect_card.visible = running || !fresh;
        connect_card.sensitive = running;
        ssh_row.visible = !managed;
        display_detail.label = !running
            ? "Start the machine, then its screen opens in its own window on this desktop."
            : "Opens in its own window on this desktop. Look for “%s” in the dock, or press Alt+Tab. If it was started without a window, use the console.".printf (machine.name);
        drop_zone.visible = !managed;
        more_button.visible = !managed;
        get_button.visible = machine.url != null || machine.recipe != null;
        if (machine.recipe != null) {
            step1_title.label = "Download Omarchy automatically";
            step1_detail.label = machine.check_summary ?? "Fetches the latest verified ARM64 nightly and installs it unattended.";
            get_button.label = machine.checking ? "Checking…" : "Check again";
            get_button.sensitive = !machine.checking;
            step2_title.label = "Or use your own installer";
        } else {
            step1_title.label = "Get an ARM64 installer";
            step1_detail.label = "Download a Linux ARM64 .iso, or use one you already have.";
            get_button.label = "Get ISO";
            step2_title.label = "Choose the installer file";
        }
        strip.visible = machine.status_text != "";
        strip.label = machine.status_text;
        var creds = machine.credentials ();
        creds_card.visible = creds != null;
        if (creds != null) creds_label.label = creds;
        hero_sub.label = "ARM64 · " + (managed ? (fresh ? (machine.installer != null ? "Imported from mseries-vm · installer ready: %s".printf (Path.get_basename (machine.installer)) : "Imported from mseries-vm · installer not finished") : "Installed · imported from mseries-vm")
            : fresh ? "New machine · not installed yet"
            : "Linux ARM64 · installed");

        var problems = Readiness.problems ();
        bool installing = running && machine.installer != null;
        start_button.visible = !running;
        stop_button.visible = running;
        stop_button.label = managed ? "Shut Down" : "Force Stop";
        start_button.label = fresh ? (machine.recipe != null && machine.installer == null ? "Download and Install" : "Start Installer") : "Start";
        pause_button.visible = running;
        pause_button.label = machine.paused ? "Resume" : "Pause";
        if (machine.paused) pause_button.add_css_class ("suggested-action"); else pause_button.remove_css_class ("suggested-action");
        bool auto_ok = machine.recipe != null && machine.installer == null && machine.check_ok;
        start_button.sensitive = problems.length == 0 && (!fresh || managed || machine.installer != null || auto_ok);
        start_button.tooltip_text = problems.length > 0 ? "Fix the items in the setup check first"
            : (fresh && !managed && machine.installer == null && !auto_ok ? (machine.recipe != null ? "Wait for the version check, or choose an installer" : "Choose an installer first") : null);

        status_pill.label = running ? (machine.paused ? "Paused" : (installing || (machine.recipe != null && machine.status_text.contains ("Installing")) ? "Installing" : "Running"))
            : fresh ? "Not installed" : "Stopped";
        status_pill.remove_css_class ("running");
        status_pill.remove_css_class ("new");
        status_pill.remove_css_class ("paused");
        if (running && machine.paused) {
            status_pill.add_css_class ("paused");
        } else if (running) {
            status_pill.add_css_class ("running");
        } else if (fresh) {
            status_pill.add_css_class ("new");
        }

        // Step badges: a check once done.
        bool have_iso = machine.installer != null;
        for (int i = 0; i < step_badges.length; i++) {
            bool done = i == 1 && have_iso;
            step_badges[i].label = done ? "✓" : "%d".printf (i + 1);
            if (done) step_badges[i].add_css_class ("done"); else step_badges[i].remove_css_class ("done");
        }
        if (step2_detail != null) {
            step2_detail.label = have_iso ? Path.get_basename (machine.installer) : "Pick it here, or drop it on the box below.";
        }

        if (machine.installer != null) {
            drop_zone.add_css_class ("chosen");
            drop_title.label = Path.get_basename (machine.installer);
            drop_detail.label = machine.installer;
        } else {
            drop_zone.remove_css_class ("chosen");
            drop_title.label = !fresh ? "Boots from its disk" : "Drop an installer here";
            drop_detail.label = !fresh
                ? "Attach an ARM64 .iso only if you want to reinstall."
                : "Drop an ARM64 .iso here, or browse for one.";
        }

        for (int i = 0; i < 8; i++) {
            hero_icon.remove_css_class ("ml-c-%d".printf (i));
        }
        hero_icon.add_css_class ("ml-c-%d".printf (machine.color));
        int64 used = machine.disk_used_bytes ();
        if (used > 0) {
            disk_v.label = "%.1f of %d GiB".printf (used / 1073741824.0, machine.disk_gib);
        }

        ready_card.remove_css_class ("bad");
        int64 free = Readiness.free_gib ();
        bool low_space = fresh && free >= 0 && free < machine.disk_gib / 2 + 10;
        if (problems.length == 0 && !low_space) {
            ready_icon.icon_name = "emblem-default-symbolic";
            ready_icon.add_css_class ("ml-ok");
            ready_title.label = "Ready to run";
            ready_detail.label = free >= 0
                ? "QEMU, UEFI firmware and acceleration are available. %d GiB free on this Mac.".printf ((int) free)
                : "QEMU, UEFI firmware and acceleration are available.";
        } else if (problems.length == 0) {
            ready_icon.icon_name = "dialog-warning-symbolic";
            ready_icon.remove_css_class ("ml-ok");
            ready_card.add_css_class ("bad");
            ready_title.label = "Low disk space";
            ready_detail.label = "Only %d GiB free on this Mac. The %d GiB disk grows as the guest writes, so free some space or shrink the disk in Settings before installing.".printf ((int) free, machine.disk_gib);
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

        settings_form.sensitive = !running && !managed;
        disk_scale.sensitive = !running && !managed && !machine.has_disk ();
        settings_note.visible = running || machine.has_disk () || managed;
        settings_note.label = managed
            ? "This machine is managed by mseries-vm. Change it with: mseries-vm set %s KEY VALUE".printf (machine.vm_name)
            : running
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
