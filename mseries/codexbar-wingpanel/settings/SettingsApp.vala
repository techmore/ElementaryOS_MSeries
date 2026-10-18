/* Native CodexBar settings for elementary OS. Replaces upstream's Qt window: same linux.json keys, applied live
 * through `codexbar-linux --configure` (no Save button, like elementary's own Settings). */
namespace MSeries {
    internal class SettingsWindow : Gtk.ApplicationWindow {
        private SettingsModel model = new SettingsModel ();
        private string app_path;
        private string cli_path;
        private string config_path;
        private string[] pending_keys = {};
        private uint apply_source = 0;
        private Gtk.Label notice;
        private Gtk.ListBox provider_list;
        private Gtk.DropDown provider_picker;
        private Gtk.StringList picker_model = new Gtk.StringList (null);
        private string[] picker_ids = {};
        private HashTable<string, string> names = new HashTable<string, string> (str_hash, str_equal);
        private bool loading = true;

        public SettingsWindow (Gtk.Application application) {
            GLib.Object (application: application, title: "CodexBar Settings", default_width: 560, default_height: 640);
            app_path = GLib.Path.build_filename (Environment.get_home_dir (), ".local", "bin", "codexbar-linux");
            cli_path = GLib.Path.build_filename (Environment.get_home_dir (), ".local", "bin", "codexbar");
            config_path = GLib.Path.build_filename (Environment.get_user_config_dir (), "codexbar", "linux.json");
            install_style ();
            reload ();

            var stack = new Gtk.Stack () { transition_type = Gtk.StackTransitionType.CROSSFADE };
            stack.add_titled (page (build_general ()), "general", "General");
            stack.add_titled (page (build_display ()), "display", "Display");
            stack.add_titled (page (build_providers ()), "providers", "Providers");
            var start_page = Environment.get_variable ("CODEXBAR_SETTINGS_PAGE");  // used by the headless render probe
            if (start_page != null && stack.get_child_by_name (start_page) != null) {
                stack.visible_child_name = start_page;
            }
            var switcher = new Gtk.StackSwitcher () { stack = stack };
            var header = new Gtk.HeaderBar ();
            header.title_widget = switcher;
            set_titlebar (header);

            notice = new Gtk.Label ("") { xalign = 0, wrap = true, visible = false, margin_start = 16, margin_end = 16 };
            notice.add_css_class ("cb-notice");
            var outer = new Gtk.Box (Gtk.Orientation.VERTICAL, 0);
            outer.append (stack);
            outer.append (notice);
            set_child (outer);
            loading = false;
        }

        // ---- plumbing --------------------------------------------------------------------

        private static void install_style () {
            var style = new Gtk.CssProvider ();
            style.load_from_string (
                ".cb-card { border-radius: 9px; background: alpha(currentColor, 0.06); } " +
                ".cb-row { padding: 8px 12px; } " +
                ".cb-card list, .cb-card row { background: transparent; } " +
                ".cb-sub { font-size: 0.85em; opacity: 0.65; } " +
                ".cb-notice { color: @error_color; padding-bottom: 8px; } " +
                ".cb-foot { font-size: 0.85em; opacity: 0.65; }");
            Gtk.StyleContext.add_provider_for_display (Gdk.Display.get_default (), style, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION);
        }

        private void reload () {
            try {
                string text;
                FileUtils.get_contents (config_path, out text);
                model.load_from_data (text);
            } catch (Error e) {
                // defaults
            }
            try {
                string out_text;
                Process.spawn_command_line_sync ("%s config providers --format json".printf (Shell.quote (cli_path)), out out_text);
                var parser = new Json.Parser ();
                parser.load_from_data (out_text, -1);
                var array = parser.get_root ().get_array ();
                for (uint i = 0; i < array.get_length (); i++) {
                    var item = array.get_object_element (i);
                    var id = item.get_string_member ("provider");
                    names.insert (id, item.get_string_member ("displayName"));
                    picker_ids += id;
                    picker_model.append (item.get_string_member ("displayName"));
                }
            } catch (Error e) {
                // the picker stays empty; the provider list still works
            }
        }

