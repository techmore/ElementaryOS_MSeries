/* Native RepoBar settings for elementary OS, laid out like CodexBar Settings. Every control applies at once
 * through `mseries-repobar settings set` (no Save button, like elementary's own Settings). */
namespace MSeries {
    internal class RepoBarSettingsWindow : Gtk.ApplicationWindow {
        private string helper;
        private Json.Object settings = new Json.Object ();
        private Gtk.Label notice;
        private Gtk.Box hidden_card;
        private Gtk.Label account_label;
        private Gtk.Label account_detail;
        private Gtk.DropDown account_choice;
        private bool populating = false;
        private string[] account_values = { "" };
        private bool loading = true;

        public RepoBarSettingsWindow (Gtk.Application application) {
            GLib.Object (application: application, title: "RepoBar Settings", default_width: 520, default_height: 640);
            helper = GLib.Path.build_filename (Environment.get_home_dir (), ".local", "bin", "mseries-repobar");
            install_style ();
            settings = run_json ({ helper, "settings", "show" }) ?? new Json.Object ();

            var header = new Gtk.HeaderBar ();
            var about = new Gtk.Button.from_icon_name ("help-about-symbolic") { tooltip_text = "About RepoBar" };
            about.clicked.connect (() => {
                new Gtk.AboutDialog () {
                    transient_for = this, modal = true, program_name = "RepoBar",
                    logo_icon_name = "github-symbolic",
                    comments = "GitHub repositories in the elementary OS panel. RepoBar reads through the GitHub CLI and never stores your token.",
                    website = "https://github.com/techmore/ElementaryOS_MSeries",
                    website_label = "elementary OS port"
                }.present ();
            });
            header.pack_end (about);
            set_titlebar (header);

            var root = new Gtk.Box (Gtk.Orientation.VERTICAL, 0);
            root.append (build_account ());
            root.append (build_panel ());
            root.append (build_dashboard ());
            root.append (build_updates ());
            root.append (build_notifications ());
            root.append (build_local ());
            root.append (build_hidden ());
            var page = new Gtk.Box (Gtk.Orientation.VERTICAL, 0) { margin_top = 6, margin_bottom = 18, margin_start = 18, margin_end = 18 };
            page.append (root);
            notice = new Gtk.Label ("") { xalign = 0, wrap = true, visible = false, margin_start = 18, margin_end = 18, margin_bottom = 8 };
            notice.add_css_class ("rb-notice");
            var outer = new Gtk.Box (Gtk.Orientation.VERTICAL, 0);
            outer.append (new Gtk.ScrolledWindow () { child = page, hscrollbar_policy = Gtk.PolicyType.NEVER, vexpand = true });
            outer.append (notice);
            set_child (outer);
            refresh_account.begin ();
            notify["is-active"].connect (() => { if (is_active) refresh_account.begin (); });
            loading = false;
        }

        // ---- plumbing --------------------------------------------------------------------

        private static void install_style () {
            var style = new Gtk.CssProvider ();
            style.load_from_string (
                ".rb-card { border-radius: 9px; background: alpha(currentColor, 0.06); } " +
                ".rb-row { padding: 8px 12px; min-height: 30px; } " +
                ".rb-sub { font-size: 0.85em; opacity: 0.65; } " +
                ".rb-notice { color: @error_color; } " +
                ".rb-foot { font-size: 0.85em; opacity: 0.65; margin-top: 2px; }");
            Gtk.StyleContext.add_provider_for_display (Gdk.Display.get_default (), style, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION);
        }

        private static Json.Object? run_json (string[] argv) {
            try {
                string output;
                Process.spawn_sync (null, argv, null, SpawnFlags.STDERR_TO_DEV_NULL, null, out output, null, null);
                var parser = new Json.Parser ();
                parser.load_from_data (output);
                return parser.get_root ().get_object ();
            } catch (Error e) {
                return null;
            }
        }

