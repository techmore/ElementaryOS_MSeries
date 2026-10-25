/* SPDX-License-Identifier: GPL-3.0-or-later
 * Manual keyboard lighting through UPower's supported backlight interface. */
public class QuickSettings.KeyboardBrightness : QuickSettings.SliderRow {
    private DBusProxy? keyboard;
    private int maximum = 0;

    public KeyboardBrightness () {
        Object (title: _("Keyboard Brightness"));
    }

    construct {
        visible = false;
        connect_keyboard.begin ();
    }

    protected override string icon_for (double value, bool dimmed) {
        return "keyboard-brightness-symbolic";
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
        if (busy) return;
        try {
            var max_reply = yield keyboard.call ("GetMaxBrightness", null, DBusCallFlags.NONE, 2000);
            maximum = max_reply.get_child_value (0).get_int32 ();
            if (maximum <= 0) { visible = false; return; }
            var reply = yield keyboard.call ("GetBrightness", null, DBusCallFlags.NONE, 2000);
            // A drag may have begun while these reads were in flight.
            if (busy) return;
            var current = reply.get_child_value (0).get_int32 ();
            show_value (100.0 * current / maximum);
            visible = true;
        } catch (Error e) {
            visible = false;
            info ("Keyboard brightness unavailable: %s", e.message);
        }
    }

    protected override async void write (double value) throws Error {
        int level = (int) Math.round (value * maximum / 100.0);
        yield keyboard.call ("SetBrightness", new Variant ("(i)", level.clamp (0, maximum)),
            DBusCallFlags.NONE, 2000);
    }

    protected override void wrote () {
        refresh.begin ();
    }
}