        private void changed (string key) {
            if (loading) {
                return;
            }
            if (!(key in pending_keys)) {
                pending_keys += key;
            }
            if (apply_source != 0) {
                Source.remove (apply_source);
            }
            apply_source = Timeout.add (350, () => {
                apply_source = 0;
                apply_pending.begin ();
                return Source.REMOVE;
            });
        }

        private async void apply_pending () {
            var keys = pending_keys;
            pending_keys = {};
            if (keys.length == 0) {
                return;
            }
            try {
                var process = new GLib.Subprocess (SubprocessFlags.STDERR_PIPE | SubprocessFlags.STDOUT_PIPE,
                    app_path, "--configure", model.patch_for (keys));
                string reply;
                string error_text;
                yield process.communicate_utf8_async (null, null, out reply, out error_text);
                if (process.get_successful ()) {
                    notice.set_visible (false);
                } else {
                    // The app answers {"ok":false,"error":"..."} on stdout.
                    var reason = "";
                    try {
                        var parser = new Json.Parser ();
                        parser.load_from_data (reply, -1);
                        reason = parser.get_root ().get_object ().get_string_member_with_default ("error", "");
                    } catch (Error e) {
                        reason = error_text.strip ();
                    }
                    notice.set_text ("CodexBar didn't accept that change" + (reason.length > 0 ? ": " + reason : ". Is CodexBar running?"));
                    notice.set_visible (true);
                }
            } catch (Error e) {
                notice.set_text ("Couldn't reach CodexBar: " + e.message);
                notice.set_visible (true);
            }
        }

        // ---- building blocks -------------------------------------------------------------

        private static Gtk.Widget page (Gtk.Widget content) {
            var box = new Gtk.Box (Gtk.Orientation.VERTICAL, 0) { margin_top = 12, margin_bottom = 16, margin_start = 18, margin_end = 18 };
            box.append (content);
            return new Gtk.ScrolledWindow () { child = box, hscrollbar_policy = Gtk.PolicyType.NEVER, vexpand = true };
        }

        private Gtk.Box section (string title, string? footer = null) {
            var box = new Gtk.Box (Gtk.Orientation.VERTICAL, 4) { margin_top = 10 };
            box.append (new Granite.HeaderLabel (title));
            var card = new Gtk.Box (Gtk.Orientation.VERTICAL, 0);
            card.add_css_class ("cb-card");
            card.name = "card";
            box.append (card);
            if (footer != null) {
                var note = new Gtk.Label (footer) { xalign = 0, wrap = true };
                note.add_css_class ("cb-foot");
                box.append (note);
            }
            return box;
        }

        private static Gtk.Box card_of (Gtk.Box section) {
            return (Gtk.Box) section.get_first_child ().get_next_sibling ();
        }

        private Gtk.Widget row (string title, string? subtitle, Gtk.Widget control) {
            var line = new Gtk.Box (Gtk.Orientation.HORIZONTAL, 12);
            line.add_css_class ("cb-row");
            var text = new Gtk.Box (Gtk.Orientation.VERTICAL, 1) { hexpand = true, valign = Gtk.Align.CENTER };
            text.append (new Gtk.Label (title) { xalign = 0, wrap = true });
            if (subtitle != null) {
                var sub = new Gtk.Label (subtitle) { xalign = 0, wrap = true };
                sub.add_css_class ("cb-sub");
                text.append (sub);
            }
            line.append (text);
            control.valign = Gtk.Align.CENTER;
            line.append (control);
            return line;
        }

        private Gtk.Switch toggle (string key) {
            var sw = new Gtk.Switch () { active = model.get_bool (key) };
            sw.notify["active"].connect (() => {
                model.values.set_boolean_member (key, sw.active);
                changed (key);
            });
            return sw;
        }

        private Gtk.SpinButton spin (string key, int min, int max, int step) {
            var button = new Gtk.SpinButton.with_range (min, max, step) { numeric = true };
            button.value = model.get_int (key);
            button.value_changed.connect (() => {
                model.values.set_int_member (key, (int64) button.value);
                changed (key);
            });
            return button;
        }

        private Gtk.DropDown choice (string key, string[] ids, string[] labels) {
            var dropdown = new Gtk.DropDown (new Gtk.StringList (labels), null);
            for (int i = 0; i < ids.length; i++) {
                if (ids[i] == model.get_string (key)) {
                    dropdown.selected = i;
                }
            }
            dropdown.notify["selected"].connect (() => {
                if (dropdown.selected < ids.length) {
                    model.values.set_string_member (key, ids[dropdown.selected]);
                    changed (key);
                }
            });
            return dropdown;
        }

