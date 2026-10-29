/* Checks how `tailscale status --json` peers become menu rows. */
int main () {
    var parser = new Json.Parser ();
    try {
        parser.load_from_data ("""{"Peer":{
          "a":{"HostName":"localhost","DNSName":"iphone-14-pro.tail1.ts.net.","OS":"iOS","Online":true,
               "TailscaleIPs":["fd7a:115c:a1e0::7d32:632c","100.96.99.44"]},
          "b":{"HostName":"sdolbec-SER8","DNSName":"sdolbec-ser8.tail1.ts.net.","OS":"linux","Online":false,
               "TailscaleIPs":["100.127.99.74","fd7a:115c:a1e0::a32:634b"]},
          "c":{"HostName":"no-ip","DNSName":"","OS":"linux","Online":true,"TailscaleIPs":[]}}}""");
    } catch (Error e) {
        error ("fixture: %s", e.message);
    }
    var peers = parser.get_root ().get_object ().get_object_member ("Peer");
    var phone = MSeries.Tailscale.Device.from_json (peers.get_object_member ("a"));
    assert (phone != null);
    assert (phone.ip == "100.96.99.44");          // IPv4 preferred even when listed second
    assert (phone.name == "iphone-14-pro");       // "localhost" replaced by MagicDNS name
    assert (phone.online);
    var ser8 = MSeries.Tailscale.Device.from_json (peers.get_object_member ("b"));
    assert (ser8.ssh_host == "sdolbec-ser8");     // `ssh sdolbec-ser8`
    assert (ser8.name == "sdolbec-SER8" && !ser8.online && ser8.ip == "100.127.99.74");
    assert (MSeries.Tailscale.Device.from_json (peers.get_object_member ("c")) == null);
    print ("tailscale device parsing: ok\n");
    return 0;
}
