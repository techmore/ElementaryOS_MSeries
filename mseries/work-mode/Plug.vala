/* M-series Work Mode preferences for elementary OS System Settings. */
namespace MSeriesWorkMode {
    public class Plug : Switchboard.Plug {
        private Gtk.Widget? content;
        private GLib.Settings settings;

        public Plug () {
            settings = new GLib.Settings ("io.elementary.mseries.work-mode");
            var supported = new Gee.TreeMap<string, string?> (null, null);
            supported.set ("personal/work-mode", "Work Mode");
            Object (
                category: Category.PERSONAL,
                code_name: "io.elementary.settings.work-mode",
                display_name: "Work Mode",
                description: "Set a work wallpaper and schedule work hours",
                icon: "preferences-desktop-wallpaper",
                supported_settings: supported
            );
        }

        public override Gtk.Widget get_widget () {
            if (content == null) {
                var page = new Adw.PreferencesPage ();
                var mode_group = new Adw.PreferencesGroup () {
                    title = "Work Mode",
                    description = "Use a dedicated wallpaper while you work."
                };
                page.add (mode_group);

                var enabled = new Adw.SwitchRow () {
                    title = "Work Mode"
                };
                settings.bind ("enabled", enabled, "active", GLib.SettingsBindFlags.DEFAULT);
                mode_group.add (enabled);

                var wallpaper = new Adw.ActionRow () {
                    title = "Work wallpaper",
                    subtitle = wallpaper_name ()
                };
                var choose = new Gtk.Button.with_label ("Choose…") {
                    valign = Gtk.Align.CENTER
                };
                choose.clicked.connect (() => choose_wallpaper (wallpaper));
                wallpaper.add_suffix (choose);
                wallpaper.activatable_widget = choose;
                mode_group.add (wallpaper);

                var schedule_group = new Adw.PreferencesGroup () {
                    title = "Schedule",
                    description = "Automatically switch wallpapers during your work hours."
                };
                page.add (schedule_group);

                var scheduled = new Adw.SwitchRow () {
                    title = "Schedule Work Mode"
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
                    title = "Schedule checked every minute"
                };
                status_group.add (status);

                // A change takes effect immediately; the user timer keeps the schedule in sync.
                settings.changed.connect (() => {
                    try {
                        GLib.Process.spawn_command_line_async ("mseries-work-mode --tick");
                    } catch (GLib.Error error) {
                        warning ("Could not apply Work Mode immediately: %s", error.message);
                    }
                });
                content = page;
            }
            return content;
        }

        private string wallpaper_name () {
            var path = settings.get_string ("work-wallpaper");
            return path == "" ? "No image selected" : GLib.Path.get_basename (path);
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
            results.set ("Work Mode", "Work Mode");
            results.set ("Work Mode → Schedule Work Mode", "Work Mode");
            results.set ("Work Mode → Work wallpaper", "Work Mode");
            return results;
        }
    }
}

public Switchboard.Plug get_plug (Module module) {
    return new MSeriesWorkMode.Plug ();
}
