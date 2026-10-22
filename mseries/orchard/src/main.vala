/*
 * Orchard: machines, containers and pods on this Mac.
 * Vala + GTK 4 + Granite 7, laid out like a first-party elementary OS app:
 * one flat sidebar with three sections (Machines under QEMU/KVM, Incus, Podman),
 * a content pane with tabs per page, suggested-action buttons, toasts and an
 * empty-state welcome. The Machines code is Machine Lab's; the Incus and Podman
 * code is Orchard for Incus's, restyled to the same visual language.
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
    public string arch;
}

const Preset[] presets = {
    { "Omarchy", "Arch-based tiling desktop", 4, 6, 32, 7, "https://omarchy.org", "omarchy", "aarch64" },
    { "elementary OS", "Pantheon desktop, daily ARM64 build", 4, 4, 32, 0, "https://elementary.io", "elementary", "aarch64" },
    { "Ubuntu", "Friendly general-purpose desktop", 4, 4, 24, 4, "https://ubuntu.com/download/server/arm", "", "aarch64" },
    { "Debian", "Rock-solid and lightweight", 2, 2, 16, 5, "https://www.debian.org/CD/netinst/", "", "aarch64" },
    { "Fedora", "Fresh packages, GNOME", 4, 4, 24, 0, "https://fedoraproject.org/server/download", "", "aarch64" },
    { "Blank Machine", "Bring any ARM64 .iso", 2, 4, 16, 1, "", "", "aarch64" },
    { "Ubuntu (x86-64)", "Emulated: much slower than ARM64", 2, 4, 24, 4, "https://ubuntu.com/download/desktop", "", "x86_64" },
    { "Debian (x86-64)", "Emulated: much slower than ARM64", 2, 2, 16, 5, "https://www.debian.org/CD/netinst/", "", "x86_64" },
    { "Blank x86-64", "Emulated: bring any amd64 .iso", 2, 4, 16, 3, "", "", "x86_64" }
};

public class MachineRow : SidebarRow {
    public Machine machine { get; construct; }

    public override int group { get { return machine.is_fresh () ? 1 : 0; } }
    public override string sort_key { owned get { return machine.name.down (); } }
    public override string header_title { owned get { return group == 0 ? "YOUR MACHINES" : "NEW — NOT INSTALLED"; } }
    public override string page_name { owned get { return machine.id; } }

    public MachineRow (Machine machine) {
        Object (machine: machine);
    }

    construct {
        build_row ("computer", machine.color);
        machine.state_changed.connect (update);
        update ();
    }

    public void update () {
        name_label.label = machine.name;
        string state = machine.running ? (machine.paused ? "Paused" : "Running") : machine.is_fresh () ? "Not installed" : "Stopped";
        sub_label.label = "%s · %s · %d CPU · %d GiB".printf (machine.emulated ? "x86-64 emulated" : "ARM64", state, machine.cpus, machine.mem_gib);
        set_color (machine.color);
        set_running (machine.running);
    }
}

public class Orchard : Gtk.Application {
    private GenericArray<Machine> machines;
    private Gtk.ApplicationWindow window;
    private Granite.Toast toast;
    private Gtk.ListBox list;
    private Gtk.Stack content;
    private bool special_page = false;
    private Gtk.Widget sidebar_box;
    private Gtk.Widget sidebar_sep;
    private HashTable<string, MachinePage> pages = new HashTable<string, MachinePage> (str_hash, str_equal);
    private uint machine_timer = 0;

    // Incus
    private IncusClient client;
    private HashTable<string, IncusInstancePage> incus_pages = new HashTable<string, IncusInstancePage> (str_hash, str_equal);
    private HashTable<string, IncusRow> incus_rows = new HashTable<string, IncusRow> (str_hash, str_equal);
    private IncusHomeRow incus_home_row;
    private IncusHomePage incus_home;
    private bool incus_busy = false;
    private uint incus_timer = 0;
    private string? pending_select = null;

    // Podman
    private PodmanRow podman_row;
    private PodmanPage podman_page;

    /* The window, once activate () has built it (tests and the screenshot path look at it). */
    public Gtk.ApplicationWindow? main_window { get { return window; } }

    public Orchard (string? id = null) {
        Object (
            application_id: id ?? Config.APP_ID,
            flags: ApplicationFlags.HANDLES_OPEN
        );
        add_main_option ("version", 'v', OptionFlags.NONE, OptionArg.NONE, "Print the version and exit", null);
    }

    protected override int handle_local_options (VariantDict options) {
        if (options.contains ("version")) {
            print ("orchard %s\n", Config.VERSION);
            return 0;
        }
        return -1;
    }

    protected override void startup () {
        base.startup ();
        Granite.init ();

        var gtk_settings = Gtk.Settings.get_default ();
        // GTK animates the text cursor's fade with a frame-clock tick for ten seconds after every
        // keystroke, which repaints the window continuously. A steady cursor keeps idle at 0 % CPU.
        gtk_settings.gtk_cursor_blink = false;
        // Granite.Settings reads the colour-scheme preference through AccountsService; without the
        // service (CI, a bare session) it logs a critical, so the hookup is skipped there.
        if (accounts_service_available ()) {
            var granite_settings = Granite.Settings.get_default ();
            gtk_settings.gtk_application_prefer_dark_theme =
                granite_settings.prefers_color_scheme == Granite.Settings.ColorScheme.DARK;
            granite_settings.notify["prefers-color-scheme"].connect (() => {
                gtk_settings.gtk_application_prefer_dark_theme =
                    granite_settings.prefers_color_scheme == Granite.Settings.ColorScheme.DARK;
            });
        }

        var provider = new Gtk.CssProvider ();
        provider.load_from_resource ("/com/github/techmore/orchard/style.css");
        Gtk.StyleContext.add_provider_for_display (
            Gdk.Display.get_default (), provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        );

        var new_action = new SimpleAction ("new-machine", null);
        new_action.activate.connect (() => add_machine (presets[0]));
        add_action (new_action);
        set_accels_for_action ("app.new-machine", { "<Control>n" });
        var new_incus = new SimpleAction ("new-instance", null);
        new_incus.activate.connect (() => show_incus_dialog ());
        add_action (new_incus);
        set_accels_for_action ("app.new-instance", { "<Control><Shift>n" });
        var palette_action = new SimpleAction ("palette", null);
        palette_action.activate.connect (show_palette);
        add_action (palette_action);
        set_accels_for_action ("app.palette", { "<Control>k" });
        var refresh_action = new SimpleAction ("refresh", null);
        refresh_action.activate.connect (() => {
            var row = list.get_selected_row () as MachineRow;
            if (row != null) {
                pages[row.machine.id].recheck ();
            } else {
                refresh_incus.begin ();
                podman_page.reload.begin ();
            }
        });
        add_action (refresh_action);
        set_accels_for_action ("app.refresh", { "F5", "<Control>r" });
        var fs_action = new SimpleAction ("fullscreen", null);
        fs_action.activate.connect (() => {
            var row = list.get_selected_row () as MachineRow;
            if (row != null) {
                pages[row.machine.id].toggle_fullscreen ();
            }
        });
        add_action (fs_action);
        set_accels_for_action ("app.fullscreen", { "F11" });
        set_accels_for_action ("app.quit", { "<Control>q" });
        var quit = new SimpleAction ("quit", null);
        quit.activate.connect (() => window.close ());
        add_action (quit);
    }

    private static bool accounts_service_available () {
        try {
            var bus = Bus.get_sync (BusType.SYSTEM);
            foreach (var method in new string[] { "NameHasOwner", "ListActivatableNames" }) {
                var reply = bus.call_sync ("org.freedesktop.DBus", "/org/freedesktop/DBus", "org.freedesktop.DBus", method,
                    method == "NameHasOwner" ? new Variant ("(s)", "org.freedesktop.Accounts") : null, null, DBusCallFlags.NONE, 1000);
                if (method == "NameHasOwner") {
                    bool owned;
                    reply.get ("(b)", out owned);
                    if (owned) return true;
                } else {
                    foreach (var name in (string[]) reply.get_child_value (0)) if (name == "org.freedesktop.Accounts") return true;
                }
            }
        } catch (Error e) {
            // no system bus at all
        }
        return false;
    }

    protected override void activate () {
        if (window != null) {
            window.present ();
            return;
        }
        machines = MachineStore.load ();
        MachineStore.discover (machines);
        client = new IncusClient ();

        window = new Gtk.ApplicationWindow (this);
        window.title = "Orchard";
        window.default_width = 980;
        window.default_height = 660;
        window.add_css_class ("orchard-window");
        window.titlebar = new Gtk.Box (Gtk.Orientation.HORIZONTAL, 0) { visible = false };

        var layout = new Gtk.Box (Gtk.Orientation.HORIZONTAL, 0);
        sidebar_box = build_sidebar ();
        layout.append (sidebar_box);
        sidebar_sep = new Gtk.Separator (Gtk.Orientation.VERTICAL);
        layout.append (sidebar_sep);

        content = new Gtk.Stack ();
        content.hhomogeneous = false;   // a wide hidden page must not widen the window
        content.vhomogeneous = false;   // and hidden pages are not measured on every relayout
        content.hexpand = true;
        content.transition_type = Gtk.StackTransitionType.CROSSFADE;
        content.add_named (build_empty_state (), "empty");
        content.add_named (new MacExperiment (), "mac");
        layout.append (content);

        var overlay = new Gtk.Overlay ();
        overlay.child = layout;
        toast = new Granite.Toast ("");
        overlay.add_overlay (toast);
        window.child = overlay;

        // Incus and Podman sections: one home row each, instance rows arrive with the first listing.
        incus_home = new IncusHomePage (client);
        incus_home.toast.connect (send_toast);
        incus_home.create_requested.connect (() => show_incus_dialog ());
        incus_home.refresh_requested.connect (() => refresh_incus.begin ());
        incus_home.tool_requested.connect ((action) => dispatch_command (action, ""));
        content.add_named (incus_home, "incus-home");
        incus_home_row = new IncusHomeRow ();
        list.append (incus_home_row);

        podman_page = new PodmanPage ();
        podman_page.notice.connect (send_toast);
        podman_page.summary.connect ((containers, running, installed) => podman_row.update (containers, running, installed));
        content.add_named (podman_page, "podman");
        podman_row = new PodmanRow ();
        list.append (podman_row);

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
        // Timers run only while the window is on screen; nothing polls once it is closed.
        window.map.connect (() => {
            if (machine_timer == 0) {
                machine_timer = Timeout.add_seconds (2, () => {
                    foreach (var m in machines.data) {
                        m.poll ();
                    }
                    return Source.CONTINUE;
                });
            }
            if (incus_timer == 0) {
                incus_timer = Timeout.add_seconds (3, () => {
                    refresh_incus.begin ();
                    return Source.CONTINUE;
                });
            }
            foreach (var m in machines.data) {
                m.poll ();
            }
            refresh_incus.begin ();
        });
        window.unmap.connect (() => {
            if (machine_timer != 0) { Source.remove (machine_timer); machine_timer = 0; }
            if (incus_timer != 0) { Source.remove (incus_timer); incus_timer = 0; }
        });
        podman_page.reload.begin ();   // one listing so the sidebar row shows the count before the page is opened
        arm_screenshot ();
        window.present ();
    }

    protected override void open (File[] files, string hint) {
        activate ();
        foreach (var file in files) {
            navigate_uri (file.get_uri ());
        }
    }

    /* ORCHARD_SCREENSHOT=<png path> renders the window to a file a few seconds after start;
     * ORCHARD_SCREENSHOT_PAGE=machines|incus|podman|<row name> picks the page first and
     * ORCHARD_SCREENSHOT_QUIT=1 closes the app afterwards. Used for the docs captures: this
     * desktop has no screenshot D-Bus interface, so the app paints itself with GSK. */
    private void arm_screenshot () {
        var target = Environment.get_variable ("ORCHARD_SCREENSHOT");
        if (target == null) return;
        var page = Environment.get_variable ("ORCHARD_SCREENSHOT_PAGE") ?? "machines";
        int delay = 4000;
        var delay_text = Environment.get_variable ("ORCHARD_SCREENSHOT_DELAY");
        if (delay_text != null) int.try_parse (delay_text, out delay);
        Timeout.add (delay, () => {
            if (page == "incus") list.select_row (incus_home_row);
            else if (page == "podman") list.select_row (podman_row);
            else if (page != "machines") select_named (page);
            else { var first = list.get_row_at_index (0); if (first is MachineRow) list.select_row (first); }
            Timeout.add (2500, () => {
                if (Environment.get_variable ("ORCHARD_DEBUG_MEASURE") != null) {
                    for (var c = content.get_first_child (); c != null; c = c.get_next_sibling ()) {
                        int mw, nw, mh, nh;
                        c.measure (Gtk.Orientation.HORIZONTAL, -1, out mw, out nw, null, null);
                        c.measure (Gtk.Orientation.VERTICAL, -1, out mh, out nh, null, null);
                        message ("page %s: min %dx%d natural %dx%d", c.get_type ().name (), mw, mh, nw, nh);
                    }
                }
                try {
                    var paintable = new Gtk.WidgetPaintable (window);
                    var snapshot = new Gtk.Snapshot ();
                    paintable.snapshot (snapshot, window.get_width (), window.get_height ());
                    var node = snapshot.free_to_node ();
                    if (node != null) {
                        var texture = window.get_renderer ().render_texture (node, null);
                        texture.save_to_png (target);
                        message ("Saved screenshot to %s", target);
                    }
                } catch (Error e) {
                    warning ("Screenshot failed: %s", e.message);
                }
                if (Environment.get_variable ("ORCHARD_SCREENSHOT_QUIT") != null) window.close ();
                return Source.REMOVE;
            });
            return Source.REMOVE;
        });
    }

    // ---- Incus ----

    /* Reconcile the sidebar with the instance list: add, update and remove rows and pages. */
    private async void refresh_incus () {
        if (incus_busy) {
            return;
        }
        incus_busy = true;
        Instance[] items = {};
        string? error = null;
        try {
            items = yield client.list_instances ();
        } catch (Error e) {
            error = e.message;
        }
        incus_busy = false;
        if (error != null) {
            incus_home.set_error (error);
            incus_home_row.update (0, 0, error);
            return;
        }
        incus_home_row.update (items.length, running_count (items), null);
        bool rows_changed = false;
        var live = new HashTable<string, bool> (str_hash, str_equal);
        foreach (var inst in items) {
            live[inst.name] = true;
            var row = incus_rows[inst.name];
            if (row != null) {
                row.update (inst);
                incus_pages[inst.name].update (inst);
            } else {
                var page = new IncusInstancePage (client, inst);
                page.toast.connect (send_toast);
                page.changed.connect (() => refresh_incus.begin ());
                incus_pages[inst.name] = page;
                content.add_named (page, "incus:" + inst.name);
                var r = new IncusRow (inst);
                incus_rows[inst.name] = r;
                list.append (r);
                rows_changed = true;
            }
        }
        var gone = new GenericArray<string> ();
        incus_rows.foreach ((name, r) => {
            if (!live.contains (name)) {
                gone.add (name);
            }
        });
        foreach (var name in gone.data) {
            var r = incus_rows[name];
            bool was_selected = list.get_selected_row () == r;
            list.remove (r);
            content.remove (incus_pages[name]);
            incus_rows.remove (name);
            incus_pages.remove (name);
            if (was_selected) {
                list.select_row (incus_home_row);
            }
            rows_changed = true;
        }
        if (rows_changed) {
            list.invalidate_sort ();
            list.invalidate_headers ();
        }
        incus_home.update (items);
        if (pending_select != null && incus_rows.contains (pending_select)) {
            list.select_row (incus_rows[pending_select]);
            pending_select = null;
        }
    }

    private static int running_count (Instance[] items) {
        int n = 0;
        foreach (var i in items) if (i.running) n++;
        return n;
    }

    private void show_incus_dialog (string initial_image = "", bool initial_vm = false) {
        int n = (int) incus_rows.size () + 1;
        string name = "lab-%d".printf (n);
        while (incus_rows.contains (name)) {
            n++;
            name = "lab-%d".printf (n);
        }
        var dialog = new IncusCreateDialog (window, client, name, initial_image, initial_vm);
        dialog.created.connect ((created_name) => {
            send_toast ("Created %s".printf (created_name));
            pending_select = created_name;
            refresh_incus.begin ();
        });
        dialog.present ();
    }

    private void select_incus (string name) {
        var row = incus_rows[name];
        if (row != null) {
            list.select_row (row);
        } else {
            list.select_row (incus_home_row);
            send_toast ("No Incus instance named %s".printf (name));
        }
    }

    /* Select the row whose page or name matches (machines by name or id, instances by name). */
    public bool select_named (string name) {
        for (var r = list.get_row_at_index (0); r != null; r = list.get_row_at_index (r.get_index () + 1)) {
            var sr = (SidebarRow) r;
            var mr = r as MachineRow;
            if (sr.page_name == name || (mr != null && mr.machine.name == name) || (r is IncusRow && ((IncusRow) r).instance.name == name)) {
                list.select_row (r);
                return true;
            }
        }
        return false;
    }

    public void navigate_uri (string uri_text) {
        try {
            var uri = Uri.parse (uri_text, UriFlags.NONE);
            if ((uri.get_scheme () ?? "").down () != "orchard") throw new IOError.INVALID_ARGUMENT ("Not an Orchard link.");
            var section = (uri.get_host () ?? "").down ();
            var target = Uri.unescape_string (uri.get_path ()) ?? "";
            while (target.has_prefix ("/")) target = target.substring (1);
            if (section == "container" || section == "machine" || section == "instance") {
                if (target == "") list.select_row (incus_home_row);
                else if (incus_rows.contains (target)) select_incus (target);
                else { pending_select = target; refresh_incus.begin (); }
            } else if (section == "containers" || section == "machines" || section == "incus" || section == "dashboard") {
                list.select_row (incus_home_row);
            } else if (section == "vm" || section == "vms") {
                if (target == "" || !select_named (target)) {
                    var first = list.get_row_at_index (0);
                    if (first is MachineRow) list.select_row (first); else content.visible_child_name = "empty";
                }
            } else if (section == "podman") {
                list.select_row (podman_row);
            } else if (section == "models" || section == "sandboxes" || section == "systemlogs" || section == "mount" || section == "mounts") {
                dispatch_command (section == "systemlogs" ? "system" : section == "mount" ? "mounts" : section, target);
            } else if (section == "image" || section == "images" || section == "network" || section == "networks" || section == "dns" || section == "profiles" || section == "projects") {
                var kind = section == "image" ? "images" : section == "network" ? "networks" : section == "dns" ? "network-zones" : section;
                dispatch_command (kind, target);
            } else {
                throw new IOError.NOT_SUPPORTED ("This Orchard destination is not available: " + section);
            }
        } catch (Error e) {
            send_toast (e.message);
        }
    }

    private void show_palette () {
        var palette = new CommandPalette (window, client);
        palette.selected.connect (dispatch_command);
        palette.present ();
    }

    /* Actions from the command palette, the Incus page's tool rows and orchard:// links. */
    private void dispatch_command (string action, string target) {
        switch (action) {
        case "dashboard":
            list.select_row (incus_home_row);
            break;
        case "models":
            new ModelsWindow (window).present ();
            break;
        case "sandboxes":
            var sandboxes = new SandboxesWindow (window, client);
            sandboxes.shell_requested.connect ((name) => open_shell (name));
            sandboxes.details_requested.connect ((name) => select_incus (name));
            sandboxes.present ();
            break;
        case "system":
            new SystemWindow (window, client).present ();
            break;
        case "mounts":
            var mounts = new MountsWindow (window, client);
            mounts.open_instance.connect ((name) => select_incus (name));
            mounts.present ();
            break;
        case "image-pull":
            new ImagePullWindow (window, client).present ();
            break;
        case "create":
            show_incus_dialog ();
            break;
        case "preferences":
            open_preferences ();
            break;
        case "refresh":
            refresh_incus.begin ();
            break;
        case "shell":
            open_shell (target);
            break;
        case "stop": case "start": case "restart":
            var page = incus_pages[target];
            if (page != null) page.perform.begin (action);
            break;
        case "inspect":
            select_incus (target);
            break;
        case "logs":
            new LogViewer (window, client, target).present ();
            break;
        case "resources":
            open_resources ("", "");
            break;
        default:
            open_resources (action, target);
            break;
        }
    }

    private void open_resources (string kind, string target) {
        var browser = new ResourceBrowser (window, client, kind, target);
        browser.launch_requested.connect ((fingerprint, vm) => show_incus_dialog ("local:" + fingerprint, vm));
        browser.present ();
    }

    private void open_shell (string name) {
        try {
            IncusShell.open (name);
        } catch (Error e) {
            send_toast ("Couldn't open Terminal: " + e.message);
        }
    }

    private void open_preferences () {
        var preferences = new Preferences ();
        var dialog = new Gtk.Window ();
        dialog.transient_for = window;
        dialog.modal = true;
        dialog.title = "Preferences";
        dialog.default_width = 460;
        dialog.resizable = false;
        var box = new Gtk.Box (Gtk.Orientation.VERTICAL, 14);
        box.margin_top = 20;
        box.margin_bottom = 20;
        box.margin_start = 24;
        box.margin_end = 24;
        var heading = new Gtk.Label ("Incus Preferences");
        heading.add_css_class ("title-2");
        heading.xalign = 0;
        box.append (heading);
        var form = new Gtk.Box (Gtk.Orientation.VERTICAL, 0);
        form.add_css_class ("ml-card");
        var shell = new Gtk.Entry ();
        shell.text = preferences.shell;
        shell.width_chars = 18;
        form.append (OrchardUi.action_row ("Shell in the instance", "Absolute path, started by Open Terminal", shell));
        string[] terminals = { "io.elementary.terminal", "gnome-terminal", "kgx", "xterm" };
        var terminal = new Gtk.DropDown.from_strings (terminals);
        for (uint i = 0; i < terminals.length; i++) if (terminals[i] == preferences.read ("terminal", "io.elementary.terminal")) terminal.selected = i;
        form.append (OrchardUi.action_row ("Terminal application", "Used for Open Terminal and the command palette's shell", terminal));
        var socket = new Gtk.Entry ();
        socket.text = preferences.read ("socket", "/var/lib/incus/unix.socket");
        socket.width_chars = 24;
        form.append (OrchardUi.action_row ("Incus Unix socket", "Restart Orchard to apply", socket, true));
        box.append (form);
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
        var save = new Gtk.Button.with_label ("Save");
        save.add_css_class ("suggested-action");
        save.clicked.connect (() => {
            try {
                if (!shell.text.has_prefix ("/") || shell.text.contains ("\n")) throw new IOError.INVALID_ARGUMENT ("Enter an absolute shell path, such as /bin/sh.");
                if (!socket.text.has_prefix ("/")) throw new IOError.INVALID_ARGUMENT ("Enter an absolute socket path.");
                preferences.write ("shell", shell.text.strip ());
                preferences.write ("terminal", terminals[terminal.selected]);
                preferences.write ("socket", socket.text.strip ());
                dialog.close ();
                send_toast ("Preferences saved");
            } catch (Error e) {
                error_label.label = e.message;
                error_label.visible = true;
            }
        });
        buttons.append (save);
        box.append (buttons);
        dialog.child = box;
        dialog.present ();
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
            var ra = (SidebarRow) a;
            var rb = (SidebarRow) b;
            if (ra.group != rb.group) return ra.group - rb.group;
            return strcmp (ra.sort_key, rb.sort_key);
        });
        list.set_header_func ((row, before) => {
            var r = (SidebarRow) row;
            if (before != null && ((SidebarRow) before).group == r.group) {
                row.set_header (null);
                return;
            }
            var h = new Gtk.Label (r.header_title);
            h.xalign = 0;
            h.add_css_class ("ml-sidebar-title");
            row.set_header (h);
        });
        list.row_selected.connect ((row) => {
            if (row == null) {
                if (!special_page) {
                    content.visible_child_name = "empty";
                }
                return;
            }
            special_page = false;
            content.visible_child_name = ((SidebarRow) row).page_name;
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
            var d = new Gtk.Label ("%s · %s · %d CPU · %d GiB".printf (p.blurb, p.arch == "x86_64" ? "x86-64" : "ARM64", p.cpus, p.mem));
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
        var incus_item = new Gtk.Button ();
        incus_item.add_css_class ("flat");
        var incus_box = new Gtk.Box (Gtk.Orientation.HORIZONTAL, 10);
        var incus_ic = new Gtk.Image.from_icon_name ("package-x-generic");
        incus_ic.pixel_size = 28;
        incus_ic.add_css_class ("ml-row-icon");
        incus_ic.add_css_class ("ml-c-1");
        incus_box.append (incus_ic);
        var incus_tb = new Gtk.Box (Gtk.Orientation.VERTICAL, 0);
        var incus_n = new Gtk.Label ("Incus container or VM…");
        incus_n.xalign = 0;
        incus_n.add_css_class ("ml-machine-name");
        var incus_d = new Gtk.Label ("Seconds to start · shares this Mac's kernel (containers)");
        incus_d.xalign = 0;
        incus_d.add_css_class ("ml-machine-sub");
        incus_tb.append (incus_n);
        incus_tb.append (incus_d);
        incus_box.append (incus_tb);
        incus_item.child = incus_box;
        incus_item.clicked.connect (() => { pop.popdown (); show_incus_dialog (); });
        pbox.append (incus_item);
        var mac_item = new Gtk.Button ();
        mac_item.add_css_class ("flat");
        var mac_lbl = new Gtk.Label ("macOS (experimental)…");
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
        var d = new Gtk.Label ("Pick a starting point. Orchard sets up sensible hardware, then walks you through the installer.");
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
            var sp = new Gtk.Label ("%s · %d CPU · %d GiB RAM · %d GiB disk".printf (p.arch == "x86_64" ? "x86-64 · emulated, slower" : "ARM64", p.cpus, p.mem, p.disk));
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
        var inc = new Gtk.Button ();
        inc.add_css_class ("flat");
        var ib = new Gtk.Box (Gtk.Orientation.HORIZONTAL, 12);
        ib.add_css_class ("ml-gallery-card");
        var ii = new Gtk.Image.from_icon_name ("package-x-generic");
        ii.pixel_size = 40;
        ii.add_css_class ("ml-row-icon");
        ii.add_css_class ("ml-c-1");
        ib.append (ii);
        var it = new Gtk.Box (Gtk.Orientation.VERTICAL, 2);
        it.valign = Gtk.Align.CENTER;
        var in_ = new Gtk.Label ("Incus container or VM");
        in_.xalign = 0;
        in_.add_css_class ("ml-spec-value");
        var ibl = new Gtk.Label ("Light Linux in seconds, via Incus");
        ibl.xalign = 0;
        ibl.add_css_class ("ml-spec-label");
        var isp = new Gtk.Label ("ARM64 · native · starts in seconds");
        isp.xalign = 0;
        isp.add_css_class ("ml-fineprint");
        it.append (in_);
        it.append (ibl);
        it.append (isp);
        ib.append (it);
        inc.child = ib;
        inc.clicked.connect (() => show_incus_dialog ());
        grid.attach (inc, i % 2, i / 2);
        i++;
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
        var mbl = new Gtk.Label ("Experimental: see how it fails");
        mbl.xalign = 0;
        mbl.add_css_class ("ml-spec-label");
        var mlearn = new Gtk.Label ("Tap to run the attempt");
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
        page.fullscreen_toggled.connect ((on) => {
            window.fullscreened = on;
            sidebar_box.visible = !on;
            sidebar_sep.visible = !on;
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
            var mr = r as MachineRow;
            if (mr != null && mr.machine == m) {
                return mr;
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
        special_page = true;
        list.unselect_all ();
        content.visible_child_name = "mac";
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
        m.arch = preset.arch;
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
        dialog.detail = "The machine is removed from Orchard. You can also delete its virtual disk, which cannot be undone.";
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
            var next = list.get_row_at_index (int.min (idx, (int) machines.length - 1)) ?? incus_home_row;
            list.select_row (next);
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

}
