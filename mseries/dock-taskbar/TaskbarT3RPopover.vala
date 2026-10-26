/* SPDX-License-Identifier: GPL-3.0
 * T3-R status popover anchored to its Dock launcher. Reads the app's local status feed only. */
using GLib;
using Gtk;
using Json;

public class Dock.TaskbarT3RPopover : GLib.Object {
    private const string APP_ID = "io.github.techmore.ClaudePantheonRs";
    private Gtk.Popover popup;
    private Gtk.Widget content;
    private bool hosted;
    private bool host_open = false;
    public signal void request_close ();
    public signal void status_changed (bool live, int64 pending, int64 running);
    private Gtk.Stack pages;
    private Gtk.Box github_page;
    private Gtk.Box accounts_page;
    private MSeries.CodexBarIndicator? accounts_indicator;
    private MSeries.RepoBarIndicator? repositories_indicator;
    private string status_path;
    private FileMonitor? monitor;
    private uint app_watch_id = 0;
    private bool application_running = false;
    private uint open_timer = 0;
    private uint close_timer = 0;
    private uint freshness_timer = 0;
    private uint status_expiry = 0;
    private bool pinned = false;
    private Gtk.Label account;
    private Gtk.Label connection;
    private Gtk.Label token_total;
    private Gtk.Label token_counts;
    private Gtk.Label token_scope;
    private Gtk.Label token_period;
    private Gtk.Label token_source;
    private Gtk.Label token_cost;
    private Gtk.Box usage_windows;
    private Gtk.Box activity;
    private Gtk.Label freshness;
    private Gtk.Label error_label;

    public TaskbarT3RPopover (Gtk.Widget anchor, int header_icon_size = 28, bool hosted = false) {
        this.hosted = hosted;
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
        if (!hosted) popup.set_parent (anchor);

        var root = new Gtk.Box (Gtk.Orientation.VERTICAL, 10) {
            width_request = 380,
            margin_top = 12,
            margin_bottom = 12,
            margin_start = 12,
            margin_end = 12
        };

        pages = new Gtk.Stack () { hhomogeneous = false, vhomogeneous = false };
        var switcher = new Gtk.StackSwitcher () { stack = pages, halign = Gtk.Align.FILL, margin_top = 8, margin_start = 8, margin_end = 8 };
        var shell = new Gtk.Box (Gtk.Orientation.VERTICAL, 6);
        shell.append (switcher);
        shell.append (pages);
        accounts_page = new Gtk.Box (Gtk.Orientation.VERTICAL, 0);
        pages.add_titled (accounts_page, "usage", "Usage");
        pages.add_titled (root, "server", "T3 server");
        github_page = new Gtk.Box (Gtk.Orientation.VERTICAL, 0);
        pages.add_titled (github_page, "github", "GitHub");
        pages.notify["visible-child-name"].connect (update_repository_page);

        var heading = new Gtk.Box (Gtk.Orientation.HORIZONTAL, 8);
        var mark = new Gtk.Image.from_icon_name ("io.github.techmore.ClaudePantheonRs") {
            // Keep the existing 28 px size at the 48 px default, then follow the shared dock token.
            pixel_size = header_icon_size
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

        var token_card = new Gtk.Box (Gtk.Orientation.VERTICAL, 4);
        token_card.add_css_class ("taskbar-t3r-card");
        var token_heading = new Gtk.Label ("Tokens · provider total") { xalign = 0 };
        token_heading.add_css_class ("heading");
        token_total = new Gtk.Label ("Token history unavailable") { xalign = 0 };
        token_total.add_css_class ("title-3");
        token_counts = detail_label ("Input — · Output —\nCached input — · Reasoning —");
        token_scope = detail_label ("Provider total across all accounts; not selected-account usage.");
        token_period = detail_label ("Date window unavailable · Unknown");
        token_source = detail_label ("T3 server token history · not read yet");
        token_cost = detail_label ("");
        token_cost.visible = false;
        token_card.append (token_heading);
        token_card.append (token_total);
        token_card.append (token_counts);
        token_card.append (token_cost);
        token_card.append (token_scope);
        token_card.append (token_period);
        token_card.append (token_source);
        root.append (token_card);

        var usage_heading = new Gtk.Label ("Plan windows · selected account") { xalign = 0 };
        usage_heading.add_css_class ("heading");
        root.append (usage_heading);
        usage_windows = new Gtk.Box (Gtk.Orientation.VERTICAL, 6);
        root.append (new Gtk.ScrolledWindow () {
            child = usage_windows,
            hscrollbar_policy = Gtk.PolicyType.NEVER,
            vscrollbar_policy = Gtk.PolicyType.AUTOMATIC,
            propagate_natural_height = true,
            max_content_height = 210
        });

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
        var usage = new Gtk.Button.with_label ("Usage");
        usage.clicked.connect (() => run_action ("usage"));
        var repositories = new Gtk.Button.with_label ("Repositories");
        repositories.clicked.connect (() => run_action ("repositories"));
        var settings = new Gtk.Button.with_label ("Settings");
        settings.clicked.connect (() => run_action ("settings"));
        var shiplog = new Gtk.Button.with_label ("Activity");
        shiplog.tooltip_text = "Shiplog · today's commits, merged PRs and closed issues";
        shiplog.clicked.connect (() => run_action ("activity"));
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
        shell.append (error_label);
        error_label.margin_start = 12;
        error_label.margin_end = 12;

        var open_full = new Gtk.Button.with_label ("Open T3");
        open_full.add_css_class ("suggested-action");
        open_full.clicked.connect (() => run_action ("open-full"));
        var footer = new Gtk.Box (Gtk.Orientation.HORIZONTAL, 6) {
            margin_start = 12, margin_end = 12, margin_bottom = 10
        };
        shiplog.hexpand = true;
        open_full.hexpand = true;
        var machines = new Gtk.Button.with_label ("Fleet");
        machines.tooltip_text = "Remote machine and agent status over SSH";
        machines.clicked.connect (() => run_action ("fleet"));
        footer.append (shiplog);
        footer.append (machines);
        footer.append (open_full);
        shell.append (footer);
        content = new Gtk.ScrolledWindow () {
            child = shell, hscrollbar_policy = Gtk.PolicyType.NEVER,
            propagate_natural_height = true, min_content_height = hosted ? 420 : -1, max_content_height = 640
        };

        if (hosted) content.add_css_class ("taskbar-t3r-popup");
        else popup.child = content;

        if (!hosted) {
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
                stop_freshness_timer ();
                if (repositories_indicator != null) repositories_indicator.closed ();
                if (accounts_indicator != null) accounts_indicator.closed ();
            });
            anchor.unmap.connect (() => {
                cancel_open ();
                cancel_close ();
                popup.popdown ();
            });
        }
        content.unmap.connect (close_host);
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

