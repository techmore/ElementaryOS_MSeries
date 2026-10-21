/* Display stream tests: pixel format conversion, the resize debouncing rules, and the real DisplayBridge
 * talking D-Bus over socketpairs to a fake QEMU that serves the VM and Console objects, takes
 * RegisterListener(fd) and then calls the listener with Scanout, Update, Disable and CursorDefine the
 * way ui/dbus-listener.c does. No display, no VM. */

public delegate bool Cond ();

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

void settle (uint ms = 200) {
    spin (() => false, ms);
}

// ---- pixel formats -------------------------------------------------------------------------------

void test_format_table () {
    var f = PixelFormat.lookup (PixelFormat.X8R8G8B8);
    assert_nonnull (f);
    assert_true (f.bytes_per_pixel == 4 && f.r_shift == 16 && f.g_shift == 8 && f.b_shift == 0);
    f = PixelFormat.lookup (PixelFormat.X8B8G8R8);
    assert_true (f.r_shift == 0 && f.g_shift == 8 && f.b_shift == 16);
    f = PixelFormat.lookup (PixelFormat.B8G8R8X8);
    assert_true (f.b_shift == 24 && f.g_shift == 16 && f.r_shift == 8);
    f = PixelFormat.lookup (PixelFormat.R8G8B8A8);
    assert_true (f.r_shift == 24 && f.g_shift == 16 && f.b_shift == 8);
    f = PixelFormat.lookup (PixelFormat.R8G8B8);
    assert_true (f.bytes_per_pixel == 3 && f.r_shift == 16 && f.b_shift == 0);
    f = PixelFormat.lookup (PixelFormat.R5G6B5);
    assert_true (f.bytes_per_pixel == 2 && f.r_shift == 11 && f.g_shift == 5 && f.b_shift == 0
        && f.r_bits == 5 && f.g_bits == 6 && f.b_bits == 5);
    f = PixelFormat.lookup (PixelFormat.B5G6R5);
    assert_true (f.b_shift == 11 && f.r_shift == 0);

    assert_null (PixelFormat.lookup (0));
    assert_null (PixelFormat.lookup (0x08010800));   // a8, not a colour format
    assert_null (PixelFormat.lookup (0x20040888));   // type 4 (indexed/colour)
    assert_null (PixelFormat.lookup (0x40020888));   // 64 bit
    assert_null (PixelFormat.lookup (0x20020088));   // no red channel
}

void test_scanout_x8r8g8b8 () {
    var s = new ScreenBuffer ();
    // 2x2, B G R x: red, green / blue, white
    uint8[] d = {
        0x00, 0x00, 0xff, 0x00,   0x00, 0xff, 0x00, 0x00,
        0xff, 0x00, 0x00, 0x00,   0xff, 0xff, 0xff, 0x00
    };
    assert_true (s.scanout (2, 2, 8, PixelFormat.X8R8G8B8, d));
    assert_true (s.width == 2 && s.height == 2 && s.enabled);
    assert_true (s.pixel_at (0, 0) == 0xffff0000);
    assert_true (s.pixel_at (1, 0) == 0xff00ff00);
    assert_true (s.pixel_at (0, 1) == 0xff0000ff);
    assert_true (s.pixel_at (1, 1) == 0xffffffff);
    // The source padding byte (x) must not leak into alpha.
    assert_true ((s.pixel_at (0, 0) >> 24) == 0xff);
    var snap = s.snapshot ();
    assert_true (snap.length == 16 && snap[2] == 0xff && snap[3] == 0xff);
    // The snapshot is a private copy.
    snap[0] = 0x55;
    assert_true (s.pixel_at (0, 0) == 0xffff0000);
}

void test_alpha_is_always_opaque () {
    var s = new ScreenBuffer ();
    uint8[] d = { 0x10, 0x20, 0x30, 0x00,   0x10, 0x20, 0x30, 0x80 };
    assert_true (s.scanout (2, 1, 8, PixelFormat.A8R8G8B8, d));
    assert_true (s.pixel_at (0, 0) == 0xff302010);
    assert_true (s.pixel_at (1, 0) == 0xff302010);
}

void test_byte_order_variants () {
    var s = new ScreenBuffer ();
    // x8b8g8r8: bytes R G B x
    uint8[] rgbx = { 0x11, 0x22, 0x33, 0x00 };
    assert_true (s.scanout (1, 1, 4, PixelFormat.X8B8G8R8, rgbx));
    assert_true (s.pixel_at (0, 0) == 0xff112233);
    // b8g8r8x8: bytes x R G B
    uint8[] xrgb = { 0x00, 0x11, 0x22, 0x33 };
    assert_true (s.scanout (1, 1, 4, PixelFormat.B8G8R8X8, xrgb));
    assert_true (s.pixel_at (0, 0) == 0xff112233);
    // r8g8b8x8: bytes x B G R
    uint8[] xbgr = { 0x00, 0x33, 0x22, 0x11 };
    assert_true (s.scanout (1, 1, 4, PixelFormat.R8G8B8X8, xbgr));
    assert_true (s.pixel_at (0, 0) == 0xff112233);
    // 24 bit r8g8b8: bytes B G R
    uint8[] bgr24 = { 0x33, 0x22, 0x11 };
    assert_true (s.scanout (1, 1, 3, PixelFormat.R8G8B8, bgr24));
    assert_true (s.pixel_at (0, 0) == 0xff112233);
    // 24 bit b8g8r8: bytes R G B
    uint8[] rgb24 = { 0x11, 0x22, 0x33 };
    assert_true (s.scanout (1, 1, 3, PixelFormat.B8G8R8, rgb24));
    assert_true (s.pixel_at (0, 0) == 0xff112233);
}

