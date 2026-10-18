// Native panel companion; container changes stay in the manager window.
private class OrchardIndicator : Wingpanel.Indicator {
    private IncusClient client = new IncusClient (10);
    private Gtk.Image icon;
    private Gtk.Box display;
    private Gtk.Label badge;
    private HashTable<string, int64?> cpu_samples = new HashTable<string, int64?> (str_hash, str_equal);
    private int64 sample_time = 0;
    private Gtk.Label action_error;
    private OrchardSparkline cpu_history;
    private OrchardSparkline memory_history;
    private Gtk.Label cpu_caption;
    private Gtk.Label memory_caption;
    private Gtk.Box menu;
    private Gtk.Box instances;
    private Gtk.Label summary;
    private bool refreshing = false;
    private GenericSet<string> pending = new GenericSet<string> (str_hash, str_equal);
    private uint timer = 0;

    public OrchardIndicator () {
        Object (code_name: "orchard-incus");
    }

    construct {
        icon = new Gtk.Image.from_icon_name ("orchard-incus-symbolic") {
            pixel_size = 16
        };
        badge = new Gtk.Label ("…");
        badge.add_css_class ("orchard-running-badge");
        display = new Gtk.Box (Gtk.Orientation.HORIZONTAL, 4) {
            tooltip_text = "Orchard for Incus · Connecting to Incus…"
        };
        display.append (icon);
        display.append (badge);
        var style = new Gtk.CssProvider ();
        style.load_from_string (
            ".orchard-running-badge { font-size: 0.8em; font-weight: 600; " +
            "border-radius: 8px; padding: 0 4px; min-width: 10px; " +
            "background-color: alpha(currentColor, 0.12); }");
        Gtk.StyleContext.add_provider_for_display (display.get_display (), style,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION);
        menu = new Gtk.Box (Gtk.Orientation.VERTICAL, 8) {
            margin_top = 12, margin_bottom = 12,
            margin_start = 12, margin_end = 12,
            width_request = 260
        };
        var title = new Gtk.Label ("Orchard for Incus") { xalign = 0 };
        title.add_css_class ("heading");
        menu.append (title);
        summary = new Gtk.Label ("Connecting to Incus…") { xalign = 0, wrap = true };
        summary.add_css_class ("dim-label");
        menu.append (summary);
        cpu_caption = new Gtk.Label ("CPU · collecting baseline") { xalign = 0 }; menu.append (cpu_caption);
        cpu_history = new OrchardSparkline (60) { content_height = 32 }; menu.append (cpu_history);
        memory_caption = new Gtk.Label ("Memory") { xalign = 0 }; menu.append (memory_caption);
        memory_history = new OrchardSparkline (60) { content_height = 32 }; menu.append (memory_history);
        instances = new Gtk.Box (Gtk.Orientation.VERTICAL, 6);
        menu.append (new Gtk.ScrolledWindow () {
            child = instances,
            hscrollbar_policy = Gtk.PolicyType.NEVER,
            propagate_natural_height = true,
            max_content_height = 240
        });
        menu.append (new Gtk.Separator (Gtk.Orientation.HORIZONTAL));
        var open = new Gtk.Button.with_label ("Open Manager…");
        open.add_css_class ("suggested-action");
        open.clicked.connect (() => {
            try {
                var app = new DesktopAppInfo ("com.github.techmore.orchard-incus.desktop");
                if (app == null) {
                    throw new IOError.NOT_FOUND ("Install the Orchard application launcher first.");
                }
                app.launch (null, null);
                close ();
            } catch (Error e) {
                summary.label = "Could not open Orchard: " + e.message;
            }
        });
        menu.append (open);
        action_error = new Gtk.Label ("") { visible = false, xalign = 0, wrap = true }; action_error.add_css_class ("error"); menu.append (action_error);
        visible = true;
        refresh.begin ();
        // Use a weak reference so the timer does not keep a removed indicator alive.
        weak OrchardIndicator indicator = this;
        timer = Timeout.add_seconds (10, () => {
            if (indicator == null) return Source.REMOVE;
            indicator.refresh.begin ();
            return Source.CONTINUE;
        });
    }

