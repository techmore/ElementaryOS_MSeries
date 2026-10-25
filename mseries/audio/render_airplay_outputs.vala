// Headless render check for quick-settings/AirPlayOutputs.vala: shows the widget, optionally
// expands the row and clicks the first dot, and saves PNGs. Run via test_airplay_outputs_render.sh.
int main (string[] args) {
    Gtk.init ();
    var win = new Gtk.Window () { default_width = 320 };
    var air = new QuickSettings.AirPlayOutputs ();
    win.child = air;
    win.present ();
    var loop = new MainLoop ();
    string prefix = args[1];
    Timeout.add (700, () => {
        // expand: click header button
        var header = (Gtk.Button) air.get_first_child ();
        stdout.printf ("header visible=%s\n", header.visible.to_string ());
        header.clicked ();
        return false;
    });
    Timeout.add (1400, () => { snap (win, "%s-expanded.png".printf (prefix)); return false; });
    Timeout.add (1600, () => {
        var rev = (Gtk.Revealer) air.get_last_child ();
        var first = ((Gtk.Box) rev.child).get_first_child ().get_first_child ();
        ((Gtk.ToggleButton) first).active = true;   // same path as a click
        return false;
    });
    Timeout.add (3200, () => { snap (win, "%s-clicked.png".printf (prefix)); loop.quit (); return false; });
    loop.run ();
    return 0;
}

void snap (Gtk.Window win, string path) {
    var paintable = new Gtk.WidgetPaintable (win);
    var snapshot = new Gtk.Snapshot ();
    paintable.snapshot (snapshot, win.get_width (), win.get_height ());
    var node = snapshot.free_to_node ();
    var renderer = win.get_native ().get_renderer ();
    var tex = renderer.render_texture (node, null);
    tex.save_to_png (path);
}
