/* Clipboard sync tests: the real ClipboardBridge talks D-Bus over a socketpair to a fake QEMU that
 * models what QEMU's ui/dbus-clipboard.c and the guest's spice-vdagentd do with grabs and serials
 * (vdagentd accepts a client grab only when its serial equals the guest counter N, then N++, or N-1).
 * No display, no VM. */

public delegate bool Cond ();

/* Run the main loop until the condition holds; false on timeout. */
bool spin (Cond c, uint ms = 5000) {
    var ctx = MainContext.default ();
    int64 end = get_monotonic_time () + (int64) ms * 1000;
    while (!c ()) {
        if (get_monotonic_time () > end) {
            return false;
        }
        if (!ctx.iteration (false)) {
            Thread.usleep (300);
        }
    }
    return true;
}

/* Let pending events (and anything that should NOT happen) play out. */
void settle (uint ms = 250) {
    spin (() => false, ms);
}

public class FakeHost : Object, HostClipboard {
    public string? text = null;
    public bool local = false;
    public bool hang = false;          // read_text never answers on its own (only a cancel ends it)
    public bool echo_later = false;    // report our own writes after the write call has returned
    public int writes = 0;

    public bool is_local { get { return local; } }
    public bool has_text { get { return text != null; } }

    public async string? read_text (Cancellable? cancellable = null) throws Error {
        Idle.add (read_text.callback);
        yield;
        if (hang) {
            ulong id = 0;
            if (cancellable != null) {
                id = cancellable.connect (() => { Idle.add (read_text.callback); });
            }
            yield;
            if (cancellable != null) {
                cancellable.disconnect (id);
                cancellable.set_error_if_cancelled ();
            }
        }
        return text;
    }

    public void write_text (string t) {
        text = t;
        local = true;
        writes++;
        if (echo_later) {
            Idle.add (() => { changed (); return Source.REMOVE; });
        } else {
            changed ();
        }
    }

    /* The user copies in another app (or this one) on the host. */
    public void user_copies (string? t, bool in_this_app = false) {
        text = t;
        local = in_this_app;
        changed ();
    }
}

[DBus (name = "org.qemu.Display1.Clipboard")]
public class FakeQemuService : Object {
    public weak FakeQemu qemu;

    public string[] interfaces {
        owned get { return new string[0]; }
    }

    [DBus (name = "Register")]
    public void register_client () throws Error {
        qemu.on_register ();
    }

    [DBus (name = "Unregister")]
    public void unregister_client () throws Error {
        qemu.registered = false;
    }

    public void grab (uint selection, uint serial, string[] mimes) throws Error {
        qemu.on_client_grab (selection, serial, mimes);
    }

    public void release (uint selection) throws Error {
        qemu.on_client_release ();
    }

    public async void request (uint selection, string[] mimes, out string reply_mime, out uint8[] data) throws Error {
        string m = "";
        uint8[] d = new uint8[0];
        yield qemu.on_client_request (out m, out d);
        reply_mime = m;
        data = d;
    }
}

public enum GuestClip {
    NOTHING,
    HOST,
    GUEST
}

/* QEMU's clipboard peer plus the guest agent behind it. */
public class FakeQemu : Object {
    public DBusConnection conn;
    public ClipboardPeer? client = null;
    public bool registered = false;
    public int register_calls = 0;
    public int grabs_received = 0;
    public int releases_received = 0;
    public int64 last_grab_serial = -1;
    public int guest_discards = 0;
    public uint request_delay_ms = 0;

    // The guest agent (spice-vdagentd): its serial counter and what its clipboard holds.
    public int64 guest_n = 0;
    public GuestClip guest_clip = GuestClip.NOTHING;
    public string? guest_text = null;
    // QEMU's own record of the latest grab serial (qemu_clipboard_check_serial).
    private int64 qemu_serial = -1;

    public void on_register () {
        registered = true;
        register_calls++;
        // QEMU resets the serial state on every Register and tells the client to do the same.
        guest_n = 0;
        qemu_serial = -1;
        guest_clip = GuestClip.NOTHING;
        call_client_register.begin ();
    }

