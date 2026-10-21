/* Read-only GitHub repository status for Pantheon's Wingpanel, styled like the CodexBar indicator. */
using GLib;
using Gtk;
using Json;
using Wingpanel;

namespace MSeries {
    public class RepoBarIndicator : Wingpanel.Indicator {
        // Scopes are the segmented switcher; filters narrow any scope from the search row's menu.
        private const string[] SCOPES = { "Dashboard", "Pinned", "Attention", "All" };
        private const string[] FILTERS = { "Any repository", "Has open issues", "Has open pull requests", "Local checkout", "Failing CI" };
        private const string[] DETAIL_KEYS = { "pulls", "issues", "ci", "traffic", "releases", "commits", "branches", "tags", "activity" };
        private const string[] DETAIL_TITLES = { "PRs", "Issues", "CI", "Traffic", "Releases", "Commits", "Branches", "Tags", "Activity" };

        private Gtk.Box panel;
        private Gtk.Label panel_prs;
        private Gtk.Label panel_issues;
        private Gtk.Label panel_alert;
        private Gtk.Label panel_running;
        private Gtk.Box menu;
        private Gtk.ListBox repo_list;
        private Gtk.Overlay list_overlay;
        private Granite.Toast? toast = null;
        private string sort_order = "activity";
        private string settings_executable;
        private string ui_state_path;
        private FileMonitor? settings_monitor = null;
        private Gtk.SearchEntry search_entry;
        private Gtk.ToggleButton[] scope_buttons = {};
        private Gtk.MenuButton filter_button;
        private Gtk.CheckButton[] filter_checks = {};
        private Gtk.Label subtitle_label;
        private Gtk.Label chip_label;
        private Gtk.Button chip_button;
        private string chip_action = "";
        private Gtk.Button refresh_button;
        private Gtk.Stack refresh_display;
        private Gtk.Spinner refresh_spinner;
        private int scope = 0;
        private int filter = 0;
        private bool in_flight = false;
        private bool show_forks = false;
        private bool show_archived = false;
        private uint refresh_source = 0;
        private uint refresh_interval = 0;
        private string executable;
        private string account = "";
        private string host = "github.com";
        private string last_snapshot_text = "";
        private string last_render_key = "";
        private int64 last_notified_fetch = 0;
        private bool notify_ci = true;
        private bool notify_workflows = true;
        private int merge_window_minutes = 60;
        private string running_summary = "";
        private bool show_contributions = true;
        private string contribution_style = "dots";
        private bool contributions_expanded = false;
        private string local_root = "";
        // "Show RepoBar in the panel" (settings.json showInPanel): off hides the module and stops refreshing and notifying.
        private bool panel_enabled = true;
        private uint settings_generation = 0;

        public RepoBarIndicator () {
            GLib.Object (code_name: "repobar");
        }

        construct {
            executable = GLib.Path.build_filename (Environment.get_home_dir (), ".local", "bin", "mseries-repobar");

            // Panel item: GitHub mark, open PRs and issues, and a status dot (red failing, yellow pending, green recent merge).
            panel = new Gtk.Box (Gtk.Orientation.HORIZONTAL, 4);
            panel.add_css_class ("mseries-repobar-bar");
            var mark = new Gtk.Image.from_icon_name ("github-symbolic") { pixel_size = 16, valign = Gtk.Align.CENTER };
            mark.add_css_class ("repo-mark");
            panel.append (mark);
            // Two stacked columns keep the readout narrow: PR over issue counts, then running workflows over a recent merge.
            // GitHub's own pull request and issue marks label the two counts.
            var counts = new Gtk.Box (Gtk.Orientation.VERTICAL, 0) { valign = Gtk.Align.CENTER };
            counts.add_css_class ("repo-counts");
            var pull_row = new Gtk.Box (Gtk.Orientation.HORIZONTAL, 3);
            pull_row.append (new Gtk.Image.from_icon_name (kind_icon ("pull")) { pixel_size = 12, valign = Gtk.Align.CENTER });
            panel_prs = new Gtk.Label ("…") { valign = Gtk.Align.CENTER, halign = Gtk.Align.START };
            panel_prs.add_css_class ("seg-value");
            pull_row.append (panel_prs);
            counts.append (pull_row);
            var issue_row = new Gtk.Box (Gtk.Orientation.HORIZONTAL, 3);
            issue_row.append (new Gtk.Image.from_icon_name (kind_icon ("issue")) { pixel_size = 12, valign = Gtk.Align.CENTER });
            panel_issues = new Gtk.Label ("") { valign = Gtk.Align.CENTER, halign = Gtk.Align.START };
            panel_issues.add_css_class ("seg-value");
            issue_row.append (panel_issues);
            counts.append (issue_row);
            panel.append (counts);
            var alerts = new Gtk.Box (Gtk.Orientation.VERTICAL, 0) { valign = Gtk.Align.CENTER };
            alerts.add_css_class ("repo-alerts");
            panel_running = new Gtk.Label ("") { valign = Gtk.Align.CENTER, halign = Gtk.Align.START, visible = false };
            panel_running.add_css_class ("seg-alert");
            panel_running.add_css_class ("alert-pending");
            alerts.append (panel_running);
            panel_alert = new Gtk.Label ("●") { valign = Gtk.Align.CENTER, halign = Gtk.Align.START, visible = false };
            panel_alert.add_css_class ("seg-alert");
            alerts.append (panel_alert);
            panel.append (alerts);
            panel.set_tooltip_text ("RepoBar · loading GitHub status… · Middle-click to refresh");
            var click = new Gtk.GestureClick () { button = 2 };
            click.released.connect (() => refresh ());
            panel.add_controller (click);
            this.visible = true;

            menu = new Gtk.Box (Gtk.Orientation.VERTICAL, 8) {
                margin_top = 8, margin_bottom = 6, margin_start = 8, margin_end = 8,
                width_request = 360
            };
            menu.add_css_class ("mseries-repobar");
            install_style (menu.get_display ());

            // Segmented scope switcher on top, like CodexBar's Quota / Sessions / Spend pages.
            var switcher = new Gtk.Box (Gtk.Orientation.HORIZONTAL, 0) { homogeneous = true };
            switcher.add_css_class ("linked");
            switcher.add_css_class ("mseries-switcher");
            for (int i = 0; i < SCOPES.length; i++) {
                int index = i;
                var button = new Gtk.ToggleButton.with_label (SCOPES[i]) { active = i == 0 };
                if (i > 0) button.set_group (scope_buttons[0]);
                button.toggled.connect (() => {
                    if (!button.get_active () || scope == index) return;
                    scope = index;
                    save_ui_state ();
                    render_cached ();
                });
                scope_buttons += button;
                switcher.append (button);
            }
            menu.append (switcher);

            var search_row = new Gtk.Box (Gtk.Orientation.HORIZONTAL, 6);
            search_entry = new Gtk.SearchEntry () { placeholder_text = "Search repositories", hexpand = true };
            search_entry.search_changed.connect (() => render_cached ());
            search_row.append (search_entry);
            filter_button = new Gtk.MenuButton () {
                icon_name = "view-sort-descending-symbolic", tooltip_text = "Filter repositories", valign = Gtk.Align.CENTER
            };
            filter_button.add_css_class ("flat");
            filter_button.set_popover (build_filter_popover ());
            search_row.append (filter_button);
            menu.append (search_row);

            var scroll = new Gtk.ScrolledWindow () {
                hscrollbar_policy = Gtk.PolicyType.NEVER,
                vscrollbar_policy = Gtk.PolicyType.AUTOMATIC,
                min_content_height = 150,
                max_content_height = 560,
                propagate_natural_height = true
            };
            // A list box gives cards keyboard focus: arrows move between repositories, Enter opens one.
            repo_list = new Gtk.ListBox () { selection_mode = Gtk.SelectionMode.NONE, activate_on_single_click = false };
            repo_list.add_css_class ("repo-list");
            repo_list.row_activated.connect ((row) => {
                string? url = row.get_data<string> ("url");
                if (url != null) open_url (url, row);
            });
            scroll.set_child (repo_list);
            list_overlay = new Gtk.Overlay () { child = scroll };
            menu.append (list_overlay);
            menu.append (new Gtk.Separator (Gtk.Orientation.HORIZONTAL));

            // Bottom bar: freshness on the left, an icon-only dock on the right (names in tooltips).
            subtitle_label = new Gtk.Label ("Loading GitHub status…") { xalign = 0, hexpand = true, ellipsize = Pango.EllipsizeMode.END };
            subtitle_label.add_css_class ("dim-label");
            subtitle_label.add_css_class ("caption");
            subtitle_label.add_css_class ("numeric");
            // The status chip acts on what it says: "N failing" shows them, "Cached"/"Offline" retries.
            chip_label = new Gtk.Label ("");
            chip_button = new Gtk.Button () { child = chip_label, valign = Gtk.Align.CENTER, visible = false };
            chip_button.add_css_class ("flat");
            chip_button.add_css_class ("chip");
            chip_button.clicked.connect (() => {
                if (chip_action == "failing") {
                    filter_checks[4].set_active (true);
                    scope_buttons[3].set_active (true);
                } else {
                    refresh ();
                }
            });
            refresh_display = new Gtk.Stack ();
            refresh_display.add_named (new Gtk.Image.from_icon_name ("view-refresh-symbolic") { pixel_size = 18 }, "idle");
            refresh_spinner = new Gtk.Spinner ();
            refresh_display.add_named (refresh_spinner, "busy");
            refresh_button = new Gtk.Button () { child = refresh_display, tooltip_text = "Refresh GitHub repositories" };
            refresh_button.add_css_class ("flat");
            refresh_button.update_property (Gtk.AccessibleProperty.LABEL, "Refresh GitHub repositories", -1);
            refresh_button.clicked.connect (() => refresh ());

            var bar = new Gtk.Box (Gtk.Orientation.HORIZONTAL, 8);
            bar.add_css_class ("mseries-bar");
            bar.append (chip_button);
            bar.append (subtitle_label);
            var actions = new Gtk.Box (Gtk.Orientation.HORIZONTAL, 0) { homogeneous = true };
            actions.add_css_class ("mseries-dock");
            actions.append (make_dock_button ("Your pull requests", kind_icon ("pull"), "/pulls"));
            actions.append (make_dock_button ("Your issues", kind_icon ("issue"), "/issues"));
            settings_executable = GLib.Path.build_filename (Environment.get_home_dir (), ".local", "bin", "mseries-repobar-settings");
            var settings_button = new Gtk.Button () {
                child = new Gtk.Image.from_icon_name ("preferences-system-symbolic") { pixel_size = 18 },
                tooltip_text = "RepoBar Settings…"
            };
            settings_button.add_css_class ("flat");
            settings_button.update_property (Gtk.AccessibleProperty.LABEL, "RepoBar Settings", -1);
            settings_button.clicked.connect (() => {
                popdown_from (settings_button);
                try {
                    Process.spawn_async (null, { settings_executable }, null,
                        SpawnFlags.STDOUT_TO_DEV_NULL | SpawnFlags.STDERR_TO_DEV_NULL, null, null);
                } catch (Error e) {
                    subtitle_label.set_text ("Settings are not installed");
                }
            });
            actions.append (settings_button);
            actions.append (refresh_button);
            bar.append (actions);
            menu.append (bar);

            // Typing anywhere in the menu searches; Ctrl+F, Ctrl+R and Alt+1…4 mirror elementary apps.
            search_entry.set_key_capture_widget (menu);
            var shortcuts = new Gtk.ShortcutController () { scope = Gtk.ShortcutScope.LOCAL };
            shortcuts.add_shortcut (new Gtk.Shortcut (Gtk.ShortcutTrigger.parse_string ("<Control>f"),
                new Gtk.CallbackAction (() => { search_entry.grab_focus (); return true; })));
            shortcuts.add_shortcut (new Gtk.Shortcut (Gtk.ShortcutTrigger.parse_string ("<Control>r"),
                new Gtk.CallbackAction (() => { refresh (); return true; })));
            for (int i = 0; i < SCOPES.length; i++) {
                int index = i;
                shortcuts.add_shortcut (new Gtk.Shortcut (Gtk.ShortcutTrigger.parse_string ("<Alt>%d".printf (i + 1)),
                    new Gtk.CallbackAction (() => { scope_buttons[index].set_active (true); return true; })));
                scope_buttons[i].set_tooltip_text ("Alt+%d".printf (i + 1));
            }
            menu.add_controller (shortcuts);
            search_entry.stop_search.connect (() => search_entry.set_text (""));

            ui_state_path = GLib.Path.build_filename (Environment.get_user_config_dir (), "mseries", "repobar", "panel.ini");
            restore_ui_state ();
            watch_settings ();
            show_state ("content-loading-symbolic", "Loading repositories…", "", false);
            // Draw the last cached snapshot at once; the helper's answer replaces it when it arrives.
            apply_panel_enabled ();
        }