        /* Applies one preference through the helper; on failure the helper's message is shown under the page. */
        private async bool apply (string key, string value) {
            if (loading) return true;
            try {
                var process = new GLib.Subprocess (SubprocessFlags.STDOUT_PIPE | SubprocessFlags.STDERR_PIPE,
                    helper, "settings", "set", key, value);
                string output;
                string error_text;
                yield process.communicate_utf8_async (null, null, out output, out error_text);
                if (!process.get_successful ()) throw new IOError.FAILED (error_text.strip ().length > 0 ? error_text.strip () : output.strip ());
                notice.set_visible (false);
                return true;
            } catch (Error e) {
                notice.set_text ("Couldn't save: " + e.message);
                notice.set_visible (true);
                return false;
            }
        }

        private Gtk.Box section (string title, string? footer = null) {
            var box = new Gtk.Box (Gtk.Orientation.VERTICAL, 4) { margin_top = 12 };
            box.append (new Granite.HeaderLabel (title));
            var card = new Gtk.Box (Gtk.Orientation.VERTICAL, 0);
            card.add_css_class ("rb-card");
            box.append (card);
            if (footer != null) {
                var note = new Gtk.Label (footer) { xalign = 0, wrap = true };
                note.add_css_class ("rb-foot");
                box.append (note);
            }
            return box;
        }

        private static Gtk.Box card_of (Gtk.Box section) {
            return (Gtk.Box) section.get_first_child ().get_next_sibling ();
        }

        private static void add_row (Gtk.Box section, Gtk.Widget row) {
            var card = card_of (section);
            if (card.get_first_child () != null) card.append (new Gtk.Separator (Gtk.Orientation.HORIZONTAL));
            card.append (row);
        }

        private static Gtk.Widget row (string title, string? subtitle, Gtk.Widget control) {
            var line = new Gtk.Box (Gtk.Orientation.HORIZONTAL, 12);
            line.add_css_class ("rb-row");
            control.update_property (Gtk.AccessibleProperty.LABEL, title, -1);
            var text = new Gtk.Box (Gtk.Orientation.VERTICAL, 1) { hexpand = true, valign = Gtk.Align.CENTER };
            text.append (new Gtk.Label (title) { xalign = 0, wrap = true });
            if (subtitle != null) {
                var sub = new Gtk.Label (subtitle) { xalign = 0, wrap = true };
                sub.add_css_class ("rb-sub");
                text.append (sub);
            }
            line.append (text);
            control.valign = Gtk.Align.CENTER;
            line.append (control);
            return line;
        }

        private Gtk.Switch toggle (string member, string key) {
            var sw = new Gtk.Switch () { active = settings.get_boolean_member_with_default (member, false) };
            bool reverting = false;
            sw.notify["active"].connect (() => {
                if (reverting) return;
                apply.begin (key, sw.active ? "true" : "false", (obj, res) => {
                    if (!apply.end (res)) { reverting = true; sw.active = !sw.active; reverting = false; }
                });
            });
            return sw;
        }

        /* Like toggle, for preferences that default to on. */
        private Gtk.Switch toggle_on (string member, string key) {
            var sw = toggle (member, key);
            if (!settings.has_member (member)) { loading = true; sw.active = true; loading = false; }
            return sw;
        }

        private Gtk.DropDown choice (string member, string key, string[] values, string[] labels) {
            var dropdown = new Gtk.DropDown (new Gtk.StringList (labels), null);
            string current = settings.has_member (member) ? settings.get_member (member).get_value ().strdup_contents ().replace ("\"", "") : "";
            for (int i = 0; i < values.length; i++) if (values[i] == current) dropdown.selected = i;
            dropdown.notify["selected"].connect (() => {
                if (dropdown.selected < values.length) apply.begin (key, values[dropdown.selected]);
            });
            return dropdown;
        }

        private Gtk.SpinButton spin (string member, string key, int min, int max, int fallback) {
            var button = new Gtk.SpinButton.with_range (min, max, 1) { numeric = true };
            button.value = (double) settings.get_int_member_with_default (member, fallback);
            uint source = 0;
            button.value_changed.connect (() => {
                if (source != 0) Source.remove (source);
                source = Timeout.add (350, () => {
                    source = 0;
                    apply.begin (key, ((int) button.value).to_string ());
                    return Source.REMOVE;
                });
            });
            return button;
        }

