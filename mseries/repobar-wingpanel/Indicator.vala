/* Read-only GitHub repository status for Pantheon's Wingpanel. */
using GLib;
using Gtk;
using Json;
using Wingpanel;

namespace MSeries {
    public class RepoBarIndicator : Wingpanel.Indicator {
        private Gtk.Box panel;
        private Gtk.Label panel_label;
        private Gtk.Label panel_counts_label;
        private Gtk.Box menu;
        private Gtk.Box repo_list;
        private Gtk.Label account_label;
        private Gtk.Label summary_label;
        private Gtk.Label freshness_label;
        private Gtk.Button refresh_button;
        private bool in_flight = false;
        private string executable;
        private string last_error = "";

        public RepoBarIndicator () {
            GLib.Object (code_name: "repobar");
        }

        construct {
            executable = GLib.Path.build_filename (Environment.get_home_dir (), ".local", "bin", "mseries-repobar");
            panel = new Gtk.Box (Gtk.Orientation.HORIZONTAL, 5);
            panel_label = new Gtk.Label ("GH") { valign = Gtk.Align.CENTER };
            panel_label.add_css_class ("mseries-repobar-icon");
            panel.append (panel_label);
            panel_counts_label = new Gtk.Label ("…") { valign = Gtk.Align.CENTER };
            panel.append (panel_counts_label);
            panel.set_tooltip_text ("GitHub repositories · loading");
            var click = new Gtk.GestureClick () { button = 2 };
            click.released.connect (() => refresh ());
            panel.add_controller (click);
            this.visible = true;

            menu = new Gtk.Box (Gtk.Orientation.VERTICAL, 8) {
                margin_top = 8, margin_bottom = 8, margin_start = 10, margin_end = 10,
                width_request = 360
            };
            menu.add_css_class ("mseries-repobar");
            install_style (menu.get_display ());

            var header = new Gtk.Box (Gtk.Orientation.VERTICAL, 2);
            account_label = new Gtk.Label ("GitHub repositories") { xalign = 0, ellipsize = Pango.EllipsizeMode.END };
            account_label.add_css_class ("title-4");
            summary_label = new Gtk.Label ("Waiting for GitHub…") { xalign = 0 };
            summary_label.add_css_class ("dim-label");
            summary_label.add_css_class ("caption");
            header.append (account_label);
            header.append (summary_label);
            menu.append (header);

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

            var footer = new Gtk.Box (Gtk.Orientation.HORIZONTAL, 6);
            freshness_label = new Gtk.Label ("") { xalign = 0, hexpand = true, ellipsize = Pango.EllipsizeMode.END };
            freshness_label.add_css_class ("dim-label");
            freshness_label.add_css_class ("caption");
            refresh_button = new Gtk.Button.from_icon_name ("view-refresh-symbolic") {
                tooltip_text = "Refresh GitHub repositories"
            };
            refresh_button.add_css_class ("flat");
            refresh_button.clicked.connect (() => refresh ());
            footer.append (freshness_label);
            footer.append (refresh_button);
            menu.append (footer);

            show_message ("Connect GitHub", "Run `gh auth login`, then refresh.");
            Timeout.add_seconds (300, () => { load_snapshot (); return Source.CONTINUE; });
            load_snapshot ();
        }

        private static void install_style (Gdk.Display display) {
            var style = new Gtk.CssProvider ();
            style.load_from_string (
                ".mseries-repobar { font-size: 9pt; } " +
                ".mseries-repobar .repo-row { padding: 6px 8px; border-radius: 8px; background: alpha(currentColor, 0.055); } " +
                ".mseries-repobar .repo-name { font-weight: 700; } " +
                ".mseries-repobar .repo-meta { font-size: 8pt; opacity: 0.75; } " +
                ".mseries-repobar .ci-ok { color: @success_color; font-weight: 700; } " +
                ".mseries-repobar .ci-warn { color: @warning_color; font-weight: 700; } " +
                ".mseries-repobar .ci-bad { color: @error_color; font-weight: 700; } " +
                ".mseries-repobar-icon { font-size: 14pt; }");
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
            panel_counts_label.set_text ("%d/%d".printf (prs, issues));
            panel.set_tooltip_text ("GitHub · %u repositories · %d open PRs · %d open issues%s".printf (
                repos.get_length (), prs, issues, failing > 0 ? " · CI failing" : ""));

            clear_rows ();
            if (repos.get_length () == 0) {
                show_message ("No repositories found", error.length > 0 ? error : "This account has no accessible repositories.");
                return;
            }
            for (uint i = 0; i < repos.get_length (); i++) {
                append_repo (repos.get_object_element (i));
            }
        }

        private void append_repo (Json.Object repo) {
            string name = repo.get_string_member_with_default ("name", "Repository");
            string url = repo.get_string_member_with_default ("url", "");
            string branch = repo.get_string_member_with_default ("branch", "");
            string ci = repo.get_string_member_with_default ("ci", "UNKNOWN");
            string release = repo.get_string_member_with_default ("release", "");
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
            var details = new Gtk.Label ("%d PRs · %d issues · ★ %d%s%s%s".printf (
                prs, issues, stars, branch.length > 0 ? " · " + branch : "",
                release.length > 0 ? " · " + release : "", archived ? " · archived" : "")) {
                xalign = 0, ellipsize = Pango.EllipsizeMode.END
            };
            details.add_css_class ("repo-meta");
            card.append (top);
            card.append (details);
            repo_list.append (card);
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
