// Private fixtures for the real shared controls and the patched battery summary widget.
public class PreviewSlider : QuickSettings.SliderRow {
    public int writes = 0;
    public double written_value = -1;
    public PreviewSlider (string label, double value) { Object (title: label); show_value (value); }
    protected override string icon_for (double value, bool dimmed) { return title == "Volume" ? "audio-volume-medium-symbolic" : title == "Keyboard Brightness" ? "keyboard-brightness-symbolic" : "display-brightness-symbolic"; }
    protected override async void write (double value) throws Error { writes++; written_value = value; }
    public void change () { slider.set_value (21); slider.set_value (64); }
}
public class PreviewControls : Gtk.Box {
    class construct { set_css_name ("quicksettings"); }
    construct { orientation = Gtk.Orientation.VERTICAL; spacing = 8; }
}
void save_preview (Gtk.Widget widget, Gtk.Window window, string path) {
    var paintable = new Gtk.WidgetPaintable (widget);
    var snapshot = new Gtk.Snapshot ();
    paintable.snapshot (snapshot, widget.get_width (), widget.get_height ());
    var node = snapshot.to_node (); assert (node != null);
    assert (window.get_renderer ().render_texture (node, null).save_to_png (path));
}
int main (string[] args) {
    Gtk.init (); Granite.init ();
    var outer = new Gtk.Box (Gtk.Orientation.VERTICAL, 8) { margin_top = 12, margin_bottom = 12, margin_start = 12, margin_end = 12 };
    outer.add_css_class ("background");
    var window = new Gtk.Window () { child = outer, decorated = false };
    if (args[1] == "quick") {
        var controls = new PreviewControls ();
        var heading = new Gtk.Label ("Quick Settings") { xalign = 0, margin_start = 12, margin_bottom = 4 };
        heading.add_css_class ("heading"); controls.append (heading);
        var card = new QuickSettings.Card ();
        var volume = new PreviewSlider ("Volume", 42);
        card.add_row (volume);
        card.add_row (new PreviewSlider ("Screen Brightness", 68));
        card.add_row (new PreviewSlider ("Keyboard Brightness", 25));
        controls.append (card);
        outer.append (controls);
        window.set_default_size (340, -1);
        assert (volume.writes == 0); // A backend value must not write itself back.
        volume.change ();
        var check = new MainLoop ();
        Timeout.add (250, () => { check.quit (); return Source.REMOVE; }); check.run ();
        assert (volume.writes == 1 && volume.written_value == 64);
    } else {
        outer.append (new Power.Widgets.HistoryCard ());
        window.set_default_size (340, -1);
    }
    window.present ();
    var loop = new MainLoop ();
    Timeout.add (400, () => { save_preview (outer, window, args[2]); loop.quit (); return Source.REMOVE; });
    loop.run ();
    if (args[1] == "battery" && Environment.get_variable ("PANEL_BASELINE") == null) {
        var card = (Power.Widgets.HistoryCard) outer.get_first_child ();
        Gtk.Expander? details = null;
        for (var child = card.get_first_child (); child != null; child = child.get_next_sibling ())
            if (child is Gtk.Expander) details = (Gtk.Expander) child;
        assert (details != null && !details.expanded);
        details.expanded = true;
        var expanded_loop = new MainLoop ();
        Timeout.add (400, () => { save_preview (outer, window, args[2].replace (".png", "-expanded.png")); expanded_loop.quit (); return Source.REMOVE; });
        expanded_loop.run ();
        assert (details.expanded);
    }
    window.destroy ();
    print ("%s fixture rendered; checks passed\n", args[1]);
    return 0;
}
