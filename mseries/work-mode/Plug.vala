/* Windows-inspired Work Mode preferences for elementary OS System Settings. */
namespace MSeriesWorkMode {
    private delegate void Sync ();

    public class Plug : Switchboard.Plug {
        private Gtk.Widget? content;
        private GLib.Settings settings;
        private Adw.ActionRow status_row;
        private Adw.EntryRow ips_row;
        private Adw.ActionRow current_ip_row;
        private Gtk.Button check_button;
        private Gtk.Button add_button;
        private string? current_ip = null;
        private uint apply_source = 0;

        public Plug () {
            var supported = new Gee.TreeMap<string, string?> (null, null);
            supported.set ("personal/work-mode", "Windows Work Mode");
            Object (
                category: Category.PERSONAL,
                code_name: "io.elementary.settings.work-mode",
                display_name: "Windows Work Mode",
                description: "Use a Windows-inspired work wallpaper and bottom dock",
                icon: "preferences-desktop-wallpaper",
                supported_settings: supported
            );
            settings = new GLib.Settings ("io.elementary.mseries.work-mode");
        }

        public override Gtk.Widget get_widget () {
            if (content == null) {
                var page = new Adw.PreferencesPage ();
                var switch_group = new Adw.PreferencesGroup () {
                    title = "Desktop mode",
                    description = "Switch the whole desktop now. It applies immediately; nothing is closed and you stay logged in."
                };
                page.add (switch_group);
                var mode_row = new Adw.ActionRow () {
                    title = "Current desktop"
                };
                var elementary_button = new Gtk.ToggleButton.with_label ("elementary") { valign = Gtk.Align.CENTER };
                var windows_button = new Gtk.ToggleButton.with_label ("Windows 11") { valign = Gtk.Align.CENTER, group = elementary_button };
                var segmented = new Gtk.Box (Gtk.Orientation.HORIZONTAL, 0) { valign = Gtk.Align.CENTER };
                segmented.add_css_class ("linked");
                segmented.append (elementary_button);
                segmented.append (windows_button);
                mode_row.add_suffix (segmented);
                switch_group.add (mode_row);
                // One source of truth: the same `enabled` key the switch below and the launcher use.
                var syncing = false;
                Sync sync_mode = () => {
                    syncing = true;
                    var on = settings.get_boolean ("enabled");
                    windows_button.active = on;
                    elementary_button.active = !on;
                    mode_row.subtitle = on ? "Windows 11 mode" : "Native elementary mode";
                    syncing = false;
                };
                windows_button.toggled.connect (() => {
                    if (!syncing) settings.set_boolean ("enabled", windows_button.active);
                });
                settings.changed["enabled"].connect (() => sync_mode ());
                sync_mode ();

                var mode_group = new Adw.PreferencesGroup () {
                    title = "Windows Work Mode",
                    description = "Use a Windows-inspired wallpaper and app dock while you work."
                };
                page.add (mode_group);

                var enabled = new Adw.SwitchRow () {
                    title = "Use Windows Work Mode"
                };
                settings.bind ("enabled", enabled, "active", GLib.SettingsBindFlags.DEFAULT);
                mode_group.add (enabled);

                var wallpaper = new Adw.ActionRow () {
                    title = "Work wallpaper",
                    subtitle = wallpaper_name ()
                };
                var wallpaper_options = new Gtk.StringList (null);
                wallpaper_options.append ("Azure Bloom");
                wallpaper_options.append ("Blue Flow");
                wallpaper_options.append ("Blue Ribbons");
                wallpaper_options.append ("Violet Arc");
                wallpaper_options.append ("Forest Flow");
                var wallpaper_dropdown = new Gtk.DropDown (wallpaper_options, null) {
                    valign = Gtk.Align.CENTER
                };
                wallpaper_dropdown.selected = wallpaper_option_index ();
                wallpaper_dropdown.notify["selected"].connect (() => {
                    string[] files = {
                        "work-mode-azure-bloom.png", "work-mode-blue-flow.png", "work-mode-blue-ribbons.png",
                        "work-mode-violet-arc.png", "work-mode-forest-flow.png"
                    };
                    if (wallpaper_dropdown.selected < files.length) {
                        set_bundled_wallpaper (files[wallpaper_dropdown.selected], wallpaper);
                    }
                });
                wallpaper.add_suffix (wallpaper_dropdown);
                var browse = new Gtk.Button.with_label ("Browse…") {
                    valign = Gtk.Align.CENTER
                };
                browse.clicked.connect (() => choose_wallpaper (wallpaper));
                wallpaper.add_suffix (browse);
                mode_group.add (wallpaper);

                var schedule_group = new Adw.PreferencesGroup () {
                    title = "Schedule",
                    description = "Turn on automatically during your work hours."
                };
                page.add (schedule_group);

                var scheduled = new Adw.SwitchRow () {
                    title = "Schedule Windows Work Mode"
                };
                settings.bind ("scheduled", scheduled, "active", GLib.SettingsBindFlags.DEFAULT);
                schedule_group.add (scheduled);

                var weekdays = new Adw.SwitchRow () {
                    title = "Weekdays only"
                };
                settings.bind ("weekdays-only", weekdays, "active", GLib.SettingsBindFlags.DEFAULT);
                schedule_group.add (weekdays);

                var start = time_row ("Start time (24-hour)", "start-time");
                schedule_group.add (start);
                var end = time_row ("End time (24-hour)", "end-time");
                schedule_group.add (end);
                foreach (var row in new Gtk.Widget[] { weekdays, start, end }) {
                    settings.bind ("scheduled", row, "sensitive", GLib.SettingsBindFlags.GET);
                }

                var network_group = new Adw.PreferencesGroup () {
                    title = "Work Network",
                    description = "Turn on only when this computer's public IP address matches your workplace. Checking the address contacts %s.".printf (service_host ())
                };
                page.add (network_group);

                var network = new Adw.SwitchRow () {
                    title = "Only on work networks"
                };
                settings.bind ("network-trigger", network, "active", GLib.SettingsBindFlags.DEFAULT);
                network_group.add (network);

                ips_row = new Adw.EntryRow () {
                    title = "Work public IP addresses (comma-separated, CIDR allowed)",
                    show_apply_button = true,
                    text = string.joinv (", ", settings.get_strv ("work-public-ips"))
                };
                ips_row.apply.connect (apply_ips);
                ips_row.changed.connect (() => ips_row.remove_css_class ("error"));
                network_group.add (ips_row);

                current_ip_row = new Adw.ActionRow () {
                    title = "Current public IP address",
                    subtitle = "Not checked"
                };
                check_button = new Gtk.Button.with_label ("Check") {
                    valign = Gtk.Align.CENTER,
                    tooltip_text = "Look up this computer's public IP address"
                };
                check_button.clicked.connect (check_public_ip);
                current_ip_row.add_suffix (check_button);
                add_button = new Gtk.Button.with_label ("Add") {
                    valign = Gtk.Align.CENTER,
                    sensitive = false,
                    tooltip_text = "Add this address to the work public IP addresses"
                };
                add_button.clicked.connect (add_current_ip);
                current_ip_row.add_suffix (add_button);
                network_group.add (current_ip_row);

                foreach (var row in new Gtk.Widget[] { ips_row, current_ip_row }) {
                    settings.bind ("network-trigger", row, "sensitive", GLib.SettingsBindFlags.GET);
                }

                var status_group = new Adw.PreferencesGroup () {
                    title = "Status"
                };
                page.add (status_group);
                status_row = new Adw.ActionRow () {
                    title = "Current state",
                    subtitle = "Checking…"
                };
                status_group.add (status_row);
                var dock_row = new Adw.ActionRow () {
                    title = "Windows-style bottom dock",
                    subtitle = "Uses your existing pinned apps and running windows."
                };
                status_group.add (dock_row);

                // A change takes effect immediately; the user timer keeps the rules in sync.
                settings.changed.connect (() => apply_now ());
                refresh_status ();
                content = page;
            }
            return content;
        }

