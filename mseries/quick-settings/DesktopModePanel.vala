/* Desktop mode row for the Quick Settings popover (top-right menu): one tap switches the whole
 * desktop between native elementary and Windows Work Mode. It only flips the Work Mode `enabled`
 * key and asks the Work Mode helper to apply it (the same path as the Settings page and
 * `mseries-desktop-mode`), so nothing is closed and nobody is logged out. The row hides itself when
 * Work Mode is not installed. */
using Gtk;

namespace MSeries {
    public class DesktopModePanel : Gtk.Box {
        private const string SCHEMA = "io.elementary.mseries.work-mode";
        private GLib.Settings? settings = null;
        private Gtk.ToggleButton elementary_button;
        private Gtk.ToggleButton windows_button;
        private Gtk.Label caption;
        private bool updating = false;

        construct {
            var source = GLib.SettingsSchemaSource.get_default ();
            if (source == null || source.lookup (SCHEMA, true) == null) {
                visible = false;
                return;
            }
            settings = new GLib.Settings (SCHEMA);
            orientation = Gtk.Orientation.HORIZONTAL;
            spacing = 6;
            margin_start = 12;
            margin_end = 12;
            add_css_class ("mseries-desktop-mode");

            append (new Gtk.Image.from_icon_name ("video-display-symbolic") { pixel_size = 16 });
            var text = new Gtk.Box (Gtk.Orientation.VERTICAL, 0) { hexpand = true };
            text.append (new Gtk.Label ("Desktop mode") { halign = Gtk.Align.START, xalign = 0 });
            caption = new Gtk.Label ("") { halign = Gtk.Align.START, xalign = 0, ellipsize = Pango.EllipsizeMode.END };
            caption.add_css_class (Granite.CssClass.DIM);
            caption.add_css_class ("caption");
            text.append (caption);
            append (text);

            elementary_button = new Gtk.ToggleButton.with_label ("elementary") { valign = Gtk.Align.CENTER };
            windows_button = new Gtk.ToggleButton.with_label ("Windows 11") { valign = Gtk.Align.CENTER, group = elementary_button };
            elementary_button.update_property (Gtk.AccessibleProperty.LABEL, "Switch to native elementary mode", -1);
            windows_button.update_property (Gtk.AccessibleProperty.LABEL, "Switch to Windows 11 mode", -1);
            var segmented = new Gtk.Box (Gtk.Orientation.HORIZONTAL, 0) { valign = Gtk.Align.CENTER };
            segmented.add_css_class ("linked");
            segmented.append (elementary_button);
            segmented.append (windows_button);
            append (segmented);

            windows_button.toggled.connect (() => {
                if (updating) return;
                settings.set_boolean ("enabled", windows_button.active);
                apply.begin ();
            });
            settings.changed["enabled"].connect (show_state);
            show_state ();
        }

        private void show_state () {
            updating = true;
            var on = settings.get_boolean ("enabled");
            windows_button.active = on;
            elementary_button.active = !on;
            caption.label = on ? "Windows 11" : "Native elementary";
            updating = false;
        }

        private async void apply () {
            var helper = GLib.Path.build_filename (GLib.Environment.get_home_dir (), ".local", "bin", "mseries-work-mode");
            try {
                var process = new GLib.Subprocess (GLib.SubprocessFlags.STDOUT_SILENCE | GLib.SubprocessFlags.STDERR_SILENCE, helper, "--tick");
                yield process.wait_async ();
            } catch (Error e) {
                warning ("could not apply desktop mode: %s", e.message);
            }
        }
    }
}
