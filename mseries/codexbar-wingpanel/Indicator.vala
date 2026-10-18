/* CodexBar quota indicator for Pantheon's Wingpanel. */
using GLib;
using Gtk;
using Json;
using Wingpanel;

namespace MSeries {
    public class CodexBarIndicator : Wingpanel.Indicator {
        private Gtk.Label panel_label;
        private Gtk.Box panel_display;
        private Gtk.Box menu;
        private Gtk.Label subtitle_label;
        private Gtk.Label chip_label;
        private Gtk.Stack pages;
        private Gtk.Box quota_box;
        private Gtk.Box sessions_box;
        private Gtk.Box spend_box;
        private Gtk.Button refresh_button;
        private Gtk.Stack refresh_display;
        private Gtk.Spinner refresh_spinner;
        private uint refresh_poll_source = 0;
        private string executable;
        private bool request_in_flight = false;
        private bool sessions_in_flight = false;
        private bool snapshot_busy = false;
        private bool snapshot_stale = false;
        private uint refresh_poll_count = 0;
        private bool refresh_after_snapshot = false;
        private RefreshPolicy refresh_policy = new RefreshPolicy ();

        // The popover is rebuilt only when the data it shows changes, so an open
        // popover never flickers and the five-second poll stays cheap.
        private string last_digest = "";
        private int64 newest_update_unix = 0;
        private string sessions_text = "";
        private string sessions_error = "";
        private int64 sessions_fetched_us = 0;
        private Json.Object? claude_data = null;
        private bool claude_in_flight = false;
        private int64 claude_fetched_us = 0;
        private Json.Array? codex_accounts = null;
        private bool codex_accounts_in_flight = false;
        private int64 codex_accounts_fetched_us = 0;
        private Json.Object? opencode_local = null;
        private bool opencode_local_in_flight = false;
        private int64 opencode_local_fetched_us = 0;

        public CodexBarIndicator () {
            GLib.Object (code_name: "codexbar");
        }

        construct {
            executable = GLib.Path.build_filename (Environment.get_home_dir (), ".local", "bin", "codexbar-linux");

            var panel_icon = new Gtk.Image.from_icon_name ("mseries-codexbar-openai-symbolic") {
                pixel_size = 12
            };
            panel_icon.add_css_class ("symbolic");
            panel_label = new Gtk.Label ("—") {
                ellipsize = Pango.EllipsizeMode.END,
                max_width_chars = 52
            };
            panel_label.add_css_class ("caption");
            panel_label.add_css_class ("mseries-codexbar-bar");
            panel_display = new Gtk.Box (Gtk.Orientation.HORIZONTAL, 5);
            panel_display.append (panel_icon);
            panel_display.append (panel_label);
            panel_display.set_tooltip_text ("CodexBar · loading usage… · Middle-click to refresh");
            var refresh_gesture = new Gtk.GestureClick () { button = 2 };
            refresh_gesture.released.connect (() => refresh_usage ());
            panel_display.add_controller (refresh_gesture);
            this.visible = true;

            menu = new Gtk.Box (Gtk.Orientation.VERTICAL, 8) {
                margin_top = 8,
                margin_bottom = 6,
                margin_start = 8,
                margin_end = 8,
                width_request = 340
            };
            menu.add_css_class ("mseries-codexbar");
            install_style (menu.get_display ());

            // Header: name and freshness on the left, state chip and refresh on the right.
            var title_row = new Gtk.Box (Gtk.Orientation.HORIZONTAL, 8);
            var menu_icon = new Gtk.Image.from_icon_name ("mseries-codexbar-openai-symbolic") {
                pixel_size = 16
            };
            menu_icon.add_css_class ("symbolic");
            title_row.append (menu_icon);

            var title_stack = new Gtk.Box (Gtk.Orientation.VERTICAL, 1) { hexpand = true };
            var title = new Gtk.Label ("CodexBar") { xalign = 0 };
            title.add_css_class ("provider-title");
            title_stack.append (title);
            subtitle_label = new Gtk.Label ("Loading usage…") { xalign = 0, ellipsize = Pango.EllipsizeMode.END };
            subtitle_label.add_css_class ("dim-label");
            subtitle_label.add_css_class ("caption");
            title_stack.append (subtitle_label);
            title_row.append (title_stack);

            chip_label = new Gtk.Label ("") { valign = Gtk.Align.CENTER, visible = false };
            chip_label.add_css_class ("chip");
            title_row.append (chip_label);

            refresh_display = new Gtk.Stack ();
            refresh_display.add_named (new Gtk.Image.from_icon_name ("view-refresh-symbolic"), "idle");
            refresh_spinner = new Gtk.Spinner ();
            refresh_display.add_named (refresh_spinner, "busy");
            refresh_button = new Gtk.Button () {
                child = refresh_display,
                tooltip_text = "Refresh usage",
                valign = Gtk.Align.CENTER
            };
            refresh_button.add_css_class ("flat");
            refresh_button.update_property (Gtk.AccessibleProperty.LABEL, "Refresh usage", -1);
            refresh_button.clicked.connect (() => refresh_usage ());
            title_row.append (refresh_button);
            menu.append (title_row);

            // Three pages keep every section above the fold; Quota is the default.
            quota_box = new Gtk.Box (Gtk.Orientation.VERTICAL, 8);
            sessions_box = new Gtk.Box (Gtk.Orientation.VERTICAL, 8);
            spend_box = new Gtk.Box (Gtk.Orientation.VERTICAL, 8);
            pages = new Gtk.Stack () {
                hhomogeneous = true,
                vhomogeneous = false,
                transition_type = Gtk.StackTransitionType.CROSSFADE,
                transition_duration = 120
            };
            pages.add_titled (quota_box, "quota", "Quota");
            pages.add_titled (sessions_box, "sessions", "Sessions");
            pages.add_titled (spend_box, "spend", "Spend");
            var switcher = new Gtk.StackSwitcher () { stack = pages, halign = Gtk.Align.FILL };
            switcher.add_css_class ("mseries-switcher");
            menu.append (switcher);

            var scroll = new Gtk.ScrolledWindow () {
                child = pages,
                hscrollbar_policy = Gtk.PolicyType.NEVER,
                vscrollbar_policy = Gtk.PolicyType.AUTOMATIC,
                propagate_natural_height = true,
                min_content_height = 150,
                max_content_height = 340
            };
            menu.append (scroll);
            menu.append (new Gtk.Separator (Gtk.Orientation.HORIZONTAL));

            // An icon-only dock: one rounded bar, four evenly spaced actions, names in tooltips.
            var actions = new Gtk.Box (Gtk.Orientation.HORIZONTAL, 2) { homogeneous = true, halign = Gtk.Align.CENTER };
            actions.add_css_class ("mseries-dock");
            actions.append (make_dock_button ("Quick View", "window-new-symbolic", "--quick-view"));
            actions.append (make_dock_button ("Usage details", "view-list-symbolic", "--usage"));
            actions.append (make_dock_button ("Spending details", "accessories-calculator-symbolic", "--spending"));
            actions.append (make_dock_button ("Settings & sign in", "avatar-default-symbolic", "--settings"));
            menu.append (actions);

            show_state (quota_box, "content-loading-symbolic", "Loading usage…", "", false);
            show_state (sessions_box, "content-loading-symbolic", "Checking sessions…", "", false);
            show_state (spend_box, "content-loading-symbolic", "Loading spend…", "", false);

            // CodexBar owns provider authentication, polling and cached usage.
            // The indicator reads snapshots and requests refreshes through documented local IPC.
            try {
                Pid child_pid;
                Process.spawn_async (null, { executable, "--background" }, null,
                    SpawnFlags.SEARCH_PATH | SpawnFlags.STDOUT_TO_DEV_NULL | SpawnFlags.STDERR_TO_DEV_NULL,
                    null, out child_pid);
            } catch (Error e) {
                subtitle_label.set_text ("Could not start CodexBar: " + e.message);
            }

            Timeout.add_seconds (5, () => { read_snapshot.begin (); return Source.CONTINUE; });
        }

