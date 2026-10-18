/* Read-only GitHub repository status for Pantheon's Wingpanel. */
using GLib;
using Gtk;
using Json;
using Wingpanel;

namespace MSeries {
    public class RepoBarIndicator : Wingpanel.Indicator {
        private Gtk.Box panel;
        private Gtk.Image panel_icon;
        private Gtk.Label panel_counts_label;
        private Gtk.Box menu;
        private Gtk.Box repo_list;
        private Gtk.SearchEntry search_entry;
        private Gtk.DropDown scope_dropdown;
        private Gtk.Label account_label;
        private Gtk.Label summary_label;
        private Gtk.Label freshness_label;
        private Gtk.Button refresh_button;
        private bool in_flight = false;
        private bool show_forks = false;
        private bool show_archived = false;
        private uint refresh_source = 0;
        private uint refresh_interval = 0;
        private string executable;
        private string last_error = "";

        public RepoBarIndicator () {
            GLib.Object (code_name: "repobar");
        }

        construct {
            executable = GLib.Path.build_filename (Environment.get_home_dir (), ".local", "bin", "mseries-repobar");
            panel = new Gtk.Box (Gtk.Orientation.HORIZONTAL, 5);
            panel_icon = new Gtk.Image.from_icon_name ("github-symbolic") {
                pixel_size = 16, valign = Gtk.Align.CENTER
            };
            panel_icon.add_css_class ("mseries-repobar-icon");
            panel.append (panel_icon);
            panel_counts_label = new Gtk.Label ("…") { valign = Gtk.Align.CENTER };
            panel.append (panel_counts_label);
            panel.set_tooltip_text ("GitHub repositories · loading");
            var click = new Gtk.GestureClick () { button = 2 };
            click.released.connect (() => refresh ());
            panel.add_controller (click);
            this.visible = true;

            menu = new Gtk.Box (Gtk.Orientation.VERTICAL, 8) {
                margin_top = 8, margin_bottom = 6, margin_start = 8, margin_end = 8,
                width_request = 390
            };
            menu.add_css_class ("mseries-repobar");
            install_style (menu.get_display ());

            var header = new Gtk.Box (Gtk.Orientation.VERTICAL, 2);
            account_label = new Gtk.Label ("GitHub repositories") { xalign = 0, ellipsize = Pango.EllipsizeMode.END };
            account_label.add_css_class ("repo-heading");
            summary_label = new Gtk.Label ("Waiting for GitHub…") { xalign = 0 };
            summary_label.add_css_class ("dim-label");
            summary_label.add_css_class ("caption");
            header.append (account_label);
            header.append (summary_label);
            menu.append (header);

            var filters = new Gtk.Box (Gtk.Orientation.HORIZONTAL, 6);
            search_entry = new Gtk.SearchEntry () { placeholder_text = "Search repositories", hexpand = true };
            search_entry.search_changed.connect (() => render_cached ());
            scope_dropdown = new Gtk.DropDown.from_strings (new string[] {
                "Dashboard", "All", "Pinned", "Issues", "Pull requests", "Needs attention", "Local"
            });
            scope_dropdown.set_size_request (150, -1);
            scope_dropdown.notify["selected"].connect (() => render_cached ());
            filters.append (search_entry);
            filters.append (scope_dropdown);
            menu.append (filters);

            var scroll = new Gtk.ScrolledWindow () {
                hscrollbar_policy = Gtk.PolicyType.NEVER,
                vscrollbar_policy = Gtk.PolicyType.AUTOMATIC,
                min_content_height = 120,
                max_content_height = 420,
                propagate_natural_height = true
            };
            repo_list = new Gtk.Box (Gtk.Orientation.VERTICAL, 4);
            scroll.set_child (repo_list);
            menu.append (scroll);
            menu.append (new Gtk.Separator (Gtk.Orientation.HORIZONTAL));

            var footer = new Gtk.Box (Gtk.Orientation.HORIZONTAL, 8);
            freshness_label = new Gtk.Label ("") { xalign = 0, hexpand = true, ellipsize = Pango.EllipsizeMode.END };
            freshness_label.add_css_class ("dim-label");
            freshness_label.add_css_class ("caption");
            refresh_button = new Gtk.Button.from_icon_name ("view-refresh-symbolic") {
                tooltip_text = "Refresh GitHub repositories"
            };
            refresh_button.add_css_class ("flat");
            refresh_button.update_property (Gtk.AccessibleProperty.LABEL, "Refresh GitHub repositories", -1);
            refresh_button.clicked.connect (() => refresh ());
            footer.append (freshness_label);
            var actions = new Gtk.Box (Gtk.Orientation.HORIZONTAL, 0);
            actions.add_css_class ("repo-dock");
            actions.append (refresh_button);
            footer.append (actions);
            menu.append (footer);

            show_message ("Connect GitHub", "Run `gh auth login`, then refresh.");
            schedule_refresh (300);
            load_snapshot ();
        }