        private static bool read_panel_enabled () {
            try {
                var parser = new Json.Parser ();
                parser.load_from_file (GLib.Path.build_filename (Environment.get_user_config_dir (), "mseries", "repobar", "settings.json"));
                return parser.get_root ().get_object ().get_boolean_member_with_default ("showInPanel", true);
            } catch (Error e) {
                return true;
            }
        }

        /* Applies the show-in-panel preference: hidden means no GitHub requests, timers or notifications until it is turned back on. */
        private void apply_panel_enabled () {
            panel_enabled = read_panel_enabled ();
            this.visible = panel_enabled;
            if (!panel_enabled) {
                if (refresh_source != 0) Source.remove (refresh_source);
                refresh_source = 0;
                refresh_interval = 0;
                return;
            }
            render_cached ();
            schedule_refresh (300);
            load_snapshot ();
        }

        private static void install_style (Gdk.Display display) {
            var style = new Gtk.CssProvider ();
            style.load_from_string (
                ".mseries-repobar { font-size: 9pt; } " +
                ".mseries-repobar .caption { font-size: 8pt; } " +
                ".mseries-repobar .numeric { font-feature-settings: \"tnum\"; } " +
                ".mseries-repobar .repo-card { padding: 6px 10px; border-radius: 8px; background: alpha(currentColor, 0.06); } " +
                ".mseries-repobar row:hover .repo-card { background: alpha(currentColor, 0.09); } " +
                ".mseries-repobar .repo-name { font-weight: 700; font-size: 9.5pt; } " +
                ".mseries-repobar .repo-owner { font-size: 8pt; opacity: 0.6; } " +
                ".mseries-repobar .count { padding: 0 7px; border-radius: 99px; font-size: 7.5pt; font-weight: 700; " +
                "  background: alpha(currentColor, 0.1); } " +
                ".mseries-repobar .count.zero { opacity: 0.45; font-weight: 400; } " +
                ".mseries-repobar .window-name { font-weight: 700; font-size: 7.5pt; opacity: 0.75; } " +
                ".mseries-repobar .chip { padding: 1px 8px; border-radius: 99px; font-size: 7.5pt; font-weight: 700; " +
                "  background: alpha(@warning_color, 0.22); color: @warning_color; } " +
                ".mseries-repobar .chip.bad { background: alpha(@error_color, 0.2); color: @error_color; } " +
                ".mseries-repobar button.chip { min-height: 0; min-width: 0; } " +
                ".mseries-repobar button.chip:hover { background: alpha(@warning_color, 0.32); } " +
                ".mseries-repobar button.chip.bad:hover { background: alpha(@error_color, 0.3); } " +
                ".mseries-repobar .text-low { color: @warning_color; } " +
                ".mseries-repobar .text-critical { color: @error_color; } " +
                ".mseries-repobar .dot-ok { color: @success_color; } " +
                ".mseries-repobar .dot-warn { color: @warning_color; } " +
                ".mseries-repobar .dot-bad { color: @error_color; } " +
                ".mseries-repobar .dot-off { opacity: 0.45; } " +
                ".mseries-repobar .state-title { font-weight: 700; } " +
                ".mseries-repobar button { padding: 3px 6px; } " +
                ".mseries-repobar button.compact { padding: 0 4px; min-height: 0; min-width: 0; } " +
                ".mseries-repobar button.link-row { padding: 1px 4px; min-height: 0; border-radius: 6px; } " +
                ".mseries-repobar button.link-row label { font-weight: 400; } " +
                ".mseries-repobar .detail-chips button { padding: 1px 8px; min-height: 0; min-width: 0; border-radius: 99px; font-size: 8pt; " +
                "  background: alpha(currentColor, 0.08); } " +
                ".mseries-repobar .detail-chips button:checked { background: alpha(@accent_color, 0.2); color: @accent_color; } " +
                ".mseries-repobar .detail-list { margin-top: 2px; padding-top: 4px; border-top: 1px solid alpha(currentColor, 0.1); } " +
                ".mseries-repobar .pinned-star { color: #d4a300; } " +
                ".mseries-repobar .section-title { font-weight: 700; font-size: 8pt; opacity: 0.75; } " +
                ".mseries-repobar list.repo-list > row .group-heading { margin-top: 2px; margin-bottom: -4px; } " +
                ".mseries-repobar .for-you { background: alpha(@accent_color, 0.08); } " +
                ".mseries-repobar .contribution-graph { color: @accent_color; } " +
                ".mseries-repobar button.site-link { opacity: 0.6; padding: 0 2px; } " +
                ".mseries-repobar button.site-link:hover, .mseries-repobar button.site-link:focus { opacity: 1; color: @accent_color; } " +
                ".mseries-repobar button.pin-off { opacity: 0; } " +
                ".mseries-repobar row:hover button.pin-off, .mseries-repobar row:focus-within button.pin-off { opacity: 0.55; } " +
                ".mseries-repobar row:hover button.pin-off:hover, .mseries-repobar button.pin-off:focus { opacity: 1; } " +
                ".mseries-repobar list.repo-list { background: transparent; } " +
                ".mseries-repobar button.show-all { font-size: 8.5pt; padding: 2px 10px; } " +
                ".mseries-repobar list.repo-list > row { padding: 0; margin-bottom: 8px; border-radius: 8px; background: transparent; } " +
                ".mseries-repobar list.repo-list > row:last-child { margin-bottom: 0; } " +
                ".mseries-repobar list.repo-list > row:focus-visible { outline: 2px solid alpha(@accent_color, 0.6); outline-offset: -2px; } " +
                ".mseries-repobar button.disclosure, .mseries-repobar button.compact.dim-label { opacity: 0.55; } " +
                ".mseries-repobar button.disclosure:hover, .mseries-repobar button.compact.dim-label:hover { opacity: 1; } " +
                ".mseries-repobar .mseries-switcher button { padding: 2px 6px; } " +
                ".mseries-repobar .mseries-dock { padding: 3px; border-radius: 12px; background: alpha(currentColor, 0.06); } " +
                ".mseries-repobar .mseries-bar { margin-top: 2px; } " +
                ".mseries-repobar .mseries-dock button { padding: 6px 11px; border-radius: 9px; min-height: 0; } " +
                ".mseries-repobar .mseries-dock button:hover { background: alpha(currentColor, 0.1); } " +
                ".mseries-repobar-bar label { font-size: 8.5pt; font-feature-settings: \"tnum\"; } " +
                ".mseries-repobar-bar .seg-value { font-size: 8.5pt; font-weight: 700; } " +
                ".mseries-repobar-bar .seg-alert { font-size: 8pt; font-weight: 700; } " +
                ".mseries-repobar-bar .seg-alert.alert-bad { color: @error_color; } " +
                ".mseries-repobar-bar .seg-alert.alert-pending { color: @warning_color; } " +
                ".mseries-repobar-bar .seg-alert.alert-good { color: @success_color; } " +
                ".mseries-repobar-bar .seg-divider { min-width: 1px; margin: 4px 0; background: alpha(currentColor, 0.22); } " +
                ".mseries-repobar-bar .stale { opacity: 0.55; } " +
                ".mseries-repobar-bar .repo-mark { opacity: 0.92; }");
            Gtk.StyleContext.add_provider_for_display (display, style, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION);
        }

        private Gtk.Popover build_filter_popover () {
            var box = new Gtk.Box (Gtk.Orientation.VERTICAL, 2) {
                margin_top = 6, margin_bottom = 6, margin_start = 6, margin_end = 6
            };
            Gtk.CheckButton? first = null;
            for (int i = 0; i < FILTERS.length; i++) {
                int index = i;
                var option = new Gtk.CheckButton.with_label (FILTERS[i]) { active = i == 0 };
                if (first != null) option.set_group (first); else first = option;
                filter_checks += option;
                option.toggled.connect (() => {
                    if (!option.get_active ()) return;
                    filter = index;
                    save_ui_state ();
                    if (index == 0) filter_button.remove_css_class ("suggested-action");
                    else filter_button.add_css_class ("suggested-action");
                    filter_button.set_tooltip_text (index == 0 ? "Filter repositories" : "Filter: " + FILTERS[index]);
                    render_cached ();
                });
                box.append (option);
            }
            return new Gtk.Popover () { child = box };
        }

        private Gtk.Button make_dock_button (string label, string icon_name, string path) {
            var button = new Gtk.Button () {
                child = new Gtk.Image.from_icon_name (icon_name) { pixel_size = 18 },
                tooltip_text = label
            };
            button.add_css_class ("flat");
            button.update_property (Gtk.AccessibleProperty.LABEL, label, -1);
            button.clicked.connect (() => open_url ("https://" + host + path, button));
            return button;
        }

        private static void popdown_from (Gtk.Widget widget) {
            // Close nested popovers first, then the Wingpanel popover that hosts the menu.
            for (var popover = widget.get_ancestor (typeof (Gtk.Popover)) as Gtk.Popover; popover != null;
                 popover = popover.get_parent () != null ? popover.get_parent ().get_ancestor (typeof (Gtk.Popover)) as Gtk.Popover : null) {
                popover.popdown ();
            }
        }

        private static void open_url (string url, Gtk.Widget source) {
            if (url.length == 0) return;
            popdown_from (source);
            new Gtk.UriLauncher (url).launch.begin (null, null);
        }

        private void show_state (string icon, string headline, string message, bool with_sign_in) {
            repo_list.remove_all ();
            last_render_key = "";
            var state = new Gtk.Box (Gtk.Orientation.VERTICAL, 6) {
                halign = Gtk.Align.CENTER, margin_top = 14, margin_bottom = 14
            };
            state.append (new Gtk.Image.from_icon_name (icon) { pixel_size = 32, opacity = 0.6 });
            var title = new Gtk.Label (headline) { justify = Gtk.Justification.CENTER };
            title.add_css_class ("state-title");
            state.append (title);
            if (message.length > 0) {
                var detail = new Gtk.Label (message) {
                    wrap = true, justify = Gtk.Justification.CENTER, max_width_chars = 40, selectable = !with_sign_in
                };
                detail.add_css_class ("dim-label");
                detail.add_css_class ("caption");
                state.append (detail);
            }
            if (with_sign_in) {
                var sign_in = new Gtk.Button.with_label ("Sign in with GitHub CLI…") { halign = Gtk.Align.CENTER, margin_top = 4 };
                sign_in.add_css_class ("suggested-action");
                sign_in.clicked.connect (() => {
                    popdown_from (sign_in);
                    try {
                        Process.spawn_async (null, { "io.elementary.terminal", "-x", "gh", "auth", "login" }, null,
                            SpawnFlags.SEARCH_PATH | SpawnFlags.STDOUT_TO_DEV_NULL | SpawnFlags.STDERR_TO_DEV_NULL, null, null);
                    } catch (Error e) {
                        subtitle_label.set_text ("Run `gh auth login` in Terminal");
                    }
                });
                state.append (sign_in);
            }
            var state_row = new Gtk.ListBoxRow () { child = state, activatable = false, focusable = false };
            repo_list.append (state_row);
        }

        private void load_snapshot () {
            read_snapshot.begin (false);
        }

        private void schedule_refresh (uint seconds) {
            seconds = seconds < 60 ? 60 : (seconds > 900 ? 900 : seconds);
            if (refresh_source != 0 && refresh_interval == seconds) return;
            if (refresh_source != 0) Source.remove (refresh_source);
            refresh_interval = seconds;
            refresh_source = Timeout.add_seconds (seconds, () => {
                load_snapshot ();
                return Source.CONTINUE;
            });
        }

        private void refresh () {
            read_snapshot.begin (true);
        }

        private void set_refreshing (bool busy) {
            refresh_display.set_visible_child_name (busy ? "busy" : "idle");
            refresh_spinner.set_spinning (busy);
            refresh_button.set_sensitive (!busy);
        }

