/* Fleet: devices managed by a TM-Remote control plane. Pure logic (no network, no UI)
 * so it can be unit-tested; the HTTP client is in fleet-client.vala. */

public class FleetDevice : Object {
    public string id { get; set; default = ""; }
    public string hostname { get; set; default = ""; }
    public string os { get; set; default = ""; }
    public string arch { get; set; default = ""; }
    public string version { get; set; default = ""; }
    public DateTime last_seen { get; set; default = new DateTime.from_unix_utc (0); }
    public string[] policy_status { get; set; default = {}; }

    // Agents check in every 30 s; tolerate a few missed intervals before "offline".
    public bool online {
        get { return new DateTime.now_utc ().difference (last_seen) < 120 * TimeSpan.SECOND; }
    }
    public bool is_linux { get { return os.down () == "linux"; } }
    public bool is_mac { get { return os.down () == "darwin" || os.down () == "macos"; } }

    public static FleetDevice from_json (Json.Object o) {
        var d = new FleetDevice ();
        d.id = o.get_string_member_with_default ("id", "");
        d.hostname = o.get_string_member_with_default ("hostname", d.id);
        d.os = o.get_string_member_with_default ("os", "");
        d.arch = o.get_string_member_with_default ("arch", "");
        d.version = o.get_string_member_with_default ("version", "");
        var seen = new DateTime.from_iso8601 (o.get_string_member_with_default ("last_seen", ""), new TimeZone.utc ());
        if (seen != null) {
            d.last_seen = seen;
        }
        string[] policy = {};
        if (o.has_member ("policy_status") && o.get_member ("policy_status").get_node_type () == Json.NodeType.ARRAY) {
            o.get_array_member ("policy_status").foreach_element ((a, i, n) => { policy += n.get_string (); });
        }
        d.policy_status = policy;
        return d;
    }

    /* The device's DNS name inside the control plane's tailnet, e.g.
     * "sdolbec-ser8.tailf80972.ts.net" when the server is "x.tailf80972.ts.net". Null when the
     * server address has no domain to borrow (an IP, localhost). */
    public string? tailnet_name (string server_url) {
        string host;
        try {
            host = Uri.parse (server_url, UriFlags.NONE).get_host () ?? "";
        } catch (UriError e) {
            return null;
        }
        var dot = host.index_of_char ('.');
        if (dot < 0 || !host.has_suffix (".ts.net")) {
            return null;
        }
        return hostname.down () + host.substring (dot);
    }
}

namespace Fleet {
    /* Build the copy-paste install command. Both values end up in a user's shell, so anything
     * outside the characters the server hands out is refused rather than quoted. */
    public string? enroll_command (string server_url, string token, bool mac) {
        if (!Regex.match_simple ("^[A-Za-z0-9_-]{8,128}$", token)) {
            return null;
        }
        if (!Regex.match_simple ("^https?://[A-Za-z0-9.:_-]+$", server_url)) {
            return null;
        }
        var script = mac ? "bootstrap-macos.sh" : "bootstrap-linux.sh";
        return "curl -fsSL %s/install/%s | sh -s -- --server %s --enroll-token %s"
            .printf (server_url, script, server_url, token);
    }

    /* Normalise what the user typed: trim, drop trailing slashes, require http(s). */
    public string? clean_server_url (string typed) {
        var url = typed.strip ();
        while (url.has_suffix ("/")) {
            url = url.substring (0, url.length - 1);
        }
        if (!url.has_prefix ("https://") && !url.has_prefix ("http://")) {
            return null;
        }
        return url;
    }
}
