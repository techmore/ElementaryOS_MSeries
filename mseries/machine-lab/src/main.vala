/*
 * Machine Lab: run another Linux on this Mac.
 * Vala + GTK 4 + Granite 7, laid out like a first-party elementary OS app:
 * flat sidebar of machines + content pane with tabs, suggested-action buttons,
 * toasts, and an empty-state welcome.
 */
using Gtk;

struct Preset {
    public string name;
    public string blurb;
    public int cpus;
    public int mem;
    public int disk;
    public int color;
    public string url;
    public string recipe;
}

const Preset[] presets = {
    { "Omarchy", "Arch-based tiling desktop", 4, 6, 32, 7, "https://omarchy.org", "omarchy" },
    { "elementary OS", "Pantheon desktop, daily ARM64 build", 4, 4, 32, 0, "https://elementary.io", "elementary" },
    { "Ubuntu", "Friendly general-purpose desktop", 4, 4, 24, 4, "https://ubuntu.com/download/server/arm", "" },
    { "Debian", "Rock-solid and lightweight", 2, 2, 16, 5, "https://www.debian.org/CD/netinst/", "" },
    { "Fedora", "Fresh packages, GNOME", 4, 4, 24, 0, "https://fedoraproject.org/server/download", "" },
    { "Blank Machine", "Bring any ARM64 .iso", 2, 4, 16, 1, "", "" }
};

public class MachineRow : Gtk.ListBoxRow {
    public Machine machine { get; construct; }
    private Gtk.Label name_label;
    private Gtk.Label sub_label;
    private Gtk.Box dot;
    private Gtk.Image icon;

    public signal void group_changed ();
    public int group { get { return machine.is_fresh () ? 1 : 0; } }

    public MachineRow (Machine machine) {
        Object (machine: machine);
    }

    construct {
        var box = new Gtk.Box (Gtk.Orientation.HORIZONTAL, 10);
        box.margin_top = 4;
        box.margin_bottom = 4;
        box.margin_start = 6;
        box.margin_end = 6;

        var overlay = new Gtk.Overlay ();
        icon = new Gtk.Image.from_icon_name ("computer");
        icon.pixel_size = 32;
        icon.add_css_class ("ml-row-icon");
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
        sub_label.add_css_class ("ml-machine-sub");
        text.append (name_label);
        text.append (sub_label);
        box.append (text);
        child = box;

        machine.state_changed.connect (update);
        update ();
    }

    public void update () {
        name_label.label = machine.name;
        string state = machine.running ? (machine.paused ? "Paused" : "Running") : machine.is_fresh () ? "Not installed" : "Stopped";
        sub_label.label = "ARM64 · %s · %d CPU · %d GiB".printf (state, machine.cpus, machine.mem_gib);
        for (int i = 0; i < 8; i++) {
            icon.remove_css_class ("ml-c-%d".printf (i));
        }
        icon.add_css_class ("ml-c-%d".printf (machine.color));
        if (machine.running) {
            dot.add_css_class ("running");
        } else {
            dot.remove_css_class ("running");
        }
    }
}

public class MachineLab : Gtk.Application {
    private GenericArray<Machine> machines;
    private Gtk.ApplicationWindow window;
    private Granite.Toast toast;
    private Gtk.ListBox list;
    private Gtk.Stack content;
    private HashTable<string, MachinePage> pages = new HashTable<string, MachinePage> (str_hash, str_equal);

    public MachineLab () {
        Object (
            application_id: "io.github.mseries.MachineLab",
            flags: ApplicationFlags.DEFAULT_FLAGS
        );
    }

    protected override void startup () {
        base.startup ();
        Granite.init ();

        var gtk_settings = Gtk.Settings.get_default ();
        var granite_settings = Granite.Settings.get_default ();
        gtk_settings.gtk_application_prefer_dark_theme =
            granite_settings.prefers_color_scheme == Granite.Settings.ColorScheme.DARK;
        granite_settings.notify["prefers-color-scheme"].connect (() => {
            gtk_settings.gtk_application_prefer_dark_theme =
                granite_settings.prefers_color_scheme == Granite.Settings.ColorScheme.DARK;
        });

        var provider = new Gtk.CssProvider ();
        provider.load_from_resource ("/io/github/mseries/MachineLab/style.css");
        Gtk.StyleContext.add_provider_for_display (
            Gdk.Display.get_default (), provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        );

        var new_action = new SimpleAction ("new-machine", null);
        new_action.activate.connect (() => add_machine (presets[0]));
        add_action (new_action);
        set_accels_for_action ("app.new-machine", { "<Control>n" });
        var refresh_action = new SimpleAction ("refresh", null);
        refresh_action.activate.connect (() => {
            var row = list.get_selected_row ();
            if (row != null) {
                pages[((MachineRow) row).machine.id].recheck ();
            }
        });
        add_action (refresh_action);
        set_accels_for_action ("app.refresh", { "F5", "<Control>r" });
        set_accels_for_action ("app.quit", { "<Control>q" });
        var quit = new SimpleAction ("quit", null);
        quit.activate.connect (() => window.close ());
        add_action (quit);
    }

