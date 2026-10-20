/* Isolated Xvfb integration check: settings changes update cached UI without requesting another snapshot. */
string labels (Gtk.Widget widget) {
    var result = (widget is Gtk.Label) ? ((Gtk.Label) widget).label : "";
    for (var child = widget.get_first_child (); child != null; child = child.get_next_sibling ()) result += " " + labels (child);
    return result;
}
string snapshots () {
    string text;
    try { GLib.FileUtils.get_contents (GLib.Environment.get_variable ("TEST_SNAPSHOT_LOG"), out text); }
    catch (GLib.Error e) { return ""; }
    return text;
}
void assert_hover (Gtk.Widget widget, bool enabled) {
    assert (widget.has_tooltip == (enabled && widget.tooltip_text != null));
    for (var child = widget.get_first_child (); child != null; child = child.get_next_sibling ()) assert_hover (child, enabled);
}
int main (string[] args) {
    Gtk.init ();
    Granite.init ();
    var indicator = new MSeries.CodexBarIndicator ();
    var bar = indicator.get_display_widget ();
    indicator.get_widget ();
    var loop = new GLib.MainLoop ();
    GLib.Timeout.add (1000, () => {
        assert (labels (bar).contains ("%"));
        assert_hover (bar, false);
        var before = snapshots ();
        // Completing account/local helpers repaint cached data without extra IPC reads.
        assert (before == "snapshot\n");
        var prefs = new MSeries.PanelPreferences ();
        assert (prefs.save_bool ("showHoverInfo", true));
        foreach (var key in new string[] {"showPercent", "showReset", "showAccounts", "showHints"}) assert (prefs.save_bool (key, false));
        GLib.Timeout.add (450, () => {
            assert (!labels (bar).contains ("%"));
            assert_hover (bar, true);
            assert (prefs.save_bool ("showHoverInfo", false));
            assert (snapshots () == before);
            foreach (var key in new string[] {"showPercent", "showReset", "showAccounts", "showHints"}) assert (prefs.save_bool (key, true));
            GLib.Timeout.add (450, () => {
                assert (labels (bar).contains ("%"));
                assert_hover (bar, false);
                assert (snapshots () == before);
                stdout.printf ("Live preferences: two atomic replacements updated the panel without snapshot requests.\n");
                loop.quit ();
                return GLib.Source.REMOVE;
            });
            return GLib.Source.REMOVE;
        });
        return GLib.Source.REMOVE;
    });
    loop.run ();
    return 0;
}
