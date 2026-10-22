private async void exercise () throws Error {
    var parser = new Json.Parser ();
    parser.load_from_data ("""{"name":"vm-starting","type":"virtual-machine","status":"Running","config":null,"snapshots":null,"state":{"cpu":{"usage":100},"memory":{"usage":256},"disk":{"root":null},"network":{"eth0":{"addresses":null,"counters":{"bytes_received":3,"bytes_sent":4}},"pending":null}}}""");
    var partial_vm = Instance.from_json (parser.get_root ().get_object ());
    assert (partial_vm.ipv4 == "" && partial_vm.network_bytes == 7 && partial_vm.cpu_available && partial_vm.memory_bytes == 256 && !partial_vm.disk_available);
    var original = new Json.Object ();
    original.set_string_member ("user.data", "#cloud-config\nkey: \"value=unicode 🌳\"\n");
    original.set_string_member ("user.empty", "");
    original.set_string_member ("volatile.id", "hidden");
    var roundtrip = ConfigText.parse (ConfigText.render (original, true), true);
    assert (roundtrip.get_string_member ("user.data") == original.get_string_member ("user.data"));
    assert (roundtrip.get_string_member ("user.empty") == "" && !roundtrip.has_member ("volatile.id"));
    assert (ConfigText.parse ("user.test=a=b\n").get_string_member ("user.test") == "a=b");
    bool invalid_config = false;
    try { ConfigText.parse ("user.test=a\nuser.test=b"); } catch (Error e) { invalid_config = true; }
    assert (invalid_config); invalid_config = false;
    try { ConfigText.parse ("volatile.id=changed", true); } catch (Error e) { invalid_config = true; }
    assert (invalid_config);
    var client = new IncusClient (10);
    var response = yield client.inspect_instance ("test");
    assert (response.get_string_member ("_orchard_etag") == "\"one\"");
    var config = new Json.Object ();
    config.set_string_member ("user.note", "quote\" slash\\ newline\nvalue");
    yield client.update_instance ("test", config, "\"one\"");
    bool conflict = false;
    try { yield client.update_instance ("test", config, "\"stale\""); } catch (Error e) { conflict = true; }
    assert (conflict);
    var limits = new Json.Object (); limits.set_string_member ("limits.cpu", "2");
    yield client.create_instance ("new", "alpine/edge", false, limits, true);
    var devices = new Json.Object (); var root = new Json.Object (); root.set_string_member ("type", "disk"); root.set_string_member ("path", "/"); root.set_string_member ("pool", "fixture"); devices.set_object_member ("root", root);
    yield client.create_instance ("sandbox", "local:cached-fingerprint", true, limits, false, devices, true);
    yield client.clone_instance ("test", "copy");
    yield client.create_snapshot ("test", "quoted\"snapshot");
    yield client.restore_snapshot ("test", "quoted\"snapshot");
    bool failed_operation = false;
    try { yield client.change_state ("test", "stop", true); } catch (Error e) { failed_operation = true; }
    assert (failed_operation);
    var archive = File.new_for_path (Environment.get_variable ("ORCHARD_TEST_ARCHIVE"));
    yield client.export_instance ("test", archive);
    string data; FileUtils.get_contents (archive.get_path (), out data);
    assert (data == "fixture-backup-contents");
    var log = yield client.read_log ("test", "lxc.log");
    assert (log == "fixture log\n");
    var empty = yield client.read_log ("test", "empty.log"); assert (empty == "");
    print ("Client lifecycle, conflict, JSON, failed-operation and streamed-export checks passed.\n");
}
int main () {
    var loop = new MainLoop ();
    int result = 1;
    exercise.begin ((obj, res) => {
        try { exercise.end (res); result = 0; }
        catch (Error e) { stderr.printf ("%s\n", e.message); }
        loop.quit ();
    });
    loop.run ();
    return result;
}