    private async void call_client_register () {
        try {
            yield get_client ().register_client ();
        } catch (Error e) {
            warning ("fake qemu: client Register failed: %s", e.message);
        }
    }

    private ClipboardPeer get_client () throws Error {
        if (client == null) {
            client = conn.get_proxy_sync (null, "/org/qemu/Display1/Clipboard", DBusProxyFlags.DO_NOT_LOAD_PROPERTIES, null);
        }
        return client;
    }

    public void on_client_grab (uint selection, uint serial, string[] mimes) throws Error {
        if (!registered) {
            throw new IOError.FAILED ("Unregistered caller");
        }
        grabs_received++;
        last_grab_serial = serial;
        if (serial < qemu_serial) {
            return;    // QEMU drops it
        }
        qemu_serial = serial;
        if (!(CLIP_TEXT in mimes)) {
            return;
        }
        // Forwarded unchanged to spice-vdagentd:
        if (serial == guest_n - 1) {
            guest_clip = GuestClip.HOST;       // the client wins the tie
        } else if (serial == guest_n) {
            guest_n++;
            guest_clip = GuestClip.HOST;
        } else {
            guest_discards++;                  // "grab discard, serial %u != session serial %u"
        }
    }

    public void on_client_release () throws Error {
        if (!registered) {
            throw new IOError.FAILED ("Unregistered caller");
        }
        releases_received++;
        if (guest_clip == GuestClip.HOST) {
            guest_clip = GuestClip.NOTHING;
        }
    }

    public async void on_client_request (out string reply_mime, out uint8[] data) throws Error {
        reply_mime = "";
        data = new uint8[0];
        if (!registered) {
            throw new IOError.FAILED ("Unregistered caller");
        }
        if (guest_clip != GuestClip.GUEST || guest_text == null) {
            throw new IOError.FAILED ("Empty clipboard");
        }
        if (request_delay_ms > 0) {
            Timeout.add (request_delay_ms, on_client_request.callback);
            yield;
        }
        reply_mime = CLIP_TEXT;
        data = guest_text.data;
    }

    /* The user pastes inside the guest: the agent asks QEMU, which asks the client. Null when the guest has
     * nothing of the host's to paste. */
    public async string? guest_paste () {
        if (guest_clip != GuestClip.HOST) {
            return null;
        }
        try {
            string mime;
            uint8[] data;
            yield get_client ().request (0, { CLIP_TEXT }, out mime, out data);
            return ((string) data).make_valid (data.length);
        } catch (Error e) {
            last_paste_error = e.message;
            return null;
        }
    }

    public string last_paste_error = "";

    /* The user copies inside the guest. */
    public async void guest_copy (string text, int64 force_serial = -1) {
        int64 serial = force_serial >= 0 ? force_serial : guest_n;
        if (force_serial < 0) {
            guest_n++;
        }
        guest_text = text;
        guest_clip = GuestClip.GUEST;
        qemu_serial = serial;
        try {
            yield get_client ().grab (0, (uint) serial, { CLIP_TEXT });
        } catch (Error e) {
            warning ("fake qemu: client Grab failed: %s", e.message);
        }
    }

    public async void guest_release () {
        guest_clip = GuestClip.NOTHING;
        try {
            yield get_client ().release (0);
        } catch (Error e) {
            warning ("fake qemu: client Release failed: %s", e.message);
        }
    }

    /* The guest agent reconnected (login, restart): fresh counter, QEMU asks the client to restart too. */
    public void guest_reconnects () {
        on_register ();
    }
}

async DBusConnection make_connection (IOStream stream, string? guid, DBusConnectionFlags flags) throws Error {
    return yield new DBusConnection (stream, guid, flags, null, null);
}

public class Rig : Object {
    public FakeHost host = new FakeHost ();
    public FakeQemu qemu = new FakeQemu ();
    public ClipboardBridge bridge;
    public GenericArray<string> statuses = new GenericArray<string> ();
    public bool ended = false;

