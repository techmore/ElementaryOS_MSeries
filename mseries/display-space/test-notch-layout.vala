// Compile with production src/Widgets/NotchLayout.vala; run under xvfb-run.
int main (string[] args) {
    Gtk.init ();
    const string MODEL = "Apple MacBook Pro (14-inch, M1 Pro, 2021)";
    assert (Wingpanel.Widgets.NotchLayout.is_active (MODEL, "eDP-1", "Y\n", 1512, 982));
    assert (!Wingpanel.Widgets.NotchLayout.is_active (MODEL, "HDMI-1", "Y", 1512, 982));
    assert (!Wingpanel.Widgets.NotchLayout.is_active (MODEL, "eDP-1", "N", 1512, 982));
    assert (!Wingpanel.Widgets.NotchLayout.is_active (MODEL, "eDP-1", "Y", 1512, 945));
    assert (!Wingpanel.Widgets.NotchLayout.is_active ("Other", "eDP-1", "Y", 1512, 982));
    assert (Wingpanel.Widgets.NotchLayout.depth (3024) == 74);
    assert (Wingpanel.Widgets.NotchLayout.depth (1512) == 37);
    assert (Wingpanel.Widgets.NotchLayout.depth (2016) == 50);
    var loop = new MainLoop ();
    var window = new Gtk.Window ();
    var left = new Gtk.ScrolledWindow ();
    var right = new Gtk.ScrolledWindow ();
    left.set_policy (EXTERNAL, NEVER);
    right.set_policy (EXTERNAL, NEVER);
    left.child = new Gtk.Label (string.nfill (200, 'L')) { halign = START };
    right.child = new Gtk.Label (string.nfill (200, 'R')) { halign = END };
    var halves = Wingpanel.Widgets.NotchLayout.halves (left, right, 1512);
    window.child = halves;
    window.set_default_size (1512, 37);
    window.present ();
    Timeout.add (250, () => {
        var width = halves.get_width ();
        var gap = Wingpanel.Widgets.NotchLayout.gap (1512);
        Gtk.Allocation la, ra;
        left.get_allocation (out la);
        right.get_allocation (out ra);
        assert (width == 1512);
        assert (la.x + la.width <= width / 2 - gap / 2);
        assert (ra.x >= width / 2 + gap / 2);
        assert (halves.get_height () == 37);
        assert (left.hadjustment.upper > left.hadjustment.page_size);
        assert (right.hadjustment.upper > right.hadjustment.page_size);
        loop.quit ();
        return Source.REMOVE;
    });
    loop.run ();
    window.destroy ();
    print ("Notch monitor gating, fractional sizes, crowded control allocation: PASS\n");
    return 0;
}