void test_rgb565 () {
    var s = new ScreenBuffer ();
    // little endian words: white, red, green, blue
    uint8[] d = { 0xff, 0xff,   0x00, 0xf8,   0xe0, 0x07,   0x1f, 0x00 };
    assert_true (s.scanout (4, 1, 8, PixelFormat.R5G6B5, d));
    assert_true (s.pixel_at (0, 0) == 0xffffffff);
    assert_true (s.pixel_at (1, 0) == 0xffff0000);
    assert_true (s.pixel_at (2, 0) == 0xff00ff00);
    assert_true (s.pixel_at (3, 0) == 0xff0000ff);
    // b5g6r5 swaps red and blue
    assert_true (s.scanout (4, 1, 8, PixelFormat.B5G6R5, d));
    assert_true (s.pixel_at (1, 0) == 0xff0000ff);
    assert_true (s.pixel_at (3, 0) == 0xffff0000);
}

void test_stride_padding () {
    var s = new ScreenBuffer ();
    // 2 pixels wide, rows 12 bytes apart (4 bytes of padding per row)
    uint8[] d = new uint8[24];
    for (int i = 0; i < 24; i++) {
        d[i] = 0xee;   // padding garbage
    }
    d[0] = 1; d[1] = 2; d[2] = 3; d[3] = 0;
    d[4] = 4; d[5] = 5; d[6] = 6; d[7] = 0;
    d[12] = 7; d[13] = 8; d[14] = 9; d[15] = 0;
    d[16] = 10; d[17] = 11; d[18] = 12; d[19] = 0;
    assert_true (s.scanout (2, 2, 12, PixelFormat.X8R8G8B8, d));
    assert_true (s.pixel_at (0, 0) == 0xff030201);
    assert_true (s.pixel_at (1, 0) == 0xff060504);
    assert_true (s.pixel_at (0, 1) == 0xff090807);
    assert_true (s.pixel_at (1, 1) == 0xff0c0b0a);
}

void test_update_region () {
    var s = new ScreenBuffer ();
    uint8[] black = new uint8[4 * 4 * 4];
    assert_true (s.scanout (4, 4, 16, PixelFormat.X8R8G8B8, black));
    int x, y, w, h;
    assert_true (s.take_dirty (out x, out y, out w, out h));
    assert_true (x == 0 && y == 0 && w == 4 && h == 4);
    assert_false (s.take_dirty (out x, out y, out w, out h));

    // 2x1 white patch at (1, 2)
    uint8[] patch = { 0xff, 0xff, 0xff, 0, 0xff, 0xff, 0xff, 0 };
    assert_true (s.update (1, 2, 2, 1, 8, PixelFormat.X8R8G8B8, patch));
    assert_true (s.pixel_at (1, 2) == 0xffffffff);
    assert_true (s.pixel_at (2, 2) == 0xffffffff);
    assert_true (s.pixel_at (0, 2) == 0xff000000);
    assert_true (s.pixel_at (3, 2) == 0xff000000);
    assert_true (s.take_dirty (out x, out y, out w, out h));
    assert_true (x == 1 && y == 2 && w == 2 && h == 1);

    // Two updates before the consumer looks: the dirty rectangle is their union.
    s.update (0, 0, 1, 1, 4, PixelFormat.X8R8G8B8, patch);
    s.update (3, 3, 1, 1, 4, PixelFormat.X8R8G8B8, patch);
    assert_true (s.take_dirty (out x, out y, out w, out h));
    assert_true (x == 0 && y == 0 && w == 4 && h == 4);
}

