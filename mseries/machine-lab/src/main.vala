/*
 * Machine Lab: run another Linux on this Mac.
 * Vala + GTK 4 + Granite 7, laid out like a first-party elementary OS app:
 * flat sidebar + content pane, hero header, spec cards, suggested action.
 */
using Gtk;

public class MachineLab : Gtk.Application {
    private string? installer_path = null;
    private Subprocess? vm = null;

    private Gtk.ApplicationWindow window;
    private Granite.Toast toast;
    private Gtk.Box drop_zone;
    private Gtk.Label drop_title;
    private Gtk.Label drop_detail;
    private Gtk.Button start_button;
    private Gtk.Button stop_button;
    private Gtk.Label status_pill;
    private Gtk.Label sidebar_sub;

    public MachineLab () {
        Object (
            application_id: "io.github.mseries.MachineLab",
            flags: ApplicationFlags.DEFAULT_FLAGS
        );
    }

    protected override void startup () {
        base.startup ();
        Granite.init ();

        // Follow the system light/dark preference like other elementary apps.
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
    }

    protected override void activate () {
        if (window != null) {
            window.present ();
            return;
        }

        window = new Gtk.ApplicationWindow (this);
        window.title = "Machine Lab";
        window.default_width = 880;
        window.default_height = 600;

        var layout = new Gtk.Box (Gtk.Orientation.HORIZONTAL, 0);
        layout.append (build_sidebar ());
        layout.append (new Gtk.Separator (Gtk.Orientation.VERTICAL));
        layout.append (build_content ());

        // Hide the stock title bar: each pane brings its own flat header.
        window.titlebar = new Gtk.Box (Gtk.Orientation.HORIZONTAL, 0) { visible = false };

        var overlay = new Gtk.Overlay ();
        overlay.child = layout;
        toast = new Granite.Toast ("");
        overlay.add_overlay (toast);
        window.child = overlay;

        update_state ();
        window.present ();
    }

    // ---- Sidebar ----------------------------------------------------------

    private Gtk.Widget build_sidebar () {
        var side = new Gtk.Box (Gtk.Orientation.VERTICAL, 0);
        side.add_css_class ("ml-sidebar");
        side.width_request = 230;

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

        var list = new Gtk.ListBox ();
        list.selection_mode = Gtk.SelectionMode.SINGLE;
        list.add_css_class ("navigation-sidebar");
        list.vexpand = true;

        var row_box = new Gtk.Box (Gtk.Orientation.HORIZONTAL, 10);
        row_box.margin_top = 4;
        row_box.margin_bottom = 4;
        row_box.margin_start = 6;
        row_box.margin_end = 6;
        var icon = new Gtk.Image.from_icon_name ("computer");
        icon.pixel_size = 32;
        row_box.append (icon);

        var text = new Gtk.Box (Gtk.Orientation.VERTICAL, 0);
        text.valign = Gtk.Align.CENTER;
        var name = new Gtk.Label ("Omarchy");
        name.xalign = 0;
        name.add_css_class ("ml-machine-name");
        sidebar_sub = new Gtk.Label ("ARM64 · Stopped");
        sidebar_sub.xalign = 0;
        sidebar_sub.add_css_class ("ml-machine-sub");
        text.append (name);
        text.append (sidebar_sub);
        row_box.append (text);

        list.append (row_box);
        list.select_row (list.get_row_at_index (0));
        side.append (list);

        return side;
    }

    // ---- Content ----------------------------------------------------------

