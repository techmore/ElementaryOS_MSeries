/* Headless: shows the eyes indicator widget with a live state, snapshots it to a PNG, and prints visibility/tooltip. */
int main (string[] args) {
    Gtk.init ();
    var ind = new MSeries.ShareEyesIndicator ();
    print ("visible-before=%s\n", ind.visible.to_string ());
    var w = new Gtk.Window ();
    var box = new Gtk.Box (Gtk.Orientation.HORIZONTAL, 0) { margin_start = 20, margin_end = 20, margin_top = 10, margin_bottom = 10 };
    box.append (ind.get_display_widget ());
    w.child = box;
    w.present ();
    var loop = new MainLoop ();
    GLib.Timeout.add (3500, () => {
        print ("visible-after=%s tooltip=%s\n", ind.visible.to_string (), ind.get_display_widget ().get_tooltip_text ());
        var paintable = new Gtk.WidgetPaintable (box);
        var snap = new Gtk.Snapshot ();
        paintable.snapshot (snap, w.get_width (), w.get_height ());
        var node = snap.free_to_node ();
        var r = w.get_native ().get_renderer ();
        var tex = r.render_texture (node, null);
        tex.save_to_png (args[1]);
        loop.quit ();
        return false;
    });
    loop.run ();
    return 0;
}