        private static void add_row (Gtk.Box section, Gtk.Widget row, bool first = false) {
            var card = card_of (section);
            if (card.get_first_child () != null) {
                card.append (new Gtk.Separator (Gtk.Orientation.HORIZONTAL));
            }
            card.append (row);
        }

        // ---- pages -----------------------------------------------------------------------

        private Gtk.Widget build_general () {
            var root = new Gtk.Box (Gtk.Orientation.VERTICAL, 0);

            var updates = section ("Updates");
            add_row (updates, row ("Refresh every", "Seconds between background checks", spin ("refreshSeconds", 60, 3600, 60)));
            add_row (updates, row ("Refresh when opening usage", null, toggle ("refreshOnOpen")));
            add_row (updates, row ("Service status", "Show provider outages", toggle ("showStatus")));
            root.append (updates);

            var alerts = section ("Notifications");
            var threshold = spin ("notifyThreshold", 1, 99, 1);
            threshold.sensitive = model.get_bool ("notifications");
            var notifications = toggle ("notifications");
            notifications.notify["active"].connect (() => { threshold.sensitive = notifications.active; });
            add_row (alerts, row ("Notify me", "Low quota, resets and outages", notifications));
            add_row (alerts, row ("Low quota threshold", "Percent remaining", threshold));
            root.append (alerts);

            var desktop = section ("Desktop", "CodexBar keeps running when its windows are closed.");
            add_row (desktop, row ("Start at login", null, autostart_switch ()));
            add_row (desktop, row ("Tray icon", null, toggle ("showTray")));
            add_row (desktop, row ("Compact Quick View from the tray", null, toggle ("compactQuickView")));
            add_row (desktop, row ("Tray style", null, choice ("trayStyle", { "meters", "icon" }, { "Meters", "Icon" })));
            add_row (desktop, row ("Local spending", "Estimate cost from local history", toggle ("showCosts")));
            root.append (desktop);
            return root;
        }

        private Gtk.Switch autostart_switch () {
            var sw = new Gtk.Switch ();
            try {
                string out_text;
                Process.spawn_command_line_sync ("%s --autostart status".printf (Shell.quote (app_path)), out out_text);
                sw.active = out_text.contains ("\"enabled\":true");
            } catch (Error e) {
                sw.sensitive = false;
            }
            sw.notify["active"].connect (() => {
                if (loading) {
                    return;
                }
                try {
                    Process.spawn_command_line_async ("%s --autostart %s".printf (Shell.quote (app_path), sw.active ? "enable" : "disable"));
                } catch (Error e) {
                    notice.set_text ("Couldn't change start at login: " + e.message);
                    notice.set_visible (true);
                }
            });
            return sw;
        }

        private Gtk.Widget build_display () {
            var root = new Gtk.Box (Gtk.Orientation.VERTICAL, 0);
            var quota = section ("Quota");
            add_row (quota, row ("Show", null, choice ("quotaDisplay", { "remaining", "used" }, { "Remaining", "Used" })));
            add_row (quota, row ("Reset time", null, choice ("resetDisplay", { "countdown", "absolute", "both" }, { "Countdown", "Clock time", "Both" })));
            add_row (quota, row ("Highlight low quota", null, toggle ("warningColors")));
            add_row (quota, row ("Show pace", "Whether you're ahead of or behind an even pace", toggle ("showPace")));
            root.append (quota);

            var bar = section ("Menu bar");
            add_row (bar, row ("Providers in the bar", "How many to show side by side", spin ("barProviders", 0, 80, 1)));
            add_row (bar, row ("Session, weekly and pace", "More detail next to each provider", toggle ("showBarDetail")));
            add_row (bar, row ("Per-model caps", null, toggle ("showScopedCaps")));
            root.append (bar);
            return root;
        }