        private static void install_style (Gdk.Display display) {
            var style = new Gtk.CssProvider ();
            style.load_from_string (
                ".mseries-repobar { font-size: 9pt; } " +
                ".mseries-repobar .caption { font-size: 8pt; } " +
                ".mseries-repobar .repo-heading { font-weight: 700; font-size: 9.5pt; } " +
                ".mseries-repobar .repo-row { padding: 6px 10px; border-radius: 8px; background: alpha(currentColor, 0.06); } " +
                ".mseries-repobar .repo-name { font-weight: 700; } " +
                ".mseries-repobar .repo-meta { font-size: 8pt; opacity: 0.72; } " +
                ".mseries-repobar .numeric { font-feature-settings: \"tnum\"; } " +
                ".mseries-repobar button { padding: 3px 6px; } " +
                ".mseries-repobar .repo-dock { padding: 3px; border-radius: 12px; background: alpha(currentColor, 0.06); } " +
                ".mseries-repobar .repo-dock button { padding: 6px 11px; border-radius: 9px; min-height: 0; min-width: 0; } " +
                ".mseries-repobar .repo-dock button:hover { background: alpha(currentColor, 0.1); } " +
                ".mseries-repobar .ci-ok { color: @success_color; font-weight: 700; } " +
                ".mseries-repobar .ci-warn { color: @warning_color; font-weight: 700; } " +
                ".mseries-repobar .ci-bad { color: @error_color; font-weight: 700; } " +
                ".mseries-repobar-icon { color: @theme_fg_color; }");
            Gtk.StyleContext.add_provider_for_display (display, style, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION);
        }

        private void show_message (string title, string detail) {
            clear_rows ();
            var row = new Gtk.Box (Gtk.Orientation.VERTICAL, 4) {
                margin_top = 12, margin_bottom = 12, margin_start = 6, margin_end = 6
            };
            var heading = new Gtk.Label (title) { xalign = 0 };
            heading.add_css_class ("repo-name");
            var explanation = new Gtk.Label (detail) {
                xalign = 0, wrap = true, selectable = true
            };
            explanation.add_css_class ("dim-label");
            row.append (heading);
            row.append (explanation);
            repo_list.append (row);
        }

        private void clear_rows () {
            Gtk.Widget? child = repo_list.get_first_child ();
            while (child != null) {
                repo_list.remove (child);
                child = repo_list.get_first_child ();
            }
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

        private async void read_snapshot (bool force) {
            if (in_flight) return;
            in_flight = true;
            refresh_button.set_sensitive (false);
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
                render_snapshot (parser.get_root ().get_object ());
            } catch (Error e) {
                last_error = e.message;
                summary_label.set_text ("GitHub status unavailable");
                freshness_label.set_text ("Check GitHub CLI sign-in");
                if (repo_list.get_first_child () == null) show_message ("GitHub unavailable", last_error);
            }
            in_flight = false;
            refresh_button.set_sensitive (true);
        }

