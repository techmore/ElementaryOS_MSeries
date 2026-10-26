/*
 * Headless probe: builds the indicator from a status.json fixture at a fixed time, checks the texts it
 * shows, and writes a PNG of the popover and the panel widget when PROBE_SHOT is set. Run under Xvfb:
 *
 *   xvfb-run -a env PROBE_SHOT=docs/screenshot-indicator.png build/probe probe/status-fixture.json
 */

static void collect (Gtk.Widget w, Gee.ArrayList<string> acc) {
    if (w is Gtk.Label) acc.add (((Gtk.Label) w).label);
    Gtk.Widget? c = w.get_first_child ();
    while (c != null) {
        collect (c, acc);
        c = c.get_next_sibling ();
    }
}

static void pump (int ms) {
    var until = get_monotonic_time () + ms * 1000;
    while (get_monotonic_time () < until) {
        while (MainContext.default ().iteration (false)) { }
        Thread.usleep (5000);
    }
}

int main (string[] args) {
    Gtk.init ();
    Granite.init ();
    var fixture = args.length > 1 ? args[1] : "probe/status-fixture.json";
    var metadata = new KeyFile ();
    try {
        metadata.load_from_file (Path.build_filename (Path.get_dirname (fixture), "..", "..", "data",
            "io.github.techmore.ClaudePantheonRs.desktop"), KeyFileFlags.NONE);
    } catch (Error e) {
        stderr.printf ("Cannot load native desktop metadata: %s\n", e.message);
        return 1;
    }
    var indicator = new ClaudePantheon.Indicator (fixture, new GLib.DesktopAppInfo.from_keyfile (metadata));
    var panel = indicator.get_display_widget ();
    var popover = indicator.get_widget ();
    // The panel and Dock compile the same complete provider/account renderer.

    var texts = new Gee.ArrayList<string> ();
    collect (popover, texts);
    collect (panel, texts);
    string[] expect = { "claude · 111 tokens", "grok · 222 tokens", "opencode · 333 tokens", "Claude Work", "Grok Work", "OpenCode Work", "2" };
    foreach (var e in expect) {
        bool found = false;
        foreach (var t in texts) if (t.contains (e)) found = true;
        if (!found) {
            stderr.printf ("FAIL: expected '%s' in %s\n", e, string.joinv (" | ", texts.to_array ()));
            return 1;
        }
    }
    var shot = Environment.get_variable ("PROBE_SHOT");
    if (shot != null) {
        var window = new Gtk.Window () { default_width = 360, default_height = 320 };
        var column = new Gtk.Box (Gtk.Orientation.VERTICAL, 12);
        var panel_row = new Gtk.Box (Gtk.Orientation.HORIZONTAL, 0) { halign = Gtk.Align.END, margin_end = 12, margin_top = 6 };
        panel_row.append (panel);
        column.append (panel_row);
        column.append (popover);
        window.child = column;
        window.present ();
        pump (300);
        var paintable = new Gtk.WidgetPaintable (window);
        var snapshot = new Gtk.Snapshot ();
        paintable.snapshot (snapshot, window.get_width (), window.get_height ());
        var node = snapshot.to_node ();
        if (node == null) {
            stderr.printf ("FAIL: nothing painted\n");
            return 1;
        }
        var texture = window.get_native ().get_renderer ().render_texture (node, null);
        texture.save_to_png (shot);
        stdout.printf ("wrote %s\n", shot);
        window.destroy ();
    }
    stdout.printf ("PASS: indicator probe (%d labels)\n", texts.size);
    return 0;
}
