/* CodexBar quota indicator for Pantheon's Wingpanel. */
using GLib;
using Gtk;
using Json;
using Wingpanel;

namespace MSeries {
    public class CodexBarIndicator : Wingpanel.Indicator {
        private Gtk.Box panel_segments;
        private string panel_digest = "";
        private PanelPreferences display_preferences = new PanelPreferences ();
        private FileMonitor? preferences_monitor;
        private uint preferences_reload_source = 0;
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
        private bool popover_open = false;
        private uint snapshot_tick = 0;
        private bool sessions_in_flight = false;
        private bool snapshot_busy = false;
        private bool snapshot_stale = false;
        private uint refresh_poll_count = 0;
        private bool refresh_after_snapshot = false;
        private RefreshPolicy refresh_policy = new RefreshPolicy ();

        // The popover is rebuilt only when the data it shows changes, so an open
        // popover never flickers and the five-second poll stays cheap.
        private string last_digest = "";
        private uint cached_repaint_source = 0;
        private int64 newest_update_unix = 0;
        private Json.Array? local_sessions = null;
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
        private bool opencode_force_pending = false;
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
            panel_segments = new Gtk.Box (Gtk.Orientation.HORIZONTAL, 8);
            panel_segments.add_css_class ("mseries-codexbar-bar");
            panel_display = new Gtk.Box (Gtk.Orientation.HORIZONTAL, 0);
            panel_display.append (panel_segments);
            show_panel_placeholder ();
            set_panel_summary ("CodexBar · loading usage… · Middle-click to refresh");
            var refresh_gesture = new Gtk.GestureClick () { button = 2 };
            refresh_gesture.released.connect (() => refresh_usage (true));
            panel_display.add_controller (refresh_gesture);
            this.visible = true;

            menu = new Gtk.Box (Gtk.Orientation.VERTICAL, 6) {
                margin_top = 8,
                margin_bottom = 5,
                margin_start = 6,
                margin_end = 6,
                width_request = 300
            };
            menu.add_css_class ("mseries-codexbar");
            install_style (menu.get_display ());
            watch_display_preferences ();

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
            refresh_button.clicked.connect (() => refresh_usage (true));

            // Three pages keep every section above the fold; Quota is the default.
            quota_box = new Gtk.Box (Gtk.Orientation.VERTICAL, 6);
            sessions_box = new Gtk.Box (Gtk.Orientation.VERTICAL, 6);
            spend_box = new Gtk.Box (Gtk.Orientation.VERTICAL, 6);
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
                max_content_height = 300
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
            actions.append (make_dock_button ("Settings", "preferences-system-symbolic", "--settings"));
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

            // Read the snapshot every 5 s while the popover is open or a refresh runs; every 30 s otherwise,
            // which is plenty for the panel-bar chip.
            Timeout.add_seconds (5, () => {
                snapshot_tick++;
                if (popover_open || snapshot_busy || refresh_poll_source != 0 || snapshot_tick % 6 == 0) {
                    read_snapshot.begin ();
                }
                return Source.CONTINUE;
            });
        }

        private void watch_display_preferences () {
            try {
                var directory = File.new_for_path (GLib.Path.build_filename (Environment.get_user_config_dir (), "codexbar"));
                preferences_monitor = directory.monitor_directory (FileMonitorFlags.NONE);
                preferences_monitor.changed.connect ((file, other_file, event) => {
                    if (file.get_basename () != "wingpanel.json" &&
                        (other_file == null || other_file.get_basename () != "wingpanel.json")) return;
                    if (preferences_reload_source != 0) Source.remove (preferences_reload_source);
                    preferences_reload_source = Timeout.add (100, () => {
                        preferences_reload_source = 0;
                        reload_display_preferences ();
                        return Source.REMOVE;
                    });
                });
            } catch (Error e) {
                // Also reload on ordinary snapshot reads if the config directory did not exist yet.
            }
        }

        private void reload_display_preferences () {
            if (!display_preferences.load ()) return;
            panel_digest = "";
            last_digest = "";
            if (panel_entries != null) {
                var now = new DateTime.now_utc ().to_unix ();
                update_panel (panel_entries, now);
                render_quota (panel_entries, now);
            }
        }

