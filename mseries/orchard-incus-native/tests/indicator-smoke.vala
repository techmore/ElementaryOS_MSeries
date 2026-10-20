[CCode (has_target = false)]
delegate Wingpanel.Indicator? LoadIndicator (Module module, Wingpanel.ServerType type);

int main (string[] args) {
    Gtk.init ();
    var module = Module.open (args[1], ModuleFlags.BIND_LOCAL);
    assert (module != null);
    void* symbol;
    assert (module.symbol ("get_indicator", out symbol));
    LoadIndicator load = (LoadIndicator) symbol;
    assert (load (module, Wingpanel.ServerType.GREETER) == null);
    var indicator = load (module, Wingpanel.ServerType.SESSION);
    assert (indicator != null && indicator.visible);
    var display = (Gtk.Box) indicator.get_display_widget ();
    assert (((Gtk.Image) display.get_first_child ()).icon_name == "orchard-incus-symbolic");
    var badge = (Gtk.Label) display.get_first_child ().get_next_sibling ();
    assert (badge.get_next_sibling () == null);
    assert (badge.label == "…");

    var output = Environment.get_variable ("ORCHARD_INDICATOR_CAPTURE");
    Gtk.Window? preview = null;
    if (output != null) {
        var body = new Gtk.Box (Gtk.Orientation.VERTICAL, 0);
        body.add_css_class ("background"); body.append (indicator.get_widget ());
        preview = new Gtk.Window () { child = body, decorated = false, default_width = 340 };
        preview.present ();
    }

    // One indicator instance must recover from an error and replace stale counts.
    string[] expected = { "2", "2", "0", "0", "—", "0", "1" };
    string[] summaries = { "2 of 3", "2 of 3", "No local instances", "0 of 1", "Incus unavailable", "No local instances", "1 of 1" };
    Gtk.Widget? first_row = null;
    int stage = 0;
    var loop = new MainLoop ();
    Timeout.add (50, () => {
        if (badge.label != expected[stage]) return Source.CONTINUE;
        if (!display.tooltip_text.contains (summaries[stage])) return Source.CONTINUE;
        // A known CPU delta proves the identical second response has actually completed.
        if (stage == 1 && !display.tooltip_text.contains ("CPU 0.0% of host")) return Source.CONTINUE;
        var menu = indicator.get_widget ();
        Gtk.ScrolledWindow? scroll = null;
        for (var child = menu.get_first_child (); child != null; child = child.get_next_sibling ())
            if (child is Gtk.ScrolledWindow) scroll = (Gtk.ScrolledWindow) child;
        assert (scroll != null);
        var rows = ((Gtk.Viewport) scroll.child).child;
        if (stage == 0) first_row = rows.get_first_child ();
        if (stage == 1) assert (first_row == rows.get_first_child ());
        assert (indicator.visible);
        assert (badge.get_next_sibling () == null);
        print ("Badge stage %d: %s\n", stage, badge.label);
        if (preview != null) {
            // Leave a frame for changed labels, then capture this fixture state.
            int captured_stage = stage;
            Timeout.add (150, () => {
                var root = preview.child;
                var paintable = new Gtk.WidgetPaintable (root);
                var snapshot = new Gtk.Snapshot ();
                paintable.snapshot (snapshot, root.get_width (), root.get_height ());
                var node = snapshot.to_node (); assert (node != null);
                assert (root.get_width () <= 360);
                assert (preview.get_renderer ().render_texture (node, null).save_to_png (output + "-" + captured_stage.to_string () + ".png"));
                if (captured_stage + 1 < expected.length) indicator.opened ();
                else loop.quit ();
                return Source.REMOVE;
            });
        }
        if (++stage == expected.length) {
            if (preview == null) loop.quit ();
            return Source.REMOVE;
        }
        if (preview == null) indicator.opened ();
        return Source.CONTINUE;
    });
    Timeout.add_seconds (15, () => { error ("Timed out at badge stage %d", stage); });
    loop.run ();
    module.make_resident ();
    return 0;
}
