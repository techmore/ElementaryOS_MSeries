void main (string[] args) {
    GLib.Test.init (ref args);
    GLib.Test.add_func ("/refresh/cold-start", () => {
        var policy = new MSeries.RefreshPolicy ();
        assert (policy.should_refresh_on_open (false, 0, 1000, 1000000));
    });
    GLib.Test.add_func ("/refresh/skip-running-fetch", () => {
        var policy = new MSeries.RefreshPolicy ();
        assert (!policy.should_refresh_on_open (true, 0, 1000, 1000000));
    });
    GLib.Test.add_func ("/refresh/skip-recent-usage", () => {
        var policy = new MSeries.RefreshPolicy ();
        assert (!policy.should_refresh_on_open (false, 971, 1000, 1000000));
        assert (policy.should_refresh_on_open (false, 970, 1000, 1000000));
    });
    GLib.Test.add_func ("/refresh/reopen-cooldown", () => {
        var policy = new MSeries.RefreshPolicy ();
        policy.requested (1000000);
        assert (!policy.should_refresh_on_open (false, 0, 1000, 60999999));
        assert (policy.should_refresh_on_open (false, 0, 1000, 61000000));
    });
    GLib.Test.add_func ("/refresh/wall-clock-change", () => {
        var policy = new MSeries.RefreshPolicy ();
        policy.requested (1000000);
        assert (!policy.should_refresh_on_open (false, 0, 999999, 2000000));
        assert (policy.should_refresh_on_open (false, 1000, 900, 61000000));
    });
    GLib.Test.run ();
}