        private async void read_snapshot (bool force) {
            if (in_flight || !panel_enabled) return;
            uint generation = settings_generation;
            in_flight = true;
            set_refreshing (true);
            if (force) subtitle_label.set_text ("Refreshing…");
            string output = "";
            string error_text = "";
            try {
                var argv = new string[] { executable };
                if (force) argv += "--refresh";
                var process = new Subprocess.newv (argv, SubprocessFlags.STDOUT_PIPE | SubprocessFlags.STDERR_PIPE);
                yield process.communicate_utf8_async (null, null, out output, out error_text);
                if (!process.get_successful () && output.strip ().length == 0) {
                    throw new IOError.FAILED (error_text.strip ().length > 0 ? error_text.strip () : "Could not read GitHub status");
                }
                var parser = new Json.Parser ();
                parser.load_from_data (output);
                if (generation == settings_generation && panel_enabled) {
                    last_snapshot_text = output;
                    render_snapshot (parser.get_root ().get_object ());
                }
            } catch (Error e) {
                if (generation != settings_generation || !panel_enabled) {
                    in_flight = false;
                    set_refreshing (false);
                    if (panel_enabled) load_snapshot ();
                    return;
                }
                // Only the helper can authorize an offline snapshot for the current account.
                clear_snapshot_state ();
                set_chip ("Offline", true, "retry", e.message + "\nClick to try again");
                subtitle_label.set_text ("GitHub status unavailable");
                subtitle_label.set_tooltip_text (e.message);
                bool signed_out = e.message.contains ("auth") || e.message.contains ("login") || e.message.contains ("No such file");
                show_state (signed_out ? "dialog-password-symbolic" : "network-error-symbolic",
                    signed_out ? "Connect GitHub" : "GitHub unavailable",
                    signed_out ? "RepoBar reads your repositories through the GitHub CLI. It never stores the token." : e.message,
                    signed_out);
            }
            in_flight = false;
            set_refreshing (false);
            if (generation != settings_generation && panel_enabled) load_snapshot ();
        }

        private void set_chip (string text, bool bad, string action = "retry", string tooltip = "") {
            chip_label.set_text (text);
            chip_button.set_visible (text.length > 0);
            chip_action = action;
            chip_button.set_tooltip_text (tooltip.length > 0 ? tooltip : action == "failing" ? "Show repositories with failing CI" : "Try refreshing again");
            if (bad) chip_button.add_css_class ("bad"); else chip_button.remove_css_class ("bad");
        }

        private void render_snapshot (Json.Object snapshot) {
            account = snapshot.get_string_member_with_default ("account", "");
            host = snapshot.get_string_member_with_default ("host", "github.com");
            bool stale = snapshot.get_boolean_member_with_default ("stale", false);
            string error = snapshot.get_string_member_with_default ("error", "");
            int64 fetched_at = snapshot.get_int_member_with_default ("fetchedAt", 0);
            var repos = snapshot.has_member ("repos") ? snapshot.get_array_member ("repos") : new Json.Array ();
            int dashboard_limit = 20;
            if (snapshot.has_member ("settings")) {
                var settings = snapshot.get_object_member ("settings");
                show_forks = settings.get_boolean_member_with_default ("showForks", false);
                show_archived = settings.get_boolean_member_with_default ("showArchived", false);
                dashboard_limit = (int) settings.get_int_member_with_default ("repoLimit", 20);
                sort_order = settings.get_string_member_with_default ("menuSort", "activity");
                schedule_refresh ((uint) settings.get_int_member_with_default ("refreshInterval", 300));
                notify_ci = settings.get_boolean_member_with_default ("notifyCi", true);
                notify_workflows = settings.get_boolean_member_with_default ("notifyWorkflows", true);
                merge_window_minutes = (int) settings.get_int_member_with_default ("mergeWindowMinutes", 60);
                show_contributions = settings.get_boolean_member_with_default ("showContributions", true);
                contribution_style = settings.get_string_member_with_default ("contributionStyle", "dots");
                local_root = settings.get_string_member_with_default ("localRoot", "");
            }
            if (error.length == 0 && fetched_at > last_notified_fetch) {
                last_notified_fetch = fetched_at;
                notify_ci_changes (repos);
                notify_workflow_runs (snapshot);
            }
            int issues = 0;
            int prs = 0;
            int failing = 0;
            int pending = 0;
            int attention = 0;
            GLib.DateTime? last_merge = null;
            string last_merge_repo = "";
            for (uint i = 0; i < repos.get_length (); i++) {
                var repo = repos.get_object_element (i);
                if (repo.get_string_member_with_default ("repoState", "visible") == "hidden") continue;
                issues += (int) repo.get_int_member_with_default ("openIssues", 0);
                prs += (int) repo.get_int_member_with_default ("openPullRequests", 0);
                if (ci_failing (repo)) failing++;
                if (ci_pending (repo)) pending++;
                var merge = repo.get_member ("lastMerge") != null && repo.get_member ("lastMerge").get_node_type () == Json.NodeType.OBJECT
                    ? repo.get_object_member ("lastMerge") : null;
                if (merge != null) {
                    var merged_at = new GLib.DateTime.from_iso8601 (merge.get_string_member_with_default ("mergedAt", ""), null);
                    if (merged_at != null && (last_merge == null || merged_at.compare (last_merge) > 0)) {
                        last_merge = merged_at;
                        last_merge_repo = repo.get_string_member_with_default ("name", "");
                    }
                }
                if (needs_attention (repo)) attention++;
            }

            // Pending is real workflow runs (any branch or pull request) when the snapshot carries them.
            string[] running_lines = {};
            if (snapshot.has_member ("actions") && snapshot.get_member ("actions").get_node_type () == Json.NodeType.OBJECT) {
                var running = snapshot.get_object_member ("actions").get_array_member ("running");
                pending = (int) running.get_length ();
                for (uint i = 0; i < running.get_length () && i < 6; i++) {
                    var run = running.get_object_element (i);
                    string repo_name = run.get_string_member_with_default ("repo", "");
                    running_lines += "%s · %s (%s)".printf (repo_name.contains ("/") ? repo_name.substring (repo_name.index_of ("/") + 1) : repo_name,
                        run.get_string_member_with_default ("name", "workflow"), run.get_string_member_with_default ("branch", ""));
                }
            }
            running_summary = string.joinv ("\n", running_lines);

            // Bottom bar: account, freshness and API quota; the chip speaks only when something is wrong.
            string freshness;
            if (fetched_at > 0) {
                int64 age = int64.max (0, GLib.get_real_time () / 1000000 - fetched_at);
                freshness = age < 60 ? "just now" : age < 3600 ? "%d min ago".printf ((int) (age / 60))
                    : "%dh ago".printf ((int) (age / 3600));
            } else {
                freshness = "not synced yet";
            }
            string quota = "";
            int remaining = -1;
            int limit = -1;
            if (snapshot.has_member ("rateLimits")) {
                var limits = snapshot.get_object_member ("rateLimits");
                if (limits.has_member ("resources") && limits.get_object_member ("resources").has_member ("core")) {
                    var core = limits.get_object_member ("resources").get_object_member ("core");
                    remaining = (int) core.get_int_member_with_default ("remaining", -1);
                    limit = (int) core.get_int_member_with_default ("limit", -1);
                    if (remaining >= 0 && limit > 0) quota = " · API %d%%".printf ((int) (100.0 * remaining / limit));
                }
            }
            subtitle_label.set_text (freshness + quota);
            subtitle_label.set_tooltip_text ((account.length > 0 ? "GitHub · " + account + "\n" : "") + "%u repositories · %d open pull requests · %d open issues%s%s".printf (
                repos.get_length (), prs, issues,
                remaining >= 0 ? "\nGitHub API: %d of %d requests left this hour".printf (remaining, limit) : "",
                error.length > 0 ? "\nLast refresh failed: " + error : ""));
            if (error.length > 0) set_chip (fetched_at > 0 ? "Cached" : "Offline", fetched_at == 0, "retry", error + "\nClick to try again");
            else if (stale) set_chip ("Cached", false);
            else if (failing > 0) set_chip ("%d failing".printf (failing), true, "failing");
            else set_chip ("", false);

            scope_buttons[2].set_label (attention > 0 ? "Attention %d".printf (attention) : "Attention");
            update_panel (prs, issues, pending, last_merge, last_merge_repo, (int) repos.get_length (), stale || error.length > 0);

            // Unchanged data and filters: keep the existing cards so open detail panes survive polling.
            string key = "%s|%d|%d|%s".printf (last_snapshot_text.hash ().to_string (), scope, filter, search_entry.get_text ());
            if (key == last_render_key) return;
            repo_list.remove_all ();
            last_render_key = key;
            if (repos.get_length () == 0) {
                show_state ("folder-open-symbolic", "No repositories yet",
                    error.length > 0 ? error : "This GitHub account has no repositories RepoBar can read.", false);
                return;
            }
            if (scope == 0 && filter == 0 && search_entry.get_text ().strip ().length == 0 && show_contributions &&
                has_object (snapshot, "contributions")) {
                var graph = build_contributions (snapshot.get_object_member ("contributions"));
                if (graph != null) repo_list.append (new Gtk.ListBoxRow () { child = graph, activatable = false });
            }
            // For You leads the dashboard: pull requests waiting on your review and issues assigned to you.
            if (scope == 0 && filter == 0 && search_entry.get_text ().strip ().length == 0 && snapshot.has_member ("forYou")) {
                var for_you = build_for_you (snapshot.get_object_member ("forYou"));
                if (for_you != null) repo_list.append (new Gtk.ListBoxRow () { child = for_you, activatable = false });
            }
            var visible = new GenericArray<Json.Object> ();
            int recent = 0;
            for (int pass = 0; pass < (scope == 0 ? 2 : 1); pass++) {
                for (uint i = 0; i < repos.get_length (); i++) {
                    var repo = repos.get_object_element (i);
                    bool pinned = repo.get_string_member_with_default ("repoState", "visible") == "pinned";
                    // Dashboard: pins first, then the most recently updated repositories up to the limit.
                    if (scope == 0 && ((pass == 0) != pinned)) continue;
                    if (scope == 0 && pass == 1 && recent >= dashboard_limit) continue;
                    if (matches_filter (repo)) {
                        visible.add (repo);
                        if (scope == 0 && pass == 1) recent++;
                    }
                }
            }
            if (scope == 2) visible.sort_with_data (compare_severity);
            else if (scope != 0 && sort_order != "activity") visible.sort_with_data (compare_repos);
            int shown = (int) visible.length;
            // Dashboard with pins: label the two groups so pinned repositories read as a deliberate list.
            int pinned_shown = 0;
            if (scope == 0) {
                for (int i = 0; i < shown; i++) {
                    if (visible[i].get_string_member_with_default ("repoState", "visible") == "pinned") pinned_shown++;
                }
            }
            bool grouped = pinned_shown > 0 && pinned_shown < shown;
            for (int i = 0; i < shown; i++) {
                var repo = visible[i];
                if (grouped && (i == 0 || i == pinned_shown)) {
                    var heading = new Gtk.Label (i == 0 ? "Pinned" : "Recently updated") { xalign = 0, margin_start = 4 };
                    heading.add_css_class ("section-title");
                    heading.add_css_class ("group-heading");
                    repo_list.append (new Gtk.ListBoxRow () { child = heading, activatable = false, focusable = false });
                }
                var row = new Gtk.ListBoxRow () { child = build_card (repo) };
                row.set_data<string> ("url", repo.get_string_member_with_default ("url", ""));
                row.update_property (Gtk.AccessibleProperty.LABEL, repo.get_string_member_with_default ("name", ""), -1);
                repo_list.append (row);
            }
            int listed = 0;
            for (uint i = 0; i < repos.get_length (); i++) if (matches_filter_in (repos.get_object_element (i), 3)) listed++;
            if (scope == 0 && shown > 0 && listed > shown) {
                var more = new Gtk.Button.with_label ("Show all %d repositories".printf (listed)) { halign = Gtk.Align.CENTER };
                more.add_css_class ("flat");
                more.add_css_class ("show-all");
                more.clicked.connect (() => scope_buttons[3].set_active (true));
                repo_list.append (new Gtk.ListBoxRow () { child = more, activatable = false });
            }
            if (shown == 0) {
                if (filter == 3 && local_root.length == 0) {
                    show_state ("folder-symbolic", "No projects folder",
                        "Choose the folder that holds your clones in RepoBar Settings → Local Checkouts.", false);
                    last_render_key = key;
                    return;
                }
                bool searching = search_entry.get_text ().strip ().length > 0 || filter != 0;
                show_state (searching ? "edit-find-symbolic" : scope == 2 ? "emblem-ok-symbolic" : "starred-symbolic",
                    searching ? "No matching repositories" : scope == 2 ? "Nothing needs attention" : "No pinned repositories",
                    searching ? "Try another search or filter." : scope == 2 ? "No failing CI, open issues or pull requests."
                        : "Pin a repository with its star to keep it on the dashboard.", false);
                last_render_key = key;
            }
        }

