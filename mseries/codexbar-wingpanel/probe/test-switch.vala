/* Exercise the real delayed confirmation and asynchronous switch against fake helpers only. */
Gtk.Button? find_button (Gtk.Widget widget, string title) {
    if (widget is Gtk.Button && ((Gtk.Button) widget).label == title) return (Gtk.Button) widget;
    for (var child = widget.get_first_child (); child != null; child = child.get_next_sibling ()) {
        var found = find_button (child, title);
        if (found != null) return found;
    }
    return null;
}
bool contains_label (Gtk.Widget widget, string text) {
    if (widget is Gtk.Label && ((Gtk.Label) widget).label.contains (text)) return true;
    for (var child = widget.get_first_child (); child != null; child = child.get_next_sibling ()) {
        if (contains_label (child, text)) return true;
    }
    return false;
}
int main (string[] args) {
    Gtk.init ();
    Granite.init ();
    var indicator = new MSeries.CodexBarIndicator ();
    var menu = indicator.get_widget ();
    var window = new Gtk.Window () { child = menu };
    window.present ();
    var loop = new MainLoop ();
    bool passed = false;
    Timeout.add (700, () => {
        var button = find_button (menu, "Switch");
        assert (button != null);
        button.clicked ();
        // Churn temporary arrays after the originating row callback returns. The old
        // confirmation captured a borrowed array that had already been freed here.
        for (int n = 0; n < 500; n++) {
            string[] churn = { "not-the-selected-account", n.to_string () };
            assert (churn.length == 2);
        }
        Timeout.add (300, () => {
            var windows = Gtk.Window.get_toplevels ();
            Gtk.Button? confirm = null;
            for (uint n = 0; n < windows.get_n_items (); n++) {
                confirm = find_button ((Gtk.Widget) windows.get_item (n), "Switch account");
                if (confirm != null) break;
            }
            assert (confirm != null);
            confirm.clicked ();
            Timeout.add (1000, () => {
                var expected = Environment.get_variable ("CB_SWITCH_EXPECT_ERROR") != null
                    ? "Couldn't switch Codex account" : "Switched ChatGPT account";
                var result_windows = Gtk.Window.get_toplevels ();
                for (uint n = 0; n < result_windows.get_n_items (); n++) {
                    if (contains_label ((Gtk.Widget) result_windows.get_item (n), expected)) passed = true;
                }
                assert (passed);
                stdout.printf ("Switch confirmation and async result: passed\n");
                loop.quit ();
                return Source.REMOVE;
            });
            return Source.REMOVE;
        });
        return Source.REMOVE;
    });
    Timeout.add (8000, () => { loop.quit (); return Source.REMOVE; });
    loop.run ();
    return passed ? 0 : 1;
}
