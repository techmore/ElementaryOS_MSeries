Gtk.Revealer marker_revealer (Gtk.Widget widget) {
    if (widget.has_css_class ("running-indicator"))
        return (Gtk.Revealer) widget.get_ancestor (typeof (Gtk.Revealer));
    for (var c = widget.get_first_child (); c != null; c = c.get_next_sibling ()) {
        var found = find_marker (c);
        if (found != null) return found;
    }
    assert_not_reached ();
}
Gtk.Revealer? find_marker (Gtk.Widget widget) {
    if (widget.has_css_class ("running-indicator"))
        return (Gtk.Revealer) widget.get_ancestor (typeof (Gtk.Revealer));
    for (var c = widget.get_first_child (); c != null; c = c.get_next_sibling ()) {
        var found = find_marker (c); if (found != null) return found;
    }
    return null;
}
int main () {
    Gtk.init ();
    var info = new DesktopAppInfo ("TeamsFixture.desktop");
    assert (info != null);
    var app = new Dock.App (info, true);
    var windows = new GenericArray<Dock.Window> ();
    var win = new Dock.Window (1);
    var props = new HashTable<string,Variant> (str_hash, str_equal);
    props["app-id"] = new Variant.string ("TeamsFixture");
    props["has-focus"] = new Variant.boolean (false);
    win.update_properties (props); windows.add (win);
    app.update_windows (windows);
    var launcher = new Dock.Launcher (app);
    var revealer = marker_revealer (launcher);
    assert (revealer.reveal_child);
    assert (!launcher.has_css_class ("focused"));
    props["has-focus"] = new Variant.boolean (true);
    win.update_properties (props); app.update_windows (windows);
    assert (launcher.has_css_class ("focused"));
    assert (revealer.reveal_child);
    app.update_windows (new GenericArray<Dock.Window> ());
    assert (!revealer.reveal_child);
    assert (!launcher.has_css_class ("focused"));
    props["has-focus"] = new Variant.boolean (false);
    win.update_properties (props); app.update_windows (windows);
    assert (revealer.reveal_child);
    assert (!launcher.has_css_class ("focused"));
    print ("PASS real launcher: initially-open marker, focus-only update, close, reopen\n");
    return 0;
}
