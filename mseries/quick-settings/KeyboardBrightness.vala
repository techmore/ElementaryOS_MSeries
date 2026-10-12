/* SPDX-License-Identifier: GPL-3.0-or-later
 * Manual keyboard lighting through UPower's supported backlight interface. */
public class QuickSettings.KeyboardBrightness : Gtk.Box {
    private DBusProxy? keyboard;
    private Gtk.Scale slider;
    private Gtk.Label percentage;
    private int maximum = 0;
    private bool updating = false;
    private bool writing = false;
    private uint timeout_id = 0;
    private double requested = 0;

    class construct {
        set_css_name ("scalebox");
    }

    construct {
        orientation = VERTICAL;
        spacing = 0;
        visible = false;
        var label = new Gtk.Label (_("Keyboard Brightness")) { xalign = 0 };
        label.add_css_class ("dim-label");
        var row = new Gtk.Box (HORIZONTAL, 6);
        var icon = new Gtk.Image.from_icon_name ("input-keyboard-symbolic");
        slider = new Gtk.Scale.with_range (HORIZONTAL, 0, 100, 1) {
            hexpand = true,
            draw_value = false,
            tooltip_text = _("Keyboard Brightness")
        };
        slider.update_property_value ({ Gtk.AccessibleProperty.LABEL }, { _("Keyboard Brightness") });
        percentage = new Gtk.Label ("0%") { width_chars = 4, xalign = 1 };
        percentage.add_css_class ("dim-label");
        row.append (icon);
        row.append (slider);
        row.append (percentage);
        append (label);
        append (row);
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
        connect_keyboard.begin ();
    }

    private async void connect_keyboard () {
        try {
            keyboard = yield new DBusProxy.for_bus (BusType.SYSTEM, DBusProxyFlags.NONE, null,
                "org.freedesktop.UPower", "/org/freedesktop/UPower/KbdBacklight",
                "org.freedesktop.UPower.KbdBacklight");
            keyboard.g_signal.connect ((sender, name, parameters) => {
                if (name == "BrightnessChanged") refresh.begin ();
            });
            keyboard.notify["g-name-owner"].connect (() => { refresh.begin (); });
            yield refresh ();
        } catch (Error e) {
            info ("Keyboard brightness unavailable: %s", e.message);
        }
    }

    private async void refresh () {
        if (writing || timeout_id != 0) return;
        try {
            var max_reply = yield keyboard.call ("GetMaxBrightness", null, DBusCallFlags.NONE, 2000);
            maximum = max_reply.get_child_value (0).get_int32 ();
            if (maximum <= 0) { visible = false; return; }
            var reply = yield keyboard.call ("GetBrightness", null, DBusCallFlags.NONE, 2000);
            // A drag may have begun while these reads were in flight.
            if (writing || timeout_id != 0) return;
            var current = reply.get_child_value (0).get_int32 ();
            updating = true;
            slider.set_value (100.0 * current / maximum);
            percentage.label = "%.0f%%".printf (slider.get_value ());
            updating = false;
            visible = true;
        } catch (Error e) {
            visible = false;
            info ("Keyboard brightness unavailable: %s", e.message);
        }
    }

    private async void write_brightness () {
        writing = true;
        double target = requested;
        do {
            target = requested;
            try {
                int level = (int) Math.round (target * maximum / 100.0);
                yield keyboard.call ("SetBrightness", new Variant ("(i)", level.clamp (0, maximum)),
                    DBusCallFlags.NONE, 2000);
            } catch (Error e) {
                warning ("Could not set keyboard brightness: %s", e.message);
                break;
            }
        } while (target != requested);
        writing = false;
        yield refresh ();
    }
}
