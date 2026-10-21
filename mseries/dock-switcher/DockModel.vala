/* SPDX-License-Identifier: GPL-3.0-or-later */
/* The dock's settings, as the page needs them. The patched M-Series dock keeps
 * its schema (with taskbar-mode) in a private directory the Settings process
 * doesn't search, so look there first, then fall back to the system schema. */
namespace MSeriesDockSwitcher {
    public class DockModel : GLib.Object {
        public const string SCHEMA_ID = "io.elementary.dock";
        public const string TASKBAR_KEY = "taskbar-mode";
        public const string AUTOHIDE_KEY = "autohide-mode";

        public bool schema_found { get; private set; default = false; }
        public bool has_taskbar_key { get; private set; default = false; }
        public bool opt_out_marker { get; private set; default = false; }

        public signal void changed ();

        private GLib.Settings? settings = null;
        private string marker_path;

        public static string default_private_dir () {
            return GLib.Path.build_filename (
                GLib.Environment.get_home_dir (), ".local", "lib", "mseries", "dock",
                "share", "glib-2.0", "schemas");
        }

        /* private_dir is searched before the system schemas (unless
         * include_system is false, which the tests use to model a machine
         * without the dock). marker_path is the opt-out file. */
        public DockModel (string? private_dir = null, bool include_system = true, string? marker = null) {
            marker_path = marker ?? GLib.Path.build_filename (
                GLib.Environment.get_user_config_dir (), "mseries", "dock", "user-disabled");

            GLib.SettingsSchemaSource? source = include_system ? GLib.SettingsSchemaSource.get_default () : null;
            var dir = private_dir ?? Environment.get_variable ("MSERIES_DOCK_SCHEMA_DIR") ?? default_private_dir ();
            if (GLib.FileUtils.test (GLib.Path.build_filename (dir, "gschemas.compiled"), GLib.FileTest.IS_REGULAR)) {
                try {
                    source = new GLib.SettingsSchemaSource.from_directory (dir, source, false);
                } catch (GLib.Error error) {
                    warning ("Dock schema directory %s is unusable: %s", dir, error.message);
                }
            }

            /* Settings.new aborts on an unknown schema, so look it up first. */
            var schema = source != null ? source.lookup (SCHEMA_ID, true) : null;
            if (schema != null) {
                schema_found = true;
                has_taskbar_key = schema.has_key (TASKBAR_KEY) && schema.has_key (AUTOHIDE_KEY);
                settings = new GLib.Settings.full (schema, null, null);
                settings.changed.connect ((key) => {
                    if (key == TASKBAR_KEY || key == AUTOHIDE_KEY) {
                        changed ();
                    }
                });
            }
            refresh_marker ();
        }

        public void refresh_marker () {
            opt_out_marker = GLib.FileUtils.test (marker_path, GLib.FileTest.EXISTS);
        }

        public Availability availability () {
            return MSeriesDockSwitcher.availability (schema_found, has_taskbar_key, opt_out_marker);
        }

        public Style style {
            get {
                if (settings != null && has_taskbar_key && settings.get_boolean (TASKBAR_KEY)) {
                    return Style.TASKBAR;
                }
                return Style.DOCK;
            }
        }

        public string autohide {
            owned get {
                return settings != null ? settings.get_string (AUTOHIDE_KEY) : "never";
            }
        }

        /* Write the style and read it back. The dock applies the change live;
         * returning the verified value lets the page say so only when it's true. */
        public bool set_style (Style value) {
            if (settings == null || !has_taskbar_key) {
                return false;
            }
            settings.set_boolean (TASKBAR_KEY, value == Style.TASKBAR);
            GLib.Settings.sync ();
            return style == value;
        }

        public bool set_autohide (string nick) {
            if (settings == null || !has_taskbar_key || autohide_index (nick) < 0) {
                return false;
            }
            settings.set_string (AUTOHIDE_KEY, nick);
            GLib.Settings.sync ();
            return autohide == nick;
        }
    }
}
