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
    private Gtk.ScrolledWindow instance_scroll;
    private Gtk.Label summary;
    private bool refreshing = false;
    private string rows_digest = "uninitialized";
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
            ".orchard-menu .orchard-title { font-size: 1.15em; font-weight: 700; } " +
            ".orchard-menu .orchard-metric { padding: 10px; border-radius: 10px; background: alpha(currentColor, 0.055); } " +
            ".orchard-menu .orchard-instance { padding: 8px 10px; border-radius: 8px; background: alpha(currentColor, 0.04); } " +
            ".orchard-menu .orchard-instance button { border-radius: 6px; } " +
            ".orchard-running-badge { font-size: 0.8em; font-weight: 600; " +
            "border-radius: 8px; padding: 0 4px; min-width: 10px; " +
            "background-color: alpha(currentColor, 0.12); }");
        Gtk.StyleContext.add_provider_for_display (display.get_display (), style,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION);
        menu = new Gtk.Box (Gtk.Orientation.VERTICAL, 8) {
            margin_top = 12, margin_bottom = 12,
            margin_start = 12, margin_end = 12,
            width_request = 300
        };
        menu.add_css_class ("orchard-menu");
        var title = new Gtk.Label ("Orchard for Incus") { xalign = 0 };
        title.add_css_class ("orchard-title");
        menu.append (title);
        summary = new Gtk.Label ("Connecting to Incus…") { xalign = 0, wrap = true };
        summary.add_css_class ("dim-label");
        menu.append (summary);
        var metrics = new Gtk.Box (Gtk.Orientation.HORIZONTAL, 8) { homogeneous = true };
        cpu_caption = new Gtk.Label ("CPU · collecting baseline") { xalign = 0, wrap = true };
        memory_caption = new Gtk.Label ("Memory · waiting for data") { xalign = 0, wrap = true };
        cpu_history = new OrchardSparkline (60) { content_height = 36 };
        memory_history = new OrchardSparkline (60) { content_height = 36 };
        var cpu_card = new Gtk.Box (Gtk.Orientation.VERTICAL, 6);
        cpu_card.add_css_class ("orchard-metric");
        cpu_card.append (cpu_caption); cpu_card.append (cpu_history);
        var memory_card = new Gtk.Box (Gtk.Orientation.VERTICAL, 6);
        memory_card.add_css_class ("orchard-metric");
        memory_card.append (memory_caption); memory_card.append (memory_history);
        metrics.append (cpu_card); metrics.append (memory_card);
        menu.append (metrics);
        var instances_title = new Gtk.Label ("Local instances") { xalign = 0, margin_top = 4 };
        instances_title.add_css_class ("heading");
        menu.append (instances_title);
        instances = new Gtk.Box (Gtk.Orientation.VERTICAL, 6);
        instance_scroll = new Gtk.ScrolledWindow () {
            child = instances,
            hscrollbar_policy = Gtk.PolicyType.NEVER,
            propagate_natural_height = true,
            max_content_height = 240
        };
        menu.append (instance_scroll);
        menu.append (new Gtk.Separator (Gtk.Orientation.HORIZONTAL));
        var open = new Gtk.Button.with_label ("Open Orchard…");
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
            var digest = new StringBuilder ();
            foreach (var item in items) digest.append_printf ("%s\t%s\t%s\n", item.name, item.status, pending.contains (item.name).to_string ());
            bool rebuild_rows = digest.str != rows_digest;
            if (rebuild_rows) {
                while (instances.get_first_child () != null) instances.remove (instances.get_first_child ());
                rows_digest = digest.str;
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
                if (!rebuild_rows) continue;
                var row = new Gtk.Box (Gtk.Orientation.HORIZONTAL, 12);
                var name = new Gtk.Label (item.name) {
                    xalign = 0, hexpand = true,
                    ellipsize = Pango.EllipsizeMode.END,
                    max_width_chars = 24
                };
                name.tooltip_text = item.name;
                var status = new Gtk.Label (item.status) { xalign = 0 };
                status.add_css_class ("caption");
                var identity = new Gtk.Box (Gtk.Orientation.VERTICAL, 2) { hexpand = true };
                identity.append (name); identity.append (status);
                row.add_css_class ("orchard-instance");
                status.add_css_class (item.running ? "success" : "dim-label");
                row.append (identity);
                var action = new Gtk.Button.from_icon_name (item.running ? "media-playback-stop-symbolic" : "media-playback-start-symbolic") {
                    tooltip_text = item.running ? "Stop " + item.name : "Start " + item.name,
                    sensitive = !pending.contains (item.name)
                };
                action.add_css_class ("flat");
                action.update_property (Gtk.AccessibleProperty.LABEL, action.tooltip_text, -1);
                var name_for_action = item.name;
                var action_name = item.running ? "stop" : "start";
                action.clicked.connect (() => {
                    action.sensitive = false;
                    change_state.begin (name_for_action, action_name);
                });
                row.append (action);
                instances.append (row);
            }
            if (items.length == 0 && instances.get_first_child () == null) {
                var empty = new Gtk.Label ("Create your first instance in Orchard.") { wrap = true, xalign = 0, max_width_chars = 30 };
                empty.add_css_class ("dim-label");
                instances.append (empty);
            }
            instance_scroll.min_content_height = int.min (168, items.length * 56);
            summary.label = items.length == 0 ? "No local instances" :
                "%d of %d instances running".printf (running, items.length);
            summary.tooltip_text = null;
            badge.label = running.to_string ();
            cpu_caption.label = cpu_ready == running ? "CPU · %.1f%% of host".printf (cores / get_num_processors () * 100) : "CPU · collecting baseline / unavailable";
            if (cpu_ready == running) cpu_history.record (cores);
            memory_caption.label = memory_ready == running ? "Memory · " + format_size ((uint64) memory_used) : "Memory · unavailable";
            if (memory_ready == running) memory_history.record (memory_used);
            cpu_history.visible = running > 0 && cpu_ready == running && cpu_history.sample_count >= 2;
            memory_history.visible = running > 0 && memory_ready == running && memory_history.sample_count >= 2;
            display.tooltip_text = "Orchard for Incus · " + summary.label + " · CPU " + (cpu_ready != running ? "collecting baseline" : "%.1f%% of host".printf (cores / get_num_processors () * 100)) + " · Memory " + format_size ((uint64) memory_used);
            sample_time = now; cpu_samples = next_samples;
        } catch (Error e) {
            while (instances.get_first_child () != null) {
                instances.remove (instances.get_first_child ());
            }
            rows_digest = "unavailable";
            instance_scroll.min_content_height = 0;
            cpu_history.visible = false; memory_history.visible = false;
            var unavailable = new Gtk.Label ("Open Orchard to check the server connection.") { xalign = 0, wrap = true, max_width_chars = 30 };
            unavailable.add_css_class ("dim-label"); instances.append (unavailable);
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