    protected override void activate () {
        if (window != null) {
            window.present ();
            return;
        }
        machines = MachineStore.load ();
        MachineStore.discover (machines);

        window = new Gtk.ApplicationWindow (this);
        window.title = "Machine Lab";
        window.default_width = 940;
        window.default_height = 640;
        window.titlebar = new Gtk.Box (Gtk.Orientation.HORIZONTAL, 0) { visible = false };

        var layout = new Gtk.Box (Gtk.Orientation.HORIZONTAL, 0);
        layout.append (build_sidebar ());
        layout.append (new Gtk.Separator (Gtk.Orientation.VERTICAL));

        content = new Gtk.Stack ();
        content.hexpand = true;
        content.transition_type = Gtk.StackTransitionType.CROSSFADE;
        content.add_named (build_empty_state (), "empty");
        layout.append (content);

        var overlay = new Gtk.Overlay ();
        overlay.child = layout;
        toast = new Granite.Toast ("");
        overlay.add_overlay (toast);
        window.child = overlay;

        foreach (var m in machines.data) {
            add_row_and_page (m);
        }
        select_first ();

        window.close_request.connect (() => {
            foreach (var m in machines.data) {
                m.stop ();
            }
            return false;
        });
        Timeout.add_seconds (2, () => {
            foreach (var m in machines.data) {
                m.poll ();
            }
            return Source.CONTINUE;
        });
        foreach (var m in machines.data) {
            m.poll ();
        }
        window.present ();
    }

    // ---- Sidebar ----------------------------------------------------------

    private Gtk.Widget build_sidebar () {
        var side = new Gtk.Box (Gtk.Orientation.VERTICAL, 0);
        side.add_css_class ("ml-sidebar");
        side.width_request = 250;

        var header = new Gtk.HeaderBar ();
        header.add_css_class ("flat");
        header.decoration_layout = "close:";
        header.title_widget = new Gtk.Label ("");
        var handle = new Gtk.WindowHandle ();
        handle.child = header;
        side.append (handle);


        list = new Gtk.ListBox ();
        list.selection_mode = Gtk.SelectionMode.SINGLE;
        list.add_css_class ("navigation-sidebar");
        list.set_sort_func ((a, b) => {
            var ra = (MachineRow) a;
            var rb = (MachineRow) b;
            if (ra.group != rb.group) return ra.group - rb.group;
            return strcmp (ra.machine.name.down (), rb.machine.name.down ());
        });
        list.set_header_func ((row, before) => {
            var r = (MachineRow) row;
            if (before != null && ((MachineRow) before).group == r.group) {
                row.set_header (null);
                return;
            }
            var h = new Gtk.Label (r.group == 0 ? "YOUR MACHINES" : "NEW — NOT INSTALLED");
            h.xalign = 0;
            h.add_css_class ("ml-sidebar-title");
            row.set_header (h);
        });
        list.row_selected.connect ((row) => {
            if (row == null) {
                content.visible_child_name = "empty";
                return;
            }
            content.visible_child_name = ((MachineRow) row).machine.id;
        });
        var scroll = new Gtk.ScrolledWindow ();
        scroll.vexpand = true;
        scroll.child = list;
        side.append (scroll);

        side.append (new Gtk.Separator (Gtk.Orientation.HORIZONTAL));
        var add = new Gtk.MenuButton ();
        var add_box = new Gtk.Box (Gtk.Orientation.HORIZONTAL, 6);
        add_box.append (new Gtk.Image.from_icon_name ("list-add-symbolic"));
        add_box.append (new Gtk.Label ("New Machine"));
        add.child = add_box;
        add.add_css_class ("flat");
        add.margin_top = 6;
        add.margin_bottom = 6;
        add.margin_start = 6;
        add.margin_end = 6;
        add.halign = Gtk.Align.START;
        add.direction = Gtk.ArrowType.UP;
        add.tooltip_markup = Granite.markup_accel_tooltip ({ "<Control>n" }, "Create a new machine");
        var pop = new Gtk.Popover ();
        var pbox = new Gtk.Box (Gtk.Orientation.VERTICAL, 2);
        pbox.margin_top = 6;
        pbox.margin_bottom = 6;
        pbox.margin_start = 6;
        pbox.margin_end = 6;
        foreach (var p in presets) {
            var item = new Gtk.Button ();
            item.add_css_class ("flat");
            var ib = new Gtk.Box (Gtk.Orientation.HORIZONTAL, 10);
            var ic = new Gtk.Image.from_icon_name ("computer");
            ic.pixel_size = 28;
            ic.add_css_class ("ml-row-icon");
            ic.add_css_class ("ml-c-%d".printf (p.color));
            ib.append (ic);
            var tb = new Gtk.Box (Gtk.Orientation.VERTICAL, 0);
            var n = new Gtk.Label (p.name);
            n.xalign = 0;
            n.add_css_class ("ml-machine-name");
            var d = new Gtk.Label ("%s · ARM64 · %d CPU · %d GiB".printf (p.blurb, p.cpus, p.mem));
            d.xalign = 0;
            d.add_css_class ("ml-machine-sub");
            tb.append (n);
            tb.append (d);
            ib.append (tb);
            item.child = ib;
            var preset = p;
            item.clicked.connect (() => { pop.popdown (); add_machine (preset); });
            pbox.append (item);
        }
        var mac_item = new Gtk.Button ();
        mac_item.add_css_class ("flat");
        var mac_lbl = new Gtk.Label ("macOS… (not available on Linux)");
        mac_lbl.xalign = 0;
        mac_lbl.add_css_class ("ml-machine-sub");
        mac_item.child = mac_lbl;
        mac_item.clicked.connect (() => { pop.popdown (); show_macos_info (); });
        pbox.append (mac_item);
        pop.child = pbox;
        add.popover = pop;
        side.append (add);
        return side;
    }