        private static void install_style (Gdk.Display display) {
            var style = new Gtk.CssProvider ();
            style.load_from_string (
                ".mseries-codexbar { font-size: 9pt; } " +
                ".mseries-codexbar .caption { font-size: 8pt; } " +
                ".mseries-codexbar .provider-title { font-weight: 700; font-size: 9.5pt; } " +
                ".mseries-codexbar .window-name { font-weight: 700; } " +
                ".mseries-codexbar .numeric { font-feature-settings: \"tnum\"; } " +
                ".mseries-codexbar .card { padding: 8px 10px; border-radius: 8px; background: alpha(currentColor, 0.06); } " +
                ".mseries-codexbar .chip { padding: 1px 8px; border-radius: 99px; font-size: 7.5pt; font-weight: 700; " +
                "  background: alpha(@warning_color, 0.22); color: @warning_color; } " +
                ".mseries-codexbar .chip.busy { background: alpha(currentColor, 0.1); color: inherit; } " +
                ".mseries-codexbar .plan { padding: 0 7px; border-radius: 99px; font-size: 7.5pt; background: alpha(currentColor, 0.1); } " +
                ".mseries-codexbar progressbar trough, .mseries-codexbar progressbar progress { min-height: 6px; border-radius: 3px; } " +
                ".mseries-codexbar progressbar.level-ok progress { background: @success_color; } " +
                ".mseries-codexbar progressbar.level-low progress { background: @warning_color; } " +
                ".mseries-codexbar progressbar.level-critical progress { background: @error_color; } " +
                ".mseries-codexbar .text-low { color: @warning_color; } " +
                ".mseries-codexbar .text-critical { color: @error_color; } " +
                ".mseries-codexbar .dot-ok { color: @success_color; } " +
                ".mseries-codexbar .dot-warn { color: @warning_color; } " +
                ".mseries-codexbar .dot-bad { color: @error_color; } " +
                ".mseries-codexbar .dot-off { opacity: 0.45; } " +
                ".mseries-codexbar .state-title { font-weight: 700; } " +
                ".mseries-codexbar button { padding: 3px 6px; } " +
                ".mseries-codexbar .mseries-dock { padding: 3px; border-radius: 12px; background: alpha(currentColor, 0.06); } " +
                ".mseries-codexbar .mseries-dock button { padding: 7px 18px; border-radius: 9px; min-height: 0; } " +
                ".mseries-codexbar .mseries-dock button:hover { background: alpha(currentColor, 0.1); } " +
                ".mseries-codexbar .account-row { margin-top: -2px; } " +
                ".mseries-codexbar .mseries-switcher button { padding: 2px 6px; } " +
                "label.mseries-codexbar-bar.level-low { color: @warning_color; } " +
                "label.mseries-codexbar-bar.level-critical { color: @error_color; } " +
                "label.mseries-codexbar-bar.stale { opacity: 0.55; }");
            Gtk.StyleContext.add_provider_for_display (display, style, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION);
        }

        private Gtk.Button make_dock_button (string label, string icon_name, string action) {
            var button = new Gtk.Button () {
                child = new Gtk.Image.from_icon_name (icon_name) { pixel_size = 18 },
                tooltip_text = label
            };
            button.add_css_class ("flat");
            button.update_property (Gtk.AccessibleProperty.LABEL, label, -1);
            button.clicked.connect (() => {
                popdown_from (button);
                run_action (action);
            });
            return button;
        }

        private static void popdown_from (Gtk.Widget widget) {
            var popover = widget.get_ancestor (typeof (Gtk.Popover)) as Gtk.Popover;
            if (popover != null) {
                popover.popdown ();
            }
        }

        private void set_refreshing (bool busy) {
            refresh_display.set_visible_child_name (busy ? "busy" : "idle");
            refresh_spinner.set_spinning (busy);
            refresh_button.set_sensitive (!busy);
        }

        private void refresh_usage () {
            if (snapshot_busy || !run_action ("--refresh")) {
                return;
            }
            refresh_policy.requested (GLib.get_monotonic_time ());
            subtitle_label.set_text ("Refreshing…");
            set_refreshing (true);
            if (refresh_poll_source != 0) {
                Source.remove (refresh_poll_source);
            }
            refresh_poll_count = 0;
            refresh_poll_source = Timeout.add_seconds (2, () => {
                read_snapshot.begin ();
                refresh_poll_count++;
                if ((!snapshot_busy && refresh_poll_count >= 3) || refresh_poll_count >= 30) {
                    refresh_poll_source = 0;
                    set_refreshing (false);
                    return Source.REMOVE;
                }
                return Source.CONTINUE;
            });
        }

        private bool run_action (string action) {
            try {
                Pid child_pid;
                Process.spawn_async (null, { executable, action }, null,
                    SpawnFlags.SEARCH_PATH | SpawnFlags.STDOUT_TO_DEV_NULL | SpawnFlags.STDERR_TO_DEV_NULL,
                    null, out child_pid);
                return true;
            } catch (Error e) {
                subtitle_label.set_text ("Could not open CodexBar: " + e.message);
                return false;
            }
        }

        private static void clear (Gtk.Box box) {
            while (box.get_first_child () != null) {
                box.remove (box.get_first_child ());
            }
        }

        // ---- Reading data -------------------------------------------------------------

