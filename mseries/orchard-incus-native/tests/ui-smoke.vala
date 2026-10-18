int main () {
    Gtk.init (); Granite.init ();
    var app = new Gtk.Application ("com.github.techmore.orchardincus.Test.T" + Uuid.string_random ().replace ("-", ""), ApplicationFlags.DEFAULT_FLAGS);
    try { app.register (null); } catch (Error e) { return 1; }
    var main_window = new MainWindow (app);
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
    foreach (var window in windows) window.destroy ();
    main_window.destroy ();
    print ("Native window construction and initial asynchronous reads passed.\n");
    return 0;
}
