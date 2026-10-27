/* SPDX-License-Identifier: GPL-3.0 */
Gtk.Button? action (Gtk.Widget widget, string label) {
    if (widget is Gtk.Button && ((Gtk.Button) widget).get_label () == label) return (Gtk.Button) widget;
    for (var child = widget.get_first_child (); child != null; child = child.get_next_sibling ()) {
        var found = action (child, label);
        if (found != null) return found;
    }
    return null;
}
Gtk.Stack? stack (Gtk.Widget widget) {
    if (widget is Gtk.Stack) return (Gtk.Stack) widget;
    for (var child = widget.get_first_child (); child != null; child = child.get_next_sibling ()) {
        var found = stack (child);
        if (found != null) return found;
    }
    return null;
}
int64 snapshot_calls () {
    string text;
    try { FileUtils.get_contents (Environment.get_home_dir () + "/snapshot-calls", out text); return text.length; }
    catch (Error e) { return 0; }
}
int main () {
    Gtk.init ();
    Gtk.Settings.get_default ().gtk_application_prefer_dark_theme = Environment.get_variable ("TEST_DARK") == "1";
    var cache = Environment.get_user_cache_dir () + "/claude-pantheon-rs";
    DirUtils.create_with_parents (cache, 0700);
    var status_path = cache + "/status.json";
    var feed = "{\"schemaVersion\":1,\"connected\":true,\"stale\":false,\"writtenAt\":\"%s\",\"pendingPrompts\":[{\"threadId\":\"fixture\"}],\"running\":[]}".printf (new DateTime.now_utc ().format_iso8601 ());
    try { FileUtils.set_contents (status_path, feed); } catch (Error e) { assert_not_reached (); }
    uint owner = Bus.own_name (BusType.SESSION, "io.github.techmore.ClaudePantheonRs", BusNameOwnerFlags.NONE);
    var indicator = new MSeries.T3Indicator ();
    var window = new Gtk.Window () { title = "Unified T3 panel probe", default_width = 540, default_height = 760 };
    var root = new Gtk.Box (Gtk.Orientation.VERTICAL, 6);
    var display = indicator.get_display_widget ();
    var content = indicator.get_widget ();
    root.append (display);
    root.append (content);
    window.child = root;
    window.present ();
    int closes = 0;
    indicator.close.connect (() => { closes++; indicator.closed (); });
    var loop = new MainLoop ();
    Timeout.add (400, () => {
        assert (snapshot_calls () == 0);
        var badge = (Gtk.Label) display.get_last_child ();
        assert (badge.visible && badge.label == "1");
        for (var child = display.get_first_child (); child != null; child = child.get_next_sibling ())
            assert (!(child is Gtk.Popover));
        indicator.opened ();
        return Source.REMOVE;
    });
    Timeout.add (2200, () => { stack (content).visible_child_name = "github"; return Source.REMOVE; });
    int64 closed_calls = 0;
    Timeout.add (4000, () => {
        indicator.closed ();
        closed_calls = snapshot_calls ();
        try { FileUtils.set_contents (status_path, "{\"schemaVersion\":1,\"stale\":true}"); }
        catch (Error e) { assert_not_reached (); }
        assert (closed_calls > 0);
        return Source.REMOVE;
    });
    Timeout.add (10000, () => {
        assert (snapshot_calls () == closed_calls);
        assert (!display.get_last_child ().visible);
        indicator.opened ();
        action (content, "Activity").clicked ();
        indicator.opened ();
        action (content, "Fleet").clicked ();
        indicator.opened ();
        action (content, "Open T3").clicked ();
        assert (closes == 3);
        return Source.REMOVE;
    });
    Timeout.add (10800, () => {
        string calls;
        try { FileUtils.get_contents (Environment.get_home_dir () + "/action-calls", out calls); }
        catch (Error e) { assert_not_reached (); }
        assert (calls.contains ("--activity") && calls.contains ("--fleet") && calls.contains ("--full"));
        window.destroy ();
        indicator.dispose ();
        Bus.unown_name (owner);
        print ("PASS native T3 panel: hosted content, lazy usage, tabs, stopped closed polling, three launch/close routes\n");
        loop.quit ();
        return Source.REMOVE;
    });
    loop.run ();
    return 0;
}