        private void render_snapshot (Json.Object snapshot) {
            string account = snapshot.get_string_member_with_default ("account", "");
            bool stale = snapshot.get_boolean_member_with_default ("stale", false);
            string error = snapshot.get_string_member_with_default ("error", "");
            int64 fetched_at = snapshot.get_int_member_with_default ("fetchedAt", 0);
            var repos = snapshot.get_array_member ("repos");
            if (snapshot.has_member ("settings")) {
                var settings = snapshot.get_object_member ("settings");
                show_forks = settings.get_boolean_member_with_default ("showForks", false);
                show_archived = settings.get_boolean_member_with_default ("showArchived", false);
                schedule_refresh ((uint) settings.get_int_member_with_default ("refreshInterval", 300));
            }
            int issues = 0;
            int prs = 0;
            int failing = 0;
            for (uint i = 0; i < repos.get_length (); i++) {
                var repo = repos.get_object_element (i);
                issues += (int) repo.get_int_member_with_default ("openIssues", 0);
                prs += (int) repo.get_int_member_with_default ("openPullRequests", 0);
                string state = repo.get_string_member_with_default ("ci", "UNKNOWN");
                if (state == "FAILURE" || state == "ERROR") failing++;
            }
            account_label.set_text (account.length > 0 ? "GitHub · " + account : "GitHub repositories");
            summary_label.set_text ("%u repos · %d open PRs · %d open issues · %d failing CI".printf (
                repos.get_length (), prs, issues, failing));
            if (error.length > 0 && fetched_at > 0) {
                freshness_label.set_text ("Refresh failed · showing cached data");
                freshness_label.set_tooltip_text (error);
            } else if (error.length > 0) {
                freshness_label.set_text ("GitHub unavailable");
                freshness_label.set_tooltip_text (error);
            } else if (fetched_at > 0) {
                int64 age = int64.max (0, GLib.get_real_time () / 1000000 - fetched_at);
                string age_text = age < 60 ? "less than a minute" : "%d min".printf ((int) (age / 60));
                freshness_label.set_text ((stale ? "Cached · updated " : "Updated ") + age_text + " ago");
                freshness_label.set_tooltip_text (stale ? "Refresh to update repository status." : null);
            } else {
                freshness_label.set_text ("Updated just now");
                freshness_label.set_tooltip_text (null);
            }
            if (snapshot.has_member ("rateLimits")) {
                var limits = snapshot.get_object_member ("rateLimits");
                if (limits.has_member ("resources")) {
                    var resources = limits.get_object_member ("resources");
                    if (resources.has_member ("core")) {
                        var core = resources.get_object_member ("core");
                        int remaining = (int) core.get_int_member_with_default ("remaining", -1);
                        int limit = (int) core.get_int_member_with_default ("limit", -1);
                        if (remaining >= 0 && limit > 0) {
                            freshness_label.set_text (freshness_label.get_text () + " · API " + remaining.to_string () + "/" + limit.to_string ());
                        }
                    }
                }
            }
            panel_counts_label.set_text ("%d/%d".printf (prs, issues));
            panel.set_tooltip_text ("GitHub · %u repositories · %d open PRs · %d open issues%s".printf (
                repos.get_length (), prs, issues, failing > 0 ? " · CI failing" : ""));

            clear_rows ();
            if (repos.get_length () == 0) {
                show_message ("No repositories found", error.length > 0 ? error : "This account has no accessible repositories.");
                return;
            }
            int shown = 0;
            int dashboard_limit = 5;
            if (snapshot.has_member ("settings")) {
                dashboard_limit = (int) snapshot.get_object_member ("settings").get_int_member_with_default ("repoLimit", 5);
            }
            for (int pass = 0; pass < (scope_dropdown.get_selected () == 0 ? 2 : 1); pass++) {
                for (uint i = 0; i < repos.get_length (); i++) {
                    var repo = repos.get_object_element (i);
                    string state = repo.get_string_member_with_default ("repoState", "visible");
                    if (scope_dropdown.get_selected () == 0 && ((pass == 0) != (state == "pinned"))) continue;
                    if (scope_dropdown.get_selected () == 0 && pass == 1 && shown >= dashboard_limit) continue;
                    if (matches_filter (repo)) {
                        append_repo (repo);
                        shown++;
                    }
                }
            }
            if (shown == 0) show_message ("No matching repositories", "Try another search or dashboard view.");
        }

        private bool matches_filter (Json.Object repo) {
            string state = repo.get_string_member_with_default ("repoState", "visible");
            string name = repo.get_string_member_with_default ("name", "");
            string description = repo.get_string_member_with_default ("description", "");
            string language = repo.get_string_member_with_default ("language", "");
            if (scope_dropdown.get_selected () != 1 && !show_archived && repo.get_boolean_member_with_default ("archived", false)) return false;
            if (scope_dropdown.get_selected () != 1 && !show_forks && repo.get_boolean_member_with_default ("fork", false)) return false;
            string query = search_entry.get_text ().strip ().casefold ();
            string topics = "";
            if (repo.has_member ("topics")) {
                var topic_array = repo.get_array_member ("topics");
                for (uint i = 0; i < topic_array.get_length (); i++) topics += " " + topic_array.get_string_element (i);
            }
            string haystack = (name + " " + description + " " + language + " " + topics).casefold ();
            if (query.length > 0 && !haystack.contains (query)) return false;
            if (scope_dropdown.get_selected () == 2 && state != "pinned") return false;
            if (scope_dropdown.get_selected () == 3 && repo.get_int_member_with_default ("openIssues", 0) == 0) return false;
            if (scope_dropdown.get_selected () == 4 && repo.get_int_member_with_default ("openPullRequests", 0) == 0) return false;
            if (scope_dropdown.get_selected () == 6 && (!repo.has_member ("local") ||
                repo.get_member ("local").get_node_type () != Json.NodeType.OBJECT)) return false;
            if (scope_dropdown.get_selected () == 5 && repo.get_string_member_with_default ("ci", "") != "FAILURE" &&
                repo.get_string_member_with_default ("ci", "") != "ERROR" &&
                repo.get_int_member_with_default ("openIssues", 0) == 0 &&
                repo.get_int_member_with_default ("openPullRequests", 0) == 0) return false;
            if (scope_dropdown.get_selected () != 1 && state == "hidden") return false;
            return true;
        }

