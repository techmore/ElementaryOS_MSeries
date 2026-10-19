private async void exercise () throws Error {
    var client = new IncusClient (5); var config = new Json.Object (); config.set_string_member ("limits.memory", "256MiB");
    yield client.update_with_restart ("success", config, "\"before\"");
    foreach (var name in new string[] { "stale", "race", "ephemeral" }) {
        bool refused = false;
        try { yield client.update_with_restart (name, config, "\"before\""); } catch (Error e) { refused = true; }
        assert (refused);
    }
    var left = new Preferences (); var right = new Preferences ();
    left.write ("one", "kept"); right.write ("two", "also-kept");
    assert (left.read ("two", "") == "also-kept" && right.read ("one", "") == "kept");
    print ("Restart flow handles volatile ETag changes, rejects real races and protects ephemeral instances; concurrent preferences are preserved.\n");
}
int main () {
    var loop = new MainLoop (); int code = 1;
    exercise.begin ((obj, result) => { try { exercise.end (result); code = 0; } catch (Error e) { stderr.printf ("%s\n", e.message); } loop.quit (); });
    loop.run (); return code;
}
