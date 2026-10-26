/* SPDX-License-Identifier: GPL-3.0
 * T3-R status popover anchored to its Dock launcher. Reads the app's local status feed only. */
using GLib;
using Gtk;
using Json;

public class Dock.TaskbarT3RPopover : GLib.Object {
    private const string APP_ID = "io.github.techmore.ClaudePantheonRs";
    private Gtk.Popover popup;
    private Dock.App app;
    private string status_path;
    private FileMonitor? monitor;
    private uint app_watch_id = 0;
    private bool application_running = false;
    private uint open_timer = 0;
    private uint close_timer = 0;
    private bool pinned = false;
    private Gtk.Label account;
    private Gtk.Label connection;
    private Gtk.Box token_history;
    private Gtk.Box local_accounts;
    private Json.Object local_reports = new Json.Object ();
    private Json.Object local_errors = new Json.Object ();
    private uint local_pending = 0;
    private int64 local_read_at = 0;
    private Gtk.Box usage_windows;
    private Gtk.Box activity;
    private Gtk.Label freshness;
    private Gtk.Label error_label;

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

        var refresh = new Gtk.Button.with_label ("Refresh saved-account usage");
        refresh.clicked.connect (() => refresh_local_accounts (true));
        root.append (refresh);
        var pages = new Gtk.Stack () { vhomogeneous = false };
        root.append (new Gtk.StackSwitcher () { stack = pages, halign = Gtk.Align.FILL, hexpand = true });
        root.append (pages);
        token_history = new Gtk.Box (Gtk.Orientation.VERTICAL, 6);
        pages.add_titled (new Gtk.ScrolledWindow () {
            child = token_history, hscrollbar_policy = Gtk.PolicyType.NEVER,
            propagate_natural_height = true, max_content_height = 350
        }, "tokens", "Tokens");

        var accounts_page = new Gtk.Box (Gtk.Orientation.VERTICAL, 8);
        var local_heading = new Gtk.Label ("Saved accounts · this computer") { xalign = 0 };
        local_heading.add_css_class ("heading");
        accounts_page.append (local_heading);
        local_accounts = new Gtk.Box (Gtk.Orientation.VERTICAL, 6);
        local_accounts.append (detail_label ("Open to read saved Codex, Claude and OpenCode accounts."));
        accounts_page.append (local_accounts);
        var usage_heading = new Gtk.Label ("T3 server · all enabled accounts") { xalign = 0 };
        usage_heading.add_css_class ("heading");
        accounts_page.append (usage_heading);
        usage_windows = new Gtk.Box (Gtk.Orientation.VERTICAL, 6);
        accounts_page.append (usage_windows);
        pages.add_titled (new Gtk.ScrolledWindow () {
            child = accounts_page, hscrollbar_policy = Gtk.PolicyType.NEVER,
            propagate_natural_height = true, max_content_height = 350
        }, "accounts", "Accounts");

        activity = new Gtk.Box (Gtk.Orientation.VERTICAL, 2);
        pages.add_titled (new Gtk.ScrolledWindow () {
            child = activity, hscrollbar_policy = Gtk.PolicyType.NEVER,
            propagate_natural_height = true, min_content_height = 32, max_content_height = 180
        }, "activity", "Activity");

        var actions = new Gtk.Box (Gtk.Orientation.HORIZONTAL, 6);
        var new_chat = new Gtk.Button.with_label ("New chat") { hexpand = true };
        new_chat.clicked.connect (() => run_action ("new-thread"));
        var usage = new Gtk.Button.with_label ("Usage");
        usage.clicked.connect (() => run_action ("usage"));
        var repositories = new Gtk.Button.with_label ("Repositories");
        repositories.clicked.connect (() => run_action ("repositories"));
        var settings = new Gtk.Button.with_label ("Settings");
        settings.clicked.connect (() => run_action ("settings"));
        actions.append (new_chat);
        actions.append (usage);
        actions.append (repositories);
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
        popup.child = new Gtk.ScrolledWindow () {
            child = root,
            hscrollbar_policy = Gtk.PolicyType.NEVER,
            vscrollbar_policy = Gtk.PolicyType.AUTOMATIC,
            propagate_natural_height = true,
            max_content_height = 640
        };

