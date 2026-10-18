namespace MSeries {
    private string config_path;

    private void write_fixture (string data) {
        try { FileUtils.set_contents (config_path, data); } catch (Error e) { error ("%s", e.message); }
    }

    private void test_preferences () {
        var prefs = new PanelPreferences ();
        foreach (var key in new string[] { "showPercent", "showReset", "showAccounts", "showHints" }) {
            assert (prefs.get_bool (key));
        }
        assert (prefs.last_error == "");
        assert (!prefs.load ());
        foreach (var key in new string[] { "showPercent", "showReset", "showAccounts", "showHints" }) {
            assert (prefs.save_bool (key, false));
        }
        var restored = new PanelPreferences ();
        foreach (var key in new string[] { "showPercent", "showReset", "showAccounts", "showHints" }) {
            assert (!restored.get_bool (key));
        }
        try {
            var info = File.new_for_path (config_path).query_info (FileAttribute.UNIX_MODE, FileQueryInfoFlags.NONE);
            assert ((info.get_attribute_uint32 (FileAttribute.UNIX_MODE) & 0777) == 0600);
        } catch (Error e) { error ("%s", e.message); }

        write_fixture ("{\"showPercent\":\"false\",\"showReset\":0,\"showAccounts\":null,\"showHints\":[],\"future\":{\"answer\":42}}");
        assert (restored.load ());
        assert (restored.get_bool ("showPercent"));
        assert (restored.get_bool ("showReset"));
        assert (restored.get_bool ("showAccounts"));
        assert (restored.get_bool ("showHints"));
        assert (restored.last_error != "");
        assert (restored.save_bool ("showPercent", false));
        try {
            var parser = new Json.Parser ();
            parser.load_from_file (config_path);
            var obj = parser.get_root ().get_object ();
            assert (obj.get_object_member ("future").get_int_member ("answer") == 42);
            assert (obj.has_member ("showHints"));
        } catch (Error e) { error ("%s", e.message); }
        assert (!restored.save_bool ("future", false));
        assert (restored.last_error != "");

        foreach (var invalid in new string[] { "{broken", "[]", "null", "true" }) {
            write_fixture (invalid);
            assert (!restored.load ());
            assert (!restored.get_bool ("showPercent"));
            assert (restored.last_error != "");
            assert (!restored.save_bool ("showPercent", true));
            try {
                string actual;
                FileUtils.get_contents (config_path, out actual);
                assert (actual == invalid);
            } catch (Error e) { error ("%s", e.message); }
            var fresh = new PanelPreferences ();
            assert (fresh.get_bool ("showPercent"));
            assert (fresh.last_error != "");
        }
        FileUtils.unlink (config_path);
        assert (restored.load ());
        assert (restored.get_bool ("showPercent"));
        assert (restored.last_error == "");
        assert (!restored.load ());
    }

    int main (string[] args) {
        Test.init (ref args);
        string directory;
        try { directory = DirUtils.make_tmp ("codexbar-panel-preferences-XXXXXX"); }
        catch (Error e) { error ("%s", e.message); }
        Environment.set_variable ("XDG_CONFIG_HOME", directory, true);
        config_path = Path.build_filename (directory, "codexbar", "wingpanel.json");
        Test.add_func ("/panel-preferences/persistence-validation-recovery", test_preferences);
        int result = Test.run ();
        FileUtils.unlink (config_path);
        DirUtils.remove (Path.get_dirname (config_path));
        DirUtils.remove (directory);
        return result;
    }
}
