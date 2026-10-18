/* Read-only GitHub repository status for Pantheon's Wingpanel, styled like the CodexBar indicator. */
using GLib;
using Gtk;
using Json;
using Wingpanel;

namespace MSeries {
    public class RepoBarIndicator : Wingpanel.Indicator {
        // Scopes are the segmented switcher; filters narrow any scope from the search row's menu.
        private const string[] SCOPES = { "Dashboard", "Pinned", "Attention", "All" };
        private const string[] FILTERS = { "Any repository", "Has open issues", "Has open pull requests", "Local checkout" };
        private const string[] DETAIL_KEYS = { "pulls", "issues", "ci", "releases", "commits", "branches", "tags", "activity" };
        private const string[] DETAIL_TITLES = { "PRs", "Issues", "CI", "Releases", "Commits", "Branches", "Tags", "Activity" };

        private Gtk.Box panel;
        private Gtk.Label panel_prs;
        private Gtk.Label panel_issues;
        private Gtk.Label panel_alert;
        private Gtk.Box menu;
        private Gtk.Box repo_list;
        private Gtk.SearchEntry search_entry;
        private Gtk.ToggleButton[] scope_buttons = {};
        private Gtk.MenuButton filter_button;
        private Gtk.Label subtitle_label;
        private Gtk.Label chip_label;
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

        public RepoBarIndicator () {
            GLib.Object (code_name: "repobar");
        }

        construct {
            executable = GLib.Path.build_filename (Environment.get_home_dir (), ".local", "bin", "mseries-repobar");

            // Panel item: GitHub mark, open PRs and issues, and a red mark only while default-branch CI fails.
            panel = new Gtk.Box (Gtk.Orientation.HORIZONTAL, 4);
            panel.add_css_class ("mseries-repobar-bar");
            var mark = new Gtk.Image.from_icon_name ("github-symbolic") { pixel_size = 16, valign = Gtk.Align.CENTER };
            mark.add_css_class ("repo-mark");
            panel.append (mark);
            panel_prs = new Gtk.Label ("…") { valign = Gtk.Align.CENTER };
            panel_prs.add_css_class ("seg-value");
            panel.append (panel_prs);
            var divider = new Gtk.Separator (Gtk.Orientation.VERTICAL);
            divider.add_css_class ("seg-divider");
            panel.append (divider);
            panel_issues = new Gtk.Label ("") { valign = Gtk.Align.CENTER };
            panel_issues.add_css_class ("seg-value");
            panel.append (panel_issues);
            panel_alert = new Gtk.Label ("●") { valign = Gtk.Align.CENTER, visible = false };
            panel_alert.add_css_class ("seg-alert");
            panel.append (panel_alert);
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
                max_content_height = 420,
                propagate_natural_height = true
            };
            repo_list = new Gtk.Box (Gtk.Orientation.VERTICAL, 8);
            scroll.set_child (repo_list);
            menu.append (scroll);
            menu.append (new Gtk.Separator (Gtk.Orientation.HORIZONTAL));

            // Bottom bar: freshness on the left, an icon-only dock on the right (names in tooltips).
            subtitle_label = new Gtk.Label ("Loading GitHub status…") { xalign = 0, hexpand = true, ellipsize = Pango.EllipsizeMode.END };
            subtitle_label.add_css_class ("dim-label");
            subtitle_label.add_css_class ("caption");
            subtitle_label.add_css_class ("numeric");
            chip_label = new Gtk.Label ("") { valign = Gtk.Align.CENTER, visible = false };
            chip_label.add_css_class ("chip");
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
            bar.append (chip_label);
            bar.append (subtitle_label);
            var actions = new Gtk.Box (Gtk.Orientation.HORIZONTAL, 0) { homogeneous = true };
            actions.add_css_class ("mseries-dock");
            actions.append (make_dock_button ("Your pull requests", "mail-send-receive-symbolic", "/pulls"));
            actions.append (make_dock_button ("Your issues", "mail-mark-important-symbolic", "/issues"));
            actions.append (make_dock_button ("Open GitHub", "web-browser-symbolic", ""));
            actions.append (refresh_button);
            bar.append (actions);
            menu.append (bar);

