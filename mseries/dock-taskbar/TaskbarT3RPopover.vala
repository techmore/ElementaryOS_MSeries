/* SPDX-License-Identifier: GPL-3.0
 * T3-R status popover anchored to its Dock launcher. Reads the app's local status feed only. */
using GLib;
using Gtk;
using Json;

public class Dock.TaskbarT3RPopover : GLib.Object {
    private const string APP_ID = "io.github.techmore.ClaudePantheonRs";
    private Gtk.Popover popup;
    private Dock.App app;
    private GLib.Settings dock_settings = new GLib.Settings ("io.elementary.dock");
    private string status_path;
    private FileMonitor? monitor;
    private uint app_watch_id = 0;
    private bool application_running = false;
    private uint open_timer = 0;
    private uint close_timer = 0;
    private bool pinned = false;
    private Gtk.Label account;
    private Gtk.Label connection;
    private Gtk.Label usage_title;
    private Gtk.Label usage_detail;
    private Gtk.LevelBar usage_bar;
    private Gtk.Label usage_reset;
    private Gtk.Box activity;
    private Gtk.Label freshness;
    private Gtk.Label error_label;

    public bool enabled {
        get { return dock_settings.get_boolean ("taskbar-mode"); }
    }

    public TaskbarT3RPopover (Gtk.Widget anchor, Dock.App app) {
        this.app = app;
        status_path = GLib.Path.build_filename (Environment.get_user_cache_dir (), "claude-pantheon-rs", "status.json");
        install_style ();

        popup = new Gtk.Popover () {
            position = Gtk.PositionType.TOP,
            autohide = false,
            has_arrow = false
        };
        popup.set_offset (0, -1);
        popup.add_css_class (Granite.STYLE_CLASS_MENU);
        popup.add_css_class ("taskbar-t3r-popup");
        popup.set_parent (anchor);

        var root = new Gtk.Box (Gtk.Orientation.VERTICAL, 10) {
            width_request = 380,
            margin_top = 12,
            margin_bottom = 12,
            margin_start = 12,
            margin_end = 12
        };

        var heading = new Gtk.Box (Gtk.Orientation.HORIZONTAL, 8);
        var mark = new Gtk.Image.from_icon_name ("io.github.techmore.ClaudePantheonRs") {
            // Keep the existing 28 px size at the 48 px default, then follow the shared dock token.
            pixel_size = ItemManager.get_icon_size () * 7 / 12
        };
        var title_block = new Gtk.Box (Gtk.Orientation.VERTICAL, 1) { hexpand = true };
        var title = new Gtk.Label ("T3-R Pantheon") { xalign = 0 };
        title.add_css_class ("heading");
        account = new Gtk.Label ("No T3 account") {
            xalign = 0,
            ellipsize = Pango.EllipsizeMode.END,
            max_width_chars = 32
        };
        account.add_css_class ("caption");
        account.add_css_class ("dim-label");
        account.add_css_class ("taskbar-t3r-account");
        title_block.append (title);
        title_block.append (account);
        heading.append (mark);
        heading.append (title_block);
        root.append (heading);

        connection = new Gtk.Label ("Pair with a T3 server in Settings") {
            xalign = 0,
            wrap = true
        };
        connection.add_css_class ("caption");
        root.append (connection);

        var usage_card = new Gtk.Box (Gtk.Orientation.VERTICAL, 5);
        usage_card.add_css_class ("taskbar-t3r-card");
        usage_title = new Gtk.Label ("Waiting for usage") { xalign = 0 };
        usage_detail = new Gtk.Label ("Usage windows appear after the first sync.") {
            xalign = 0,
            wrap = true
        };
        usage_detail.add_css_class ("caption");
        usage_detail.add_css_class ("dim-label");
        usage_bar = new Gtk.LevelBar () { min_value = 0, max_value = 100 };
        usage_bar.add_offset_value ("low", 60);
        usage_bar.add_offset_value ("high", 90);
        usage_bar.add_offset_value ("full", 100);
        usage_bar.add_css_class ("taskbar-t3r-gauge");
        usage_reset = new Gtk.Label ("") { xalign = 0 };
        usage_reset.add_css_class ("caption");
        usage_reset.add_css_class ("dim-label");
        usage_card.append (usage_title);
        usage_card.append (usage_detail);
        usage_card.append (usage_bar);
        usage_card.append (usage_reset);
        root.append (usage_card);

        var activity_title = new Gtk.Label ("Activity") { xalign = 0 };
        activity_title.add_css_class ("heading");
        root.append (activity_title);
        activity = new Gtk.Box (Gtk.Orientation.VERTICAL, 2);
        var activity_scroll = new Gtk.ScrolledWindow () {
            child = activity,
            hscrollbar_policy = Gtk.PolicyType.NEVER,
            vscrollbar_policy = Gtk.PolicyType.AUTOMATIC,
            propagate_natural_height = true,
            min_content_height = 32,
            max_content_height = 180
        };
        root.append (activity_scroll);

        var actions = new Gtk.Box (Gtk.Orientation.HORIZONTAL, 6);
        var new_chat = new Gtk.Button.with_label ("New chat") { hexpand = true };
        new_chat.clicked.connect (() => run_action ("new-thread"));
        var usage = new Gtk.Button.with_label ("Usage");
        usage.clicked.connect (() => run_action ("usage"));
        var settings = new Gtk.Button.with_label ("Settings");
        settings.clicked.connect (() => run_action ("settings"));
        actions.append (new_chat);
        actions.append (usage);
        actions.append (settings);
        root.append (actions);

        freshness = new Gtk.Label ("No status snapshot yet") { xalign = 0 };
        freshness.add_css_class ("caption");
        freshness.add_css_class ("dim-label");
        root.append (freshness);

        error_label = new Gtk.Label ("") { xalign = 0, wrap = true, visible = false };
        error_label.add_css_class ("error");
        root.append (error_label);

        var open_full = new Gtk.Button.with_label ("Open full chat");
        open_full.add_css_class ("suggested-action");
        open_full.clicked.connect (() => run_action ("open-full"));
        root.append (open_full);
        popup.child = root;

        var motion = new Gtk.EventControllerMotion ();
        motion.enter.connect (() => {
            cancel_close ();
            if (enabled && open_timer == 0 && !popup.visible) {
                open_timer = Timeout.add (250, () => {
                    open_timer = 0;
                    show_popup (false);
                    return Source.REMOVE;
                });
            }
        });
        motion.leave.connect (() => {
            cancel_open ();
            schedule_close ();
        });
        anchor.add_controller (motion);

        var popup_motion = new Gtk.EventControllerMotion ();
        popup_motion.enter.connect (cancel_close);
        popup_motion.leave.connect (schedule_close);
        ((Gtk.Widget) popup).add_controller (popup_motion);

        var keys = new Gtk.EventControllerKey ();
        keys.key_pressed.connect ((key) => {
            if (key != Gdk.Key.Escape) return false;
            popup.popdown ();
            return true;
        });
        ((Gtk.Widget) popup).add_controller (keys);
        popup.closed.connect (() => {
            pinned = false;
            cancel_close ();
        });
        anchor.unmap.connect (() => {
            cancel_open ();
            cancel_close ();
            popup.popdown ();
        });
        dock_settings.changed["taskbar-mode"].connect (() => {
            if (!enabled) popup.popdown ();
        });

        app_watch_id = GLib.Bus.watch_name (GLib.BusType.SESSION, APP_ID, GLib.BusNameWatcherFlags.NONE,
            (connection, name, owner) => {
                application_running = true;
                reload ();
            },
            (connection, name) => {
                application_running = false;
                reload ();
            });
        watch_status ();
        reload ();
    }

