Json.Object fixture (string json) {
    var parser = new Json.Parser ();
    try { parser.load_from_data (json); } catch (GLib.Error e) { GLib.error ("%s", e.message); }
    return parser.get_root ().get_object ();
}

int main (string[] args) {
    GLib.Test.init (ref args);
    GLib.Test.add_func ("/eta/session-depletion", () => {
        var eta = MSeries.QuotaEta.from_window (fixture ("""{"remaining":12,"pace":"30% in deficit | Expected 20% used | Projected empty in 1h 5m"}"""));
        assert (eta.state == MSeries.EtaState.DEPLETING);
        assert (eta.seconds == 3900 && eta.compact == "~1h5m");
    });
    GLib.Test.add_func ("/eta/weekly-depletion", () => {
        var eta = MSeries.QuotaEta.from_window (fixture ("""{"remaining":82,"pace":"14% in deficit | Expected 4% used | Runs out in 1d 7h"}"""));
        assert (eta.seconds == 111600 && eta.detail == "Est. empty in ~1d 7h at this pace");
    });
    GLib.Test.add_func ("/eta/safe-until-reset", () => {
        var eta = MSeries.QuotaEta.from_window (fixture ("""{"remaining":87,"pace":"21% in reserve | Expected 34% used | Lasts until reset | 1.5× headroom"}"""));
        assert (eta.state == MSeries.EtaState.SAFE && eta.compact == "until reset");
    });
    GLib.Test.add_func ("/eta/exhausted-without-pace", () => {
        var eta = MSeries.QuotaEta.from_window (fixture ("""{"remaining":0,"pace":"","minutes":null,"resetText":"Resets in 19m"}"""));
        assert (eta.state == MSeries.EtaState.EXHAUSTED && eta.compact == "reset 19m");
    });
    GLib.Test.add_func ("/eta/unknown-and-format-drift", () => {
        foreach (var json in new string[] {
            """{"remaining":null,"pace":"Lasts until reset"}""",
            """{"remaining":"0","pace":"Lasts until reset"}""",
            """{"remaining":-1,"pace":"Lasts until reset"}""",
            """{"remaining":101,"pace":"Lasts until reset"}""",
            """{"remaining":60,"pace":""}""",
            """{"remaining":60,"pace":"Runs out in twelve hours"}""",
            """{"remaining":60,"pace":"Runs out in 999999999999d"}"""
        }) assert (MSeries.QuotaEta.from_window (fixture (json)).state == MSeries.EtaState.UNKNOWN);
    });
    GLib.Test.add_func ("/eta/stale-and-expired-reset", () => {
        var window = fixture ("""{"remaining":0,"pace":"","resetsAt":"1970-01-01T00:00:10Z"}""");
        assert (MSeries.QuotaEta.from_window (window, true).state == MSeries.EtaState.STALE);
        assert (MSeries.QuotaEta.from_window (window, false, 11).state == MSeries.EtaState.UNKNOWN);
    });
    GLib.Test.add_func ("/eta/immediate-projection", () => {
        var eta = MSeries.QuotaEta.from_window (fixture ("""{"remaining":1,"pace":"Projected empty now"}"""));
        assert (eta.state == MSeries.EtaState.DEPLETING && eta.seconds == 0 && eta.compact == "~now");
    });
    GLib.Test.add_func ("/eta/earliest-limiting-window", () => {
        var entry = fixture ("""{"windows":[{"label":"5 hour","remaining":87,"pace":"Lasts until reset"},{"label":"7 day","remaining":82,"pace":"Runs out in 1d 7h"},{"remaining":5,"pace":"Projected empty in 20m"}]}""");
        var eta = MSeries.QuotaEta.for_entry (entry, false, 0);
        assert (eta.seconds == 1200 && eta.compact == "~20m");
    });
    GLib.Test.add_func ("/eta/unknown-prevents-safe-summary", () => {
        var entry = fixture ("""{"windows":[{"remaining":90,"pace":"Lasts until reset"},{"remaining":50,"pace":""}]}""");
        assert (MSeries.QuotaEta.for_entry (entry, false, 0).state == MSeries.EtaState.UNKNOWN);
    });
    GLib.Test.add_func ("/eta/exhaustion-overrides-forecast", () => {
        var entry = fixture ("""{"windows":[{"remaining":80,"pace":"Runs out in 1d"},{"remaining":0,"resetText":"Resets in 2h"}]}""");
        assert (MSeries.QuotaEta.for_entry (entry, false, 0).state == MSeries.EtaState.EXHAUSTED);
    });
    GLib.Test.add_func ("/eta/provider-freshness", () => {
        var entry = fixture ("""{"updatedAt":"1970-01-01T00:16:40Z","error":""}""");
        assert (!MSeries.QuotaEta.entry_stale (entry, false, 1180));
        assert (MSeries.QuotaEta.entry_stale (entry, false, 1181));
        assert (MSeries.QuotaEta.entry_stale (entry, true, 1000));
        assert (MSeries.QuotaEta.entry_stale (entry, false, 939));
        assert (MSeries.QuotaEta.entry_stale (fixture ("{}"), false, 1000));
        entry.set_string_member ("error", "Usage unavailable");
        assert (MSeries.QuotaEta.entry_stale (entry, false, 1000));
    });
    return GLib.Test.run ();
}
