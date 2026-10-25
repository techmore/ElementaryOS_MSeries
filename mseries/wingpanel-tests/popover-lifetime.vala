/* Isolated reproduction for the anchor lifetime bug in Wingpanel 6b8ae0453b1f.
 * No live panel, user accounts or app windows are touched. */
class DemoIndicator : Wingpanel.Indicator {
    private Gtk.Widget bar;
    private Gtk.Widget content;
    public DemoIndicator (string name) {
        Object (code_name: name);
        visible = true;
        bar = new Gtk.Label (name) { width_request = 220, height_request = 28 };
        content = new Gtk.Label (name + " popup") { width_request = 309, height_request = 54 };
    }
    public override void opened () {}
    public override void closed () {}
    public override Gtk.Widget get_display_widget () { return bar; }
    public override Gtk.Widget? get_widget () { return content; }
}
int main () {
    Gtk.init ();
    Granite.init ();
    Gtk.Settings.get_default ().gtk_enable_animations = Environment.get_variable ("TEST_ANIMATIONS") == "1";
    var manager = new Wingpanel.Services.PopoverManager ();
    int transitions = 0;
    manager.notify["current-indicator"].connect (() => transitions++);
    var box = new Gtk.Box (Gtk.Orientation.HORIZONTAL, 0);
    Wingpanel.Widgets.IndicatorEntry? a = new Wingpanel.Widgets.IndicatorEntry (new DemoIndicator ("first"), manager);
    var b = new Wingpanel.Widgets.IndicatorEntry (new DemoIndicator ("second"), manager);
    box.append (a);
    box.append (b);
    var window = new Gtk.Window () { child = box, default_width = 440, default_height = 28 };
    window.present ();
    var loop = new MainLoop ();
    Timeout.add (300, () => { manager.current_indicator = a; return Source.REMOVE; });
    Timeout.add (650, () => {
        // Setup has completed. Any critical during anchor removal/switch/close fails the test.
        Log.set_always_fatal (LogLevelFlags.LEVEL_ERROR | LogLevelFlags.LEVEL_CRITICAL);
        box.remove (a);
        a = null;
        manager.current_indicator = Environment.get_variable ("TEST_ACTION") == "close" ? null : b;
        return Source.REMOVE;
    });
    Timeout.add (1000, () => { manager.current_indicator = null; return Source.REMOVE; });
    Timeout.add (1400, () => { loop.quit (); return Source.REMOVE; });
    loop.run ();
    stdout.printf ("Popover transitions: %d\n", transitions);
    assert (transitions >= 2);
    return 0;
}