        private void render_cached () {
            try {
                string contents;
                if (!FileUtils.get_contents (Environment.get_home_dir () + "/.cache/mseries/repobar/snapshot.json", out contents)) return;
                var parser = new Json.Parser ();
                parser.load_from_data (contents);
                render_snapshot (parser.get_root ().get_object ());
            } catch (Error e) {
                // Keep the last rendered list while the first snapshot is loading.
            }
        }

        private void append_repo (Json.Object repo) {
            string name = repo.get_string_member_with_default ("name", "Repository");
            string url = repo.get_string_member_with_default ("url", "");
            string branch = repo.get_string_member_with_default ("branch", "");
            string ci = repo.get_string_member_with_default ("ci", "UNKNOWN");
            string release = repo.get_string_member_with_default ("release", "");
            string state = repo.get_string_member_with_default ("repoState", "visible");
            int prs = (int) repo.get_int_member_with_default ("openPullRequests", 0);
            int issues = (int) repo.get_int_member_with_default ("openIssues", 0);
            int stars = (int) repo.get_int_member_with_default ("stars", 0);
            bool archived = repo.get_boolean_member_with_default ("archived", false);

            var card = new Gtk.Box (Gtk.Orientation.VERTICAL, 3);
            card.add_css_class ("repo-row");
            var top = new Gtk.Box (Gtk.Orientation.HORIZONTAL, 6);
            var link = new Gtk.LinkButton.with_label (url, name) { halign = Gtk.Align.FILL, hexpand = true };
            link.add_css_class ("repo-name");
            var ci_label = new Gtk.Label (ci_label_text (ci));
            ci_label.add_css_class (ci_css (ci));
            ci_label.set_tooltip_text ("Default branch CI: " + ci);
            top.append (link);
            top.append (ci_label);
            var state_button = new Gtk.Button.with_label (state == "pinned" ? "Unpin" : "Pin") {
                tooltip_text = state == "pinned" ? "Remove from dashboard pins" : "Pin to dashboard"
            };
            state_button.add_css_class ("flat");
            state_button.clicked.connect (() => change_repo_state.begin (name, state == "pinned" ? "unpin" : "pin"));
            var hide_button = new Gtk.Button.from_icon_name ("view-conceal-symbolic") { tooltip_text = "Hide repository" };
            hide_button.add_css_class ("flat");
            hide_button.clicked.connect (() => change_repo_state.begin (name, "hide"));
            top.append (state_button);
            top.append (hide_button);
            var details = new Gtk.Label ("%d PRs · %d issues · ★ %d%s%s%s".printf (
                prs, issues, stars, branch.length > 0 ? " · " + branch : "",
                release.length > 0 ? " · " + release : "", archived ? " · archived" : "")) {
                xalign = 0, ellipsize = Pango.EllipsizeMode.END
            };
            details.add_css_class ("repo-meta");
            string commits_1h = "—";
            string commits_24h = "—";
            string commits_30d = "—";
            if (repo.has_member ("commitCounts") && repo.get_member ("commitCounts").get_node_type () == Json.NodeType.OBJECT) {
                var commit_counts = repo.get_object_member ("commitCounts");
                int64 count_1h = commit_counts.get_int_member_with_default ("1h", -1);
                int64 count_24h = commit_counts.get_int_member_with_default ("24h", -1);
                int64 count_30d = commit_counts.get_int_member_with_default ("30d", -1);
                commits_1h = count_1h >= 0 ? count_1h.to_string () : "—";
                commits_24h = count_24h >= 0 ? count_24h.to_string () : "—";
                commits_30d = count_30d >= 0 ? count_30d.to_string () : "—";
            }
            var commit_summary = new Gtk.Label ("Commits · 1h %s · 24h %s · 30d %s".printf (
                commits_1h, commits_24h, commits_30d)) {
                xalign = 0, hexpand = true, ellipsize = Pango.EllipsizeMode.END
            };
            commit_summary.add_css_class ("repo-meta");
            commit_summary.add_css_class ("numeric");
            commit_summary.set_tooltip_text ("Default branch commits during each time window; refreshed with the repository snapshot.");
            card.append (top);
            card.append (details);
            card.append (commit_summary);
            if (repo.has_member ("recentActivity") && repo.get_member ("recentActivity").get_node_type () != Json.NodeType.NULL) {
                var activity = repo.get_object_member ("recentActivity");
                string kind = activity.get_string_member_with_default ("kind", "activity");
                string title = activity.get_string_member_with_default ("title", "");
                string activity_url = activity.get_string_member_with_default ("url", "");
                if (title.length > 0) {
                    var activity_link = new Gtk.LinkButton.with_label (activity_url, kind + " · " + title) {
                        halign = Gtk.Align.START
                    };
                    activity_link.add_css_class ("repo-meta");
                    card.append (activity_link);
                }
            }
            if (repo.has_member ("local") && repo.get_member ("local").get_node_type () == Json.NodeType.OBJECT) {
                var local = repo.get_object_member ("local");
                string local_branch = local.get_string_member_with_default ("branch", "");
                int behind = (int) local.get_int_member_with_default ("behind", 0);
                int ahead = (int) local.get_int_member_with_default ("ahead", 0);
                int dirty = (int) local.get_int_member_with_default ("dirtyFileCount", 0);
                var local_label = new Gtk.Label ("Local · %s%s%s%s".printf (
                    local_branch, dirty > 0 ? " · %d modified".printf (dirty) : "",
                    behind > 0 ? " · ↓ %d".printf (behind) : "",
                    ahead > 0 ? " · ↑ %d".printf (ahead) : "")) { xalign = 0, ellipsize = Pango.EllipsizeMode.END };
                local_label.add_css_class ("repo-meta");
                local_label.set_tooltip_text (local.get_string_member_with_default ("path", ""));
                card.append (local_label);
            }
            var detail_box = new Gtk.Box (Gtk.Orientation.VERTICAL, 5) {
                margin_top = 5, margin_bottom = 2, margin_start = 4, margin_end = 4
            };
            detail_box.append (new Gtk.Label ("Expand to load recent GitHub details.") {
                xalign = 0, wrap = true
            });
            var details_expander = new Gtk.Expander ("Recent details") { hexpand = true };
            details_expander.set_child (detail_box);
            bool details_sections_added = false;
            details_expander.notify["expanded"].connect (() => {
                if (details_expander.get_expanded () && !details_sections_added) {
                    details_sections_added = true;
                    clear_box (detail_box);
                    append_repo_detail_expander (detail_box, name, url, "issues", "Issues");
                    append_repo_detail_expander (detail_box, name, url, "pulls", "Pull requests");
                    append_repo_detail_expander (detail_box, name, url, "ci", "CI runs");
                    append_repo_detail_expander (detail_box, name, url, "releases", "Releases");
                    append_repo_detail_expander (detail_box, name, url, "activity", "Activity");
                    append_repo_detail_expander (detail_box, name, url, "commits", "Commits");
                    append_repo_detail_expander (detail_box, name, url, "branches", "Branches");
                    append_repo_detail_expander (detail_box, name, url, "tags", "Tags");
                }
            });
            card.append (details_expander);
            repo_list.append (card);
        }