        private async void read_snapshot (bool refresh_if_old = false) {
            refresh_after_snapshot = refresh_after_snapshot || refresh_if_old;
            if (request_in_flight) {
                return;
            }
            request_in_flight = true;

            try {
                var process = new GLib.Subprocess (SubprocessFlags.STDOUT_PIPE | SubprocessFlags.STDERR_PIPE,
                    executable, "--snapshot");
                string stdout_text;
                string stderr_text;
                yield process.communicate_utf8_async (null, null, out stdout_text, out stderr_text);
                if (!process.get_successful () || stdout_text.strip ().length == 0) {
                    show_unavailable ("dialog-warning-symbolic", "CodexBar isn't running", "Start CodexBar and sign in to see your quota.");
                    ensure_sessions (60);
                    return;
                }

                var parser = new Json.Parser ();
                parser.load_from_data (stdout_text, -1);
                var root = parser.get_root ();
                if (root == null || root.get_node_type () != Json.NodeType.OBJECT) {
                    show_unavailable ("dialog-warning-symbolic", "Unsupported CodexBar data", "CodexBar returned a snapshot this panel can't read. Update the panel after a CodexBar upgrade.");
                    ensure_sessions (60);
                    return;
                }
                var snapshot = root.get_object ();
                update_snapshot (snapshot);
                ensure_sessions (60);
                if (refresh_after_snapshot && should_refresh_on_open (snapshot)) {
                    refresh_usage ();
                }
            } catch (Error e) {
                show_unavailable ("dialog-warning-symbolic", "Couldn't read usage", e.message);
                ensure_sessions (60);
            } finally {
                request_in_flight = false;
                refresh_after_snapshot = false;
            }
        }

        private bool should_refresh_on_open (Json.Object snapshot) {
            int64 oldest_update_unix = 0;
            var entries = snapshot.get_array_member ("entries");
            if (entries != null) {
                for (uint i = 0; i < entries.get_length (); i++) {
                    var entry = entries.get_object_element (i);
                    var updated = entry.get_string_member ("updatedAt") ?? "";
                    var timestamp = new DateTime.from_iso8601 (updated, null);
                    if (timestamp == null) {
                        oldest_update_unix = 0;
                        break;
                    }
                    if (oldest_update_unix == 0 || timestamp.to_unix () < oldest_update_unix) {
                        oldest_update_unix = timestamp.to_unix ();
                    }
                }
            }
            return refresh_policy.should_refresh_on_open (snapshot.get_boolean_member ("busy"),
                oldest_update_unix, new DateTime.now_utc ().to_unix (), GLib.get_monotonic_time ());
        }

        private void ensure_sessions (int max_age_seconds) {
            if (sessions_fetched_us == 0 ||
                GLib.get_monotonic_time () - sessions_fetched_us > max_age_seconds * GLib.TimeSpan.SECOND) {
                refresh_sessions.begin ();
            }
            if (claude_fetched_us == 0 ||
                GLib.get_monotonic_time () - claude_fetched_us > 120 * GLib.TimeSpan.SECOND) {
                refresh_claude.begin ();
            }
            if (codex_accounts_fetched_us == 0 ||
                GLib.get_monotonic_time () - codex_accounts_fetched_us > 300 * GLib.TimeSpan.SECOND) {
                refresh_codex_accounts.begin ();
            }
            if (opencode_local_fetched_us == 0 ||
                GLib.get_monotonic_time () - opencode_local_fetched_us > max_age_seconds * GLib.TimeSpan.SECOND) {
                refresh_opencode_local.begin ();
            }
        }

        private static string helper_path (string name) {
            return GLib.Path.build_filename (Environment.get_home_dir (), ".local", "lib", "codexbar-cli", name);
        }

        // Upstream's Codex account switching is macOS-only; our helper keeps one saved sign-in per account.
        private async void refresh_codex_accounts () {
            if (codex_accounts_in_flight) {
                return;
            }
            codex_accounts_in_flight = true;
            var before = codex_accounts_digest (codex_accounts);
            try {
                var process = new GLib.Subprocess (SubprocessFlags.STDOUT_PIPE | SubprocessFlags.STDERR_PIPE,
                    "python3", helper_path ("codexbar-accounts.py"), "usage");
                string stdout_text;
                string stderr_text;
                yield process.communicate_utf8_async (null, null, out stdout_text, out stderr_text);
                Json.Array? parsed = null;
                if (process.get_successful () && stdout_text.strip ().length > 0) {
                    var parser = new Json.Parser ();
                    parser.load_from_data (stdout_text, -1);
                    var root = parser.get_root ();
                    if (root != null && root.get_node_type () == Json.NodeType.OBJECT) {
                        var list = root.get_object ().get_array_member ("accounts");
                        parsed = list != null ? list.ref () : null;
                    }
                }
                codex_accounts = parsed;
            } catch (Error e) {
                codex_accounts = null;
            } finally {
                codex_accounts_in_flight = false;
                codex_accounts_fetched_us = GLib.get_monotonic_time ();
            }
            if (codex_accounts_digest (codex_accounts) != before) {
                last_digest = "";
                read_snapshot.begin ();
            }
        }

        // Claude accounts come from claude-swap (cswap), the same tool upstream CodexBar drives on macOS.
        private async void refresh_claude () {
            if (claude_in_flight) {
                return;
            }
            claude_in_flight = true;
            var before = local_digest (claude_data);
            try {
                var process = new GLib.Subprocess (SubprocessFlags.STDOUT_PIPE | SubprocessFlags.STDERR_PIPE,
                    "python3", helper_path ("codexbar-claude.py"), "list");
                string stdout_text;
                string stderr_text;
                yield process.communicate_utf8_async (null, null, out stdout_text, out stderr_text);
                Json.Object? parsed = null;
                if (process.get_successful () && stdout_text.strip ().length > 0) {
                    var parser = new Json.Parser ();
                    parser.load_from_data (stdout_text, -1);
                    var root = parser.get_root ();
                    if (root != null && root.get_node_type () == Json.NodeType.OBJECT
                        && root.get_object ().get_boolean_member_with_default ("available", false)) {
                        parsed = root.get_object ().ref ();
                    }
                }
                claude_data = parsed;
            } catch (Error e) {
                claude_data = null;
            } finally {
                claude_in_flight = false;
                claude_fetched_us = GLib.get_monotonic_time ();
            }
            if (local_digest (claude_data) != before) {
                last_digest = "";
                read_snapshot.begin ();
            }
        }

        private void run_claude_helper (string[] arguments) {
            try {
                string[] command = { "python3", helper_path ("codexbar-claude.py") };
                foreach (var argument in arguments) {
                    command += argument;
                }
                var process = new GLib.Subprocess.newv (command, SubprocessFlags.STDOUT_SILENCE | SubprocessFlags.STDERR_SILENCE);
                process.wait_async.begin (null, () => {
                    claude_fetched_us = 0;
                    last_digest = "";
                    refresh_claude.begin ();
                    read_snapshot.begin ();
                });
            } catch (Error e) {
                subtitle_label.set_text ("Could not switch Claude account: " + e.message);
            }
        }

