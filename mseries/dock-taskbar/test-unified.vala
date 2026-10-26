Gtk.Button? find_action (Gtk.Widget widget, string label) {
    if (widget is Gtk.Button && ((Gtk.Button) widget).get_label () == label) return (Gtk.Button) widget;
    for (var child = widget.get_first_child (); child != null; child = child.get_next_sibling ()) {
        var found = find_action (child, label);
        if (found != null) return found;
    }
    return null;
}
/* Production widgets on a private display, with a private helper and bus. */
Gtk.Stack? find_stack (Gtk.Widget widget) {
    if (widget is Gtk.Stack) return (Gtk.Stack) widget;
    for (var child = widget.get_first_child (); child != null; child = child.get_next_sibling ()) {
        var found = find_stack (child);
        if (found != null) return found;
    }
    return null;
}
int main () {
    Gtk.init ();
    var settings = Gtk.Settings.get_default ();
    settings.gtk_application_prefer_dark_theme = Environment.get_variable ("TEST_DARK") == "1";
    var window = new Gtk.Window () { default_width = 900, default_height = 850 };
    var row = new Gtk.Box (Gtk.Orientation.VERTICAL, 0);
    var entry = new Gtk.Entry ();
    row.append (entry);
    var item = new Dock.TaskbarT3 ();
    row.append (item);
    window.child = row;
    window.present ();
    var button = (Gtk.Button) item.get_first_child ();
    Gtk.Popover? popup = null;
    for (var child = button.get_first_child (); child != null; child = child.get_next_sibling ())
        if (child is Gtk.Popover) popup = (Gtk.Popover) child;
    assert (popup != null);
    Gtk.EventControllerMotion? motion = null;
    var controllers = button.observe_controllers ();
    for (uint i = 0; i < controllers.get_n_items (); i++)
        if (controllers.get_item (i) is Gtk.EventControllerMotion) motion = (Gtk.EventControllerMotion) controllers.get_item (i);
    assert (motion != null);
    var loop = new MainLoop ();
    Timeout.add (200, () => { entry.grab_focus (); motion.enter (1, 1); return Source.REMOVE; });
    Timeout.add (600, () => {
        assert (popup.visible && !popup.autohide);
        assert (window.get_focus () == entry || window.get_focus ().is_ancestor (entry));
        assert (!FileUtils.test (Environment.get_home_dir () + "/helper-called", FileTest.EXISTS));
        button.clicked ();
        assert (popup.visible && popup.autohide);
        var stack = find_stack (popup.child);
        assert (stack != null);
        stack.visible_child_name = "github";
        return Source.REMOVE;
    });
    Timeout.add (1400, () => {
        assert (FileUtils.test (Environment.get_home_dir () + "/helper-called", FileTest.EXISTS));
        find_stack (popup.child).visible_child_name = "usage";
        return Source.REMOVE;
    });
    Timeout.add (2000, () => {
        button.clicked (); assert (!popup.visible);
        motion.enter (1, 1);
        return Source.REMOVE;
    });
    Timeout.add (2400, () => { assert (popup.visible); motion.leave (); return Source.REMOVE; });
    Timeout.add (3000, () => {
        assert (!popup.visible);
        button.clicked (); assert (popup.visible && popup.autohide);
        print ("PASS unified T3: hover focus, click pin/toggle, delayed close, lazy GitHub helper, Usage/GitHub switching\n");
        // Leave the private fixture visible briefly for external screenshot capture.
        return Source.REMOVE;
    });
    Timeout.add (4500, () => {
        find_stack (popup.child).visible_child_name = "github";
        return Source.REMOVE;
    });
    int64 snapshots_when_closed = 0;
    Timeout.add (6500, () => {
        button.clicked ();
        assert (!popup.visible);
        string calls;
        try { FileUtils.get_contents (Environment.get_home_dir () + "/snapshot-calls", out calls); }
        catch (Error e) { assert_not_reached (); }
        snapshots_when_closed = calls.length;
        return Source.REMOVE;
    });
    Timeout.add (12500, () => {
        string calls;
        try { FileUtils.get_contents (Environment.get_home_dir () + "/snapshot-calls", out calls); }
        catch (Error e) { assert_not_reached (); }
        assert (calls.length == snapshots_when_closed);
        print ("PASS closed embedded usage does not poll snapshots during the next 5-second interval\n");
        button.clicked ();
        find_action (popup.child, "Activity").clicked ();
        return Source.REMOVE;
    });
    Timeout.add (13000, () => {
        string calls;
        try { FileUtils.get_contents (Environment.get_home_dir () + "/action-calls", out calls); }
        catch (Error e) { assert_not_reached (); }
        assert (calls.contains ("--activity"));
        button.clicked ();
        find_action (popup.child, "Open T3").clicked ();
        return Source.REMOVE;
    });
    Timeout.add (13500, () => {
        string calls;
        try { FileUtils.get_contents (Environment.get_home_dir () + "/action-calls", out calls); }
        catch (Error e) { assert_not_reached (); }
        assert (calls.contains ("--full"));
        print ("PASS Activity and Open T3 launch the declared desktop actions\n");
        loop.quit ();
        return Source.REMOVE;
    });
    loop.run ();
    window.close ();
    return 0;
}
