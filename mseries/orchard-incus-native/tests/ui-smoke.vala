Gtk.Widget? find_selection (Gtk.Widget root) {
    if (root is Gtk.CheckButton) return root;
    for (var child = root.get_first_child (); child != null; child = child.get_next_sibling ()) {
        var found = find_selection (child); if (found != null) return found;
    }
    return null;
}
Gtk.Button? find_button (Gtk.Widget root, string label) {
    if (root is Gtk.Button && ((Gtk.Button) root).label == label) return (Gtk.Button) root;
    for (var child = root.get_first_child (); child != null; child = child.get_next_sibling ()) {
        var found = find_button (child, label); if (found != null) return found;
    }
    return null;
}
int main () {
    Gtk.init (); // Fixture windows do not initialize the desktop AccountsService integration.
    var app = new Gtk.Application ("com.github.techmore.orchardincus.Test.T" + Uuid.string_random ().replace ("-", ""), ApplicationFlags.DEFAULT_FLAGS);
    try { app.register (null); } catch (Error e) { return 1; }
    var main_window = new MainWindow (app);
    main_window.set_default_size (720, 640);
    main_window.navigate_uri ("orchard://containers");
    main_window.present ();
    var client = new IncusClient (5);
    Gtk.Window[] windows = {
        new InstanceDetails (main_window, client, "fixture"),
        new ResourceBrowser (main_window, client),
        new CommandPalette (main_window, client),
        new ModelsWindow (main_window),
        new SandboxesWindow (main_window, client),
        new SandboxCreateWindow (main_window, client),
        new SystemWindow (main_window, client),
        new MountsWindow (main_window, client),
        new LogViewer (main_window, client, "fixture"),
        new ImagePullWindow (main_window, client),
        new DeviceEditor (main_window, client, "fixture", "disk")
    };
    var loop = new MainLoop ();
    Timeout.add (1000, () => { loop.quit (); return Source.REMOVE; });
    loop.run ();
    int minimum, natural;
    main_window.measure (Gtk.Orientation.HORIZONTAL, -1, out minimum, out natural, null, null);
    print ("Orchard minimum width: %d; allocated: %d\n", minimum, main_window.get_width ());
    assert (minimum <= 720);
    assert (main_window.get_width () <= 720);
    var selected = (Gtk.CheckButton) find_selection (main_window.child);
    var clear = find_button (main_window.child, "Clear selection");
    assert (selected != null && clear != null);
    var bulk = clear.get_ancestor (typeof (Gtk.FlowBox));
    assert (!bulk.visible);
    selected.active = true;
    assert (bulk.visible);
    clear.clicked ();
    assert (!bulk.visible);
    // Named menu actions must remain available after removing the crowded toolbar.
    assert (main_window.lookup_action ("resources") != null);
    string[] menu_actions = { "resources", "models", "sandboxes", "system", "mounts", "logs", "preferences" };
    Type[] menu_windows = { typeof (ResourceBrowser), typeof (ModelsWindow), typeof (SandboxesWindow), typeof (SystemWindow), typeof (MountsWindow), typeof (LogViewer), typeof (Gtk.Window) };
    for (int i = 0; i < menu_actions.length; i++) {
        main_window.activate_action (menu_actions[i], null);
        bool found = false;
        var toplevels = Gtk.Window.get_toplevels ();
        for (uint j = 0; j < toplevels.get_n_items (); j++) {
            var candidate = (Gtk.Window) toplevels.get_item (j);
            if (candidate.visible && candidate.get_type () == menu_windows[i] &&
                (menu_actions[i] != "preferences" || candidate.title == "Preferences")) {
                found = true;
                candidate.destroy ();
                break;
            }
        }
        assert (found);
    }
    main_window.activate_action ("dashboard", null);
    var page = Environment.get_variable ("ORCHARD_UI_PAGE") ?? "containers";
    main_window.navigate_uri ("orchard://" + (page == "dashboard" || page == "podman" ? page : "containers"));
    var capture_path = Environment.get_variable ("ORCHARD_UI_CAPTURE");
    if (capture_path != null) {
        // Navigation invalidates the current render node; wait for the next layout/frame. The Podman
        // page lists real containers through subprocesses, so it is given time to finish its first poll.
        var render_loop = new MainLoop ();
        Timeout.add (page == "podman" ? 2500 : 250, () => { render_loop.quit (); return Source.REMOVE; });
        render_loop.run ();
        var paintable = new Gtk.WidgetPaintable (main_window);
        var snapshot = new Gtk.Snapshot ();
        paintable.snapshot (snapshot, main_window.get_width (), main_window.get_height ());
        var node = snapshot.to_node ();
        assert (node != null);
        var texture = main_window.get_renderer ().render_texture (node, null);
        assert (texture.save_to_png (capture_path));
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
        var details_loop = new MainLoop ();
        Timeout.add (capture_path != null ? 4000 : 500, () => { details_loop.quit (); return Source.REMOVE; });
        details_loop.run ();
        if (capture_path != null) {
            var paintable = new Gtk.WidgetPaintable (details);
            var snapshot = new Gtk.Snapshot ();
            paintable.snapshot (snapshot, details.get_width (), details.get_height ());
            var node = snapshot.to_node ();
            assert (node != null);
            var texture = details.get_renderer ().render_texture (node, null);
            assert (texture.save_to_png (capture_path.replace (".png", "-details.png")));
        }
        details.destroy ();
    }
    foreach (var window in windows) window.destroy ();
    main_window.destroy ();
    print ("Native window construction and initial asynchronous reads passed.\n");
    return 0;
}
