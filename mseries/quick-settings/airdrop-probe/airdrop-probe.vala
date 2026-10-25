/* Headless: drives AirDropPanel against the stub backend and prints what it shows. args: out-prefix */
int main (string[] args) {
    Gtk.init ();
    Granite.init ();
    var panel = new MSeries.AirDropPanel ();
    var w = new Gtk.Window ();
    var box = new Gtk.Box (Gtk.Orientation.VERTICAL, 0) { margin_start = 20, margin_end = 20, margin_top = 10, margin_bottom = 10, width_request = 300 };
    box.append (panel);
    w.child = box;
    w.present ();
    var loop = new MainLoop ();
    var out_prefix = args[1];
    var scenario = GLib.Environment.get_variable ("PROBE_SCENARIO") ?? "normal";
    void shot (string name) {
        var paintable = new Gtk.WidgetPaintable (box);
        var snap = new Gtk.Snapshot ();
        paintable.snapshot (snap, w.get_width (), w.get_height ());
        var tex = w.get_native ().get_renderer ().render_texture (snap.free_to_node (), null);
        tex.save_to_png (out_prefix + "-" + name + ".png");
    }
    // map starts the first poll; give it time, then walk through the states.
    GLib.Timeout.add (1500, () => {
        print ("collapsed-initial expanded=%s status=%s\n", panel.expanded.to_string (), panel.status_text);
        shot ("collapsed");
        panel.set_expanded (true);
        return false;
    });
    GLib.Timeout.add (2200, () => {
        print ("expanded status=%s problem=%s\n", panel.status_text, panel.problem_text);
        shot ("expanded");
        if (scenario == "normal") panel.receive_switch.active = true;
        return false;
    });
    GLib.Timeout.add (4500, () => {
        print ("after-on switch=%s status=%s problem=%s\n", panel.receive_switch.active.to_string (), panel.status_text, panel.problem_text);
        shot ("on");
        if (scenario == "normal") panel.receive_switch.active = false;
        return false;
    });
    GLib.Timeout.add (6800, () => {
        print ("after-off switch=%s status=%s\n", panel.receive_switch.active.to_string (), panel.status_text);
        loop.quit ();
        return false;
    });
    loop.run ();
    return 0;
}
