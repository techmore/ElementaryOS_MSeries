[CCode (has_target = false)]
delegate Wingpanel.Indicator? LoadIndicator (Module module, Wingpanel.ServerType type);

int main (string[] args) {
    Gtk.init ();
    var module = Module.open (args[1], ModuleFlags.BIND_LOCAL);
    assert (module != null);
    void* symbol;
    assert (module.symbol ("get_indicator", out symbol));
    LoadIndicator load = (LoadIndicator) symbol;
    assert (load (module, Wingpanel.ServerType.GREETER) == null);
    var indicator = load (module, Wingpanel.ServerType.SESSION);
    assert (indicator != null && indicator.visible);
    var display = (Gtk.Box) indicator.get_display_widget ();
    assert (((Gtk.Image) display.get_first_child ()).icon_name == "orchard-incus-symbolic");
    var badge = (Gtk.Label) display.get_first_child ().get_next_sibling ();
    assert (badge.get_next_sibling () == null);
    assert (badge.label == "…");

    // One indicator instance must recover from an error and replace stale counts.
    string[] expected = { "2", "0", "0", "—", "1" };
    int stage = 0;
    var loop = new MainLoop ();
    Timeout.add (50, () => {
        if (badge.label != expected[stage]) return Source.CONTINUE;
        // The two zero stages have different responses: empty vs all stopped.
        if (stage == 1 && !display.tooltip_text.contains ("No local instances")) return Source.CONTINUE;
        if (stage == 2 && !display.tooltip_text.contains ("0 of 1")) return Source.CONTINUE;
        if (stage == 3) assert (display.tooltip_text.contains ("Incus unavailable"));
        assert (indicator.visible);
        assert (badge.get_next_sibling () == null);
        print ("Badge stage %d: %s\n", stage, badge.label);
        if (++stage == expected.length) {
            loop.quit ();
            return Source.REMOVE;
        }
        indicator.opened ();
        return Source.CONTINUE;
    });
    Timeout.add_seconds (15, () => { error ("Timed out at badge stage %d", stage); });
    loop.run ();
    module.make_resident ();
    return 0;
}