            show_state ("content-loading-symbolic", "Loading repositories…", "", false);
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
                ".mseries-repobar .repo-card:hover { background: alpha(currentColor, 0.09); } " +
                ".mseries-repobar .repo-name { font-weight: 700; font-size: 9.5pt; } " +
                ".mseries-repobar .repo-owner { font-size: 8pt; opacity: 0.6; } " +
                ".mseries-repobar .count { padding: 0 7px; border-radius: 99px; font-size: 7.5pt; font-weight: 700; " +
                "  background: alpha(currentColor, 0.1); } " +
                ".mseries-repobar .count.zero { opacity: 0.45; font-weight: 400; } " +
                ".mseries-repobar .window-name { font-weight: 700; font-size: 7.5pt; opacity: 0.75; } " +
                ".mseries-repobar .chip { padding: 1px 8px; border-radius: 99px; font-size: 7.5pt; font-weight: 700; " +
                "  background: alpha(@warning_color, 0.22); color: @warning_color; } " +
                ".mseries-repobar .chip.bad { background: alpha(@error_color, 0.2); color: @error_color; } " +
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
                ".mseries-repobar button.disclosure, .mseries-repobar button.compact.dim-label { opacity: 0.55; } " +
                ".mseries-repobar button.disclosure:hover, .mseries-repobar button.compact.dim-label:hover { opacity: 1; } " +
                ".mseries-repobar .mseries-switcher button { padding: 2px 6px; } " +
                ".mseries-repobar .mseries-dock { padding: 3px; border-radius: 12px; background: alpha(currentColor, 0.06); } " +
                ".mseries-repobar .mseries-bar { margin-top: 2px; } " +
                ".mseries-repobar .mseries-dock button { padding: 6px 11px; border-radius: 9px; min-height: 0; } " +
                ".mseries-repobar .mseries-dock button:hover { background: alpha(currentColor, 0.1); } " +
                ".mseries-repobar-bar label { font-size: 8.5pt; font-feature-settings: \"tnum\"; } " +
                ".mseries-repobar-bar .seg-value { font-size: 7.5pt; font-weight: 700; } " +
                ".mseries-repobar-bar .seg-alert { font-size: 7pt; color: @error_color; } " +
                ".mseries-repobar-bar .seg-divider { min-width: 1px; margin: 4px 0; background: alpha(currentColor, 0.22); } " +
                ".mseries-repobar-bar .stale { opacity: 0.55; } " +
                ".mseries-repobar-bar .repo-mark { color: @theme_fg_color; }");
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
                option.toggled.connect (() => {
                    if (!option.get_active ()) return;
                    filter = index;
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
            clear_box (repo_list);
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
            repo_list.append (state);
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
            if (in_flight) return;
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
                last_snapshot_text = output;
                render_snapshot (parser.get_root ().get_object ());
            } catch (Error e) {
                set_chip ("Offline", true);
                subtitle_label.set_text ("GitHub status unavailable");
                subtitle_label.set_tooltip_text (e.message);
                if (last_snapshot_text.length == 0) {
                    bool signed_out = e.message.contains ("auth") || e.message.contains ("login") || e.message.contains ("No such file");
                    show_state (signed_out ? "dialog-password-symbolic" : "network-error-symbolic",
                        signed_out ? "Connect GitHub" : "GitHub unavailable",
                        signed_out ? "RepoBar reads your repositories through the GitHub CLI. It never stores the token." : e.message,
                        signed_out);
                }
            }
            in_flight = false;
            set_refreshing (false);
        }

        private void set_chip (string text, bool bad) {
            chip_label.set_text (text);
            chip_label.set_visible (text.length > 0);
            if (bad) chip_label.add_css_class ("bad"); else chip_label.remove_css_class ("bad");
        }

