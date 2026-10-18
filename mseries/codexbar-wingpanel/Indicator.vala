/* CodexBar quota indicator for Pantheon's Wingpanel. */
using GLib;
using Gtk;
using Json;
using Wingpanel;

namespace MSeries {
    public class CodexBarIndicator : Wingpanel.Indicator {
        private Gtk.Box panel_segments;
        private string panel_digest = "";
        private Json.Array? panel_entries = null;
        private delegate void ActionFunc ();
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
        private Json.Array? opencode_accounts = null;
        private bool opencode_accounts_in_flight = false;
        private int64 opencode_accounts_fetched_us = 0;
        private uint opencode_generation = 0;
        private bool opencode_switch_in_flight = false;
        private bool opencode_login_in_flight = false;
        private Gtk.Label[] account_quota_labels = {};
        private Json.Array[] account_quota_windows = {};
        private Json.Array hint_candidates = new Json.Array ();
        private Json.Object hint_selection = new Json.Object ();
        private string hints_digest = "";

        public CodexBarIndicator () {
            GLib.Object (code_name: "codexbar");
        }

        construct {
            executable = GLib.Path.build_filename (Environment.get_home_dir (), ".local", "bin", "codexbar-linux");

            // One dense segment per provider: company mark, % left of the binding limit, time to its reset.
            panel_segments = new Gtk.Box (Gtk.Orientation.HORIZONTAL, 9);
            panel_segments.add_css_class ("mseries-codexbar-bar");
            panel_display = new Gtk.Box (Gtk.Orientation.HORIZONTAL, 0);
            panel_display.append (panel_segments);
            show_panel_placeholder ();
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

            // No header: the quota cards lead. Freshness and refresh live in the bottom bar with the dock.
            subtitle_label = new Gtk.Label ("Loading usage…") { xalign = 0, hexpand = true, ellipsize = Pango.EllipsizeMode.END };
            subtitle_label.add_css_class ("dim-label");
            subtitle_label.add_css_class ("caption");
            subtitle_label.add_css_class ("numeric");
            chip_label = new Gtk.Label ("") { valign = Gtk.Align.CENTER, visible = false };
            chip_label.add_css_class ("chip");

            refresh_display = new Gtk.Stack ();
            refresh_display.add_named (new Gtk.Image.from_icon_name ("view-refresh-symbolic") { pixel_size = 18 }, "idle");
            refresh_spinner = new Gtk.Spinner ();
            refresh_display.add_named (refresh_spinner, "busy");
            refresh_button = new Gtk.Button () {
                child = refresh_display,
                tooltip_text = "Refresh usage"
            };
            refresh_button.add_css_class ("flat");
            refresh_button.update_property (Gtk.AccessibleProperty.LABEL, "Refresh usage", -1);
            refresh_button.clicked.connect (() => refresh_usage ());

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

            // Bottom bar: freshness on the left, an icon-only dock on the right (names in tooltips).
            var bar = new Gtk.Box (Gtk.Orientation.HORIZONTAL, 8);
            bar.add_css_class ("mseries-bar");
            bar.append (chip_label);
            bar.append (subtitle_label);
            var actions = new Gtk.Box (Gtk.Orientation.HORIZONTAL, 0) { homogeneous = true };
            actions.add_css_class ("mseries-dock");
            actions.append (make_dock_button ("Quick View", "window-new-symbolic", "--quick-view"));
            actions.append (make_dock_button ("Usage details", "view-list-symbolic", "--usage"));
            actions.append (make_dock_button ("Spending details", "accessories-calculator-symbolic", "--spending"));
            actions.append (make_dock_button ("Settings & sign in", "avatar-default-symbolic", "--settings"));
            actions.append (refresh_button);
            bar.append (actions);
            menu.append (bar);

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
                ".mseries-codexbar .card { padding: 6px 10px; border-radius: 8px; background: alpha(currentColor, 0.06); } " +
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
                ".mseries-codexbar .account-star, .mseries-codexbar-bar .account-star { color: #d4a300; font-weight: 700; } " +
                ".mseries-codexbar .account-reset-hint, .mseries-codexbar-bar .account-reset-hint { color: @error_color; font-weight: 800; } " +
                ".mseries-codexbar .dot-ok { color: @success_color; } " +
                ".mseries-codexbar .dot-warn { color: @warning_color; } " +
                ".mseries-codexbar .dot-bad { color: @error_color; } " +
                ".mseries-codexbar .dot-off { opacity: 0.45; } " +
                ".mseries-codexbar .state-title { font-weight: 700; } " +
                ".mseries-codexbar button { padding: 3px 6px; } " +
                ".mseries-codexbar .mseries-dock { padding: 3px; border-radius: 12px; background: alpha(currentColor, 0.06); } " +
                ".mseries-codexbar .mseries-bar { margin-top: 2px; } " +
                ".mseries-codexbar .mseries-dock button { padding: 6px 11px; border-radius: 9px; min-height: 0; } " +
                ".mseries-codexbar .mseries-dock button:hover { background: alpha(currentColor, 0.1); } " +
                ".mseries-codexbar .account-line { min-height: 0; } " +
                ".mseries-codexbar .provider-mark { opacity: 0.9; } " +
                ".mseries-codexbar .mark-claude { color: #d97757; opacity: 1; } " +
                ".mseries-codexbar button.compact { padding: 1px 8px; min-height: 0; min-width: 0; } " +
                ".mseries-codexbar button.flat.compact { padding: 0 4px; } " +
                ".mseries-codexbar .mseries-switcher button { padding: 2px 6px; } " +
                ".mseries-codexbar-bar label { font-size: 8.5pt; font-feature-settings: \"tnum\"; } " +
                ".mseries-codexbar-bar .seg-value { font-weight: 700; } " +
                ".mseries-codexbar-bar .seg-reset { font-size: 7.5pt; opacity: 0.7; } " +
                ".mseries-codexbar-bar .seg-secondary { font-size: 7.5pt; } " +
                ".mseries-codexbar-bar .level-low { color: @warning_color; } " +
                ".mseries-codexbar-bar .level-critical { color: @error_color; } " +
                ".mseries-codexbar-bar .mark-claude { color: #d97757; } " +
                ".mseries-codexbar-bar .stale { opacity: 0.55; }");
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
            refresh_claude.begin ();
            refresh_codex_accounts.begin ();
            refresh_opencode_accounts.begin ();
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
                // Settings open our native window when it is installed; upstream's Qt window is the fallback.
                var native_settings = GLib.Path.build_filename (Environment.get_home_dir (), ".local", "bin", "codexbar-settings");
                var program = action == "--settings" && FileUtils.test (native_settings, FileTest.IS_EXECUTABLE) ? native_settings : executable;
                string[] command = program == executable ? new string[] { executable, action } : new string[] { native_settings };
                Process.spawn_async (null, command, null,
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
            if (opencode_accounts_fetched_us == 0 ||
                GLib.get_monotonic_time () - opencode_accounts_fetched_us > 120 * GLib.TimeSpan.SECOND) {
                refresh_opencode_accounts.begin ();
            }
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

        private async void refresh_opencode_accounts () {
            if (opencode_accounts_in_flight) return;
            opencode_accounts_in_flight = true;
            var generation = opencode_generation;
            var before = codex_accounts_digest (opencode_accounts);
            try {
                var process = new GLib.Subprocess (SubprocessFlags.STDOUT_PIPE | SubprocessFlags.STDERR_PIPE,
                    "python3", helper_path ("codexbar-opencode-local.py"), "accounts");
                string output;
                yield process.communicate_utf8_async (null, null, out output, null);
                var parser = new Json.Parser ();
                parser.load_from_data (output);
                var root = parser.get_root ();
                if (generation != opencode_generation) return;
                opencode_accounts = null;
                if (process.get_successful () && root != null && root.get_node_type () == Json.NodeType.OBJECT
                    && root.get_object ().has_member ("accounts")) {
                    var accounts = root.get_object ().get_array_member ("accounts");
                    if (accounts != null) opencode_accounts = accounts.ref ();
                }
            } catch (Error e) {
                if (generation == opencode_generation) opencode_accounts = null;
            } finally {
                opencode_accounts_in_flight = false;
                opencode_accounts_fetched_us = generation == opencode_generation ? GLib.get_monotonic_time () : 0;
                if (generation != opencode_generation) refresh_opencode_accounts.begin ();
            }
            if (before != codex_accounts_digest (opencode_accounts)) {
                last_digest = "";
                read_snapshot.begin ();
            }
        }

        private async void switch_opencode_account (string account_id) {
            if (opencode_switch_in_flight) return;
            opencode_switch_in_flight = true;
            var ok = false;
            var message = "OpenCode could not switch accounts. Open OpenCode and try again.";
            try {
                var process = new GLib.Subprocess (SubprocessFlags.STDOUT_PIPE | SubprocessFlags.STDERR_PIPE,
                    "python3", helper_path ("codexbar-opencode-local.py"), "switch", account_id);
                string output;
                yield process.communicate_utf8_async (null, null, out output, null);
                var parser = new Json.Parser ();
                parser.load_from_data (output);
                var root = parser.get_root ();
                if (root != null && root.get_node_type () == Json.NodeType.OBJECT) {
                    ok = process.get_successful () && root.get_object ().get_boolean_member_with_default ("ok", false);
                    message = root.get_object ().get_string_member_with_default ("message", message);
                }
            } catch (Error e) { }
            opencode_switch_in_flight = false;
            // In-flight reads from the old selection must not replace the new account data.
            opencode_generation++;
            opencode_accounts_fetched_us = 0;
            opencode_local_fetched_us = 0;
            last_digest = "";
            refresh_opencode_accounts.begin ();
            refresh_opencode_local.begin ();
            run_action ("--refresh");
            read_snapshot.begin ();
            tell (ok ? "Switched OpenCode account" : "Couldn't switch OpenCode account", message);
        }

        private bool claude_switch_in_flight = false;

        private void choose_claude_switch (string number, string email, bool installed, bool ready) {
            if (claude_switch_in_flight) return;
            if (!installed) {
                switch_claude_account.begin (number, false);
                return;
            }
            var dialog = new Gtk.AlertDialog ("Switch to %s?", email);
            dialog.detail = ready
                ? "Switch both restarts the Claude app and changes its sign-in and Claude Code's command-line login. Finish any running work in Claude first."
                : "This account needs one sign-in in the Claude app before fast switching works. Set up app saves the current app login and restarts Claude at its sign-in screen. Finish any running work first, sign in to this account, then choose Save app login here. CLI only changes Claude Code's command-line login.";
            dialog.buttons = { "Cancel", "CLI only", ready ? "Switch both" : "Set up app" };
            dialog.cancel_button = 0;
            dialog.default_button = 0;
            dialog.modal = false;
            dialog.choose.begin (null, null, (obj, res) => {
                try {
                    var choice = dialog.choose.end (res);
                    if (choice == 1 || choice == 2 && ready) {
                        switch_claude_account.begin (number, choice == 2);
                    } else if (choice == 2) {
                        run_saver.begin ({ "python3", helper_path ("codexbar-claude.py"), "app-login", number },
                            "Sign in to the Claude app", "Couldn't set up the app login", true);
                    }
                } catch (Error e) { }
            });
        }

        // Runs outside Claude, so restarting the app cannot terminate this operation.
        private async void switch_claude_account (string number, bool desktop) {
            if (claude_switch_in_flight) return;
            claude_switch_in_flight = true;
            var ok = false;
            var message = "";
            try {
                string[] command = { "python3", helper_path ("codexbar-claude.py"), "switch", number };
                if (desktop) command += "--desktop";
                var process = new GLib.Subprocess.newv (command, SubprocessFlags.STDOUT_PIPE | SubprocessFlags.STDERR_PIPE);
                string stdout_text;
                string stderr_text;
                yield process.communicate_utf8_async (null, null, out stdout_text, out stderr_text);
                try {
                    var parser = new Json.Parser ();
                    parser.load_from_data (stdout_text ?? "", -1);
                    var root = parser.get_root ();
                    if (root != null && root.get_node_type () == Json.NodeType.OBJECT) {
                        ok = root.get_object ().get_boolean_member_with_default ("ok", false);
                        message = root.get_object ().get_string_member_with_default ("message", "");
                    }
                } catch (Error e) {
                    message = (stderr_text ?? "").strip ();
                }
            } catch (Error e) {
                message = e.message;
            }
            claude_switch_in_flight = false;
            tell (ok ? "Switched Claude account" : "Couldn't switch Claude account",
                message.length > 0 ? message : "The helper reported an error.");
            claude_fetched_us = 0;
            last_digest = "";
            refresh_claude.begin ();
            read_snapshot.begin ();
        }

        private void tell (string heading, string detail) {
            var dialog = new Granite.MessageDialog.with_image_from_icon_name (heading, detail,
                "dialog-information", Gtk.ButtonsType.CLOSE);
            dialog.response.connect (() => dialog.close ());
            dialog.present ();
        }

        private async void run_saver (string[] command, string ok_heading, string failure_heading,
                                      bool report_output = false) {
            try {
                var process = new GLib.Subprocess.newv (command, SubprocessFlags.STDOUT_PIPE | SubprocessFlags.STDERR_MERGE);
                string output;
                yield process.communicate_utf8_async (null, null, out output, null);
                if (process.get_successful ()) {
                    tell (ok_heading, report_output && output.strip ().length > 0
                        ? output.strip () : "It now appears under Accounts.");
                    if (report_output) refresh_usage ();
                } else if (!(process.get_if_exited () && process.get_exit_status () == 130)) {
                    tell (failure_heading, output.strip ().length > 0 ? output.strip () : "The helper reported an error.");
                }
            } catch (Error e) {
                tell (failure_heading, e.message);
            }
            codex_accounts_fetched_us = 0;
            claude_fetched_us = 0;
            last_digest = "";
            refresh_codex_accounts.begin ();
            refresh_claude.begin ();
        }

        // Browser accounts live in native OpenCode; API-key and cookie quota setup remain alternatives.
        private void add_opencode_account () {
            if (opencode_login_in_flight) return;
            opencode_login_in_flight = true;
            run_saver.begin ({ "python3", helper_path ("codexbar-opencode-login.py"), "login" },
                "OpenCode account connected", "Couldn't connect to OpenCode", true, (obj, result) => {
                    run_saver.end (result);
                    opencode_login_in_flight = false;
                    opencode_generation++;
                    opencode_accounts_fetched_us = 0;
                    opencode_local_fetched_us = 0;
                    last_digest = "";
                    refresh_opencode_accounts.begin ();
                    refresh_opencode_local.begin ();
                    run_action ("--refresh");
                    read_snapshot.begin ();
                });
        }

        private void add_claude_account () {
            run_saver.begin ({ "python3", helper_path ("codexbar-claude.py"), "login" },
                "Claude account added", "Couldn't add the Claude account");
        }

        private Gtk.Widget build_claude_card (int64 now_unix) {
            var card = new Gtk.Box (Gtk.Orientation.VERTICAL, 6);
            card.add_css_class ("card");
            var head = new Gtk.Box (Gtk.Orientation.HORIZONTAL, 6);
            var dot = new Gtk.Label ("●");
            dot.add_css_class ("dot-off");
            head.append (dot);
            head.append (build_provider_mark ("claude", "Claude"));
            head.append (build_hint_badges ("claude", true));
            var email = claude_data.get_string_member_with_default ("activeEmail", "");
            var accounts = claude_data.get_array_member ("accounts");
            head.append (build_identity (email, claude_data.get_string_member_with_default ("activePlan", "")));
            card.append (head);
            // CLI and desktop can be switched separately; always name both when they differ.
            var desktop = claude_data.has_member ("desktop") ? claude_data.get_object_member ("desktop") : null;
            if (desktop != null && desktop.get_boolean_member_with_default ("differs", false)) {
                var there = desktop.get_string_member_with_default ("email", "");
                var note = subtle_label ("Claude app: %s".printf (
                    there.length > 0 ? there : "another account"));
                note.set_tooltip_text (claude_data.get_string_member_with_default ("desktopNote", ""));
                card.append (note);
            }
            var snapshot_error = claude_data.get_string_member_with_default ("desktopSnapshotError", "");
            if (snapshot_error.length > 0) card.append (subtle_label (snapshot_error));

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

            var listed = accounts != null ? accounts.get_length () : 0;
            card.append (build_accounts_header ("Sign in to Claude Code, then save that login with claude-swap",
                () => add_claude_account ()));
            if (desktop != null && desktop.get_boolean_member_with_default ("installed", false)) {
                var save_app = new Gtk.Button.with_label ("Save app login") {
                    halign = Gtk.Align.START, tooltip_text = "Remember the Claude app's current sign-in for fast switching"
                };
                save_app.add_css_class ("compact");
                save_app.clicked.connect (() => {
                    popdown_from (save_app);
                    run_saver.begin ({ "python3", helper_path ("codexbar-claude.py"), "app-save" },
                        "Claude app login saved", "Couldn't save the app login", true);
                });
                card.append (save_app);
            }
            for (uint i = 0; i < listed; i++) {
                var account = accounts.get_object_element (i);
                if (account.get_boolean_member_with_default ("active", false) &&
                    (desktop == null || !desktop.get_boolean_member_with_default ("installed", false) ||
                     account.get_boolean_member_with_default ("desktopActive", false))) {
                    continue;
                }
                var number = account.get_int_member_with_default ("number", 0).to_string ();
                var name = account.get_string_member_with_default ("email", "");
                var windows = account.get_array_member ("windows");
                var detail = "Quota unavailable";
                var ready = account.get_boolean_member_with_default ("desktopReady", false);
                var installed = desktop != null && desktop.get_boolean_member_with_default ("installed", false);
                if (installed && !ready) detail += " · app sign-in needed";
                card.append (build_account_line (name, detail,
                    "Choose whether to switch Claude Code or the Claude app and CLI to %s".printf (name),
                    () => choose_claude_switch (number, name, installed, ready), windows, hint_id ("claude", account), account.get_string_member_with_default ("plan", "")));
            }
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

        private AccountDialog? codex_login_dialog = null;

        private void add_codex_account () {
            if (codex_login_dialog != null) {
                codex_login_dialog.present ();
                return;
            }
            codex_login_dialog = new AccountDialog ("Add a Codex account",
                "Connect another ChatGPT account to CodexBar.",
                "mseries-codexbar-openai-symbolic", { "python3", helper_path ("codexbar-accounts.py"), "login" });
            codex_login_dialog.completed.connect (() => {
                codex_accounts_fetched_us = 0;
                refresh_codex_accounts.begin ();
            });
            codex_login_dialog.close_request.connect (() => { codex_login_dialog = null; return false; });
            codex_login_dialog.present ();
        }

        private Gtk.Widget build_codex_accounts () {
            var box = new Gtk.Box (Gtk.Orientation.VERTICAL, 2);
            box.append (build_accounts_header ("Sign in to another ChatGPT account", () => add_codex_account ()));
            if (codex_accounts == null) {
                return box;
            }
            for (uint i = 0; i < codex_accounts.get_length (); i++) {
                var account = codex_accounts.get_object_element (i);
                if (account.get_boolean_member_with_default ("active", false)) {
                    continue;
                }
                var email = account.get_string_member_with_default ("email", "");
                var account_id = account.get_string_member_with_default ("id", email);
                var windows = account.has_member ("windows") ? account.get_array_member ("windows") : null;
                var detail = account.has_member ("error") ? "unavailable" : "—";
                box.append (build_account_line (email, detail,
                    "Make %s the active Codex account. Restart running Codex sessions to use it.".printf (email),
                    () => run_accounts_helper ({ "switch", account_id }), windows, hint_id ("codex", account), account.get_string_member_with_default ("plan", "")));
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

        // Local history supplements OpenCode account quota and remains available while signed out.
        private async void refresh_opencode_local () {
            if (opencode_local_in_flight) {
                return;
            }
            opencode_local_in_flight = true;
            var generation = opencode_generation;
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
                if (generation != opencode_generation) return;
                changed = local_digest (parsed) != local_digest (opencode_local);
                opencode_local = parsed;
            } catch (Error e) {
                if (generation == opencode_generation) {
                    changed = opencode_local != null;
                    opencode_local = null;
                }
            } finally {
                opencode_local_in_flight = false;
                opencode_local_fetched_us = generation == opencode_generation ? GLib.get_monotonic_time () : 0;
                if (generation != opencode_generation) refresh_opencode_local.begin ();
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

            // The panel's countdowns tick every poll; the popover is rebuilt only when its data changes.
            panel_entries = entries;
            update_account_hints (entries, now_unix);
            update_panel (entries, now_unix);
            for (int i = 0; i < account_quota_labels.length; i++) {
                account_quota_labels[i].set_markup (colored_account_quota (account_quota_labels[i], account_quota_windows[i], now_unix));
            }
            var digest = snapshot_digest (snapshot, now_unix);
            if (digest == last_digest) {
                return;
            }
            last_digest = digest;
            render_quota (entries, now_unix);
            render_spend (snapshot);
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

        private static int provider_rank (string provider) {
            return provider == "codex" ? 0 : provider == "claude" ? 1 : provider == "opencodego" ? 2 : 3;
        }

        private static string hint_id (string provider, Json.Object account) {
            if (account.get_boolean_member_with_default ("active", false)) return provider + ":active";
            var key = account.get_string_member_with_default ("id", "");
            if (key.length == 0 && account.has_member ("number")) key = account.get_int_member ("number").to_string ();
            if (key.length == 0) key = account.get_string_member_with_default ("email", "unknown");
            return provider + ":saved:" + key;
        }

        private static void hint_candidate (Json.Array candidates, string id, string email, Json.Array? windows, bool stale) {
            var candidate = new Json.Object ();
            candidate.set_string_member ("id", id);
            candidate.set_string_member ("email", email.length > 0 ? email : "Active account");
            candidate.set_boolean_member ("stale", stale);
            candidate.set_array_member ("windows", windows != null ? windows.ref () : new Json.Array ());
            candidates.add_object_element (candidate);
        }

        private void update_account_hints (Json.Array entries, int64 now_unix) {
            hint_candidates = new Json.Array ();
            string[] supplied = {};
            for (uint i = 0; i < entries.get_length (); i++) {
                var entry = entries.get_object_element (i);
                var provider = entry.get_string_member_with_default ("provider", "").down ();
                supplied += provider;
                hint_candidate (hint_candidates, provider + ":active", account_email_for (provider, entry),
                    entry.get_array_member ("windows"), QuotaEta.entry_stale (entry, snapshot_stale, now_unix)
                    || entry.get_string_member_with_default ("error", "").length > 0);
            }
            foreach (var provider in new string[] { "codex", "claude", "opencodego" }) {
                var accounts = provider_accounts (provider);
                var fetched = provider == "codex" ? codex_accounts_fetched_us
                    : provider == "claude" ? claude_fetched_us : opencode_accounts_fetched_us;
                var max_age = (provider == "codex" ? 600 : 240) * GLib.TimeSpan.SECOND;
                for (uint i = 0; accounts != null && i < accounts.get_length (); i++) {
                    var account = accounts.get_object_element (i);
                    if (account.get_boolean_member_with_default ("active", false) && provider in supplied) continue;
                    hint_candidate (hint_candidates, hint_id (provider, account), account.get_string_member_with_default ("email", ""),
                        account.has_member ("windows") ? account.get_array_member ("windows") : null,
                        fetched == 0 || GLib.get_monotonic_time () - fetched > max_age || account.has_member ("error"));
                }
            }
            hint_selection = Presentation.account_hints (hint_candidates, now_unix);
            var digest = local_digest (hint_selection);
            for (uint i = 0; i < hint_candidates.get_length (); i++) {
                var candidate = hint_candidates.get_object_element (i);
                digest += candidate.get_string_member ("id") + candidate.get_string_member ("email");
            }
            if (digest != hints_digest) {
                hints_digest = digest;
                last_digest = "";
                panel_digest = "";
            }
        }

        private bool has_hint (string kind, string id, bool provider = false) {
            var selected = hint_selection.has_member (kind) ? hint_selection.get_array_member (kind) : null;
            for (uint i = 0; selected != null && i < selected.get_length (); i++) {
                var candidate = selected.get_string_element (i);
                if (provider ? candidate.has_prefix (id + ":") : candidate == id) return true;
            }
            return false;
        }

        private string hint_description (string kind, string id, bool provider) {
            var text = new StringBuilder (kind == "best"
                ? "Most available quota · highest percentage across the account's tightest reported limit. Percentages are relative to each plan, not absolute token counts."
                : "Next weekly reset · earliest upcoming 7-day reset among accounts with current data.");
            for (uint i = 0; i < hint_candidates.get_length (); i++) {
                var candidate = hint_candidates.get_object_element (i);
                var key = candidate.get_string_member ("id");
                if (!(provider ? key.has_prefix (id + ":") : key == id) || !has_hint (kind, key)) continue;
                text.append ("\n" + candidate.get_string_member ("email"));
                if (kind == "weekly") {
                    var reset = Presentation.account_weekly_reset (candidate.get_array_member ("windows"), new DateTime.now_utc ().to_unix ());
                    if (reset > 0) text.append (" · " + new DateTime.from_unix_utc (reset).to_local ().format ("%a %b %d, %H:%M"));
                }
            }
            return text.str;
        }

        private Gtk.Widget build_hint_badges (string id, bool provider = false) {
            var box = new Gtk.Box (Gtk.Orientation.HORIZONTAL, 3) { valign = Gtk.Align.CENTER };
            if (has_hint ("best", id, provider)) {
                var star = new Gtk.Label ("★") { tooltip_text = hint_description ("best", id, provider) };
                star.add_css_class ("account-star");
                star.update_property (Gtk.AccessibleProperty.LABEL, "Most available quota", -1);
                box.append (star);
            }
            if (has_hint ("weekly", id, provider)) {
                var reset = new Gtk.Label ("!") { tooltip_text = hint_description ("weekly", id, provider) };
                reset.add_css_class ("account-reset-hint");
                reset.update_property (Gtk.AccessibleProperty.LABEL, "Next weekly reset", -1);
                box.append (reset);
            }
            box.visible = box.get_first_child () != null;
            return box;
        }

        private string hint_markup (string id, Gtk.Widget widget) {
            return (has_hint ("best", id) ? "<span foreground=\"#d4a300\" weight=\"bold\">★</span> " : "")
                + (has_hint ("weekly", id) ? "<span foreground=\"%s\" weight=\"bold\">!</span> ".printf (
                    quota_theme_color (widget, "error_color", "#c6262e")) : "");
        }

        private void show_panel_placeholder () {
            panel_digest = "";
            clear (panel_segments);
            panel_segments.append (new Gtk.Label ("—"));
        }

        /* Fills one segment's texts from a quota window list; returns the level of the binding window. */
        private static QuotaLevel window_segment (Json.Array windows, int64 now_unix, out string value_text,
                                                  out string reset_text, StringBuilder tooltip) {
            value_text = "—";
            reset_text = "";
            var level = QuotaLevel.UNKNOWN;
            var binding = Presentation.binding_window (windows);
            // Keep the five-hour balance visible even when a longer window is lower.
            // Every window remains separate in the dropdown and account summaries.
            for (uint w = 0; w < windows.get_length (); w++) {
                var candidate = windows.get_object_element (w);
                var minutes = candidate.get_int_member_with_default ("minutes", 0);
                if (candidate.get_string_member_with_default ("key", "") == "primary" || minutes > 0 && minutes <= 360) {
                    binding = (int) w;
                    break;
                }
            }
            for (uint w = 0; w < windows.get_length (); w++) {
                var window = windows.get_object_element (w);
                var minutes = (int) window.get_int_member_with_default ("minutes", 0);
                var short_label = Presentation.short_window_label (
                    window.get_string_member_with_default ("label", "Quota"), minutes);
                var node = window.get_member ("remaining");
                if (node == null || node.get_node_type () != Json.NodeType.VALUE) {
                    tooltip.append ("\n  %s  not reported yet".printf (short_label));
                    continue;
                }
                var remaining = node.get_double ();
                var reset = window.get_string_member_with_default ("resetText", "");
                tooltip.append ("\n  %s  %0.0f%% left · %s".printf (short_label, remaining,
                    reset.length > 0 ? reset.down () : "reset unknown"));
                if ((int) w != binding) continue;
                level = Presentation.level_for (remaining);
                value_text = "%s %0.0f%%".printf (short_label, remaining);
                var resets_at = new DateTime.from_iso8601 (window.get_string_member_with_default ("resetsAt", ""), null);
                reset_text = resets_at != null ? Presentation.countdown_text (resets_at.to_unix () - now_unix)
                    : compact_reset (reset).replace (" ", "");
            }
            return level;
        }

        private void update_panel (Json.Array entries, int64 now_unix) {
            string[] providers = {};
            string[] values = {};
            string[] resets = {};
            QuotaLevel[] levels = {};
            bool[] stales = {};
            var tooltip = new StringBuilder ();
            var has_claude = false;

            for (uint i = 0; i < entries.get_length (); i++) {
                var entry = entries.get_object_element (i);
                var provider = (entry.get_string_member ("provider") ?? "").down ();
                has_claude = has_claude || provider == "claude";
                var windows = entry.get_array_member ("windows");
                var stale = QuotaEta.entry_stale (entry, snapshot_stale, now_unix);
                var section = new StringBuilder (provider_title (provider));
                string value_text = "—";
                string reset_text = "";
                var level = QuotaLevel.UNKNOWN;
                if (windows != null && windows.get_length () > 0) {
                    level = window_segment (windows, now_unix, out value_text, out reset_text, section);
                    if (provider == "opencodego") {
                        var local_tokens = opencode_week_tokens ();
                        if (local_tokens.length > 0) {
                            value_text += " · " + local_tokens + " tok";
                            section.append ("\n  " + local_tokens + " local tokens in 7 days (all local accounts)");
                        }
                    }
                } else if (provider == "opencodego" && opencode_local != null) {
                    // No account quota without a web sign-in: show this machine's 7-day token count instead.
                    var periods = opencode_local.get_array_member ("periods");
                    for (uint p = 0; periods != null && p < periods.get_length (); p++) {
                        var period = periods.get_object_element (p);
                        var label = period.get_string_member_with_default ("label", "");
                        var tokens = period.get_int_member_with_default ("tokens", 0);
                        section.append ("\n  %s".printf (Presentation.local_usage_line (label,
                            period.get_double_member_with_default ("costUSD", 0),
                            period.get_int_member_with_default ("requests", 0), tokens)));
                        if (label.contains ("7")) {
                            value_text = Presentation.panel_count_text (tokens);
                            reset_text = "7d tok";
                        }
                    }
                    section.append ("\n  Local estimate, not account quota");
                    stale = false;
                } else {
                    var error = entry.get_string_member_with_default ("error", "");
                    section.append ("\n  " + (error.length > 0 ? error : "Usage not reported yet"));
                }
                providers += provider;
                values += value_text;
                resets += reset_text;
                levels += level;
                stales += stale;
                tooltip.append ((tooltip.len > 0 ? "\n\n" : "") + section.str);
            }

            // Claude quota comes from our claude-swap helper when upstream's snapshot has no Claude entry.
            if (!has_claude && claude_data != null) {
                var accounts = claude_data.get_array_member ("accounts");
                for (uint i = 0; accounts != null && i < accounts.get_length (); i++) {
                    var account = accounts.get_object_element (i);
                    var windows = account.get_array_member ("windows");
                    if (!account.get_boolean_member_with_default ("active", false) || windows == null
                        || windows.get_length () == 0) continue;
                    var section = new StringBuilder ("Claude");
                    string value_text;
                    string reset_text;
                    var level = window_segment (windows, now_unix, out value_text, out reset_text, section);
                    providers += "claude";
                    values += value_text;
                    resets += reset_text;
                    levels += level;
                    stales += false;
                    tooltip.append ((tooltip.len > 0 ? "\n\n" : "") + section.str);
                    break;
                }
            }

            panel_display.set_tooltip_text (tooltip.len > 0
                ? tooltip.str + (snapshot_stale ? "\n\nCached: CodexBar couldn't reach a provider." : "")
                    + "\n\nMiddle-click to refresh"
                : "Usage unavailable");

            var digest = new StringBuilder ();
            digest.append (hints_digest);
            foreach (var provider in new string[] { "codex", "claude", "opencodego" }) {
                digest.append (alternate_account_text (provider, now_unix));
            }
            for (int i = 0; i < providers.length; i++) {
                digest.append ("%s|%s|%s|%d|%s;".printf (providers[i], values[i], resets[i], (int) levels[i],
                    stales[i].to_string ()));
            }
            if (digest.str == panel_digest) return;
            panel_digest = digest.str;

            clear (panel_segments);
            for (int rank = 0; rank <= 3; rank++) {
                for (int i = 0; i < providers.length; i++) {
                    if (provider_rank (providers[i]) != rank) continue;
                    panel_segments.append (build_panel_segment (providers[i], values[i], resets[i], levels[i], stales[i]));
                }
            }
            if (providers.length == 0) panel_segments.append (new Gtk.Label ("—"));
        }

        private Gtk.Widget build_panel_segment (string provider, string value_text, string reset_text,
                                                       QuotaLevel level, bool stale) {
            var segment = new Gtk.Box (Gtk.Orientation.HORIZONTAL, 3);
            if (stale) segment.add_css_class ("stale");
            var mark = build_provider_mark (provider, provider_title (provider));
            var icon = mark as Gtk.Image;
            if (icon != null) {
                icon.pixel_size = 12;
                icon.valign = Gtk.Align.CENTER;
            }
            segment.append (mark);
            segment.append (build_hint_badges (provider, true));
            var value = new Gtk.Label (value_text) { valign = Gtk.Align.BASELINE_CENTER };
            value.add_css_class ("seg-value");
            if (level == QuotaLevel.LOW) value.add_css_class ("level-low");
            if (level == QuotaLevel.CRITICAL) value.add_css_class ("level-critical");
            segment.append (value);
            if (reset_text.length > 0) {
                var reset = new Gtk.Label (reset_text) { valign = Gtk.Align.BASELINE_CENTER };
                reset.add_css_class ("seg-reset");
                segment.append (reset);
            }
            var alternate = alternate_account_text (provider, new DateTime.now_utc ().to_unix ());
            if (alternate.length == 0) return segment;
            var stack = new Gtk.Box (Gtk.Orientation.VERTICAL, 0) { valign = Gtk.Align.CENTER };
            stack.append (segment);
            var label = new Gtk.Label (null) { xalign = 0, use_markup = true };
            label.add_css_class ("seg-secondary");
            var markup = new StringBuilder ();
            var accounts = provider_accounts (provider);
            for (uint i = 0; accounts != null && i < accounts.get_length (); i++) {
                var account = accounts.get_object_element (i);
                if (account.get_boolean_member_with_default ("active", false)) continue;
                if (markup.len > 0) markup.append ("  ");
                var windows = account.has_member ("windows") ? account.get_array_member ("windows") : null;
                markup.append ("%s%lld: %s".printf (hint_markup (hint_id (provider, account), label), account.get_int_member_with_default ("number", i + 1),
                    windows == null || windows.get_length () == 0 ? "—"
                        : colored_account_quota (label, windows, new DateTime.now_utc ().to_unix ())));
            }
            label.set_markup (markup.str);
            stack.append (label);
            stack.set_tooltip_text (alternate_account_tooltip (provider));
            return stack;
        }

        private Json.Array? provider_accounts (string provider) {
            return provider == "codex" ? codex_accounts : provider == "opencodego" ? opencode_accounts
                : provider == "claude" && claude_data != null ? claude_data.get_array_member ("accounts") : null;
        }

        private string alternate_account_text (string provider, int64 now_unix) {
            var accounts = provider_accounts (provider);
            var text = new StringBuilder ();
            for (uint i = 0; accounts != null && i < accounts.get_length (); i++) {
                var account = accounts.get_object_element (i);
                if (account.get_boolean_member_with_default ("active", false)) continue;
                var windows = account.has_member ("windows") ? account.get_array_member ("windows") : null;
                if (text.len > 0) text.append ("  ");
                text.append ("%lld: %s".printf (account.get_int_member_with_default ("number", i + 1),
                    windows != null && windows.get_length () > 0 ? Presentation.account_quota (windows, now_unix) : "—"));
            }
            return text.str;
        }

        private string alternate_account_tooltip (string provider) {
            var text = new StringBuilder (provider_title (provider) + " · alternate accounts · % quota left, ↻ reset countdown");
            var accounts = provider_accounts (provider);
            for (uint i = 0; accounts != null && i < accounts.get_length (); i++) {
                var account = accounts.get_object_element (i);
                if (account.get_boolean_member_with_default ("active", false)) continue;
                text.append ("\n%lld: %s".printf (account.get_int_member_with_default ("number", i + 1),
                    account.get_string_member_with_default ("email", "Saved account")));
                var id = hint_id (provider, account);
                if (has_hint ("best", id)) text.append (" · ★ Most available quota");
                if (has_hint ("weekly", id)) text.append (" · ! Next weekly reset");
            }
            return text.str;
        }

        // ---- Pages --------------------------------------------------------------------

        private static string provider_title (string provider) {
            return provider == "codex" ? "OpenAI Codex" :
                provider == "claude" ? "Claude" :
                provider == "opencodego" ? "OpenCode Go" : provider;
        }

        private void render_quota (Json.Array entries, int64 now_unix) {
            account_quota_labels = {};
            account_quota_windows = {};
            clear (quota_box);
            var has_claude = false;
            for (uint i = 0; i < entries.get_length (); i++) {
                has_claude = has_claude || entries.get_object_element (i).get_string_member_with_default ("provider", "").down () == "claude";
            }
            // Match the panel order, including Claude's locally supplied accounts card.
            for (int rank = 0; rank <= 3; rank++) {
                if (rank == provider_rank ("claude") && !has_claude && claude_data != null) {
                    quota_box.append (build_claude_card (now_unix));
                }
                for (uint i = 0; i < entries.get_length (); i++) {
                    var entry = entries.get_object_element (i);
                    if (provider_rank (entry.get_string_member_with_default ("provider", "").down ()) == rank) {
                        quota_box.append (build_provider_card (entry, now_unix));
                    }
                }
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
            head.append (build_provider_mark (provider, title_text));
            head.append (build_hint_badges (provider, true));
            var email = account_email_for (provider, entry);
            var plan = entry.get_string_member_with_default ("plan", "");
            var accounts = provider_accounts (provider);
            for (uint i = 0; accounts != null && i < accounts.get_length (); i++) {
                var account = accounts.get_object_element (i);
                if (account.get_boolean_member_with_default ("active", false) && email.length > 0 &&
                    account.get_string_member_with_default ("email", "").down () == email.down ()) {
                    // Upstream's generic "Go" describes this provider, not the workspace's tier.
                    if (plan.strip ().length == 0 || (provider == "opencodego" &&
                        (plan.down () == "go" || account.get_string_member_with_default ("planSource", "") == "console"))) {
                        plan = account.get_string_member_with_default ("plan", "");
                    }
                    break;
                }
            }
            head.append (build_identity (email, plan));
            card.append (head);

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
                card.append (build_codex_accounts ());
            }
            if (provider == "opencodego") {
                var local_tokens = opencode_week_tokens ();
                if (windows != null && windows.get_length () > 0 && local_tokens.length > 0) {
                    card.append (subtle_label (local_tokens + " local tokens · 7 days · all local accounts"));
                }
                card.append (build_accounts_header ("Connect another OpenCode Go key or browser sign-in",
                    () => add_opencode_account ()));
                for (uint i = 0; opencode_accounts != null && i < opencode_accounts.get_length (); i++) {
                    var account = opencode_accounts.get_object_element (i);
                    if (account.get_boolean_member_with_default ("active", false)) continue;
                    var saved_email = account.get_string_member_with_default ("email", "Saved account");
                    var workspace = account.get_string_member_with_default ("workspace", "");
                    var caption = workspace.length > 0 ? saved_email + " · " + workspace : saved_email;
                    var account_id = account.get_string_member_with_default ("id", "");
                    card.append (build_account_line (caption,
                        account.get_string_member_with_default ("error", "Quota unavailable"),
                        "Make %s active in OpenCode and refresh CodexBar usage".printf (caption),
                        () => switch_opencode_account.begin (account_id),
                        account.has_member ("windows") ? account.get_array_member ("windows") : null,
                        hint_id ("opencodego", account), account.get_string_member_with_default ("plan", ""),
                        account.get_boolean_member_with_default ("switchable", true)));
                }
            }
            if (error.length > 0 || windows == null || windows.get_length () == 0) {
                var estimate = provider == "opencodego" ? opencode_local : null;
                var periods = estimate != null ? estimate.get_array_member ("periods") : null;
                if (periods != null && periods.get_length () > 0) {
                    card.append (subtle_label (estimate.get_string_member_with_default ("message", "Local usage estimate · not account quota")));
                    for (uint i = 0; i < periods.get_length (); i++) {
                        var period = periods.get_object_element (i);
                        if (period.get_int_member_with_default ("requests", 0) == 0 && i + 1 < periods.get_length ()) {
                            continue;
                        }
                        card.append (subtle_label (Presentation.local_usage_line (
                            period.get_string_member_with_default ("label", ""),
                            period.get_double_member_with_default ("costUSD", 0),
                            period.get_int_member_with_default ("requests", 0),
                            period.get_int_member_with_default ("tokens", 0))));
                    }
                    card.append (subtle_label ("Sign in to OpenCode or connect a Go API key to load account quota."));
                } else {
                    card.append (subtle_label (provider == "opencodego"
                        ? "Sign in to OpenCode or connect a Go API key. Local activity is under Sessions."
                        : error.length > 0 ? error : "No usage reported yet."));
                }
                var settings = new Gtk.Button.with_label (provider == "opencodego" ? "Sign in…" : "Open Settings…") {
                    halign = Gtk.Align.START
                };
                settings.clicked.connect (() => {
                    popdown_from (settings);
                    if (provider == "opencodego") {
                        add_opencode_account ();
                    } else {
                        run_action ("--settings");
                    }
                });
                card.append (settings);
            }
            return card;
        }

        private string opencode_week_tokens () {
            var periods = opencode_local != null ? opencode_local.get_array_member ("periods") : null;
            for (uint i = 0; periods != null && i < periods.get_length (); i++) {
                var period = periods.get_object_element (i);
                if (period.get_string_member_with_default ("label", "") == "7 days") {
                    return Presentation.panel_count_text (period.get_int_member_with_default ("tokens", 0));
                }
            }
            return "";
        }

        /* Dense building blocks shared by every provider card. */
        private static string compact_reset (string reset) {
            return reset.has_prefix ("Resets in ") ? reset.substring (10) : reset;
        }

        /* The company mark replaces the written provider name; the name stays in the tooltip and for screen readers. */
        private static Gtk.Widget build_provider_mark (string provider, string title_text) {
            var icon_name = provider == "codex" ? "mseries-codexbar-openai-symbolic" :
                provider == "claude" ? "mseries-codexbar-claude-symbolic" :
                provider == "opencodego" ? "mseries-codexbar-opencode-symbolic" : "";
            if (icon_name.length == 0 || !Gtk.IconTheme.get_for_display (Gdk.Display.get_default ()).has_icon (icon_name)) {
                var text = new Gtk.Label (title_text) { xalign = 0 };
                text.add_css_class ("provider-title");
                return text;
            }
            var icon = new Gtk.Image.from_icon_name (icon_name) { pixel_size = 18 };
            icon.add_css_class ("provider-mark");
            icon.add_css_class ("mark-" + provider);
            icon.set_tooltip_text (title_text);
            icon.update_property (Gtk.AccessibleProperty.LABEL, title_text, -1);
            return icon;
        }

        private Gtk.Widget build_plan_badge (string email, string plan) {
            var text = Presentation.plan_label (plan);
            var badge = new Gtk.Label (text.length > 0 ? text : "Plan unavailable") {
                valign = Gtk.Align.CENTER, ellipsize = Pango.EllipsizeMode.END, max_width_chars = 18
            };
            badge.add_css_class ("plan");
            if (text.length == 0) badge.add_css_class ("dim-label");
            badge.tooltip_text = text.length > 0 ? "Reported plan for %s: %s".printf (email, text)
                : "This service hasn't reported a plan for this account.";
            return badge;
        }

        private Gtk.Widget build_identity (string email, string plan = "") {
            var identity = new Gtk.Box (Gtk.Orientation.HORIZONTAL, 4) { halign = Gtk.Align.END, hexpand = true };
            identity.add_css_class ("account-row");
            var icon = new Gtk.Image.from_icon_name ("avatar-default-symbolic") { pixel_size = 12 };
            icon.add_css_class ("dim-label");
            identity.append (icon);
            var label = new Gtk.Label (email.length > 0 ? email : "Account not detected") {
                xalign = 1, ellipsize = Pango.EllipsizeMode.MIDDLE, max_width_chars = 30
            };
            label.add_css_class ("caption");
            label.add_css_class ("dim-label");
            identity.set_tooltip_text (email.length > 0 ? "Signed in as " + email
                : "CodexBar can't tell which account this is signed in with");
            identity.append (label);
            identity.append (build_plan_badge (email, plan));
            return identity;
        }

        private Gtk.Widget build_accounts_header (string tooltip, owned ActionFunc on_add) {
            var row = new Gtk.Box (Gtk.Orientation.HORIZONTAL, 4);
            var title = new Gtk.Label ("Accounts") { xalign = 0, hexpand = true };
            title.add_css_class ("caption");
            title.add_css_class ("dim-label");
            row.append (title);
            var add = new Gtk.Button () { child = new Gtk.Image.from_icon_name ("list-add-symbolic") { pixel_size = 12 }, tooltip_text = tooltip, valign = Gtk.Align.CENTER };
            add.add_css_class ("flat");
            add.add_css_class ("compact");
            add.update_property (Gtk.AccessibleProperty.LABEL, tooltip, -1);
            add.clicked.connect (() => {
                popdown_from (add);
                on_add ();
            });
            row.append (add);
            return row;
        }

        private Gtk.Widget build_account_line (string email, string detail, string switch_tooltip,
                                               owned ActionFunc? on_switch, Json.Array? windows = null, string candidate_id = "", string plan = "", bool switch_sensitive = true) {
            var line = new Gtk.Box (Gtk.Orientation.HORIZONTAL, 6);
            line.add_css_class ("account-line");
            var name = new Gtk.Label (email) { xalign = 0, hexpand = true, ellipsize = Pango.EllipsizeMode.MIDDLE };
            name.set_tooltip_text (email);
            var content = new Gtk.Box (Gtk.Orientation.VERTICAL, 0) { hexpand = true };
            var identity = new Gtk.Box (Gtk.Orientation.HORIZONTAL, 4);
            identity.append (build_hint_badges (candidate_id));
            identity.append (name);
            identity.append (build_plan_badge (email, plan));
            content.append (identity);
            var has_quota = windows != null && windows.get_length () > 0;
            var meta = new Gtk.Label (has_quota ? Presentation.account_quota (windows, new DateTime.now_utc ().to_unix ()) : detail) {
                xalign = 0, wrap = true, wrap_mode = Pango.WrapMode.WORD_CHAR
            };
            meta.set_tooltip_text ("Quota remaining · ↻ time until reset. " + detail);
            meta.add_css_class ("caption");
            if (!has_quota) meta.add_css_class ("dim-label");
            else meta.set_markup (colored_account_quota (meta, windows, new DateTime.now_utc ().to_unix ()));
            meta.add_css_class ("numeric");
            content.append (meta);
            line.append (content);
            if (has_quota) {
                account_quota_labels += meta;
                account_quota_windows += windows;
            }
            if (on_switch == null) return line;
            var button = new Gtk.Button.with_label ("Switch") {
                valign = Gtk.Align.CENTER, sensitive = switch_sensitive,
                tooltip_text = switch_sensitive ? switch_tooltip : "Sign in to this account again in OpenCode before switching"
            };
            button.add_css_class ("compact");
            button.clicked.connect (() => {
                popdown_from (button);
                on_switch ();
            });
            line.append (button);
            return line;
        }

        private static string quota_theme_color (Gtk.Widget widget, string name, string fallback) {
            Gdk.RGBA color;
            if (!widget.get_style_context ().lookup_color (name, out color)) return fallback;
            return "#%02x%02x%02x".printf ((int) (color.red * 255), (int) (color.green * 255), (int) (color.blue * 255));
        }

        private static string colored_account_quota (Gtk.Widget widget, Json.Array? windows, int64 now_unix) {
            return Presentation.account_quota_markup (windows, now_unix,
                quota_theme_color (widget, "success_color", "#2e7d32"),
                quota_theme_color (widget, "warning_color", "#a66300"),
                quota_theme_color (widget, "error_color", "#c6262e"));
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
            if (email.length == 0 && provider == "opencodego") {
                for (uint i = 0; opencode_accounts != null && i < opencode_accounts.get_length (); i++) {
                    var account = opencode_accounts.get_object_element (i);
                    if (account.get_boolean_member_with_default ("active", false)) {
                        email = account.get_string_member_with_default ("email", "");
                        break;
                    }
                }
            }
            return email;
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

            var group = new Gtk.Box (Gtk.Orientation.VERTICAL, 1);
            var row = new Gtk.Box (Gtk.Orientation.HORIZONTAL, 6);
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
                xalign = 1, width_request = 58
            };
            percent.add_css_class ("numeric");
            if (level == QuotaLevel.LOW) percent.add_css_class ("text-low");
            if (level == QuotaLevel.CRITICAL) percent.add_css_class ("text-critical");
            row.append (percent);
            var reset_label = new Gtk.Label (compact_reset (reset)) { xalign = 1, width_request = 46 };
            reset_label.add_css_class ("caption");
            reset_label.add_css_class ("dim-label");
            reset_label.add_css_class ("numeric");
            reset_label.set_tooltip_text (reset);
            row.append (reset_label);
            group.append (row);

            // The forecast only gets its own line when it is a warning; otherwise the reset sits inline.
            if (!known || eta.state == EtaState.EXHAUSTED || eta.state == EtaState.DEPLETING) {
                var caption_text = known ? Presentation.window_caption (reset, eta.state, eta.detail)
                    : "Usage not reported yet";
                var caption = new Gtk.Label (caption_text) { xalign = 0, wrap = true, margin_start = 40 };
                caption.add_css_class ("caption");
                caption.add_css_class (eta.state == EtaState.EXHAUSTED ? "text-critical" :
                    eta.state == EtaState.DEPLETING ? "text-low" : "dim-label");
                group.append (caption);
            }

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
            panel_entries = null;
            show_panel_placeholder ();
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