        private Gtk.Widget build_providers () {
            var root = new Gtk.Box (Gtk.Orientation.VERTICAL, 0);
            var shown = section ("Providers", "The order here is the order in the panel. Sign in and switch accounts from the panel's Accounts section.");
            provider_list = new Gtk.ListBox () { selection_mode = Gtk.SelectionMode.NONE };
            provider_list.add_css_class ("cb-listbox");
            card_of (shown).append (provider_list);
            rebuild_providers ();
            root.append (shown);

            var add = section ("Add a provider");
            provider_picker = new Gtk.DropDown (picker_model, null) { enable_search = true, hexpand = true };
            var add_button = new Gtk.Button.with_label ("Add");
            add_button.add_css_class ("suggested-action");
            add_button.clicked.connect (() => {
                var index = (int) provider_picker.selected;
                if (index >= 0 && index < picker_ids.length && model.add_provider (picker_ids[index])) {
                    enable_in_cli (picker_ids[index]);
                    rebuild_providers ();
                    changed ("providerOrder");
                    changed ("provider");
                }
            });
            var line = new Gtk.Box (Gtk.Orientation.HORIZONTAL, 8);
            line.add_css_class ("cb-row");
            line.append (provider_picker);
            line.append (add_button);
            card_of (add).append (line);
            root.append (add);

            var advanced = section ("Advanced");
            add_row (advanced, row ("Data source", "Where usage is read from", choice ("source", { "auto", "oauth", "cli", "api", "web" },
                { "Automatic", "OAuth", "Command line", "API", "Web" })));
            add_row (advanced, row ("Show account identity", null, toggle ("showIdentity")));
            root.append (advanced);
            return root;
        }

        private void enable_in_cli (string id) {
            try {
                Process.spawn_command_line_async ("%s config enable --provider %s".printf (Shell.quote (cli_path), Shell.quote (id)));
            } catch (Error e) {
                // the provider is still listed; the CLI may enable it itself
            }
        }

        private void rebuild_providers () {
            Gtk.Widget? child = provider_list.get_first_child ();
            while (child != null) {
                var next = child.get_next_sibling ();
                provider_list.remove (child);
                child = next;
            }
            var ids = model.providers ();
            for (int i = 0; i < ids.length; i++) {
                provider_list.append (provider_row (ids[i], i, ids.length));
            }
        }

        private Gtk.Widget provider_row (string id, int index, int count) {
            var line = new Gtk.Box (Gtk.Orientation.HORIZONTAL, 8);
            line.add_css_class ("cb-row");
            var mark = "mseries-codexbar-%s-symbolic".printf (id == "codex" ? "openai" : id == "opencodego" ? "opencode" : id);
            var icon = new Gtk.Image.from_icon_name (Gtk.IconTheme.get_for_display (Gdk.Display.get_default ()).has_icon (mark)
                ? mark : "application-x-executable-symbolic") { pixel_size = 16 };
            line.append (icon);
            line.append (new Gtk.Label (names.contains (id) ? names.get (id) : id) { xalign = 0, hexpand = true });
            line.append (icon_button ("go-up-symbolic", "Move up", index > 0, () => {
                if (model.move_provider (id, -1)) { rebuild_providers (); changed ("providerOrder"); }
            }));
            line.append (icon_button ("go-down-symbolic", "Move down", index < count - 1, () => {
                if (model.move_provider (id, 1)) { rebuild_providers (); changed ("providerOrder"); }
            }));
            line.append (icon_button ("edit-delete-symbolic", "Remove", count > 1, () => {
                if (model.remove_provider (id)) { rebuild_providers (); changed ("providerOrder"); }
            }));
            return line;
        }

        private delegate void Callback ();

        private Gtk.Button icon_button (string icon_name, string label, bool enabled, owned Callback on_click) {
            var button = new Gtk.Button.from_icon_name (icon_name) { tooltip_text = label, sensitive = enabled };
            button.add_css_class ("flat");
            button.update_property (Gtk.AccessibleProperty.LABEL, label, -1);
            button.clicked.connect (() => on_click ());
            return button;
        }
    }

    internal class SettingsApp : Gtk.Application {
        public SettingsApp () {
            GLib.Object (application_id: "com.steipete.CodexBar.Settings", flags: ApplicationFlags.DEFAULT_FLAGS);
        }

        protected override void activate () {
            var window = active_window;
            if (window == null) {
                window = new SettingsWindow (this);
            }
            window.present ();
        }
    }

    int main (string[] args) {
        return new SettingsApp ().run (args);
    }
}