void test_update_is_clipped_and_checked () {
    var s = new ScreenBuffer ();
    uint8[] black = new uint8[3 * 3 * 4];
    assert_true (s.scanout (3, 3, 12, PixelFormat.X8R8G8B8, black));
    int x, y, w, h;
    s.take_dirty (out x, out y, out w, out h);

    // A 2x2 patch whose top left corner is at (-1, -1): only its bottom right pixel lands, at (0, 0).
    uint8[] p = {
        1, 0, 0, 0,   2, 0, 0, 0,
        3, 0, 0, 0,   4, 0, 0, 0
    };
    assert_true (s.update (-1, -1, 2, 2, 8, PixelFormat.X8R8G8B8, p));
    assert_true (s.pixel_at (0, 0) == 0xff000004);
    assert_true (s.pixel_at (1, 0) == 0xff000000);
    assert_true (s.take_dirty (out x, out y, out w, out h));
    assert_true (x == 0 && y == 0 && w == 1 && h == 1);

    // Hanging over the right edge.
    assert_true (s.update (2, 2, 2, 2, 8, PixelFormat.X8R8G8B8, p));
    assert_true (s.pixel_at (2, 2) == 0xff000001);

    // Entirely outside, empty, too little data, or a stride smaller than a row: rejected, nothing changes.
    s.take_dirty (out x, out y, out w, out h);
    uint64 v = s.version;
    assert_false (s.update (3, 0, 2, 2, 8, PixelFormat.X8R8G8B8, p));
    assert_false (s.update (0, 0, 0, 2, 8, PixelFormat.X8R8G8B8, p));
    assert_false (s.update (0, 0, 3, 3, 12, PixelFormat.X8R8G8B8, p));
    assert_false (s.update (0, 0, 2, 2, 4, PixelFormat.X8R8G8B8, p));
    assert_false (s.update (0, 0, 2, 2, 8, 0xdeadbeefu, p));
    assert_true (s.version == v);
    assert_false (s.take_dirty (out x, out y, out w, out h));
}

void test_scanout_is_checked () {
    var s = new ScreenBuffer ();
    uint8[] small = new uint8[16];
    assert_false (s.scanout (0, 4, 16, PixelFormat.X8R8G8B8, small));
    assert_false (s.scanout (4, 4, 16, PixelFormat.X8R8G8B8, small));      // data for 1 row only
    assert_false (s.scanout (4, 1, 8, PixelFormat.X8R8G8B8, small));       // stride smaller than a row
    assert_false (s.scanout (4, 1, 16, 0x1234, small));                    // unknown format
    assert_false (s.scanout (100000, 1, 400000, PixelFormat.X8R8G8B8, small));
    assert_false (s.enabled);
    // An update with no screen is rejected too.
    assert_false (s.update (0, 0, 1, 1, 4, PixelFormat.X8R8G8B8, small));
    // A good one still works afterwards, and a resize replaces the picture.
    assert_true (s.scanout (4, 1, 16, PixelFormat.X8R8G8B8, small));
    uint8[] bigger = new uint8[5 * 2 * 4];
    assert_true (s.scanout (5, 2, 20, PixelFormat.X8R8G8B8, bigger));
    assert_true (s.width == 5 && s.height == 2 && s.snapshot ().length == 40);
    s.disable ();
    assert_false (s.enabled);
    assert_false (s.update (0, 0, 1, 1, 4, PixelFormat.X8R8G8B8, small));
    assert_true (s.width == 5);   // the last picture stays
}

void test_full_hd_conversion_is_fast_enough () {
    var s = new ScreenBuffer ();
    int w = 1920;
    int h = 1080;
    uint8[] frame = new uint8[w * h * 4];
    for (int i = 0; i < frame.length; i += 4) {
        frame[i] = (uint8) (i >> 8);
    }
    int64 t0 = get_monotonic_time ();
    for (int i = 0; i < 5; i++) {
        assert_true (s.scanout (w, h, w * 4, PixelFormat.X8R8G8B8, frame));
    }
    int64 same = (get_monotonic_time () - t0) / 5000;
    t0 = get_monotonic_time ();
    uint8[] frame565 = new uint8[w * h * 2];
    assert_true (s.scanout (w, h, w * 2, PixelFormat.R5G6B5, frame565));
    int64 slow = (get_monotonic_time () - t0) / 1000;
    message ("1080p x8r8g8b8 scanout %lld ms, r5g6b5 %lld ms", same, slow);
    // Generous bounds: a frame must convert well inside the 16 ms of one displayed frame on a normal build,
    // and not minutes even on a loaded CI runner.
    assert_true (same < 250);
    assert_true (slow < 2000);
}

// ---- resize rules --------------------------------------------------------------------------------

const int64 MS = 1000;

void test_snap_and_limits () {
    var p = new ResizePlanner ();
    int w, h;
    p.snap (1283, 801, out w, out h);
    assert_true (w == 1280 && h == 800);
    p.snap (100, 100, out w, out h);
    assert_true (w == 640 && h == 480);
    p.snap (20000, 9000, out w, out h);
    assert_true (w == 7680 && h == 4320);
    assert_true (ResizePlanner.mm_for (1920) == 508);
    assert_true (ResizePlanner.mm_for (0) == 1);
    assert_true (ResizePlanner.mm_for (2000000) == 65535);
}