        private void add_claude_account () {
            // Sign in to Claude Code first; this saves whichever login is active into claude-swap.
            try {
                new GLib.Subprocess (SubprocessFlags.NONE, "xdg-terminal-exec", "sh", "-c",
                    "cswap add; printf '\\nPress Enter to close. '; read -r _");
            } catch (Error e) {
                subtitle_label.set_text ("Could not open a terminal: " + e.message);
            }
            claude_fetched_us = 0;
        }

        private Gtk.Widget build_claude_card (int64 now_unix) {
            var card = new Gtk.Box (Gtk.Orientation.VERTICAL, 6);
            card.add_css_class ("card");
            var head = new Gtk.Box (Gtk.Orientation.HORIZONTAL, 6);
            var dot = new Gtk.Label ("●");
            dot.add_css_class ("dot-off");
            head.append (dot);
            var title = new Gtk.Label ("Claude") { xalign = 0, hexpand = true };
            title.add_css_class ("provider-title");
            head.append (title);
            card.append (head);

            var email = claude_data.get_string_member_with_default ("activeEmail", "");
            var accounts = claude_data.get_array_member ("accounts");
            var row = new Gtk.Box (Gtk.Orientation.HORIZONTAL, 5);
            row.add_css_class ("account-row");
            var icon = new Gtk.Image.from_icon_name ("avatar-default-symbolic") { pixel_size = 12 };
            icon.add_css_class ("dim-label");
            row.append (icon);
            var who = new Gtk.Label (email.length > 0 ? email : "Account not detected") {
                xalign = 0, hexpand = true, ellipsize = Pango.EllipsizeMode.MIDDLE
            };
            who.add_css_class ("caption");
            who.add_css_class ("dim-label");
            row.append (who);
            card.append (row);

            var shown_quota = false;
            if (accounts != null) {
                for (uint i = 0; i < accounts.get_length (); i++) {
                    var account = accounts.get_object_element (i);
                    var windows = account.get_array_member ("windows");
                    if (account.get_boolean_member_with_default ("active", false) && windows != null) {
                        dot.remove_css_class ("dot-off");
                        dot.add_css_class ("dot-ok");
                        for (uint w = 0; w < windows.get_length (); w++) {
                            card.append (build_window ("Claude", windows.get_object_element (w), false, now_unix));
                            shown_quota = true;
                        }
                    }
                }
            }
            if (!shown_quota) {
                card.append (subtle_label (accounts != null && accounts.get_length () > 0
                    ? "Quota isn't available for this account yet."
                    : "Add this login to see quota and switch between Claude accounts."));
            }

            var others = false;
            if (accounts != null) {
                for (uint i = 0; i < accounts.get_length (); i++) {
                    var account = accounts.get_object_element (i);
                    if (account.get_boolean_member_with_default ("active", false)) {
                        continue;
                    }
                    if (!others) {
                        card.append (subtle_label ("Other accounts"));
                        others = true;
                    }
                    var number = account.get_int_member_with_default ("number", 0).to_string ();
                    var name = account.get_string_member_with_default ("email", "");
                    var line = new Gtk.Box (Gtk.Orientation.HORIZONTAL, 8);
                    var text = new Gtk.Box (Gtk.Orientation.VERTICAL, 0) { hexpand = true };
                    text.append (new Gtk.Label (name) { xalign = 0, ellipsize = Pango.EllipsizeMode.END });
                    var windows = account.get_array_member ("windows");
                    var detail = "usage unavailable";
                    if (windows != null && windows.get_length () > 0) {
                        var last = windows.get_object_element (windows.get_length () - 1);
                        detail = "%s %.0f%% left".printf (last.get_string_member_with_default ("label", "Quota"),
                            last.get_double_member_with_default ("remaining", 0));
                    }
                    text.append (subtle_label (detail));
                    line.append (text);
                    var switch_button = new Gtk.Button.with_label ("Switch") { valign = Gtk.Align.CENTER };
                    switch_button.set_tooltip_text ("Make %s the active Claude account".printf (name));
                    switch_button.clicked.connect (() => {
                        popdown_from (switch_button);
                        run_claude_helper ({ "switch", number });
                    });
                    line.append (switch_button);
                    card.append (line);
                }
            }
            var add = new Gtk.Button.with_label ("Add account…") { halign = Gtk.Align.START };
            add.set_tooltip_text ("Sign in to Claude Code, then save that login with claude-swap");
            add.clicked.connect (() => {
                popdown_from (add);
                add_claude_account ();
            });
            card.append (add);
            return card;
        }

        private static string codex_accounts_digest (Json.Array? accounts) {
            if (accounts == null) {
                return "";
            }
            var generator = new Json.Generator ();
            var node = new Json.Node (Json.NodeType.ARRAY);
            node.set_array (accounts);
            generator.root = node;
            return generator.to_data (null);
        }

        private void run_accounts_helper (string[] arguments) {
            try {
                string[] command = { "python3", helper_path ("codexbar-accounts.py") };
                foreach (var argument in arguments) {
                    command += argument;
                }
                var process = new GLib.Subprocess.newv (command, SubprocessFlags.STDOUT_SILENCE | SubprocessFlags.STDERR_SILENCE);
                process.wait_async.begin (null, () => {
                    // The active account changed: re-read quota and the account list from scratch.
                    codex_accounts_fetched_us = 0;
                    last_digest = "";
                    run_action ("--refresh");
                    refresh_codex_accounts.begin ();
                    read_snapshot.begin ();
                });
            } catch (Error e) {
                subtitle_label.set_text ("Could not switch account: " + e.message);
            }
        }

        private void add_codex_account () {
            // Remember the signed-in account first, then let `codex login` sign in the next one.
            try {
                var save = new GLib.Subprocess (SubprocessFlags.STDOUT_SILENCE | SubprocessFlags.STDERR_SILENCE,
                    "python3", helper_path ("codexbar-accounts.py"), "save");
                save.wait_async.begin (null, () => {
                    try {
                        new GLib.Subprocess (SubprocessFlags.NONE, "xdg-terminal-exec", "codex", "login");
                    } catch (Error e) {
                        subtitle_label.set_text ("Could not open a terminal: " + e.message);
                    }
                    codex_accounts_fetched_us = 0;
                });
            } catch (Error e) {
                subtitle_label.set_text ("Could not save the current account: " + e.message);
            }
        }