    public async void setup () throws Error {
        int[] fds = new int[2];
        assert_true (Posix.socketpair (Posix.AF_UNIX, Posix.SOCK_STREAM, 0, fds) == 0);
        var s_stream = SocketConnection.factory_create_connection (new Socket.from_fd (fds[0]));
        var c_stream = SocketConnection.factory_create_connection (new Socket.from_fd (fds[1]));

        DBusConnection? server = null;
        DBusConnection? client = null;
        int pending = 2;
        make_connection.begin (s_stream, DBus.generate_guid (),
            DBusConnectionFlags.AUTHENTICATION_SERVER | DBusConnectionFlags.AUTHENTICATION_ALLOW_ANONYMOUS | DBusConnectionFlags.DELAY_MESSAGE_PROCESSING,
            (o, r) => {
                try { server = make_connection.end (r); } catch (Error e) { warning ("server: %s", e.message); }
                pending--;
            });
        make_connection.begin (c_stream, null, DBusConnectionFlags.AUTHENTICATION_CLIENT | DBusConnectionFlags.DELAY_MESSAGE_PROCESSING,
            (o, r) => {
                try { client = make_connection.end (r); } catch (Error e) { warning ("client: %s", e.message); }
                pending--;
            });
        assert_true (spin (() => pending == 0));
        assert_nonnull (server);
        assert_nonnull (client);

        qemu.conn = server;
        var service = new FakeQemuService ();
        service.qemu = qemu;
        server.register_object ("/org/qemu/Display1/Clipboard", service);
        server.start_message_processing ();

        bridge = new ClipboardBridge (host);
        bridge.debounce_ms = 5;
        bridge.status.connect ((m) => { statuses.add (m); });
        bridge.ended.connect (() => { ended = true; });
        bool ok = yield bridge.attach (client);
        assert_true (ok);
        assert_true (qemu.registered);
        service_keepalive = service;
        settle (80);   // the initial session reset and announce
    }

    private FakeQemuService? service_keepalive = null;

    public async string? paste () {
        return yield qemu.guest_paste ();
    }
}

void run_setup (Rig rig) {
    bool done = false;
    rig.setup.begin ((o, r) => {
        try {
            rig.setup.end (r);
        } catch (Error e) {
            warning ("setup failed: %s", e.message);
            Test.fail ();
        }
        done = true;
    });
    assert_true (spin (() => done));
}

string? paste_now (Rig rig) {
    bool done = false;
    string? result = null;
    rig.paste.begin ((o, r) => { result = rig.paste.end (r); done = true; });
    assert_true (spin (() => done));
    return result;
}

void guest_copies (Rig rig, string text, int64 serial = -1) {
    bool done = false;
    rig.qemu.guest_copy.begin (text, serial, (o, r) => { rig.qemu.guest_copy.end (r); done = true; });
    assert_true (spin (() => done));
}

// ---- pure serial rules ----

void test_serial_rules () {
    var s = new ClipboardSync ();
    // A fresh session: the first host grab carries serial 0 (the guest agent counter starts at 0).
    assert_true (s.claim_for_host () == 0);
    assert_true (s.claim_for_host () == 1);
    assert_true (s.owner == ClipOwner.HOST);

    // A guest grab with the serial of our latest grab is a tie: the host (client) wins.
    assert_false (s.accept_guest_grab (1));
    assert_true (s.owner == ClipOwner.HOST);
    // Lower: stale.
    assert_false (s.accept_guest_grab (0));
    // Higher: the guest copied after us, and the counter follows it.
    uint gen = s.generation;
    assert_true (s.accept_guest_grab (2));
    assert_true (s.owner == ClipOwner.GUEST);
    assert_true (s.generation != gen);
    assert_true (s.next_serial == 3);
    assert_true (s.claim_for_host () == 3);

    // A jump ahead is followed.
    assert_true (s.accept_guest_grab (10));
    assert_true (s.claim_for_host () == 11);

    // Release only means something while the host owns the clipboard.
    assert_true (s.release_host ());
    assert_false (s.release_host ());
    assert_true (s.owner == ClipOwner.NONE);

    // Reset (QEMU's Register): the counter is 0 again and nobody owns anything.
    s.claim_for_host ();
    s.reset ();
    assert_true (s.owner == ClipOwner.NONE);
    assert_true (s.claim_for_host () == 0);

    // The same serial again from the guest when the guest owned the previous grab is not a tie.
    var t = new ClipboardSync ();
    assert_true (t.accept_guest_grab (0));
    assert_true (t.accept_guest_grab (0));
    t.guest_released ();
    assert_true (t.owner == ClipOwner.NONE);
}

