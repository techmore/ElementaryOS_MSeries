/* Headless: shows the indicator (panel widget + popover content) and snapshots both to PNGs. args: out-prefix [create-link] */
int main (string[] args) {
    Gtk.init ();
    var ind = new MSeries.ShareEyesIndicator ();
    var w = new Gtk.Window ();
    var box = new Gtk.Box (Gtk.Orientation.VERTICAL, 12) { margin_start = 20, margin_end = 20, margin_top = 10, margin_bottom = 10 };
    box.append (ind.get_display_widget ());
    box.append (ind.get_widget ());
    w.child = box;
    w.present ();
    ind.opened ();
    var loop = new MainLoop ();
    GLib.Timeout.add (4500, () => {
        print ("visible=%s tooltip=%s\n", ind.visible.to_string (), ind.get_display_widget ().get_tooltip_text ());
        var paintable = new Gtk.WidgetPaintable (box);
        var snap = new Gtk.Snapshot ();
        paintable.snapshot (snap, w.get_width (), w.get_height ());
        var tex = w.get_native ().get_renderer ().render_texture (snap.free_to_node (), null);
        tex.save_to_png (args[1]);
        loop.quit ();
        return false;
    });
    loop.run ();
    return 0;
}