        private Gtk.Widget? build_codex_accounts (Gtk.Widget parent_for_popdown) {
            if (codex_accounts == null || codex_accounts.get_length () < 2) {
                return null;
            }
            var box = new Gtk.Box (Gtk.Orientation.VERTICAL, 4);
            box.append (subtle_label ("Other accounts"));
            for (uint i = 0; i < codex_accounts.get_length (); i++) {
                var account = codex_accounts.get_object_element (i);
                if (account.get_boolean_member_with_default ("active", false)) {
                    continue;
                }
                var email = account.get_string_member_with_default ("email", "");
                var account_id = account.get_string_member_with_default ("id", email);
                var row = new Gtk.Box (Gtk.Orientation.HORIZONTAL, 8);
                var text = new Gtk.Box (Gtk.Orientation.VERTICAL, 0) { hexpand = true };
                var name = new Gtk.Label (email) { xalign = 0, ellipsize = Pango.EllipsizeMode.END };
                text.append (name);
                var detail = Presentation.plan_label (account.get_string_member_with_default ("plan", ""));
                var windows = account.get_array_member ("windows");
                if (windows != null && windows.get_length () > 0) {
                    var window = windows.get_object_element (windows.get_length () - 1);
                    detail = (detail.length > 0 ? detail + " · " : "") + "%s %.0f%% left".printf (
                        window.get_string_member_with_default ("label", "Quota"),
                        window.get_double_member_with_default ("remaining", 0));
                } else if (account.has_member ("error")) {
                    detail = (detail.length > 0 ? detail + " · " : "") + "usage unavailable";
                }
                text.append (subtle_label (detail));
                row.append (text);
                var switch_button = new Gtk.Button.with_label ("Switch") { valign = Gtk.Align.CENTER };
                switch_button.set_tooltip_text ("Make %s the active Codex account. Restart running Codex sessions to use it.".printf (email));
                switch_button.clicked.connect (() => {
                    popdown_from (parent_for_popdown);
                    run_accounts_helper ({ "switch", account_id });
                });
                row.append (switch_button);
                box.append (row);
            }
            return box;
        }

        private static string local_digest (Json.Object? usage) {
            if (usage == null) {
                return "";
            }
            var generator = new Json.Generator ();
            var node = new Json.Node (Json.NodeType.OBJECT);
            node.set_object (usage);
            generator.root = node;
            return generator.to_data (null);
        }

        // OpenCode Go's account quota needs a web sign-in, so show what this machine's own history says.
        private async void refresh_opencode_local () {
            if (opencode_local_in_flight) {
                return;
            }
            opencode_local_in_flight = true;
            var helper = GLib.Path.build_filename (Environment.get_home_dir (), ".local", "lib",
                "codexbar-cli", "codexbar-opencode-local.py");
            var changed = false;
            try {
                var process = new GLib.Subprocess (SubprocessFlags.STDOUT_PIPE | SubprocessFlags.STDERR_PIPE,
                    "python3", helper);
                string stdout_text;
                string stderr_text;
                yield process.communicate_utf8_async (null, null, out stdout_text, out stderr_text);
                Json.Object? parsed = null;
                if (process.get_successful () && stdout_text.strip ().length > 0) {
                    var parser = new Json.Parser ();
                    parser.load_from_data (stdout_text, -1);
                    var root = parser.get_root ();
                    if (root != null && root.get_node_type () == Json.NodeType.OBJECT
                        && (root.get_object ().get_string_member_with_default ("status", "") == "available"
                            || root.get_object ().get_string_member_with_default ("accountEmail", "").length > 0)) {
                        parsed = root.get_object ().ref ();
                    }
                }
                changed = local_digest (parsed) != local_digest (opencode_local);
                opencode_local = parsed;
            } catch (Error e) {
                changed = opencode_local != null;
                opencode_local = null;
            } finally {
                opencode_local_in_flight = false;
                opencode_local_fetched_us = GLib.get_monotonic_time ();
            }
            if (changed) {
                last_digest = "";
                read_snapshot.begin ();
            }
        }

        private async void refresh_sessions () {
            if (sessions_in_flight) {
                return;
            }
            sessions_in_flight = true;
            var helper = GLib.Path.build_filename (Environment.get_home_dir (), ".local", "lib",
                "codexbar-cli", "codexbar-sessions.py");
            try {
                var process = new GLib.Subprocess (SubprocessFlags.STDOUT_PIPE | SubprocessFlags.STDERR_PIPE,
                    "python3", helper);
                string stdout_text;
                string stderr_text;
                yield process.communicate_utf8_async (null, null, out stdout_text, out stderr_text);
                if (!process.get_successful () || stdout_text.strip ().length == 0) {
                    sessions_error = "The session check couldn't run. Reinstall the CodexBar panel.";
                } else {
                    sessions_text = stdout_text;
                    sessions_error = "";
                }
            } catch (Error e) {
                sessions_error = "The session check is unavailable: " + e.message;
            } finally {
                sessions_in_flight = false;
                sessions_fetched_us = GLib.get_monotonic_time ();
                render_sessions ();
            }
        }

        // ---- Snapshot to UI -----------------------------------------------------------

        private string snapshot_digest (Json.Object snapshot, int64 now_unix) {
            var text = new StringBuilder ();
            foreach (var name in new string[] { "entries", "spending" }) {
                var node = snapshot.get_member (name);
                if (node != null) {
                    var generator = new Json.Generator ();
                    generator.root = node;
                    text.append (generator.to_data (null));
                }
            }
            text.append ("|%s|%s".printf (snapshot_stale.to_string (), snapshot.get_boolean_member ("busy").to_string ()));
            var entries = snapshot.get_array_member ("entries");
            if (entries != null) {
                for (uint i = 0; i < entries.get_length (); i++) {
                    text.append (QuotaEta.entry_stale (entries.get_object_element (i), snapshot_stale, now_unix) ? "S" : "F");
                }
            }
            return GLib.Checksum.compute_for_string (GLib.ChecksumType.MD5, text.str);
        }

        private void update_snapshot (Json.Object snapshot) {
            var now_unix = new DateTime.now_utc ().to_unix ();
            snapshot_stale = snapshot.get_boolean_member ("stale");
            snapshot_busy = snapshot.get_boolean_member ("busy");
            var entries = snapshot.get_array_member ("entries");
            if (entries == null || entries.get_length () == 0) {
                last_digest = "";
                newest_update_unix = 0;
                set_refreshing (snapshot_busy);
                if (snapshot_busy) {
                    show_state (quota_box, "content-loading-symbolic", "Fetching usage…",
                        "Your limits will appear when the update completes.", false);
                    subtitle_label.set_text ("Refreshing…");
                } else {
                    show_unavailable ("dialog-information-symbolic", "No quota data yet", "Open Settings to sign in to a provider.");
                }
                return;
            }

            newest_update_unix = 0;
            for (uint i = 0; i < entries.get_length (); i++) {
                var timestamp = new DateTime.from_iso8601 (entries.get_object_element (i).get_string_member ("updatedAt") ?? "", null);
                if (timestamp != null && timestamp.to_unix () > newest_update_unix) {
                    newest_update_unix = timestamp.to_unix ();
                }
            }
            refresh_header (now_unix);

            var digest = snapshot_digest (snapshot, now_unix);
            if (digest == last_digest) {
                return;
            }
            last_digest = digest;
            render_quota (entries, now_unix);
            render_spend (snapshot);
            update_panel (entries, now_unix);
        }

