/* Exercises the production widget against the private BlueZ fixture. */
Gtk.Button? device_button (Gtk.Box list, string name) {
    for (var row = list.get_first_child (); row != null; row = row.get_next_sibling ()) {
        var label = row.get_first_child ().get_next_sibling () as Gtk.Label;
        if (label != null && label.label == name) return row.get_last_child () as Gtk.Button;
    }
    return null;
}

int main () {
    Gtk.init ();
    var widget = new QuickSettings.Bluetooth ();
    var toggle = (Granite.SwitchModelButton) widget.get_first_child ();
    var devices = (Gtk.Box) toggle.get_next_sibling ();
    var status = (Gtk.Label) devices.get_next_sibling ();
    var window = new Gtk.Window () { child = widget, default_width = 360 };
    window.present ();
    var loop = new MainLoop ();
    int stage = 0, ticks = 0;
    Timeout.add (100, () => {
        if (++ticks >= 100) error ("Timed out at stage %d; toggle %s / %s", stage, toggle.active.to_string (), status.label);
        var keyboard = device_button (devices, "Test keyboard");
        if (stage == 0 && toggle.sensitive) {
            assert (toggle.active);
            assert (keyboard != null);
            assert (device_button (devices, "Stranger") == null);
            keyboard.clicked ();
            stage++;
        } else if (stage == 1 && keyboard != null && keyboard.label == "Disconnect") {
            keyboard.clicked ();
            stage++;
        } else if (stage == 2 && keyboard != null && keyboard.label == "Connect") {
            device_button (devices, "Offline headset").clicked ();
            stage++;
        } else if (stage == 3 && status.visible) {
            assert (status.label.contains ("Offline headset"));
            assert (device_button (devices, "Offline headset").sensitive);
            toggle.active = false;
            stage++;
        } else if (stage == 4 && toggle.sensitive && !toggle.active) {
            assert (!devices.visible);
            toggle.active = true;
            stage++;
        } else if (stage == 5 && toggle.sensitive && toggle.active) {
            assert (devices.visible);
            assert (device_button (devices, "Test keyboard") != null);
            print ("PASS: saved devices only; connect/disconnect; error recovery; power off/on\n");
            window.destroy ();
            loop.quit ();
            return Source.REMOVE;
        }
        return Source.CONTINUE;
    });
    loop.run ();
    return 0;
}
