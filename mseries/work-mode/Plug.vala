/* Windows-inspired Work Mode preferences for elementary OS System Settings. */
namespace MSeriesWorkMode {
    public class Plug : Switchboard.Plug {
        private Gtk.Widget? content;
        private GLib.Settings settings;

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
                var mode_group = new Adw.PreferencesGroup () {
                    title = "Windows Work Mode",
                    description = "Use a Windows-inspired wallpaper and app dock while you work."
                };
                page.add (mode_group);

                var enabled = new Adw.SwitchRow () {
                    title = "Windows Work Mode"
                };
                settings.bind ("enabled", enabled, "active", GLib.SettingsBindFlags.DEFAULT);
                mode_group.add (enabled);

                var wallpaper = new Adw.ActionRow () {
                    title = "Work wallpaper",
                    subtitle = wallpaper_name ()
                };
                var wallpaper_options = new Gtk.StringList (null);
                wallpaper_options.append ("Blue Flow");
                wallpaper_options.append ("Blue Ribbons");
                wallpaper_options.append ("Violet Arc");
                wallpaper_options.append ("Forest Flow");
                var wallpaper_dropdown = new Gtk.DropDown (wallpaper_options, null) {
                    valign = Gtk.Align.CENTER
                };
                wallpaper_dropdown.selected = wallpaper_option_index ();
                wallpaper_dropdown.notify["selected"].connect (() => {
                    switch (wallpaper_dropdown.selected) {
                    case 0:
                        set_bundled_wallpaper ("work-mode-blue-flow.png", wallpaper);
                        break;
                    case 1:
                        set_bundled_wallpaper ("work-mode-blue-ribbons.png", wallpaper);
                        break;
                    case 2:
                        set_bundled_wallpaper ("work-mode-violet-arc.png", wallpaper);
                        break;
                    case 3:
                        set_bundled_wallpaper ("work-mode-forest-flow.png", wallpaper);
                        break;
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
                    description = "Automatically activate the work wallpaper and dock during your work hours."
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

                var start = new Adw.EntryRow () {
                    title = "Start time (24-hour)"
                };
                settings.bind ("start-time", start, "text", GLib.SettingsBindFlags.DEFAULT);
                schedule_group.add (start);

                var end = new Adw.EntryRow () {
                    title = "End time (24-hour)"
                };
                settings.bind ("end-time", end, "text", GLib.SettingsBindFlags.DEFAULT);
                schedule_group.add (end);

                var status_group = new Adw.PreferencesGroup () {
                    title = "Status"
                };
                page.add (status_group);
                var status = new Adw.ActionRow () {
                    title = "Windows-style bottom dock",
                    subtitle = "Uses your existing pinned apps and running windows."
                };
                status_group.add (status);

                // A change takes effect immediately; the user timer keeps the schedule in sync.
                settings.changed.connect (() => {
                    try {
                        GLib.Process.spawn_command_line_async ("mseries-work-mode --tick");
                    } catch (GLib.Error error) {
                        warning ("Could not apply Windows Work Mode immediately: %s", error.message);
                    }
                });
                content = page;
            }
            return content;
        }

        private string wallpaper_name () {
            var path = settings.get_string ("work-wallpaper");
            if (path == "") {
                return "No image selected";
            }
            switch (GLib.Path.get_basename (path)) {
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
            case "work-mode-blue-flow.png": return 0;
            case "work-mode-blue-ribbons.png": return 1;
            case "work-mode-violet-arc.png": return 2;
            case "work-mode-forest-flow.png": return 3;
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

        public override void shown () {}
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
            return results;
        }
    }
}

public Switchboard.Plug get_plug (Module module) {
    return new MSeriesWorkMode.Plug ();
}
