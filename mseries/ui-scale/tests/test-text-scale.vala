/* Drives the Quick Settings TextScale widget against in-memory GSettings. */
int failures = 0;

void expect (bool condition, string message) {
    if (!condition) {
        stderr.printf ("FAIL: %s\n", message);
        failures++;
    }
}

void settle (int ms = 500) {
    var loop = new MainLoop ();
    Timeout.add (ms, () => { loop.quit (); return Source.REMOVE; });
    loop.run ();
}

int main (string[] args) {
    Gtk.init ();
    Granite.init ();
    var settings = new Settings ("org.gnome.desktop.interface");
    settings.set_double ("text-scaling-factor", 0.85108303249097472);

    var widget = new QuickSettings.TextScale ();
    var window = new Gtk.Window () { child = widget };
    window.present ();
    settle (100);

    var zoom_out = (Gtk.Button) widget.get_first_child ();
    var scale = (Gtk.Scale) zoom_out.get_next_sibling ();
    var zoom_in = (Gtk.Button) widget.get_last_child ();

    expect (scale.adjustment.value == 0, "0.851 shows Compact");
    expect (zoom_out.sensitive, "off-ladder 0.851 can still step down to Compact");
    expect (settings.get_double ("text-scaling-factor") > 0.851, "opening the widget does not rewrite the value");

    zoom_out.clicked ();
    settle ();
    expect (settings.get_double ("text-scaling-factor") == 0.85, "down from 0.851 snaps to 0.85");
    expect (!zoom_out.sensitive, "Compact disables decrease");

    double[] expected = { 0.92, 1.0, 1.1, 1.25, 1.5 };
    foreach (var value in expected) {
        zoom_in.clicked ();
        settle ();
        expect (settings.get_double ("text-scaling-factor") == value, "increase lands on %g".printf (value));
    }
    expect (!zoom_in.sensitive, "Largest disables increase");

    // Rapid presses coalesce into one write of the final step.
    zoom_out.clicked ();
    zoom_out.clicked ();
    zoom_out.clicked ();
    settle ();
    expect (settings.get_double ("text-scaling-factor") == 1.0, "three quick decreases land on Default");

    // Dragging/keyboard sets fractional positions; they snap to whole steps.
    scale.adjustment.value = 2.6;
    settle ();
    expect (scale.adjustment.value == 3, "slider snaps to a whole step");
    expect (settings.get_double ("text-scaling-factor") == 1.1, "slider writes the snapped step");

    // An external change is mirrored without being written back.
    settings.set_double ("text-scaling-factor", 1.3);
    settle ();
    expect (scale.adjustment.value == 4, "external 1.3 shows Larger");
    expect (settings.get_double ("text-scaling-factor") == 1.3, "external value is not rewritten by the widget");
    expect (scale.tooltip_text.contains ("Larger"), "tooltip names the step");

    if (failures == 0) {
        print ("text-scale: all checks passed\n");
    }
    return failures == 0 ? 0 : 1;
}
