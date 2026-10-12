/* A small StatusNotifier host for Signal's tray icon in Pantheon Wingpanel. */
using GLib;
using Gtk;
using Wingpanel;

[DBus (name = "org.kde.StatusNotifierItem")]
private interface StatusNotifierItem : Object {
    public abstract string Id { owned get; }
    public abstract string Title { owned get; }
    public abstract string Status { owned get; }
    public abstract string? IconName { owned get; }
    public abstract string? IconThemePath { owned get; }
    public abstract string? AttentionIconName { owned get; }
    public abstract IconPixmap[]? IconPixmap { owned get; }
    public abstract IconPixmap[]? AttentionIconPixmap { owned get; }
    public abstract bool ItemIsMenu { get; }
    public abstract async void Activate (int x, int y) throws Error;
    public abstract async void ContextMenu (int x, int y) throws Error;
    public signal void NewTitle ();
    public signal void NewIcon ();
    public signal void NewAttentionIcon ();
    public signal void NewStatus (string status);
}

[DBus (name = "org.kde.StatusNotifierWatcher")]
private interface StatusNotifierWatcherProxy : Object {
    public abstract async void RegisterStatusNotifierHost (string service) throws Error;
    public abstract string[] RegisteredStatusNotifierItems { owned get; }
    public signal void StatusNotifierItemRegistered (string service);
    public signal void StatusNotifierItemUnregistered (string service);
}

[DBus (signature = "(iiay)")]
private struct IconPixmap {
    public int width;
    public int height;
    public uint8[] data;
}

[DBus (name = "org.kde.StatusNotifierWatcher")]
private class StatusNotifierWatcher : Object {
    private Gee.ArrayList<string> items = new Gee.ArrayList<string> ();

    public async void RegisterStatusNotifierItem (string service, BusName sender) throws Error {
        var normalized = service;
        if (service.has_prefix ("/")) {
            normalized = sender + ":" + service;
        }
        if (!items.contains (normalized)) {
            items.add (normalized);
            StatusNotifierItemRegistered (normalized);
            var owner = normalized;
            var separator = owner.last_index_of (":");
            if (separator > 0) {
                owner = owner.substring (0, separator);
            }
            Bus.watch_name (BusType.SESSION, owner, BusNameWatcherFlags.NONE, null, (connection, name) => {
                if (items.remove (normalized)) {
                    StatusNotifierItemUnregistered (normalized);
                }
            });
        }
    }

    public async void RegisterStatusNotifierHost (string service) throws Error {
        StatusNotifierHostRegistered ();
    }

    public string[] RegisteredStatusNotifierItems {
        owned get {
            var result = new string[items.size];
            for (int i = 0; i < items.size; i++) {
                result[i] = items[i];
            }
            return result;
        }
    }

    public bool IsStatusNotifierHostRegistered { get { return true; } }
    public int ProtocolVersion { get { return 0; } }

    public signal void StatusNotifierItemRegistered (string service);
    public signal void StatusNotifierItemUnregistered (string service);
    public signal void StatusNotifierHostRegistered ();
}

private class TrayItem : Gtk.Box {
    private StatusNotifierItem proxy;
    private Gtk.Image image;
    private string title;
    private string service;
    private string bus_name;
    private string object_path;
    public signal void vanished ();

    public TrayItem (string service, string bus_name, string object_path) {
        GLib.Object (orientation: Gtk.Orientation.HORIZONTAL, spacing: 0);
        this.service = service;
        this.bus_name = bus_name;
        this.object_path = object_path;
        title = "Application tray item";
        image = new Gtk.Image () { pixel_size = 18 };
        append (image);
        set_visible (false);
        set_tooltip_text (title);

        var context_click = new Gtk.GestureClick () { button = Gdk.BUTTON_SECONDARY };
        context_click.pressed.connect ((n_press, x, y) => {
            proxy.ContextMenu.begin ((int) x, (int) y, (obj, res) => {
                try { proxy.ContextMenu.end (res); } catch (Error e) { }
            });
        });
        add_controller (context_click);

        initialize.begin ();
    }

    public void activate_item () {
        if (proxy == null) {
            return;
        }
        proxy.Activate.begin (0, 0, (obj, res) => {
            try { proxy.Activate.end (res); } catch (Error e) { }
        });
    }

    private async void initialize () {
        try {
            proxy = yield Bus.get_proxy<StatusNotifierItem> (
                BusType.SESSION, bus_name, object_path, DBusProxyFlags.NONE
            );
            // This host exists for Signal; leave other apps' tray items alone.
            if (!proxy.Id.down ().contains ("signal")) {
                vanished ();
                return;
            }
            proxy.NewTitle.connect (() => update_title ());
            proxy.NewIcon.connect (() => update_icon ());
            proxy.NewAttentionIcon.connect (() => update_icon ());
            proxy.NewStatus.connect ((status) => update_status (status));
            update_title ();
            update_icon ();
            update_status (proxy.Status);
        } catch (Error e) {
            vanished ();
        }
    }

