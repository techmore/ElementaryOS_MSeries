/* Headless: shows the indicator (panel widget + popover content) and snapshots both to PNGs. args: out-prefix [create-link] */
int main (string[] args) {
    Gtk.init ();
    Granite.init ();
    var ind = new MSeries.SharePanel () { notify_waiting = GLib.Environment.get_variable ("SHARE_NOTIFY") == "1", always_visible = true };
    var w = new Gtk.Window () { default_width = int.parse (GLib.Environment.get_variable ("PROBE_W") ?? "0") };
    var box = new Gtk.Box (Gtk.Orientation.VERTICAL, 12) { margin_start = 20, margin_end = 20, margin_top = 10, margin_bottom = 10 };
    
    box.append (ind);
    w.child = box;
    w.present ();
    var loop = new MainLoop ();
    GLib.Timeout.add (int.parse (GLib.Environment.get_variable ("PROBE_MS") ?? "4500"), () => {
        print ("visible=%s\n", ind.visible.to_string ());
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
