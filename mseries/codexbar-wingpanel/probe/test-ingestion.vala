/* Real indicator, fake home/backends: a malformed refresh must fail safely and recover. */
string labels (Gtk.Widget widget) {
    string text = (widget is Gtk.Label) ? ((Gtk.Label) widget).label : "";
    for (var child = widget.get_first_child (); child != null; child = child.get_next_sibling ()) text += " " + labels (child);
    return text;
}
int main (string[] args) {
    Gtk.init ();
    Granite.init ();
    // Treat GLib/JSON precondition failures as test failures, not harmless log noise.
    Log.set_always_fatal (LogLevelFlags.LEVEL_ERROR | LogLevelFlags.LEVEL_CRITICAL);
    var indicator = new MSeries.CodexBarIndicator ();
    var menu = indicator.get_widget ();
    var bar = indicator.get_display_widget ();
    var loop = new MainLoop ();
    string[] inputs = {"{\"entries\":[null]}", "{\"entries\":[{\"windows\":[3]}]}",
        "{\"entries\":{}}", "{\"busy\":\"yes\"}", "[]", "null", "not json"};
    int step = -1;
    Timeout.add (350, () => {
        try {
            if (step == -1) assert (labels (bar).contains ("%"));
            else if (step < inputs.length) assert (labels (menu).contains ("Couldn't read usage"));
            else {
                assert (labels (bar).contains ("%"));
                stdout.printf ("Malformed snapshots rejected; valid data recovered; no GLib criticals.\n");
                loop.quit ();
                return Source.REMOVE;
            }
            step++;
            string text;
            if (step < inputs.length) text = inputs[step];
            else FileUtils.get_contents (Environment.get_variable ("CB_GOOD_FIXTURE"), out text);
            FileUtils.set_contents (Environment.get_variable ("CB_FIXTURE"), text);
            indicator.get_widget ();
        } catch (Error e) { error ("Probe IO: %s", e.message); }
        return Source.CONTINUE;
    });
    loop.run ();
    return 0;
}
