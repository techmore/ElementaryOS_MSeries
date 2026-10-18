// Validate external JSON before it reaches the in-process Wingpanel renderer.
// Unknown fields are allowed for forward compatibility. Bound work and recursion too.
namespace MSeries {
    internal class JsonBoundary : Object {
        private static Json.Node? member (Json.Object obj, string key) {
            return obj.has_member (key) ? obj.get_member (key) : null;
        }
        public static string text (Json.Object obj, string key, string fallback = "") {
            var node = member (obj, key);
            return node != null && node.get_value_type () == typeof (string) ? node.get_string () : fallback;
        }
        public static bool flag (Json.Object obj, string key, bool fallback = false) {
            var node = member (obj, key);
            return node != null && node.get_value_type () == typeof (bool) ? node.get_boolean () : fallback;
        }
        public static int64 integer (Json.Object obj, string key, int64 fallback = 0) {
            var node = member (obj, key);
            return node != null && (node.get_value_type () == typeof (int64) || node.get_value_type () == typeof (double))
                ? node.get_int () : fallback;
        }
        public static double number (Json.Object obj, string key, double fallback = 0) {
            var node = member (obj, key);
            return node != null && (node.get_value_type () == typeof (int64) || node.get_value_type () == typeof (double))
                ? node.get_double () : fallback;
        }
        public static unowned Json.Array? array (Json.Object obj, string key) {
            var node = member (obj, key);
            return node != null && node.get_node_type () == Json.NodeType.ARRAY ? node.get_array () : null;
        }
        public static unowned Json.Object? object_member (Json.Object obj, string key) {
            var node = member (obj, key);
            return node != null && node.get_node_type () == Json.NodeType.OBJECT ? node.get_object () : null;
        }

        public static void validate (Json.Node? root) throws GLib.IOError {
            if (root == null || root.get_node_type () != Json.NodeType.OBJECT)
                throw new GLib.IOError.INVALID_DATA ("Expected a JSON object");
            uint budget = 20000;
            walk (root, 0, ref budget);
        }

        private static void walk (Json.Node node, uint depth, ref uint budget) throws GLib.IOError {
            if (depth > 24 || budget == 0)
                throw new GLib.IOError.INVALID_DATA ("Usage data exceeds panel limits");
            budget--;
            if (node.get_node_type () == Json.NodeType.ARRAY) {
                var elements = node.get_array ();
                for (uint i = 0; i < elements.get_length (); i++)
                    walk (elements.get_element (i), depth + 1, ref budget);
                return;
            }
            if (node.get_node_type () != Json.NodeType.OBJECT) return;
            var obj = node.get_object ();
            foreach (var key in obj.get_members ()) {
                var value = obj.get_member (key);
                // Nullable optional values are used by upstream (e.g. remaining).
                if (value.is_null ()) {
                    walk (value, depth + 1, ref budget);
                    continue;
                }
                bool valid = true;
                switch (key) {
                    case "accountEmail":
                    case "activeEmail":
                    case "activePlan":
                    case "desktopNote":
                    case "desktopSnapshotError":
                    case "detail":
                    case "email":
                    case "error":
                    case "id":
                    case "key":
                    case "label":
                    case "message":
                    case "name":
                    case "nextExpiresAt":
                    case "note":
                    case "pace":
                    case "plan":
                    case "planSource":
                    case "provider":
                    case "resetText":
                    case "resetsAt":
                    case "state":
                    case "status":
                    case "statusLevel":
                    case "updatedAt":
                    case "workspace":
                        valid = value.get_value_type () == typeof (string);
                        break;
                    case "minutes":
                    case "number":
                    case "requests":
                    case "tokens":
                        valid = value.get_value_type () == typeof (int64) || value.get_value_type () == typeof (double);
                        break;
                    case "remaining":
                    case "costUSD":
                    case "month":
                    case "today":
                        valid = value.get_value_type () == typeof (int64) || value.get_value_type () == typeof (double);
                        break;
                    case "active":
                    case "busy":
                    case "desktopActive":
                    case "desktopReady":
                    case "differs":
                    case "installed":
                    case "ok":
                    case "stale":
                    case "switchable":
                        valid = value.get_value_type () == typeof (bool);
                        break;
                    case "accounts":
                    case "entries":
                    case "periods":
                    case "sessions":
                    case "spending":
                    case "windows":
                        valid = value.get_node_type () == Json.NodeType.ARRAY;
                        break;
                    case "desktop":
                    case "resetCredits":
                        valid = value.get_node_type () == Json.NodeType.OBJECT;
                        break;
                }
                if (!valid) throw new GLib.IOError.INVALID_DATA ("Invalid usage field: " + key);
                if (value.get_node_type () == Json.NodeType.ARRAY) {
                    var array = value.get_array ();
                    for (uint i = 0; i < array.get_length (); i++) {
                        var child = array.get_element (i);
                        // Every external collection rendered by the panel contains objects.
                        if (key == "accounts" || key == "entries" || key == "periods"
                            || key == "sessions" || key == "spending" || key == "windows") {
                            if (child.get_node_type () != Json.NodeType.OBJECT)
                                throw new GLib.IOError.INVALID_DATA ("Invalid usage collection: " + key);
                        }
                    }
                }
                walk (value, depth + 1, ref budget);
            }
        }
    }
}