void test_resize_waits_for_the_window_to_settle () {
    var p = new ResizePlanner ();
    p.guest_size (1280, 800);
    int w, h;
    int64 t = 0;
    // A window drag: a new size every 20 ms for a second.
    for (int i = 0; i < 50; i++) {
        p.request (1300 + i * 8, 900, t);
        assert_false (p.due (t, out w, out h));
        t += 20 * MS;
    }
    // Still inside the quiet period after the last change.
    assert_false (p.due (t + 100 * MS, out w, out h));
    assert_false (p.due (t + 300 * MS, out w, out h));
    // Then exactly one send.
    int64 last = t - 20 * MS;
    assert_true (p.due (last + 400 * MS, out w, out h));
    assert_true (w == 1688 && h == 896);
    p.sent (w, h, last + 400 * MS);
    assert_false (p.due (last + 5000 * MS, out w, out h));
}

void test_resize_is_rate_limited () {
    var p = new ResizePlanner ();
    int w, h;
    p.request (1600, 900, 0);
    assert_true (p.due (500 * MS, out w, out h));
    p.sent (w, h, 500 * MS);
    // Another size right after, settled: waits for the minimum gap.
    p.request (1200, 700, 600 * MS);
    assert_false (p.due (1100 * MS, out w, out h));
    assert_false (p.due (1400 * MS, out w, out h));
    assert_true (p.due (1500 * MS, out w, out h));
    assert_true (w == 1200 && h == 696);
}

void test_small_changes_and_matching_sizes_are_ignored () {
    var p = new ResizePlanner ();
    int w, h;
    // The guest is already at this size: nothing to send.
    p.guest_size (1280, 800);
    p.request (1283, 805, 0);
    assert_false (p.due (500 * MS, out w, out h));
    assert_false (p.due (5000 * MS, out w, out h));

    // A few pixels either way after a send is jitter.
    p.request (1600, 900, 10000 * MS);
    assert_true (p.due (10500 * MS, out w, out h));
    p.sent (w, h, 10500 * MS);
    p.request (1608, 904, 20000 * MS);
    assert_false (p.due (21000 * MS, out w, out h));
    p.request (1640, 904, 22000 * MS);
    assert_true (p.due (23000 * MS, out w, out h));
}

void test_a_guest_that_ignores_the_request_is_not_asked_in_a_loop () {
    var p = new ResizePlanner ();
    int w, h;
    p.guest_size (1280, 800);
    p.request (1600, 900, 0);
    assert_true (p.due (500 * MS, out w, out h));
    p.sent (w, h, 500 * MS);
    // The guest keeps showing 1280x800 (it cannot change): same window, same wanted size, no new request.
    p.guest_size (1280, 800);
    for (int i = 0; i < 10; i++) {
        p.request (1600, 900, (1000 + i * 1000) * MS);
        assert_false (p.due ((2000 + i * 1000) * MS, out w, out h));
    }
}

void test_reset_after_a_restart () {
    var p = new ResizePlanner ();
    int w, h;
    p.request (1600, 900, 0);
    assert_true (p.due (500 * MS, out w, out h));
    p.sent (w, h, 500 * MS);
    p.reset ();
    p.guest_size (1024, 768);   // the machine restarted at its own default size
    p.request (1600, 900, 100000 * MS);
    assert_true (p.due (101000 * MS, out w, out h));
    assert_true (w == 1600 && h == 896);
}

void test_ignores_a_hidden_window () {
    var p = new ResizePlanner ();
    int w, h;
    p.request (0, 0, 0);
    p.request (-5, 300, 0);
    assert_false (p.due (10000 * MS, out w, out h));
}

// ---- the fake QEMU -------------------------------------------------------------------------------

[DBus (name = "org.qemu.Display1.VM")]
public class FakeVm : Object {
    [DBus (name = "ConsoleIDs")]
    public uint[] console_ids {
        owned get { return { 0, 1 }; }
    }

    public string name {
        owned get { return "fake"; }
    }

    public string[] interfaces {
        owned get { return new string[0]; }
    }
}

[DBus (name = "org.qemu.Display1.Console")]
public class FakeConsole : Object {
    public weak FakeQemu qemu;
    public string label_text = "VGA";
    public string kind = "Graphic";

    [DBus (name = "Type")]
    public string console_type {
        owned get { return kind; }
    }

    [DBus (name = "Label")]
    public string console_label {
        owned get { return label_text; }
    }

    public string[] interfaces {
        owned get { return new string[0]; }
    }

    public void register_listener (Socket sock) throws Error {
        qemu.on_register_listener (sock, this);
    }

    [DBus (name = "SetUIInfo")]
    public void set_ui_info (uint16 width_mm, uint16 height_mm, int xoff, int yoff, uint width, uint height) throws Error {
        qemu.on_set_ui_info (width_mm, height_mm, xoff, yoff, width, height);
    }
}

public class UiInfoCall : Object {
    public int width_mm;
    public int height_mm;
    public int width;
    public int height;
}

async DBusConnection make_connection (IOStream stream, string? guid, DBusConnectionFlags flags) throws Error {
    return yield new DBusConnection (stream, guid, flags, null, null);
}

