/* SPDX-License-Identifier: GPL-3.0-or-later
 * Remote Desktop: status model and presentation. No toolkit or bus code lives
 * here, so the wording and state rules are unit-tested. */
namespace MSeries.Remote {
    public enum Phase {
        /* The service answered but sharing is switched off. */
        OFF,
        IDLE,
        PENDING,
        ACTIVE,
        /* The viewer dropped; the session is held briefly for a reconnect. */
        GRACE,
        /* The background service cannot be reached. */
        UNAVAILABLE
    }

    public class PendingRequest : Object {
        public string id { get; set; default = ""; }
        public string device { get; set; default = ""; }
        public bool control_offered { get; set; }
        public int64 requested_ms { get; set; }
        public int64 expires_ms { get; set; }
    }

    public class SessionInfo : Object {
        public string id { get; set; default = ""; }
        public string device { get; set; default = ""; }
        public bool control { get; set; }
        public bool control_permitted { get; set; }
        public bool connected { get; set; }
    }

    public class Link : Object {
        public string label { get; set; default = ""; }
        public string url { get; set; default = ""; }
    }

    public class Invite : Object {
        public Link[] links = {};
        /* QR rows of '0'/'1'. */
        public string[] qr = {};
        public int64 expires_ms { get; set; }
        public bool control_offered { get; set; }

        public static Invite? parse (string json) {
            var parser = new Json.Parser ();
            try {
                parser.load_from_data (json);
            } catch (Error e) {
                return null;
            }
            var root = parser.get_root ();
            if (root == null || root.get_node_type () != Json.NodeType.OBJECT) return null;
            var o = root.get_object ();
            var invite = new Invite () {
                expires_ms = o.get_int_member_with_default ("expires_ms", 0),
                control_offered = o.get_boolean_member_with_default ("control_offered", false)
            };
            Link[] parsed_links = {};
            var links = o.get_array_member ("links");
            if (links != null) {
                foreach (var node in links.get_elements ()) {
                    var lo = node.get_object ();
                    if (lo == null) continue;
                    parsed_links += new Link () {
                        label = lo.get_string_member_with_default ("label", ""),
                        url = lo.get_string_member_with_default ("url", "")
                    };
                }
            }
            string[] rows = {};
            var qr = o.get_array_member ("qr");
            if (qr != null) {
                foreach (var node in qr.get_elements ()) rows += node.get_string ();
            }
            invite.links = parsed_links;
            invite.qr = rows;
            return invite;
        }
    }

    public class Status : Object {
        public Phase phase { get; set; default = Phase.UNAVAILABLE; }
        public bool enabled { get; set; }
        public string? listen { get; set; default = null; }
        public string backend { get; set; default = ""; }
        public PendingRequest? pending { get; set; default = null; }
        public SessionInfo? session { get; set; default = null; }
        public int64 grace_until_ms { get; set; }
        public int invites_pending { get; set; }

        public static Status unavailable () {
            return new Status ();
        }

