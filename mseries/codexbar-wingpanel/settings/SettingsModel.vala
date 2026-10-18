/* Settings for the CodexBar desktop app (linux.json), without any UI: defaults, validation and provider-list edits.
 * The app validates everything again when it receives --configure, so this only has to avoid sending nonsense. */
namespace MSeries {
    internal class SettingsModel : GLib.Object {
        public const int MAX_PROVIDERS = 80;
        public Json.Object values = new Json.Object ();

        public SettingsModel () {
            values.set_string_member ("provider", "codex");
            values.set_string_member ("source", "auto");
            values.set_int_member ("refreshSeconds", 300);
            values.set_int_member ("notifyThreshold", 10);
            values.set_int_member ("barProviders", 2);
            values.set_string_member ("quotaDisplay", "remaining");
            values.set_string_member ("resetDisplay", "countdown");
            values.set_string_member ("trayStyle", "meters");
            foreach (var key in new string[] { "showCosts", "showStatus", "showTray", "showPace" }) {
                values.set_boolean_member (key, true);
            }
            foreach (var key in new string[] { "notifications", "compactQuickView", "refreshOnOpen", "showBarDetail",
                "showScopedCaps", "warningColors", "allAccounts", "showIdentity", "followOmarchyTheme" }) {
                values.set_boolean_member (key, false);
            }
            values.set_array_member ("providerOrder", new Json.Array ());
        }

        /* Merge a linux.json document over the defaults; unknown or wrongly typed members are ignored. */
        public bool load_from_data (string text) {
            try {
                var parser = new Json.Parser ();
                parser.load_from_data (text, -1);
                var root = parser.get_root ();
                if (root == null || root.get_node_type () != Json.NodeType.OBJECT) {
                    return false;
                }
                root.get_object ().foreach_member ((object, name, node) => {
                    if (!values.has_member (name)) {
                        return;
                    }
                    var current = values.get_member (name);
                    if (node.get_node_type () == current.get_node_type () &&
                        (node.get_node_type () != Json.NodeType.VALUE || node.get_value_type () == current.get_value_type ())) {
                        values.set_member (name, node.copy ());
                    }
                });
                return true;
            } catch (Error e) {
                return false;
            }
        }

        public bool get_bool (string key) {
            return values.get_boolean_member_with_default (key, false);
        }

        public int get_int (string key) {
            return (int) values.get_int_member_with_default (key, 0);
        }

        public string get_string (string key) {
            return values.get_string_member_with_default (key, "");
        }

        public string[] providers () {
            var result = new string[0];
            var array = values.get_array_member ("providerOrder");
            for (uint i = 0; i < array.get_length (); i++) {
                result += array.get_string_element (i);
            }
            return result;
        }

        public static bool valid_provider_id (string id) {
            if (id.length < 1 || id.length > 80 || id in new string[] { "all", "both", "enabled", "custom" }) {
                return false;
            }
            for (int i = 0; i < id.length; i++) {
                var c = id[i];
                if (!((c >= 'a' && c <= 'z') || (c >= '0' && c <= '9') || c == '-')) {
                    return false;
                }
            }
            return true;
        }

        private void set_providers (string[] ids) {
            var array = new Json.Array ();
            foreach (var id in ids) {
                array.add_string_element (id);
            }
            values.set_array_member ("providerOrder", array);
            values.set_string_member ("provider", "custom");
        }

        public bool add_provider (string id) {
            var list = providers ();
            if (!valid_provider_id (id) || id in list || list.length >= MAX_PROVIDERS) {
                return false;
            }
            list += id;
            set_providers (list);
            return true;
        }

        /* Refuse to empty the list: the app rejects "custom" with no providers. */
        public bool remove_provider (string id) {
            var list = providers ();
            if (list.length <= 1) {
                return false;
            }
            var kept = new string[0];
            var found = false;
            foreach (var entry in list) {
                if (entry == id) {
                    found = true;
                } else {
                    kept += entry;
                }
            }
            if (found) {
                set_providers (kept);
            }
            return found;
        }

        public bool move_provider (string id, int direction) {
            var list = providers ();
            for (int i = 0; i < list.length; i++) {
                if (list[i] == id) {
                    var j = i + direction;
                    if (j < 0 || j >= list.length) {
                        return false;
                    }
                    var swap = list[j];
                    list[j] = list[i];
                    list[i] = swap;
                    set_providers (list);
                    return true;
                }
            }
            return false;
        }

        /* The --configure payload for a set of changed keys. */
        public string patch_for (string[] keys) {
            var patch = new Json.Object ();
            foreach (var key in keys) {
                if (values.has_member (key)) {
                    patch.set_member (key, values.get_member (key).copy ());
                }
            }
            var node = new Json.Node (Json.NodeType.OBJECT);
            node.set_object (patch);
            var generator = new Json.Generator ();
            generator.root = node;
            return generator.to_data (null);
        }
    }
}
