/* Talks to the local screen-share server as its owner (cookie session, same CSRF header the owner page sends). */
namespace MSeries {
    public class ViewerInfo : GLib.Object {
        public string vid = "";
        public string state = "";
        public string ip = "";
    }

    public class ShareClient : GLib.Object {
        private Soup.Session session = new Soup.Session () { timeout = 4 };
        private bool logged_in = false;
        public string base_url = "";
        public string email = "";
        public string password = "";
        public ViewerInfo[] viewers = {};
        public bool live = false;
        public bool reachable = false;
        public int link_count = 0;
        public bool link_auto = false;
        public string? link_id = null;
        public string? link_token = null;
        public int64 link_expires = 0;

        construct {
            session.add_feature (new Soup.CookieJar ());
        }

        public void configure (string url, string mail, string pw) {
            if (url != base_url || mail != email || pw != password) {
                logged_in = false;
                link_id = null;
                link_token = null;
            }
            base_url = url; email = mail; password = pw;
        }

        private async Json.Object? call (string method, string path, string? body, bool retry = true) {
            if (base_url == "") return null;
            var msg = new Soup.Message (method, base_url + path);
            msg.request_headers.append ("x-rupert-share", "1");
            if (body != null) {
                msg.set_request_body_from_bytes ("application/json", new GLib.Bytes (body.data));
            }
            try {
                var bytes = yield session.send_and_read_async (msg, GLib.Priority.DEFAULT, null);
                if (msg.status_code == 401 && retry && path != "/auth/login") {
                    logged_in = false;
                    if (yield login ()) return yield call (method, path, body, false);
                    return null;
                }
                if (msg.status_code < 200 || msg.status_code >= 300) return null;
                var text = (string) bytes.get_data ();
                var parser = new Json.Parser ();
                parser.load_from_data (text != null && text.length > 0 ? text : "{}");
                var root = parser.get_root ();
                return root != null && root.get_node_type () == Json.NodeType.OBJECT ? root.get_object ().ref () : new Json.Object ();
            } catch (GLib.Error e) {
                return null;
            }
        }

        private async bool login () {
            var b = new Json.Builder ();
            b.begin_object ().set_member_name ("email").add_string_value (email)
             .set_member_name ("password").add_string_value (password).end_object ();
            var gen = new Json.Generator ();
            gen.root = b.get_root ();
            var r = yield call ("POST", "/auth/login", gen.to_data (null), false);
            logged_in = r != null;
            return logged_in;
        }

        /* Fetch /status; returns true when what the popover shows changed. */
        public async bool refresh () {
            if (!logged_in && !(yield login ())) {
                bool changed = reachable;
                reachable = false; viewers = {}; live = false;
                return changed;
            }
            var s = yield call ("GET", "/api/v1/share/status", null);
            if (s == null) {
                bool changed = reachable;
                reachable = false; viewers = {}; live = false;
                return changed;
            }
            var before = digest ();
            reachable = true;
            live = s.has_member ("live") && s.get_boolean_member ("live");
            ViewerInfo[] vs = {};
            if (s.has_member ("viewers")) {
                s.get_array_member ("viewers").foreach_element ((a, i, n) => {
                    var o = n.get_object ();
                    var v = new ViewerInfo ();
                    v.vid = o.get_string_member ("vid");
                    v.state = o.get_string_member ("state");
                    v.ip = o.has_member ("ip") ? o.get_string_member ("ip") : "";
                    vs += v;
                });
            }
            viewers = vs;
            bool link_alive = false;
            link_count = s.has_member ("links") ? (int) s.get_array_member ("links").get_length () : 0;
            if (s.has_member ("links")) {
                s.get_array_member ("links").foreach_element ((a, i, n) => {
                    var o = n.get_object ();
                    if (link_id != null && o.get_string_member ("id") == link_id) {
                        link_alive = true;
                        link_auto = o.has_member ("auto_admit") && o.get_boolean_member ("auto_admit");
                        link_expires = o.get_int_member ("expires_at");
                    }
                });
            }
            if (!link_alive) { link_id = null; link_token = null; }
            return before != digest ();
        }

        public string digest () {
            var sb = new StringBuilder ();
            sb.append ("%s|%s|%s|%d|".printf (reachable.to_string (), live.to_string (), link_id ?? "", link_count));
            foreach (var v in viewers) sb.append ("%s:%s;".printf (v.vid, v.state));
            return sb.str;
        }

        public string? viewer_link (string base_for_viewers) {
            return link_token == null ? null : base_for_viewers + "/v/" + link_token;
        }

        public async bool create_link (bool auto_admit = false) {
            var r = yield call ("POST", "/api/v1/share/links", auto_admit ? "{\"auto_admit\":true}" : "{}");
            if (r == null || !r.has_member ("token")) return false;
            link_id = r.get_string_member ("id");
            link_token = r.get_string_member ("token");
            yield refresh ();
            return true;
        }

        public async void viewer_action (string vid, string action) {
            yield call ("POST", "/api/v1/share/viewers/" + GLib.Uri.escape_string (vid, null, true) + "/" + action, "{}");
            yield refresh ();
        }

        public async void stop () {
            yield call ("POST", "/api/v1/share/stop", "{}");
            yield refresh ();
        }
    }
}