    private void update_title () {
        var value = proxy.Title;
        if (value != null && value.length > 0) {
            title = value;
            set_tooltip_text (title);
        }
    }

    private void update_status (string status) {
        if (status == "Passive") {
            set_visible (false);
        } else {
            set_visible (true);
            update_icon ();
        }
    }

    private void update_icon () {
        var status = proxy.Status;
        if (status == "NeedsAttention") {
            var attention_name = proxy.AttentionIconName;
            if (attention_name != null && attention_name.length > 0) {
                image.set_from_icon_name (attention_name);
                return;
            }
            var attention_pixmaps = proxy.AttentionIconPixmap;
            if (attention_pixmaps != null && set_pixmap (attention_pixmaps)) {
                return;
            }
        }

        var icon_name = proxy.IconName;
        if (icon_name != null && icon_name.length > 0) {
            // Electron writes each icon change to a new status_icon_N.png in a
            // temp directory. GTK's icon theme never rescans that directory, so
            // load the file directly instead of looking the name up.
            var icon_theme_path = proxy.IconThemePath;
            if (icon_theme_path != null && icon_theme_path.length > 0 &&
                set_icon_file (Path.build_filename (icon_theme_path, icon_name + ".png"))) {
                icon_retry = false;
                return;
            }
            // The file may still be mid-write; look once more shortly.
            if (!icon_retry && icon_theme_path != null && icon_theme_path.length > 0) {
                icon_retry = true;
                Timeout.add (300, () => { update_icon (); return Source.REMOVE; });
            }
            if (Gtk.IconTheme.get_for_display (Gdk.Display.get_default ()).has_icon (icon_name)) {
                image.set_from_icon_name (icon_name);
                return;
            }
        }
        var pixmaps = proxy.IconPixmap;
        if (pixmaps != null && set_pixmap (pixmaps)) {
            return;
        }
        image.set_from_icon_name ("org.signal.Signal");
    }

    private bool icon_retry = false;

    private bool set_icon_file (string path) {
        try {
            var pixbuf = new Gdk.Pixbuf.from_file_at_size (path, 36, 36);
            image.set_from_paintable (Gdk.Texture.for_pixbuf (pixbuf));
            return true;
        } catch (Error e) {
            return false;
        }
    }

    private bool set_pixmap (IconPixmap[]? pixmaps) {
        if (pixmaps == null || pixmaps.length == 0) {
            return false;
        }

        int best = -1;
        int best_diff = int.MAX;
        for (int i = 0; i < pixmaps.length; i++) {
            var candidate = pixmaps[i];
            if (candidate.width <= 0 || candidate.height <= 0 ||
                candidate.width > 512 || candidate.height > 512) {
                continue;
            }
            var diff = (candidate.width - 18).abs () + (candidate.height - 18).abs ();
            if (diff < best_diff) {
                best = i;
                best_diff = diff;
            }
        }
        if (best < 0) {
            return false;
        }

        var pixmap = pixmaps[best];
        var expected = (size_t) pixmap.width * (size_t) pixmap.height * 4;
        if (pixmap.data.length < expected) {
            return false;
        }

        uint8[] rgba = new uint8[expected];
        for (size_t i = 0; i < expected; i += 4) {
            rgba[i] = pixmap.data[i + 1];
            rgba[i + 1] = pixmap.data[i + 2];
            rgba[i + 2] = pixmap.data[i + 3];
            rgba[i + 3] = pixmap.data[i];
        }

        var bytes = new Bytes (rgba);
        var pixbuf = new Gdk.Pixbuf.from_bytes (
            bytes, Gdk.Colorspace.RGB, true, 8,
            pixmap.width, pixmap.height, pixmap.width * 4
        );
        image.set_from_paintable (Gdk.Texture.for_pixbuf (pixbuf));
        return true;
    }
}

private class SignalTrayIndicator : Wingpanel.Indicator {
    private Gtk.Box display;
    private Gtk.Box menu;
    private StatusNotifierWatcher? watcher;
    private StatusNotifierWatcherProxy? watcher_proxy;
    private Gee.HashMap<string, TrayItem> tray_items = new Gee.HashMap<string, TrayItem> ();
    private uint watcher_name_id = 0;
    private uint host_name_id = 0;
    private string host_name;

    public SignalTrayIndicator () {
        GLib.Object (code_name: "signal-tray");
        visible = false;
    }