        /* Panel dot: red while default-branch CI fails, yellow with a count while runs are pending, green when a pull
           request merged within the configured window (an hour by default), and hidden when nothing is going on. */
        private void update_panel (int prs, int issues, int pending, GLib.DateTime? last_merge,
                                   string last_merge_repo, int repo_count, bool stale) {
            panel_prs.set_text (prs.to_string ());
            panel_issues.set_text (issues.to_string ());
            int64 merge_age = last_merge != null ? (GLib.get_real_time () - last_merge.to_unix () * 1000000) / 1000000 : -1;
            bool merged_recently = merge_age >= 0 && merge_age <= merge_window_minutes * 60;
            // Yellow counts workflow runs in progress; green marks a recent merge. Failing CI is left to notifications.
            panel_alert.remove_css_class ("alert-good");
            string status = "";
            if (merged_recently) {
                panel_alert.set_text ("●");
                panel_alert.add_css_class ("alert-good");
            }
            panel_alert.set_visible (merged_recently);
            if (pending > 0) {
                panel_running.set_text ("● %d".printf (pending));
                status += " · %d workflow run%s in progress".printf (pending, pending == 1 ? "" : "s");
            }
            panel_running.set_visible (pending > 0);
            if (running_summary.length > 0) status += "\n" + running_summary;
            if (merged_recently) status += " · merged %s %d min ago".printf (last_merge_repo, (int) (merge_age / 60));
            if (stale) panel.add_css_class ("stale"); else panel.remove_css_class ("stale");
            panel.set_tooltip_text ("GitHub%s · %d repositories · %d open pull requests · %d open issues%s%s\nMiddle-click to refresh".printf (
                account.length > 0 ? " · " + account : "", repo_count, prs, issues, status, stale ? " · cached" : ""));
        }

        /* Attention: failing CI first, then the most open work (a pull request weighs twice an issue). */
        private static int compare_severity (Json.Object a, Json.Object b) {
            bool fa = ci_failing (a);
            bool fb = ci_failing (b);
            if (fa != fb) return fa ? -1 : 1;
            int64 wa = 2 * a.get_int_member_with_default ("openPullRequests", 0) + a.get_int_member_with_default ("openIssues", 0);
            int64 wb = 2 * b.get_int_member_with_default ("openPullRequests", 0) + b.get_int_member_with_default ("openIssues", 0);
            return wa == wb ? 0 : (wb > wa ? 1 : -1);
        }

        private int compare_repos (Json.Object a, Json.Object b) {
            string member = sort_order == "prs" ? "openPullRequests" : sort_order == "issues" ? "openIssues" :
                sort_order == "stars" ? "stars" : "";
            if (member.length > 0) {
                int64 difference = b.get_int_member_with_default (member, 0) - a.get_int_member_with_default (member, 0);
                if (difference != 0) return difference > 0 ? 1 : -1;
            }
            if (sort_order == "pinned") {
                bool pa = a.get_string_member_with_default ("repoState", "") == "pinned";
                bool pb = b.get_string_member_with_default ("repoState", "") == "pinned";
                if (pa != pb) return pa ? -1 : 1;
                return 0;
            }
            return member.length > 0 ? 0 : strcmp (a.get_string_member_with_default ("name", "").casefold (),
                b.get_string_member_with_default ("name", "").casefold ());
        }

        private void restore_ui_state () {
            var file = new KeyFile ();
            try {
                file.load_from_file (ui_state_path, KeyFileFlags.NONE);
                int saved_scope = file.get_integer ("panel", "scope");
                int saved_filter = file.get_integer ("panel", "filter");
                if (saved_scope >= 0 && saved_scope < SCOPES.length) scope_buttons[saved_scope].set_active (true);
                if (saved_filter > 0 && saved_filter < FILTERS.length) filter_checks[saved_filter].set_active (true);
            } catch (Error e) {
                // First run: Dashboard, no filter.
            }
            try {
                file.load_from_file (ui_state_path, KeyFileFlags.NONE);
                contributions_expanded = file.get_boolean ("panel", "contributionsExpanded");
            } catch (Error e) {
                // The contribution graph starts collapsed.
            }
        }

        private void save_ui_state () {
            var file = new KeyFile ();
            file.set_integer ("panel", "scope", scope);
            file.set_integer ("panel", "filter", filter);
            file.set_boolean ("panel", "contributionsExpanded", contributions_expanded);
            try {
                DirUtils.create_with_parents (GLib.Path.get_dirname (ui_state_path), 0700);
                file.save_to_file (ui_state_path);
            } catch (Error e) {
                // Remembering the tab is a convenience only.
            }
        }

        /* Settings changes from the Settings window or CLI re-read the cached snapshot without a GitHub request. */
        private void watch_settings () {
            try {
                var directory = File.new_for_path (GLib.Path.build_filename (Environment.get_user_config_dir (), "mseries", "repobar"));
                DirUtils.create_with_parents (directory.get_path (), 0700);
                settings_monitor = directory.monitor_directory (FileMonitorFlags.WATCH_MOVES);
                uint pending = 0;
                settings_monitor.changed.connect ((file, other, event) => {
                    string name = (other ?? file).get_basename ();
                    if (file.get_basename () != "settings.json" && name != "settings.json") return;
                    settings_generation++;
                    clear_snapshot_state ();
                    show_state ("content-loading-symbolic", "Loading repositories…", "", false);
                    if (pending != 0) Source.remove (pending);
                    pending = Timeout.add (200, () => {
                        pending = 0;
                        if (read_panel_enabled () != panel_enabled) apply_panel_enabled ();
                        else if (panel_enabled) load_snapshot ();
                        return Source.REMOVE;
                    });
                });
            } catch (Error e) {
                // Changes still apply at the next scheduled read.
            }
        }

        private delegate void UndoAction ();
        private delegate void LayoutAction ();

        private void show_toast (string title, owned UndoAction? undo) {
            if (toast != null) {
                toast.withdraw ();
                list_overlay.remove_overlay (toast);
            }
            var next = new Granite.Toast (title) { valign = Gtk.Align.END, halign = Gtk.Align.CENTER };
            if (undo != null) {
                next.set_default_action ("Undo");
                next.default_action.connect (() => undo ());
            }
            next.dismissed.connect (() => {
                if (toast == next) {
                    list_overlay.remove_overlay (next);
                    toast = null;
                }
            });
            list_overlay.add_overlay (next);
            toast = next;
            next.send_notification ();
        }

        private Gtk.Widget? build_contributions (Json.Object contributions) {
            if (!contributions.has_member ("weeks")) return null;
            var weeks = contributions.get_array_member ("weeks");
            if (weeks.get_length () == 0) return null;
            int64 total = contributions.get_int_member_with_default ("total", 0);
            int64 week_total = 0;
            var last = weeks.get_array_element (weeks.get_length () - 1);
            for (uint i = 0; i < last.get_length (); i++) week_total += last.get_array_element (i).get_int_element (1);
            string full = "%s this week · %s this year".printf (group_digits (week_total), group_digits (total));

            // Collapsed (the default) is a single line: heading, one mark per week, and this week's count.
            // Clicking the heading expands it to the day-by-day calendar; clicking the calendar opens the profile.
            var card = new Gtk.Box (Gtk.Orientation.VERTICAL, 4);
            card.add_css_class ("repo-card");
            var head = new Gtk.Box (Gtk.Orientation.HORIZONTAL, 6);
            head.set_cursor_from_name ("pointer");
            var chevron = new Gtk.Image.from_icon_name ("pan-end-symbolic") { pixel_size = 12, opacity = 0.55 };
            head.append (chevron);
            var title = new Gtk.Label ("Contributions") { xalign = 0 };
            title.add_css_class ("section-title");
            head.append (title);
            var graph = new ContributionGraph (weeks, contribution_style, true) { valign = Gtk.Align.CENTER };
            var summary = new Gtk.Label ("") { xalign = 1, hexpand = true };
            summary.add_css_class ("caption");
            summary.add_css_class ("dim-label");
            summary.add_css_class ("numeric");
            head.append (summary);
            card.append (head);
            var open_profile = new Gtk.GestureClick () { button = 1 };
            open_profile.released.connect (() => {
                if (contributions_expanded) open_url ("https://" + host + "/" + account, graph);
            });
            graph.add_controller (open_profile);

            LayoutAction layout = () => {
                if (graph.get_parent () == card) card.remove (graph);
                else if (graph.get_parent () == head) head.remove (graph);
                graph.set_compact (!contributions_expanded);
                if (contributions_expanded) {
                    card.append (graph);
                    graph.set_tooltip_text (null);
                } else {
                    head.insert_child_after (graph, title);
                }
                graph.margin_start = contributions_expanded ? 0 : 4;
                summary.hexpand = contributions_expanded;
                summary.set_text (contributions_expanded ? full : "%s this week".printf (group_digits (week_total)));
                chevron.icon_name = contributions_expanded ? "pan-down-symbolic" : "pan-end-symbolic";
                head.set_tooltip_text (contributions_expanded ? "Collapse to one line" : full + "\nClick to show every day");
            };
            layout ();
            var toggle = new Gtk.GestureClick () { button = 1 };
            toggle.released.connect (() => {
                contributions_expanded = !contributions_expanded;
                save_ui_state ();
                layout ();
            });
            head.add_controller (toggle);
            card.update_property (Gtk.AccessibleProperty.LABEL, "Contributions: " + full, -1);
            return card;
        }

        private static string group_digits (int64 value) {
            string digits = value.to_string ();
            var grouped = new StringBuilder ();
            for (int i = 0; i < digits.length; i++) {
                if (i > 0 && (digits.length - i) % 3 == 0) grouped.append_c (',');
                grouped.append_c (digits[i]);
            }
            return grouped.str;
        }

        private Gtk.Widget? build_for_you (Json.Object for_you) {
            string[] keys = { "reviews", "assigned" };
            string[] titles = { "Review requested", "Assigned to you" };
            string[] icons = { kind_icon ("pull"), kind_icon ("issue") };
            string[] more_urls = { "/pulls/review-requested", "/issues/assigned" };
            Gtk.Box? card = null;
            for (int k = 0; k < keys.length; k++) {
                if (!for_you.has_member (keys[k])) continue;
                var group = for_you.get_object_member (keys[k]);
                int64 count = group.get_int_member_with_default ("count", 0);
                if (count <= 0) continue;
                if (card == null) {
                    card = new Gtk.Box (Gtk.Orientation.VERTICAL, 2);
                    card.add_css_class ("repo-card");
                    card.add_css_class ("for-you");
                }
                var head = new Gtk.Box (Gtk.Orientation.HORIZONTAL, 6) { margin_top = card.get_first_child () != null ? 4 : 0 };
                var title = new Gtk.Label (titles[k]) { xalign = 0, hexpand = true };
                title.add_css_class ("section-title");
                head.append (title);
                head.append (count_pill ((int) count, "", count.to_string () + " waiting"));
                card.append (head);
                var items = group.get_array_member ("items");
                for (uint i = 0; i < items.get_length (); i++) {
                    var item = items.get_object_element (i);
                    string repo = item.get_string_member_with_default ("repo", "");
                    string repo_short = repo.contains ("/") ? repo.substring (repo.index_of ("/") + 1) : repo;
                    card.append (link_row (icons[k], item.get_string_member_with_default ("title", ""),
                        repo_short + " #" + item.get_int_member_with_default ("number", 0).to_string (),
                        item.get_string_member_with_default ("url", "")));
                }
                if (count > items.get_length ()) {
                    card.append (link_row ("view-more-symbolic", "See all " + count.to_string () + " on GitHub", "",
                        "https://" + host + more_urls[k]));
                }
            }
            return card;
        }