// ---- host -> guest (issue #263) ----

void test_first_host_copy_reaches_the_guest () {
    var rig = new Rig ();
    run_setup (rig);
    rig.host.user_copies ("hello from the host");
    assert_true (spin (() => rig.qemu.guest_clip == GuestClip.HOST));
    // The regression: the first grab must carry serial 0 or spice-vdagentd drops it.
    assert_true (rig.qemu.last_grab_serial == 0);
    assert_true (rig.qemu.guest_discards == 0);
    assert_cmpstr (paste_now (rig), CompareOperator.EQ, "hello from the host");
}

void test_serials_stay_in_lockstep () {
    var rig = new Rig ();
    run_setup (rig);
    rig.host.user_copies ("A");
    assert_true (spin (() => rig.qemu.grabs_received == 1));
    settle (30);
    rig.host.user_copies ("B");
    assert_true (spin (() => rig.qemu.grabs_received == 2));
    settle (30);
    assert_cmpstr (paste_now (rig), CompareOperator.EQ, "B");

    guest_copies (rig, "G");
    assert_true (spin (() => rig.host.text == "G"));
    settle (60);
    // Host copies after the guest copied: the serial continues from the guest's.
    rig.host.user_copies ("C");
    assert_true (spin (() => rig.qemu.grabs_received == 3));
    settle (30);
    assert_cmpstr (paste_now (rig), CompareOperator.EQ, "C");
    assert_true (rig.qemu.guest_discards == 0);

    guest_copies (rig, "G2");
    assert_true (spin (() => rig.host.text == "G2"));
    assert_true (rig.qemu.guest_discards == 0);
}

void test_rapid_notifications_make_one_grab () {
    var rig = new Rig ();
    run_setup (rig);
    rig.bridge.debounce_ms = 40;
    for (int i = 0; i < 5; i++) {
        rig.host.user_copies ("x");   // GDK reports one copy several times
    }
    assert_true (spin (() => rig.qemu.grabs_received >= 1));
    settle (150);
    assert_true (rig.qemu.grabs_received == 1);
}

void test_session_reset_offers_the_host_clipboard_again () {
    var rig = new Rig ();
    run_setup (rig);
    rig.host.user_copies ("kept");
    assert_true (spin (() => rig.qemu.guest_clip == GuestClip.HOST));
    int before = rig.qemu.grabs_received;
    // The guest agent reconnects (a login, an agent restart): its counter is back at 0 and it forgot our grab.
    rig.qemu.guest_reconnects ();
    assert_true (rig.qemu.guest_clip == GuestClip.NOTHING);
    assert_true (spin (() => rig.qemu.grabs_received > before));
    assert_true (rig.qemu.last_grab_serial == 0);
    assert_true (rig.qemu.guest_clip == GuestClip.HOST);
    assert_true (rig.qemu.guest_discards == 0);
    assert_cmpstr (paste_now (rig), CompareOperator.EQ, "kept");
}

void test_clipboard_copied_before_the_agent_is_offered_on_attach () {
    var rig = new Rig ();
    rig.host.text = "copied earlier";
    run_setup (rig);
    assert_true (spin (() => rig.qemu.guest_clip == GuestClip.HOST));
    assert_cmpstr (paste_now (rig), CompareOperator.EQ, "copied earlier");
}

void test_empty_or_non_text_host_clipboard_is_released () {
    var rig = new Rig ();
    run_setup (rig);
    rig.host.user_copies ("secret");
    assert_true (spin (() => rig.qemu.guest_clip == GuestClip.HOST));
    rig.host.user_copies (null);   // an image, a file, or cleared
    assert_true (spin (() => rig.qemu.releases_received == 1));
    assert_true (rig.qemu.guest_clip == GuestClip.NOTHING);
    assert_null (paste_now (rig));
}

