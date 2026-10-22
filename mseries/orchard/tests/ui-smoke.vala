/* The whole Orchard window against a fake Incus socket and a fake podman (test-ui.py): the three
 * sidebar sections, the Incus home and instance pages, the Podman page, every secondary window
 * reachable from the palette and orchard:// links, and the GSK capture used for the docs. */

Gtk.Widget? find_row (Gtk.Widget root, Type type) {
    if (root.get_type () == type) return root;
    for (var child = root.get_first_child (); child != null; child = child.get_next_sibling ()) {
        var found = find_row (child, type); if (found != null) return found;
    }
    return null;
}

void spin (uint ms) {
    var loop = new MainLoop ();
    Timeout.add (ms, () => { loop.quit (); return Source.REMOVE; });
    loop.run ();
}

void capture (Gtk.Window window, string path) {
    var paintable = new Gtk.WidgetPaintable (window);
    var snapshot = new Gtk.Snapshot ();
    paintable.snapshot (snapshot, window.get_width (), window.get_height ());
    var node = snapshot.to_node ();
    assert (node != null);
    var texture = window.get_renderer ().render_texture (node, null);
    assert (texture.save_to_png (path));
}

int main () {
    Environment.set_variable ("GSK_RENDERER", Environment.get_variable ("GSK_RENDERER") ?? "cairo", true);
    Gtk.init (); // Fixture windows do not initialize the desktop AccountsService integration.
    var app = new Orchard ("com.github.techmore.orchard.Test.T" + Uuid.string_random ().replace ("-", ""));
    try { app.register (null); } catch (Error e) { return 1; }
    app.activate ();
    var main_window = app.main_window;
    assert (main_window != null);
    main_window.set_default_size (980, 660);   // the app's default size: no page may widen it (887 px minimum on CI fonts, 775 here)
    spin (1500);   // first Incus listing against the fixture socket

    int minimum, natural;
    main_window.measure (Gtk.Orientation.HORIZONTAL, -1, out minimum, out natural, null, null);
    print ("Orchard minimum width: %d; allocated: %d\n", minimum, main_window.get_width ());
    assert (minimum <= 980);
    assert (main_window.get_width () <= 980);

    // The sidebar has the Incus home row, the fixture instance and the Podman row.
    assert (find_row (main_window.child, typeof (IncusHomeRow)) != null);
    assert (find_row (main_window.child, typeof (PodmanRow)) != null);
    var instance_row = find_row (main_window.child, typeof (IncusRow)) as IncusRow;
    assert (instance_row != null);
    assert (instance_row.instance.name == "fixture-with-a-long-name-that-must-not-widen-the-window");

    // orchard:// links select pages; unknown instances fall back to the Incus page.
    app.navigate_uri ("orchard://containers");
    app.navigate_uri ("orchard://container/fixture-with-a-long-name-that-must-not-widen-the-window");
    spin (300);
    app.navigate_uri ("orchard://podman");
    app.navigate_uri ("orchard://dashboard");

    // Every secondary window opens from a link or the palette action.
    string[] links = { "orchard://models", "orchard://sandboxes", "orchard://systemlogs", "orchard://mounts", "orchard://images", "orchard://networks", "orchard://profiles" };
    Type[] windows = { typeof (ModelsWindow), typeof (SandboxesWindow), typeof (SystemWindow), typeof (MountsWindow), typeof (ResourceBrowser), typeof (ResourceBrowser), typeof (ResourceBrowser) };
    for (int i = 0; i < links.length; i++) {
        app.navigate_uri (links[i]);
        bool found = false;
        var toplevels = Gtk.Window.get_toplevels ();
        for (uint j = 0; j < toplevels.get_n_items (); j++) {
            var candidate = (Gtk.Window) toplevels.get_item (j);
            if (candidate.visible && candidate.get_type () == windows[i]) { found = true; candidate.destroy (); break; }
        }
        assert (found);
    }
    app.activate_action ("palette", null);
    bool palette = false;
    var tops = Gtk.Window.get_toplevels ();
    for (uint j = 0; j < tops.get_n_items (); j++) {
        var candidate = (Gtk.Window) tops.get_item (j);
        if (candidate.visible && candidate is CommandPalette) { palette = true; candidate.destroy (); break; }
    }
    assert (palette);
    spin (300);

    var page = Environment.get_variable ("ORCHARD_UI_PAGE") ?? "incus";
    if (page == "podman") app.navigate_uri ("orchard://podman");
    else if (page == "instance") app.navigate_uri ("orchard://container/fixture-with-a-long-name-that-must-not-widen-the-window");
    else app.navigate_uri ("orchard://dashboard");
    var capture_path = Environment.get_variable ("ORCHARD_UI_CAPTURE");
    if (capture_path != null) {
        // Navigation invalidates the current render node; wait for the next layout/frame. The Podman
        // page lists real containers through subprocesses, so it is given time to finish its first poll.
        spin (page == "podman" ? 2500 : 500);
        capture (main_window, capture_path);
    }
    // The Podman details window is built for the first listed container (the fixture's "web" under
    // meson test, a real container when ORCHARD_PODMAN is unset) and captured next to the page.
    if (page == "podman") {
        var podman = new PodmanClient ();
        PodmanContainer[] listed = {};
        var list_loop = new MainLoop ();
        podman.list_containers.begin ((obj, res) => {
            try { listed = podman.list_containers.end (res); } catch (Error e) { warning ("%s", e.message); }
            list_loop.quit ();
        });
        list_loop.run ();
        assert (listed.length > 0);
        var details = new PodmanDetails (main_window, podman, listed[0]);
        details.present ();
        spin (capture_path != null ? 4000 : 500);
        if (capture_path != null) capture (details, capture_path.replace (".png", "-details.png"));
        details.destroy ();
    }
    main_window.destroy ();
    print ("Native window construction and initial asynchronous reads passed.\n");
    return 0;
}
