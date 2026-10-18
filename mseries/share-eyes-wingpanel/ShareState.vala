/* Reads the file the screen-share launcher keeps up to date (it only exists while the launcher runs, mode 0600, in a 0700 dir).
 * Contract: $XDG_RUNTIME_DIR/rupert-share/state.json =
 *   {"live":bool,"viewers":int,"updated":unix_seconds,"port":int,"email":str,"password":str,"public_url":str}
 * A file not refreshed for STALE_SECS counts as "no launcher running", so a crashed launcher never leaves the eyes stuck on. */
namespace MSeries {
    public class ShareState : GLib.Object {
        public const int64 STALE_SECS = 15;
        public bool running { get; private set; default = false; }
        public bool live { get; private set; default = false; }
        public int viewers { get; private set; default = 0; }
        public int port { get; private set; default = 0; }
        public string email { get; private set; default = ""; }
        public string password { get; private set; default = ""; }
        public string public_url { get; private set; default = ""; }

        public static string default_path () {
            return GLib.Path.build_filename (GLib.Environment.get_user_runtime_dir (), "rupert-share", "state.json");
        }

        public string local_url { owned get { return "http://127.0.0.1:%d".printf (port); } }
        public string share_page { owned get { return local_url + "/share"; } }
        public string viewer_base { owned get { return public_url != "" ? public_url : local_url; } }

        /* Returns true when anything the indicator shows changed. */
        public bool parse (string? text, int64 now) {
            bool n_running = false, n_live = false;
            int n_viewers = 0, n_port = 0;
            string n_email = "", n_password = "", n_public = "";
            if (text != null) {
                try {
                    var parser = new Json.Parser ();
                    parser.load_from_data (text);
                    var root = parser.get_root ();
                    if (root != null && root.get_node_type () == Json.NodeType.OBJECT) {
                        var o = root.get_object ();
                        int64 updated = o.has_member ("updated") ? o.get_int_member ("updated") : 0;
                        if (now - updated <= STALE_SECS) {
                            n_running = true;
                            n_live = o.has_member ("live") && o.get_boolean_member ("live");
                            if (n_live && o.has_member ("viewers")) {
                                n_viewers = (int) o.get_int_member ("viewers").clamp (0, 99);
                            }
                            if (o.has_member ("port")) n_port = (int) o.get_int_member ("port");
                            if (o.has_member ("email")) n_email = o.get_string_member ("email");
                            if (o.has_member ("password")) n_password = o.get_string_member ("password");
                            if (o.has_member ("public_url")) n_public = o.get_string_member ("public_url");
                        }
                    }
                } catch (GLib.Error e) {
                    n_running = false;
                }
            }
            bool changed = n_running != running || n_live != live || n_viewers != viewers || n_port != port
                || n_email != email || n_password != password || n_public != public_url;
            running = n_running; live = n_live; viewers = n_viewers; port = n_port;
            email = n_email; password = n_password; public_url = n_public;
            return changed;
        }

        public string tooltip () {
            if (!running) {
                return "Screen share is not running";
            }
            if (!live) {
                return "Screen share ready · not sharing yet";
            }
            return viewers == 1 ? "Sharing your screen · 1 person watching"
                : viewers == 0 ? "Sharing your screen · nobody watching yet"
                : "Sharing your screen · %d people watching".printf (viewers);
        }

        /* Owner page with the login in the URL fragment (never sent to the server; the page clears it and signs in). */
        public string login_url () {
            return "%s#u=%s&p=%s".printf (share_page, GLib.Uri.escape_string (email, null, true), GLib.Uri.escape_string (password, null, true));
        }

        public string login_text () {
            return "Screen share (this computer)\nOpen: %s\nUsername: %s\nPassword: %s\n".printf (share_page, email, password);
        }
    }
}