        // ---- sections --------------------------------------------------------------------

        private Gtk.Widget build_account () {
            var account = section ("Account",
                "RepoBar uses the GitHub CLI's sign-ins and reads as the account chosen here. Choosing one does not change which account git and other tools use. Your token stays with the GitHub CLI.");
            var line = new Gtk.Box (Gtk.Orientation.HORIZONTAL, 12);
            line.add_css_class ("rb-row");
            line.append (new Gtk.Image.from_icon_name ("github-symbolic") { pixel_size = 32 });
            var text = new Gtk.Box (Gtk.Orientation.VERTICAL, 1) { hexpand = true, valign = Gtk.Align.CENTER };
            account_label = new Gtk.Label ("Checking sign-in…") { xalign = 0 };
            account_label.add_css_class (Granite.STYLE_CLASS_H4_LABEL);
            account_detail = new Gtk.Label (settings.get_string_member_with_default ("host", "github.com")) { xalign = 0 };
            account_detail.add_css_class ("rb-sub");
            text.append (account_label);
            text.append (account_detail);
            line.append (text);
            var sign_in = new Gtk.Button.with_label ("Add Account…") { valign = Gtk.Align.CENTER, tooltip_text = "Sign another GitHub account in to the GitHub CLI" };
            sign_in.clicked.connect (() => {
                try {
                    Process.spawn_async (null, { "io.elementary.terminal", "-x", helper, "auth", "login" }, null,
                        SpawnFlags.SEARCH_PATH | SpawnFlags.STDOUT_TO_DEV_NULL | SpawnFlags.STDERR_TO_DEV_NULL, null, null);
                } catch (Error e) {
                    notice.set_text ("Open Terminal and run: gh auth login");
                    notice.set_visible (true);
                }
            });
            line.append (sign_in);
            add_row (account, line);
            account_choice = new Gtk.DropDown (new Gtk.StringList ({ "Follow GitHub CLI" }), null);
            account_choice.notify["selected"].connect (() => {
                if (populating || account_choice.selected >= account_values.length) return;
                apply.begin ("account", account_values[account_choice.selected], (obj, res) => {
                    apply.end (res);
                    refresh_account.begin ();
                });
            });
            add_row (account, row ("Read as", "Dashboard, notifications and clones use this account", account_choice));
            return account;
        }

        private Gtk.Widget build_panel () {
            var panel = section ("Panel",
                "Off hides RepoBar in the panel and taskbar and stops its refreshing and notifications. Open RepoBar Settings from the app launcher to turn it back on.");
            add_row (panel, row ("Show RepoBar in the panel", "Applies now and at every login", toggle_on ("showInPanel", "show-in-panel")));
            return panel;
        }

        private async void refresh_account () {
            try {
                var process = new GLib.Subprocess (SubprocessFlags.STDOUT_PIPE | SubprocessFlags.STDERR_SILENCE, helper, "auth", "status");
                string output;
                yield process.communicate_utf8_async (null, null, out output, null);
                var parser = new Json.Parser ();
                parser.load_from_data (output);
                var status = parser.get_root ().get_object ();
                bool authenticated = status.get_boolean_member_with_default ("authenticated", false);
                bool follows = status.get_boolean_member_with_default ("followsCli", true);
                string host = status.get_string_member_with_default ("host", "github.com");
                string login = status.get_string_member_with_default ("account", "");
                account_label.set_text (authenticated ? login : (login.length > 0 ? login + " is signed out" : "Not signed in"));
                account_detail.set_text (host + (authenticated ? " · read-only access" : " · sign in to see your repositories"));

                populating = true;
                string[] labels = { "Follow GitHub CLI" };
                account_values = { "" };
                uint selected = 0;
                if (status.has_member ("accounts")) {
                    status.get_array_member ("accounts").foreach_element ((array, index, node) => {
                        var item = node.get_object ();
                        string item_login = item.get_string_member_with_default ("login", "");
                        string item_host = item.get_string_member_with_default ("host", "github.com");
                        labels += item_login + " · " + item_host;
                        account_values += item_login + "@" + item_host;
                        if (!follows && item_login == login && item_host == host) selected = account_values.length - 1;
                    });
                }
                account_choice.model = new Gtk.StringList (labels);
                account_choice.selected = selected;
                populating = false;
            } catch (Error e) {
                populating = false;
                account_label.set_text ("GitHub CLI unavailable");
                account_detail.set_text ("Install the gh package, then sign in");
            }
        }