        private void append_repo_detail_expander (Gtk.Box parent, string name, string repo_url, string key, string title) {
            var content = new Gtk.Box (Gtk.Orientation.VERTICAL, 3) {
                margin_top = 3, margin_bottom = 3, margin_start = 8, margin_end = 4
            };
            var expander = new Gtk.Expander (title) { hexpand = true };
            expander.set_child (content);
            bool requested = false;
            expander.notify["expanded"].connect (() => {
                if (expander.get_expanded () && !requested) {
                    requested = true;
                    load_repo_detail.begin (name, repo_url, key, content);
                }
            });
            parent.append (expander);
        }

        private async void load_repo_detail (string name, string repo_url, string key, Gtk.Box content) {
            clear_box (content);
            var loading = new Gtk.Box (Gtk.Orientation.HORIZONTAL, 7);
            var spinner = new Gtk.Spinner ();
            spinner.start ();
            loading.append (spinner);
            loading.append (new Gtk.Label ("Loading…") { xalign = 0 });
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
                append_detail_message (content, "Could not load " + key, e.message);
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
            if (items == null) {
                append_detail_message (content, "No details available", "The GitHub response did not include this section.");
                return;
            }
            if (items.get_length () == 0) {
                string empty_text = key == "issues" ? "No open issues" :
                    key == "pulls" ? "No open pull requests" :
                    key == "ci" ? "No recent runs" :
                    key == "releases" ? "No releases" :
                    key == "activity" ? "No recent activity" :
                    key == "commits" ? "No recent commits" :
                    key == "branches" ? "No branches found" : "No tags found";
                content.append (new Gtk.Label (empty_text) { xalign = 0 });
                return;
            }
            for (uint i = 0; i < items.get_length (); i++) {
                var item = items.get_object_element (i);
                string label = item.get_string_member_with_default ("title", "");
                if (label.length == 0) label = item.get_string_member_with_default ("name", "");
                if (label.length == 0) label = item.get_string_member_with_default ("tag_name", "");
                if (key == "commits" && item.has_member ("commit")) {
                    var commit = item.get_object_member ("commit");
                    label = commit.get_string_member_with_default ("message", label).split ("\n")[0];
                }
                if (key == "activity") {
                    label = item.get_string_member_with_default ("type", "Repository activity");
                    if (item.has_member ("actor")) {
                        label += " · " + item.get_object_member ("actor").get_string_member_with_default ("login", "");
                    }
                }
                if (label.length == 0) label = item.get_string_member_with_default ("html_url", "Repository item");
                string detail = item.get_string_member_with_default ("conclusion", "");
                if (detail.length == 0) detail = item.get_string_member_with_default ("status", "");
                string url = item.get_string_member_with_default ("html_url", "");
                if (key == "branches" || key == "tags") {
                    string ref_name = key == "branches" ? item.get_string_member_with_default ("name", "") : item.get_string_member_with_default ("name", "");
                    if (ref_name.length > 0) url = repo_url + "/tree/" + Uri.escape_string (ref_name, null, true);
                    detail = key == "branches" ? "branch" : "tag";
                }
                if (key == "activity") detail = item.get_string_member_with_default ("created_at", "");
                if (detail.length > 0) label += " · " + detail;
                if (url.length > 0 && key != "activity") {
                    var link = new Gtk.LinkButton.with_label (url, label) { halign = Gtk.Align.START };
                    link.add_css_class ("repo-meta");
                    content.append (link);
                } else {
                    content.append (new Gtk.Label (label) { xalign = 0, wrap = true });
                }
            }
        }