    private Gtk.Widget build_empty_state () {
        var page = new Gtk.Box (Gtk.Orientation.VERTICAL, 0);
        var header = new Gtk.HeaderBar ();
        header.add_css_class ("flat");
        header.decoration_layout = ":maximize";
        header.title_widget = new Gtk.Label ("");
        var handle = new Gtk.WindowHandle ();
        handle.child = header;
        page.append (handle);

        var box = new Gtk.Box (Gtk.Orientation.VERTICAL, 8);
        box.vexpand = true;
        box.valign = Gtk.Align.CENTER;
        box.halign = Gtk.Align.CENTER;
        box.margin_start = 32;
        box.margin_end = 32;
        box.width_request = 520;
        var t = new Gtk.Label ("Create a Machine");
        t.add_css_class ("title-1");
        box.append (t);
        var d = new Gtk.Label ("Pick a starting point. Machine Lab sets up sensible hardware, then walks you through the installer.");
        d.wrap = true;
        d.justify = Gtk.Justification.CENTER;
        d.margin_bottom = 14;
        d.add_css_class ("dim-label");
        box.append (d);

        var grid = new Gtk.Grid ();
        grid.column_homogeneous = true;
        grid.column_spacing = 12;
        grid.row_spacing = 12;
        int i = 0;
        foreach (var p in presets) {
            var card = new Gtk.Button ();
            card.add_css_class ("flat");
            var cb = new Gtk.Box (Gtk.Orientation.HORIZONTAL, 12);
            cb.add_css_class ("ml-gallery-card");
            var ic = new Gtk.Image.from_icon_name ("computer");
            ic.pixel_size = 40;
            ic.add_css_class ("ml-row-icon");
            ic.add_css_class ("ml-c-%d".printf (p.color));
            cb.append (ic);
            var tb = new Gtk.Box (Gtk.Orientation.VERTICAL, 2);
            tb.valign = Gtk.Align.CENTER;
            var n = new Gtk.Label (p.name);
            n.xalign = 0;
            n.add_css_class ("ml-spec-value");
            var bl = new Gtk.Label (p.blurb);
            bl.xalign = 0;
            bl.add_css_class ("ml-spec-label");
            var sp = new Gtk.Label ("ARM64 · %d CPU · %d GiB RAM · %d GiB disk".printf (p.cpus, p.mem, p.disk));
            sp.xalign = 0;
            sp.add_css_class ("ml-fineprint");
            tb.append (n);
            tb.append (bl);
            tb.append (sp);
            cb.append (tb);
            card.child = cb;
            var preset = p;
            card.clicked.connect (() => add_machine (preset));
            grid.attach (card, i % 2, i / 2);
            i++;
        }
        var mac = new Gtk.Button ();
        mac.add_css_class ("flat");
        var mb = new Gtk.Box (Gtk.Orientation.HORIZONTAL, 12);
        mb.add_css_class ("ml-gallery-card");
        var mi = new Gtk.Image.from_icon_name ("computer");
        mi.pixel_size = 40;
        mi.add_css_class ("ml-row-icon");
        mi.add_css_class ("ml-c-6");
        mb.append (mi);
        var mt = new Gtk.Box (Gtk.Orientation.VERTICAL, 2);
        mt.valign = Gtk.Align.CENTER;
        var mn = new Gtk.Label ("macOS");
        mn.xalign = 0;
        mn.add_css_class ("ml-spec-value");
        var mbl = new Gtk.Label ("Not possible on this Mac under Linux");
        mbl.xalign = 0;
        mbl.add_css_class ("ml-spec-label");
        var mlearn = new Gtk.Label ("Tap to see what works instead");
        mlearn.xalign = 0;
        mlearn.add_css_class ("ml-fineprint");
        mt.append (mn);
        mt.append (mbl);
        mt.append (mlearn);
        mb.append (mt);
        mac.child = mb;
        mac.clicked.connect (() => show_macos_info ());
        grid.attach (mac, i % 2, i / 2);
        box.append (grid);
        page.append (box);
        return page;
    }