void test_paste_after_the_host_changed_gets_the_current_text () {
    var rig = new Rig ();
    run_setup (rig);
    rig.host.user_copies ("old");
    assert_true (spin (() => rig.qemu.guest_clip == GuestClip.HOST));
    rig.host.text = "new";   // content moves before the next grab is announced
    assert_cmpstr (paste_now (rig), CompareOperator.EQ, "new");
}

// ---- guest -> host and loop prevention ----

void test_guest_copy_reaches_the_host_without_an_echo () {
    var rig = new Rig ();
    run_setup (rig);
    guest_copies (rig, "from the guest");
    assert_true (spin (() => rig.host.text == "from the guest"));
    settle (300);
    assert_true (rig.host.writes == 1);
    assert_true (rig.bridge.host_grabs == 0);
    assert_true (rig.qemu.grabs_received == 0);   // nothing went back to the guest
    assert_true (rig.qemu.guest_clip == GuestClip.GUEST);
}

void test_late_echo_of_our_own_write_is_recognised_by_content () {
    var rig = new Rig ();
    run_setup (rig);
    rig.host.echo_later = true;    // the toolkit reports the change after our write returned
    guest_copies (rig, "no loop");
    assert_true (spin (() => rig.host.text == "no loop"));
    settle (300);
    assert_true (rig.qemu.grabs_received == 0);
}

void test_a_real_host_copy_after_a_guest_copy_is_sent () {
    var rig = new Rig ();
    run_setup (rig);
    guest_copies (rig, "guest text");
    assert_true (spin (() => rig.host.text == "guest text"));
    settle (60);
    // Copy made by the host app itself (local content, but not what the guest gave us).
    rig.host.user_copies ("host text", true);
    assert_true (spin (() => rig.qemu.grabs_received == 1));
    assert_true (rig.qemu.guest_discards == 0);
    // Then the guest copies the very same text it gave us before: the host must follow, not stay on the older copy.
    guest_copies (rig, "guest text");
    assert_true (spin (() => rig.host.text == "guest text"));
}

void test_guest_clipboard_manager_regrabbing_our_text_is_not_rewritten () {
    var rig = new Rig ();
    run_setup (rig);
    rig.host.user_copies ("host text");
    assert_true (spin (() => rig.qemu.guest_clip == GuestClip.HOST));
    assert_cmpstr (paste_now (rig), CompareOperator.EQ, "host text");
    guest_copies (rig, "host text");   // a guest clipboard manager re-owns what it just read
    settle (200);
    assert_true (rig.host.writes == 0);
}

void test_tie_goes_to_the_host () {
    var rig = new Rig ();
    run_setup (rig);
    rig.host.user_copies ("H");
    assert_true (spin (() => rig.qemu.guest_clip == GuestClip.HOST));
    // The guest copied at the same moment, with the same serial as our grab: the client wins.
    guest_copies (rig, "G", rig.qemu.last_grab_serial);
    settle (200);
    assert_cmpstr (rig.host.text, CompareOperator.EQ, "H");
    assert_true (rig.host.writes == 0);
    assert_true (rig.bridge.sync.owner == ClipOwner.HOST);
}

void test_stale_guest_grab_is_discarded () {
    var rig = new Rig ();
    run_setup (rig);
    rig.host.user_copies ("one");
    assert_true (spin (() => rig.qemu.grabs_received == 1));
    settle (30);
    rig.host.user_copies ("two");
    assert_true (spin (() => rig.qemu.grabs_received == 2));
    settle (30);
    guest_copies (rig, "stale", 0);
    settle (200);
    assert_true (rig.host.writes == 0);
    assert_true (rig.bridge.sync.owner == ClipOwner.HOST);
}

void test_a_newer_host_copy_supersedes_a_slow_guest_fetch () {
    var rig = new Rig ();
    run_setup (rig);
    rig.qemu.request_delay_ms = 250;
    guest_copies (rig, "slow guest text");
    settle (40);                         // the bridge is waiting for the guest's data
    rig.host.user_copies ("host wins");
    settle (500);
    assert_cmpstr (rig.host.text, CompareOperator.EQ, "host wins");
    assert_true (rig.host.writes == 0);
}