        private static string helper_path () {
            return GLib.Path.build_filename (GLib.Environment.get_home_dir (), ".local", "bin", "mseries-work-mode");
        }

        private string service_host () {
            var service = settings.get_string ("public-ip-service");
            var host = GLib.Uri.peek_scheme (service) != null ? service.split ("/")[2] : null;
            return host ?? service;
        }

        private Adw.EntryRow time_row (string title, string key) {
            var row = new Adw.EntryRow () {
                title = title,
                show_apply_button = true,
                text = settings.get_string (key)
            };
            row.apply.connect (() => {
                var value = row.text.strip ();
                if (!GLib.Regex.match_simple ("^([01][0-9]|2[0-3]):[0-5][0-9]$", value)) {
                    row.add_css_class ("error");
                    row.title = "%s — use HH:MM".printf (title);
                    return;
                }
                row.remove_css_class ("error");
                row.title = title;
                settings.set_string (key, value);
            });
            return row;
        }

        private void apply_ips () {
            string[] addresses = {};
            foreach (var part in ips_row.text.split (",")) {
                var entry = part.strip ();
                if (entry == "") {
                    continue;
                }
                var mask = entry.contains ("/") ? entry : null;
                try {
                    if (mask != null) {
                        new GLib.InetAddressMask.from_string (entry);
                    } else if (new GLib.InetAddress.from_string (entry) == null) {
                        throw new GLib.IOError.INVALID_ARGUMENT ("invalid address");
                    }
                } catch (GLib.Error error) {
                    ips_row.add_css_class ("error");
                    ips_row.title = "“%s” is not an IP address or CIDR range".printf (entry);
                    return;
                }
                addresses += entry;
            }
            ips_row.remove_css_class ("error");
            ips_row.title = "Work public IP addresses (comma-separated, CIDR allowed)";
            settings.set_strv ("work-public-ips", addresses);
        }

