async void check_processes (MainLoop loop) {
    int ticks = 0;
    var heartbeat = Timeout.add (10, () => { ticks++; return Source.CONTINUE; });
    try {
        assert ((yield MSeries.HelperProcess.read ({"/bin/sh", "-c", "printf valid"})) == "valid");
        assert ((yield MSeries.HelperProcess.read ({"/bin/sh", "-c", "printf 1234"}, 1000, 4)) == "1234");
        try {
            yield MSeries.HelperProcess.read ({"/bin/sh", "-c", "exec sleep 5"}, 100);
            assert_not_reached ();
        } catch (IOError e) { assert (e.code == IOError.TIMED_OUT); }
        assert (ticks > 0); // A stalled helper never blocks the main loop.
        try {
            yield MSeries.HelperProcess.read ({"/bin/sh", "-c", "exec yes overflow"}, 1000, 1024);
            assert_not_reached ();
        } catch (IOError e) { assert (e.code == IOError.NO_SPACE); }
        try {
            yield MSeries.HelperProcess.read ({"/bin/sh", "-c", "exit 7"});
            assert_not_reached ();
        } catch (IOError e) { assert (e.code == IOError.FAILED); }
        foreach (var command in new string[] {"printf '\\000'", "printf '\\377'"}) {
            try {
                yield MSeries.HelperProcess.read ({"/bin/sh", "-c", command});
                assert_not_reached ();
            } catch (IOError e) { assert (e.code == IOError.INVALID_DATA); }
        }
        assert ((yield MSeries.HelperProcess.read ({"/bin/echo", "recovered"})) == "recovered\n");
    } catch (Error e) { error ("Unexpected helper failure: %s", e.message); }
    Source.remove (heartbeat);
    loop.quit ();
}
int main () {
    Log.set_always_fatal (LogLevelFlags.LEVEL_ERROR | LogLevelFlags.LEVEL_CRITICAL);
    var loop = new MainLoop ();
    check_processes.begin (loop);
    loop.run ();
    return 0;
}