void test_guest_release_clears_ownership () {
    var rig = new Rig ();
    run_setup (rig);
    guest_copies (rig, "g");
    assert_true (spin (() => rig.host.text == "g"));
    bool done = false;
    rig.qemu.guest_release.begin ((o, r) => { rig.qemu.guest_release.end (r); done = true; });
    assert_true (spin (() => done && rig.bridge.sync.owner == ClipOwner.NONE));
    assert_cmpstr (rig.host.text, CompareOperator.EQ, "g");   // the host keeps the last content
}

// ---- limits and switches ----

void test_size_limit_both_ways () {
    var rig = new Rig ();
    run_setup (rig);
    rig.bridge.max_bytes = 100;
    var big = new StringBuilder ();
    for (int i = 0; i < 200; i++) {
        big.append_c ('x');
    }
    rig.host.user_copies (big.str);
    assert_true (spin (() => rig.qemu.guest_clip == GuestClip.HOST));
    assert_null (paste_now (rig));
    assert_true (rig.statuses.length == 1);
    assert_true ("limit" in rig.statuses.get (0));

    rig.host.user_copies (null);
    settle (60);
    guest_copies (rig, big.str);
    settle (250);
    assert_true (rig.host.writes == 0);
    assert_true (rig.statuses.length == 2);

    // Text exactly at the limit goes through.
    rig.bridge.max_bytes = 200;
    rig.host.user_copies (big.str);
    assert_true (spin (() => rig.qemu.guest_clip == GuestClip.HOST));
    assert_true (paste_now (rig) == big.str);
}

void test_host_to_guest_can_be_turned_off () {
    var rig = new Rig ();
    run_setup (rig);
    rig.bridge.host_to_guest = false;
    rig.host.user_copies ("private");
    settle (250);
    assert_true (rig.qemu.grabs_received == 0);
    assert_true (rig.qemu.guest_clip == GuestClip.NOTHING);

    // Turning it on offers what is on the clipboard now.
    rig.bridge.host_to_guest = true;
    assert_true (spin (() => rig.qemu.guest_clip == GuestClip.HOST));
    assert_cmpstr (paste_now (rig), CompareOperator.EQ, "private");

    // Turning it off withdraws the offer, and even a late Request is refused.
    rig.bridge.host_to_guest = false;
    assert_true (spin (() => rig.qemu.releases_received == 1));
    assert_true (rig.qemu.guest_clip == GuestClip.NOTHING);
    rig.qemu.guest_clip = GuestClip.HOST;   // a guest that ignored the release
    assert_null (paste_now (rig));
}

void test_guest_to_host_can_be_turned_off () {
    var rig = new Rig ();
    run_setup (rig);
    rig.bridge.guest_to_host = false;
    guest_copies (rig, "keep out");
    settle (250);
    assert_true (rig.host.writes == 0);
    assert_null (rig.host.text);
    // The serial still follows the guest, so a host copy afterwards is accepted by it.
    rig.host.user_copies ("fine");
    assert_true (spin (() => rig.qemu.guest_clip == GuestClip.HOST));
    assert_true (rig.qemu.guest_discards == 0);
}

void test_a_stuck_host_clipboard_does_not_hold_qemu () {
    var rig = new Rig ();
    run_setup (rig);
    rig.host.user_copies ("slow owner");
    assert_true (spin (() => rig.qemu.guest_clip == GuestClip.HOST));
    rig.host.hang = true;
    rig.bridge.provide_timeout_ms = 150;
    int64 start = get_monotonic_time ();
    assert_null (paste_now (rig));
    assert_true (get_monotonic_time () - start < 3 * 1000 * 1000);
    assert_true (rig.qemu.last_paste_error != "");
}

void test_non_text_requests_are_refused () {
    var rig = new Rig ();
    run_setup (rig);
    rig.host.user_copies ("text");
    assert_true (spin (() => rig.qemu.guest_clip == GuestClip.HOST));
    bool done = false;
    string? error = null;
    rig.qemu.client.request.begin (0, { "image/png" }, (o, r) => {
        try {
            string m;
            uint8[] d;
            rig.qemu.client.request.end (r, out m, out d);
        } catch (Error e) {
            error = e.message;
        }
        done = true;
    });
    assert_true (spin (() => done));
    assert_nonnull (error);
}