        private Gtk.Widget build_dashboard () {
            var dashboard = section ("Dashboard", "Pinned repositories always stay on the dashboard, above the most recently updated ones.");
            add_row (dashboard, row ("Recent repositories", "Shown below your pins", spin ("repoLimit", "repo-limit", 1, 100, 20)));
            add_row (dashboard, row ("Sort other lists by", "Pinned, Attention and All",
                choice ("menuSort", "menu-sort", { "activity", "prs", "issues", "stars", "repo" },
                    { "Recent activity", "Pull requests", "Issues", "Stars", "Name" })));
            add_row (dashboard, row ("Contribution graph", "Your activity over recent weeks", toggle_on ("showContributions", "show-contributions")));
            add_row (dashboard, row ("Graph style", "Click the graph's heading to expand or collapse it",
                choice ("contributionStyle", "contribution-style", { "dots", "fine", "squares" },
                    { "Dots", "Fine dots", "Squares" })));
            add_row (dashboard, row ("Show forks", null, toggle ("showForks", "show-forks")));
            add_row (dashboard, row ("Show archived repositories", null, toggle ("showArchived", "show-archived")));
            return dashboard;
        }

        private Gtk.Widget build_updates () {
            var updates = section ("Updates", "Each refresh uses a few GitHub API requests; your hourly allowance is shown in the panel menu.");
            add_row (updates, row ("Refresh every", null, choice ("refreshInterval", "refresh-interval",
                { "60", "120", "300", "900" }, { "Minute", "2 minutes", "5 minutes", "15 minutes" })));
            return updates;
        }

        private Gtk.Widget build_notifications () {
            var notifications = section ("Notifications", "Announced once per change, after a refresh; hidden and archived repositories stay quiet.");
            var sw = new Gtk.Switch () { active = settings.get_boolean_member_with_default ("notifyCi", true) };
            bool reverting = false;
            sw.notify["active"].connect (() => {
                if (reverting) return;
                apply.begin ("notify-ci", sw.active ? "true" : "false", (obj, res) => {
                    if (!apply.end (res)) { reverting = true; sw.active = !sw.active; reverting = false; }
                });
            });
            add_row (notifications, row ("CI status changes", "When a default branch starts failing or passes again", sw));
            var runs = new Gtk.Switch () { active = settings.get_boolean_member_with_default ("notifyWorkflows", true) };
            bool reverting_runs = false;
            runs.notify["active"].connect (() => {
                if (reverting_runs) return;
                apply.begin ("notify-workflows", runs.active ? "true" : "false", (obj, res) => {
                    if (!apply.end (res)) { reverting_runs = true; runs.active = !runs.active; reverting_runs = false; }
                });
            });
            add_row (notifications, row ("Workflow runs", "When a GitHub Actions run finishes on any branch or pull request", runs));
            return notifications;
        }