    public void toggle_from_icon () {
        if (!enabled) return;
        cancel_open ();
        if (popup.visible && pinned) popup.popdown ();
        else show_popup (true);
    }

    private void show_popup (bool interactive) {
        if (!enabled) return;
        cancel_close ();
        if (popup.visible && popup.autohide != interactive) popup.popdown ();
        pinned = interactive;
        popup.autohide = interactive;
        reload ();
        popup.popup ();
    }

    private void watch_status () {
        var file = File.new_for_path (status_path);
        try {
            monitor = file.monitor_file (FileMonitorFlags.NONE);
            monitor.changed.connect ((changed_file, other_file, event) => reload ());
        } catch (Error e) {
            warning ("T3-R status monitor: %s", e.message);
        }
    }

    private static bool style_installed = false;

    private static void install_style () {
        if (style_installed) return;
        var style = new Gtk.CssProvider ();
        style.load_from_string ("""
            popover.taskbar-t3r-popup > contents {
                padding: 0;
                border-radius: 12px;
            }
            .taskbar-t3r-popup .taskbar-t3r-card {
                padding: 10px;
                border-radius: 10px;
                background: alpha(currentColor, 0.045);
                box-shadow: inset 0 0 0 1px alpha(currentColor, 0.06);
            }
            .taskbar-t3r-popup .taskbar-t3r-gauge trough,
            .taskbar-t3r-popup .taskbar-t3r-gauge progress {
                min-height: 10px;
                border-radius: 5px;
            }
            .taskbar-t3r-popup button.flat {
                padding: 6px 8px;
                border-radius: 6px;
            }
        """);
        Gtk.StyleContext.add_provider_for_display (Gdk.Display.get_default (), style,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION);
        style_installed = true;
    }