        /* Desktop notification when default-branch CI starts failing or recovers. The first snapshot after login
         * only records states (persisted in the cache) so nothing old is announced again. */
        private void notify_ci_changes (Json.Array repos) {
            string path = GLib.Path.build_filename (Environment.get_user_cache_dir (), "mseries", "repobar", "ci-states.json");
            var previous = new HashTable<string, string> (str_hash, str_equal);
            bool have_previous = false;
            try {
                string text;
                FileUtils.get_contents (path, out text);
                var parser = new Json.Parser ();
                parser.load_from_data (text);
                var saved = parser.get_root ().get_object ();
                foreach (var name in saved.get_members ()) previous.insert (name, saved.get_string_member (name));
                have_previous = true;
            } catch (Error e) {
                // First run: record only.
            }
            var current = new Json.Object ();
            string[] failed = {};
            string[] fixed = {};
            string first_url = "";
            for (uint i = 0; i < repos.get_length (); i++) {
                var repo = repos.get_object_element (i);
                string name = repo.get_string_member_with_default ("name", "");
                string ci = repo.get_string_member_with_default ("ci", "UNKNOWN");
                current.set_string_member (name, ci);
                if (!have_previous || !previous.contains (name) || repo.get_boolean_member_with_default ("archived", false) ||
                    repo.get_string_member_with_default ("repoState", "visible") == "hidden") continue;
                string before = previous.get (name);
                bool was_bad = before == "FAILURE" || before == "ERROR";
                bool is_bad = ci == "FAILURE" || ci == "ERROR";
                string short_name = name.contains ("/") ? name.substring (name.index_of ("/") + 1) : name;
                if (is_bad && !was_bad) {
                    failed += short_name;
                    if (first_url.length == 0) first_url = repo.get_string_member_with_default ("url", "") + "/actions";
                } else if (was_bad && ci == "SUCCESS") {
                    fixed += short_name;
                }
            }
            try {
                DirUtils.create_with_parents (GLib.Path.get_dirname (path), 0700);
                var generator = new Json.Generator ();
                var root = new Json.Node (Json.NodeType.OBJECT);
                root.set_object (current);
                generator.set_root (root);
                FileUtils.set_contents_full (path, generator.to_data (null), -1, FileSetContentsFlags.CONSISTENT, 0600);
                FileUtils.chmod (path, 0600);
            } catch (Error e) {
                // Without saved states the next refresh records again instead of notifying.
            }
            if (!notify_ci) return;
            if (failed.length > 0) {
                send_notification (failed.length == 1 ? "CI failing on %s".printf (failed[0]) : "CI failing on %d repositories".printf (failed.length),
                    failed.length == 1 ? "The default branch's latest checks failed." : string.joinv (", ", failed),
                    failed.length == 1 ? first_url : "https://" + host + "/" + account, "dialog-error");
            }
            if (fixed.length > 0) {
                send_notification (fixed.length == 1 ? "CI passing again on %s".printf (fixed[0]) : "CI passing again on %d repositories".printf (fixed.length),
                    fixed.length == 1 ? "The default branch's latest checks passed." : string.joinv (", ", fixed), "", "emblem-ok");
            }
        }

        /* Desktop notification for each workflow run that finished since the last refresh, on any branch or pull
           request in recently active repositories. The first snapshot after login only records what was seen. */
        private void notify_workflow_runs (Json.Object snapshot) {
            if (!snapshot.has_member ("actions") || snapshot.get_member ("actions").get_node_type () != Json.NodeType.OBJECT) return;
            string path = GLib.Path.build_filename (Environment.get_user_cache_dir (), "mseries", "repobar", "run-states.json");
            var notified = new HashTable<string, bool> (str_hash, str_equal);
            bool have_previous = false;
            try {
                string text;
                FileUtils.get_contents (path, out text);
                var parser = new Json.Parser ();
                parser.load_from_data (text);
                var saved = parser.get_root ().get_object ().get_array_member ("notified");
                for (uint i = 0; i < saved.get_length (); i++) notified.insert (saved.get_string_element (i), true);
                have_previous = true;
            } catch (Error e) {
                // First run: record only.
            }
            var finished = snapshot.get_object_member ("actions").get_array_member ("finished");
            string[] passed = {};
            string[] failed = {};
            string first_url = "";
            var ids = new Json.Array ();
            for (uint i = 0; i < finished.get_length (); i++) {
                var run = finished.get_object_element (i);
                string id = run.get_int_member_with_default ("id", 0).to_string ();
                ids.add_string_element (id);
                if (!have_previous || notified.contains (id)) continue;
                string repo_name = run.get_string_member_with_default ("repo", "");
                string short_name = repo_name.contains ("/") ? repo_name.substring (repo_name.index_of ("/") + 1) : repo_name;
                string label = "%s · %s (%s)".printf (short_name, run.get_string_member_with_default ("name", "workflow"),
                    run.get_string_member_with_default ("branch", ""));
                string conclusion = run.get_string_member_with_default ("conclusion", "");
                if (conclusion == "success") passed += label;
                else if (conclusion == "failure" || conclusion == "timed_out" || conclusion == "startup_failure") {
                    failed += label;
                    if (first_url.length == 0) first_url = run.get_string_member_with_default ("url", "");
                }
            }
            // Keep a window of recent ids so a run is announced once, even after it leaves the finished list.
            foreach (var old in notified.get_keys ()) if (ids.get_length () < 200) ids.add_string_element (old);
            try {
                DirUtils.create_with_parents (GLib.Path.get_dirname (path), 0700);
                var generator = new Json.Generator ();
                var root = new Json.Node (Json.NodeType.OBJECT);
                var object = new Json.Object ();
                object.set_array_member ("notified", ids);
                root.set_object (object);
                generator.set_root (root);
                FileUtils.set_contents_full (path, generator.to_data (null), -1, FileSetContentsFlags.CONSISTENT, 0600);
                FileUtils.chmod (path, 0600);
            } catch (Error e) {
                // Without saved ids the next refresh records again instead of notifying.
            }
            if (!notify_workflows) return;
            if (failed.length > 0) {
                send_notification (failed.length == 1 ? "Workflow failed" : "%d workflows failed".printf (failed.length),
                    string.joinv ("\n", failed), failed.length == 1 ? first_url : "https://" + host + "/" + account, "dialog-error");
            }
            if (passed.length > 0) {
                send_notification (passed.length == 1 ? "Workflow passed" : "%d workflows passed".printf (passed.length),
                    string.joinv ("\n", passed), "", "emblem-ok");
            }
        }

        private void send_notification (string title, string body, string url, string urgency_icon) {
            string[] argv = { "notify-send", "--app-name=RepoBar", "--icon=github-symbolic", title, body };
            if (url.length > 0) argv = { "notify-send", "--app-name=RepoBar", "--icon=github-symbolic", "--action=open=Open on GitHub", title, body };
            try {
                var process = new Subprocess.newv (argv, SubprocessFlags.STDOUT_PIPE | SubprocessFlags.STDERR_SILENCE);
                process.communicate_utf8_async.begin (null, null, (obj, res) => {
                    try {
                        string output;
                        process.communicate_utf8_async.end (res, out output, null);
                        if (output != null && output.strip () == "open") new Gtk.UriLauncher (url).launch.begin (null, null);
                    } catch (Error e) {
                        // Dismissed or the notification server went away.
                    }
                });
            } catch (Error e) {
                // No notification server: the panel dot and chip still show the failure.
            }
        }

        /* RepoBar's own GitHub-style marks (elementary has no issue/pull request/commit icons), with stock fallbacks. */
        private static string kind_icon (string kind) {
            string own = kind == "pull" ? "mseries-repobar-pull-symbolic" : kind == "issue" ? "mseries-repobar-issue-symbolic" :
                kind == "commit" ? "mseries-repobar-commit-symbolic" : "";
            if (own.length > 0 && Gtk.IconTheme.get_for_display (Gdk.Display.get_default ()).has_icon (own)) return own;
            return kind == "pull" ? "mail-send-receive-symbolic" : kind == "issue" ? "dialog-information-symbolic" :
                kind == "release" ? "starred-symbolic" : "document-open-recent-symbolic";
        }

        private static bool ci_failing (Json.Object repo) {
            string ci = repo.get_string_member_with_default ("ci", "");
            return ci == "FAILURE" || ci == "ERROR";
        }

        private static bool ci_pending (Json.Object repo) {
            string ci = repo.get_string_member_with_default ("ci", "");
            return ci == "PENDING" || ci == "EXPECTED";
        }

        private static bool needs_attention (Json.Object repo) {
            return ci_failing (repo) || repo.get_int_member_with_default ("openIssues", 0) > 0 ||
                repo.get_int_member_with_default ("openPullRequests", 0) > 0;
        }

        private bool matches_filter (Json.Object repo) {
            return matches_filter_in (repo, scope);
        }

        private bool matches_filter_in (Json.Object repo, int scope) {
            string state = repo.get_string_member_with_default ("repoState", "visible");
            bool all = scope == 3;
            if (!all && state == "hidden") return false;
            if (!all && !show_archived && repo.get_boolean_member_with_default ("archived", false)) return false;
            if (!all && !show_forks && repo.get_boolean_member_with_default ("fork", false)) return false;
            if (scope == 1 && state != "pinned") return false;
            if (scope == 2 && !needs_attention (repo)) return false;
            if (filter == 1 && repo.get_int_member_with_default ("openIssues", 0) == 0) return false;
            if (filter == 2 && repo.get_int_member_with_default ("openPullRequests", 0) == 0) return false;
            if (filter == 3 && !has_object (repo, "local")) return false;
            if (filter == 4 && !ci_failing (repo)) return false;
            string query = search_entry.get_text ().strip ().casefold ();
            if (query.length == 0) return true;
            string haystack = repo.get_string_member_with_default ("name", "") + " " +
                repo.get_string_member_with_default ("description", "") + " " +
                repo.get_string_member_with_default ("language", "");
            if (repo.has_member ("topics")) {
                var topics = repo.get_array_member ("topics");
                for (uint i = 0; i < topics.get_length (); i++) haystack += " " + topics.get_string_element (i);
            }
            return haystack.casefold ().contains (query);
        }

        private static bool has_object (Json.Object object, string member) {
            return object.has_member (member) && object.get_member (member).get_node_type () == Json.NodeType.OBJECT;
        }

        private void clear_snapshot_state () {
            last_snapshot_text = "";
            // Reset summaries, account tooltip, contribution graph and cards together.
            render_snapshot (new Json.Object ());
        }

        private void render_cached () {
            // Disk snapshots must pass the helper's resolved-account validation first.
            if (last_snapshot_text.length == 0) return;
            try {
                var parser = new Json.Parser ();
                parser.load_from_data (last_snapshot_text);
                render_snapshot (parser.get_root ().get_object ());
            } catch (Error e) {
                // Keep the last rendered list while the first snapshot is loading.
            }
        }

        // ---- Repository cards ---------------------------------------------------------

        private Gtk.Widget build_card (Json.Object repo) {
            string full_name = repo.get_string_member_with_default ("name", "Repository");
            string url = repo.get_string_member_with_default ("url", "");
            string ci = repo.get_string_member_with_default ("ci", "UNKNOWN");
            string state = repo.get_string_member_with_default ("repoState", "visible");
            int prs = (int) repo.get_int_member_with_default ("openPullRequests", 0);
            int issues = (int) repo.get_int_member_with_default ("openIssues", 0);
            int slash = full_name.index_of ("/");
            string owner = slash > 0 ? full_name.substring (0, slash) : "";
            string short_name = slash > 0 ? full_name.substring (slash + 1) : full_name;

            var card = new Gtk.Box (Gtk.Orientation.VERTICAL, 4);
            card.add_css_class ("repo-card");

            // The summary (everything but the details pane) opens the repository; right-click for preferences.
            var summary = new Gtk.Box (Gtk.Orientation.VERTICAL, 3);
            summary.set_cursor_from_name ("pointer");
            var open_click = new Gtk.GestureClick () { button = 1 };
            open_click.released.connect (() => open_url (url, summary));
            summary.add_controller (open_click);
            card.append (summary);

            var head = new Gtk.Box (Gtk.Orientation.HORIZONTAL, 6);
            var dot = new Gtk.Label ("●") { valign = Gtk.Align.CENTER };
            dot.add_css_class (ci_css (ci));
            dot.set_tooltip_text (ci_description (ci));
            dot.update_property (Gtk.AccessibleProperty.LABEL, ci_description (ci), -1);
            head.append (dot);
            var name = new Gtk.Label (short_name) { xalign = 0, ellipsize = Pango.EllipsizeMode.END };
            name.add_css_class ("repo-name");
            name.set_tooltip_text (full_name + (repo.get_string_member_with_default ("description", "").length > 0
                ? "\n" + repo.get_string_member_with_default ("description", "") : ""));
            head.append (name);
            if (owner.length > 0 && owner != account) {
                var owner_label = new Gtk.Label (owner) { ellipsize = Pango.EllipsizeMode.END, valign = Gtk.Align.BASELINE_CENTER };
                owner_label.add_css_class ("repo-owner");
                head.append (owner_label);
            }
            if (repo.get_boolean_member_with_default ("private", false)) {
                var padlock = new Gtk.Image.from_icon_name ("system-lock-screen-symbolic") { pixel_size = 12, tooltip_text = "Private" };
                padlock.add_css_class ("dim-label");
                head.append (padlock);
            }
            string pages = repo.get_string_member_with_default ("pagesUrl", "");
            string homepage = repo.get_string_member_with_default ("homepage", "");
            string site = pages.length > 0 ? pages : homepage;
            if (site.length > 0) {
                // Globe right of the name: the GitHub Pages site, or the repository's website when it has no Pages.
                string globe = Gtk.IconTheme.get_for_display (Gdk.Display.get_default ()).has_icon ("mseries-repobar-globe-symbolic")
                    ? "mseries-repobar-globe-symbolic" : "web-browser-symbolic";
                var site_button = new Gtk.Button.from_icon_name (globe) {
                    valign = Gtk.Align.CENTER,
                    tooltip_text = (pages.length > 0 ? "Open GitHub Pages site" : "Open website") + "\n" + site
                };
                site_button.add_css_class ("flat");
                site_button.add_css_class ("compact");
                site_button.add_css_class ("site-link");
                site_button.update_property (Gtk.AccessibleProperty.LABEL,
                    (pages.length > 0 ? "Open GitHub Pages site for " : "Open website for ") + short_name, -1);
                site_button.clicked.connect (() => open_url (site, site_button));
                head.append (site_button);
            }
            if (state == "hidden") {
                var hidden = new Gtk.Image.from_icon_name ("view-conceal-symbolic") {
                    pixel_size = 12, tooltip_text = "Hidden from the dashboard · right-click to show"
                };
                hidden.add_css_class ("dim-label");
                head.append (hidden);
            }
            head.append (new Gtk.Box (Gtk.Orientation.HORIZONTAL, 0) { hexpand = true });
            head.append (count_pill (prs, kind_icon ("pull"), "%d open pull request%s".printf (prs, prs == 1 ? "" : "s")));
            head.append (count_pill (issues, kind_icon ("issue"), "%d open issue%s".printf (issues, issues == 1 ? "" : "s")));
            head.append (build_pin_button (full_name, state));
            var details_toggle = new Gtk.ToggleButton () {
                icon_name = "pan-end-symbolic", valign = Gtk.Align.CENTER,
                tooltip_text = "Pull requests, issues, CI, releases and more"
            };
            details_toggle.add_css_class ("flat");
            details_toggle.add_css_class ("compact");
            details_toggle.add_css_class ("disclosure");
            details_toggle.update_property (Gtk.AccessibleProperty.LABEL, "Details for " + full_name, -1);
            head.append (details_toggle);
            summary.append (head);

            summary.append (build_meta_row (repo));
            var activity = build_activity_row (repo);
            if (activity != null) summary.append (activity);
            var local = build_local_row (repo);
            if (local != null) summary.append (local);

            string local_path = has_object (repo, "local") ? repo.get_object_member ("local").get_string_member_with_default ("path", "") : "";
            card.append (build_details (full_name, url, details_toggle,
                repo.has_member ("localCheckouts") ? repo.get_array_member ("localCheckouts") : null));

            var context = new Gtk.GestureClick () { button = 3 };
            context.pressed.connect ((n, x, y) => show_card_menu (card, full_name, url, site, state, local_path, x, y));
            card.add_controller (context);
            return card;
        }