    private async void refresh () {
        if (refreshing) return;
        refreshing = true;
        try {
            var items = yield client.list_instances ();
            while (instances.get_first_child () != null) {
                instances.remove (instances.get_first_child ());
            }
            int running = 0;
            int64 memory_used = 0;
            int memory_ready = 0;
            double cores = 0;
            int cpu_ready = 0;
            int64 now = get_monotonic_time ();
            double elapsed = (now - sample_time) / 1000000.0;
            var next_samples = new HashTable<string, int64?> (str_hash, str_equal);
            foreach (var item in items) {
                if (item.running) {
                    running++; memory_used += item.memory_bytes;
                    if (item.memory_available) memory_ready++;
                    var previous = cpu_samples.lookup (item.name);
                    if (sample_time != 0 && item.cpu_available && previous != null && elapsed > 0 && item.cpu_ns >= previous) { cores += (item.cpu_ns - previous) / elapsed / 1000000000.0; cpu_ready++; }
                    if (item.cpu_available) next_samples.insert (item.name, item.cpu_ns);
                }
                var row = new Gtk.Box (Gtk.Orientation.HORIZONTAL, 12);
                var name = new Gtk.Label (item.name) {
                    xalign = 0, hexpand = true,
                    ellipsize = Pango.EllipsizeMode.END,
                    max_width_chars = 24
                };
                var status = new Gtk.Label (item.status) { xalign = 1 };
                status.add_css_class (item.running ? "success" : "dim-label");
                row.append (name);
                row.append (status);
                var action = new Gtk.Button.from_icon_name (item.running ? "media-playback-stop-symbolic" : "media-playback-start-symbolic") {
                    tooltip_text = item.running ? "Stop " + item.name : "Start " + item.name,
                    sensitive = !pending.contains (item.name)
                };
                var name_for_action = item.name;
                var action_name = item.running ? "stop" : "start";
                action.clicked.connect (() => {
                    action.sensitive = false;
                    change_state.begin (name_for_action, action_name);
                });
                row.append (action);
                instances.append (row);
            }
            summary.label = items.length == 0 ? "No local instances" :
                "%d of %d instances running".printf (running, items.length);
            summary.tooltip_text = null;
            badge.label = running.to_string ();
            cpu_caption.label = cpu_ready == running ? "CPU · %.1f%% of host".printf (cores / get_num_processors () * 100) : "CPU · collecting baseline / unavailable";
            if (cpu_ready == running) cpu_history.record (cores);
            memory_caption.label = memory_ready == running ? "Memory · " + format_size ((uint64) memory_used) : "Memory · unavailable";
            if (memory_ready == running) memory_history.record (memory_used);
            display.tooltip_text = "Orchard for Incus · " + summary.label + " · CPU " + (cpu_ready != running ? "collecting baseline" : "%.1f%% of host".printf (cores / get_num_processors () * 100)) + " · Memory " + format_size ((uint64) memory_used);
            sample_time = now; cpu_samples = next_samples;
        } catch (Error e) {
            while (instances.get_first_child () != null) {
                instances.remove (instances.get_first_child ());
            }
            summary.label = "Incus unavailable";
            summary.tooltip_text = e.message;
            badge.label = "—";
            cpu_caption.label = "CPU · unavailable"; memory_caption.label = "Memory · unavailable";
            sample_time = 0; cpu_samples.remove_all ();
            display.tooltip_text = "Orchard for Incus · Incus unavailable";
        }
        refreshing = false;
    }

    private async void change_state (string name, string action) {
        if (pending.contains (name)) return;
        pending.add (name);
        try {
            yield client.change_state (name, action);
            action_error.visible = false;
        } catch (Error e) {
            action_error.label = "Could not " + action + " " + name + ": " + e.message;
            action_error.visible = true;
        }
        pending.remove (name);
        yield refresh ();
    }

    public override Gtk.Widget get_display_widget () { return display; }
    public override Gtk.Widget? get_widget () { return menu; }
    public override void opened () { refresh.begin (); }
    public override void closed () { }
    public override void dispose () {
        if (timer != 0) { Source.remove (timer); timer = 0; }
        base.dispose ();
    }
}

public Wingpanel.Indicator? get_indicator (Module module, Wingpanel.ServerType server_type) {
    if (server_type != Wingpanel.ServerType.SESSION) return null;
    return new OrchardIndicator ();
}
