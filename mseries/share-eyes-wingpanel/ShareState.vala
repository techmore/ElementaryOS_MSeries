/* Reads the share-state file the screen-share launcher keeps up to date.
 * Contract: $XDG_RUNTIME_DIR/rupert-share/state.json = {"live":bool,"viewers":int,"updated":unix_seconds}.
 * A file not refreshed for STALE_SECS counts as "not sharing", so a crashed launcher never leaves eyes stuck on. */
namespace MSeries {
    public class ShareState : GLib.Object {
        public const int64 STALE_SECS = 15;
        public bool live { get; private set; default = false; }
        public int viewers { get; private set; default = 0; }

        public static string default_path () {
            return GLib.Path.build_filename (GLib.Environment.get_user_runtime_dir (), "rupert-share", "state.json");
        }

        /* Returns true when live/viewers changed. */
        public bool parse (string? text, int64 now) {
            bool new_live = false;
            int new_viewers = 0;
            if (text != null) {
                try {
                    var parser = new Json.Parser ();
                    parser.load_from_data (text);
                    var root = parser.get_root ();
                    if (root != null && root.get_node_type () == Json.NodeType.OBJECT) {
                        var o = root.get_object ();
                        int64 updated = o.has_member ("updated") ? o.get_int_member ("updated") : 0;
                        if (o.has_member ("live") && o.get_boolean_member ("live") && now - updated <= STALE_SECS) {
                            new_live = true;
                            if (o.has_member ("viewers")) {
                                new_viewers = (int) o.get_int_member ("viewers").clamp (0, 99);
                            }
                        }
                    }
                } catch (GLib.Error e) {
                    new_live = false;
                }
            }
            bool changed = new_live != live || new_viewers != viewers;
            live = new_live;
            viewers = new_viewers;
            return changed;
        }

        public string tooltip () {
            if (!live) {
                return "Not sharing your screen";
            }
            return viewers == 1 ? "Sharing your screen · 1 person watching"
                : viewers == 0 ? "Sharing your screen · nobody watching yet"
                : "Sharing your screen · %d people watching".printf (viewers);
        }
    }
}