        /* A counter led by its kind's icon, like GitHub's own; no icon gives a plain number. */
        private static Gtk.Widget count_pill (int count, string icon, string description) {
            var pill = new Gtk.Box (Gtk.Orientation.HORIZONTAL, 3) { valign = Gtk.Align.CENTER, tooltip_text = description };
            pill.add_css_class ("count");
            pill.add_css_class ("numeric");
            if (count == 0) pill.add_css_class ("zero");
            if (icon.length > 0) pill.append (new Gtk.Image.from_icon_name (icon) { pixel_size = 10 });
            pill.append (new Gtk.Label (count.to_string ()));
            pill.update_property (Gtk.AccessibleProperty.LABEL, description, -1);
            return pill;
        }

        private Gtk.Widget build_pin_button (string name, string state) {
            bool pinned = state == "pinned";
            var star = new Gtk.Button.from_icon_name (pinned ? "starred-symbolic" : "non-starred-symbolic") {
                tooltip_text = pinned ? "Unpin from dashboard" : "Pin to dashboard", valign = Gtk.Align.CENTER
            };
            star.add_css_class ("flat");
            star.add_css_class ("compact");
            star.add_css_class (pinned ? "pinned-star" : "pin-off");
            star.update_property (Gtk.AccessibleProperty.LABEL, star.tooltip_text, -1);
            star.clicked.connect (() => change_repo_state.begin (name, pinned ? "unpin" : "pin"));
            return star;
        }

        /* Branch, release, stars, then default-branch commits per window in CodexBar's short window labels. */
        private static Gtk.Widget build_meta_row (Json.Object repo) {
            var row = new Gtk.Box (Gtk.Orientation.HORIZONTAL, 6);
            string[] parts = {};
            string branch = repo.get_string_member_with_default ("branch", "");
            string release = repo.get_string_member_with_default ("release", "");
            string language = repo.get_string_member_with_default ("language", "");
            if (branch.length > 0) parts += branch;
            if (release.length > 0) parts += release;
            parts += "★ " + repo.get_int_member_with_default ("stars", 0).to_string ();
            if (language.length > 0) parts += language;
            if (repo.get_boolean_member_with_default ("archived", false)) parts += "archived";
            var meta = new Gtk.Label (string.joinv (" · ", parts)) { xalign = 0, hexpand = true, ellipsize = Pango.EllipsizeMode.END };
            meta.add_css_class ("caption");
            meta.add_css_class ("dim-label");
            row.append (meta);
            if (has_object (repo, "commitCounts")) {
                var counts = repo.get_object_member ("commitCounts");
                string[] windows = { "1h", "24h", "30d" };
                string[] names = { "1H", "1D", "30D" };
                for (int i = 0; i < windows.length; i++) {
                    int64 value = counts.get_int_member_with_default (windows[i], -1);
                    var label = new Gtk.Label (names[i]);
                    label.add_css_class ("window-name");
                    row.append (label);
                    var number = new Gtk.Label (value >= 0 ? value.to_string () : "—") { xalign = 0, width_chars = 3 };
                    number.add_css_class ("caption");
                    number.add_css_class ("numeric");
                    if (value <= 0) number.add_css_class ("dim-label");
                    row.append (number);
                }
                row.set_tooltip_text ("Commits to the default branch in the last hour, day and 30 days");
            }
            return row;
        }

        private Gtk.Widget? build_activity_row (Json.Object repo) {
            if (!has_object (repo, "recentActivity")) return null;
            var activity = repo.get_object_member ("recentActivity");
            string title = activity.get_string_member_with_default ("title", "");
            if (title.length == 0) return null;
            string kind = activity.get_string_member_with_default ("kind", "activity");
            string icon = kind_icon (kind.contains ("pull") ? "pull" : kind.contains ("issue") ? "issue" :
                kind.contains ("release") ? "release" : "commit");
            string when = relative_time (activity.get_string_member_with_default ("updatedAt", ""));
            return link_row (icon, title, when.length > 0 && when != activity.get_string_member_with_default ("updatedAt", "")
                ? when : kind,
                activity.get_string_member_with_default ("url", ""));
        }

        private Gtk.Widget? build_local_row (Json.Object repo) {
            if (!has_object (repo, "local")) return null;
            var local = repo.get_object_member ("local");
            int behind = (int) local.get_int_member_with_default ("behind", 0);
            int ahead = (int) local.get_int_member_with_default ("ahead", 0);
            int dirty = (int) local.get_int_member_with_default ("dirtyFileCount", 0);
            var row = new Gtk.Box (Gtk.Orientation.HORIZONTAL, 6);
            row.append (new Gtk.Image.from_icon_name ("folder-symbolic") { pixel_size = 12, opacity = 0.7 });
            var branch = new Gtk.Label ("Local · " + local.get_string_member_with_default ("branch", "detached")) {
                xalign = 0, hexpand = true, ellipsize = Pango.EllipsizeMode.END
            };
            branch.add_css_class ("caption");
            branch.add_css_class ("dim-label");
            row.append (branch);
            if (dirty > 0) row.append (status_text ("%d modified".printf (dirty), "text-low"));
            if (behind > 0) row.append (status_text ("↓%d".printf (behind), "text-low"));
            if (ahead > 0) row.append (status_text ("↑%d".printf (ahead), "dim-label"));
            if (dirty == 0 && behind == 0 && ahead == 0) row.append (status_text ("up to date", "dim-label"));
            int others = repo.has_member ("localCheckouts") ? (int) repo.get_array_member ("localCheckouts").get_length () - 1 : 0;
            if (others > 0) {
                var more = status_text ("+%d".printf (others), "dim-label");
                more.add_css_class ("count");
                more.set_tooltip_text ("%d more checkout%s (worktrees or clones) · see Details → Checkouts".printf (others, others == 1 ? "" : "s"));
                row.append (more);
            }
            string path = local.get_string_member_with_default ("path", "");
            var button = new Gtk.Button () { child = row, tooltip_text = "Open %s in Files".printf (path) };
            button.add_css_class ("flat");
            button.add_css_class ("link-row");
            button.clicked.connect (() => open_folder (path, button));
            return button;
        }

        /* One local checkout: folder name and branch, its state, and a terminal button; the row opens the folder. */
        /* Worktrees are usually named "<repo>-<topic>"; show just the topic so the names fit and stay distinct. */
        private static string checkout_label (string path, string repo_name) {
            string folder = GLib.Path.get_basename (path);
            string repo = repo_name.contains ("/") ? repo_name.substring (repo_name.last_index_of ("/") + 1) : repo_name;
            string lower = folder.casefold ();
            string prefix = repo.casefold ();
            if (lower == prefix) return "main checkout";
            if (lower.has_prefix (prefix) && folder.length > repo.length + 1) {
                unichar separator = folder.get_char (repo.length);
                if (separator == '-' || separator == '_' || separator == '.') return folder.substring (repo.length + 1);
            }
            return folder;
        }

        private static Gtk.Widget checkout_row (Json.Object checkout, string repo_name) {
            string path = checkout.get_string_member_with_default ("path", "");
            int dirty = (int) checkout.get_int_member_with_default ("dirtyFileCount", 0);
            int behind = (int) checkout.get_int_member_with_default ("behind", 0);
            int ahead = (int) checkout.get_int_member_with_default ("ahead", 0);
            var line = new Gtk.Box (Gtk.Orientation.HORIZONTAL, 4);
            var content = new Gtk.Box (Gtk.Orientation.HORIZONTAL, 6);
            content.append (new Gtk.Image.from_icon_name ("folder-symbolic") { pixel_size = 12, opacity = 0.7 });
            string label = checkout_label (path, repo_name);
            var folder = new Gtk.Label (label) {
                xalign = 0, ellipsize = Pango.EllipsizeMode.END, max_width_chars = 18, width_chars = 12
            };
            if (label == "main checkout") folder.add_css_class ("dim-label");
            folder.add_css_class ("caption");
            content.append (folder);
            string branch_name = checkout.get_boolean_member_with_default ("detached", false) ? "detached" :
                checkout.get_string_member_with_default ("branch", "");
            var branch = new Gtk.Label (branch_name) { xalign = 0, hexpand = true, ellipsize = Pango.EllipsizeMode.END };
            branch.add_css_class ("caption");
            branch.add_css_class ("dim-label");
            content.append (branch);
            if (dirty > 0) content.append (status_text ("%d modified".printf (dirty), "text-low"));
            if (behind > 0) content.append (status_text ("↓%d".printf (behind), "text-low"));
            if (ahead > 0) content.append (status_text ("↑%d".printf (ahead), "dim-label"));
            if (dirty == 0 && behind == 0 && ahead == 0) content.append (status_text ("clean", "dim-label"));
            var open = new Gtk.Button () {
                child = content, hexpand = true, tooltip_text = "%s\n%s\nOpen in Files".printf (path, branch_name)
            };
            open.add_css_class ("flat");
            open.add_css_class ("link-row");
            open.clicked.connect (() => open_folder (path, open));
            line.append (open);
            var terminal = new Gtk.Button.from_icon_name ("utilities-terminal-symbolic") { tooltip_text = "Open in Terminal", valign = Gtk.Align.CENTER };
            terminal.add_css_class ("flat");
            terminal.add_css_class ("compact");
            terminal.add_css_class ("dim-label");
            terminal.update_property (Gtk.AccessibleProperty.LABEL, "Open %s in Terminal".printf (GLib.Path.get_basename (path)), -1);
            terminal.clicked.connect (() => open_terminal (path, terminal));
            line.append (terminal);
            return line;
        }

        private static Gtk.Label status_text (string text, string css) {
            var label = new Gtk.Label (text);
            label.add_css_class ("caption");
            label.add_css_class ("numeric");
            label.add_css_class (css);
            return label;
        }

