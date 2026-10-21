// Compiled with the actual patched Wingpanel sources in an isolated session.
class StartupIndicator : Wingpanel.Indicator {
    private Gtk.Label label = new Gtk.Label ("Clock");
    public StartupIndicator () { Object (code_name: "datetime", visible: true); }
    public override Gtk.Widget get_display_widget () { return label; }
    public override Gtk.Widget? get_widget () { return null; }
    public override void opened () {}
    public override void closed () {}
}

int main (string[] args) {
    Gtk.init ();
    Granite.init ();
    var window = new Wingpanel.PanelWindow ();
    assert (window.get_surface () == null);
    int minimum, natural, mb, nb;
    window.measure (Gtk.Orientation.HORIZONTAL, -1, out minimum, out natural, out mb, out nb);
    var monitor = (Gdk.Monitor) Gdk.Display.get_default ().get_monitors ().get_item (0);
    assert (minimum == monitor.geometry.width);
    assert (natural == minimum && natural < 10000);
    print ("PASS: pre-surface panel measurement equals monitor width (%d)\n", natural);
    window.destroy ();

    var entries = new ListStore (typeof (Wingpanel.Widgets.IndicatorEntry));
    bool notch = false;
    var left_filter = new Gtk.CustomFilter ((item) => notch);
    var center_filter = new Gtk.CustomFilter ((item) => !notch);
    var left_model = new Gtk.FilterListModel (entries, left_filter);
    var center_model = new Gtk.FilterListModel (entries, center_filter);
    var left = new Wingpanel.Widgets.IndicatorBar (left_model);
    var center = new Wingpanel.Widgets.IndicatorBar (center_model);
    entries.append (new Wingpanel.Widgets.IndicatorEntry (new StartupIndicator (), new Wingpanel.Services.PopoverManager ()));
    for (int i = 0; i < 20; i++) {
        left.suspend_model ();
        center.suspend_model ();
        notch = !notch;
        left_filter.changed (Gtk.FilterChange.DIFFERENT);
        center_filter.changed (Gtk.FilterChange.DIFFERENT);
        left.resume_model ();
        center.resume_model ();
        assert (left_model.get_n_items () == (notch ? 1 : 0));
        assert (center_model.get_n_items () == (notch ? 0 : 1));
    }
    entries.remove_all ();
    print ("PASS: empty indicator bars and 20 clock reparent transitions without GTK criticals\n");
    return 0;
}
