int main () {
    Gtk.init (); Granite.init ();
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
    main_window.navigate_uri ("orchard://containers");
    var capture_path = Environment.get_variable ("ORCHARD_UI_CAPTURE");
    if (capture_path != null) {
        // Navigation invalidates the current render node; wait for the next layout/frame.
        var render_loop = new MainLoop ();
        Timeout.add (250, () => { render_loop.quit (); return Source.REMOVE; });
        render_loop.run ();
        var paintable = new Gtk.WidgetPaintable (main_window);
        var snapshot = new Gtk.Snapshot ();
        paintable.snapshot (snapshot, main_window.get_width (), main_window.get_height ());
        var node = snapshot.to_node ();
        assert (node != null);
        var texture = main_window.get_renderer ().render_texture (node, null);
        assert (texture.save_to_png (capture_path));
    }
    foreach (var window in windows) window.destroy ();
    main_window.destroy ();
    print ("Native window construction and initial asynchronous reads passed.\n");
    return 0;
}
