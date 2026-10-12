/* SPDX-License-Identifier: GPL-3.0-or-later
 * Screen brightness for Pantheon's Mutter backlight API. */
public class QuickSettings.ScreenBrightness : Gtk.Box {
    private DBusProxy? display;
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
            display.g_properties_changed.connect (() => { refresh (); });
            display.notify["g-name-owner"].connect (() => { refresh (); });
            refresh ();
        } catch (Error e) {
            warning ("Screen brightness unavailable: %s", e.message);
        }
    }

    private bool read_panel (Variant backlight, out uint serial, out string connector,
                            out int minimum, out int maximum, out int current) {
        serial = backlight.get_child_value (0).get_uint32 ();
        connector = "";
        minimum = maximum = current = 0;
        var panels = backlight.get_child_value (1);
        for (size_t i = 0; i < panels.n_children (); i++) {
            var panel = panels.get_child_value (i);
            string name;
            bool active = false;
            if (panel.lookup ("connector", "s", out name) && name.has_prefix ("eDP-") &&
                panel.lookup ("active", "b", out active) && active &&
                panel.lookup ("min", "i", out minimum) &&
                panel.lookup ("max", "i", out maximum) && maximum > minimum &&
                panel.lookup ("value", "i", out current)) {
                connector = name;
                return true;
            }
        }
        return false;
    }

    private void refresh () {
        var value = display.get_cached_property ("Backlight");
        uint serial;
        string connector;
        int minimum = 0, maximum = 0, current = 0;
        visible = display.g_name_owner != null && value != null &&
            read_panel (value, out serial, out connector, out minimum, out maximum, out current);
        if (!visible || writing || timeout_id != 0) return;
        updating = true;
        slider.set_value (100.0 * (current - minimum) / (maximum - minimum));
        updating = false;
    }

    private async void write_brightness () {
        writing = true;
        double target = requested;
        do {
            target = requested;
            try {
                // Read a fresh serial for each write; other brightness controls may run too.
                var reply = yield display.get_connection ().call (display.g_name,
                    display.g_object_path, "org.freedesktop.DBus.Properties", "Get",
                    new Variant ("(ss)", display.g_interface_name, "Backlight"),
                    new VariantType ("(v)"), DBusCallFlags.NONE, 3000);
                var value = reply.get_child_value (0).get_variant ();
                uint serial;
                string connector;
                int minimum = 0, maximum = 0, current = 0;
                if (read_panel (value, out serial, out connector, out minimum, out maximum, out current)) {
                    int level = minimum + (int) Math.round (target * (maximum - minimum) / 100.0);
                    yield display.call ("SetBacklight", new Variant ("(usi)", serial, connector, level),
                        DBusCallFlags.NONE, 3000);
                }
            } catch (Error e) {
                warning ("Could not set screen brightness: %s", e.message);
                break;
            }
        } while (target != requested);
        writing = false;
        refresh ();
    }
}
