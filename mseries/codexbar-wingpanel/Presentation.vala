/* Pure presentation rules for the CodexBar indicator: what is worth showing, and how it is worded. */
namespace MSeries {
    internal enum QuotaLevel { UNKNOWN, OK, LOW, CRITICAL }

    internal class Presentation : GLib.Object {
        public static QuotaLevel level_for (double remaining) {
            if (remaining < 0) return QuotaLevel.UNKNOWN;
            if (remaining <= 10) return QuotaLevel.CRITICAL;
            if (remaining <= 25) return QuotaLevel.LOW;
            return QuotaLevel.OK;
        }

        /* The more urgent of two levels; UNKNOWN neither hides a measured problem nor invents one. */
        public static QuotaLevel worse (QuotaLevel a, QuotaLevel b) {
            if (a == QuotaLevel.UNKNOWN) return b;
            if (b == QuotaLevel.UNKNOWN) return a;
            return (int) a >= (int) b ? a : b;
        }

        public static string short_window_label (string label, int minutes) {
            var normalized = label.down ();
            if (normalized.contains ("hour") || minutes > 0 && minutes <= 360) {
                var hours = minutes > 0 ? (minutes + 30) / 60 : 5;
                return "%dH".printf (hours);
            }
            if (normalized.contains ("week")) return "7D";
            if (normalized.contains ("month")) return "30D";
            if (normalized.contains ("day") || minutes >= 1440) {
                var days = minutes > 0 ? (minutes + 720) / 1440 : 7;
                return "%dD".printf (days);
            }
            return label;
        }

        public static string plan_label (string plan) {
            var value = plan.strip ();
            if (value.length == 0 || value.down () == "unknown") return "";
            if (value.down () == "prolite") return "Pro Lite";
            if (value.down () == "go") return "Go";
            return value.substring (0, 1).up () + value.substring (1);
        }

        public static string age_text (int64 seconds) {
            if (seconds < 60) return "just now";
            if (seconds < 3600) return "%d min ago".printf ((int) (seconds / 60));
            if (seconds < 86400) return "%d h ago".printf ((int) (seconds / 3600));
            return "%d d ago".printf ((int) (seconds / 86400));
        }

        public static string count_text (int64 value) {
            if (value >= 1000000000) return "%.1fB".printf ((double) value / 1000000000.0);
            if (value >= 1000000) return "%.1fM".printf ((double) value / 1000000.0);
            if (value >= 1000) return "%.0fK".printf ((double) value / 1000.0);
            return value.to_string ();
        }

        /* count_text without the decimal once it adds nothing at panel density: "121M", "9.4M". */
        public static string panel_count_text (int64 value) {
            if (value >= 100000000 && value < 1000000000) return "%.0fM".printf ((double) value / 1000000.0);
            return count_text (value);
        }

        /* Label the bar number when its window isn't the short session limit, so "35%" is never ambiguous. */
        public static string quota_lead (string short_label, int minutes, string remaining_text) {
            return minutes > 360 && short_label.length > 0 ? short_label + " " + remaining_text : remaining_text;
        }

        /* Name the limiting window in a warning unless the bar already led with that window. */
        public static string limiting_window (string window, string lead_window) {
            return window == lead_window ? "" : window;
        }

        /* Healthy and unknown stay quiet; only a real warning adds the limiting window and its ETA. */
        public static string bar_segment (string remaining_text, EtaState state, string eta_compact, string window) {
            if (state == EtaState.DEPLETING || state == EtaState.EXHAUSTED) {
                return remaining_text + " · " + (window.length > 0 ? window + " " : "") + eta_compact;
            }
            return remaining_text;
        }

        /* Compact time to a reset for the panel: "38m", "4h44m", "6d22h"; empty when unknown or already due. */
        public static string countdown_text (int64 seconds) {
            if (seconds <= 0) return "";
            if (seconds < 3600) return "%dm".printf ((int) ((seconds + 59) / 60));
            if (seconds < 86400) return "%dh%02dm".printf ((int) (seconds / 3600), (int) (seconds % 3600 / 60));
            return "%dd%dh".printf ((int) (seconds / 86400), (int) (seconds % 86400 / 3600));
        }