    private void reload () {
        error_label.visible = false;
        var parser = new Json.Parser ();
        try {
            parser.load_from_file (status_path);
        } catch (Error e) {
            render_unavailable ();
            return;
        }
        var node = parser.get_root ();
        if (node == null || node.get_node_type () != Json.NodeType.OBJECT) {
            render_unavailable ();
            return;
        }
        var feed = node.get_object ();
        bool connected = feed.has_member ("connected") && feed.get_boolean_member ("connected");
        bool stale = feed.has_member ("stale") && feed.get_boolean_member ("stale");
        bool live = application_running && connected && !stale;
        string server = feed.get_string_member_with_default ("server", "");
        string selected_id = feed.get_string_member_with_default ("selectedProviderId", "");
        string selected_provider = feed.get_string_member_with_default ("selectedProvider", "");
        string updated = feed.get_string_member_with_default (connected ? "updatedAt" : "writtenAt", "");

        string account_name = selected_provider.length > 0 ? selected_provider : selected_id;
        account.label = account_name.length > 0 ? account_name : "No provider selected";
        string connection_status;
        if (live) {
            connection_status = server.length > 0 ? "Connected to %s · live status".printf (server) : "Connected · live status";
        } else if (server.length > 0) {
            connection_status = "Offline · last synced from %s".printf (server);
        } else {
            connection_status = "Pair with a T3 server in Settings";
        }
        connection.label = connection_status;
        connection.remove_css_class ("connected");
        connection.remove_css_class ("stale");
        connection.add_css_class (live ? "connected" : "stale");
        render_usage (feed, selected_id, live);
        render_activity (feed, live);
        freshness.label = freshness_text (updated);
    }

    private void render_unavailable () {
        account.label = "No T3 account";
        connection.label = "Pair with a T3 server in Settings";
        usage_title.label = "Waiting for usage";
        usage_detail.label = "Usage windows appear after the first sync.";
        usage_bar.visible = false;
        usage_reset.label = "";
        clear_activity ();
        append_message ("No live activity is available yet.");
        freshness.label = "No status snapshot yet";
    }

    private void render_usage (Json.Object feed, string selected_id, bool live) {
        Json.Array? windows = null;
        if (feed.has_member ("windows") && feed.get_member ("windows").get_node_type () == Json.NodeType.ARRAY) {
            windows = feed.get_array_member ("windows");
        }
        Json.Object? selected = null;
        double highest = -1;
        if (windows != null && selected_id.length > 0) {
            for (uint i = 0; i < windows.get_length (); i++) {
                var window = windows.get_object_element (i);
                if (window.get_string_member_with_default ("instanceId", "") != selected_id) continue;
                double used = window.has_member ("usedPercent") ? window.get_double_member ("usedPercent") : 0;
                if (selected == null || used > highest) {
                    selected = window;
                    highest = used;
                }
            }
        }
        if (selected == null) {
            usage_title.label = "No usage window reported";
            usage_detail.label = live ? "T3 has not reported a quota window yet." : "Usage appears after the first sync.";
            usage_bar.visible = false;
            usage_reset.label = "";
            return;
        }
        string provider = selected.get_string_member_with_default ("provider", "Provider");
        string label = selected.get_string_member_with_default ("label", "Usage");
        string reset = selected.get_string_member_with_default ("resetsAt", "");
        usage_title.label = live ? "%s · %s".printf (provider, label) : "Last known · %s · %s".printf (provider, label);
        usage_detail.label = live ? "%.0f%% used".printf (highest) : "Last known · %.0f%% used".printf (highest);
        usage_bar.value = double.min (double.max (highest, 0.0), 100.0);
        usage_bar.visible = true;
        usage_reset.label = reset_summary (reset);
    }

    private void render_activity (Json.Object feed, bool live) {
        clear_activity ();
        var pending = array_member (feed, "pendingPrompts");
        var running = array_member (feed, "running");
        uint count = 0;
        if (pending != null) {
            for (uint i = 0; i < pending.get_length () && count < 3; i++) {
                append_thread (pending.get_object_element (i), true, live);
                count++;
            }
        }
        if (running != null) {
            for (uint i = 0; i < running.get_length () && count < 3; i++) {
                append_thread (running.get_object_element (i), false, live);
                count++;
            }
        }
        uint total = (pending != null ? pending.get_length () : 0) + (running != null ? running.get_length () : 0);
        if (!live) {
            clear_activity ();
            append_message (total == 0 ? "No live activity is available while offline." :
                "Last sync showed %u active item(s). Reconnect to refresh.".printf (total));
        } else if (total == 0) {
            append_message ("No active work right now.");
        } else if (total > 3) {
            append_message ("More activity is available in the full chat.");
        }
    }