    private Gtk.Widget build_content () {
        var pane = new Gtk.Box (Gtk.Orientation.VERTICAL, 0);
        pane.hexpand = true;

        var header = new Gtk.HeaderBar ();
        header.add_css_class ("flat");
        header.decoration_layout = ":maximize";
        header.title_widget = new Gtk.Label ("");
        var handle = new Gtk.WindowHandle ();
        handle.child = header;
        pane.append (handle);

        var scroller = new Gtk.ScrolledWindow ();
        scroller.vexpand = true;
        scroller.hscrollbar_policy = Gtk.PolicyType.NEVER;
        pane.append (scroller);

        var clamp = new Gtk.Box (Gtk.Orientation.VERTICAL, 20);
        clamp.margin_start = 32;
        clamp.margin_end = 32;
        clamp.margin_bottom = 28;
        clamp.halign = Gtk.Align.FILL;
        clamp.width_request = 480;
        scroller.child = clamp;

        // Hero
        var hero = new Gtk.Box (Gtk.Orientation.HORIZONTAL, 18);
        var hero_icon = new Gtk.Image.from_icon_name ("computer");
        hero_icon.pixel_size = 64;
        hero_icon.add_css_class ("ml-hero-icon");
        hero_icon.valign = Gtk.Align.START;
        hero.append (hero_icon);

        var hero_text = new Gtk.Box (Gtk.Orientation.VERTICAL, 4);
        hero_text.hexpand = true;
        hero_text.valign = Gtk.Align.CENTER;
        var title = new Gtk.Label ("Omarchy");
        title.add_css_class ("title-1");
        title.xalign = 0;
        hero_text.append (title);

        var subtitle = new Gtk.Label ("A second Linux, running side by side with elementary OS. It uses your Mac's hardware virtualization, so it stays fast.");
        subtitle.wrap = true;
        subtitle.xalign = 0;
        subtitle.add_css_class ("dim-label");
        hero_text.append (subtitle);

        status_pill = new Gtk.Label ("Stopped");
        status_pill.add_css_class ("ml-pill");
        status_pill.halign = Gtk.Align.START;
        status_pill.margin_top = 6;
        hero_text.append (status_pill);
        hero.append (hero_text);
        clamp.append (hero);

        // Specs
        var specs = new Gtk.Grid ();
        specs.column_homogeneous = true;
        specs.row_homogeneous = true;
        specs.column_spacing = 12;
        specs.row_spacing = 12;
        specs.attach (spec_card ("computer-symbolic", "4 virtual CPUs", "Processor"), 0, 0);
        specs.attach (spec_card ("media-optical-symbolic", "6 GiB", "Memory"), 1, 0);
        specs.attach (spec_card ("drive-harddisk-symbolic", "64 GiB", "Disk (grows as used)"), 0, 1);
        specs.attach (spec_card ("network-wired-symbolic", "Shared network", "SSH on localhost:2222"), 1, 1);
        clamp.append (specs);

        // Installer drop zone
        drop_zone = new Gtk.Box (Gtk.Orientation.HORIZONTAL, 14);
        drop_zone.add_css_class ("ml-drop");
        var drop_icon = new Gtk.Image.from_icon_name ("media-optical");
        drop_icon.pixel_size = 48;
        drop_zone.append (drop_icon);

        var drop_text = new Gtk.Box (Gtk.Orientation.VERTICAL, 2);
        drop_text.hexpand = true;
        drop_text.valign = Gtk.Align.CENTER;
        drop_title = new Gtk.Label ("Choose an installer");
        drop_title.xalign = 0;
        drop_title.add_css_class ("title-3");
        drop_detail = new Gtk.Label ("Drop an ARM64 .iso here, or browse for one.");
        drop_detail.xalign = 0;
        drop_detail.ellipsize = Pango.EllipsizeMode.MIDDLE;
        drop_detail.add_css_class ("dim-label");
        drop_text.append (drop_title);
        drop_text.append (drop_detail);
        drop_zone.append (drop_text);

        var browse = new Gtk.Button.with_label ("Browse…");
        browse.valign = Gtk.Align.CENTER;
        browse.clicked.connect (() => choose_installer.begin ());
        drop_zone.append (browse);
        clamp.append (drop_zone);

        var target = new Gtk.DropTarget (typeof (Gdk.FileList), Gdk.DragAction.COPY);
        target.enter.connect (() => { drop_zone.add_css_class ("hover"); return Gdk.DragAction.COPY; });
        target.leave.connect (() => drop_zone.remove_css_class ("hover"));
        target.drop.connect ((value) => {
            drop_zone.remove_css_class ("hover");
            var files = (Gdk.FileList) value.get_boxed ();
            foreach (var f in files.get_files ()) {
                set_installer (f.get_path ());
                return true;
            }
            return false;
        });
        drop_zone.add_controller (target);

        // Actions
        var actions = new Gtk.Box (Gtk.Orientation.HORIZONTAL, 8);
        actions.halign = Gtk.Align.END;
        stop_button = new Gtk.Button.with_label ("Force Stop");
        stop_button.add_css_class (Granite.CssClass.DESTRUCTIVE);
        stop_button.clicked.connect (stop_vm);
        actions.append (stop_button);

        start_button = new Gtk.Button.with_label ("Start Machine");
        start_button.add_css_class (Granite.CssClass.SUGGESTED);
        start_button.clicked.connect (start_vm);
        actions.append (start_button);
        clamp.append (actions);

        var fine = new Gtk.Label ("Prototype: this boots the installer and leaves installing the system to you. Needs QEMU, UEFI firmware and access to /dev/kvm.");
        fine.wrap = true;
        fine.xalign = 0;
        fine.add_css_class ("ml-fineprint");
        clamp.append (fine);

        return pane;
    }

