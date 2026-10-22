// SPDX-License-Identifier: GPL-3.0-or-later
// Actual production Launcher/ItemGroup/ItemManager; isolated display/state/settings.
[DBus (name="org.pantheon.gala.DesktopIntegration")]
class SizePolicyCompositor : Object {
    public uint version { get { return 1; } }
    public async Dock.DesktopIntegration.Window[] get_windows () throws DBusError, IOError { return {}; }
    public async Dock.DesktopIntegration.RunningApplication[] get_running_applications () throws DBusError, IOError { return {}; }
    public async int get_active_workspace () throws DBusError, IOError { return 0; }
    public async int get_n_workspaces () throws DBusError, IOError { return 1; }
    public async void focus_window (uint64 uid) throws DBusError, IOError {}
    public async void show_windows_for (string id) throws DBusError, IOError {}
    public async void move_window_to_workspace (uint64 uid, int workspace) throws DBusError, IOError {}
    public async void activate_workspace (int workspace) throws DBusError, IOError {}
    public async void reorder_workspace (int a, int b) throws DBusError, IOError {}
}
void drain () {
    var loop = new MainLoop ();
    Timeout.add (600, () => { loop.quit (); return Source.REMOVE; });
    loop.run ();
}
void write_policy (string contents) {
    var directory = Path.build_filename (Environment.get_user_state_dir (), "mseries");
    DirUtils.create_with_parents (directory, 0700);
    try {
        var temporary = Path.build_filename (directory, "policy-test.tmp");
        FileUtils.set_contents (temporary, contents);
        assert (FileUtils.rename (temporary, Path.build_filename (directory, "ui-scale-policy.ini")) == 0);
    } catch (Error e) { error ("%s", e.message); }
    drain ();
}
void check_state (Dock.Launcher launcher, Dock.ItemGroup group, Gtk.Separator? separator,
                  Settings settings, int expected) {
    assert (settings.get_int ("icon-size") == 40);
    assert (launcher.icon_size == expected);
    assert (group.width_request == expected + Dock.ItemManager.get_padding () * 2);
    assert (Dock.ItemManager.get_padding () == 5);
    if (separator != null) assert (separator.height_request == expected);
}
int main () {
    Gtk.init ();
    var service_ready = new MainLoop ();
    Bus.own_name (BusType.SESSION, "org.pantheon.gala", BusNameOwnerFlags.NONE,
        (connection) => {
            try {
                connection.register_object ("/org/pantheon/gala/DesktopInterface", new SizePolicyCompositor ());
            } catch (Error e) { error ("%s", e.message); }
        }, () => service_ready.quit ());
    service_ready.run ();
    var settings = new Settings ("io.elementary.dock");
    settings.set_strv ("launchers", {});
    settings.set_int ("icon-size", 40);
    settings.set_boolean ("taskbar-mode", true);
    var info = new DesktopAppInfo ("TeamsFixture.desktop");
    assert (info != null);
    var app = new Dock.App (info, true);
    var launcher = new Dock.Launcher (app);
    var model = new ListStore (typeof (Dock.App));
    var group = new Dock.ItemGroup (model, (obj) => new Dock.Launcher ((Dock.App) obj));
    model.append (app);
    var manager = Dock.ItemManager.get_default ();
    Gtk.Separator? separator = null;
    for (var child = manager.get_first_child (); child != null; child = child.get_next_sibling ()) {
        if (child is Gtk.Separator) separator = (Gtk.Separator) child;
    }
    var box = new Gtk.Box (Gtk.Orientation.VERTICAL, 0);
    box.append (launcher);
    box.append (group);
    var window = new Gtk.Window () { child = box };
    window.present ();
    drain ();
    check_state (launcher, group, separator, settings, 43);
    // No settings writes below: both adoption and unmanage must invalidate caches.
    write_policy ("[SizeSystem]\nversion=1\nmanaged=true\n");
    check_state (launcher, group, separator, settings, 36);
    write_policy ("[SizeSystem]\nversion=1\nmanaged=false\n");
    check_state (launcher, group, separator, settings, 43);
    write_policy ("[SizeSystem]\nversion=1\nmanaged=true\n");
    check_state (launcher, group, separator, settings, 36);
    write_policy ("malformed");
    check_state (launcher, group, separator, settings, 43);
    write_policy ("[SizeSystem]\nversion=1\nmanaged=true\n");
    check_state (launcher, group, separator, settings, 36);
    assert (FileUtils.unlink (Path.build_filename (Environment.get_user_state_dir (),
        "mseries", "ui-scale-policy.ini")) == 0);
    drain ();
    check_state (launcher, group, separator, settings, 43);
    window.destroy ();
    stdout.printf ("PASS: actual Launcher cache, ItemGroup relayout and separator update across atomic adoption/unmanage/malformed/delete without icon-size change (separator present:%s)\n",
        (separator != null).to_string ());
    return 0;
}