        /* A full-width flat row: icon, ellipsized title and an optional dim trailing caption; opens its link. */
        private static Gtk.Widget link_row (string icon, string title, string trailing, string url) {
            var content = new Gtk.Box (Gtk.Orientation.HORIZONTAL, 6);
            content.append (new Gtk.Image.from_icon_name (icon) { pixel_size = 12, opacity = 0.7 });
            var text = new Gtk.Label (title) { xalign = 0, hexpand = true, ellipsize = Pango.EllipsizeMode.END };
            text.add_css_class ("caption");
            content.append (text);
            if (trailing.length > 0) {
                var meta = new Gtk.Label (trailing) { ellipsize = Pango.EllipsizeMode.END, max_width_chars = 14 };
                meta.add_css_class ("caption");
                meta.add_css_class ("dim-label");
                content.append (meta);
            }
            if (url.length == 0) {
                content.margin_start = 4;
                return content;
            }
            var button = new Gtk.Button () { child = content, tooltip_text = title };
            button.add_css_class ("flat");
            button.add_css_class ("link-row");
            button.clicked.connect (() => open_url (url, button));
            return button;
        }

        private void show_card_menu (Gtk.Widget card, string name, string url, string site, string state, string local_path,
                                     double x, double y) {
            var box = new Gtk.Box (Gtk.Orientation.VERTICAL, 0) { margin_top = 4, margin_bottom = 4 };
            var popover = new Gtk.Popover () { child = box, has_arrow = false };
            popover.set_parent (card);
            popover.set_pointing_to ({ (int) x, (int) y, 1, 1 });
            popover.closed.connect (() => Idle.add (() => { popover.unparent (); return Source.REMOVE; }));
            box.append (menu_item ("Open on GitHub", () => open_url (url, card)));
            if (site.length > 0) box.append (menu_item ("Open Website", () => open_url (site, card)));
            box.append (menu_item ("Copy Link", () => card.get_clipboard ().set_text (url)));
            box.append (new Gtk.Separator (Gtk.Orientation.HORIZONTAL) { margin_top = 3, margin_bottom = 3 });
            if (local_path.length > 0) {
                box.append (menu_item ("Open Folder", () => open_folder (local_path, card)));
                box.append (menu_item ("Open in Terminal", () => open_terminal (local_path, card)));
                box.append (new Gtk.Separator (Gtk.Orientation.HORIZONTAL) { margin_top = 3, margin_bottom = 3 });
            } else if (local_root.length > 0) {
                box.append (menu_item ("Clone to %s".printf (GLib.Path.get_basename (local_root)), () => clone_repository.begin (name)));
                box.append (new Gtk.Separator (Gtk.Orientation.HORIZONTAL) { margin_top = 3, margin_bottom = 3 });
            }
            box.append (menu_item (state == "pinned" ? "Unpin from Dashboard" : "Pin to Dashboard",
                () => change_repo_state.begin (name, state == "pinned" ? "unpin" : "pin")));
            box.append (menu_item (state == "hidden" ? "Show Repository" : "Hide Repository",
                () => change_repo_state.begin (name, state == "hidden" ? "show" : "hide")));
            popover.popup ();
        }

        private static void open_folder (string path, Gtk.Widget source) {
            if (path.length == 0) return;
            popdown_from (source);
            new Gtk.FileLauncher (File.new_for_path (path)).launch.begin (null, null);
        }

        private static void open_terminal (string path, Gtk.Widget source) {
            if (path.length == 0) return;
            popdown_from (source);
            try {
                Process.spawn_async (path, { "io.elementary.terminal", "--working-directory=" + path }, null,
                    SpawnFlags.SEARCH_PATH | SpawnFlags.STDOUT_TO_DEV_NULL | SpawnFlags.STDERR_TO_DEV_NULL, null, null);
            } catch (Error e) {
                open_folder (path, source);
            }
        }

        private async void clone_repository (string name) {
            string short_name = name.contains ("/") ? name.substring (name.index_of ("/") + 1) : name;
            show_toast ("Cloning %s…".printf (short_name), null);
            try {
                var process = new Subprocess.newv (new string[] { executable, "--json", "local", "clone", name },
                    SubprocessFlags.STDOUT_PIPE | SubprocessFlags.STDERR_PIPE);
                string output;
                string error_text;
                yield process.communicate_utf8_async (null, null, out output, out error_text);
                var parser = new Json.Parser ();
                parser.load_from_data (output);
                var result = parser.get_root ().get_object ();
                if (!process.get_successful () || result.has_member ("error")) {
                    throw new IOError.FAILED (result.get_string_member_with_default ("error", error_text.strip ()));
                }
                string path = result.get_string_member_with_default ("path", "");
                show_toast ("Cloned %s".printf (short_name), null);
                if (path.length > 0) new Gtk.FileLauncher (File.new_for_path (path)).launch.begin (null, null);
                refresh ();
            } catch (Error e) {
                show_toast ("Couldn't clone %s".printf (short_name), null);
                subtitle_label.set_tooltip_text (e.message);
            }
        }

        private delegate void MenuAction ();

        private static Gtk.Widget menu_item (string label, owned MenuAction action) {
            var button = new Gtk.Button () { child = new Gtk.Label (label) { xalign = 0 } };
            button.add_css_class ("flat");
            button.add_css_class ("menuitem");
            button.clicked.connect (() => {
                var popover = button.get_ancestor (typeof (Gtk.Popover)) as Gtk.Popover;
                if (popover != null) popover.popdown ();
                action ();
            });
            return button;
        }

        // ---- Details pane: category chips, each fetched once on first selection ------------

        private Gtk.Widget build_details (string name, string url, Gtk.ToggleButton toggle, Json.Array? checkouts) {
            var revealer = new Gtk.Revealer () {
                transition_type = Gtk.RevealerTransitionType.SLIDE_DOWN, transition_duration = 120
            };
            var pane = new Gtk.Box (Gtk.Orientation.VERTICAL, 4) { margin_top = 4 };
            var chips = new Gtk.FlowBox () {
                selection_mode = Gtk.SelectionMode.NONE, max_children_per_line = 8, min_children_per_line = 4,
                column_spacing = 4, row_spacing = 4, homogeneous = false
            };
            chips.add_css_class ("detail-chips");
            var list = new Gtk.Box (Gtk.Orientation.VERTICAL, 1);
            list.add_css_class ("detail-list");
            list.set_visible (false);
            Gtk.ToggleButton? first = null;
            if (checkouts != null && checkouts.get_length () > 0) {
                // Local checkouts come from the last scan, so this tab needs no GitHub request.
                var chip = new Gtk.ToggleButton.with_label ("Checkouts %u".printf (checkouts.get_length ()));
                chip.add_css_class ("flat");
                first = chip;
                chip.toggled.connect (() => {
                    if (!chip.get_active ()) return;
                    list.set_visible (true);
                    clear_box (list);
                    for (uint i = 0; i < checkouts.get_length (); i++) list.append (checkout_row (checkouts.get_object_element (i), name));
                });
                chips.append (chip);
            }
            for (int i = 0; i < DETAIL_KEYS.length; i++) {
                string key = DETAIL_KEYS[i];
                var chip = new Gtk.ToggleButton.with_label (DETAIL_TITLES[i]);
                chip.add_css_class ("flat");
                if (first != null) chip.set_group (first); else first = chip;
                chip.toggled.connect (() => {
                    if (!chip.get_active ()) return;
                    list.set_visible (true);
                    load_repo_detail.begin (name, url, key, list);
                });
                chips.append (chip);
            }
            pane.append (chips);
            pane.append (list);
            revealer.set_child (pane);
            toggle.toggled.connect (() => {
                revealer.set_reveal_child (toggle.get_active ());
                toggle.set_icon_name (toggle.get_active () ? "pan-down-symbolic" : "pan-end-symbolic");
                if (toggle.get_active () && first != null && !first.get_active ()) first.set_active (true);
            });
            return revealer;
        }

        private async void load_repo_detail (string name, string repo_url, string key, Gtk.Box content) {
            clear_box (content);
            var loading = new Gtk.Box (Gtk.Orientation.HORIZONTAL, 7) { margin_start = 4 };
            var spinner = new Gtk.Spinner ();
            spinner.start ();
            loading.append (spinner);
            var loading_label = new Gtk.Label ("Loading…") { xalign = 0 };
            loading_label.add_css_class ("caption");
            loading_label.add_css_class ("dim-label");
            loading.append (loading_label);
            content.append (loading);
            try {
                var process = new Subprocess.newv (new string[] { executable, key, name, "--limit", "5" },
                    SubprocessFlags.STDOUT_PIPE | SubprocessFlags.STDERR_PIPE);
                string output;
                string error_text;
                yield process.communicate_utf8_async (null, null, out output, out error_text);
                if (!process.get_successful () && output.strip ().length == 0) {
                    throw new IOError.FAILED (error_text.strip ().length > 0 ? error_text.strip () : "GitHub data is unavailable");
                }
                var parser = new Json.Parser ();
                parser.load_from_data (output);
                render_repo_detail (key, parser.get_root (), repo_url, content);
            } catch (Error e) {
                clear_box (content);
                content.append (link_row ("dialog-error-symbolic", "Could not load " + key, "", ""));
                content.get_last_child ().set_tooltip_text (e.message);
            }
        }

        private void render_repo_detail (string key, Json.Node node, string repo_url, Gtk.Box content) {
            clear_box (content);
            if (key == "traffic" && node.get_node_type () == Json.NodeType.OBJECT) {
                var traffic = node.get_object ();
                content.append (traffic_row (traffic, "views", "Views", "visitors", repo_url + "/graphs/traffic"));
                content.append (traffic_row (traffic, "clones", "Clones", "cloners", repo_url + "/graphs/traffic"));
                return;
            }
            Json.Array? items = null;
            if (node.get_node_type () == Json.NodeType.ARRAY) {
                items = node.get_array ();
            } else if (key == "ci" && node.get_node_type () == Json.NodeType.OBJECT) {
                var object = node.get_object ();
                if (object.has_member ("workflow_runs")) items = object.get_array_member ("workflow_runs");
            }
            if (items == null || items.get_length () == 0) {
                string empty_text = items == null ? "Not available for this repository" :
                    key == "issues" ? "No open issues" :
                    key == "pulls" ? "No open pull requests" :
                    key == "ci" ? "No recent runs" :
                    key == "releases" ? "No releases" :
                    key == "activity" ? "No recent activity" :
                    key == "commits" ? "No recent commits" :
                    key == "branches" ? "No branches found" : "No tags found";
                var empty = new Gtk.Label (empty_text) { xalign = 0, margin_start = 4 };
                empty.add_css_class ("caption");
                empty.add_css_class ("dim-label");
                content.append (empty);
                return;
            }
            string icon = key == "pulls" ? kind_icon ("pull") :
                key == "issues" ? kind_icon ("issue") : key == "commits" ? kind_icon ("commit") :
                key == "ci" ? "emblem-ok-symbolic" :
                key == "releases" || key == "tags" ? "starred-symbolic" : "document-open-recent-symbolic";
            for (uint i = 0; i < items.get_length (); i++) {
                var item = items.get_object_element (i);
                string label = item.get_string_member_with_default ("title", "");
                if (label.length == 0) label = item.get_string_member_with_default ("name", "");
                if (label.length == 0) label = item.get_string_member_with_default ("tag_name", "");
                if (key == "commits" && item.has_member ("commit")) {
                    label = item.get_object_member ("commit").get_string_member_with_default ("message", label).split ("\n")[0];
                }
                string detail = item.get_string_member_with_default ("conclusion", "");
                if (detail.length == 0) detail = item.get_string_member_with_default ("status", "");
                string url = item.get_string_member_with_default ("html_url", "");
                if (key == "pulls" || key == "issues") {
                    int64 number = item.get_int_member_with_default ("number", 0);
                    if (number > 0) detail = "#" + number.to_string ();
                }
                if (key == "commits") detail = item.get_string_member_with_default ("sha", "").substring (0, int.min (7,
                    item.get_string_member_with_default ("sha", "").length));
                if (key == "branches" || key == "tags") {
                    string ref_name = item.get_string_member_with_default ("name", "");
                    if (ref_name.length > 0) url = repo_url + "/tree/" + Uri.escape_string (ref_name, null, true);
                    detail = "";
                }
                if (key == "activity") {
                    label = item.get_string_member_with_default ("type", "Repository activity").replace ("Event", "");
                    if (item.has_member ("actor")) {
                        label += " · " + item.get_object_member ("actor").get_string_member_with_default ("login", "");
                    }
                    detail = relative_time (item.get_string_member_with_default ("created_at", ""));
                    url = "";
                }
                if (label.length == 0) label = url.length > 0 ? url : "Repository item";
                var row = link_row (key == "ci" ? ci_run_icon (detail) : icon, label, detail.down (), url);
                content.append (row);
            }
        }

