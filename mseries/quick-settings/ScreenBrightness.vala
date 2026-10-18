/* SPDX-License-Identifier: GPL-3.0-or-later
 * Screen brightness for the Apple panel. The slider follows the same perceptual curve as the
 * mseries-brightness keys (nits = 2 + (max - 2) * level^2.2, 2 nits being the panel's hardware
 * floor) and writes through logind, which has no floor. Mutter's SetBacklight stops at 1% of
 * the range (5 nits) and is only the fallback. */
public class QuickSettings.ScreenBrightness : Gtk.Box {
    private const double FLOOR = 2.0;
    private const double GAMMA = 2.2;
    private const string BACKLIGHT = "/sys/class/backlight/apple-panel-bl";
    private DBusProxy? display;
    private DBusProxy? logind;
    private Gtk.Scale slider;
    private Gtk.Label percentage;
    private bool updating = false;
    private bool writing = false;
    private uint timeout_id = 0;
    private double requested = 0;

    class construct {
        set_css_name ("scalebox");
    }

    construct {
        orientation = HORIZONTAL;
        spacing = 6;
        visible = false;
        var icon = new Gtk.Image.from_icon_name ("display-brightness-symbolic") {
            tooltip_text = _("Screen Brightness")
        };
        slider = new Gtk.Scale.with_range (HORIZONTAL, 0, 100, 1) {
            hexpand = true,
            draw_value = false,
            tooltip_text = _("Screen Brightness")
        };
        slider.update_property_value ({ Gtk.AccessibleProperty.LABEL }, { _("Screen Brightness") });
        percentage = new Gtk.Label ("") { width_chars = 4, xalign = 1 };
        percentage.add_css_class ("dim-label");
        append (icon);
        append (slider);
        append (percentage);
        slider.value_changed.connect (() => {
            percentage.label = "%.0f%%".printf (slider.get_value ());
            if (updating) return;
            requested = slider.get_value ();
            if (timeout_id != 0) Source.remove (timeout_id);
            timeout_id = Timeout.add (100, () => {
                timeout_id = 0;
                if (!writing) write_brightness.begin ();
                return Source.REMOVE;
            });
        });
        destroy.connect (() => {
            if (timeout_id != 0) Source.remove (timeout_id);
        });
        connect_display.begin ();
    }

    private async void connect_display () {
        try {
            display = yield new DBusProxy.for_bus (BusType.SESSION, DBusProxyFlags.NONE, null,
                "org.gnome.Mutter.DisplayConfig", "/org/gnome/Mutter/DisplayConfig",
                "org.gnome.Mutter.DisplayConfig");
            // Mutter notices backlight changes made through logind and reports them here.
            display.g_properties_changed.connect (() => { refresh (); });
        } catch (Error e) {
            warning ("Mutter backlight fallback unavailable: %s", e.message);
        }
        try {
            logind = yield new DBusProxy.for_bus (BusType.SYSTEM, DBusProxyFlags.NONE, null,
                "org.freedesktop.login1", "/org/freedesktop/login1/session/auto",
                "org.freedesktop.login1.Session");
        } catch (Error e) {
            warning ("logind backlight unavailable: %s", e.message);
        }
        refresh ();
    }

    private bool read_nits (string name, out int value) {
        value = 0;
        try {
            string contents;
            FileUtils.get_contents (Path.build_filename (BACKLIGHT, name), out contents);
            value = int.parse (contents.strip ());
            return true;
        } catch (FileError e) {
            return false;
        }
    }

    private static double level_to_nits (double level, int maximum) {
        return FLOOR + (maximum - FLOOR) * Math.pow (level.clamp (0.0, 1.0), GAMMA);
    }

    private static double nits_to_level (int nits, int maximum) {
        double span = maximum - FLOOR;
        return Math.pow (((double) nits - FLOOR).clamp (0.0, span) / span, 1.0 / GAMMA);
    }

    private void refresh () {
        int current, maximum;
        bool available = read_nits ("max_brightness", out maximum) &&
            read_nits ("brightness", out current) && maximum > (int) FLOOR;
        visible = available && (logind != null || display != null);
        if (!visible || writing || timeout_id != 0) return;
        updating = true;
        read_nits ("brightness", out current);
        slider.set_value (100.0 * nits_to_level (current, maximum));
        updating = false;
    }

    // The slider's lowest position is the 2-nit hardware floor; clear any software dim layer
    // the brightness keys set below it (the patched Gala re-reads the file).
    private void clear_software_dim () {
        var path = Path.build_filename (Environment.get_user_runtime_dir (), "mseries-dim");
        if (!FileUtils.test (path, FileTest.EXISTS)) return;
        try {
            FileUtils.set_contents (path, "0\n");
        } catch (FileError e) {
            warning ("Could not clear the software dim layer: %s", e.message);
        }
    }

    private async void write_via_mutter (int nits) throws Error {
        // Fallback only: Mutter refuses anything below its 1% minimum.
        var reply = yield display.get_connection ().call (display.g_name,
            display.g_object_path, "org.freedesktop.DBus.Properties", "Get",
            new Variant ("(ss)", display.g_interface_name, "Backlight"),
            new VariantType ("(v)"), DBusCallFlags.NONE, 3000);
        var value = reply.get_child_value (0).get_variant ();
        var serial = value.get_child_value (0).get_uint32 ();
        var panels = value.get_child_value (1);
        for (size_t i = 0; i < panels.n_children (); i++) {
            var panel = panels.get_child_value (i);
            string name;
            int minimum = 0, maximum = 0;
            if (panel.lookup ("connector", "s", out name) && name.has_prefix ("eDP-") &&
                panel.lookup ("min", "i", out minimum) && panel.lookup ("max", "i", out maximum)) {
                int level = nits.clamp (minimum, maximum);
                yield display.call ("SetBacklight", new Variant ("(usi)", serial, name, level),
                    DBusCallFlags.NONE, 3000);
                return;
            }
        }
    }

    private async void write_brightness () {
        writing = true;
        double target = requested;
        do {
            target = requested;
            int maximum;
            if (!read_nits ("max_brightness", out maximum)) break;
            int nits = (int) Math.round (level_to_nits (target / 100.0, maximum));
            nits = nits.clamp ((int) FLOOR, maximum);
            try {
                if (logind != null) {
                    yield logind.call ("SetBrightness", new Variant ("(ssu)", "backlight", "apple-panel-bl", (uint32) nits),
                        DBusCallFlags.NONE, 3000);
                } else if (display != null) {
                    yield write_via_mutter (nits);
                }
            } catch (Error e) {
                warning ("Could not set screen brightness through logind (%s); trying Mutter", e.message);
                try {
                    if (display != null) yield write_via_mutter (nits);
                } catch (Error e2) {
                    warning ("Could not set screen brightness: %s", e2.message);
                    break;
                }
            }
            clear_software_dim ();
        } while (target != requested);
        writing = false;
        refresh ();
    }
}
