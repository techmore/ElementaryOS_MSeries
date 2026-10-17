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
            if (plan.length == 0) return "";
            if (plan == "prolite") return "Pro Lite";
            return plan.substring (0, 1).up () + plan.substring (1);
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

        /* The one line under a limit: when it resets, plus the forecast only when it is a warning. */
        public static string window_caption (string reset, EtaState state, string eta_detail) {
            if (state == EtaState.EXHAUSTED) return eta_detail;
            var base_text = reset.length > 0 ? reset : "Reset time unknown";
            return state == EtaState.DEPLETING ? base_text + " · " + eta_detail : base_text;
        }
    }
}