public class FakeQemu : Object {
    public DBusConnection conn;
    public DBusConnection? listener = null;
    public int registrations = 0;
    public string? listener_interfaces = null;
    public GenericArray<UiInfoCall> ui_info = new GenericArray<UiInfoCall> ();
    public bool supports_ui_info = true;
    public int replies = 0;
    private FakeConsole console0 = new FakeConsole ();
    private FakeConsole console1 = new FakeConsole ();
    private FakeVm vm = new FakeVm ();

    public void export_objects (bool graphic_console) throws Error {
        console0.qemu = this;
        console1.qemu = this;
        console0.kind = graphic_console ? "Text" : "Text";
        console1.kind = graphic_console ? "Graphic" : "Text";
        conn.register_object ("/org/qemu/Display1/VM", vm);
        conn.register_object ("/org/qemu/Display1/Console_0", console0);
        conn.register_object ("/org/qemu/Display1/Console_1", console1);
    }

    public void on_register_listener (Socket sock, FakeConsole which) throws Error {
        registrations++;
        var stream = SocketConnection.factory_create_connection (sock);
        // QEMU is the D-Bus server on the listener socket; it does this right after replying.
        make_connection.begin (stream, DBus.generate_guid (), DBusConnectionFlags.AUTHENTICATION_SERVER
            | DBusConnectionFlags.AUTHENTICATION_ALLOW_ANONYMOUS, (o, r) => {
            try {
                listener = make_connection.end (r);
                read_interfaces.begin ();
            } catch (Error e) {
                warning ("fake qemu listener: %s", e.message);
            }
        });
    }

    private async void read_interfaces () {
        try {
            var reply = yield listener.call (null, "/org/qemu/Display1/Listener", "org.freedesktop.DBus.Properties", "Get",
                new Variant ("(ss)", "org.qemu.Display1.Listener", "Interfaces"), new VariantType ("(v)"), DBusCallFlags.NONE, 5000);
            Variant v;
            reply.get ("(v)", out v);
            listener_interfaces = string.joinv (",", v.dup_strv ());
        } catch (Error e) {
            listener_interfaces = "error: " + e.message;
        }
    }

    public void on_set_ui_info (uint16 width_mm, uint16 height_mm, int xoff, int yoff, uint width, uint height) throws Error {
        if (!supports_ui_info) {
            throw new IOError.NOT_SUPPORTED ("SetUIInfo is not supported");
        }
        var c = new UiInfoCall ();
        c.width_mm = width_mm;
        c.height_mm = height_mm;
        c.width = (int) width;
        c.height = (int) height;
        ui_info.add (c);
    }

    // What QEMU's display listener sends.

    private Variant ay (uint8[] data) {
        return new Variant.from_bytes (new VariantType ("ay"), new Bytes (data), true);
    }

    private void call_listener (string method, Variant params) {
        listener.call.begin (null, "/org/qemu/Display1/Listener", "org.qemu.Display1.Listener", method, params,
            null, DBusCallFlags.NONE, -1, null, (o, r) => {
                try {
                    listener.call.end (r);
                    replies++;
                } catch (Error e) {
                    warning ("listener %s: %s", method, e.message);
                }
            });
    }

    public void scanout (uint w, uint h, uint stride, uint format, uint8[] data) {
        call_listener ("Scanout", new Variant.tuple ({
            new Variant.uint32 (w), new Variant.uint32 (h), new Variant.uint32 (stride), new Variant.uint32 (format), ay (data)
        }));
    }

    public void update (int x, int y, int w, int h, uint stride, uint format, uint8[] data) {
        call_listener ("Update", new Variant.tuple ({
            new Variant.int32 (x), new Variant.int32 (y), new Variant.int32 (w), new Variant.int32 (h),
            new Variant.uint32 (stride), new Variant.uint32 (format), ay (data)
        }));
    }

    public void disable () {
        call_listener ("Disable", new Variant.tuple ({}));
    }

    public void mouse_set (int x, int y, int on) {
        call_listener ("MouseSet", new Variant.tuple ({ new Variant.int32 (x), new Variant.int32 (y), new Variant.int32 (on) }));
    }

    public void cursor_define (int w, int h, int hot_x, int hot_y, uint8[] data) {
        call_listener ("CursorDefine", new Variant.tuple ({
            new Variant.int32 (w), new Variant.int32 (h), new Variant.int32 (hot_x), new Variant.int32 (hot_y), ay (data)
        }));
    }
}

public class Rig : Object {
    public FakeQemu qemu = new FakeQemu ();
    public DisplayBridge bridge = new DisplayBridge ();
    public DBusConnection? control = null;
    public int frames = 0;
    public int cursors = 0;
    public CursorShape? last_cursor = null;
    public bool ended = false;