    construct {
        display = new Gtk.Box (Gtk.Orientation.HORIZONTAL, 2);
        menu = new Gtk.Box (Gtk.Orientation.VERTICAL, 10) {
            margin_top = 12,
            margin_bottom = 12,
            margin_start = 12,
            margin_end = 12,
            width_request = 260
        };
        var title = new Gtk.Label ("Signal Beta") {
            xalign = 0,
            halign = Gtk.Align.START
        };
        title.add_css_class ("heading");
        menu.append (title);
        var hint = new Gtk.Label ("Open Signal to link your phone or reply to messages.") {
            xalign = 0,
            wrap = true,
            halign = Gtk.Align.START
        };
        hint.add_css_class ("dim-label");
        menu.append (hint);
        var open_button = new Gtk.Button.with_label ("Open Signal");
        open_button.add_css_class ("suggested-action");
        open_button.clicked.connect (() => activate_signal ());
        menu.append (open_button);
        host_name = "org.kde.StatusNotifierHost-%d".printf ((int) Posix.getpid ());
        start_watcher ();
    }

    private void start_watcher () {
        watcher = new StatusNotifierWatcher ();
        watcher_name_id = Bus.own_name (
            BusType.SESSION,
            "org.kde.StatusNotifierWatcher",
            BusNameOwnerFlags.NONE,
            (connection) => {
                try {
                    connection.register_object<StatusNotifierWatcher> ("/StatusNotifierWatcher", watcher);
                } catch (Error e) {
                    warning ("Could not export StatusNotifierWatcher: %s", e.message);
                }
            },
            (connection, name) => connect_to_watcher.begin (),
            (connection, name) => connect_to_watcher.begin ()
        );
        host_name_id = Bus.own_name (BusType.SESSION, host_name, BusNameOwnerFlags.NONE);
    }

    private async void connect_to_watcher () {
        try {
            watcher_proxy = yield Bus.get_proxy<StatusNotifierWatcherProxy> (
                BusType.SESSION,
                "org.kde.StatusNotifierWatcher",
                "/StatusNotifierWatcher",
                DBusProxyFlags.NONE
            );
            watcher_proxy.StatusNotifierItemRegistered.connect (on_item_registered);
            watcher_proxy.StatusNotifierItemUnregistered.connect (on_item_unregistered);
            yield watcher_proxy.RegisterStatusNotifierHost (host_name);
            foreach (var service in watcher_proxy.RegisteredStatusNotifierItems) {
                on_item_registered (service);
            }
        } catch (Error e) {
            Timeout.add_seconds (2, () => {
                connect_to_watcher.begin ();
                return Source.REMOVE;
            });
        }
    }

    private void on_item_registered (string service) {
        if (tray_items.has_key (service)) {
            return;
        }
        string bus_name;
        string object_path;
        var slash = service.index_of ("/");
        if (slash > 0) {
            var before = service.substring (0, slash);
            var colon = before.last_index_of (":");
            if (colon > 0) {
                bus_name = service.substring (0, colon);
                object_path = service.substring (colon + 1);
            } else {
                bus_name = before;
                object_path = service.substring (slash);
            }
        } else {
            bus_name = service;
            object_path = "/StatusNotifierItem";
        }

        var item = new TrayItem (service, bus_name, object_path);
        item.vanished.connect (() => on_item_unregistered (service));
        tray_items.set (service, item);
        display.append (item);
        item.notify["visible"].connect (() => update_indicator_visibility ());
    }

    private void on_item_unregistered (string service) {
        var item = tray_items.get (service);
        if (item != null) {
            display.remove (item);
            tray_items.unset (service);
        }
        update_indicator_visibility ();
    }

    private void update_indicator_visibility () {
        bool any_visible = false;
        foreach (var item in tray_items.values) {
            if (item.get_visible ()) {
                any_visible = true;
                break;
            }
        }
        visible = any_visible;
    }

    private void activate_signal () {
        var binary = Path.build_filename (Environment.get_home_dir (), ".local", "bin", "signal-desktop");
        string[] argv;
        if (FileUtils.test (binary, FileTest.IS_EXECUTABLE)) {
            argv = { binary, "--use-tray-icon" };
        } else {
            argv = { "flatpak", "run", "org.signal.Signal" };
        }
        try {
            Pid child_pid;
            Process.spawn_async (null, argv, null, SpawnFlags.SEARCH_PATH, null, out child_pid);
        } catch (Error e) {
            warning ("Could not open Signal: %s", e.message);
        }
    }

    public override Gtk.Widget get_display_widget () {
        return display;
    }

    public override Gtk.Widget? get_widget () {
        return menu;
    }

    public override void opened () { }
    public override void closed () { }

    public override void dispose () {
        if (watcher_name_id != 0) {
            Bus.unown_name (watcher_name_id);
            watcher_name_id = 0;
        }
        if (host_name_id != 0) {
            Bus.unown_name (host_name_id);
            host_name_id = 0;
        }
        base.dispose ();
    }
}

public Wingpanel.Indicator? get_indicator (Module module, Wingpanel.ServerType server_type) {
    if (server_type != Wingpanel.ServerType.SESSION) {
        return null;
    }
    return new SignalTrayIndicator ();
}