    private void append_thread (Json.Object item, bool pending, bool live) {
        string title = item.get_string_member_with_default ("title", "Untitled thread");
        string id = item.get_string_member_with_default ("id", "");
        string provider = item.get_string_member_with_default ("provider", "");
        int64 requests = item.has_member ("count") ? int64.max (1, item.get_int_member ("count")) : 1;
        string detail = pending ? "Needs approval · %lld request(s)".printf (requests) :
            provider.length > 0 ? "Running · " + provider : "Running";
        var text = new Gtk.Box (Gtk.Orientation.VERTICAL, 1);
        var primary = new Gtk.Label (title) { xalign = 0, ellipsize = Pango.EllipsizeMode.END };
        var secondary = new Gtk.Label (detail) { xalign = 0, ellipsize = Pango.EllipsizeMode.END };
        secondary.add_css_class ("caption");
        secondary.add_css_class (pending ? "warning" : "dim-label");
        text.append (primary);
        text.append (secondary);
        if (live && id.length > 0) {
            var button = new Gtk.Button () { child = text, hexpand = true };
            button.add_css_class ("flat");
            button.clicked.connect (() => open_thread (id));
            activity.append (button);
        } else {
            activity.append (text);
        }
    }

    private static Json.Array? array_member (Json.Object object, string key) {
        if (!object.has_member (key) || object.get_member (key).get_node_type () != Json.NodeType.ARRAY) return null;
        return object.get_array_member (key);
    }

    private void append_message (string message) {
        var label = new Gtk.Label (message) { xalign = 0, wrap = true };
        label.add_css_class ("caption");
        label.add_css_class ("dim-label");
        activity.append (label);
    }

    private void clear_activity () {
        var child = activity.get_first_child ();
        while (child != null) {
            var next = child.get_next_sibling ();
            activity.remove (child);
            child = next;
        }
    }

    private void run_action (string action) {
        var context = Gdk.Display.get_default ().get_app_launch_context ();
        context.set_timestamp (Gdk.CURRENT_TIME);
        app.launch (context, action);
        popup.popdown ();
    }

    private void open_thread (string id) {
        var executable = Environment.find_program_in_path ("claude-pantheon-rs");
        if (executable == null) {
            executable = GLib.Path.build_filename (Environment.get_home_dir (), ".local", "bin", "claude-pantheon-rs");
        }
        try {
            Pid pid;
            Process.spawn_async (null, { executable, "--thread", id }, null, SpawnFlags.SEARCH_PATH, null, out pid);
            if (pid <= 0) throw new IOError.FAILED ("The T3-R application did not start.");
            popup.popdown ();
        } catch (Error e) {
            error_label.label = "Could not open the thread: " + e.message;
            error_label.visible = true;
        }
    }

    private static string reset_summary (string iso) {
        if (iso.length == 0) return "";
        var at = new DateTime.from_iso8601 (iso, new TimeZone.utc ());
        if (at == null) return "";
        var seconds = at.difference (new DateTime.now_utc ()) / TimeSpan.SECOND;
        if (seconds <= 0) return "Resets now";
        if (seconds >= 86400) return "Resets in " + (seconds / 86400).to_string () + " d " + ((seconds % 86400) / 3600).to_string () + " h";
        if (seconds >= 3600) return "Resets in " + (seconds / 3600).to_string () + " h " + ((seconds % 3600) / 60).to_string () + " min";
        return "Resets in " + int64.max (seconds / 60, 1).to_string () + " min";
    }

    private static string freshness_text (string iso) {
        if (iso.length == 0) return "No status snapshot yet";
        var at = new DateTime.from_iso8601 (iso, new TimeZone.utc ());
        if (at == null) return "Status time unavailable";
        var seconds = int64.max (new DateTime.now_utc ().difference (at) / TimeSpan.SECOND, 0);
        if (seconds < 60) return "Updated just now";
        if (seconds < 3600) return "Updated " + (seconds / 60).to_string () + " min ago";
        return "Updated " + at.to_local ().format ("%H:%M");
    }

    private void cancel_open () {
        if (open_timer > 0) {
            Source.remove (open_timer);
            open_timer = 0;
        }
    }

    private void cancel_close () {
        if (close_timer > 0) {
            Source.remove (close_timer);
            close_timer = 0;
        }
    }

    private void schedule_close () {
        cancel_close ();
        if (pinned) return;
        close_timer = Timeout.add (450, () => {
            close_timer = 0;
            popup.popdown ();
            return Source.REMOVE;
        });
    }

    private void cancel_timers () {
        cancel_open ();
        cancel_close ();
    }

    public override void dispose () {
        cancel_timers ();
        if (app_watch_id != 0) {
            GLib.Bus.unwatch_name (app_watch_id);
            app_watch_id = 0;
        }
        if (popup != null && popup.get_parent () != null) popup.unparent ();
        monitor = null;
        base.dispose ();
    }
}
