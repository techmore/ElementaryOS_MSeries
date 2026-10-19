/*
 * Machine Lab: run another Linux on this Mac.
 * Vala + GTK 4 + Granite 7, laid out like a first-party elementary OS app:
 * flat sidebar of machines + content pane with tabs, suggested-action buttons,
 * toasts, and an empty-state welcome.
 */
using Gtk;

public class MachineRow : Gtk.ListBoxRow {
    public Machine machine { get; construct; }
    private Gtk.Label name_label;
    private Gtk.Label sub_label;
    private Gtk.Box dot;

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
        var icon = new Gtk.Image.from_icon_name ("computer");
        icon.pixel_size = 32;
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
        sub_label.label = "%s · %d CPU · %d GiB".printf (
            machine.running ? "Running" : "Stopped", machine.cpus, machine.mem_gib);
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
        new_action.activate.connect (() => add_machine ());
        add_action (new_action);
        set_accels_for_action ("app.new-machine", { "<Control>n" });
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

        var heading = new Gtk.Label ("MACHINES");
        heading.xalign = 0;
        heading.add_css_class ("ml-sidebar-title");
        side.append (heading);

        list = new Gtk.ListBox ();
        list.selection_mode = Gtk.SelectionMode.SINGLE;
        list.add_css_class ("navigation-sidebar");
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
        var add = new Gtk.Button ();
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
        add.tooltip_markup = Granite.markup_accel_tooltip ({ "<Control>n" }, "Create a new machine");
        add.clicked.connect (() => add_machine ());
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

        var box = new Gtk.Box (Gtk.Orientation.VERTICAL, 10);
        box.vexpand = true;
        box.valign = Gtk.Align.CENTER;
        box.halign = Gtk.Align.CENTER;
        box.width_request = 380;
        var icon = new Gtk.Image.from_icon_name ("computer");
        icon.pixel_size = 128;
        icon.add_css_class ("ml-empty-icon");
        box.append (icon);
        var t = new Gtk.Label ("No Machines Yet");
        t.add_css_class ("title-1");
        t.margin_top = 12;
        box.append (t);
        var d = new Gtk.Label ("Create a machine to run another Linux next to elementary OS, with full hardware acceleration.");
        d.wrap = true;
        d.justify = Gtk.Justification.CENTER;
        d.add_css_class ("dim-label");
        box.append (d);
        var b = new Gtk.Button.with_label ("New Machine");
        b.add_css_class ("suggested-action");
        b.add_css_class ("pill");
        b.halign = Gtk.Align.CENTER;
        b.margin_top = 12;
        b.clicked.connect (() => add_machine ());
        box.append (b);
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
        page.start_requested.connect (() => start_machine (m));
        page.remove_requested.connect (() => confirm_remove.begin (m));
        pages[m.id] = page;
        content.add_named (page, m.id);
        list.append (new MachineRow (m));
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

    private void add_machine () {
        var m = new Machine ();
        m.id = "machine-%s".printf (Uuid.string_random ().substring (0, 8));
        int n = machines.length + 1;
        m.name = "Machine %d".printf (n);
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
        string? launcher = find_launcher ();
        if (launcher == null) {
            show_error ("The QEMU launcher was not found. Set MACHINE_LAB_LAUNCHER to the full path of run-vm.sh.");
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
        string installed = "/usr/bin/machine-lab-run-vm";
        if (FileUtils.test (installed, FileTest.IS_EXECUTABLE)) {
            return installed;
        }
        string exe_dir = Path.get_dirname (Environment.get_prgname () ?? "");
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