        private void refresh_header (int64 now_unix) {
            set_refreshing (snapshot_busy);
            if (snapshot_busy) {
                subtitle_label.set_text ("Refreshing…");
            } else if (newest_update_unix > 0) {
                subtitle_label.set_text ("Updated " + Presentation.age_text (now_unix - newest_update_unix));
            } else {
                subtitle_label.set_text ("Waiting for data");
            }
            chip_label.remove_css_class ("busy");
            if (snapshot_busy) {
                chip_label.set_text ("Refreshing");
                chip_label.add_css_class ("busy");
                chip_label.set_visible (true);
            } else if (snapshot_stale) {
                chip_label.set_text ("Cached");
                chip_label.set_tooltip_text ("CodexBar couldn't reach a provider; showing the last good data.");
                chip_label.set_visible (true);
            } else {
                chip_label.set_visible (false);
            }
        }

        private void update_panel (Json.Array entries, int64 now_unix) {
            var parts = new string[0];
            var tags = new string[0];
            var tooltip = new StringBuilder ();
            var level = QuotaLevel.UNKNOWN;
            for (uint i = 0; i < entries.get_length (); i++) {
                var entry = entries.get_object_element (i);
                var provider = (entry.get_string_member ("provider") ?? "").down ();
                var windows = entry.get_array_member ("windows");
                if (windows == null || windows.get_length () == 0) {
                    continue;
                }
                var stale = QuotaEta.entry_stale (entry, snapshot_stale, now_unix);
                var eta = QuotaEta.for_entry (entry, stale, now_unix);
                tooltip.append ("%s%s\n".printf (tooltip.len > 0 ? "\n" : "", provider_title (provider)));
                string remaining_text = "—";
                string lead_window = "";
                bool first_measured = true;
                for (uint w = 0; w < windows.get_length (); w++) {
                    var window = windows.get_object_element (w);
                    var node = window.get_member ("remaining");
                    var short_label = Presentation.short_window_label (window.get_string_member ("label") ?? "Quota",
                        (int) window.get_int_member ("minutes"));
                    if (node == null || node.get_node_type () == Json.NodeType.NULL) {
                        tooltip.append ("  %s  not reported yet\n".printf (short_label));
                        continue;
                    }
                    var remaining = node.get_double ();
                    level = Presentation.worse (level, Presentation.level_for (remaining));
                    if (first_measured) {
                        // The first measured window is the provider's session/general quota.
                        var minutes = (int) window.get_int_member ("minutes");
                        remaining_text = Presentation.quota_lead (short_label, minutes, "%0.0f%%".printf (remaining));
                        lead_window = minutes > 360 ? short_label : "";
                        first_measured = false;
                    }
                    tooltip.append ("  %s  %0.0f%% left · %s\n".printf (short_label, remaining,
                        (window.get_string_member ("resetText") ?? "").length > 0
                            ? window.get_string_member ("resetText").down () : "reset unknown"));
                }
                if (provider.contains ("codex") || provider.contains ("claude")) {
                    tags += provider.contains ("codex") ? "CX" : "CL";
                    parts += Presentation.bar_segment (remaining_text, eta.state, eta.compact,
                        Presentation.limiting_window (
                            Presentation.short_window_label (eta.window_label, eta.window_minutes), lead_window));
                }
            }

            var shown = new string[0];
            for (int i = 0; i < parts.length; i++) {
                shown += (parts.length > 1 ? tags[i] + " " : "") + parts[i];
            }
            panel_label.set_text (shown.length > 0 ? string.joinv ("   ", shown) : "—");
            panel_label.remove_css_class ("level-low");
            panel_label.remove_css_class ("level-critical");
            panel_label.remove_css_class ("stale");
            if (snapshot_stale) panel_label.add_css_class ("stale");
            if (level == QuotaLevel.LOW) panel_label.add_css_class ("level-low");
            if (level == QuotaLevel.CRITICAL) panel_label.add_css_class ("level-critical");
            panel_display.set_tooltip_text (tooltip.len > 0
                ? tooltip.str.strip () + (snapshot_stale ? "\n\nCached: CodexBar couldn't reach a provider." : "")
                    + "\n\nMiddle-click to refresh"
                : "Usage unavailable");
        }

        // ---- Pages --------------------------------------------------------------------

        private static string provider_title (string provider) {
            return provider == "codex" ? "OpenAI Codex" :
                provider == "claude" ? "Claude" :
                provider == "opencodego" ? "OpenCode Go" : provider;
        }

        private void render_quota (Json.Array entries, int64 now_unix) {
            clear (quota_box);
            for (uint i = 0; i < entries.get_length (); i++) {
                quota_box.append (build_provider_card (entries.get_object_element (i), now_unix));
            }
            var has_claude = false;
            for (uint i = 0; i < entries.get_length (); i++) {
                has_claude = has_claude || entries.get_object_element (i).get_string_member_with_default ("provider", "") == "claude";
            }
            if (!has_claude && claude_data != null) {
                quota_box.append (build_claude_card (now_unix));
            }
        }