        /* One traffic series: label, 14-day bars, total and unique count; opens GitHub's traffic graph. */
        private static Gtk.Widget traffic_row (Json.Object traffic, string key, string title, string unique_word, string url) {
            var series = traffic.has_member (key) ? traffic.get_object_member (key) : new Json.Object ();
            int64 total = series.get_int_member_with_default ("count", 0);
            int64 uniques = series.get_int_member_with_default ("uniques", 0);
            var days = series.has_member (key) ? series.get_array_member (key) : new Json.Array ();
            var line = new Gtk.Box (Gtk.Orientation.HORIZONTAL, 6);
            var name = new Gtk.Label (title) { xalign = 0, width_chars = 6 };
            name.add_css_class ("window-name");
            line.append (name);
            line.append (new TrafficBars (days));
            var totals = new Gtk.Label ("%s · %s %s".printf (group_digits (total), group_digits (uniques), unique_word)) {
                xalign = 1, width_chars = 18
            };
            totals.add_css_class ("caption");
            totals.add_css_class ("numeric");
            line.append (totals);
            var button = new Gtk.Button () {
                child = line,
                tooltip_text = "%s in the last 14 days: %s from %s unique %s".printf (title, group_digits (total), group_digits (uniques), unique_word)
            };
            button.add_css_class ("flat");
            button.add_css_class ("link-row");
            button.clicked.connect (() => open_url (url, button));
            return button;
        }

        private static string ci_run_icon (string conclusion) {
            return conclusion == "failure" || conclusion == "cancelled" ? "dialog-error-symbolic" :
                conclusion == "success" ? "emblem-ok-symbolic" : "content-loading-symbolic";
        }

        private static string relative_time (string iso) {
            var time = new DateTime.from_iso8601 (iso, new TimeZone.utc ());
            if (time == null) return iso;
            int64 minutes = (new DateTime.now_utc ().to_unix () - time.to_unix ()) / 60;
            if (minutes < 60) return int64.max (0, minutes).to_string () + "m ago";
            if (minutes < 1440) return (minutes / 60).to_string () + "h ago";
            return (minutes / 1440).to_string () + "d ago";
        }

        private static void clear_box (Gtk.Box box) {
            while (box.get_first_child () != null) box.remove (box.get_first_child ());
        }

        private async void change_repo_state (string name, string action, bool undoing = false) {
            try {
                var process = new Subprocess.newv (new string[] { executable, action, name },
                    SubprocessFlags.STDOUT_PIPE | SubprocessFlags.STDERR_PIPE);
                string output;
                string error_text;
                yield process.communicate_utf8_async (null, null, out output, out error_text);
                if (!process.get_successful ()) throw new IOError.FAILED (error_text.strip ());
                read_snapshot.begin (false);
                if (!undoing) {
                    string short_name = name.contains ("/") ? name.substring (name.index_of ("/") + 1) : name;
                    string opposite = action == "pin" ? "unpin" : action == "unpin" ? "pin" : action == "hide" ? "show" : "hide";
                    string verb = action == "pin" ? "Pinned" : action == "unpin" ? "Unpinned" : action == "hide" ? "Hid" : "Showing";
                    show_toast ("%s %s".printf (verb, short_name), () => change_repo_state.begin (name, opposite, true));
                }
            } catch (Error e) {
                subtitle_label.set_text ("Could not update repository preference");
                subtitle_label.set_tooltip_text (e.message);
            }
        }

        private static string ci_description (string state) {
            switch (state) {
            case "SUCCESS": return "Default branch CI passing";
            case "FAILURE": return "Default branch CI failing";
            case "ERROR": return "Default branch CI errored";
            case "PENDING":
            case "EXPECTED": return "Default branch CI running";
            default: return "No CI status on the default branch";
            }
        }

        private static string ci_css (string state) {
            if (state == "SUCCESS") return "dot-ok";
            if (state == "FAILURE" || state == "ERROR") return "dot-bad";
            if (state == "PENDING" || state == "EXPECTED") return "dot-warn";
            return "dot-off";
        }

        /* Hooks for the headless render probe (probe/render-probe.vala). */
        public void probe_select_scope (string name) {
            for (int i = 0; i < SCOPES.length; i++) {
                if (SCOPES[i].down () == name.down ()) scope_buttons[i].set_active (true);
            }
        }

        private static void select_chip (Gtk.Widget widget, string label) {
            var chip = widget as Gtk.ToggleButton;
            if (chip != null && chip.label != null && chip.label.has_prefix (label)) { chip.set_active (true); return; }
            for (var child = widget.get_first_child (); child != null; child = child.get_next_sibling ()) select_chip (child, label);
        }

        public void probe_toast () {
            show_toast ("Hid dock", () => {});
        }

        public void probe_expand_first () {
            for (int i = 0; ; i++) {
                var row = repo_list.get_row_at_index (i);
                if (row == null) return;
                var card = row.get_child ();
                var head = card != null && card.get_first_child () != null ? card.get_first_child ().get_first_child () : null;
                var toggle = head != null ? head.get_last_child () as Gtk.ToggleButton : null;
                if (toggle != null) {
                    toggle.set_active (true);
                    var chip_name = Environment.get_variable ("RB_DETAIL");
                    if (chip_name != null) select_chip (card, chip_name);
                    return;
                }
            }
        }

        public override Gtk.Widget get_display_widget () {
            return panel;
        }

        public override Gtk.Widget? get_widget () {
            return menu;
        }

        public override void opened () {
            load_snapshot ();
        }

        public override void closed () {
        }
    }
}

namespace MSeries {
    /* Fourteen daily bars scaled to the busiest day, in the accent colour; empty days show a faint stub. */
    internal class TrafficBars : Gtk.DrawingArea {
        private int64[] counts = new int64[14];

        public TrafficBars (Json.Array days) {
            // GitHub lists only days with data; place each by its date, newest at the right.
            var today = new DateTime.now_utc ();
            for (uint i = 0; i < days.get_length (); i++) {
                var day = days.get_object_element (i);
                var stamp = new DateTime.from_iso8601 (day.get_string_member_with_default ("timestamp", ""), null);
                if (stamp == null) continue;
                int ago = (int) ((today.to_unix () - stamp.to_unix ()) / 86400);
                if (ago >= 0 && ago < 14) counts[13 - ago] += day.get_int_member_with_default ("count", 0);
            }
            add_css_class ("contribution-graph");
            content_height = 16;
            hexpand = true;
            set_draw_func (draw);
        }

        private void draw (Gtk.DrawingArea area, Cairo.Context cr, int width, int height) {
            var color = get_color ();
            int64 peak = 1;
            foreach (var count in counts) peak = int64.max (peak, count);
            double slot = width / 14.0;
            for (int i = 0; i < 14; i++) {
                double bar = counts[i] == 0 ? 1.5 : double.max (2, height * (double) counts[i] / peak);
                cr.set_source_rgba (color.red, color.green, color.blue, counts[i] == 0 ? 0.2 : 0.85);
                cr.rectangle (i * slot + 1, height - bar, slot - 2, bar);
                cr.fill ();
            }
        }
    }

    /* GitHub's contribution calendar: one column per week (newest at the right), as many weeks as fit,
     * shaded from the accent colour; hovering a mark names its date and count. Styles: "squares" (GitHub's
     * look), "dots" (smaller circles) and "fine" (toned periods). Compact mode is one row: a mark per week. */
    internal class ContributionGraph : Gtk.DrawingArea {
        private Json.Array weeks;
        private string style;
        private bool compact;
        private int cell;
        private int gap;

        public ContributionGraph (Json.Array weeks, string style, bool compact) {
            this.weeks = weeks;
            this.style = style == "squares" || style == "fine" ? style : "dots";
            cell = this.style == "squares" ? 9 : this.style == "fine" ? 3 : 6;
            gap = this.style == "squares" ? 2 : this.style == "fine" ? 3 : 2;
            add_css_class ("contribution-graph");
            hexpand = true;
            has_tooltip = true;
            set_draw_func (draw);
            query_tooltip.connect (on_tooltip);
            set_compact (compact);
        }

        public void set_compact (bool value) {
            compact = value;
            // A compact row keeps a hover target of at least 8 px even for fine dots.
            content_height = compact ? int.max (cell, 8) : 7 * (cell + gap) - gap;
            queue_draw ();
        }

        private int visible_weeks (int width) {
            return int.min ((int) weeks.get_length (), (width + gap) / (cell + gap));
        }

        private int64 week_total (Json.Array week) {
            int64 total = 0;
            for (uint d = 0; d < week.get_length (); d++) total += week.get_array_element (d).get_int_element (1);
            return total;
        }

        private void draw (Gtk.DrawingArea area, Cairo.Context cr, int width, int height) {
            var color = get_color ();
            int shown = visible_weeks (width);
            int offset = width - (shown * (cell + gap) - gap);
            uint first = weeks.get_length () - shown;
            // Empty days stay faintly visible so the grid (or row of periods) still reads as a calendar.
            double[] alphas = { style == "squares" ? 0.1 : 0.16, 0.35, 0.55, 0.78, 1.0 };
            if (compact) {
                int64 peak = 1;
                for (int w = 0; w < shown; w++) peak = int64.max (peak, week_total (weeks.get_array_element (first + w)));
                double top = (height - cell) / 2.0;
                for (int w = 0; w < shown; w++) {
                    int64 total = week_total (weeks.get_array_element (first + w));
                    int level = total == 0 ? 0 : (int) ((4 * total + peak - 1) / peak).clamp (1, 4);
                    cr.set_source_rgba (color.red, color.green, color.blue, alphas[level]);
                    mark (cr, offset + w * (cell + gap), top);
                }
                return;
            }
            for (int w = 0; w < shown; w++) {
                var week = weeks.get_array_element (first + w);
                for (uint d = 0; d < week.get_length (); d++) {
                    // GitHub's first week can start mid-week; place days by weekday so rows line up.
                    var day = week.get_array_element (d);
                    int row = week.get_length () < 7 && w == 0 ? (int) (7 - week.get_length () + d) : (int) d;
                    int level = (int) day.get_int_element (2).clamp (0, 4);
                    cr.set_source_rgba (color.red, color.green, color.blue, alphas[level]);
                    mark (cr, offset + w * (cell + gap), row * (cell + gap));
                }
            }
        }

        private void mark (Cairo.Context cr, double x, double y) {
            if (style == "squares") {
                double r = 2;
                cr.new_sub_path ();
                cr.arc (x + cell - r, y + r, r, -Math.PI / 2, 0);
                cr.arc (x + cell - r, y + cell - r, r, 0, Math.PI / 2);
                cr.arc (x + r, y + cell - r, r, Math.PI / 2, Math.PI);
                cr.arc (x + r, y + r, r, Math.PI, 3 * Math.PI / 2);
                cr.close_path ();
            } else {
                cr.new_sub_path ();
                cr.arc (x + cell / 2.0, y + cell / 2.0, cell / 2.0, 0, 2 * Math.PI);
            }
            cr.fill ();
        }

        private bool on_tooltip (int x, int y, bool keyboard, Gtk.Tooltip tooltip) {
            int width = get_width ();
            int shown = visible_weeks (width);
            int offset = width - (shown * (cell + gap) - gap);
            // Hit-test by slot (mark plus its gap) so the tiny "fine" marks are still easy to hover.
            int w = (x - offset) / (cell + gap);
            if (x < offset || w < 0 || w >= shown) return false;
            var week = weeks.get_array_element (weeks.get_length () - shown + w);
            if (compact) {
                if (week.get_length () == 0) return false;
                int64 total = week_total (week);
                var start = new DateTime.from_iso8601 (week.get_array_element (0).get_string_element (0) + "T12:00:00Z", null);
                tooltip.set_text ("%s contribution%s · week of %s".printf (total == 0 ? "No" : total.to_string (),
                    total == 1 ? "" : "s", start != null ? start.format ("%-d %b %Y") : week.get_array_element (0).get_string_element (0)));
                return true;
            }
            int row = y / (cell + gap);
            if (row < 0 || row > 6) return false;
            int d = week.get_length () < 7 && w == 0 ? row - (int) (7 - week.get_length ()) : row;
            if (d < 0 || d >= week.get_length ()) return false;
            var day = week.get_array_element (d);
            int64 count = day.get_int_element (1);
            var date = new DateTime.from_iso8601 (day.get_string_element (0) + "T12:00:00Z", null);
            string when = date != null ? date.format ("%a %-d %b %Y") : day.get_string_element (0);
            tooltip.set_text ("%s contribution%s · %s".printf (count == 0 ? "No" : count.to_string (), count == 1 ? "" : "s", when));
            return true;
        }
    }
}

public Wingpanel.Indicator? get_indicator (Module module, Wingpanel.ServerType server_type) {
    if (server_type != Wingpanel.ServerType.SESSION) return null;
    return new MSeries.RepoBarIndicator ();
}
