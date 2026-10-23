/* Local Wingpanel preferences. Never passed to upstream's linux.json parser. */
namespace MSeries {
    public class PanelPreferences : GLib.Object {
        private Json.Object values = new Json.Object ();
        private string path;
        private const string[] KEYS = { "showPercent", "showReset", "showAccounts", "showHints", "showTokens", "compactQuota", "showHoverInfo", "accountLegend", "denseTable" };
        public string last_error { get; private set; default = ""; }

        public PanelPreferences () {
            path = Path.build_filename (Environment.get_user_config_dir (), "codexbar", "wingpanel.json");
            load ();
        }

        public bool get_bool (string key) {
            var node = values.get_member (key);
            return node != null && node.get_value_type () == typeof (bool) ? node.get_boolean () : key != "compactQuota" && key != "showHoverInfo" && key != "accountLegend";
        }

        private Json.Object read_values () throws Error {
            string data;
            try {
                FileUtils.get_contents (path, out data);
            } catch (FileError e) {
                if (e.code == FileError.NOENT) {
                    return new Json.Object ();
                }
                throw e;
            }
            var parser = new Json.Parser ();
            parser.load_from_data (data);
            var root = parser.get_root ();
            if (root == null || root.get_node_type () != Json.NodeType.OBJECT) {
                throw new IOError.INVALID_DATA ("Wingpanel preferences must be a JSON object");
            }
            return root.get_object ();
        }

        private string validation_error (Json.Object obj) {
            foreach (var key in KEYS) {
                var node = obj.get_member (key);
                if (node != null && node.get_value_type () != typeof (bool)) {
                    return "Wingpanel preference '%s' must be a boolean; using its default".printf (key);
                }
            }
            return "";
        }

        // Returns whether effective display values changed, not whether reading succeeded.
        // On parse/I/O failure retain the last good values; inspect last_error for failures.
        public bool load () {
            try {
                var next = read_values ();
                bool[] before = {};
                foreach (var key in KEYS) { before += get_bool (key); }
                values = next;
                last_error = validation_error (values);
                for (int i = 0; i < KEYS.length; i++) {
                    if (before[i] != get_bool (KEYS[i])) { return true; }
                }
            } catch (Error e) {
                last_error = "Couldn't read Wingpanel preferences: " + e.message;
            }
            return false;
        }

        // Re-read before patching so unrelated/unknown keys survive. Refuse to overwrite
        // corrupt files. Atomic replacement creates a private (0600) destination inode.
        public bool save_bool (string key, bool value) {
            last_error = "";
            if (!(key in KEYS)) {
                last_error = "Unknown Wingpanel preference: " + key;
                return false;
            }
            try {
                var next = read_values ();
                next.set_boolean_member (key, value);
                var root = new Json.Node (Json.NodeType.OBJECT);
                root.set_object (next);
                var generator = new Json.Generator ();
                generator.set_root (root);
                generator.pretty = true;
                var directory = File.new_for_path (Path.get_dirname (path));
                try {
                    directory.make_directory_with_parents ();
                } catch (IOError e) {
                    if (e.code != IOError.EXISTS) { throw e; }
                }
                string etag;
                File.new_for_path (path).replace_contents (generator.to_data (null).data, null, false,
                    FileCreateFlags.PRIVATE | FileCreateFlags.REPLACE_DESTINATION, out etag);
                values = next;
                last_error = validation_error (values);
                return true;
            } catch (Error e) {
                last_error = "Couldn't save Wingpanel preferences: " + e.message;
                return false;
            }
        }
    }
}
