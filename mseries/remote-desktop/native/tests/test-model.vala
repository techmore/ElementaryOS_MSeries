using MSeries.Remote;

const string IDLE = """{"enabled":true,"listen":"0.0.0.0:8484","backend":"mutter","phase":"idle","pending":null,"session":null,"grace_until_ms":null,"invites_pending":1}""";
const string OFF = """{"enabled":false,"listen":null,"backend":"mutter","phase":"idle","pending":null,"session":null,"grace_until_ms":null,"invites_pending":0}""";
const string PENDING = """{"enabled":true,"listen":"0.0.0.0:8484","backend":"mutter","phase":"pending","pending":{"id":"r1","device":"Pixel 8","control_offered":true,"requested_ms":1000,"expires_ms":61000},"session":null,"grace_until_ms":null,"invites_pending":0}""";
const string ACTIVE = """{"enabled":true,"listen":"0.0.0.0:8484","backend":"mutter","phase":"active","pending":null,"session":{"id":"s1","device":"Pixel 8","control":false,"control_permitted":true,"connected":true},"grace_until_ms":null,"invites_pending":0}""";
const string GRACE = """{"enabled":true,"listen":null,"backend":"mutter","phase":"grace","pending":null,"session":{"id":"s1","device":"Pixel 8","control":true,"control_permitted":true,"connected":false},"grace_until_ms":99000,"invites_pending":0}""";

void expect (bool ok, string what) {
    if (!ok) {
        error ("FAILED: %s", what);
    }
}

void test_parse () {
    var s = Status.parse (IDLE);
    expect (s != null && s.phase == Phase.IDLE && s.enabled && s.listen == "0.0.0.0:8484", "idle parses");
    s = Status.parse (OFF);
    expect (s.phase == Phase.OFF && !s.enabled && s.listen == null, "off parses");
    s = Status.parse (PENDING);
    expect (s.phase == Phase.PENDING && s.pending.id == "r1" && s.pending.control_offered && s.pending.device == "Pixel 8", "pending parses");
    s = Status.parse (ACTIVE);
    expect (s.phase == Phase.ACTIVE && !s.session.control && s.session.control_permitted && s.session.connected, "active parses");
    s = Status.parse (GRACE);
    expect (s.phase == Phase.GRACE && s.grace_until_ms == 99000 && s.session.control, "grace parses");
    expect (Status.parse ("not json") == null, "garbage is rejected");
    expect (Status.parse ("[]") == null, "wrong root is rejected");
}

void test_presentation () {
    expect (!Presentation.indicator_visible (Status.unavailable ()), "no indicator when the service is gone");
    expect (!Presentation.indicator_visible (Status.parse (OFF)), "no indicator when sharing is off");
    expect (Presentation.indicator_visible (Status.parse (IDLE)), "indicator when ready");
    expect (!Presentation.sharing_now (Status.parse (IDLE)), "idle is not sharing");
    expect (!Presentation.sharing_now (Status.parse (PENDING)), "a request is not sharing yet");
    expect (Presentation.sharing_now (Status.parse (ACTIVE)), "active is sharing");
    expect (Presentation.sharing_now (Status.parse (GRACE)), "grace still counts as sharing");
    expect (Presentation.icon_name (Status.parse (ACTIVE)) == "mseries-remote-sharing-symbolic", "sharing icon");
    expect (Presentation.icon_name (Status.parse (IDLE)) == "mseries-remote-symbolic", "ready icon");
    expect (Presentation.title (Status.parse (ACTIVE)).contains ("viewing"), "view-only wording");
    expect (Presentation.title (Status.parse (GRACE)).contains ("controlling") == false, "grace wording does not claim control");
    var controlling = Status.parse (ACTIVE);
    controlling.session.control = true;
    expect (Presentation.title (controlling).contains ("controlling"), "control wording");
    expect (Presentation.title (Status.parse (PENDING)).contains ("Pixel 8"), "pending names the device");
    expect (Presentation.countdown (272000) == "4:32", "countdown formats");
    expect (Presentation.countdown (-5) == "0:00", "countdown never negative");
    expect (Presentation.countdown (1) == "0:01", "countdown rounds up");
}

void test_invite () {
    var i = Invite.parse ("""{"links":[{"label":"Tailnet","url":"http://100.64.0.9:8484/#i=abc"},{"label":"Local network","url":"http://192.168.1.2:8484/#i=abc"}],"qr":["101","010","101"],"expires_ms":123,"control_offered":true}""");
    expect (i != null && i.links.length == 2 && i.links[0].label == "Tailnet" && i.qr.length == 3 && i.control_offered && i.expires_ms == 123, "invite parses");
    expect (Invite.parse ("{") == null, "bad invite rejected");
}

int main (string[] args) {
    Test.init (ref args);
    Test.add_func ("/remote/parse", test_parse);
    Test.add_func ("/remote/presentation", test_presentation);
    Test.add_func ("/remote/invite", test_invite);
    return Test.run ();
}
