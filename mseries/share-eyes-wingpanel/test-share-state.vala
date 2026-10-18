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
    assert (s.parse (full, now + 100) && !s.running && !s.live);          /* stale: launcher gone */
    assert (!s.parse ("not json", now) && !s.running);
    s.parse ("{\"live\":false,\"viewers\":3,\"updated\":1000,\"port\":1}", now);
    assert (s.running && !s.live && s.viewers == 0 && s.tooltip ().contains ("not sharing yet"));
    s.parse ("{\"live\":true,\"viewers\":1,\"updated\":1000,\"port\":1}", now);
    assert (s.tooltip () == "Sharing your screen · 1 person watching");
    s.parse ("{\"live\":true,\"viewers\":0,\"updated\":1000,\"port\":1}", now);
    assert (s.tooltip ().contains ("nobody"));
    print ("share-state: ok\n");
}