    // ---- Machines ---------------------------------------------------------

    private void add_row_and_page (Machine m) {
        var page = new MachinePage (m);
        page.toast.connect (send_toast);
        page.changed.connect (() => {
            MachineStore.save (machines);
            row_for (m).update ();
        });
        m.installer_detached.connect (() => {
            MachineStore.save (machines);
            send_toast ("%s is installed. It will boot from its disk now.".printf (m.name));
        });
        page.start_requested.connect (() => start_machine (m));
        page.remove_requested.connect (() => confirm_remove.begin (m));
        pages[m.id] = page;
        content.add_named (page, m.id);
        var row = new MachineRow (m);
        m.state_changed.connect (() => list.invalidate_sort ());
        m.state_changed.connect (() => list.invalidate_headers ());
        list.append (row);
    }

    private MachineRow row_for (Machine m) {
        for (var r = list.get_row_at_index (0); r != null; r = list.get_row_at_index (r.get_index () + 1)) {
            if (((MachineRow) r).machine == m) {
                return (MachineRow) r;
            }
        }
        assert_not_reached ();
    }

    private void select_first () {
        var first = list.get_row_at_index (0);
        if (first != null) {
            list.select_row (first);
        } else {
            content.visible_child_name = "empty";
        }
    }

    private void show_macos_info () {
        var dialog = new Gtk.AlertDialog ("macOS can't run as a guest here");
        dialog.detail = "A macOS guest on Apple Silicon needs Apple's Virtualization framework and virtual hardware, which only exist on macOS hosts. Linux KVM on this Mac can't provide them, and no open implementation boots macOS.\n\nWhat works:\n• Your internal macOS is still installed. Hold the power button at startup and pick it at the boot picker.\n• Run a macOS VM on a Mac that runs macOS (UTM or Tart) and reach it over the network.\n• Use the elementary OS, Omarchy and other Linux machines here for everything else.";
        dialog.buttons = { "OK" };
        dialog.show (window);
    }

    private string? newest_iso (string pattern) {
        string? best = null;
        int64 best_time = 0;
        try {
            var root = Path.build_filename (Machine.vms_dir (), "downloads");
            var top = Dir.open (root);
            string? d;
            while ((d = top.read_name ()) != null) {
                var sub = Path.build_filename (root, d);
                if (!FileUtils.test (sub, FileTest.IS_DIR)) continue;
                var inner = Dir.open (sub);
                string? f;
                while ((f = inner.read_name ()) != null) {
                    if (!PatternSpec.match_simple (pattern, f)) continue;
                    var path = Path.build_filename (sub, f);
                    var info = File.new_for_path (path).query_info ("time::modified", FileQueryInfoFlags.NONE);
                    int64 t = info.get_modification_date_time ().to_unix ();
                    if (t > best_time) { best_time = t; best = path; }
                }
            }
        } catch (Error e) {}
        return best;
    }

