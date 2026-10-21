/* Private fake-helper test. No real GitHub account or running panel. */
string widget_text (Gtk.Widget widget) {
    string text = widget.get_tooltip_text () ?? "";
    if (widget is Gtk.Label) text += ((Gtk.Label) widget).label;
    for (var child = widget.get_first_child (); child != null; child = child.get_next_sibling ())
        text += widget_text (child);
    return text;
}
int main () {
    Gtk.init ();
    Granite.init ();
    var indicator = new MSeries.RepoBarIndicator ();
    var menu = indicator.get_widget ();
    var panel = indicator.get_display_widget ();
    var window = new Gtk.Window ();
    var root = new Gtk.Box (Gtk.Orientation.VERTICAL, 0);
    root.append (panel); root.append (menu); window.child = root; window.present ();
    var loop = new MainLoop ();
    bool failed = false;
    string mode = Environment.get_variable ("RB_TEST_MODE") ?? "race";
    Timeout.add (mode == "failure" ? 500 : 100, () => {
        string text = widget_text (root);
        if (mode == "failure" ? !text.contains ("ALICE_PRIVATE") : text.contains ("DISK_PRIVATE")) {
            stderr.printf ("invalid initial state (%s)\n", mode); failed = true;
        }
        try {
            FileUtils.set_contents (Environment.get_home_dir () + "/phase", mode == "failure" ? "failure" : "bob");
            if (mode == "race")
                FileUtils.set_contents (Environment.get_user_config_dir () + "/mseries/repobar/settings.json", "{\"version\":1,\"account\":\"bob\"}");
            else indicator.opened ();
        } catch (Error e) { failed = true; }
        return Source.REMOVE;
    });
    Timeout.add (2200, () => {
        string text = widget_text (root);
        if (text.contains ("ALICE_PRIVATE") || text.contains ("DISK_PRIVATE") ||
            (mode == "race" && !text.contains ("BOB_PRIVATE"))) {
            stderr.printf ("account content leaked or expected new account missing (%s)\n", mode); failed = true;
        }
        loop.quit (); return Source.REMOVE;
    });
    loop.run ();
    return failed ? 1 : 0;
}