        private Gtk.Widget build_local () {
            var local = section ("Local Checkouts",
                "RepoBar matches clones in this folder to your repositories and shows their branch, changes and sync state. It never changes them on its own.");
            string root = settings.get_string_member_with_default ("localRoot", "");
            var folder_label = new Gtk.Label (root.length > 0 ? Path.get_basename (root) : "None") { ellipsize = Pango.EllipsizeMode.MIDDLE, max_width_chars = 18 };
            var folder_button = new Gtk.Button () { child = folder_label, tooltip_text = root.length > 0 ? root : "Choose a projects folder" };
            var clear = new Gtk.Button.from_icon_name ("edit-clear-symbolic") { tooltip_text = "Stop scanning", sensitive = root.length > 0 };
            clear.add_css_class ("flat");
            folder_button.clicked.connect (() => {
                var dialog = new Gtk.FileDialog () { title = "Choose Projects Folder", modal = true };
                dialog.select_folder.begin (this, null, (obj, res) => {
                    try {
                        var file = dialog.select_folder.end (res);
                        if (file == null || file.get_path () == null) return;
                        string path = file.get_path ();
                        apply.begin ("local-root", path, (o, r) => {
                            if (!apply.end (r)) return;
                            folder_label.set_text (Path.get_basename (path));
                            folder_button.set_tooltip_text (path);
                            clear.set_sensitive (true);
                        });
                    } catch (Error e) {
                        // Dismissed.
                    }
                });
            });
            clear.clicked.connect (() => {
                apply.begin ("local-root", "", (o, r) => {
                    if (!apply.end (r)) return;
                    folder_label.set_text ("None");
                    folder_button.set_tooltip_text ("Choose a projects folder");
                    clear.set_sensitive (false);
                });
            });
            var controls = new Gtk.Box (Gtk.Orientation.HORIZONTAL, 4);
            controls.append (folder_button);
            controls.append (clear);
            add_row (local, row ("Projects folder", null, controls));
            add_row (local, row ("Search depth", "Folder levels below the projects folder", spin ("localDepth", "local-depth", 1, 10, 4)));
            return local;
        }

        private Gtk.Widget build_hidden () {
            var hidden = section ("Hidden Repositories", "Hide repositories from the panel menu with a right-click. They still appear under All.");
            hidden_card = card_of (hidden);
            rebuild_hidden ();
            return hidden;
        }

        private void rebuild_hidden () {
            while (hidden_card.get_first_child () != null) hidden_card.remove (hidden_card.get_first_child ());
            string[] names = {};
            if (settings.has_member ("repoStates")) {
                var states = settings.get_object_member ("repoStates");
                foreach (var name in states.get_members ()) {
                    if (states.get_string_member_with_default (name, "") == "hidden") names += name;
                }
            }
            if (names.length == 0) {
                var empty = new Gtk.Label ("No hidden repositories") { xalign = 0 };
                empty.add_css_class ("rb-sub");
                var line = new Gtk.Box (Gtk.Orientation.HORIZONTAL, 0);
                line.add_css_class ("rb-row");
                line.append (empty);
                hidden_card.append (line);
                return;
            }
            for (int i = 0; i < names.length; i++) {
                string name = names[i];
                if (i > 0) hidden_card.append (new Gtk.Separator (Gtk.Orientation.HORIZONTAL));
                var show = new Gtk.Button.with_label ("Show");
                show.clicked.connect (() => show_repository.begin (name));
                hidden_card.append (row (name, null, show));
            }
        }

        private async void show_repository (string name) {
            try {
                var process = new GLib.Subprocess (SubprocessFlags.STDOUT_SILENCE | SubprocessFlags.STDERR_PIPE, helper, "show", name);
                string error_text;
                yield process.communicate_utf8_async (null, null, null, out error_text);
                if (!process.get_successful ()) throw new IOError.FAILED (error_text.strip ());
                settings = run_json ({ helper, "settings", "show" }) ?? settings;
                rebuild_hidden ();
            } catch (Error e) {
                notice.set_text ("Couldn't show " + name + ": " + e.message);
                notice.set_visible (true);
            }
        }
    }

    internal class RepoBarSettingsApp : Gtk.Application {
        public RepoBarSettingsApp () {
            GLib.Object (application_id: "io.github.techmore.RepoBar.Settings", flags: ApplicationFlags.DEFAULT_FLAGS);
        }

        protected override void startup () {
            base.startup ();
            Granite.init ();
            var quit = new SimpleAction ("quit", null);
            quit.activate.connect (() => this.quit ());
            add_action (quit);
            set_accels_for_action ("app.quit", { "<Control>q", "<Control>w" });
        }

        protected override void activate () {
            var window = active_window ?? new RepoBarSettingsWindow (this);
            window.present ();
        }
    }

    int main (string[] args) {
        return new RepoBarSettingsApp ().run (args);
    }
}
