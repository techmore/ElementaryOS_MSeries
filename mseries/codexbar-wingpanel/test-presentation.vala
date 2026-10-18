Json.Object hint_account (string id, double session, double weekly, string weekly_reset, bool stale = false) {
    var account = new Json.Object ();
    account.set_string_member ("id", id);
    account.set_boolean_member ("stale", stale);
    var windows = new Json.Array ();
    var short_window = new Json.Object ();
    short_window.set_string_member ("label", "5 hour");
    short_window.set_int_member ("minutes", 300);
    short_window.set_double_member ("remaining", session);
    short_window.set_string_member ("resetsAt", "2026-10-18T12:05:00Z");
    windows.add_object_element (short_window);
    var long_window = new Json.Object ();
    long_window.set_string_member ("label", "7 day");
    long_window.set_int_member ("minutes", 10080);
    long_window.set_double_member ("remaining", weekly);
    long_window.set_string_member ("resetsAt", weekly_reset);
    windows.add_object_element (long_window);
    account.set_array_member ("windows", windows);
    return account;
}

int main (string[] args) {
    GLib.Test.init (ref args);
    GLib.Test.add_func ("/presentation/account-hints-usable-headroom", () => {
        var now = new DateTime.from_iso8601 ("2026-10-18T12:00:00Z", null).to_unix ();
        var accounts = new Json.Array ();
        accounts.add_object_element (hint_account ("exhausted-session", 0, 99, "2026-10-18T12:30:00Z"));
        accounts.add_object_element (hint_account ("limited-weekly", 95, 20, "2026-10-19T12:00:00Z"));
        accounts.add_object_element (hint_account ("saved-best", 80, 75, "2026-10-20T12:00:00Z"));
        accounts.add_object_element (hint_account ("stale", 100, 100, "2026-10-18T12:01:00Z", true));
        var hints = MSeries.Presentation.account_hints (accounts, now);
        assert (hints.get_array_member ("best").get_length () == 1);
        assert (hints.get_array_member ("best").get_string_element (0) == "saved-best");
        assert (hints.get_array_member ("weekly").get_length () == 1);
        assert (hints.get_array_member ("weekly").get_string_element (0) == "exhausted-session");
    });
    GLib.Test.add_func ("/presentation/account-hints-ties-and-expired", () => {
        var now = new DateTime.from_iso8601 ("2026-10-18T12:00:00Z", null).to_unix ();
        var accounts = new Json.Array ();
        accounts.add_object_element (hint_account ("a", 75, 80, "2026-10-19T12:00:00Z"));
        accounts.add_object_element (hint_account ("b", 80, 75, "2026-10-19T12:00:00Z"));
        accounts.add_object_element (hint_account ("past", 100, 100, "2026-10-18T11:59:00Z"));
        var hints = MSeries.Presentation.account_hints (accounts, now);
        assert (hints.get_array_member ("best").get_length () == 2);
        assert (hints.get_array_member ("weekly").get_length () == 2);
        // The five-hour resets at 12:05 do not change the 7-day reset selection.
        hints = MSeries.Presentation.account_hints (accounts, now + 300);
        assert (hints.get_array_member ("best").get_length () == 0);
        assert (hints.get_array_member ("weekly").get_length () == 2);
    });
    GLib.Test.add_func ("/presentation/account-hints-unknown-monthly-zero", () => {
        var now = new DateTime.from_iso8601 ("2026-10-18T12:00:00Z", null).to_unix ();
        var accounts = new Json.Array ();
        var zero = hint_account ("zero", 0, 0, "2026-10-19T12:00:00Z");
        accounts.add_object_element (zero);
        var unknown = hint_account ("unknown", 99, 99, "bad timestamp");
        unknown.get_array_member ("windows").get_object_element (0).set_null_member ("remaining");
        accounts.add_object_element (unknown);
        var monthly = hint_account ("monthly", 0, 0, "2026-10-18T12:01:00Z");
        var window = monthly.get_array_member ("windows").get_object_element (1);
        window.set_int_member ("minutes", 43200);
        window.set_string_member ("label", "30 day");
        accounts.add_object_element (monthly);
        var hints = MSeries.Presentation.account_hints (accounts, now);
        assert (hints.get_array_member ("best").get_length () == 0);
        assert (hints.get_array_member ("weekly").get_length () == 1);
        assert (hints.get_array_member ("weekly").get_string_element (0) == "zero");
        // A monthly label with no duration metadata must not fall back to "7D".
        window.set_int_member ("minutes", 0);
        hints = MSeries.Presentation.account_hints (accounts, now);
        assert (hints.get_array_member ("weekly").get_length () == 1);
        assert (hints.get_array_member ("weekly").get_string_element (0) == "zero");
        assert (MSeries.Presentation.account_headroom (null, now) < 0);
    });
    GLib.Test.add_func ("/presentation/level", () => {
        assert (MSeries.Presentation.level_for (-1) == MSeries.QuotaLevel.UNKNOWN);
        assert (MSeries.Presentation.level_for (0) == MSeries.QuotaLevel.CRITICAL);
        assert (MSeries.Presentation.level_for (10) == MSeries.QuotaLevel.CRITICAL);
        assert (MSeries.Presentation.level_for (10.5) == MSeries.QuotaLevel.LOW);
        assert (MSeries.Presentation.level_for (25) == MSeries.QuotaLevel.LOW);
        assert (MSeries.Presentation.level_for (25.5) == MSeries.QuotaLevel.OK);
        assert (MSeries.Presentation.level_for (100) == MSeries.QuotaLevel.OK);
    });
    GLib.Test.add_func ("/presentation/alternate-account-windows", () => {
        var parser = new Json.Parser ();
        try {
            parser.load_from_data ("[{\"label\":\"5 hour\",\"minutes\":300,\"remaining\":0,\"resetsAt\":\"2026-10-18T13:30:00Z\"},{\"label\":\"7 day\",\"minutes\":10080,\"remaining\":72,\"resetsAt\":\"2026-10-20T12:00:00Z\"},{\"label\":\"30 day\",\"minutes\":43200,\"remaining\":91}]");
        } catch (Error e) { assert_not_reached (); }
        var now = new DateTime.from_iso8601 ("2026-10-18T12:00:00Z", null).to_unix ();
        assert (MSeries.Presentation.account_quota (parser.get_root ().get_array (), now)
            == "5H 0% ↻1h30m · 7D 72% ↻2d0h · 30D 91% ↻?");
        assert (MSeries.Presentation.account_quota (parser.get_root ().get_array (), now + 5400)
            .has_prefix ("5H 0% ↻now"));
        assert (MSeries.Presentation.account_quota (null, now) == "Quota unavailable");
        var colored = MSeries.Presentation.account_quota_markup (parser.get_root ().get_array (), now,
            "#00aa00", "#ffaa00", "#ff0000");
        assert (colored.contains ("foreground=\"#ff0000\" weight=\"semibold\">5H 0%"));
        assert (colored.contains ("foreground=\"#00aa00\" weight=\"semibold\">7D 72%"));
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
    GLib.Test.add_func ("/presentation/reset-credits", () => {
        assert (MSeries.Presentation.reset_count_text (-1) == "");
        assert (MSeries.Presentation.reset_count_text (1) == "1 reset");
        assert (MSeries.Presentation.reset_count_text (3) == "3 resets");
        assert (MSeries.Presentation.reset_credits_line (0, 5000) == "0 resets available");
        assert (MSeries.Presentation.reset_credits_line (2, 0) == "2 resets available");
        assert (MSeries.Presentation.reset_credits_line (2, 3600) == "2 resets available · first expires in 1h00m");
        assert (MSeries.Presentation.reset_expiry_urgent (2, 3600));
        assert (!MSeries.Presentation.reset_expiry_urgent (2, 90000));
        assert (!MSeries.Presentation.reset_expiry_urgent (0, 3600));
    });
    GLib.Test.add_func ("/presentation/countdown", () => {
        assert (MSeries.Presentation.countdown_text (0) == "");
        assert (MSeries.Presentation.countdown_text (-5) == "");
        assert (MSeries.Presentation.countdown_text (61) == "2m");
        assert (MSeries.Presentation.countdown_text (3600) == "1h00m");
        assert (MSeries.Presentation.countdown_text (4 * 3600 + 44 * 60 + 10) == "4h44m");
        assert (MSeries.Presentation.countdown_text (6 * 86400 + 22 * 3600 + 59 * 60) == "6d22h");
    });
    GLib.Test.add_func ("/presentation/panel-count", () => {
        assert (MSeries.Presentation.panel_count_text (120813143) == "121M");
        assert (MSeries.Presentation.panel_count_text (9400000) == "9.4M");
        assert (MSeries.Presentation.panel_count_text (1813153516) == "1.8B");
    });
    GLib.Test.add_func ("/presentation/binding-window", () => {
        var parser = new Json.Parser ();
        try {
            parser.load_from_data ("[{\"remaining\":79},{\"remaining\":null},{\"remaining\":12},{\"remaining\":12}]");
        } catch (Error e) {
            assert_not_reached ();
        }
        assert (MSeries.Presentation.binding_window (parser.get_root ().get_array ()) == 2);
        try {
            parser.load_from_data ("[{\"remaining\":null},{}]");
        } catch (Error e) {
            assert_not_reached ();
        }
        assert (MSeries.Presentation.binding_window (parser.get_root ().get_array ()) == -1);
    });
    GLib.Test.add_func ("/presentation/plan-label", () => {
        assert (MSeries.Presentation.plan_label ("prolite") == "Pro Lite");
        assert (MSeries.Presentation.plan_label ("pro") == "Pro");
        assert (MSeries.Presentation.plan_label ("max") == "Max");
        assert (MSeries.Presentation.plan_label ("") == "");
        assert (MSeries.Presentation.plan_label ("enterprise") == "Enterprise");
        assert (MSeries.Presentation.plan_label (" plus ") == "Plus");
        assert (MSeries.Presentation.plan_label ("go") == "Go");
        assert (MSeries.Presentation.plan_label ("unknown") == "");
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