        private Gtk.Widget build_provider_card (Json.Object entry, int64 now_unix) {
            var provider = (entry.get_string_member ("provider") ?? "Provider").down ();
            var title_text = provider_title (provider);
            var error = entry.get_string_member ("error") ?? "";
            var status = entry.get_string_member ("status") ?? "";
            var status_level = entry.get_string_member ("statusLevel") ?? "";
            var stale = QuotaEta.entry_stale (entry, snapshot_stale, now_unix);

            var card = new Gtk.Box (Gtk.Orientation.VERTICAL, 6);
            card.add_css_class ("card");

            var head = new Gtk.Box (Gtk.Orientation.HORIZONTAL, 6);
            var dot = new Gtk.Label ("●");
            string dot_class = error.length > 0 ? "dot-bad" :
                status_level == "none" ? "dot-ok" :
                status_level == "minor" ? "dot-warn" :
                status_level == "unknown" || status_level.length == 0 ? "dot-off" : "dot-bad";
            dot.add_css_class (dot_class);
            dot.set_tooltip_text (error.length > 0 ? "Problem fetching this provider" :
                status.length > 0 ? status : "Provider status unknown");
            head.append (dot);
            var title = new Gtk.Label (title_text) { xalign = 0, hexpand = true };
            title.add_css_class ("provider-title");
            head.append (title);
            var plan = Presentation.plan_label (entry.get_string_member ("plan") ?? "");
            if (plan.length > 0) {
                var plan_label = new Gtk.Label (plan) { valign = Gtk.Align.CENTER };
                plan_label.add_css_class ("plan");
                head.append (plan_label);
            }
            card.append (head);
            card.append (build_account_row (provider, entry));

            var windows = entry.get_array_member ("windows");
            if (windows != null && windows.get_length () > 0) {
                for (uint i = 0; i < windows.get_length (); i++) {
                    card.append (build_window (title_text, windows.get_object_element (i), stale, now_unix));
                }
            }

            // Say so only when something is wrong; "All Systems Operational" is noise.
            if (error.length == 0 && status.length > 0 && status_level != "none" && status_level != "unknown") {
                card.append (subtle_label ("Provider status · " + status));
            }
            if (provider == "codex") {
                var others = build_codex_accounts (card);
                if (others != null) {
                    card.append (others);
                }
                var add = new Gtk.Button.with_label ("Add account…") { halign = Gtk.Align.START };
                add.set_tooltip_text ("Sign in to another ChatGPT account with codex login");
                add.clicked.connect (() => {
                    popdown_from (add);
                    add_codex_account ();
                });
                card.append (add);
            }
            if (error.length > 0 || windows == null || windows.get_length () == 0) {
                var estimate = provider == "opencodego" ? opencode_local : null;
                var periods = estimate != null ? estimate.get_array_member ("periods") : null;
                if (periods != null && periods.get_length () > 0) {
                    card.append (subtle_label (estimate.get_string_member_with_default ("message", "Local usage estimate · not account quota")));
                    for (uint i = 0; i < periods.get_length (); i++) {
                        var period = periods.get_object_element (i);
                        card.append (subtle_label (Presentation.local_usage_line (
                            period.get_string_member_with_default ("label", ""),
                            period.get_double_member_with_default ("costUSD", 0),
                            period.get_int_member_with_default ("requests", 0),
                            period.get_int_member_with_default ("tokens", 0))));
                    }
                    card.append (subtle_label ("Account quota needs a web sign-in at opencode.ai."));
                } else {
                    card.append (subtle_label (provider == "opencodego"
                        ? "Quota needs a web sign-in at opencode.ai. Local activity is under Sessions."
                        : error.length > 0 ? error : "No usage reported yet."));
                }
                var settings = new Gtk.Button.with_label (provider == "opencodego" ? "Sign in…" : "Open Settings…") {
                    halign = Gtk.Align.START
                };
                settings.clicked.connect (() => {
                    popdown_from (settings);
                    run_action ("--settings");
                });
                card.append (settings);
            }
            return card;
        }

        /* Which login a provider is tied to: quiet, under the title, never the focus of the card. */
        private string account_email_for (string provider, Json.Object entry) {
            var email = entry.get_string_member_with_default ("accountEmail", "");
            if (email.length == 0 && provider == "codex" && codex_accounts != null) {
                for (uint i = 0; i < codex_accounts.get_length (); i++) {
                    var account = codex_accounts.get_object_element (i);
                    if (account.get_boolean_member_with_default ("active", false)) {
                        email = account.get_string_member_with_default ("email", "");
                    }
                }
            }
            if (email.length == 0 && provider == "opencodego" && opencode_local != null) {
                email = opencode_local.get_string_member_with_default ("accountEmail", "");
            }
            return email;
        }

        private Gtk.Widget build_account_row (string provider, Json.Object entry) {
            var email = account_email_for (provider, entry);
            var row = new Gtk.Box (Gtk.Orientation.HORIZONTAL, 5);
            row.add_css_class ("account-row");
            var icon = new Gtk.Image.from_icon_name ("avatar-default-symbolic") { pixel_size = 12 };
            icon.add_css_class ("dim-label");
            row.append (icon);
            var label = new Gtk.Label (email.length > 0 ? email : "Account not detected") {
                xalign = 0, hexpand = true, ellipsize = Pango.EllipsizeMode.MIDDLE, selectable = false
            };
            label.add_css_class ("caption");
            label.add_css_class ("dim-label");
            label.set_tooltip_text (email.length > 0 ? "Signed in as " + email : "CodexBar can't tell which account this is signed in with");
            row.append (label);
            return row;
        }

        private Gtk.Widget build_window (string provider_title_text, Json.Object window, bool stale, int64 now_unix) {
            var label = window.get_string_member ("label") ?? "Quota";
            var reset = window.get_string_member ("resetText") ?? "";
            var pace = window.get_string_member ("pace") ?? "";
            var remaining_node = window.get_member ("remaining");
            var known = remaining_node != null && remaining_node.get_node_type () != Json.NodeType.NULL;
            var remaining = known
                ? GLib.Math.fmin (100.0, GLib.Math.fmax (0.0, remaining_node.get_double ())) : -1.0;
            var level = Presentation.level_for (remaining);
            var eta = QuotaEta.from_window (window, stale, now_unix);

            var group = new Gtk.Box (Gtk.Orientation.VERTICAL, 2);
            var row = new Gtk.Box (Gtk.Orientation.HORIZONTAL, 8);
            var name = new Gtk.Label (Presentation.short_window_label (label, (int) window.get_int_member ("minutes"))) {
                xalign = 0, width_request = 34
            };
            name.add_css_class ("window-name");
            row.append (name);
            var progress = new Gtk.ProgressBar () {
                show_text = false, hexpand = true, valign = Gtk.Align.CENTER, sensitive = known
            };
            progress.set_fraction (known ? remaining / 100.0 : 0);
            if (level == QuotaLevel.OK) progress.add_css_class ("level-ok");
            if (level == QuotaLevel.LOW) progress.add_css_class ("level-low");
            if (level == QuotaLevel.CRITICAL) progress.add_css_class ("level-critical");
            var spoken = known ? "%0.0f percent remaining".printf (remaining) : "usage not reported yet";
            progress.update_property (Gtk.AccessibleProperty.LABEL, "%s %s limit, %s".printf (provider_title_text, label, spoken), -1);
            row.append (progress);
            var percent = new Gtk.Label (known ? "%0.0f%% left".printf (remaining) : "—") {
                xalign = 1, width_request = 62
            };
            percent.add_css_class ("numeric");
            if (level == QuotaLevel.LOW) percent.add_css_class ("text-low");
            if (level == QuotaLevel.CRITICAL) percent.add_css_class ("text-critical");
            row.append (percent);
            group.append (row);

            var caption_text = known ? Presentation.window_caption (reset, eta.state, eta.detail)
                : "Usage not reported yet";
            var caption = new Gtk.Label (caption_text) { xalign = 0, wrap = true, margin_start = 42 };
            caption.add_css_class ("caption");
            caption.add_css_class (eta.state == EtaState.EXHAUSTED ? "text-critical" :
                eta.state == EtaState.DEPLETING ? "text-low" : "dim-label");
            group.append (caption);

            var detail = known ? "%0.0f%% remaining".printf (remaining) : "Usage not reported yet";
            if (reset.length > 0) detail += " · " + reset;
            if (pace.length > 0) detail += " · " + pace;
            group.set_tooltip_text (label + " · " + detail);
            return group;
        }

