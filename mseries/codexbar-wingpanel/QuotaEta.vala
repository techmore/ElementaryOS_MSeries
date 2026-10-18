/* Present CodexBar's existing quota projections without inventing token balances. */
namespace MSeries {
    internal enum EtaState { UNKNOWN, STALE, EXHAUSTED, DEPLETING, SAFE }

    internal class QuotaEta : GLib.Object {
        public EtaState state = EtaState.UNKNOWN;
        public string detail = "ETA unavailable · more usage needed";
        public string compact = "ETA —";
        public int64 seconds = int64.MAX;
        public string window_label = "";
        public int window_minutes = 0;

        private static string text_member (Json.Object obj, string name) {
            var node = obj.get_member (name);
            return node != null && node.get_node_type () == Json.NodeType.VALUE &&
                node.get_value_type () == typeof (string) ? node.get_string () ?? "" : "";
        }

        private static int64 duration_seconds (string duration) {
            int64 total = 0;
            if (duration == "now") return 0;
            foreach (var part in duration.split (" ")) {
                if (part.length > 10 || !GLib.Regex.match_simple ("^[0-9]+[dhm]$", part)) return -1;
                var value = int64.parse (part.substring (0, part.length - 1));
                var unit = part[part.length - 1];
                total += value * (unit == 'd' ? 86400 : unit == 'h' ? 3600 : 60);
            }
            return total;
        }

        public static bool entry_stale (Json.Object entry, bool snapshot_stale, int64 now_unix) {
            var updated = text_member (entry, "updatedAt");
            var timestamp = new GLib.DateTime.from_iso8601 (updated, null);
            return snapshot_stale || text_member (entry, "error").length > 0 ||
                timestamp == null || now_unix - timestamp.to_unix () > 180 ||
                timestamp.to_unix () - now_unix > 60;
        }

        public static QuotaEta from_window (Json.Object window, bool stale = false, int64 now_unix = 0) {
            var eta = new QuotaEta ();
            eta.window_label = text_member (window, "label");
            var minutes = window.get_member ("minutes");
            if (minutes != null && minutes.get_node_type () == Json.NodeType.VALUE &&
                (minutes.get_value_type () == typeof (double) || minutes.get_value_type () == typeof (int64))) {
                eta.window_minutes = (int) minutes.get_int ();
            }
            if (stale) {
                eta.state = EtaState.STALE;
                eta.detail = "ETA unavailable · usage is out of date";
                return eta;
            }
            var reset = text_member (window, "resetsAt");
            var reset_time = new GLib.DateTime.from_iso8601 (reset, null);
            if (now_unix > 0 && reset_time != null && reset_time.to_unix () <= now_unix) {
                eta.detail = "ETA unavailable · awaiting quota refresh";
                return eta;
            }
            var remaining = window.get_member ("remaining");
            if (remaining == null || remaining.get_node_type () != Json.NodeType.VALUE ||
                (remaining.get_value_type () != typeof (double) && remaining.get_value_type () != typeof (int64))) return eta;
            var value = remaining.get_double ();
            if (!value.is_finite () || value < 0 || value > 100) return eta;
            if (value == 0) {
                eta.state = EtaState.EXHAUSTED;
                eta.seconds = 0;
                var reset_text = text_member (window, "resetText");
                eta.detail = "Quota exhausted" + (reset_text.length > 0 ? " · " + reset_text : " · reset unknown");
                eta.compact = reset_text.has_prefix ("Resets in ")
                    ? "reset " + reset_text.substring (10).replace (" ", "") : "exhausted";
                return eta;
            }
            var pace = text_member (window, "pace");
            foreach (var raw in pace.split ("|")) {
                var part = raw.strip ();
                if (part == "Lasts until reset") {
                    eta.state = EtaState.SAFE;
                    eta.detail = "Estimated to last until reset at this pace";
                    eta.compact = "until reset";
                    return eta;
                }
                string duration;
                if (part.has_prefix ("Projected empty in ")) duration = part.substring (19);
                else if (part.has_prefix ("Runs out in ")) duration = part.substring (12);
                else if (part == "Projected empty now" || part == "Runs out now") duration = "now";
                else continue;
                var seconds = duration_seconds (duration);
                if (seconds < 0) continue;
                eta.state = EtaState.DEPLETING;
                eta.seconds = seconds;
                eta.detail = duration == "now" ? "Estimated empty now at this pace"
                    : "Est. empty in ~" + duration + " at this pace";
                eta.compact = duration == "now" ? "~now" : "~" + duration.replace (" ", "");
                return eta;
            }
            return eta;
        }

        public static QuotaEta for_entry (Json.Object entry, bool stale, int64 now_unix) {
            var selected = new QuotaEta ();
            bool unknown = false;
            var windows = JsonBoundary.array (entry, "windows");
            if (windows == null) return selected;
            for (uint i = 0; i < windows.get_length (); i++) {
                var eta = from_window (windows.get_object_element (i), stale, now_unix);
                if (eta.state == EtaState.STALE || eta.state == EtaState.EXHAUSTED) return eta;
                if (eta.state == EtaState.UNKNOWN) unknown = true;
                else if (eta.state == EtaState.DEPLETING &&
                         (selected.state != EtaState.DEPLETING || eta.seconds < selected.seconds)) selected = eta;
                else if (eta.state == EtaState.SAFE && selected.state == EtaState.UNKNOWN) selected = eta;
            }
            // A safe measured window cannot vouch for another window with an unknown projection.
            if (unknown && selected.state == EtaState.SAFE) return new QuotaEta ();
            return selected;
        }
    }
}