        private void append_detail_message (Gtk.Box parent, string title, string message) {
            var heading = new Gtk.Label (title) { xalign = 0 };
            heading.add_css_class ("repo-name");
            parent.append (heading);
            parent.append (new Gtk.Label (message) { xalign = 0, wrap = true });
        }

        private void clear_box (Gtk.Box box) {
            Gtk.Widget? child = box.get_first_child ();
            while (child != null) {
                box.remove (child);
                child = box.get_first_child ();
            }
        }

        private async void change_repo_state (string name, string action) {
            try {
                var process = new Subprocess.newv (new string[] { executable, action, name },
                    SubprocessFlags.STDOUT_PIPE | SubprocessFlags.STDERR_PIPE);
                string output;
                string error_text;
                yield process.communicate_utf8_async (null, null, out output, out error_text);
                if (!process.get_successful ()) throw new IOError.FAILED (error_text.strip ());
                read_snapshot.begin (true);
            } catch (Error e) {
                last_error = e.message;
                summary_label.set_text ("Could not update repository preference");
            }
        }

        private static string ci_label_text (string state) {
            switch (state) {
            case "SUCCESS": return "✓";
            case "FAILURE": return "✕";
            case "ERROR": return "!";
            case "PENDING":
            case "EXPECTED": return "…";
            default: return "—";
            }
        }

        private static string ci_css (string state) {
            if (state == "SUCCESS") return "ci-ok";
            if (state == "FAILURE" || state == "ERROR") return "ci-bad";
            if (state == "PENDING" || state == "EXPECTED") return "ci-warn";
            return "repo-meta";
        }

        public override Gtk.Widget get_display_widget () {
            return panel;
        }

        public override Gtk.Widget? get_widget () {
            load_snapshot ();
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
