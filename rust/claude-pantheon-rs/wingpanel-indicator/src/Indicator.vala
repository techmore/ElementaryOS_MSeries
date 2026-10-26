/* SPDX-License-Identifier: GPL-3.0
 * T3 menu-bar indicator. Shares the complete native account/token view with the Dock.
 * The badge and view observe the client's local feed; neither opens a T3 connection.
 */
public class ClaudePantheon.Indicator : Wingpanel.Indicator {
    private const string APP_ID = "io.github.techmore.ClaudePantheonRs";
    private Gtk.Box? display_widget;
    private Gtk.Widget? popover_widget;
    private Gtk.Label? badge;
    private Gtk.Image? icon;
    private Dock.TaskbarT3RPopover? usage_view;
    private GLib.DesktopAppInfo? desktop;
    private GLib.FileMonitor? monitor;
    private string status_path;

    public Indicator (string? path = null, GLib.DesktopAppInfo? application = null) {
        Object (code_name: "claude-pantheon");
        status_path = path ?? Path.build_filename (Environment.get_user_cache_dir (), "claude-pantheon-rs", "status.json");
        desktop = application ?? new GLib.DesktopAppInfo (APP_ID + ".desktop");
        visible = true;
        try {
            monitor = GLib.File.new_for_path (status_path).monitor_file (GLib.FileMonitorFlags.NONE);
            monitor.changed.connect (() => reload ());
        } catch (Error e) {
            warning ("T3 status feed monitor: %s", e.message);
        }
    }

    public override Gtk.Widget get_display_widget () {
        if (display_widget == null) {
            icon = new Gtk.Image.from_icon_name (APP_ID + "-symbolic");
            badge = new Gtk.Label ("");
            badge.add_css_class ("caption");
            display_widget = new Gtk.Box (Gtk.Orientation.HORIZONTAL, 3);
            display_widget.append (icon);
            display_widget.append (badge);
            display_widget.update_property (Gtk.AccessibleProperty.LABEL, "T3 provider usage and accounts", -1);
            reload ();
        }
        return display_widget;
    }

    public override Gtk.Widget? get_widget () {
        if (popover_widget == null) {
            if (desktop == null) {
                popover_widget = new Gtk.Label ("Install the native T3 client to view provider usage.") { wrap = true };
            } else {
                usage_view = new Dock.TaskbarT3RPopover (get_display_widget (), desktop, true, 28, status_path);
                usage_view.dismiss_requested.connect (() => close ());
                popover_widget = usage_view.get_widget ();
            }
        }
        return popover_widget;
    }

    public override void opened () {
        get_widget ();
        if (usage_view != null) usage_view.opened ();
        reload ();
    }

    public override void closed () { }

    public void reload () {
        if (badge == null || icon == null) return;
        badge.label = "";
        icon.icon_name = APP_ID + "-symbolic";
        try {
            var parser = new Json.Parser ();
            parser.load_from_file (status_path);
            MSeries.JsonBoundary.validate (parser.get_root ());
            var feed = parser.get_root ().get_object ();
            if (MSeries.JsonBoundary.integer (feed, "schemaVersion") != 1) return;
            var pending = MSeries.JsonBoundary.array (feed, "pendingPrompts");
            int64 prompts = 0;
            for (uint i = 0; pending != null && i < pending.get_length (); i++) {
                var node = pending.get_element (i);
                if (node.get_node_type () != Json.NodeType.OBJECT) continue;
                prompts += int64.max (MSeries.JsonBoundary.integer (node.get_object (), "count", 1), 1);
            }
            var running = MSeries.JsonBoundary.array (feed, "running");
            badge.label = prompts > 0 ? prompts.to_string () : running != null && running.get_length () > 0 ? "•" : "";
            icon.icon_name = prompts > 0 ? "dialog-question-symbolic" : APP_ID + "-symbolic";
        } catch (Error e) {
            display_widget.tooltip_text = "T3 status unavailable";
        }
    }
}

public Wingpanel.Indicator? get_indicator (Module module, Wingpanel.ServerType server_type) {
    return server_type == Wingpanel.ServerType.SESSION ? new ClaudePantheon.Indicator () : null;
}