        public static Status? parse (string json) {
            var parser = new Json.Parser ();
            try {
                parser.load_from_data (json);
            } catch (Error e) {
                return null;
            }
            var root = parser.get_root ();
            if (root == null || root.get_node_type () != Json.NodeType.OBJECT) return null;
            var o = root.get_object ();
            var s = new Status ();
            s.enabled = o.get_boolean_member_with_default ("enabled", false);
            s.backend = o.get_string_member_with_default ("backend", "");
            s.listen = o.get_null_member ("listen") || !o.has_member ("listen") ? null : o.get_string_member ("listen");
            s.invites_pending = (int) o.get_int_member_with_default ("invites_pending", 0);
            s.grace_until_ms = o.get_null_member ("grace_until_ms") ? 0 : o.get_int_member_with_default ("grace_until_ms", 0);
            if (o.has_member ("pending") && !o.get_null_member ("pending")) {
                var p = o.get_object_member ("pending");
                s.pending = new PendingRequest () {
                    id = p.get_string_member_with_default ("id", ""),
                    device = p.get_string_member_with_default ("device", ""),
                    control_offered = p.get_boolean_member_with_default ("control_offered", false),
                    requested_ms = p.get_int_member_with_default ("requested_ms", 0),
                    expires_ms = p.get_int_member_with_default ("expires_ms", 0)
                };
            }
            if (o.has_member ("session") && !o.get_null_member ("session")) {
                var x = o.get_object_member ("session");
                s.session = new SessionInfo () {
                    id = x.get_string_member_with_default ("id", ""),
                    device = x.get_string_member_with_default ("device", ""),
                    control = x.get_boolean_member_with_default ("control", false),
                    control_permitted = x.get_boolean_member_with_default ("control_permitted", false),
                    connected = x.get_boolean_member_with_default ("connected", false)
                };
            }
            switch (o.get_string_member_with_default ("phase", "idle")) {
                case "pending": s.phase = Phase.PENDING; break;
                case "active": s.phase = Phase.ACTIVE; break;
                case "grace": s.phase = Phase.GRACE; break;
                default: s.phase = s.enabled ? Phase.IDLE : Phase.OFF; break;
            }
            if (!s.enabled && s.phase == Phase.IDLE) s.phase = Phase.OFF;
            return s;
        }
    }

    /* Wording and indicator rules shared by the app, the panel indicator and the taskbar. */
    namespace Presentation {
        /* The indicator is visible whenever anything could be shared or is being shared. */
        public bool indicator_visible (Status s) {
            return s.phase != Phase.OFF && s.phase != Phase.UNAVAILABLE;
        }

        /* A session is on screen: the person at the desktop must be able to see it at a glance. */
        public bool sharing_now (Status s) {
            return s.phase == Phase.ACTIVE || s.phase == Phase.GRACE;
        }

        public string icon_name (Status s) {
            return sharing_now (s) ? "mseries-remote-sharing-symbolic" : "mseries-remote-symbolic";
        }

        public string title (Status s) {
            switch (s.phase) {
                case Phase.UNAVAILABLE: return _("Remote access isn't running");
                case Phase.OFF: return _("Remote access is off");
                case Phase.IDLE: return _("Ready for a phone");
                case Phase.PENDING:
                    return _("“%s” wants to connect").printf (device_name (s));
                case Phase.ACTIVE:
                    return s.session != null && s.session.control
                        ? _("“%s” is controlling this computer").printf (device_name (s))
                        : _("“%s” is viewing this computer").printf (device_name (s));
                case Phase.GRACE:
                    return _("Waiting for “%s” to reconnect").printf (device_name (s));
            }
            return "";
        }

        public string detail (Status s) {
            switch (s.phase) {
                case Phase.UNAVAILABLE:
                    return _("The background service could not be reached.");
                case Phase.OFF:
                    return _("Nobody can connect. Turn it on to let your phone ask for access.");
                case Phase.IDLE:
                    return _("Create a link to connect. Nothing is shared until you approve it here.");
                case Phase.PENDING:
                    return _("It will see your whole screen. Nothing is recorded.");
                case Phase.ACTIVE:
                    return _("Your screen is being shared. Nothing is recorded.");
                case Phase.GRACE:
                    return _("The connection dropped. The session ends by itself if the phone doesn't return.");
            }
            return "";
        }

        public string device_name (Status s) {
            if (s.session != null && s.session.device != "") return s.session.device;
            if (s.pending != null && s.pending.device != "") return s.pending.device;
            return _("Unknown device");
        }

        /* Short text for a tooltip or compact readout. */
        public string tooltip (Status s) {
            switch (s.phase) {
                case Phase.ACTIVE:
                case Phase.GRACE:
                case Phase.PENDING:
                    return title (s);
                default:
                    return _("Remote Desktop") + " — " + title (s);
            }
        }

        /* "4:32" style countdown; never negative. */
        public string countdown (int64 ms_left) {
            int64 total = ms_left < 0 ? 0 : (ms_left + 999) / 1000;
            return "%d:%02d".printf ((int) (total / 60), (int) (total % 60));
        }
    }
}