    public async void setup (bool graphic_console = true, bool attach_bridge = true) throws Error {
        int[] fds = new int[2];
        assert_true (Posix.socketpair (Posix.AF_UNIX, Posix.SOCK_STREAM, 0, fds) == 0);
        var s_stream = SocketConnection.factory_create_connection (new Socket.from_fd (fds[0]));
        var c_stream = SocketConnection.factory_create_connection (new Socket.from_fd (fds[1]));
        DBusConnection? server = null;
        int pending = 2;
        make_connection.begin (s_stream, DBus.generate_guid (),
            DBusConnectionFlags.AUTHENTICATION_SERVER | DBusConnectionFlags.AUTHENTICATION_ALLOW_ANONYMOUS, (o, r) => {
            try { server = make_connection.end (r); } catch (Error e) { warning ("server: %s", e.message); }
            pending--;
        });
        make_connection.begin (c_stream, null, DBusConnectionFlags.AUTHENTICATION_CLIENT, (o, r) => {
            try { control = make_connection.end (r); } catch (Error e) { warning ("client: %s", e.message); }
            pending--;
        });
        assert_true (spin (() => pending == 0));
        assert_nonnull (server);
        assert_nonnull (control);
        qemu.conn = server;
        qemu.export_objects (graphic_console);

        bridge.frame_changed.connect (() => { frames++; });
        bridge.cursor_changed.connect ((s) => { cursors++; last_cursor = s; });
        bridge.ended.connect (() => { ended = true; });
        if (attach_bridge) {
            bool ok = yield bridge.attach (control);
            if (!ok) {
                warning ("attach failed: %s", bridge.failure);
            }
            assert_true (ok);
            assert_true (spin (() => qemu.listener != null && qemu.listener_interfaces != null));
        }
    }
}