        private static void install_style (Gdk.Display display) {
            var style = new Gtk.CssProvider ();
            style.load_from_string (
                ".mseries-codexbar { font-size: 8pt; } " +
                ".mseries-codexbar .caption { font-size: 7pt; } " +
                ".mseries-codexbar .provider-title { font-weight: 700; font-size: 8.5pt; } " +
                ".mseries-codexbar .window-name { font-weight: 700; } " +
                ".mseries-codexbar .numeric { font-feature-settings: \"tnum\"; } " +
                ".mseries-codexbar .card { padding: 5px 8px; border-radius: 8px; background: alpha(currentColor, 0.06); } " +
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
                ".mseries-codexbar button { padding: 2px 5px; } " +
                ".mseries-codexbar .mseries-dock { padding: 3px; border-radius: 12px; background: alpha(currentColor, 0.06); } " +
                ".mseries-codexbar .mseries-bar { margin-top: 2px; } " +
                ".mseries-codexbar .mseries-dock button { padding: 5px 9px; border-radius: 9px; min-height: 0; } " +
                ".mseries-codexbar .mseries-dock button:hover { background: alpha(currentColor, 0.1); } " +
                ".mseries-codexbar .account-line { min-height: 0; } " +
                ".mseries-codexbar .account-name { font-size: 8pt; } " +
                ".mseries-codexbar .account-meta { font-size: 7pt; } " +
                ".mseries-codexbar .account-line button { padding: 2px 8px; min-height: 0; } " +
                ".mseries-codexbar .provider-mark { opacity: 0.9; } " +
                ".mseries-codexbar .mark-claude { color: #d97757; opacity: 1; } " +
                ".mseries-codexbar button.compact { padding: 1px 8px; min-height: 0; min-width: 0; } " +
                ".mseries-codexbar button.flat.compact { padding: 0 4px; } " +
                ".mseries-codexbar .mseries-switcher button { padding: 2px 6px; } " +
                ".mseries-codexbar-bar label { font-size: 7.5pt; font-feature-settings: \"tnum\"; } " +
                ".mseries-codexbar-bar .seg-value { font-weight: 700; } " +
                ".mseries-codexbar-bar .seg-reset { font-size: 6.5pt; opacity: 0.7; } " +
                ".mseries-codexbar-bar .seg-secondary { font-size: 6.5pt; } " +
                ".mseries-codexbar-bar .level-low { color: @warning_color; } " +
                ".mseries-codexbar-bar .level-critical { color: @error_color; } " +
                ".mseries-codexbar-bar .provider-mark { opacity: 0.92; } " +
                ".mseries-codexbar-bar .seg-divider { min-width: 1px; margin: 4px 0; background: alpha(currentColor, 0.22); } " +
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

        // A click on Refresh bypasses the helpers' caches; the automatic refresh on open does not.
        private void refresh_usage (bool force = false) {
            refresh_claude.begin (force);
            refresh_codex_accounts.begin (force);
            refresh_opencode_accounts.begin (force);
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
            // Poll fallback also covers replacing/deleting the monitored directory itself.
            reload_display_preferences ();
            if (preferences_monitor == null) watch_display_preferences ();
            refresh_after_snapshot = refresh_after_snapshot || refresh_if_old;
            if (request_in_flight) {
                return;
            }
            request_in_flight = true;

            try {
                var stdout_text = yield HelperProcess.read ({ executable, "--snapshot" }, 5000);
                if (stdout_text.strip ().length == 0) {
                    show_unavailable ("dialog-warning-symbolic", "CodexBar isn't running", "Start CodexBar and sign in to see your quota.");
                    ensure_sessions (60);
                    return;
                }

                var parser = new Json.Parser ();
                parser.load_from_data (stdout_text, -1);
                var root = parser.get_root ();
                JsonBoundary.validate (root);
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
            var entries = JsonBoundary.array (snapshot, "entries");
            if (entries != null) {
                for (uint i = 0; i < entries.get_length (); i++) {
                    var entry = entries.get_object_element (i);
                    var updated = JsonBoundary.text (entry, "updatedAt", "");
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
            return refresh_policy.should_refresh_on_open (JsonBoundary.flag (snapshot, "busy"),
                oldest_update_unix, new DateTime.now_utc ().to_unix (), GLib.get_monotonic_time ());
        }

        // Helper refreshes (sessions, Claude, Codex accounts, OpenCode) run when the popover is open. With it closed
        // they refresh on a slow background tick; local token totals use the same cached cadence.
        private const int BACKGROUND_SECONDS = 900;

        private bool due (int64 fetched_us, int open_seconds) {
            var limit = popover_open ? open_seconds : BACKGROUND_SECONDS;
            return fetched_us == 0 || GLib.get_monotonic_time () - fetched_us > limit * GLib.TimeSpan.SECOND;
        }

        private void ensure_sessions (int max_age_seconds) {
            if (due (sessions_fetched_us, max_age_seconds)) {
                refresh_sessions.begin ();
            }
            if (due (claude_fetched_us, 120)) {
                refresh_claude.begin ();
            }
            if (due (codex_accounts_fetched_us, 300)) {
                refresh_codex_accounts.begin ();
            }
            if (due (opencode_accounts_fetched_us, 120)) {
                refresh_opencode_accounts.begin ();
            }
            if (due (opencode_local_fetched_us, max_age_seconds)) {
                refresh_opencode_local.begin ();
            }
        }

        private static string helper_path (string name) {
            return GLib.Path.build_filename (Environment.get_home_dir (), ".local", "lib", "codexbar-cli", name);
        }

        // Upstream's Codex account switching is macOS-only; our helper keeps one saved sign-in per account.
        private async void refresh_codex_accounts (bool force = false) {
            if (codex_accounts_in_flight) {
                return;
            }
            codex_accounts_in_flight = true;
            var before = codex_accounts_digest (codex_accounts);
            try {
                string[] command = { "python3", helper_path ("codexbar-accounts.py"), "usage" };
                if (force) {
                    command += "--force";
                }
                var stdout_text = yield HelperProcess.read (command, 120000);
                Json.Array? parsed = null;
                if (stdout_text.strip ().length > 0) {
                    var parser = new Json.Parser ();
                    parser.load_from_data (stdout_text, -1);
                    var root = parser.get_root ();
                    JsonBoundary.validate (root);
                    if (root != null && root.get_node_type () == Json.NodeType.OBJECT) {
                        var list = JsonBoundary.array (root.get_object (), "accounts");
                        parsed = list != null ? list.ref () : null;
                    }
                }
                // A helper that failed to answer must not wipe what the panel already shows.
                codex_accounts = parsed;
            } catch (Error e) {
                // keep the last good list
            } finally {
                codex_accounts_in_flight = false;
                codex_accounts_fetched_us = GLib.get_monotonic_time ();
            }
            if (codex_accounts_digest (codex_accounts) != before) {
                repaint_cached_quota ();
            }
        }

        // Claude accounts come from claude-swap (cswap), the same tool upstream CodexBar drives on macOS.
        private async void refresh_claude (bool force = false) {
            if (claude_in_flight) {
                return;
            }
            claude_in_flight = true;
            var before = local_digest (claude_data);
            try {
                string[] command = { "python3", helper_path ("codexbar-claude.py"), "list" };
                if (force) {
                    command += "--force";
                }
                var stdout_text = yield HelperProcess.read (command, 120000);
                Json.Object? parsed = null;
                if (stdout_text.strip ().length > 0) {
                    var parser = new Json.Parser ();
                    parser.load_from_data (stdout_text, -1);
                    var root = parser.get_root ();
                    JsonBoundary.validate (root);
                    if (root != null && root.get_node_type () == Json.NodeType.OBJECT
                        && JsonBoundary.flag (root.get_object (), "available", false)) {
                        parsed = root.get_object ().ref ();
                    }
                }
                claude_data = parsed;
            } catch (Error e) {
                // keep the last good list
            } finally {
                claude_in_flight = false;
                claude_fetched_us = GLib.get_monotonic_time ();
            }
            if (local_digest (claude_data) != before) {
                repaint_cached_quota ();
            }
        }

        private async void refresh_opencode_accounts (bool force = false) {
            if (opencode_accounts_in_flight) {
                opencode_force_pending = opencode_force_pending || force;
                return;
            }
            opencode_accounts_in_flight = true;
            var generation = opencode_generation;
            var before = codex_accounts_digest (opencode_accounts);
            try {
                string[] command = { "python3", helper_path ("codexbar-opencode-local.py"), "accounts" };
                if (force) command += "--force";
                var output = yield HelperProcess.read (command, 120000);
                var parser = new Json.Parser ();
                parser.load_from_data (output);
                var root = parser.get_root ();
                JsonBoundary.validate (root);
                if (generation != opencode_generation) return;
                opencode_accounts = null;
                if (root != null && root.get_node_type () == Json.NodeType.OBJECT
                    && root.get_object ().has_member ("accounts")) {
                    var accounts = JsonBoundary.array (root.get_object (), "accounts");
                    if (accounts != null) opencode_accounts = accounts.ref ();
                }
            } catch (Error e) {
                if (generation == opencode_generation) opencode_accounts = null;
            } finally {
                opencode_accounts_in_flight = false;
                opencode_accounts_fetched_us = generation == opencode_generation ? GLib.get_monotonic_time () : 0;
                if (opencode_force_pending || generation != opencode_generation) {
                    var force_next = opencode_force_pending;
                    opencode_force_pending = false;
                    refresh_opencode_accounts.begin (force_next);
                }
            }
            if (before != codex_accounts_digest (opencode_accounts)) {
                repaint_cached_quota ();
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
                JsonBoundary.validate (root);
                if (root != null && root.get_node_type () == Json.NodeType.OBJECT) {
                    ok = process.get_successful () && JsonBoundary.flag (root.get_object (), "ok", false);
                    message = JsonBoundary.text (root.get_object (), "message", message);
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
                ? "Claude will save a work handoff, close and reopen with this account, and Claude Code's command-line login will change too. Missing local Code conversations will carry over with their workspace context. Finish running work first. CodexBar stays running."
                : "This account needs one sign-in in the Claude app before fast switching works. Claude will reopen at its sign-in screen. Sign in to the account shown above, then reopen CodexBar to save it. Missing local Code conversations will carry over. Finish running work first.";
            dialog.buttons = { "Cancel", ready ? "Switch Claude account" : "Set up app sign-in" };
            dialog.cancel_button = 0;
            dialog.default_button = 0;
            dialog.modal = false;
            dialog.choose.begin (null, null, (obj, res) => {
                try {
                    if (dialog.choose.end (res) == 1) {
                        if (ready) {
                            switch_claude_account.begin (number, true);
                        } else {
                            run_saver.begin ({ "python3", helper_path ("codexbar-claude.py"), "app-login", number },
                                "Sign in to the Claude app", "Couldn't set up the app login", true);
                        }
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
            var handoff_ready = false;
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
                    JsonBoundary.validate (root);
                    if (root != null && root.get_node_type () == Json.NodeType.OBJECT) {
                        ok = process.get_successful () && JsonBoundary.flag (root.get_object (), "ok", false);
                        message = JsonBoundary.text (root.get_object (), "message", "");
                        handoff_ready = JsonBoundary.flag (root.get_object (), "handoffReady", false);
                    }
                } catch (Error e) {
                    message = (stderr_text ?? "").strip ();
                }
            } catch (Error e) {
                message = e.message;
            }
            claude_switch_in_flight = false;
            tell (ok ? "Switched Claude account" : "Couldn't switch Claude account",
                message.length > 0 ? message : "The helper reported an error.", ok && handoff_ready);
            claude_fetched_us = 0;
            last_digest = "";
            refresh_claude.begin ();
            read_snapshot.begin ();
        }

        private void tell (string heading, string detail, bool handoff_review = false) {
            var dialog = new Granite.MessageDialog.with_image_from_icon_name (heading, detail,
                "dialog-information", Gtk.ButtonsType.CLOSE);
            if (handoff_review) dialog.add_button ("Review GitHub handoff…", Gtk.ResponseType.APPLY);
            dialog.response.connect ((response) => {
                dialog.close ();
                if (handoff_review && response == Gtk.ResponseType.APPLY) {
                    try {
                        Process.spawn_async (null, { "python3", helper_path ("codexbar-claude.py"), "handoff-review" },
                            null, SpawnFlags.SEARCH_PATH, null, null);
                    } catch (Error e) { tell ("Could not open handoff review", "Run codexbar-claude.py handoff-review to retry."); }
                }
            });
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

        /* Clicking a provider's card opens its desktop app, or brings it forward when it is already running
         * (these Electron apps are single-instance, so relaunching hands focus to the open window). Buttons inside
         * the card claim their own clicks first. */
        private static string? desktop_id_for (string provider) {
            switch (provider) {
                case "codex": return "chatgpt.desktop";
                case "claude": return "com.anthropic.Claude.desktop";
                case "opencodego": return "ai.opencode.desktop.dev.desktop";
                default: return null;
            }
        }

        private static string? grok_binary () {
            var found = Environment.find_program_in_path ("grok");
            if (found != null) return found;
            foreach (var relative in new string[] { ".grok/bin/grok", ".local/bin/grok" }) {
                var candidate = GLib.Path.build_filename (Environment.get_home_dir (), relative);
                if (FileUtils.test (candidate, FileTest.IS_EXECUTABLE)) return candidate;
            }
            return null;
        }

        /* Grok Build is a terminal program: its card opens it, and its sign-in runs `grok login`, in the
         * default terminal (xdg-terminal-exec, installed with CodexBar). Null when either is missing. */
        private static GLib.AppInfo? terminal_app_for (string provider, string[] arguments = {}) {
            if (provider != "grok") return null;
            var terminal = Environment.find_program_in_path ("xdg-terminal-exec");
            var grok = grok_binary ();
            if (terminal == null || grok == null) return null;
            var command = new StringBuilder (Shell.quote (terminal));
            command.append (" " + Shell.quote (grok));
            foreach (var argument in arguments) command.append (" " + Shell.quote (argument));
            try {
                return GLib.AppInfo.create_from_commandline (command.str, "Grok Build", GLib.AppInfoCreateFlags.NONE);
            } catch (Error e) {
                return null;
            }
        }

        private void open_desktop_app (string provider, Gtk.Widget from, string[] arguments = {}) {
            var id = desktop_id_for (provider);
            GLib.AppInfo? app = null;
            if (id != null) {
                app = new GLib.DesktopAppInfo (id);
            } else {
                app = terminal_app_for (provider, arguments);
            }
            if (app == null) {
                subtitle_label.set_text (provider == "grok" ? "Grok Build or a terminal (xdg-terminal-exec) isn't installed"
                    : "%s isn't installed as a desktop app".printf (provider_title (provider)));
                return;
            }
            popdown_from (from);
            try {
                app.launch (null, Gdk.Display.get_default ().get_app_launch_context ());
            } catch (Error e) {
                subtitle_label.set_text ("Could not open %s: %s".printf (provider_title (provider), e.message));
            }
        }

        private void open_app_on_click (Gtk.Widget card, string provider) {
            if (desktop_id_for (provider) == null && terminal_app_for (provider) == null) {
                return;
            }
            var click = new Gtk.GestureClick () { button = 1 };
            click.released.connect ((presses, x, y) => open_desktop_app (provider, card));
            card.add_controller (click);
            card.set_cursor_from_name ("pointer");
        }

        private Gtk.Widget build_claude_card (int64 now_unix) {
            var card = new Gtk.Box (Gtk.Orientation.VERTICAL, 6);
            card.add_css_class ("card");
            open_app_on_click (card, "claude");
            var head = new Gtk.Box (Gtk.Orientation.HORIZONTAL, 6);
            var dot = new Gtk.Label ("●");
            dot.add_css_class ("dot-off");
            head.append (dot);
            head.append (build_provider_mark ("claude", "Claude"));
            head.append (build_hint_badges ("claude", true));
            var email = JsonBoundary.text (claude_data, "activeEmail", "");
            var accounts = JsonBoundary.array (claude_data, "accounts");
            head.append (build_identity (email, JsonBoundary.text (claude_data, "activePlan", "")));
            head.append (build_add_account_button ("Sign in to Claude Code, then save that login with claude-swap",
                () => add_claude_account ()));
            card.append (head);
            append_weekly_tokens (card, "claude");
            // CLI and desktop can be switched separately; always name both when they differ.
            var desktop = claude_data.has_member ("desktop") ? JsonBoundary.object_member (claude_data, "desktop") : null;
            if (desktop != null && JsonBoundary.flag (desktop, "differs", false)) {
                var there = JsonBoundary.text (desktop, "email", "");
                var note = subtle_label ("Claude app: %s".printf (
                    there.length > 0 ? there : "another account"));
                note.set_tooltip_text (JsonBoundary.text (claude_data, "desktopNote", ""));
                card.append (note);
            }
            var snapshot_error = JsonBoundary.text (claude_data, "desktopSnapshotError", "");
            if (snapshot_error.length > 0) card.append (subtle_label (snapshot_error));

            var shown_quota = false;
            if (accounts != null) {
                for (uint i = 0; i < accounts.get_length (); i++) {
                    var account = accounts.get_object_element (i);
                    var windows = JsonBoundary.array (account, "windows");
                    if (JsonBoundary.flag (account, "active", false) && windows != null) {
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
            // The helper saves the Claude app's login by itself whenever it lists accounts, so a standing
            // button is noise. Offer it only when the app's current login is not one of the saved accounts.
            var app_installed = desktop != null && JsonBoundary.flag (desktop, "installed", false);
            var app_login_saved = false;
            for (uint i = 0; i < listed; i++) {
                if (JsonBoundary.flag (accounts.get_object_element (i), "desktopActive", false)) {
                    app_login_saved = true;
                }
            }
            if (app_installed && (!app_login_saved || snapshot_error.length > 0)) {
                var save_app = new Gtk.Button.with_label ("Save Claude app login") {
                    halign = Gtk.Align.START, tooltip_text = "The Claude app's current sign-in isn't saved yet. Save it for fast switching."
                };
                save_app.add_css_class ("flat");
                save_app.add_css_class ("caption");
                save_app.clicked.connect (() => {
                    popdown_from (save_app);
                    run_saver.begin ({ "python3", helper_path ("codexbar-claude.py"), "app-save" },
                        "Claude app login saved", "Couldn't save the app login", true);
                });
                card.append (save_app);
            }
            for (uint i = 0; i < listed; i++) {
                var account = accounts.get_object_element (i);
                if (JsonBoundary.flag (account, "active", false) &&
                    (desktop == null || !JsonBoundary.flag (desktop, "installed", false) ||
                     JsonBoundary.flag (account, "desktopActive", false))) {
                    continue;
                }
                var number = JsonBoundary.integer (account, "number", 0).to_string ();
                var name = JsonBoundary.text (account, "email", "");
                var windows = JsonBoundary.array (account, "windows");
                var detail = "Quota unavailable";
                var ready = JsonBoundary.flag (account, "desktopReady", false);
                var installed = desktop != null && JsonBoundary.flag (desktop, "installed", false);
                if (installed && !ready) detail += " · app sign-in needed";
                card.append (build_account_line (name, detail,
                    "Choose whether to switch Claude Code or the Claude app and CLI to %s".printf (name),
                    () => choose_claude_switch (number, name, installed, ready), windows, hint_id ("claude", account), JsonBoundary.text (account, "plan", "")));
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

        /* Switch always answers on screen: success names the account, failure says why. Silence looked like "nothing happened". */
        private void choose_codex_switch (owned string account_id) {
            if (codex_switch_in_flight) return;
            var email = account_id.split ("|")[0];
            var dialog = new Gtk.AlertDialog ("Switch ChatGPT to %s?", email);
            dialog.detail = "ChatGPT will close and reopen with this account. Finish running work first; unsaved drafts may be lost. CodexBar stays running.";
            dialog.buttons = { "Cancel", "Switch account" };
            dialog.cancel_button = 0;
            dialog.default_button = 0;
            dialog.choose.begin (null, null, (obj, res) => {
                try {
                    if (dialog.choose.end (res) == 1 && !codex_switch_in_flight) {
                        switch_codex_account.begin (account_id);
                    }
                } catch (Error e) { }
            });
        }

        private bool codex_switch_in_flight = false;

        private async void switch_codex_account (owned string account_id) {
            if (codex_switch_in_flight) return;
            codex_switch_in_flight = true;
            var ok = false;
            var message = "";
            try {
                string[] command = { "python3", helper_path ("codexbar-accounts.py"), "switch", account_id, "--desktop" };
                var process = new GLib.Subprocess.newv (command, SubprocessFlags.STDOUT_PIPE | SubprocessFlags.STDERR_MERGE);
                string output;
                yield process.communicate_utf8_async (null, null, out output, null);
                ok = process.get_successful ();
                try {
                    var parser = new Json.Parser ();
                    parser.load_from_data (output.strip (), -1);
                    var root = parser.get_root ();
                    JsonBoundary.validate (root);
                    if (root == null || root.get_node_type () != Json.NodeType.OBJECT) {
                        ok = false;
                        message = "The account helper returned an invalid response.";
                    } else {
                        var response = root.get_object ();
                        ok = ok && JsonBoundary.flag (response, "ok", false);
                        message = JsonBoundary.text (response, "message", "");
                    }
                } catch (Error e) {
                    ok = false;
                    message = "The account helper returned an invalid response.";
                }
            } catch (Error e) {
                message = e.message;
            }
            codex_switch_in_flight = false;
            // The active account changed (or didn't): re-read quota and the account list from scratch.
            codex_accounts_fetched_us = 0;
            last_digest = "";
            run_action ("--refresh");
            refresh_codex_accounts.begin (true);
            read_snapshot.begin ();
            if (!ok) {
                tell ("Couldn't switch Codex account", message.length > 0 ? message : "The helper reported an error.");
                return;
            }
            tell ("Switched ChatGPT account", message);
        }

        /* A small native confirm dialog; used for the ChatGPT restart offer after a Codex switch. */
        private void ask_to_save (string heading, string detail, string save_label, owned ActionFunc on_save) {
            var dialog = new Gtk.AlertDialog ("%s", heading);
            dialog.detail = detail;
            dialog.buttons = { "Cancel", save_label };
            dialog.cancel_button = 0;
            dialog.default_button = 1;
            dialog.modal = false;
            dialog.choose.begin (null, null, (obj, res) => {
                try {
                    if (dialog.choose.end (res) == 1) {
                        on_save ();
                    }
                } catch (Error e) {
                    // dismissed
                }
            });
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
            if (codex_accounts == null) {
                return box;
            }
            for (uint i = 0; i < codex_accounts.get_length (); i++) {
                var account = codex_accounts.get_object_element (i);
                if (JsonBoundary.flag (account, "active", false)) {
                    continue;
                }
                var email = JsonBoundary.text (account, "email", "");
                var account_id = JsonBoundary.text (account, "id", email);
                var windows = account.has_member ("windows") ? JsonBoundary.array (account, "windows") : null;
                var detail = account.has_member ("error") ? "unavailable" : "—";
                var resets = account.has_member ("resetCredits") ? JsonBoundary.object_member (account, "resetCredits") : null;
                box.append (build_account_line (email, detail,
                    "Close and reopen ChatGPT with %s. CodexBar stays running.".printf (email)
                        + (JsonBoundary.flag (account, "stale", false)
                            ? "\n\nShowing the previous quota: the latest refresh failed." : ""),
                    () => choose_codex_switch (account_id), windows, hint_id ("codex", account), JsonBoundary.text (account, "plan", ""), true, resets));
            }
            return box;
        }

        /* Available resets for a Codex account as a one-row chip, with when the first expires; red inside the last day. */
        private Gtk.Label build_reset_credits (Json.Object credits, int64 now_unix) {
            var available = JsonBoundary.integer (credits, "available", -1);
            var expires = JsonBoundary.text (credits, "nextExpiresAt", "");
            var when = expires.length > 0 ? new GLib.DateTime.from_iso8601 (expires, null) : null;
            var seconds = when != null ? when.to_unix () - now_unix : 0;
            var chip = new Gtk.Label (Presentation.reset_credits_chip (available, seconds)) { valign = Gtk.Align.CENTER };
            chip.add_css_class ("caption");
            chip.add_css_class ("numeric");
            chip.add_css_class (Presentation.reset_expiry_urgent (available, seconds) ? "text-critical" : "dim-label");
            chip.set_tooltip_text (Presentation.reset_credits_line (available, seconds));
            return chip;
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
                var stdout_text = yield HelperProcess.read ({ "python3", helper });
                Json.Object? parsed = null;
                if (stdout_text.strip ().length > 0) {
                    var parser = new Json.Parser ();
                    parser.load_from_data (stdout_text, -1);
                    var root = parser.get_root ();
                    JsonBoundary.validate (root);
                    if (root != null && root.get_node_type () == Json.NodeType.OBJECT
                        && (JsonBoundary.text (root.get_object (), "status", "") == "available"
                            || JsonBoundary.text (root.get_object (), "accountEmail", "").length > 0)) {
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
                repaint_cached_quota ();
            }
        }

        private async void refresh_sessions () {
            if (sessions_in_flight) {
                return;
            }
            sessions_in_flight = true;
            var before_tokens = weekly_tokens_digest ();
            var helper = GLib.Path.build_filename (Environment.get_home_dir (), ".local", "lib",
                "codexbar-cli", "codexbar-sessions.py");
            try {
                var stdout_text = yield HelperProcess.read ({ "python3", helper });
                if (stdout_text.strip ().length == 0) {
                    sessions_error = "The session check couldn't run. Reinstall the CodexBar panel.";
                } else {
                    var parser = new Json.Parser ();
                    parser.load_from_data (stdout_text);
                    JsonBoundary.validate (parser.get_root ());
                    var parsed = JsonBoundary.array (parser.get_root ().get_object (), "sessions");
                    if (parsed == null) throw new IOError.INVALID_DATA ("Missing local session data");
                    local_sessions = parsed.ref ();
                    sessions_error = "";
                }
            } catch (Error e) {
                sessions_error = "The session check is unavailable: " + e.message;
            } finally {
                sessions_in_flight = false;
                sessions_fetched_us = GLib.get_monotonic_time ();
                render_sessions ();
                // Repaint cached panel data immediately; never request another provider poll.
                if (panel_entries != null) update_panel (panel_entries, new DateTime.now_utc ().to_unix ());
                if (before_tokens != weekly_tokens_digest ()) repaint_cached_quota ();
            }
        }

        private string weekly_tokens_digest () {
            var digest = new StringBuilder ();
            foreach (var provider in TOKEN_PROVIDERS) digest.append (local_week_tokens (provider) + "|");
            return digest.str;
        }

        private void repaint_cached_quota () {
            if (cached_repaint_source != 0) return;
            cached_repaint_source = Idle.add (() => {
                cached_repaint_source = 0;
                if (panel_entries != null) {
                    var now = new DateTime.now_utc ().to_unix ();
                    var previous_digest = last_digest;
                    update_account_hints (panel_entries, now);
                    update_panel (panel_entries, now);
                    render_quota (panel_entries, now);
                    // This repaint already applied helper/hint invalidations; an unchanged
                    // scheduled snapshot must not rebuild the same cards a second time.
                    last_digest = previous_digest;
                }
                return Source.REMOVE;
            });
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
            text.append ("|%s|%s".printf (snapshot_stale.to_string (), JsonBoundary.flag (snapshot, "busy").to_string ()));
            var entries = JsonBoundary.array (snapshot, "entries");
            if (entries != null) {
                for (uint i = 0; i < entries.get_length (); i++) {
                    text.append (QuotaEta.entry_stale (entries.get_object_element (i), snapshot_stale, now_unix) ? "S" : "F");
                }
            }
            return GLib.Checksum.compute_for_string (GLib.ChecksumType.MD5, text.str);
        }

        private void update_snapshot (Json.Object snapshot) {
            var now_unix = new DateTime.now_utc ().to_unix ();
            snapshot_stale = JsonBoundary.flag (snapshot, "stale");
            snapshot_busy = JsonBoundary.flag (snapshot, "busy");
            var entries = JsonBoundary.array (snapshot, "entries");
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
                var timestamp = new DateTime.from_iso8601 (JsonBoundary.text (entries.get_object_element (i), "updatedAt", ""), null);
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

        /* Known providers first (Codex, Claude, OpenCode Go, Grok); anything else upstream reports follows. */
        private const int LAST_PROVIDER_RANK = 4;
        private const string[] TOKEN_PROVIDERS = { "codex", "claude", "opencodego", "grok" };

        private static int provider_rank (string provider) {
            return provider == "codex" ? 0 : provider == "claude" ? 1 : provider == "opencodego" ? 2
                : provider == "grok" ? 3 : LAST_PROVIDER_RANK;
        }

        private static string hint_id (string provider, Json.Object account) {
            if (JsonBoundary.flag (account, "active", false)) return provider + ":active";
            var key = JsonBoundary.text (account, "id", "");
            if (key.length == 0 && account.has_member ("number")) key = JsonBoundary.integer (account, "number").to_string ();
            if (key.length == 0) key = JsonBoundary.text (account, "email", "unknown");
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
                var provider = JsonBoundary.text (entry, "provider", "").down ();
                supplied += provider;
                hint_candidate (hint_candidates, provider + ":active", account_email_for (provider, entry),
                    JsonBoundary.array (entry, "windows"), QuotaEta.entry_stale (entry, snapshot_stale, now_unix)
                    || JsonBoundary.text (entry, "error", "").length > 0);
            }
            foreach (var provider in new string[] { "codex", "claude", "opencodego" }) {
                var accounts = provider_accounts (provider);
                var fetched = provider == "codex" ? codex_accounts_fetched_us
                    : provider == "claude" ? claude_fetched_us : opencode_accounts_fetched_us;
                var max_age = (provider == "codex" ? 600 : 240) * GLib.TimeSpan.SECOND;
                for (uint i = 0; accounts != null && i < accounts.get_length (); i++) {
                    var account = accounts.get_object_element (i);
                    if (JsonBoundary.flag (account, "active", false) && provider in supplied) continue;
                    hint_candidate (hint_candidates, hint_id (provider, account), JsonBoundary.text (account, "email", ""),
                        account.has_member ("windows") ? JsonBoundary.array (account, "windows") : null,
                        fetched == 0 || GLib.get_monotonic_time () - fetched > max_age || account.has_member ("error"));
                }
            }
            hint_selection = Presentation.account_hints (hint_candidates, now_unix);
            var digest = local_digest (hint_selection);
            for (uint i = 0; i < hint_candidates.get_length (); i++) {
                var candidate = hint_candidates.get_object_element (i);
                digest += JsonBoundary.text (candidate, "id") + JsonBoundary.text (candidate, "email");
            }
            if (digest != hints_digest) {
                hints_digest = digest;
                last_digest = "";
                panel_digest = "";
            }
        }

        private bool has_hint (string kind, string id, bool provider = false) {
            var selected = hint_selection.has_member (kind) ? JsonBoundary.array (hint_selection, kind) : null;
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
                var key = JsonBoundary.text (candidate, "id");
                if (!(provider ? key.has_prefix (id + ":") : key == id) || !has_hint (kind, key)) continue;
                text.append ("\n" + JsonBoundary.text (candidate, "email"));
                if (kind == "weekly") {
                    var reset = Presentation.account_weekly_reset (JsonBoundary.array (candidate, "windows"), new DateTime.now_utc ().to_unix ());
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

        /* The tooltip is for the pointer; assistive tech needs the same summary as the widget's name. */
        private void set_panel_summary (string text) {
            panel_display.set_tooltip_text (text);
            panel_display.update_property (Gtk.AccessibleProperty.LABEL, text.replace ("\n\n", ". ").replace ("\n", ", "), -1);
        }

        private void show_panel_placeholder () {
            panel_digest = "";
            clear (panel_segments);
            var dash = new Gtk.Label ("—");
            dash.add_css_class ("dim-label");
            panel_segments.append (dash);
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
                var minutes = JsonBoundary.integer (candidate, "minutes", 0);
                if (JsonBoundary.text (candidate, "key", "") == "primary" || minutes > 0 && minutes <= 360) {
                    binding = (int) w;
                    break;
                }
            }
            for (uint w = 0; w < windows.get_length (); w++) {
                var window = windows.get_object_element (w);
                var minutes = (int) JsonBoundary.integer (window, "minutes", 0);
                var short_label = Presentation.short_window_label (
                    JsonBoundary.text (window, "label", "Quota"), minutes);
                var node = window.get_member ("remaining");
                if (node == null || node.get_node_type () != Json.NodeType.VALUE) {
                    tooltip.append ("\n  %s  not reported yet".printf (short_label));
                    continue;
                }
                var remaining = node.get_double ();
                var reset = JsonBoundary.text (window, "resetText", "");
                tooltip.append ("\n  %s  %0.0f%% left · %s".printf (short_label, remaining,
                    reset.length > 0 ? reset.down () : "reset unknown"));
                if ((int) w != binding) continue;
                level = Presentation.level_for (remaining);
                value_text = "%s %0.0f%%".printf (short_label, remaining);
                var resets_at = new DateTime.from_iso8601 (JsonBoundary.text (window, "resetsAt", ""), null);
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
                var provider = (JsonBoundary.text (entry, "provider", "")).down ();
                has_claude = has_claude || provider == "claude";
                var windows = JsonBoundary.array (entry, "windows");
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
                            // Keep the primary row compact; local tokens use the lower row when
                            // there is no alternate account, and remain in this tooltip in either case.
                            section.append ("\n  " + local_tokens + " tokens in 7 days");
                        }
                    }
                } else if (provider == "opencodego" && opencode_local != null) {
                    // No account quota without a web sign-in: show this machine's 7-day token count instead.
                    var periods = JsonBoundary.array (opencode_local, "periods");
                    for (uint p = 0; periods != null && p < periods.get_length (); p++) {
                        var period = periods.get_object_element (p);
                        var label = JsonBoundary.text (period, "label", "");
                        var tokens = JsonBoundary.integer (period, "tokens", 0);
                        section.append ("\n  %s".printf (Presentation.local_usage_line (label,
                            JsonBoundary.number (period, "costUSD", 0),
                            JsonBoundary.integer (period, "requests", 0), tokens)));
                        if (label.contains ("7")) {
                            value_text = "Usage";
                            reset_text = "";
                        }
                    }
                    section.append ("\n  Local estimate, not account quota");
                    stale = false;
                } else {
                    var error = JsonBoundary.text (entry, "error", "");
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
                var accounts = JsonBoundary.array (claude_data, "accounts");
                for (uint i = 0; accounts != null && i < accounts.get_length (); i++) {
                    var account = accounts.get_object_element (i);
                    var windows = JsonBoundary.array (account, "windows");
                    if (!JsonBoundary.flag (account, "active", false) || windows == null
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

            foreach (var provider in TOKEN_PROVIDERS) {
                var count = local_week_tokens (provider);
                if (count.length > 0) tooltip.append ("\n\n%s · 7d: %s tokens".printf (provider_title (provider), count));
            }
            set_panel_summary (tooltip.len > 0
                ? tooltip.str + (snapshot_stale ? "\n\nCached: CodexBar couldn't reach a provider." : "")
                    + "\n\nMiddle-click to refresh"
                : "Usage unavailable");

            var digest = new StringBuilder ();
            digest.append (hints_digest);
            foreach (var provider in TOKEN_PROVIDERS)
                digest.append (local_week_tokens (provider) + "|");
            foreach (var provider in TOKEN_PROVIDERS) {
                digest.append (alternate_account_text (provider, now_unix));
                var windows = active_panel_windows (provider);
                if (windows != null) digest.append (colored_account_quota (panel_display, windows, now_unix, true));
            }
            for (int i = 0; i < providers.length; i++) {
                digest.append ("%s|%s|%s|%d|%s;".printf (providers[i], values[i], resets[i], (int) levels[i],
                    stales[i].to_string ()));
            }
            if (digest.str == panel_digest) return;
            panel_digest = digest.str;

            clear (panel_segments);
            for (int rank = 0; rank <= LAST_PROVIDER_RANK; rank++) {
                for (int i = 0; i < providers.length; i++) {
                    if (provider_rank (providers[i]) != rank) continue;
                    if (panel_segments.get_first_child () != null) {
                        var divider = new Gtk.Separator (Gtk.Orientation.VERTICAL);
                        divider.add_css_class ("seg-divider");
                        panel_segments.append (divider);
                    }
                    panel_segments.append (build_panel_segment (providers[i], values[i], resets[i], levels[i], stales[i]));
                }
            }
            if (providers.length == 0) panel_segments.append (new Gtk.Label ("—"));
        }

        private Json.Array? active_panel_windows (string provider) {
            for (uint i = 0; panel_entries != null && i < panel_entries.get_length (); i++) {
                var entry = panel_entries.get_object_element (i);
                if (JsonBoundary.text (entry, "provider").down () == provider) {
                    var windows = JsonBoundary.array (entry, "windows");
                    if (windows != null && windows.get_length () > 0) return windows;
                }
            }
            var accounts = provider_accounts (provider);
            for (uint i = 0; accounts != null && i < accounts.get_length (); i++) {
                var account = accounts.get_object_element (i);
                if (JsonBoundary.flag (account, "active")) return JsonBoundary.array (account, "windows");
            }
            return null;
        }

        private static string quota_reset_tooltip (Json.Object window) {
            var timestamp = new DateTime.from_iso8601 (JsonBoundary.text (window, "resetsAt"), null);
            if (timestamp != null) {
                var seconds = timestamp.to_unix () - new DateTime.now_utc ().to_unix ();
                return seconds <= 0 ? "Reset due now" : "Resets in " + Presentation.countdown_text (seconds);
            }
            var reset = JsonBoundary.text (window, "resetText");
            return reset.length > 0 ? reset : "Reset time unknown";
        }

        private void apply_quota_dot (Gtk.Label label, string caption, double remaining, string reset = "Reset time unknown") {
            if (!display_preferences.get_bool ("compactQuota") || remaining < 0) return;
            var color = quota_theme_color (label, Presentation.dot_color (remaining),
                remaining > 70 ? "#2e7d32" : remaining >= 25 ? "#a66300" : "#c6262e");
            label.remove_css_class ("level-low");
            label.remove_css_class ("level-critical");
            label.use_markup = true;
            var percent = Presentation.dot_percent (remaining);
            if (percent.length > 0) percent = "<span foreground=\"%s\" weight=\"bold\">%s</span>".printf (
                quota_theme_color (label, "error_color", "#c6262e"), Markup.escape_text (percent));
            label.label = "%s <span foreground=\"%s\">●</span>%s".printf (
                Markup.escape_text (caption), color, percent);
            label.tooltip_text = "%s · %g%% remaining · %s".printf (caption, remaining, reset);
        }

        private void apply_primary_quota_dot (Gtk.Label label, string provider) {
            var windows = active_panel_windows (provider);
            if (windows == null || windows.get_length () == 0) return;
            int selected = Presentation.binding_window (windows);
            for (uint i = 0; i < windows.get_length (); i++) {
                var window = windows.get_object_element (i);
                var minutes = JsonBoundary.integer (window, "minutes");
                if (JsonBoundary.text (window, "key") == "primary" || (minutes > 0 && minutes <= 360)) {
                    selected = (int) i;
                    break;
                }
            }
            if (selected < 0) return;
            var window = windows.get_object_element ((uint) selected);
            apply_quota_dot (label, Presentation.short_window_label (JsonBoundary.text (window, "label", "Quota"),
                (int) JsonBoundary.integer (window, "minutes")), JsonBoundary.number (window, "remaining", -1), quota_reset_tooltip (window));
        }

        /* Returns whether the weekly value or its countdown was drawn in the heading. */
        private bool append_weekly_panel_quota (Gtk.Box heading, string provider) {
            var windows = active_panel_windows (provider);
            for (uint i = 0; windows != null && i < windows.get_length (); i++) {
                var window = windows.get_object_element (i);
                if (JsonBoundary.integer (window, "minutes") != 10080) continue;
                var remaining = JsonBoundary.number (window, "remaining", -1);
                if (remaining < 0) return false;
                var value = new Gtk.Label ("· 7D %0.0f%%".printf (remaining));
                value.add_css_class ("seg-value");
                var level = Presentation.level_for (remaining);
                if (level == QuotaLevel.LOW) value.add_css_class ("level-low");
                if (level == QuotaLevel.CRITICAL) value.add_css_class ("level-critical");
                apply_quota_dot (value, "7D", remaining, quota_reset_tooltip (window));
                var shown = false;
                if (display_preferences.get_bool ("showPercent")) {
                    heading.append (value);
                    shown = true;
                }
                if (display_preferences.get_bool ("showReset") && !display_preferences.get_bool ("compactQuota")) {
                    var timestamp = new DateTime.from_iso8601 (JsonBoundary.text (window, "resetsAt"), null);
                    var countdown = timestamp != null
                        ? Presentation.countdown_text (timestamp.to_unix () - new DateTime.now_utc ().to_unix ())
                        : compact_reset (JsonBoundary.text (window, "resetText")).replace (" ", "");
                    if (countdown.length > 0) {
                        var reset = new Gtk.Label (countdown);
                        reset.add_css_class ("seg-reset");
                        heading.append (reset);
                        shown = true;
                    }
                }
                return shown;
            }
            return false;
        }

        private Gtk.Widget build_panel_segment (string provider, string value_text, string reset_text,
                                                       QuotaLevel level, bool stale) {
            var local_tokens = display_preferences.get_bool ("showTokens") ? local_week_tokens (provider) : "";
            var dot_mode = display_preferences.get_bool ("compactQuota");
            var details_on_top = dot_mode || (provider == "codex" || provider == "claude" || provider == "grok") && (local_tokens.length > 0 ||
                ((display_preferences.get_bool ("showPercent") || display_preferences.get_bool ("showReset")) && active_panel_windows (provider) != null));
            var segment = new Gtk.Box (Gtk.Orientation.HORIZONTAL, provider == "opencodego" ? 2 : 3);
            if (provider == "opencodego") segment.add_css_class ("seg-opencode");
            if (stale) segment.add_css_class ("stale");
            var mark = build_provider_mark (provider, provider_title (provider));
            var icon = mark as Gtk.Image;
            if (icon != null) {
                icon.pixel_size = 13;
                icon.valign = Gtk.Align.CENTER;
            }
            var heading = details_on_top ? new Gtk.Box (Gtk.Orientation.HORIZONTAL, 3) : segment;
            var weekly_shown = false;
            if (details_on_top && stale) heading.add_css_class ("stale");
            heading.append (mark);
            if (display_preferences.get_bool ("showHints")) heading.append (build_hint_badges (provider, true));
            if (details_on_top) {
                if (local_tokens.length > 0) {
                    var tokens = new Gtk.Label ("7d · %s tok".printf (local_tokens)) { xalign = 0 };
                    tokens.add_css_class ("seg-value");
                    tokens.tooltip_text = "Tokens processed in seven days";
                    heading.append (tokens);
                }
                if (!dot_mode) weekly_shown = append_weekly_panel_quota (heading, provider);
            }
            var value = new Gtk.Label (value_text) { valign = Gtk.Align.BASELINE_CENTER };
            value.add_css_class ("seg-value");
            if (level == QuotaLevel.LOW) value.add_css_class ("level-low");
            if (level == QuotaLevel.CRITICAL) value.add_css_class ("level-critical");
            apply_primary_quota_dot (value, provider);
            // A provider whose binding window is its weekly one (Grok's credits) already shows it in the
            // token heading; repeating the same value and countdown on the lower row adds nothing.
            var weekly_in_heading = weekly_shown && value_text.has_prefix ("7D ");
            if (display_preferences.get_bool ("showPercent")) {
                if (dot_mode) heading.append (value);
                else if (!weekly_in_heading) segment.append (value);
            } else {
                if (level == QuotaLevel.LOW) mark.add_css_class ("level-low");
                if (level == QuotaLevel.CRITICAL) mark.add_css_class ("level-critical");
            }
            if (dot_mode && !value.get_text ().has_prefix ("7D ")) append_weekly_panel_quota (heading, provider);
            if (display_preferences.get_bool ("showReset") && !dot_mode && reset_text.length > 0 && !weekly_in_heading) {
                var reset = new Gtk.Label (reset_text) { valign = Gtk.Align.BASELINE_CENTER };
                reset.add_css_class ("seg-reset");
                segment.append (reset);
            }
            var alternate = alternate_account_text (provider, new DateTime.now_utc ().to_unix ());
            var show_alternate = display_preferences.get_bool ("showAccounts") && alternate.length > 0;
            if (!details_on_top && !show_alternate && local_tokens.length == 0) return segment;
            var stack = new Gtk.Box (Gtk.Orientation.VERTICAL, 0) { valign = Gtk.Align.CENTER };
            if (provider == "opencodego") stack.add_css_class ("seg-opencode");
            stack.append (heading);
            if (details_on_top && !show_alternate) {
                if (segment.get_first_child () != null) stack.append (segment);
                return stack;
            }
            var label = new Gtk.Label (null) { xalign = 0, use_markup = true };
            label.add_css_class ("seg-secondary");
            if (!show_alternate) {
                label.label = "7d · %s tok".printf (local_tokens);
                label.tooltip_text = "Tokens processed in seven days";
                stack.append (label);
                return stack;
            }
            var markup = new StringBuilder ();
            if (details_on_top && !dot_mode) markup.append ("· ");
            if (!details_on_top && local_tokens.length > 0) markup.append (Markup.escape_text ("7d · %s tok  ·  ".printf (local_tokens)));
            var accounts = provider_accounts (provider);
            for (uint i = 0; accounts != null && i < accounts.get_length (); i++) {
                var account = accounts.get_object_element (i);
                if (JsonBoundary.flag (account, "active", false)) continue;
                if (markup.len > 0) markup.append ("  ");
                var windows = account.has_member ("windows") ? JsonBoundary.array (account, "windows") : null;
                markup.append ("%s%lld: %s".printf ((display_preferences.get_bool ("showHints") ? hint_markup (hint_id (provider, account), label) : ""), JsonBoundary.integer (account, "number", i + 1),
                    windows == null || windows.get_length () == 0 ? "—"
                        : panel_account_quota (label, windows, new DateTime.now_utc ().to_unix ())));
            }
            label.set_markup (markup.str);
            if (details_on_top) {
                segment.append (label);
                stack.append (segment);
            } else {
                stack.append (label);
            }
            stack.set_tooltip_text (alternate_account_tooltip (provider));
            return stack;
        }

        private Json.Array? provider_accounts (string provider) {
            return provider == "codex" ? codex_accounts : provider == "opencodego" ? opencode_accounts
                : provider == "claude" && claude_data != null ? JsonBoundary.array (claude_data, "accounts") : null;
        }

        private string alternate_account_text (string provider, int64 now_unix) {
            var accounts = provider_accounts (provider);
            var text = new StringBuilder ();
            for (uint i = 0; accounts != null && i < accounts.get_length (); i++) {
                var account = accounts.get_object_element (i);
                if (JsonBoundary.flag (account, "active", false)) continue;
                var windows = account.has_member ("windows") ? JsonBoundary.array (account, "windows") : null;
                if (text.len > 0) text.append ("  ");
                text.append ("%lld: %s".printf (JsonBoundary.integer (account, "number", i + 1),
                    windows != null && windows.get_length () > 0 ? Presentation.account_quota (windows, now_unix) : "—"));
            }
            return text.str;
        }

        private string alternate_account_tooltip (string provider) {
            var text = new StringBuilder (provider_title (provider) + " · alternate accounts · % quota left, ↻ reset countdown");
            var accounts = provider_accounts (provider);
            for (uint i = 0; accounts != null && i < accounts.get_length (); i++) {
                var account = accounts.get_object_element (i);
                if (JsonBoundary.flag (account, "active", false)) continue;
                text.append ("\n%lld: %s".printf (JsonBoundary.integer (account, "number", i + 1),
                    JsonBoundary.text (account, "email", "Saved account")));
                var windows = JsonBoundary.array (account, "windows");
                if (windows != null) text.append (" · " + Presentation.account_quota (windows, new DateTime.now_utc ().to_unix ()));
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
                provider == "opencodego" ? "OpenCode Go" :
                provider == "grok" ? "Grok" : provider;
        }

        private void render_quota (Json.Array entries, int64 now_unix) {
            account_quota_labels = {};
            account_quota_windows = {};
            clear (quota_box);
            var has_claude = false;
            for (uint i = 0; i < entries.get_length (); i++) {
                has_claude = has_claude || JsonBoundary.text (entries.get_object_element (i), "provider", "").down () == "claude";
            }
            // Match the panel order, including Claude's locally supplied accounts card.
            for (int rank = 0; rank <= LAST_PROVIDER_RANK; rank++) {
                if (rank == provider_rank ("claude") && !has_claude && claude_data != null) {
                    quota_box.append (build_claude_card (now_unix));
                }
                for (uint i = 0; i < entries.get_length (); i++) {
                    var entry = entries.get_object_element (i);
                    if (provider_rank (JsonBoundary.text (entry, "provider", "").down ()) == rank) {
                        quota_box.append (build_provider_card (entry, now_unix));
                    }
                }
            }
        }

        private void append_weekly_tokens (Gtk.Box card, string provider) {
            var tokens = local_week_tokens (provider);
            if (tokens.length > 0) card.append (subtle_label (tokens + " tokens · 7 days"));
        }

        private Gtk.Widget build_provider_card (Json.Object entry, int64 now_unix) {
            var provider = (JsonBoundary.text (entry, "provider", "Provider")).down ();
            var title_text = provider_title (provider);
            var error = JsonBoundary.text (entry, "error", "");
            var status = JsonBoundary.text (entry, "status", "");
            var status_level = JsonBoundary.text (entry, "statusLevel", "");
            var stale = QuotaEta.entry_stale (entry, snapshot_stale, now_unix);

            var card = new Gtk.Box (Gtk.Orientation.VERTICAL, 6);
            card.add_css_class ("card");
            open_app_on_click (card, provider);

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
            var plan = JsonBoundary.text (entry, "plan", "");
            var accounts = provider_accounts (provider);
            for (uint i = 0; accounts != null && i < accounts.get_length (); i++) {
                var account = accounts.get_object_element (i);
                if (JsonBoundary.flag (account, "active", false) && email.length > 0 &&
                    JsonBoundary.text (account, "email", "").down () == email.down ()) {
                    // Upstream's generic "Go" describes this provider, not the workspace's tier.
                    if (plan.strip ().length == 0 || (provider == "opencodego" &&
                        (plan.down () == "go" || JsonBoundary.text (account, "planSource", "") == "console"))) {
                        plan = JsonBoundary.text (account, "plan", "");
                    }
                    break;
                }
            }
            head.append (build_identity (email, plan));
            var active_resets = provider == "codex" ? entry.get_member ("resetCredits") : null;
            if (active_resets != null && active_resets.get_node_type () == Json.NodeType.OBJECT) {
                head.append (build_reset_credits (active_resets.get_object (), now_unix));
            }
            if (provider == "codex") {
                head.append (build_add_account_button ("Sign in to another ChatGPT account", () => add_codex_account ()));
            } else if (provider == "opencodego") {
                head.append (build_add_account_button ("Connect another OpenCode Go key or browser sign-in",
                    () => add_opencode_account ()));
            }
            card.append (head);
            append_weekly_tokens (card, provider);

            var windows = JsonBoundary.array (entry, "windows");
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
            if (provider == "grok") {
                append_detail_rows (card, entry);
            }
            if (provider == "opencodego") {
                for (uint i = 0; opencode_accounts != null && i < opencode_accounts.get_length (); i++) {
                    var account = opencode_accounts.get_object_element (i);
                    if (JsonBoundary.flag (account, "active", false)) continue;
                    var saved_email = JsonBoundary.text (account, "email", "Saved account");
                    var workspace = JsonBoundary.text (account, "workspace", "");
                    var caption = workspace.length > 0 ? saved_email + " · " + workspace : saved_email;
                    var account_id = JsonBoundary.text (account, "id", "");
                    card.append (build_account_line (caption,
                        JsonBoundary.text (account, "error", "Quota unavailable"),
                        "Make %s active in OpenCode and refresh CodexBar usage".printf (caption),
                        () => switch_opencode_account.begin (account_id),
                        account.has_member ("windows") ? JsonBoundary.array (account, "windows") : null,
                        hint_id ("opencodego", account), JsonBoundary.text (account, "plan", ""),
                        JsonBoundary.flag (account, "switchable", true)));
                }
            }
            if (error.length > 0 || windows == null || windows.get_length () == 0) {
                var estimate = provider == "opencodego" ? opencode_local : null;
                var periods = estimate != null ? JsonBoundary.array (estimate, "periods") : null;
                if (periods != null && periods.get_length () > 0) {
                    card.append (subtle_label (JsonBoundary.text (estimate, "message", "Local usage estimate · not account quota")));
                    for (uint i = 0; i < periods.get_length (); i++) {
                        var period = periods.get_object_element (i);
                        if (JsonBoundary.integer (period, "requests", 0) == 0 && i + 1 < periods.get_length ()) {
                            continue;
                        }
                        card.append (subtle_label (Presentation.local_usage_line (
                            JsonBoundary.text (period, "label", ""),
                            JsonBoundary.number (period, "costUSD", 0),
                            JsonBoundary.integer (period, "requests", 0),
                            JsonBoundary.integer (period, "tokens", 0))));
                    }
                    card.append (subtle_label ("Sign in to OpenCode or connect a Go API key to load account quota."));
                } else if (provider == "grok") {
                    card.append (subtle_label ("No Grok credits reported. If you are signed out, run grok login. Local activity is under Sessions."));
                } else {
                    card.append (subtle_label (provider == "opencodego"
                        ? "Sign in to OpenCode or connect a Go API key. Local activity is under Sessions."
                        : error.length > 0 ? error : "No usage reported yet."));
                }
                // Grok signs in with its own CLI; without a terminal launcher, Settings remains the fallback.
                var grok_login = provider == "grok" && terminal_app_for ("grok", { "login" }) != null;
                var settings = new Gtk.Button.with_label (provider == "opencodego" || grok_login ? "Sign in…" : "Open Settings…") {
                    halign = Gtk.Align.START
                };
                if (grok_login) settings.tooltip_text = "Open grok login in a terminal, then refresh CodexBar";
                settings.clicked.connect (() => {
                    popdown_from (settings);
                    if (provider == "opencodego") {
                        add_opencode_account ();
                    } else if (grok_login) {
                        open_desktop_app ("grok", settings, { "login" });
                    } else {
                        run_action ("--settings");
                    }
                });
                card.append (settings);
            }
            return card;
        }

        /* Upstream's informational detail sections (Grok: "Usage breakdown" product shares and
         * "Limit Reset Credits"), shown as compact text lines. Every collection is type-checked here
         * because the boundary validator treats these keys as forward-compatible unknowns. */
        private void append_detail_rows (Gtk.Box card, Json.Object entry) {
            var sections = JsonBoundary.array (entry, "details");
            for (uint i = 0; sections != null && i < sections.get_length () && i < 4; i++) {
                var section_node = sections.get_element (i);
                if (section_node.get_node_type () != Json.NodeType.OBJECT) continue;
                var section = section_node.get_object ();
                var rows = JsonBoundary.array (section, "rows");
                var parts = new StringBuilder ();
                for (uint r = 0; rows != null && r < rows.get_length () && r < 8; r++) {
                    var row_node = rows.get_element (r);
                    if (row_node.get_node_type () != Json.NodeType.OBJECT) continue;
                    var row = row_node.get_object ();
                    var label = JsonBoundary.text (row, "label").strip ();
                    var value = JsonBoundary.text (row, "value").strip ();
                    if (label.length == 0 && value.length == 0) continue;
                    if (parts.len > 0) parts.append (" · ");
                    parts.append (label.length > 0 && value.length > 0 ? label + " " + value : label + value);
                }
                if (parts.len == 0) continue;
                var title = JsonBoundary.text (section, "title").strip ();
                var line = subtle_label (title.length > 0 ? title + " · " + parts.str : parts.str);
                card.append (line);
            }
        }

        private string opencode_week_tokens () {
            return local_week_tokens ("opencodego");
        }

        private string local_week_tokens (string provider) {
            var session_id = provider == "opencodego" ? "opencode" : provider;
            for (uint i = 0; local_sessions != null && i < local_sessions.get_length (); i++) {
                var session = local_sessions.get_object_element (i);
                if (JsonBoundary.text (session, "id") != session_id) continue;
                var periods = JsonBoundary.array (session, "periods");
                for (uint p = 0; periods != null && p < periods.get_length (); p++) {
                    var period = periods.get_object_element (p);
                    if (JsonBoundary.text (period, "label") == "7 days") {
                        var tokens = JsonBoundary.integer (period, "tokens", -1);
                        return tokens >= 0 ? Presentation.panel_count_text (tokens) : "";
                    }
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
                provider == "opencodego" ? "mseries-codexbar-opencode-symbolic" :
                provider == "grok" ? "mseries-codexbar-grok-symbolic" : "";
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

        /* The "+" sits at the card's top right: no "Accounts" label row, the saved accounts speak for themselves. */
        private Gtk.Widget build_add_account_button (string tooltip, owned ActionFunc on_add) {
            var add = new Gtk.Button () {
                child = new Gtk.Image.from_icon_name ("list-add-symbolic") { pixel_size = 12 },
                tooltip_text = tooltip, valign = Gtk.Align.CENTER, halign = Gtk.Align.END
            };
            add.add_css_class ("flat");
            add.add_css_class ("compact");
            add.update_property (Gtk.AccessibleProperty.LABEL, tooltip, -1);
            add.clicked.connect (() => {
                popdown_from (add);
                on_add ();
            });
            return add;
        }

        private Gtk.Widget build_account_line (string email, string detail, string switch_tooltip,
                                               owned ActionFunc? on_switch, Json.Array? windows = null, string candidate_id = "", string plan = "", bool switch_sensitive = true,
                                               Json.Object? resets = null) {
            var line = new Gtk.Box (Gtk.Orientation.HORIZONTAL, 6);
            line.add_css_class ("account-line");
            var name = new Gtk.Label (email) { xalign = 0, hexpand = true, ellipsize = Pango.EllipsizeMode.MIDDLE };
            name.set_tooltip_text (email);
            // One row: badges, name, plan and resets on the left, quota and time-to-reset to their right, then Switch.
            name.add_css_class ("account-name");
            name.ellipsize = Pango.EllipsizeMode.END;  // the start of an address identifies it better than the middle
            name.width_chars = 8;
            var identity = new Gtk.Box (Gtk.Orientation.HORIZONTAL, 4) { hexpand = true };
            identity.append (build_hint_badges (candidate_id));
            identity.append (name);
            // The plan lives in the tooltip here: the single row has no room for a badge beside the quota.
            var plan_text = Presentation.plan_label (plan);
            name.set_tooltip_text (plan_text.length > 0 ? "%s · %s".printf (email, plan_text) : email);
            if (resets != null) {
                var chip = build_reset_credits (resets, new DateTime.now_utc ().to_unix ());
                chip.margin_start = 2;
                identity.append (chip);
            }
            line.append (identity);
            var has_quota = windows != null && windows.get_length () > 0;
            var meta = new Gtk.Label (has_quota ? Presentation.account_quota (windows, new DateTime.now_utc ().to_unix ()) : detail) {
                xalign = 1, valign = Gtk.Align.CENTER, justify = Gtk.Justification.RIGHT,
                wrap = true, wrap_mode = Pango.WrapMode.WORD_CHAR, max_width_chars = 34
            };  // two windows fit on the row; a third wraps instead of widening the popover
            meta.set_tooltip_text ("Quota remaining · ↻ time until reset. " + detail);
            meta.add_css_class ("caption");
            meta.add_css_class ("account-meta");
            if (!has_quota) meta.add_css_class ("dim-label");
            else meta.set_markup (colored_account_quota (meta, windows, new DateTime.now_utc ().to_unix ()));
            meta.add_css_class ("numeric");
            line.append (meta);
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

        private string panel_account_quota (Gtk.Widget widget, Json.Array windows, int64 now_unix) {
            if (!display_preferences.get_bool ("compactQuota"))
                return colored_account_quota (widget, windows, now_unix, true);
            if (!display_preferences.get_bool ("showPercent")) return "";
            var text = new StringBuilder ();
            for (uint i = 0; i < windows.get_length (); i++) {
                var window = windows.get_object_element (i);
                var remaining = JsonBoundary.number (window, "remaining", -1);
                if (remaining < 0) continue;
                if (text.len > 0) text.append (" · ");
                var dot = new Gtk.Label (null);
                apply_quota_dot (dot, Presentation.short_window_label (JsonBoundary.text (window, "label", "Quota"),
                    (int) JsonBoundary.integer (window, "minutes")), remaining);
                text.append (dot.label);
            }
            return text.str;
        }

        /* quiet: healthy values keep the text color, so only low and critical quota draws the eye (panel bar). */
        private string colored_account_quota (Gtk.Widget widget, Json.Array? windows, int64 now_unix, bool quiet = false) {
            return Presentation.account_quota_markup (windows, now_unix,
                quiet ? "" : quota_theme_color (widget, "success_color", "#2e7d32"),
                quota_theme_color (widget, "warning_color", "#a66300"),
                quota_theme_color (widget, "error_color", "#c6262e"),
                display_preferences.get_bool ("showPercent"), display_preferences.get_bool ("showReset"));
        }

        /* Which login a provider is tied to: quiet, under the title, never the focus of the card. */
        private string account_email_for (string provider, Json.Object entry) {
            var email = JsonBoundary.text (entry, "accountEmail", "");
            if (email.length == 0 && provider == "codex" && codex_accounts != null) {
                for (uint i = 0; i < codex_accounts.get_length (); i++) {
                    var account = codex_accounts.get_object_element (i);
                    if (JsonBoundary.flag (account, "active", false)) {
                        email = JsonBoundary.text (account, "email", "");
                    }
                }
            }
            if (email.length == 0 && provider == "opencodego" && opencode_local != null) {
                email = JsonBoundary.text (opencode_local, "accountEmail", "");
            }
            if (email.length == 0 && provider == "grok") {
                // codexbar-sessions.py reports only the email from Grok's own sign-in file.
                for (uint i = 0; local_sessions != null && i < local_sessions.get_length (); i++) {
                    var session = local_sessions.get_object_element (i);
                    if (JsonBoundary.text (session, "id") == "grok") email = JsonBoundary.text (session, "accountEmail", "");
                }
            }
            if (email.length == 0 && provider == "opencodego") {
                for (uint i = 0; opencode_accounts != null && i < opencode_accounts.get_length (); i++) {
                    var account = opencode_accounts.get_object_element (i);
                    if (JsonBoundary.flag (account, "active", false)) {
                        email = JsonBoundary.text (account, "email", "");
                        break;
                    }
                }
            }
            return email;
        }

        private Gtk.Widget build_window (string provider_title_text, Json.Object window, bool stale, int64 now_unix) {
            var label = JsonBoundary.text (window, "label", "Quota");
            var reset = JsonBoundary.text (window, "resetText", "");
            var pace = JsonBoundary.text (window, "pace", "");
            var remaining_node = window.get_member ("remaining");
            var known = remaining_node != null && remaining_node.get_node_type () != Json.NodeType.NULL;
            var remaining = known
                ? GLib.Math.fmin (100.0, GLib.Math.fmax (0.0, remaining_node.get_double ())) : -1.0;
            var level = Presentation.visual_level (remaining);
            var eta = QuotaEta.from_window (window, stale, now_unix);

            var group = new Gtk.Box (Gtk.Orientation.VERTICAL, 1);
            var row = new Gtk.Box (Gtk.Orientation.HORIZONTAL, 6);
            var name = new Gtk.Label (Presentation.short_window_label (label, (int) JsonBoundary.integer (window, "minutes"))) {
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
            if (display_preferences.get_bool ("showPercent")) row.append (percent);
            var reset_label = new Gtk.Label (compact_reset (reset)) { xalign = 1, width_request = 46 };
            reset_label.add_css_class ("caption");
            reset_label.add_css_class ("dim-label");
            reset_label.add_css_class ("numeric");
            reset_label.set_tooltip_text (reset);
            if (display_preferences.get_bool ("showReset")) row.append (reset_label);
            group.append (row);

            // The forecast only gets its own line when it is a warning; otherwise the reset sits inline.
            if (!known || eta.state == EtaState.EXHAUSTED || eta.state == EtaState.DEPLETING) {
                // Explicit owned string; see Presentation.account_quota for the nested-ternary valac defect.
                string caption_text = "Usage not reported yet";
                if (known) {
                    caption_text = display_preferences.get_bool ("showReset")
                        ? Presentation.window_caption (reset, eta.state, eta.detail)
                        : eta.state == EtaState.EXHAUSTED ? "Limit reached" : eta.detail;
                }
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
            var spending = snapshot.has_member ("spending") ? JsonBoundary.array (snapshot, "spending") : null;
            if (spending == null || spending.get_length () == 0) {
                show_state (spend_box, "emblem-documents-symbolic", "No spend data yet",
                    "CodexBar estimates spend from local token use once it has seen some.", false);
                return;
            }
            for (uint i = 0; i < spending.get_length (); i++) {
                var item = spending.get_object_element (i);
                var provider = (JsonBoundary.text (item, "provider", "")).down ();
                var card = new Gtk.Box (Gtk.Orientation.VERTICAL, 4);
                card.add_css_class ("card");
                var title = new Gtk.Label (provider_title (provider)) { xalign = 0 };
                title.add_css_class ("provider-title");
                card.append (title);
                var error = JsonBoundary.text (item, "error", "");
                if (error.length > 0) {
                    card.append (subtle_label (error));
                } else {
                    append_metric (card, "Today", "$%0.2f".printf (JsonBoundary.number (item, "today")));
                    append_metric (card, "This month", "$%0.2f".printf (JsonBoundary.number (item, "month")));
                    append_metric (card, "Tokens this month", Presentation.count_text (JsonBoundary.integer (item, "tokens")));
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
            var sessions = local_sessions;
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
            var state = JsonBoundary.text (session, "state", "off");
            var card = new Gtk.Box (Gtk.Orientation.VERTICAL, 4);
            card.add_css_class ("card");
            var head = new Gtk.Box (Gtk.Orientation.HORIZONTAL, 6);
            var dot = new Gtk.Label ("●");
            dot.add_css_class (state == "ok" ? "dot-ok" : state == "warn" ? "dot-warn" : "dot-off");
            dot.set_tooltip_text (state == "ok" ? "Ready" : state == "warn" ? "Needs attention" : "Not set up");
            head.append (dot);
            var title = new Gtk.Label (JsonBoundary.text (session, "name", "Session")) { xalign = 0, hexpand = true };
            title.add_css_class ("provider-title");
            head.append (title);
            card.append (head);
            card.append (subtle_label (JsonBoundary.text (session, "detail", "")));

            var periods = session.has_member ("periods") ? JsonBoundary.array (session, "periods") : null;
            if (periods == null || periods.get_length () == 0) {
                return card;
            }
            // 5 hours and 7 days are the windows the plans are limited by.
            for (uint i = 0; i < periods.get_length () && i < 2; i++) {
                var period = periods.get_object_element (i);
                var cost = JsonBoundary.number (period, "costUSD");
                var value = "%s req · %s tok".printf (JsonBoundary.integer (period, "requests").to_string (),
                    Presentation.count_text (JsonBoundary.integer (period, "tokens")));
                if (cost > 0) {
                    value += " · $%0.2f".printf (cost);
                }
                append_metric (card, JsonBoundary.text (period, "label", "Usage"), value);
            }
            var note = JsonBoundary.text (session, "note", "");
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
            set_panel_summary (headline + " · " + message);
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
            popover_open = true;
            snapshot_tick = 0;
            read_snapshot.begin (true);
            ensure_sessions (15);
        }

        public override void closed () {
            popover_open = false;
        }
    }
}

public Wingpanel.Indicator? get_indicator (Module module, Wingpanel.ServerType server_type) {
    if (server_type != Wingpanel.ServerType.SESSION) {
        return null;
    }
    return new MSeries.CodexBarIndicator ();
}