        private void render_snapshot (Json.Object snapshot) {
            account = snapshot.get_string_member_with_default ("account", "");
            host = snapshot.get_string_member_with_default ("host", "github.com");
            bool stale = snapshot.get_boolean_member_with_default ("stale", false);
            string error = snapshot.get_string_member_with_default ("error", "");
            int64 fetched_at = snapshot.get_int_member_with_default ("fetchedAt", 0);
            var repos = snapshot.has_member ("repos") ? snapshot.get_array_member ("repos") : new Json.Array ();
            int dashboard_limit = 5;
            if (snapshot.has_member ("settings")) {
                var settings = snapshot.get_object_member ("settings");
                show_forks = settings.get_boolean_member_with_default ("showForks", false);
                show_archived = settings.get_boolean_member_with_default ("showArchived", false);
                dashboard_limit = (int) settings.get_int_member_with_default ("repoLimit", 5);
                schedule_refresh ((uint) settings.get_int_member_with_default ("refreshInterval", 300));
            }
            int issues = 0;
            int prs = 0;
            int failing = 0;
            int attention = 0;
            for (uint i = 0; i < repos.get_length (); i++) {
                var repo = repos.get_object_element (i);
                if (repo.get_string_member_with_default ("repoState", "visible") == "hidden") continue;
                issues += (int) repo.get_int_member_with_default ("openIssues", 0);
                prs += (int) repo.get_int_member_with_default ("openPullRequests", 0);
                if (ci_failing (repo)) failing++;
                if (needs_attention (repo)) attention++;
            }

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
            if (error.length > 0) set_chip (fetched_at > 0 ? "Cached" : "Offline", fetched_at == 0);
            else if (stale) set_chip ("Cached", false);
            else if (failing > 0) set_chip ("%d failing".printf (failing), true);
            else set_chip ("", false);

            scope_buttons[2].set_label (attention > 0 ? "Attention %d".printf (attention) : "Attention");
            update_panel (prs, issues, failing, (int) repos.get_length (), stale || error.length > 0);

            // Unchanged data and filters: keep the existing cards so open detail panes survive polling.
            string key = "%s|%d|%d|%s".printf (last_snapshot_text.hash ().to_string (), scope, filter, search_entry.get_text ());
            if (key == last_render_key) return;
            clear_box (repo_list);
            last_render_key = key;
            if (repos.get_length () == 0) {
                show_state ("folder-open-symbolic", "No repositories yet",
                    error.length > 0 ? error : "This GitHub account has no repositories RepoBar can read.", false);
                return;
            }
            int shown = 0;
            for (int pass = 0; pass < (scope == 0 ? 2 : 1); pass++) {
                for (uint i = 0; i < repos.get_length (); i++) {
                    var repo = repos.get_object_element (i);
                    bool pinned = repo.get_string_member_with_default ("repoState", "visible") == "pinned";
                    // Dashboard: pins first, then the most recently updated repositories up to the limit.
                    if (scope == 0 && ((pass == 0) != pinned)) continue;
                    if (scope == 0 && pass == 1 && shown >= dashboard_limit) continue;
                    if (matches_filter (repo)) {
                        repo_list.append (build_card (repo));
                        shown++;
                    }
                }
            }
            if (shown == 0) {
                bool searching = search_entry.get_text ().strip ().length > 0 || filter != 0;
                show_state (searching ? "edit-find-symbolic" : scope == 2 ? "emblem-ok-symbolic" : "starred-symbolic",
                    searching ? "No matching repositories" : scope == 2 ? "Nothing needs attention" : "No pinned repositories",
                    searching ? "Try another search or filter." : scope == 2 ? "No failing CI, open issues or pull requests."
                        : "Pin a repository with its star to keep it on the dashboard.", false);
                last_render_key = key;
            }
        }

        private void update_panel (int prs, int issues, int failing, int repo_count, bool stale) {
            panel_prs.set_text ("%d PR".printf (prs));
            panel_issues.set_text ("%d".printf (issues) + (issues == 1 ? " issue" : " issues"));
            panel_alert.set_visible (failing > 0);
            if (stale) panel.add_css_class ("stale"); else panel.remove_css_class ("stale");
            panel.set_tooltip_text ("GitHub%s · %d repositories · %d open pull requests · %d open issues%s%s\nMiddle-click to refresh".printf (
                account.length > 0 ? " · " + account : "", repo_count, prs, issues,
                failing > 0 ? " · CI failing on %d".printf (failing) : "", stale ? " · cached" : ""));
        }

        private static bool ci_failing (Json.Object repo) {
            string ci = repo.get_string_member_with_default ("ci", "");
            return ci == "FAILURE" || ci == "ERROR";
        }

        private static bool needs_attention (Json.Object repo) {
            return ci_failing (repo) || repo.get_int_member_with_default ("openIssues", 0) > 0 ||
                repo.get_int_member_with_default ("openPullRequests", 0) > 0;
        }