        private void check_public_ip () {
            check_button.sensitive = false;
            current_ip_row.subtitle = "Checking…";
            run_helper.begin ({ "--public-ip" }, (obj, res) => {
                string? output = run_helper.end (res);
                check_button.sensitive = true;
                if (output == null || output.strip () == "") {
                    current_ip = null;
                    add_button.sensitive = false;
                    current_ip_row.subtitle = "Couldn’t check. Make sure you’re online, then try again.";
                    return;
                }
                current_ip = output.strip ();
                var listed = current_ip in settings.get_strv ("work-public-ips");
                add_button.sensitive = !listed;
                current_ip_row.subtitle = listed ? "%s · already a work address".printf (current_ip) : current_ip;
                refresh_status ();
            });
        }

        private void add_current_ip () {
            if (current_ip == null) {
                return;
            }
            var addresses = settings.get_strv ("work-public-ips");
            if (!(current_ip in addresses)) {
                addresses += current_ip;
                settings.set_strv ("work-public-ips", addresses);
            }
            ips_row.text = string.joinv (", ", settings.get_strv ("work-public-ips"));
            add_button.sensitive = false;
            current_ip_row.subtitle = "%s · already a work address".printf (current_ip);
        }

        private void apply_now () {
            // Coalesce bursts of changes into one serialized run of the user service.
            if (apply_source != 0) {
                GLib.Source.remove (apply_source);
            }
            apply_source = GLib.Timeout.add (300, () => {
                apply_source = 0;
                try {
                    new GLib.Subprocess.newv (
                        { "systemctl", "--user", "start", "mseries-work-mode.service" },
                        GLib.SubprocessFlags.STDOUT_SILENCE | GLib.SubprocessFlags.STDERR_SILENCE
                    ).wait_async.begin (null, () => refresh_status ());
                } catch (GLib.Error error) {
                    status_row.subtitle = "Couldn’t apply Windows Work Mode: %s".printf (error.message);
                }
                return GLib.Source.REMOVE;
            });
        }