        var motion = new Gtk.EventControllerMotion ();
        motion.enter.connect (() => {
            cancel_close ();
            if (open_timer == 0 && !popup.visible) {
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
        cancel_open ();
        if (popup.visible && pinned) popup.popdown ();
        else show_popup (true);
    }

    private void show_popup (bool interactive) {
        cancel_close ();
        if (popup.visible && popup.autohide != interactive) popup.popdown ();
        pinned = interactive;
        popup.autohide = interactive;
        reload ();
        refresh_local_accounts ();
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
            .taskbar-t3r-popup .taskbar-t3r-gauge block.filled.low { background-color: @success_color; }
            .taskbar-t3r-popup .taskbar-t3r-gauge block.filled.high { background-color: @warning_color; }
            .taskbar-t3r-popup .taskbar-t3r-gauge block.filled.full { background-color: @error_color; }
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
        if (MSeries.JsonBoundary.integer (feed, "schemaVersion") != 1) {
            render_unavailable ();
            return;
        }
        bool connected = MSeries.JsonBoundary.flag (feed, "connected");
        bool stale = MSeries.JsonBoundary.flag (feed, "stale", true);
        bool live = application_running && connected && !stale;
        string server = MSeries.JsonBoundary.text (feed, "server");
        string selected_id = MSeries.JsonBoundary.text (feed, "selectedProviderId");
        string selected_provider = MSeries.JsonBoundary.text (feed, "selectedProvider");
        string updated = MSeries.JsonBoundary.text (feed, connected ? "updatedAt" : "writtenAt");

        string account_name = selected_id.length > 0
            ? selected_provider.length > 0 ? selected_provider : selected_id
            : "";
        account.label = account_name.length > 0 ? "Selected for chat: " + account_name : "No chat provider selected";
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
        render_tokens (feed, live);
        render_usage (feed, live);
        render_activity (feed, live);
        freshness.label = freshness_text (updated);
    }

    private void render_unavailable () {
        account.label = "No T3 account";
        connection.label = "Pair with a T3 server in Settings";
        clear_box (token_history);
        token_history.append (detail_label ("T3 token history unavailable; no token counts are assumed."));
        clear_box (usage_windows);
        usage_windows.append (detail_label ("No usage windows reported."));
        clear_activity ();
        append_message ("No live activity is available yet.");
        freshness.label = "No status snapshot yet";
    }

    private static Gtk.Label detail_label (string text) {
        var label = new Gtk.Label (text) { xalign = 0, wrap = true };
        label.add_css_class ("caption");
        label.add_css_class ("dim-label");
        return label;
    }

    private static string token_count (Json.Object usage, string key) {
        if (!usage.has_member (key)) return "—";
        var node = usage.get_member (key);
        if (node.get_value_type () != typeof (int64) || node.get_int () < 0) return "—";
        return node.get_int ().to_string ();
    }

    private void render_tokens (Json.Object feed, bool live) {
        clear_box (token_history);
        token_history.append (new Gtk.Label ("Token history · all providers") { xalign = 0 });
        var rows = array_member (feed, "tokenHistory");
        if (rows == null || rows.get_length () == 0) {
            token_history.append (detail_label ("No provider history reported; token counts are unknown."));
            return;
        }
        for (uint i = 0; i < rows.get_length (); i++) {
            var node = rows.get_element (i);
            if (node.get_node_type () != Json.NodeType.OBJECT) continue;
            var row = node.get_object ();
            var card = new Gtk.Box (Gtk.Orientation.VERTICAL, 4);
            card.add_css_class ("taskbar-t3r-card");
            string provider = MSeries.JsonBoundary.text (row, "provider", "Unknown provider");
            string state = MSeries.JsonBoundary.text (row, "state", "unknown");
            if (!live && state == "fresh") state = "stale";
            card.append (new Gtk.Label (provider + " · " + token_count (row, "tokens") + " tokens") { xalign = 0, wrap = true });
            card.append (detail_label ("Input %s · Output %s\nCached %s · Reasoning %s".printf (
                token_count (row, "input_tokens"), token_count (row, "output_tokens"),
                token_count (row, "cached_input_tokens"), token_count (row, "reasoning_tokens"))));
            card.append (detail_label (MSeries.JsonBoundary.text (row, "since_day") + " – " +
                MSeries.JsonBoundary.text (row, "until_day") + " · " + state));
            card.append (detail_label ("T3 provider total · all accounts; not account attribution or remaining quota."));
            card.append (detail_label ("History observed: " + MSeries.JsonBoundary.text (row, "read_at", "unknown")));
            double cost = MSeries.JsonBoundary.number (row, "api_equivalent_cost_usd", -1);
            if (cost.is_finite () && cost >= 0) card.append (detail_label ("API-equivalent estimate · $%.4f USD".printf (cost)));
            token_history.append (card);
        }
    }

    private void render_usage (Json.Object feed, bool live) {
        clear_box (usage_windows);
        var rows = array_member (feed, "accounts");
        if (rows == null || rows.get_length () == 0) {
            usage_windows.append (detail_label ("T3 account observations unavailable; no quota is assumed."));
            return;
        }
        for (uint i = 0; i < rows.get_length (); i++) {
            var node = rows.get_element (i);
            if (node.get_node_type () != Json.NodeType.OBJECT) continue;
            var row = node.get_object ();
            var card = new Gtk.Box (Gtk.Orientation.VERTICAL, 4);
            card.add_css_class ("taskbar-t3r-card");
            card.append (new Gtk.Label (MSeries.JsonBoundary.text (row, "title") + " · " +
                MSeries.JsonBoundary.text (row, "instance_id")) { xalign = 0, wrap = true });
            var windows = array_member (row, "windows");
            if (windows == null || windows.get_length () == 0) card.append (detail_label ("Quota not reported · unknown"));
            for (uint j = 0; windows != null && j < windows.get_length (); j++) {
                var wn = windows.get_element (j);
                if (wn.get_node_type () != Json.NodeType.OBJECT) continue;
                var w = wn.get_object ();
                string state = MSeries.JsonBoundary.text (w, "state", "unknown");
                if (!live && state == "fresh") state = "stale";
                append_window (card, MSeries.JsonBoundary.text (w, "title", "Plan window"),
                    MSeries.JsonBoundary.number (w, "used_percent", -1), "used", state,
                    MSeries.JsonBoundary.text (w, "resets_at"),
                    live && state == "fresh" && MSeries.JsonBoundary.flag (w, "live"));
            }
            card.append (detail_label ("T3 server observation: " + MSeries.JsonBoundary.text (row, "checked_at", "unknown")));
            usage_windows.append (card);
        }
    }

    private static void append_window (Gtk.Box card, string title, double value, string unit,
                                       string state, string reset, bool live) {
        var reset_at = new DateTime.from_iso8601 (reset, new TimeZone.utc ());
        if (reset_at != null && reset_at.compare (new DateTime.now_utc ()) <= 0) {
            state = "reset passed · refresh required";
            live = false;
        }
        bool valid = value.is_finite () && value >= 0 && value <= 100;
        string text = valid ? "%s · %.0f%% %s · %s".printf (title, value, unit, state) :
            title + " · quota unknown · " + state;
        card.append (detail_label (text));
        if (valid && live) {
            var bar = new Gtk.LevelBar () { min_value = 0, max_value = 100, value = unit == "left" ? 100 - value : value };
            bar.add_css_class ("taskbar-t3r-gauge");
            bar.update_property (Gtk.AccessibleProperty.LABEL, text, -1);
            card.append (bar);
        }
        string reset_text = reset_summary (reset);
        card.append (detail_label (reset_text.length > 0 ? reset_text : "Reset time not reported"));
    }

    private void refresh_local_accounts (bool force = false) {
        if (local_pending > 0 || (!force && local_read_at > 0 &&
            GLib.get_monotonic_time () - local_read_at < 60 * GLib.TimeSpan.SECOND)) return;
        local_pending = 3;
        read_local.begin ("Codex", "codexbar-accounts.py", "usage", force);
        read_local.begin ("Claude", "codexbar-claude.py", "list", force);
        read_local.begin ("OpenCode", "codexbar-opencode-local.py", "accounts", force);
        render_local_accounts ();
    }

    private async void read_local (string provider, string helper, string command, bool force) {
        try {
            string path = GLib.Path.build_filename (Environment.get_home_dir (), ".local", "lib", "codexbar-cli", helper);
            if (!FileUtils.test (path, FileTest.IS_REGULAR)) path = GLib.Path.build_filename ("/usr/lib/codexbar-cli", helper);
            string[] args = { "python3", path, command };
            if (force) args += "--force";
            string output = yield MSeries.HelperProcess.read (args, 120000);
            var parser = new Json.Parser ();
            parser.load_from_data (output);
            MSeries.JsonBoundary.validate (parser.get_root ());
            var report = parser.get_root ().get_object ();
            if (array_member (report, "accounts") == null) throw new IOError.INVALID_DATA ("Missing account list");
            if (provider == "Codex") yield attach_active_codex (report);
            local_reports.set_object_member (provider, report.ref ());
            if (local_errors.has_member (provider)) local_errors.remove_member (provider);
        } catch (Error e) {
            local_errors.set_string_member (provider, "Saved-account read failed; retained values are last-known.");
        }
        local_pending--;
        if (local_pending == 0) local_read_at = GLib.get_monotonic_time ();
        render_local_accounts ();
    }

    private async void attach_active_codex (Json.Object report) {
        try {
            string cli = GLib.Path.build_filename (Environment.get_home_dir (), ".local", "bin", "codexbar");
            string output = yield MSeries.HelperProcess.read ({ cli, "usage", "--provider", "codex", "--format", "json" }, 60000);
            var parser = new Json.Parser ();
            parser.load_from_data (output);
            var root = parser.get_root ();
            if (root == null || root.get_node_type () != Json.NodeType.ARRAY || root.get_array ().get_length () == 0) return;
            var row_node = root.get_array ().get_element (0);
            MSeries.JsonBoundary.validate (row_node);
            var usage = MSeries.JsonBoundary.object_member (row_node.get_object (), "usage");
            if (usage == null) return;
            string email = MSeries.JsonBoundary.text (usage, "accountEmail");
            var observed = new DateTime.from_iso8601 (MSeries.JsonBoundary.text (usage, "updatedAt"), new TimeZone.utc ());
            if (email.length == 0 || observed == null) return;
            var accounts = array_member (report, "accounts");
            for (uint i = 0; accounts != null && i < accounts.get_length (); i++) {
                var account = accounts.get_object_element (i);
                if (!MSeries.JsonBoundary.flag (account, "active") ||
                    MSeries.JsonBoundary.text (account, "email") != email) continue;
                var windows = new Json.Array ();
                foreach (string key in new string[] { "primary", "secondary", "tertiary" }) {
                    var window = MSeries.JsonBoundary.object_member (usage, key);
                    if (window == null) continue;
                    double used = MSeries.JsonBoundary.number (window, "usedPercent", -1);
                    if (!used.is_finite () || used < 0 || used > 100) continue;
                    var normalized = new Json.Object ();
                    int64 minutes = MSeries.JsonBoundary.integer (window, "windowMinutes");
                    normalized.set_string_member ("label", minutes >= 1440 ? (minutes / 1440).to_string () + " day" :
                        minutes >= 60 ? (minutes / 60).to_string () + " hour" :
                        minutes > 0 ? minutes.to_string () + " min" : key);
                    normalized.set_double_member ("remaining", 100 - used);
                    normalized.set_string_member ("resetsAt", MSeries.JsonBoundary.text (window, "resetsAt"));
                    windows.add_object_element (normalized);
                }
                account.set_array_member ("windows", windows);
                account.set_int_member ("fetchedAt", observed.to_unix ());
                account.set_boolean_member ("stale", false);
            }
        } catch (Error e) {
            // The saved identity still renders; an unavailable active reading stays unknown.
        }
    }

    private void render_local_accounts () {
        clear_box (local_accounts);
        foreach (string provider in new string[] { "Codex", "Claude", "OpenCode" }) {
            var report = MSeries.JsonBoundary.object_member (local_reports, provider);
            bool failed = local_errors.has_member (provider) || (report != null &&
                (MSeries.JsonBoundary.flag (report, "failed") || MSeries.JsonBoundary.flag (report, "stale")));
            var accounts = report != null ? array_member (report, "accounts") : null;
            if (accounts == null || accounts.get_length () == 0) {
                local_accounts.append (detail_label (provider + (failed ? " · account source unavailable" :
                    local_pending > 0 ? " · reading saved accounts…" : " · no saved accounts reported")));
                continue;
            }
            for (uint i = 0; i < accounts.get_length (); i++) {
                var node = accounts.get_element (i);
                if (node.get_node_type () != Json.NodeType.OBJECT) continue;
                var account = node.get_object ();
                var card = new Gtk.Box (Gtk.Orientation.VERTICAL, 4);
                card.add_css_class ("taskbar-t3r-card");
                string name = MSeries.JsonBoundary.text (account, "email", "Saved account");
                card.append (new Gtk.Label (provider + " · " + name +
                    (MSeries.JsonBoundary.flag (account, "active") ? " · active" : "")) { xalign = 0, wrap = true });
                string state = "observation time unknown";
                double fetched = MSeries.JsonBoundary.number (account, "fetchedAt", -1);
                int64 now = new DateTime.now_utc ().to_unix ();
                if (fetched >= 0 && fetched <= now && now - fetched <= 900) state = "fresh";
                if (failed || MSeries.JsonBoundary.flag (account, "stale") ||
                    MSeries.JsonBoundary.text (account, "error").length > 0 ||
                    (fetched >= 0 && now - fetched > 900)) state = "stale · last known";
                var windows = array_member (account, "windows");
                if (windows == null || windows.get_length () == 0)
                    card.append (detail_label ("Quota unknown · this account has no reported windows"));
                for (uint j = 0; windows != null && j < windows.get_length (); j++) {
                    var wn = windows.get_element (j);
                    if (wn.get_node_type () != Json.NodeType.OBJECT) continue;
                    var w = wn.get_object ();
                    append_window (card, MSeries.JsonBoundary.text (w, "label", "Plan window"),
                        MSeries.JsonBoundary.number (w, "remaining", -1), "left", state,
                        MSeries.JsonBoundary.text (w, "resetsAt"), state == "fresh");
                }
                card.append (detail_label ("Computer-local saved account · " + MSeries.JsonBoundary.text (account, "plan")));
                if (fetched >= 0 && fetched <= now) {
                    var observed = new DateTime.from_unix_utc ((int64) fetched);
                    card.append (detail_label ("Observed: " + observed.format ("%Y-%m-%d %H:%M UTC")));
                }
                if (failed) card.append (detail_label (MSeries.JsonBoundary.text (local_errors, provider)));
                local_accounts.append (card);
            }
        }
    }

    private static void clear_box (Gtk.Box box) {
        var child = box.get_first_child ();
        while (child != null) {
            var next = child.get_next_sibling ();
            box.remove (child);
            child = next;
        }
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
        string model = item.get_string_member_with_default ("model", "");
        int64 requests = item.has_member ("count") ? int64.max (1, item.get_int_member ("count")) : 1;
        string detail = pending ? "Needs approval · %s request(s)".printf (requests.to_string ()) :
            "Running";
        if (model.length > 0) detail += " · Model: %s".printf (model);
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
        if (seconds <= 0) return "Reset passed · refresh required";
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
