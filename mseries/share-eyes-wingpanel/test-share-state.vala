void main () {
    var s = new MSeries.ShareState ();
    int64 now = 1000;
    assert (!s.parse (null, now) && !s.live);
    assert (s.parse ("{\"live\":true,\"viewers\":2,\"updated\":995}", now) && s.live && s.viewers == 2);
    assert (!s.parse ("{\"live\":true,\"viewers\":2,\"updated\":999}", now));
    assert (s.parse ("{\"live\":true,\"viewers\":2,\"updated\":900}", now) && !s.live);   /* stale */
    assert (!s.parse ("not json", now) && !s.live);
    assert (!s.parse ("{\"live\":false,\"viewers\":3,\"updated\":1000}", now) && !s.live && s.viewers == 0);
    s.parse ("{\"live\":true,\"viewers\":1,\"updated\":1000}", now);
    assert (s.tooltip () == "Sharing your screen · 1 person watching");
    s.parse ("{\"live\":true,\"viewers\":0,\"updated\":1000}", now);
    assert (s.tooltip ().contains ("nobody"));
    print ("share-state: ok\n");
}