        /* The window that will stop you first: lowest measured remaining; a tie keeps the earlier (shorter) one. */
        public static int binding_window (Json.Array windows) {
            int best = -1;
            double best_remaining = 0;
            for (uint i = 0; i < windows.get_length (); i++) {
                var node = windows.get_object_element (i).get_member ("remaining");
                if (node == null || node.get_node_type () != Json.NodeType.VALUE) continue;
                var remaining = node.get_double ();
                if (best < 0 || remaining < best_remaining) {
                    best = (int) i;
                    best_remaining = remaining;
                }
            }
            return best;
        }

        /* Saved accounts retain every window: a weekly balance must never hide an empty 5-hour limit. */
        public static string account_quota (Json.Array? windows, int64 now_unix, bool show_percent = true, bool show_reset = true) {
            if (!show_percent && !show_reset) return "";
            var parts = new StringBuilder ();
            for (uint i = 0; windows != null && i < windows.get_length (); i++) {
                var window = windows.get_object_element (i);
                var node = window.get_member ("remaining");
                if (node == null || node.get_node_type () != Json.NodeType.VALUE) continue;
                var minutes = (int) JsonBoundary.integer (window, "minutes", 0);
                var label = short_window_label (JsonBoundary.text (window, "label", "Quota"), minutes);
                var reset = new DateTime.from_iso8601 (JsonBoundary.text (window, "resetsAt", ""), null);
                var eta = reset == null ? "?" : reset.to_unix () <= now_unix ? "now"
                    : countdown_text (reset.to_unix () - now_unix);
                if (parts.len > 0) parts.append (" · ");
                parts.append (label);
                if (show_percent) parts.append (" %.0f%%".printf (node.get_double ().clamp (0, 100)));
                if (show_reset) parts.append (" ↻" + eta);
            }
            return parts.len > 0 ? parts.str : "Quota unavailable";
        }

        public static string account_quota_markup (Json.Array? windows, int64 now_unix,
                                                    string healthy, string low, string critical, bool show_percent = true, bool show_reset = true) {
            if (!show_percent && !show_reset) return "";
            var text = new StringBuilder ();
            for (uint i = 0; windows != null && i < windows.get_length (); i++) {
                var window = windows.get_object_element (i);
                var remaining = window.get_member ("remaining");
                if (remaining == null || remaining.get_node_type () != Json.NodeType.VALUE) continue;
                var single = new Json.Array ();
                single.add_object_element (window.ref ());
                var parts = account_quota (single, now_unix, show_percent, show_reset).split (" ↻", 2);
                var level = level_for (remaining.get_double ());
                var color = level == QuotaLevel.CRITICAL ? critical : level == QuotaLevel.LOW ? low : healthy;
                if (text.len > 0) text.append (" · ");
                text.append (color.length > 0
                    ? "<span foreground=\"%s\" weight=\"semibold\">%s</span>".printf (color, Markup.escape_text (parts[0]))
                    : "<span weight=\"semibold\">%s</span>".printf (Markup.escape_text (parts[0])));
                if (parts.length > 1) text.append ("<span alpha=\"65%\"> ↻%s</span>".printf (Markup.escape_text (parts[1])));
            }
            return text.len > 0 ? text.str : "Quota unavailable";
        }

        /* Percent of quota is the only comparable unit supplied by these providers.
         * The lowest window is usable headroom: 0% session + 90% weekly cannot win.
         * Unknown/expired windows and stale accounts never earn a recommendation. */
        public static double account_headroom (Json.Array? windows, int64 now_unix) {
            double lowest = 101;
            for (uint i = 0; windows != null && i < windows.get_length (); i++) {
                var window = windows.get_object_element (i);
                var node = window.get_member ("remaining");
                if (node == null || node.get_node_type () != Json.NodeType.VALUE) return -1;
                var remaining = node.get_double ();
                if (remaining < 0 || remaining > 100 || remaining.is_nan ()) return -1;
                var reset = new DateTime.from_iso8601 (JsonBoundary.text (window, "resetsAt", ""), null);
                if (reset != null && reset.to_unix () <= now_unix) return -1;
                lowest = double.min (lowest, remaining);
            }
            return lowest <= 100 ? lowest : -1;
        }