    public Gtk.Widget get_host_widget () { return content; }

    public void open_host () {
        if (!hosted) return;
        host_open = true;
        reload ();
        update_repository_page ();
        start_freshness_timer ();
    }

    public void close_host () {
        host_open = false;
        stop_freshness_timer ();
        if (accounts_indicator != null) accounts_indicator.closed ();
        if (repositories_indicator != null) repositories_indicator.closed ();
    }

    private bool menu_visible () { return hosted ? host_open : popup.visible; }

    private void dismiss () {
        if (hosted) { close_host (); request_close (); }
        else popup.popdown ();
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
        popup.popup ();
        update_repository_page ();
        start_freshness_timer ();
    }

    private void start_freshness_timer () {
        if (freshness_timer == 0) freshness_timer = Timeout.add_seconds (30, () => {
            reload ();
            return Source.CONTINUE;
        });
    }

    private void update_repository_page () {
        if (menu_visible () && pages.visible_child_name == "usage") {
            if (accounts_indicator == null) {
                accounts_indicator = new MSeries.CodexBarIndicator (true);
                accounts_page.append (accounts_indicator.get_widget ());
            }
            accounts_indicator.opened ();
        } else if (accounts_indicator != null) {
            accounts_indicator.closed ();
        }
        if (!menu_visible () || pages.visible_child_name != "github") {
            if (repositories_indicator != null) repositories_indicator.closed ();
            return;
        }
        if (repositories_indicator == null) {
            repositories_indicator = new MSeries.RepoBarIndicator (true);
            repositories_indicator.get_widget ().width_request = 460;
            github_page.append (repositories_indicator.get_widget ());
        }
        repositories_indicator.opened ();
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
            .taskbar-t3r-popup { font-size: 1.2em; }
            .taskbar-t3r-popup .mseries-codexbar,
            .taskbar-t3r-popup .mseries-repobar { font-size: 1em; }
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
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION + 1);
        style_installed = true;
    }

    private void reload () {
        if (status_expiry != 0) { Source.remove (status_expiry); status_expiry = 0; }
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
        string observed = MSeries.JsonBoundary.text (feed, "writtenAt");
        var observed_at = new DateTime.from_iso8601 (observed, new TimeZone.utc ());
        bool recent = observed_at != null &&
            new DateTime.now_utc ().difference (observed_at) <= 15 * TimeSpan.MINUTE &&
            observed_at.difference (new DateTime.now_utc ()) <= TimeSpan.MINUTE;
        bool live = application_running && connected && !stale && recent;
        // An idle panel still expires its badge; this one-shot never polls collectors.
        if (hosted && live) {
            var remaining = 15 * 60 - new DateTime.now_utc ().difference (observed_at) / TimeSpan.SECOND;
            status_expiry = Timeout.add_seconds ((uint) int64.max (remaining + 1, 1), () => {
                status_expiry = 0;
                reload ();
                return Source.REMOVE;
            });
        }
        string server = MSeries.JsonBoundary.text (feed, "server");
        string selected_id = MSeries.JsonBoundary.text (feed, "selectedProviderId");
        string selected_provider = MSeries.JsonBoundary.text (feed, "selectedProvider");
        string updated = MSeries.JsonBoundary.text (feed, connected ? "updatedAt" : "writtenAt");

        string account_name = selected_id.length > 0
            ? selected_provider.length > 0 ? selected_provider : selected_id
            : "";
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
        var pending = array_member (feed, "pendingPrompts");
        var running = array_member (feed, "running");
        status_changed (live, pending != null ? pending.get_length () : 0,
            running != null ? running.get_length () : 0);
        render_tokens (feed, selected_id, live);
        render_usage (feed, selected_id, live);
        render_activity (feed, live);
        freshness.label = freshness_text (updated);
    }

    private void render_unavailable () {
        status_changed (false, 0, 0);
        account.label = "No T3 account";
        connection.label = "Pair with a T3 server in Settings";
        token_total.label = "Token history unavailable";
        token_counts.label = "Input — · Output —\nCached input — · Reasoning —";
        token_scope.label = "Provider total across all accounts; not selected-account usage.";
        token_period.label = "Date window unavailable · Unavailable";
        token_source.label = "T3 server token history · not read yet";
        token_cost.visible = false;
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

    private void render_tokens (Json.Object feed, string selected_id, bool live) {
        var usage = MSeries.JsonBoundary.object_member (feed, "tokenUsage");
        token_cost.visible = false;
        if (usage == null || selected_id.length == 0) {
            token_total.label = "Token history unavailable";
            token_counts.label = "Input — · Output —\nCached input — · Reasoning —";
            token_scope.label = "Provider total across all accounts; not selected-account usage.";
            token_period.label = "Date window unavailable · Unavailable";
            token_source.label = "T3 server token history · not read yet";
            return;
        }
        string state = MSeries.JsonBoundary.text (usage, "state", "unknown");
        bool known = state == "fresh" || state == "stale";
        string freshness = known ? (live && state == "fresh" ? "Fresh" : "Stale · last known") :
            state == "unavailable" ? "Unavailable" : "Unknown";
        token_total.label = known ? token_count (usage, "totalTokens") + " tokens" :
            "Token history " + (state == "unavailable" ? "unavailable" : "unknown");
        token_counts.label = known ? "Input %s · Output %s\nCached input %s · Reasoning %s".printf (
            token_count (usage, "inputTokens"), token_count (usage, "outputTokens"),
            token_count (usage, "cachedInputTokens"), token_count (usage, "reasoningTokens")) :
            "Input — · Output —\nCached input — · Reasoning —";
        string kind = MSeries.JsonBoundary.text (usage, "providerKind");
        token_scope.label = (kind.length > 0 ? kind + " provider total" : "Provider total") +
            " · all accounts\nNot selected-account usage.";
        string since = MSeries.JsonBoundary.text (usage, "sinceDay");
        string until = MSeries.JsonBoundary.text (usage, "untilDay");
        token_period.label = (since.length > 0 && until.length > 0 ? since + " – " + until :
            "Date window unavailable") + " · " + freshness;
        string read_at = MSeries.JsonBoundary.text (usage, "readAt");
        token_source.label = "T3 server token history · " +
            (read_at.length > 0 ? "read " + read_at : "not read yet");
        double cost = MSeries.JsonBoundary.number (usage, "estimatedCostUsd", -1);
        if (known && cost.is_finite () && cost >= 0) {
            token_cost.label = "Estimated cost · $%.4f USD".printf (cost);
            token_cost.visible = true;
        }
    }

    private void render_usage (Json.Object feed, string selected_id, bool live) {
        clear_box (usage_windows);
        var windows = array_member (feed, "windows");
        uint count = 0;
        if (windows != null && selected_id.length > 0) {
            for (uint i = 0; i < windows.get_length (); i++) {
                var node = windows.get_element (i);
                if (node.get_node_type () != Json.NodeType.OBJECT) continue;
                var window = node.get_object ();
                if (MSeries.JsonBoundary.text (window, "instanceId") != selected_id) continue;
                count++;
                var card = new Gtk.Box (Gtk.Orientation.VERTICAL, 4);
                card.add_css_class ("taskbar-t3r-card");
                string label = MSeries.JsonBoundary.text (window, "label", "Usage");
                card.append (new Gtk.Label (label) { xalign = 0, wrap = true });
                double used = MSeries.JsonBoundary.number (window, "usedPercent", -1);
                bool valid = used.is_finite () && used >= 0 && used <= 100;
                string state = MSeries.JsonBoundary.text (window, "state", "unknown");
                bool fresh = live && state == "fresh" && MSeries.JsonBoundary.flag (window, "live", false);
                string reset = MSeries.JsonBoundary.text (window, "resetsAt");
                var reset_at = new DateTime.from_iso8601 (reset, new TimeZone.utc ());
                if (reset_at != null && reset_at.compare (new DateTime.now_utc ()) <= 0) fresh = false;
                string detail;
                if (!valid || (state != "fresh" && state != "stale")) {
                    detail = state == "unavailable" ? "Usage unavailable" : "Usage unknown";
                } else {
                    detail = fresh ? "%.0f%% used · Fresh".printf (used) :
                        "%.0f%% used · Stale, last known".printf (used);
                }
                card.append (detail_label (detail));
                if (valid && fresh) {
                    var bar = new Gtk.LevelBar () { min_value = 0, max_value = 100, value = used };
                    bar.add_offset_value ("low", 60);
                    bar.add_offset_value ("high", 90);
                    bar.add_offset_value ("full", 100);
                    bar.add_css_class ("taskbar-t3r-gauge");
                    card.append (bar);
                }
                string reset_text = reset_summary (reset);
                card.append (detail_label (reset_text.length > 0 ? reset_text : "Reset time unavailable"));
                usage_windows.append (card);
            }
        }
        if (count == 0) {
            usage_windows.append (detail_label (live ? "T3 has not reported a plan window for this account." :
                "No plan windows available. Reconnect to refresh."));
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
        var info = new DesktopAppInfo (APP_ID + ".desktop");
        if (info == null) {
            error_label.label = "T3 is not installed. Install T3 to open this page.";
            error_label.visible = true;
            return;
        }
        info.launch_action (action, context);
        dismiss ();
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
            dismiss ();
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

    private void stop_freshness_timer () {
        if (freshness_timer != 0) { Source.remove (freshness_timer); freshness_timer = 0; }
    }

    private void cancel_timers () {
        stop_freshness_timer ();
        cancel_open ();
        cancel_close ();
    }

    public override void dispose () {
        if (status_expiry != 0) { Source.remove (status_expiry); status_expiry = 0; }
        cancel_timers ();
        if (accounts_indicator != null) accounts_indicator.closed ();
        if (repositories_indicator != null) repositories_indicator.closed ();
        if (app_watch_id != 0) {
            GLib.Bus.unwatch_name (app_watch_id);
            app_watch_id = 0;
        }
        if (popup != null && popup.get_parent () != null) popup.unparent ();
        monitor = null;
        base.dispose ();
    }
}
