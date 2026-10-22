private async void exercise_models () throws Error {
    var base_url = Environment.get_variable ("ORCHARD_MODEL_TEST_URL");
    var service = new ModelService (false);
    var models = yield service.list_models (base_url + "/v1");
    assert (models.length == 1 && models[0] == "fixture-model");
    var answer = yield service.chat (base_url + "/v1", models[0], "quoted\"prompt\nline");
    assert (answer == "fixture answer");
    bool denied = false;
    try { yield service.list_models (base_url + "/auth"); } catch (Error e) { denied = e is IOError.PERMISSION_DENIED; }
    assert (denied);
    bool invalid = false;
    try { ModelService.validate_endpoint ("https://alice:secret@example.test/v1"); } catch (Error e) { invalid = true; }
    assert (invalid);
    var network = new Json.Object (); var network_config = new Json.Object ();
    network.set_string_member ("type", "bridge"); network.set_boolean_member ("managed", true); network.set_object_member ("config", network_config);
    network_config.set_string_member ("ipv4.address", "10.40.0.1/24"); network_config.set_string_member ("ipv4.routing", "false"); network_config.set_string_member ("ipv4.nat", "false"); network_config.set_string_member ("ipv6.address", "none"); network_config.set_string_member ("raw.dnsmasq", "port=0");
    assert (ModelBridge.container_url ("http://127.0.0.1:11434/v1", network) == "http://10.40.0.1:11434/v1");
    assert (ModelBridge.container_url ("https://models.example.test/v1", network) == "https://models.example.test/v1");
    assert (ModelBridge.host_only (network));
    network_config.set_string_member ("ipv4.nat", "true"); assert (!ModelBridge.host_only (network));
    network_config.set_string_member ("ipv4.nat", "false"); network_config.set_string_member ("ipv6.address", "auto"); assert (!ModelBridge.host_only (network));
    network_config.set_string_member ("ipv6.address", "none"); network_config.set_string_member ("raw.dnsmasq", "port=0\nport=53"); assert (!ModelBridge.host_only (network));
    print ("Model discovery, completion, auth failure and credential-free endpoint checks passed.\n");
}
int main () {
    var loop = new MainLoop (); int code = 1;
    exercise_models.begin ((obj, result) => {
        try { exercise_models.end (result); code = 0; } catch (Error e) { stderr.printf ("%s\n", e.message); }
        loop.quit ();
    });
    loop.run (); return code;
}