        private bool matches_filter (Json.Object repo) {
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

        private void render_cached () {
            if (last_snapshot_text.length == 0) {
                try {
                    string contents;
                    if (!FileUtils.get_contents (Environment.get_home_dir () + "/.cache/mseries/repobar/snapshot.json", out contents)) return;
                    last_snapshot_text = contents;
                } catch (Error e) {
                    return;
                }
            }
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
            if (state == "hidden") {
                var hidden = new Gtk.Image.from_icon_name ("view-conceal-symbolic") {
                    pixel_size = 12, tooltip_text = "Hidden from the dashboard · right-click to show"
                };
                hidden.add_css_class ("dim-label");
                head.append (hidden);
            }
            head.append (new Gtk.Box (Gtk.Orientation.HORIZONTAL, 0) { hexpand = true });
            head.append (count_pill (prs, "PR", "%d open pull request%s".printf (prs, prs == 1 ? "" : "s")));
            head.append (count_pill (issues, "⊙", "%d open issue%s".printf (issues, issues == 1 ? "" : "s"), true));
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

            card.append (build_details (full_name, url, details_toggle));

            var context = new Gtk.GestureClick () { button = 3 };
            context.pressed.connect ((n, x, y) => show_card_menu (card, full_name, url, state, x, y));
            card.add_controller (context);
            return card;
        }

        private static Gtk.Widget count_pill (int count, string mark, string description, bool mark_first = false) {
            var pill = new Gtk.Box (Gtk.Orientation.HORIZONTAL, 3) { valign = Gtk.Align.CENTER, tooltip_text = description };
            pill.add_css_class ("count");
            pill.add_css_class ("numeric");
            if (count == 0) pill.add_css_class ("zero");
            pill.append (new Gtk.Label (mark_first ? "%s %d".printf (mark, count) : "%d %s".printf (count, mark)));
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
            if (pinned) star.add_css_class ("pinned-star"); else star.add_css_class ("dim-label");
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
            string icon = kind == "commit" ? "document-open-recent-symbolic" :
                kind.contains ("pull") ? "mail-send-receive-symbolic" :
                kind.contains ("issue") ? "mail-mark-important-symbolic" :
                kind.contains ("release") ? "starred-symbolic" : "document-open-recent-symbolic";
            return link_row (icon, title, kind, activity.get_string_member_with_default ("url", ""));
        }

        private Gtk.Widget? build_local_row (Json.Object repo) {
            if (!has_object (repo, "local")) return null;
            var local = repo.get_object_member ("local");
            int behind = (int) local.get_int_member_with_default ("behind", 0);
            int ahead = (int) local.get_int_member_with_default ("ahead", 0);
            int dirty = (int) local.get_int_member_with_default ("dirtyFileCount", 0);
            var row = new Gtk.Box (Gtk.Orientation.HORIZONTAL, 6) { margin_start = 4 };
            row.set_tooltip_text (local.get_string_member_with_default ("path", ""));
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
            return row;
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

        private void show_card_menu (Gtk.Widget card, string name, string url, string state, double x, double y) {
            var box = new Gtk.Box (Gtk.Orientation.VERTICAL, 0) { margin_top = 4, margin_bottom = 4 };
            var popover = new Gtk.Popover () { child = box, has_arrow = false };
            popover.set_parent (card);
            popover.set_pointing_to ({ (int) x, (int) y, 1, 1 });
            popover.closed.connect (() => Idle.add (() => { popover.unparent (); return Source.REMOVE; }));
            box.append (menu_item ("Open on GitHub", () => open_url (url, card)));
            box.append (menu_item ("Copy Link", () => card.get_clipboard ().set_text (url)));
            box.append (new Gtk.Separator (Gtk.Orientation.HORIZONTAL) { margin_top = 3, margin_bottom = 3 });
            box.append (menu_item (state == "pinned" ? "Unpin from Dashboard" : "Pin to Dashboard",
                () => change_repo_state.begin (name, state == "pinned" ? "unpin" : "pin")));
            box.append (menu_item (state == "hidden" ? "Show Repository" : "Hide Repository",
                () => change_repo_state.begin (name, state == "hidden" ? "show" : "hide")));
            popover.popup ();
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

        private Gtk.Widget build_details (string name, string url, Gtk.ToggleButton toggle) {
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
            string icon = key == "pulls" ? "mail-send-receive-symbolic" :
                key == "issues" ? "mail-mark-important-symbolic" :
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

        private async void change_repo_state (string name, string action) {
            try {
                var process = new Subprocess.newv (new string[] { executable, action, name },
                    SubprocessFlags.STDOUT_PIPE | SubprocessFlags.STDERR_PIPE);
                string output;
                string error_text;
                yield process.communicate_utf8_async (null, null, out output, out error_text);
                if (!process.get_successful ()) throw new IOError.FAILED (error_text.strip ());
                read_snapshot.begin (false);
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

        public void probe_expand_first () {
            var card = repo_list.get_first_child ();
            var head = card != null && card.get_first_child () != null ? card.get_first_child ().get_first_child () : null;
            var toggle = head != null ? head.get_last_child () as Gtk.ToggleButton : null;
            if (toggle != null) toggle.set_active (true);
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

public Wingpanel.Indicator? get_indicator (Module module, Wingpanel.ServerType server_type) {
    if (server_type != Wingpanel.ServerType.SESSION) return null;
    return new MSeries.RepoBarIndicator ();
}