    private void add_machine (Preset preset) {
        var m = new Machine ();
        m.id = "machine-%s".printf (Uuid.string_random ().substring (0, 8));
        int n = machines.length + 1;
        m.name = machines.length == 0 ? preset.name : "%s %d".printf (preset.name, n);
        m.cpus = preset.cpus;
        m.mem_gib = preset.mem;
        m.disk_gib = preset.disk;
        m.color = preset.color;
        m.url = preset.url == "" ? null : preset.url;
        m.recipe = preset.recipe == "" ? null : preset.recipe;
        if (preset.recipe == "elementary") {
            // Use the ARM64 ISO mseries-vm already downloaded, if there is one.
            m.recipe = null;
            m.installer = newest_iso ("elementaryos*arm64*.iso");
        }
        int port = 2222;
        bool clash = true;
        while (clash) {
            clash = false;
            foreach (var o in machines.data) {
                if (o.ssh_port == port) { port++; clash = true; }
            }
        }
        m.ssh_port = port;
        machines.add (m);
        MachineStore.save (machines);
        add_row_and_page (m);
        list.select_row (row_for (m));
        pages[m.id].show_tab ("settings");
        send_toast ("Created %s".printf (m.name));
    }

    private void start_machine (Machine m) {
        if (m.managed) {
            string? tool = Machine.find_mseries_vm ();
            if (tool == null) {
                show_error ("mseries-vm was not found. Set MSERIES_VM_TOOL to its full path.");
                return;
            }
            try {
                m.start (tool);
                send_toast ("Starting %s…".printf (m.name));
            } catch (Error e) {
                show_error (e.message);
            }
            return;
        }
        string? launcher = find_launcher ();
        if (launcher == null) {
            show_error ("The QEMU launcher (run-vm.sh) was not found next to the app. Set MACHINE_LAB_LAUNCHER to its full path.");
            return;
        }
        if (!m.has_disk () && m.installer == null) {
            show_error ("This machine has no disk yet. Choose an ARM64 installer image first.");
            return;
        }
        foreach (var o in machines.data) {
            if (o != m && o.running && o.ssh_port == m.ssh_port) {
                show_error ("%s is already using SSH port %d. Change the port in Settings.".printf (o.name, o.ssh_port));
                return;
            }
        }
        try {
            m.start (launcher);
            send_toast ("Starting %s…".printf (m.name));
        } catch (Error e) {
            show_error (e.message);
        }
    }

    private async void confirm_remove (Machine m) {
        var dialog = new Gtk.AlertDialog ("Remove “%s”?".printf (m.name));
        dialog.detail = "The machine is removed from Machine Lab. You can also delete its virtual disk, which cannot be undone.";
        dialog.buttons = { "Cancel", "Remove", "Remove and Delete Disk" };
        dialog.cancel_button = 0;
        dialog.default_button = 0;
        try {
            int choice = yield dialog.choose (window, null);
            if (choice == 0) return;
            m.stop ();
            if (choice == 2) {
                m.delete_files ();
            }
            var row = row_for (m);
            int idx = row.get_index ();
            list.remove (row);
            content.remove (pages[m.id]);
            pages.remove (m.id);
            machines.remove (m);
            MachineStore.save (machines);
            var next = list.get_row_at_index (int.min (idx, (int) machines.length - 1));
            if (next != null) {
                list.select_row (next);
            } else {
                content.visible_child_name = "empty";
            }
            send_toast ("Removed %s".printf (m.name));
        } catch (Error e) {
            // dialog dismissed
        }
    }

    private string? find_launcher () {
        string? override_path = Environment.get_variable ("MACHINE_LAB_LAUNCHER");
        if (override_path != null && FileUtils.test (override_path, FileTest.IS_EXECUTABLE)) {
            return override_path;
        }
        foreach (var installed in new string[] {
            Path.build_filename (Environment.get_home_dir (), ".local", "bin", "machine-lab-run-vm"),
            "/usr/bin/machine-lab-run-vm"
        }) {
            if (FileUtils.test (installed, FileTest.IS_EXECUTABLE)) {
                return installed;
            }
        }
        string exe_dir = "";
        try {
            exe_dir = Path.get_dirname (FileUtils.read_link ("/proc/self/exe"));
        } catch (Error e) {}
        string[] candidates = {
            Path.build_filename (exe_dir, "run-vm.sh"),
            Path.build_filename (exe_dir, "..", "launcher", "run-vm.sh")
        };
        foreach (var c in candidates) {
            if (FileUtils.test (c, FileTest.IS_EXECUTABLE)) {
                return c;
            }
        }
        return null;
    }

    private void send_toast (string message) {
        toast.title = message;
        toast.send_notification ();
    }

    private void show_error (string message) {
        var dialog = new Gtk.AlertDialog ("Could not start the virtual machine");
        dialog.detail = message;
        dialog.show (window);
    }

    public static int main (string[] args) {
        return new MachineLab ().run (args);
    }
}
