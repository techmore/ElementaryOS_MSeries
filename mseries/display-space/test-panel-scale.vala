// SPDX-License-Identifier: GPL-3.0-or-later
// Compile with the production IndicatorBar after all layout patches.
class Wingpanel.Widgets.IndicatorEntry : Granite.Bin {
    public IndicatorEntry () {
        child = new Gtk.Box (Gtk.Orientation.HORIZONTAL, 8);
        ((Gtk.Box) child).append (new Gtk.Image.from_icon_name ("audio-volume-high-symbolic") { pixel_size = 16 });
        ((Gtk.Box) child).append (new Gtk.Label ("Applications · 12:34"));
    }
}
int main (string[] args) {
    Gtk.init ();
    var entries = new GLib.ListStore (typeof (Wingpanel.Widgets.IndicatorEntry));
    entries.append (new Wingpanel.Widgets.IndicatorEntry ());
    var bar = new Wingpanel.Widgets.IndicatorBar (entries);
    foreach (var orientation in new Gtk.Orientation[] { Gtk.Orientation.HORIZONTAL, Gtk.Orientation.VERTICAL }) {
        int minimum, natural, baseline_min, baseline_nat;
        int child_min, child_nat;
        bar.child.measure (orientation, -1, out child_min, out child_nat, null, null);
        bar.measure (orientation, -1, out minimum, out natural, out baseline_min, out baseline_nat);
        assert (minimum == (int) Math.ceil (child_min * 1.15f));
        assert (natural == (int) Math.ceil (child_nat * 1.15f));
    }
    var window = new Gtk.Window () { child = bar, decorated = false };
    window.present ();
    var loop = new GLib.MainLoop ();
    GLib.Timeout.add (300, () => {
        Graphene.Point source = Graphene.Point ().init (100, 10);
        Graphene.Point mapped;
        assert (bar.child.compute_point (bar, source, out mapped));
        assert (Math.fabs (mapped.x - 115) < 0.01);
        assert (Math.fabs (mapped.y - 11.5) < 0.01);
        assert (bar.child.get_width () <= bar.get_width () / 1.15f + 1);
        stdout.printf ("PASS: panel measurement and allocation scale all contents by 1.15\n");
        loop.quit ();
        return GLib.Source.REMOVE;
    });
    loop.run ();
    window.destroy ();
    return 0;
}