        private void render_spend (Json.Object snapshot) {
            clear (spend_box);
            var spending = snapshot.has_member ("spending") ? snapshot.get_array_member ("spending") : null;
            if (spending == null || spending.get_length () == 0) {
                show_state (spend_box, "emblem-documents-symbolic", "No spend data yet",
                    "CodexBar estimates spend from local token use once it has seen some.", false);
                return;
            }
            for (uint i = 0; i < spending.get_length (); i++) {
                var item = spending.get_object_element (i);
                var provider = (item.get_string_member ("provider") ?? "").down ();
                var card = new Gtk.Box (Gtk.Orientation.VERTICAL, 4);
                card.add_css_class ("card");
                var title = new Gtk.Label (provider_title (provider)) { xalign = 0 };
                title.add_css_class ("provider-title");
                card.append (title);
                var error = item.get_string_member ("error") ?? "";
                if (error.length > 0) {
                    card.append (subtle_label (error));
                } else {
                    append_metric (card, "Today", "$%0.2f".printf (item.get_double_member ("today")));
                    append_metric (card, "This month", "$%0.2f".printf (item.get_double_member ("month")));
                    append_metric (card, "Tokens this month", Presentation.count_text (item.get_int_member ("tokens")));
                }
                spend_box.append (card);
            }
            spend_box.append (subtle_label ("List-price estimate of your local token use. It is not what you were billed."));
        }

        private void render_sessions () {
            clear (sessions_box);
            if (sessions_error.length > 0) {
                show_state (sessions_box, "dialog-warning-symbolic", "Sessions unavailable", sessions_error, false);
                return;
            }
            var parser = new Json.Parser ();
            Json.Array? sessions = null;
            try {
                parser.load_from_data (sessions_text, -1);
                var root = parser.get_root ();
                if (root != null && root.get_node_type () == Json.NodeType.OBJECT) {
                    sessions = root.get_object ().get_array_member ("sessions");
                }
            } catch (Error e) {
                sessions = null;
            }
            if (sessions == null || sessions.get_length () == 0) {
                show_state (sessions_box, "dialog-warning-symbolic", "No sessions found",
                    "The session check returned nothing to show.", false);
                return;
            }
            for (uint i = 0; i < sessions.get_length (); i++) {
                sessions_box.append (build_session (sessions.get_object_element (i)));
            }
        }

        private Gtk.Widget build_session (Json.Object session) {
            var state = session.get_string_member ("state") ?? "off";
            var card = new Gtk.Box (Gtk.Orientation.VERTICAL, 4);
            card.add_css_class ("card");
            var head = new Gtk.Box (Gtk.Orientation.HORIZONTAL, 6);
            var dot = new Gtk.Label ("●");
            dot.add_css_class (state == "ok" ? "dot-ok" : state == "warn" ? "dot-warn" : "dot-off");
            dot.set_tooltip_text (state == "ok" ? "Ready" : state == "warn" ? "Needs attention" : "Not set up");
            head.append (dot);
            var title = new Gtk.Label (session.get_string_member ("name") ?? "Session") { xalign = 0, hexpand = true };
            title.add_css_class ("provider-title");
            head.append (title);
            card.append (head);
            card.append (subtle_label (session.get_string_member ("detail") ?? ""));

            var periods = session.has_member ("periods") ? session.get_array_member ("periods") : null;
            if (periods == null || periods.get_length () == 0) {
                return card;
            }
            // 5 hours and 7 days are the windows the plans are limited by.
            for (uint i = 0; i < periods.get_length () && i < 2; i++) {
                var period = periods.get_object_element (i);
                var cost = period.get_double_member ("costUSD");
                var value = "%s req · %s tok".printf (period.get_int_member ("requests").to_string (),
                    Presentation.count_text (period.get_int_member ("tokens")));
                if (cost > 0) {
                    value += " · $%0.2f".printf (cost);
                }
                append_metric (card, period.get_string_member ("label") ?? "Usage", value);
            }
            var note = session.get_string_member ("note") ?? "";
            if (note.length > 0) {
                card.append (subtle_label (note));
            }
            return card;
        }

        // ---- Small builders -----------------------------------------------------------

        private static Gtk.Label subtle_label (string text) {
            var label = new Gtk.Label (text) { xalign = 0, wrap = true, halign = Gtk.Align.FILL };
            label.add_css_class ("dim-label");
            label.add_css_class ("caption");
            return label;
        }

        private static void append_metric (Gtk.Box card, string name, string value) {
            var row = new Gtk.Box (Gtk.Orientation.HORIZONTAL, 8);
            row.append (new Gtk.Label (name) { xalign = 0, hexpand = true });
            var value_label = new Gtk.Label (value) { xalign = 1 };
            value_label.add_css_class ("numeric");
            row.append (value_label);
            card.append (row);
        }

        /* A centred, explained state: never a bare "Unavailable". */
        private void show_state (Gtk.Box page, string icon, string headline, string message, bool with_settings) {
            clear (page);
            var state = new Gtk.Box (Gtk.Orientation.VERTICAL, 6) {
                halign = Gtk.Align.CENTER, margin_top = 14, margin_bottom = 14
            };
            state.append (new Gtk.Image.from_icon_name (icon) { pixel_size = 32, opacity = 0.6 });
            var title = new Gtk.Label (headline) { justify = Gtk.Justification.CENTER };
            title.add_css_class ("state-title");
            state.append (title);
            if (message.length > 0) {
                var detail = new Gtk.Label (message) {
                    wrap = true, justify = Gtk.Justification.CENTER, max_width_chars = 36
                };
                detail.add_css_class ("dim-label");
                detail.add_css_class ("caption");
                state.append (detail);
            }
            if (with_settings) {
                var settings = new Gtk.Button.with_label ("Open Settings…") { halign = Gtk.Align.CENTER, margin_top = 4 };
                settings.add_css_class ("suggested-action");
                settings.clicked.connect (() => {
                    popdown_from (settings);
                    run_action ("--settings");
                });
                state.append (settings);
            }
            page.append (state);
        }

        private void show_unavailable (string icon, string headline, string message) {
            snapshot_busy = false;
            last_digest = "";
            panel_label.set_text ("—");
            panel_label.remove_css_class ("level-low");
            panel_label.remove_css_class ("level-critical");
            panel_display.set_tooltip_text (headline + " · " + message);
            subtitle_label.set_text ("Usage unavailable");
            chip_label.set_visible (false);
            set_refreshing (false);
            show_state (quota_box, icon, headline, message, true);
        }

        public override Gtk.Widget get_display_widget () {
            return panel_display;
        }

        public override Gtk.Widget? get_widget () {
            read_snapshot.begin ();
            return menu;
        }

        public override void opened () {
            read_snapshot.begin (true);
            ensure_sessions (15);
        }

        public override void closed () {
        }
    }
}

public Wingpanel.Indicator? get_indicator (Module module, Wingpanel.ServerType server_type) {
    if (server_type != Wingpanel.ServerType.SESSION) {
        return null;
    }
    return new MSeries.CodexBarIndicator ();
}