void run_setup (Rig rig, bool graphic = true, bool attach_bridge = true) {
    bool done = false;
    rig.setup.begin (graphic, attach_bridge, (o, r) => {
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

void test_bridge_finds_the_graphic_console_and_registers () {
    var rig = new Rig ();
    run_setup (rig);
    assert_true (rig.qemu.registrations == 1);
    assert_true (rig.bridge.active);
    // No extra interfaces: QEMU keeps sending plain pixel copies we can read.
    assert_cmpstr (rig.qemu.listener_interfaces, CompareOperator.EQ, "");
}

void test_scanout_and_updates_reach_the_screen () {
    var rig = new Rig ();
    run_setup (rig);
    uint8[] red = new uint8[4 * 2 * 4];
    for (int i = 0; i < red.length; i += 4) {
        red[i + 2] = 0xff;
    }
    rig.qemu.scanout (4, 2, 16, PixelFormat.X8R8G8B8, red);
    assert_true (spin (() => rig.bridge.scanouts == 1));
    assert_true (rig.frames == 1);
    assert_true (rig.bridge.screen.width == 4 && rig.bridge.screen.height == 2);
    assert_true (rig.bridge.screen.pixel_at (3, 1) == 0xffff0000);

    uint8[] green = { 0x00, 0xff, 0x00, 0x00 };
    rig.qemu.update (1, 1, 1, 1, 4, PixelFormat.X8R8G8B8, green);
    assert_true (spin (() => rig.bridge.updates == 1));
    assert_true (rig.bridge.screen.pixel_at (1, 1) == 0xff00ff00);
    assert_true (rig.bridge.screen.pixel_at (0, 1) == 0xffff0000);
    assert_true (rig.frames == 2);
}

void test_guest_resolution_change_is_followed () {
    var rig = new Rig ();
    run_setup (rig);
    rig.qemu.scanout (2, 2, 8, PixelFormat.X8R8G8B8, new uint8[16]);
    assert_true (spin (() => rig.bridge.scanouts == 1));
    rig.qemu.scanout (3, 1, 12, PixelFormat.X8R8G8B8, new uint8[12]);
    assert_true (spin (() => rig.bridge.scanouts == 2));
    assert_true (rig.bridge.screen.width == 3 && rig.bridge.screen.height == 1);
}

void test_large_frame_goes_through () {
    var rig = new Rig ();
    run_setup (rig);
    int w = 1920;
    int h = 1080;
    uint8[] frame = new uint8[w * h * 4];
    for (int i = 0; i < frame.length; i += 4) {
        frame[i] = 0x40;
        frame[i + 1] = 0x80;
        frame[i + 2] = 0xc0;
    }
    int64 t0 = get_monotonic_time ();
    rig.qemu.scanout (w, h, w * 4, PixelFormat.X8R8G8B8, frame);
    assert_true (spin (() => rig.bridge.scanouts == 1, 10000));
    message ("1080p Scanout over D-Bus: %lld ms", (get_monotonic_time () - t0) / 1000);
    assert_true (rig.bridge.screen.pixel_at (1919, 1079) == 0xffc08040);
}

void test_bad_data_is_counted_and_ignored () {
    var rig = new Rig ();
    run_setup (rig);
    rig.qemu.scanout (4, 4, 16, PixelFormat.X8R8G8B8, new uint8[8]);        // claims 64 bytes, sends 8
    rig.qemu.scanout (2, 2, 8, 0xdeadbeefu, new uint8[16]);                  // unknown format
    rig.qemu.update (0, 0, 1, 1, 4, PixelFormat.X8R8G8B8, new uint8[4]);    // update before any screen
    assert_true (spin (() => rig.bridge.rejected == 3));
    assert_true (rig.bridge.scanouts == 0 && rig.frames == 0);
    // The connection is still good.
    rig.qemu.scanout (1, 1, 4, PixelFormat.X8R8G8B8, new uint8[4]);
    assert_true (spin (() => rig.bridge.scanouts == 1));
}

void test_disable_and_cursor () {
    var rig = new Rig ();
    run_setup (rig);
    rig.qemu.scanout (1, 1, 4, PixelFormat.X8R8G8B8, new uint8[4]);
    assert_true (spin (() => rig.bridge.scanouts == 1));
    rig.qemu.disable ();
    assert_true (spin (() => !rig.bridge.screen.enabled));
    assert_true (rig.bridge.screen.width == 1);

    // A 2x2 cursor, B G R A, with the hot spot in the middle; the top left pixel is opaque.
    uint8[] c = new uint8[16];
    c[0] = 0x10; c[1] = 0x20; c[2] = 0x30; c[3] = 0xff;
    rig.qemu.cursor_define (2, 2, 1, 1, c);
    assert_true (spin (() => rig.cursors == 1));
    assert_true (rig.last_cursor.width == 2 && rig.last_cursor.hot_x == 1 && rig.last_cursor.hot_y == 1);
    assert_true (rig.last_cursor.data.length == 16 && rig.last_cursor.data[2] == 0x30);
    assert_false (rig.last_cursor.is_blank ());

    // Fully transparent means "no pointer".
    rig.qemu.cursor_define (2, 2, 0, 0, new uint8[16]);
    assert_true (spin (() => rig.cursors == 2));
    assert_true (rig.last_cursor.is_blank ());

    // Nonsense sizes are dropped; MouseSet is accepted.
    rig.qemu.cursor_define (100000, 100000, 0, 0, new uint8[16]);
    rig.qemu.cursor_define (4, 4, 0, 0, new uint8[16]);
    rig.qemu.mouse_set (10, 10, 1);
    settle (200);
    assert_true (rig.cursors == 2);
}

void test_resize_sends_ui_info () {
    var rig = new Rig ();
    run_setup (rig);
    bool done = false;
    bool ok = false;
    rig.bridge.resize.begin (1920, 1080, (o, r) => { ok = rig.bridge.resize.end (r); done = true; });
    assert_true (spin (() => done));
    assert_true (ok);
    assert_true (rig.qemu.ui_info.length == 1);
    var c = rig.qemu.ui_info.get (0);
    assert_true (c.width == 1920 && c.height == 1080);
    assert_true (c.width_mm == 508 && c.height_mm == 286);
    assert_true (rig.bridge.sent_width == 1920 && rig.bridge.sent_height == 1080);
    assert_true (rig.bridge.resize_supported);
}

void test_resize_unsupported_is_remembered () {
    var rig = new Rig ();
    run_setup (rig);
    rig.qemu.supports_ui_info = false;   // ramfb, for instance
    bool done = false;
    bool ok = true;
    rig.bridge.resize.begin (1024, 768, (o, r) => { ok = rig.bridge.resize.end (r); done = true; });
    assert_true (spin (() => done));
    assert_false (ok);
    assert_false (rig.bridge.resize_supported);
    // No further attempts reach QEMU.
    rig.qemu.supports_ui_info = true;
    done = false;
    rig.bridge.resize.begin (1024, 768, (o, r) => { ok = rig.bridge.resize.end (r); done = true; });
    assert_true (spin (() => done));
    assert_false (ok);
    assert_true (rig.qemu.ui_info.length == 0);
}

void test_no_graphic_console_fails_cleanly () {
    var rig = new Rig ();
    run_setup (rig, false, false);
    bool done = false;
    bool ok = true;
    rig.bridge.attach.begin (rig.control, (o, r) => { ok = rig.bridge.attach.end (r); done = true; });
    assert_true (spin (() => done));
    assert_false (ok);
    assert_false (rig.bridge.active);
    assert_true (rig.bridge.failure != "");
    assert_true (rig.qemu.registrations == 0);
}

void test_missing_display_fails_cleanly () {
    // A control connection to something that is not QEMU's display (the machine was started without it).
    var rig = new Rig ();
    run_setup (rig, true, false);
    rig.qemu.conn.close.begin (null);
    assert_true (spin (() => rig.control.closed));
    bool done = false;
    bool ok = true;
    rig.bridge.attach.begin (rig.control, (o, r) => { ok = rig.bridge.attach.end (r); done = true; });
    assert_true (spin (() => done));
    assert_false (ok);
    assert_false (rig.bridge.active);
}

void test_listener_loss_ends_the_bridge () {
    var rig = new Rig ();
    run_setup (rig);
    rig.qemu.listener.close.begin (null);
    assert_true (spin (() => rig.ended));
    assert_false (rig.bridge.active);
}

void test_stop_unregisters () {
    var rig = new Rig ();
    run_setup (rig);
    rig.bridge.stop ();
    assert_false (rig.bridge.active);
    assert_true (spin (() => rig.qemu.listener.closed));
    assert_false (rig.ended);   // our own stop is not "ended"
    // The control connection stays usable for the clipboard.
    assert_false (rig.control.closed);
}

void test_can_attach_again_after_stop () {
    var rig = new Rig ();
    run_setup (rig);
    rig.bridge.stop ();
    assert_true (spin (() => rig.qemu.listener.closed));
    bool done = false;
    bool ok = false;
    rig.bridge.attach.begin (rig.control, (o, r) => { ok = rig.bridge.attach.end (r); done = true; });
    assert_true (spin (() => done));
    assert_true (ok);
    assert_true (rig.qemu.registrations == 2);
    rig.qemu.scanout (1, 1, 4, PixelFormat.X8R8G8B8, new uint8[4]);
    assert_true (spin (() => rig.bridge.scanouts == 1));
}

void test_settings_round_trip () {
    string dir = "";
    try {
        dir = DirUtils.make_tmp ("ml-display-XXXXXX");
    } catch (Error e) {
        Test.fail ();
    }
    string path = Path.build_filename (dir, "machine-lab", "settings.ini");
    var s = new DisplaySettings ();
    assert_true (s.resize_guest);
    // Keys other parts of the app keep in the same file survive.
    try {
        DirUtils.create_with_parents (Path.get_dirname (path), 0755);
        FileUtils.set_contents (path, "[clipboard]\nhost_to_guest=false\n");
    } catch (Error e) {
        Test.fail ();
    }
    s.resize_guest = false;
    assert_true (s.save_to (path));
    var t = new DisplaySettings ();
    t.load_from (path);
    assert_false (t.resize_guest);
    var kf = new KeyFile ();
    try {
        kf.load_from_file (path, KeyFileFlags.NONE);
        assert_false (kf.get_boolean ("clipboard", "host_to_guest"));
    } catch (Error e) {
        Test.fail ();
    }
    var u = new DisplaySettings ();
    u.load_from (Path.build_filename (dir, "missing.ini"));
    assert_true (u.resize_guest);
}

int main (string[] args) {
    Test.init (ref args);
    Test.add_func ("/pixels/format-table", test_format_table);
    Test.add_func ("/pixels/scanout-x8r8g8b8", test_scanout_x8r8g8b8);
    Test.add_func ("/pixels/alpha-opaque", test_alpha_is_always_opaque);
    Test.add_func ("/pixels/byte-orders", test_byte_order_variants);
    Test.add_func ("/pixels/rgb565", test_rgb565);
    Test.add_func ("/pixels/stride-padding", test_stride_padding);
    Test.add_func ("/pixels/update-region", test_update_region);
    Test.add_func ("/pixels/update-clipping", test_update_is_clipped_and_checked);
    Test.add_func ("/pixels/scanout-checks", test_scanout_is_checked);
    Test.add_func ("/pixels/full-hd-speed", test_full_hd_conversion_is_fast_enough);
    Test.add_func ("/resize/snap-and-limits", test_snap_and_limits);
    Test.add_func ("/resize/debounce", test_resize_waits_for_the_window_to_settle);
    Test.add_func ("/resize/rate-limit", test_resize_is_rate_limited);
    Test.add_func ("/resize/tolerance", test_small_changes_and_matching_sizes_are_ignored);
    Test.add_func ("/resize/no-loop", test_a_guest_that_ignores_the_request_is_not_asked_in_a_loop);
    Test.add_func ("/resize/reset", test_reset_after_a_restart);
    Test.add_func ("/resize/hidden-window", test_ignores_a_hidden_window);
    Test.add_func ("/display/attach", test_bridge_finds_the_graphic_console_and_registers);
    Test.add_func ("/display/scanout-update", test_scanout_and_updates_reach_the_screen);
    Test.add_func ("/display/guest-resolution", test_guest_resolution_change_is_followed);
    Test.add_func ("/display/large-frame", test_large_frame_goes_through);
    Test.add_func ("/display/bad-data", test_bad_data_is_counted_and_ignored);
    Test.add_func ("/display/disable-cursor", test_disable_and_cursor);
    Test.add_func ("/display/resize-ui-info", test_resize_sends_ui_info);
    Test.add_func ("/display/resize-unsupported", test_resize_unsupported_is_remembered);
    Test.add_func ("/display/no-graphic-console", test_no_graphic_console_fails_cleanly);
    Test.add_func ("/display/no-display", test_missing_display_fails_cleanly);
    Test.add_func ("/display/listener-loss", test_listener_loss_ends_the_bridge);
    Test.add_func ("/display/stop", test_stop_unregisters);
    Test.add_func ("/display/reattach", test_can_attach_again_after_stop);
    Test.add_func ("/display/settings", test_settings_round_trip);
    return Test.run ();
}
