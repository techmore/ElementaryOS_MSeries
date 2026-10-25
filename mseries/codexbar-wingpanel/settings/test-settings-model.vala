int main (string[] args) {
    GLib.Test.init (ref args);
    GLib.Test.add_func ("/settings/defaults-and-load", () => {
        var model = new MSeries.SettingsModel ();
        assert (model.get_int ("refreshSeconds") == 300);
        assert (model.get_bool ("showTray"));
        assert (!model.get_bool ("notifications"));
        assert (model.load_from_data ("{\"refreshSeconds\":120,\"notifications\":true,\"providerOrder\":[\"codex\",\"opencodego\"],\"provider\":\"custom\",\"executable\":\"x\",\"trayStyle\":5}"));
        assert (model.get_int ("refreshSeconds") == 120);
        assert (model.get_bool ("notifications"));
        assert (model.providers ().length == 2);
        assert (model.get_string ("trayStyle") == "meters");        /* wrong type ignored */
        assert (!model.values.has_member ("executable"));            /* unknown key ignored */
        assert (!model.load_from_data ("not json"));
    });
    GLib.Test.add_func ("/settings/providers", () => {
        var model = new MSeries.SettingsModel ();
        assert (model.add_provider ("codex"));
        assert (model.add_provider ("claude"));
        assert (!model.add_provider ("codex"));                      /* duplicate */
        assert (!model.add_provider ("Bad Id"));
        assert (!model.add_provider ("all"));
        assert (model.get_string ("provider") == "custom");
        assert (model.move_provider ("claude", -1));
        assert (model.providers ()[0] == "claude");
        assert (!model.move_provider ("claude", -1));                /* already first */
        assert (model.remove_provider ("claude"));
        assert (!model.remove_provider ("codex"));                   /* never empty the list */
        assert (model.providers ().length == 1);
    });
    GLib.Test.add_func ("/settings/patch", () => {
        var model = new MSeries.SettingsModel ();
        model.values.set_int_member ("refreshSeconds", 600);
        var patch = model.patch_for ({ "refreshSeconds", "notifications", "nope" });
        assert (patch.contains ("\"refreshSeconds\":600"));
        assert (patch.contains ("\"notifications\":false"));
        assert (!patch.contains ("nope"));
    });
    return GLib.Test.run ();
}
