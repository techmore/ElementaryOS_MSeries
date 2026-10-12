using GLib;
using Gtk;

private class TroubleshooterIndicator : Wingpanel.Indicator {
    private Gtk.Box display;
    private Gtk.Box menu;
    private Gtk.Label badge;
    private Gtk.Label status;
    private Gtk.Label detail;
    private string state_dir;
    private uint timer;

    public TroubleshooterIndicator () {
        Object (code_name: "mseries-troubleshooter");
    }

    construct {
        state_dir = Path.build_filename (Environment.get_home_dir (), ".local/state/mseries-troubleshooter");
        display = new Gtk.Box (Gtk.Orientation.HORIZONTAL, 4);
        var icon = new Gtk.Image.from_icon_name ("mseries-robot-symbolic") { pixel_size = 16 };
        display.append (icon);
        badge = new Gtk.Label ("");
        display.append (badge);
        display.set_tooltip_text ("Local crash troubleshooting · Gemma 4");
        menu = new Gtk.Box (Gtk.Orientation.VERTICAL, 8) {
            margin_top = 12, margin_bottom = 12, margin_start = 12, margin_end = 12,
            width_request = 280
        };
        var title = new Gtk.Label ("Local Troubleshooter") { xalign = 0 };
        title.add_css_class ("heading");
        menu.append (title);
        status = new Gtk.Label ("Watching for crashes") { xalign = 0, wrap = true };
        menu.append (status);
        detail = new Gtk.Label ("Gemma 4 · On-device diagnosis") { xalign = 0, wrap = true };
        detail.add_css_class ("dim-label");
        menu.append (detail);
        var open = new Gtk.Button.with_label ("Analyze Logs…");
        open.add_css_class ("suggested-action");
        open.clicked.connect (() => {
            try {
                var app = new DesktopAppInfo ("mseries-troubleshooter.desktop");
                if (app != null) app.launch (null, null);
            } catch (Error e) { warning ("Cannot open troubleshooter: %s", e.message); }
        });
        menu.append (open);
        var performance = new Gtk.Button.with_label ("Check Performance…");
        performance.clicked.connect (() => {
            try {
                var app = new DesktopAppInfo ("mseries-troubleshooter.desktop");
                if (app != null) app.launch_action ("Performance", new AppLaunchContext ());
            } catch (Error e) { warning ("Cannot open performance check: %s", e.message); }
        });
        menu.append (performance);
        var automatic = new Gtk.CheckButton.with_label ("Automatically diagnose new crashes");
        automatic.active = FileUtils.test (Path.build_filename (state_dir, "auto-diagnose"), FileTest.EXISTS);
        automatic.toggled.connect (() => {
            var path = Path.build_filename (state_dir, "auto-diagnose");
            try {
                DirUtils.create_with_parents (state_dir, 0700);
                if (automatic.active) FileUtils.set_contents (path, "enabled\n");
                else FileUtils.unlink (path);
            } catch (Error e) { warning ("Cannot update automatic diagnosis: %s", e.message); }
        });
        menu.append (automatic);
        var note = new Gtk.Label ("Diagnosis only. Suggested changes are never executed.") { xalign = 0, wrap = true };
        note.add_css_class ("dim-label");
        menu.append (note);
        visible = true;
        refresh ();
        timer = Timeout.add_seconds (10, () => { refresh (); return Source.CONTINUE; });
    }

    private void refresh () {
        try {
            string content;
            if (!FileUtils.get_contents (Path.build_filename (state_dir, "crashes.json"), out content)) return;
            if (content.length > 65536) return;
            var parser = new Json.Parser ();
            parser.load_from_data (content);
            var root = parser.get_root ().get_object ();
            status.label = root.get_string_member ("status");
            var events = root.get_array_member ("events");
            badge.label = events.get_length () > 0 ? events.get_length ().to_string () : "";
            if (events.get_length () > 0) {
                var event = events.get_object_element (events.get_length () - 1);
                detail.label = "%s · PID %s · %s".printf (event.get_string_member ("program"),
                    event.get_string_member ("pid"), event.get_string_member ("signal"));
            }
        } catch (Error e) { status.label = "Crash status unavailable"; }
    }

    public override Gtk.Widget get_display_widget () { return display; }
    public override Gtk.Widget? get_widget () { return menu; }
    public override void opened () { refresh (); }
    public override void closed () { }
    public override void dispose () {
        if (timer != 0) { Source.remove (timer); timer = 0; }
        base.dispose ();
    }
}

public Wingpanel.Indicator? get_indicator (Module module, Wingpanel.ServerType server_type) {
    if (server_type != Wingpanel.ServerType.SESSION) return null;
    return new TroubleshooterIndicator ();
}