        public static int64 account_weekly_reset (Json.Array? windows, int64 now_unix) {
            int64 earliest = 0;
            for (uint i = 0; windows != null && i < windows.get_length (); i++) {
                var window = windows.get_object_element (i);
                var minutes = JsonBoundary.integer (window, "minutes", 0);
                var label = JsonBoundary.text (window, "label", "").down ();
                if (minutes != 10080 && !(minutes == 0 && (label.contains ("week")
                    || label == "7d" || label.has_prefix ("7 day")))) continue;
                var reset = new DateTime.from_iso8601 (JsonBoundary.text (window, "resetsAt", ""), null);
                if (reset != null && reset.to_unix () > now_unix && (earliest == 0 || reset.to_unix () < earliest)) {
                    earliest = reset.to_unix ();
                }
            }
            return earliest;
        }

        public static Json.Object account_hints (Json.Array accounts, int64 now_unix) {
            var best = new Json.Array ();
            var weekly = new Json.Array ();
            double highest = 0;
            int64 soonest = 0;
            for (uint i = 0; i < accounts.get_length (); i++) {
                var account = accounts.get_object_element (i);
                if (JsonBoundary.flag (account, "stale", false)) continue;
                var id = JsonBoundary.text (account, "id", "");
                if (id.length == 0) continue;
                var windows = account.has_member ("windows") ? JsonBoundary.array (account, "windows") : null;
                var remaining = account_headroom (windows, now_unix);
                if (remaining > 0 && remaining >= highest) {
                    if (remaining > highest) best = new Json.Array ();
                    highest = remaining;
                    best.add_string_element (id);
                }
                var reset = account_weekly_reset (windows, now_unix);
                if (reset > 0 && (soonest == 0 || reset <= soonest)) {
                    if (soonest == 0 || reset < soonest) weekly = new Json.Array ();
                    soonest = reset;
                    weekly.add_string_element (id);
                }
            }
            var hints = new Json.Object ();
            hints.set_array_member ("best", best);
            hints.set_array_member ("weekly", weekly);
            return hints;
        }

        /* One line of local OpenCode Go activity: an estimate from this machine's history, not account quota. */
        public static string local_usage_line (string label, double cost_usd, int64 requests, int64 tokens) {
            return "%s · $%.2f · %s %s · %s tokens".printf (label, cost_usd, count_text (requests),
                requests == 1 ? "request" : "requests", count_text (tokens));
        }

        /* The one line under a limit: when it resets, plus the forecast only when it is a warning. */
        public static string window_caption (string reset, EtaState state, string eta_detail) {
            if (state == EtaState.EXHAUSTED) return eta_detail;
            var base_text = reset.length > 0 ? reset : "Reset time unknown";
            return state == EtaState.DEPLETING ? base_text + " · " + eta_detail : base_text;
        }

        /* "2 resets" for an account line; empty when the count is unknown. */
        public static string reset_count_text (int64 available) {
            if (available < 0) return "";
            return "%s %s".printf (available.to_string (), available == 1 ? "reset" : "resets");
        }

        /* "2 resets available · first expires in 3d4h"; the expiry is dropped when unknown or past. */
        public static string reset_credits_line (int64 available, int64 seconds_to_expiry) {
            if (available < 0) return "";
            var text = "%s available".printf (reset_count_text (available));
            var countdown = countdown_text (seconds_to_expiry);
            return available > 0 && countdown.length > 0 ? text + " · first expires in " + countdown : text;
        }

        /* One-row form for a header or account line: "2 resets · exp 3d4h"; the full sentence goes in the tooltip. */
        public static string reset_credits_chip (int64 available, int64 seconds_to_expiry) {
            var count = reset_count_text (available);
            var countdown = countdown_text (seconds_to_expiry);
            return available > 0 && countdown.length > 0 ? count + " · exp " + countdown : count;
        }

        /* Within a day of the first reset expiring, use it or lose it. */
        public static bool reset_expiry_urgent (int64 available, int64 seconds_to_expiry) {
            return available > 0 && seconds_to_expiry > 0 && seconds_to_expiry < 86400;
        }
    }
}