    private Gtk.Widget spec_card (string icon_name, string value, string label) {
        var card = new Gtk.Box (Gtk.Orientation.HORIZONTAL, 12);
        card.add_css_class ("ml-card");
        card.add_css_class ("ml-spec");

        var icon = new Gtk.Image.from_icon_name (icon_name);
        icon.pixel_size = 24;
        card.append (icon);

        var text = new Gtk.Box (Gtk.Orientation.VERTICAL, 0);
        text.valign = Gtk.Align.CENTER;
        var v = new Gtk.Label (value);
        v.xalign = 0;
        v.add_css_class ("ml-spec-value");
        var l = new Gtk.Label (label);
        l.xalign = 0;
        l.add_css_class ("ml-spec-label");
        text.append (v);
        text.append (l);
        card.append (text);
        return card;
    }

    // ---- State ------------------------------------------------------------

    private bool is_running () {
        return vm != null;
    }

    private void update_state () {
        bool running = is_running ();
        start_button.visible = !running;
        stop_button.visible = running;
        start_button.sensitive = installer_path != null;

        status_pill.label = running ? "Running" : "Stopped";
        if (running) {
            status_pill.add_css_class ("running");
            status_pill.remove_css_class ("stopped");
        } else {
            status_pill.remove_css_class ("running");
            status_pill.add_css_class ("stopped");
        }
        sidebar_sub.label = running ? "ARM64 · Running" : "ARM64 · Stopped";

        if (installer_path != null) {
            drop_zone.add_css_class ("chosen");
            drop_title.label = Path.get_basename (installer_path);
            drop_detail.label = installer_path;
        } else {
            drop_zone.remove_css_class ("chosen");
            drop_title.label = "Choose an installer";
            drop_detail.label = "Drop an ARM64 .iso here, or browse for one.";
        }
    }

    private void set_installer (string? path) {
        if (path == null) {
            return;
        }
        installer_path = path;
        update_state ();
    }

    private void notify_user (string message) {
        toast.title = message;
        toast.send_notification ();
    }

    // ---- Actions ----------------------------------------------------------

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
            var file = yield chooser.open (window, null);
            set_installer (file.get_path ());
        } catch (GLib.Error error) {
            // GTK reports user cancellation through the same error path.
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

        // Source tree: build/machine-lab -> ../launcher/run-vm.sh
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

    private void start_vm () {
        if (installer_path == null || is_running ()) {
            return;
        }
        string? launcher = find_launcher ();
        if (launcher == null) {
            show_error ("The QEMU launcher was not found. Set MACHINE_LAB_LAUNCHER to the full path of run-vm.sh.");
            return;
        }

        string vm_dir = Path.build_filename (Environment.get_user_data_dir (), "machine-lab", "omarchy-arm64");
        try {
            string[] argv = { launcher, installer_path, vm_dir };
            vm = new Subprocess.newv (argv, SubprocessFlags.NONE);
            vm.wait_async.begin (null, (obj, res) => {
                try {
                    vm.wait_async.end (res);
                    int code = vm.get_if_exited () ? vm.get_exit_status () : -1;
                    if (code > 0) {
                        notify_user ("The machine stopped with an error (exit %d)".printf (code));
                    } else {
                        notify_user ("Machine stopped");
                    }
                } catch (Error e) {
                    notify_user (e.message);
                }
                vm = null;
                update_state ();
            });
            update_state ();
            notify_user ("Starting Omarchy…");
        } catch (Error error) {
            show_error (error.message);
        }
    }

    private void stop_vm () {
        if (vm != null) {
            vm.force_exit ();
        }
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
