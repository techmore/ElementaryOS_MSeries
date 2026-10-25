void main () {
    var s = new MSeries.ShareState ();
    int64 now = 1000;
    assert (!s.parse (null, now) && !s.running);
    string full = "{\"live\":true,\"viewers\":2,\"updated\":995,\"port\":8799,\"email\":\"a@b\",\"password\":\"pw\",\"public_url\":\"http://h:8799\"}";
    assert (s.parse (full, now) && s.running && s.live && s.viewers == 2 && s.port == 8799);
    assert (s.share_page == "http://127.0.0.1:8799/share" && s.viewer_base == "http://h:8799");
    assert (s.login_text () == "Screen share (this computer)\nOpen: http://127.0.0.1:8799/share\nUsername: a@b\nPassword: pw\n");
    assert (s.login_url () == "http://127.0.0.1:8799/share#u=a%40b&p=pw");
    assert (!s.parse (full, now));
    // A wall-clock step backwards must not keep an old launcher live indefinitely.
    assert (s.parse (full, 994) && !s.running && !s.live && s.viewers == 0);
    assert (s.port == 0 && s.email == "" && s.password == "" && s.public_url == "");
    assert (s.parse (full, now) && s.running && s.live);  // fresh heartbeat recovers
    assert (!s.parse (full, 1010) && s.running);         // exactly 15 seconds is fresh
    assert (s.parse (full, 1011) && !s.running);         // 16 seconds is stale
    assert (s.parse (full, now) && s.running);
    s.parse ("{\"live\":true,\"updated\":0}", 0);
    assert (!s.running && !s.live);                    // no valid heartbeat
    s.parse ("{\"live\":true}", 0);
    assert (!s.running && !s.live);                    // absent timestamp
    assert (s.parse (full, now) && s.running);
    assert (s.parse (full, now + 100) && !s.running && !s.live);          /* stale: launcher gone */
    assert (!s.parse ("not json", now) && !s.running);
    s.parse ("{\"live\":false,\"viewers\":3,\"updated\":1000,\"port\":1}", now);
    assert (s.running && !s.live && s.viewers == 0 && s.tooltip ().contains ("not sharing yet"));
    s.parse ("{\"live\":true,\"viewers\":1,\"updated\":1000,\"port\":1}", now);
    assert (s.tooltip () == "Sharing your screen · 1 person watching");
    s.parse ("{\"live\":true,\"viewers\":0,\"updated\":1000,\"port\":1}", now);
    assert (s.tooltip ().contains ("nobody"));
    s.parse ("{\"live\":true,\"viewers\":0,\"updated\":1000,\"port\":1,\"public_url\":\"https://tm-remote.stoverparc.org\",\"lan_url\":\"http://192.168.1.5:8799\"}", now);
    var b = s.link_bases ();
    assert (b.length[0] == 2 && b[0, 0] == "Internet" && b[0, 1] == "https://tm-remote.stoverparc.org" && b[1, 0] == "Local network" && b[1, 1] == "http://192.168.1.5:8799");
    s.parse ("{\"live\":true,\"viewers\":0,\"updated\":1000,\"port\":1,\"public_url\":\"http://192.168.1.5:8799\"}", now);
    b = s.link_bases ();
    assert (b.length[0] == 1 && b[0, 0] == "Local network" && b[0, 1] == "http://192.168.1.5:8799");
    print ("share-state: ok\n");
}