        private void refresh_status () {
            run_helper.begin ({ "--status" }, (obj, res) => {
                string? output = run_helper.end (res);
                status_row.subtitle = output != null && output.strip () != ""
                    ? output.strip ()
                    : "Status unavailable. Reinstall Windows Work Mode.";
            });
        }

        private async string? run_helper (string[] args) {
            string[] argv = { helper_path () };
            foreach (var arg in args) {
                argv += arg;
            }
            try {
                var process = new GLib.Subprocess.newv (
                    argv, GLib.SubprocessFlags.STDOUT_PIPE | GLib.SubprocessFlags.STDERR_SILENCE
                );
                string? stdout_text;
                yield process.communicate_utf8_async (null, null, out stdout_text, null);
                return process.get_successful () ? stdout_text : null;
            } catch (GLib.Error error) {
                warning ("Windows Work Mode helper failed: %s", error.message);
                return null;
            }
        }

        private string wallpaper_name () {
            var path = settings.get_string ("work-wallpaper");
            if (path == "") {
                return "No image selected";
            }
            switch (GLib.Path.get_basename (path)) {
            case "work-mode-azure-bloom.png": return "Azure Bloom";
            case "work-mode-blue-flow.png": return "Blue Flow";
            case "work-mode-blue-ribbons.png": return "Blue Ribbons";
            case "work-mode-violet-arc.png": return "Violet Arc";
            case "work-mode-forest-flow.png": return "Forest Flow";
            default: return GLib.Path.get_basename (path);
            }
        }

        private uint wallpaper_option_index () {
            var basename = GLib.Path.get_basename (settings.get_string ("work-wallpaper"));
            switch (basename) {
            case "work-mode-azure-bloom.png": return 0;
            case "work-mode-blue-flow.png": return 1;
            case "work-mode-blue-ribbons.png": return 2;
            case "work-mode-violet-arc.png": return 3;
            case "work-mode-forest-flow.png": return 4;
            default: return Gtk.INVALID_LIST_POSITION;
            }
        }

        private void set_bundled_wallpaper (string filename, Adw.ActionRow row) {
            var path = GLib.Path.build_filename ("/usr/share", "backgrounds", "mseries", filename);
            settings.set_string ("work-wallpaper", path);
            row.subtitle = wallpaper_name ();
        }

        private void choose_wallpaper (Adw.ActionRow row) {
            var chooser = new Gtk.FileChooserNative (
                "Choose a work wallpaper",
                null,
                Gtk.FileChooserAction.OPEN,
                "Choose",
                "Cancel"
            );
            var filter = new Gtk.FileFilter () {
                name = "Images"
            };
            foreach (var pattern in new string[] { "*.png", "*.jpg", "*.jpeg", "*.webp", "*.bmp", "*.tif", "*.tiff" }) {
                filter.add_pattern (pattern);
            }
            chooser.add_filter (filter);
            chooser.response.connect ((response) => {
                if (response == Gtk.ResponseType.ACCEPT) {
                    var file = chooser.get_file ();
                    if (file != null && file.get_path () != null) {
                        settings.set_string ("work-wallpaper", file.get_path ());
                        row.subtitle = wallpaper_name ();
                    }
                }
                chooser.destroy ();
            });
            chooser.show ();
        }

        public override void shown () {
            if (status_row != null) {
                refresh_status ();
            }
        }
        public override void hidden () {}

        public override void search_callback (string location) {}

        public override async Gee.TreeMap<string, string> search (string query) {
            var results = new Gee.TreeMap<string, string> (
                (GLib.CompareDataFunc<string>) strcmp,
                (Gee.EqualDataFunc<string>) str_equal
            );
            results.set ("Windows Work Mode", "Windows Work Mode");
            results.set ("Windows Work Mode → Schedule", "Windows Work Mode");
            results.set ("Windows Work Mode → Work wallpaper", "Windows Work Mode");
            results.set ("Windows Work Mode → Work Network", "Windows Work Mode");
            return results;
        }
    }
}

public Switchboard.Plug get_plug (Module module) {
    return new MSeriesWorkMode.Plug ();
}
