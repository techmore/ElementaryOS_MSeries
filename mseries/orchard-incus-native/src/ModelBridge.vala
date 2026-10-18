public class ModelBridge : Object {
    public static string container_url (string endpoint, Json.Object network) throws Error {
        var base_url = ModelService.validate_endpoint (endpoint);
        var uri = Uri.parse (base_url, UriFlags.NONE);
        var address = new InetAddress.from_string (uri.get_host ());
        bool loopback = uri.get_host () == "localhost" || (address != null && address.get_is_loopback ());
        if (!loopback) return base_url;
        var config = network.get_object_member ("config");
        var gateway = config.get_string_member_with_default ("ipv4.address", "").split ("/")[0];
        if (new InetAddress.from_string (gateway) == null) throw new IOError.FAILED ("The selected network does not report an IPv4 host gateway.");
        return Uri.build (UriFlags.NONE, uri.get_scheme (), null, gateway, uri.get_port (), uri.get_path (), null, null).to_string ();
    }
    public static bool host_only (Json.Object network) {
        var config = network.get_object_member ("config");
        return network.get_string_member_with_default ("type", "") == "bridge"
            && network.get_boolean_member_with_default ("managed", false)
            && config.get_string_member_with_default ("ipv4.routing", "true") == "false"
            && config.get_string_member_with_default ("ipv4.nat", "false") == "false"
            && config.get_string_member_with_default ("ipv6.address", "") == "none"
            && config.get_string_member_with_default ("raw.dnsmasq", "").strip () == "port=0";
    }
    public static async string attach (IncusClient client, string instance, string endpoint) throws Error {
        var response = yield client.inspect_instance (instance);
        var data = response.get_object_member ("metadata");
        var devices = data.get_object_member ("expanded_devices");
        string network_name = "";
        foreach (var key in devices.get_members ()) {
            var device = devices.get_object_member (key);
            if (device.get_string_member_with_default ("type", "") != "nic") continue;
            var network = device.get_string_member_with_default ("network", "");
            if (network != "") {
                if (network_name != "" && network_name != network) throw new IOError.FAILED ("This instance has several networks; configure its model endpoint explicitly instead of guessing a gateway.");
                network_name = network;
            }
        }
        if (network_name == "") throw new IOError.FAILED ("Attach a managed Incus network first.");
        var network = yield client.call ("GET", "/1.0/networks/" + Uri.escape_string (network_name, null, false));
        var reachable = container_url (endpoint, network.get_object_member ("metadata"));
        var config = new Json.Object ();
        config.set_string_member ("environment.OPENAI_BASE_URL", reachable);
        config.set_string_member ("user.orchard.model-endpoint", reachable);
        yield client.update_instance (instance, config, response.get_string_member ("_orchard_etag"));
        return reachable;
    }
}
