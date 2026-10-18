public class Preferences : Object {
    private KeyFile values = new KeyFile ();
    private string filename;
    public Preferences () {
        filename = Path.build_filename (Environment.get_user_config_dir (), "orchard-incus", "preferences.ini");
        try { values.load_from_file (filename, KeyFileFlags.NONE); } catch (Error e) { }
    }
    public string read (string key, string fallback) {
        try { values.load_from_file (filename, KeyFileFlags.NONE); } catch (Error e) { }
        try { return values.get_string ("General", key); } catch (Error e) { return fallback; }
    }
    public void write (string key, string value) throws Error {
        try { values.load_from_file (filename, KeyFileFlags.NONE); } catch (Error e) { }
        values.set_string ("General", key, value);
        DirUtils.create_with_parents (Path.get_dirname (filename), 0700);
        values.save_to_file (filename);
    }
    public string shell { owned get { return read ("shell", "/bin/sh"); } }
}

public class PaletteMatch : Object {
    public static int score (string query, string text) {
        var q = query.down ().strip ();
        var haystack = text.down ();
        if (q == "") return 0;
        if (haystack.contains (q)) return 1000 - haystack.index_of (q);
        int cursor = 0;
        int result = 0;
        for (int i = 0; i < q.length; i++) {
            int found = haystack.index_of_char (q[i], cursor);
            if (found < 0) return -1;
            result += found == cursor ? 5 : 1;
            cursor = found + 1;
        }
        return result;
    }
}