void test_connection_loss_ends_the_bridge () {
    var rig = new Rig ();
    run_setup (rig);
    rig.qemu.conn.close.begin (null);
    assert_true (spin (() => rig.ended));
    assert_false (rig.bridge.active);
    rig.host.user_copies ("after");   // must not crash
    settle (100);
}

void test_settings_round_trip () {
    string dir = "";
    try {
        dir = DirUtils.make_tmp ("ml-clip-XXXXXX");
    } catch (Error e) {
        Test.fail ();
    }
    string path = Path.build_filename (dir, "machine-lab", "settings.ini");
    var s = new ClipboardSettings ();
    assert_true (s.host_to_guest);
    assert_true (s.guest_to_host);
    s.host_to_guest = false;
    assert_true (s.save_to (path));
    var t = new ClipboardSettings ();
    t.load_from (path);
    assert_false (t.host_to_guest);
    assert_true (t.guest_to_host);
    // A missing or broken file keeps the defaults (both on).
    var u = new ClipboardSettings ();
    u.load_from (Path.build_filename (dir, "nope.ini"));
    assert_true (u.host_to_guest && u.guest_to_host);
    try {
        FileUtils.set_contents (path, "[clipboard\nbroken");
    } catch (Error e) {
        Test.fail ();
    }
    var v = new ClipboardSettings ();
    v.load_from (path);
    assert_true (v.host_to_guest && v.guest_to_host);
}

int main (string[] args) {
    Test.init (ref args);
    Test.add_func ("/clipsync/serial-rules", test_serial_rules);
    Test.add_func ("/clipsync/settings", test_settings_round_trip);
    Test.add_func ("/clipboard/host-to-guest/first-copy", test_first_host_copy_reaches_the_guest);
    Test.add_func ("/clipboard/host-to-guest/serials-in-lockstep", test_serials_stay_in_lockstep);
    Test.add_func ("/clipboard/host-to-guest/debounce", test_rapid_notifications_make_one_grab);
    Test.add_func ("/clipboard/host-to-guest/session-reset", test_session_reset_offers_the_host_clipboard_again);
    Test.add_func ("/clipboard/host-to-guest/offered-on-attach", test_clipboard_copied_before_the_agent_is_offered_on_attach);
    Test.add_func ("/clipboard/host-to-guest/release", test_empty_or_non_text_host_clipboard_is_released);
    Test.add_func ("/clipboard/host-to-guest/current-text", test_paste_after_the_host_changed_gets_the_current_text);
    Test.add_func ("/clipboard/guest-to-host/no-echo", test_guest_copy_reaches_the_host_without_an_echo);
    Test.add_func ("/clipboard/guest-to-host/late-echo", test_late_echo_of_our_own_write_is_recognised_by_content);
    Test.add_func ("/clipboard/guest-to-host/host-copy-after", test_a_real_host_copy_after_a_guest_copy_is_sent);
    Test.add_func ("/clipboard/guest-to-host/manager-regrab", test_guest_clipboard_manager_regrabbing_our_text_is_not_rewritten);
    Test.add_func ("/clipboard/races/tie", test_tie_goes_to_the_host);
    Test.add_func ("/clipboard/races/stale", test_stale_guest_grab_is_discarded);
    Test.add_func ("/clipboard/races/superseded-fetch", test_a_newer_host_copy_supersedes_a_slow_guest_fetch);
    Test.add_func ("/clipboard/races/guest-release", test_guest_release_clears_ownership);
    Test.add_func ("/clipboard/limits/size", test_size_limit_both_ways);
    Test.add_func ("/clipboard/limits/host-to-guest-switch", test_host_to_guest_can_be_turned_off);
    Test.add_func ("/clipboard/limits/guest-to-host-switch", test_guest_to_host_can_be_turned_off);
    Test.add_func ("/clipboard/limits/stuck-host", test_a_stuck_host_clipboard_does_not_hold_qemu);
    Test.add_func ("/clipboard/limits/non-text", test_non_text_requests_are_refused);
    Test.add_func ("/clipboard/connection-loss", test_connection_loss_ends_the_bridge);
    return Test.run ();
}
