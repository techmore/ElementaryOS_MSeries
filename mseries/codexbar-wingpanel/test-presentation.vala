int main (string[] args) {
    GLib.Test.init (ref args);
    GLib.Test.add_func ("/presentation/level", () => {
        assert (MSeries.Presentation.level_for (-1) == MSeries.QuotaLevel.UNKNOWN);
        assert (MSeries.Presentation.level_for (0) == MSeries.QuotaLevel.CRITICAL);
        assert (MSeries.Presentation.level_for (10) == MSeries.QuotaLevel.CRITICAL);
        assert (MSeries.Presentation.level_for (10.5) == MSeries.QuotaLevel.LOW);
        assert (MSeries.Presentation.level_for (25) == MSeries.QuotaLevel.LOW);
        assert (MSeries.Presentation.level_for (25.5) == MSeries.QuotaLevel.OK);
        assert (MSeries.Presentation.level_for (100) == MSeries.QuotaLevel.OK);
    });
    GLib.Test.add_func ("/presentation/worst-level", () => {
        assert (MSeries.Presentation.worse (MSeries.QuotaLevel.OK, MSeries.QuotaLevel.LOW) == MSeries.QuotaLevel.LOW);
        assert (MSeries.Presentation.worse (MSeries.QuotaLevel.CRITICAL, MSeries.QuotaLevel.LOW) == MSeries.QuotaLevel.CRITICAL);
        // Unknown never hides a measured problem or invents one.
        assert (MSeries.Presentation.worse (MSeries.QuotaLevel.UNKNOWN, MSeries.QuotaLevel.OK) == MSeries.QuotaLevel.OK);
        assert (MSeries.Presentation.worse (MSeries.QuotaLevel.UNKNOWN, MSeries.QuotaLevel.UNKNOWN) == MSeries.QuotaLevel.UNKNOWN);
    });
    GLib.Test.add_func ("/presentation/window-labels", () => {
        assert (MSeries.Presentation.short_window_label ("5 hour", 300) == "5H");
        assert (MSeries.Presentation.short_window_label ("7 day", 10080) == "7D");
        assert (MSeries.Presentation.short_window_label ("Weekly", 0) == "7D");
        assert (MSeries.Presentation.short_window_label ("Monthly", 0) == "30D");
        assert (MSeries.Presentation.short_window_label ("Session", 0) == "Session");
    });
    GLib.Test.add_func ("/presentation/plan-label", () => {
        assert (MSeries.Presentation.plan_label ("prolite") == "Pro Lite");
        assert (MSeries.Presentation.plan_label ("pro") == "Pro");
        assert (MSeries.Presentation.plan_label ("max") == "Max");
        assert (MSeries.Presentation.plan_label ("") == "");
        assert (MSeries.Presentation.plan_label ("enterprise") == "Enterprise");
    });
    GLib.Test.add_func ("/presentation/age", () => {
        assert (MSeries.Presentation.age_text (-5) == "just now");
        assert (MSeries.Presentation.age_text (4) == "just now");
        assert (MSeries.Presentation.age_text (59) == "just now");
        assert (MSeries.Presentation.age_text (60) == "1 min ago");
        assert (MSeries.Presentation.age_text (150) == "2 min ago");
        assert (MSeries.Presentation.age_text (3600) == "1 h ago");
        assert (MSeries.Presentation.age_text (3 * 3600 + 120) == "3 h ago");
        assert (MSeries.Presentation.age_text (2 * 86400) == "2 d ago");
    });
    GLib.Test.add_func ("/presentation/bar-segment", () => {
        // Healthy or unknown pace stays quiet: just the percentage.
        assert (MSeries.Presentation.bar_segment ("72%", MSeries.EtaState.SAFE, "until reset", "5H") == "72%");
        assert (MSeries.Presentation.bar_segment ("72%", MSeries.EtaState.UNKNOWN, "ETA —", "") == "72%");
        assert (MSeries.Presentation.bar_segment ("72%", MSeries.EtaState.STALE, "ETA —", "") == "72%");
        // Only a real warning adds the limiting window and its ETA.
        assert (MSeries.Presentation.bar_segment ("18%", MSeries.EtaState.DEPLETING, "~1h10m", "5H") == "18% · 5H ~1h10m");
        assert (MSeries.Presentation.bar_segment ("0%", MSeries.EtaState.EXHAUSTED, "reset 19m", "5H") == "0% · 5H reset 19m");
        assert (MSeries.Presentation.bar_segment ("—", MSeries.EtaState.UNKNOWN, "ETA —", "") == "—");
    });
    GLib.Test.add_func ("/presentation/quota-lead", () => {
        // A session-length window needs no label; a longer one must say which limit the number is.
        assert (MSeries.Presentation.quota_lead ("5H", 300, "72%") == "72%");
        assert (MSeries.Presentation.quota_lead ("7D", 10080, "35%") == "7D 35%");
        assert (MSeries.Presentation.quota_lead ("Session", 0, "50%") == "50%");
        assert (MSeries.Presentation.quota_lead ("", 0, "—") == "—");
        assert (MSeries.Presentation.limiting_window ("7D", "7D") == "");
        assert (MSeries.Presentation.limiting_window ("5H", "7D") == "5H");
        assert (MSeries.Presentation.limiting_window ("5H", "") == "5H");
    });
    GLib.Test.add_func ("/presentation/caption", () => {
        assert (MSeries.Presentation.window_caption ("Resets in 3h 10m", MSeries.EtaState.SAFE, "Estimated to last until reset at this pace") == "Resets in 3h 10m");
        assert (MSeries.Presentation.window_caption ("Resets in 3h 10m", MSeries.EtaState.UNKNOWN, "ETA unavailable · more usage needed") == "Resets in 3h 10m");
        assert (MSeries.Presentation.window_caption ("Resets in 3h 10m", MSeries.EtaState.STALE, "ETA unavailable · usage is out of date") == "Resets in 3h 10m");
        assert (MSeries.Presentation.window_caption ("Resets in 3h 10m", MSeries.EtaState.DEPLETING, "Est. empty in ~1h 10m at this pace") == "Resets in 3h 10m · Est. empty in ~1h 10m at this pace");
        assert (MSeries.Presentation.window_caption ("Resets in 19m", MSeries.EtaState.EXHAUSTED, "Quota exhausted · Resets in 19m") == "Quota exhausted · Resets in 19m");
        assert (MSeries.Presentation.window_caption ("", MSeries.EtaState.UNKNOWN, "") == "Reset time unknown");
    });
    GLib.Test.add_func ("/presentation/counts", () => {
        assert (MSeries.Presentation.count_text (0) == "0");
        assert (MSeries.Presentation.count_text (999) == "999");
        assert (MSeries.Presentation.count_text (1500) == "2K");
        assert (MSeries.Presentation.count_text (1850000) == "1.9M");
        assert (MSeries.Presentation.count_text (1744010089) == "1.7B");
    });
    GLib.Test.add_func ("/presentation/local-usage", () => {
        assert (MSeries.Presentation.local_usage_line ("7 days", 14.719468, 565, 120813143) == "7 days · $14.72 · 565 requests · 120.8M tokens");
        assert (MSeries.Presentation.local_usage_line ("5 hours", 0, 1, 0) == "5 hours · $0.00 · 1 request · 0 tokens");
    });
    return GLib.Test.run ();
}
