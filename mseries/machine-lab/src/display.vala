/* The guest display over QEMU's D-Bus display (org.qemu.Display1), instead of polling QMP screendump.
 *
 * No GTK in this file, so the pixel conversion, the resize rules and the whole D-Bus exchange can be tested
 * against a fake QEMU on a socketpair (tests/test-display.vala).
 *
 *   control connection (shared with the clipboard, one per machine)
 *       /org/qemu/Display1/VM                 ConsoleIDs
 *       /org/qemu/Display1/Console_N          Type, RegisterListener(fd), SetUIInfo(...)
 *   listener connection (a second socketpair handed over by RegisterListener; QEMU is the server, we the client)
 *       /org/qemu/Display1/Listener           Scanout / Update / Disable / MouseSet / CursorDefine (we implement)
 *
 * The listener advertises no extra interfaces, so QEMU sends plain pixel copies (Scanout for a whole
 * screen, Update for the changed rectangle) rather than shared-memory or DMABUF scanouts. */

// ---- pixel formats -------------------------------------------------------------------------------

/* One pixman pixel format, as QEMU names it in Scanout and Update (PIXMAN_FORMAT(bpp, type, a, r, g, b)). */
public class PixelFormat : Object {
    public int bytes_per_pixel { get; private set; default = 4; }
    public int r_shift { get; private set; default = 0; }
    public int g_shift { get; private set; default = 0; }
    public int b_shift { get; private set; default = 0; }
    public int r_bits { get; private set; default = 8; }
    public int g_bits { get; private set; default = 8; }
    public int b_bits { get; private set; default = 8; }

    // The formats QEMU produces for guest screens, by pixman code (little endian memory order in the comments).
    public const uint X8R8G8B8 = 0x20020888;   // virtio-gpu, virtio-vga, ramfb: bytes B G R x
    public const uint A8R8G8B8 = 0x20028888;   // bytes B G R A
    public const uint X8B8G8R8 = 0x20030888;   // bytes R G B x
    public const uint A8B8G8R8 = 0x20038888;
    public const uint B8G8R8X8 = 0x20080888;   // bytes x R G B
    public const uint B8G8R8A8 = 0x20088888;
    public const uint R8G8B8X8 = 0x20090888;   // bytes x B G R
    public const uint R8G8B8A8 = 0x20098888;
    public const uint R8G8B8 = 0x18020888;     // 24 bit, bytes B G R
    public const uint B8G8R8 = 0x18030888;     // 24 bit, bytes R G B
    public const uint R5G6B5 = 0x10020565;
    public const uint B5G6R5 = 0x10030565;

    /* The layout of a pixman format code, or null for anything this viewer cannot show (indexed, float, YUV).
     * Pixel words are read little endian, which is the byte order of every host Machine Lab runs on. */
    public static PixelFormat? lookup (uint code) {
        int bpp = (int) (code >> 24);
        int type = (int) ((code >> 16) & 0xff);
        int r = (int) ((code >> 8) & 0xf);
        int g = (int) ((code >> 4) & 0xf);
        int b = (int) (code & 0xf);
        if (bpp != 16 && bpp != 24 && bpp != 32) {
            return null;
        }
        if (r == 0 || g == 0 || b == 0 || r > 8 || g > 8 || b > 8 || r + g + b > bpp) {
            return null;
        }
        // Channel order from the most significant bit down, per pixman's type name.
        string seq;
        switch (type) {
            case 2: seq = "argb"; break;
            case 3: seq = "abgr"; break;
            case 8: seq = "bgra"; break;
            case 9: seq = "rgba"; break;
            default: return null;
        }
        var f = new PixelFormat ();
        f.bytes_per_pixel = bpp / 8;
        f.r_bits = r;
        f.g_bits = g;
        f.b_bits = b;
        // Alpha, or the padding of an "x" format, takes every bit the colours do not.
        int alpha_width = bpp - (r + g + b);
        int pos = bpp;
        for (int i = 0; i < 4; i++) {
            switch (seq[i]) {
                case 'a':
                    pos -= alpha_width;
                    break;
                case 'r':
                    pos -= r;
                    f.r_shift = pos;
                    break;
                case 'g':
                    pos -= g;
                    f.g_shift = pos;
                    break;
                default:
                    pos -= b;
                    f.b_shift = pos;
                    break;
            }
        }
        return f;
    }

    private static uint8 expand (uint v, int bits) {
        if (bits == 8) {
            return (uint8) v;
        }
        uint top = (1u << bits) - 1;
        return (uint8) ((v * 255 + top / 2) / top);
    }

    /* Split one pixel (the raw little endian word) into 8 bit B, G, R. */
    public void split (uint word, out uint8 b, out uint8 g, out uint8 r) {
        r = expand ((word >> r_shift) & ((1u << r_bits) - 1), r_bits);
        g = expand ((word >> g_shift) & ((1u << g_bits) - 1), g_bits);
        b = expand ((word >> b_shift) & ((1u << b_bits) - 1), b_bits);
    }
}

/* The guest screen as the viewer shows it: always B8G8R8A8 with opaque alpha, converted from whatever QEMU sends. */
public class ScreenBuffer : Object {
    public const int MAX_DIMENSION = 16384;
    public const int64 MAX_BYTES = 512 * 1024 * 1024;

    public int width { get; private set; default = 0; }
    public int height { get; private set; default = 0; }
    /* Bumped by every change, so a consumer can tell whether it already has the latest picture. */
    public uint64 version { get; private set; default = 0; }
    public bool enabled { get; private set; default = false; }

    private uint8[] pixels = new uint8[0];
    private int dx0 = 0;
    private int dy0 = 0;
    private int dx1 = 0;
    private int dy1 = 0;
    private bool dirty = false;

    /* A new screen of this size and format, with the pixels sent with it (QEMU's Scanout). False, and no
     * change, when the data does not fit the stated size or the format is not understood. */
    public bool scanout (int w, int h, int stride, uint format, uint8[] data) {
        var f = PixelFormat.lookup (format);
        if (f == null || w <= 0 || h <= 0 || w > MAX_DIMENSION || h > MAX_DIMENSION) {
            return false;
        }
        if ((int64) w * h * 4 > MAX_BYTES || !rows_fit (f, w, h, stride, data.length)) {
            return false;
        }
        if (w != width || h != height || pixels.length != w * h * 4) {
            pixels = new uint8[w * h * 4];
        }
        width = w;
        height = h;
        enabled = true;
        copy_sub (f, 0, 0, w, h, 0, 0, stride, data);
        mark (0, 0, w, h);
        version++;
        return true;
    }

    /* Replace one rectangle (QEMU's Update). The rectangle is clipped to the screen; false when there is no
     * screen yet, the rectangle is empty or entirely outside, or the data is too short for it. */
    public bool update (int x, int y, int w, int h, int stride, uint format, uint8[] data) {
        var f = PixelFormat.lookup (format);
        if (f == null || !enabled || w <= 0 || h <= 0) {
            return false;
        }
        if (!rows_fit (f, w, h, stride, data.length)) {
            return false;
        }
        int cx0 = int.max (x, 0);
        int cy0 = int.max (y, 0);
        int cx1 = (int) int64.min ((int64) x + w, width);
        int cy1 = (int) int64.min ((int64) y + h, height);
        if (cx0 >= cx1 || cy0 >= cy1) {
            return false;
        }
        // The data starts at (x, y); skip what was clipped away at the top and left.
        copy_sub (f, cx0, cy0, cx1 - cx0, cy1 - cy0, cx0 - x, cy0 - y, stride, data);
        mark (cx0, cy0, cx1 - cx0, cy1 - cy0);
        version++;
        return true;
    }

    /* The guest turned the display off. The last picture stays until a new Scanout. */
    public void disable () {
        enabled = false;
        version++;
    }

    /* The rectangle changed since the last call, or false when nothing did. */
    public bool take_dirty (out int x, out int y, out int w, out int h) {
        x = dx0;
        y = dy0;
        w = dx1 - dx0;
        h = dy1 - dy0;
        bool d = dirty;
        dirty = false;
        return d;
    }

    /* A private copy of the picture (B8G8R8A8, stride width * 4), safe to hand to a texture. */
    public uint8[] snapshot () {
        uint8[] copy = new uint8[pixels.length];
        if (pixels.length > 0) {
            Memory.copy (copy, pixels, pixels.length);
        }
        return copy;
    }

    /* One pixel as 0xAARRGGBB (0 outside the screen). */
    public uint32 pixel_at (int x, int y) {
        if (x < 0 || y < 0 || x >= width || y >= height) {
            return 0;
        }
        int o = (y * width + x) * 4;
        return ((uint32) pixels[o + 3] << 24) | ((uint32) pixels[o + 2] << 16) | ((uint32) pixels[o + 1] << 8) | pixels[o];
    }

    private static bool rows_fit (PixelFormat f, int w, int h, int stride, int length) {
        int row = w * f.bytes_per_pixel;
        if (stride < row) {
            return false;
        }
        return (int64) stride * (h - 1) + row <= length;
    }

    private void mark (int x, int y, int w, int h) {
        if (!dirty) {
            dx0 = x;
            dy0 = y;
            dx1 = x + w;
            dy1 = y + h;
            dirty = true;
            return;
        }
        dx0 = int.min (dx0, x);
        dy0 = int.min (dy0, y);
        dx1 = int.max (dx1, x + w);
        dy1 = int.max (dy1, y + h);
    }

    /* Convert w x h pixels, starting at (src_x, src_y) of data, into the picture at (x, y). */
    private void copy_sub (PixelFormat f, int x, int y, int w, int h, int src_x, int src_y, int stride, uint8[] data) {
        int bpp = f.bytes_per_pixel;
        bool same_order = bpp == 4 && f.r_shift == 16 && f.g_shift == 8 && f.b_shift == 0
            && f.r_bits == 8 && f.g_bits == 8 && f.b_bits == 8;
        for (int row = 0; row < h; row++) {
            int s = (src_y + row) * stride + src_x * bpp;
            int d = ((y + row) * width + x) * 4;
            if (same_order) {
                // x8r8g8b8 and a8r8g8b8 are B G R x in memory already: copy the row, then make alpha opaque.
                Memory.copy ((uint8*) pixels + d, (uint8*) data + s, w * 4);
                for (int i = 0; i < w; i++) {
                    pixels[d + i * 4 + 3] = 0xff;
                }
                continue;
            }
            for (int i = 0; i < w; i++) {
                int p = s + i * bpp;
                uint word;
                if (bpp == 4) {
                    word = (uint) data[p] | ((uint) data[p + 1] << 8) | ((uint) data[p + 2] << 16) | ((uint) data[p + 3] << 24);
                } else if (bpp == 3) {
                    word = (uint) data[p] | ((uint) data[p + 1] << 8) | ((uint) data[p + 2] << 16);
                } else {
                    word = (uint) data[p] | ((uint) data[p + 1] << 8);
                }
                uint8 b, g, r;
                f.split (word, out b, out g, out r);
                int o = d + i * 4;
                pixels[o] = b;
                pixels[o + 1] = g;
                pixels[o + 2] = r;
                pixels[o + 3] = 0xff;
            }
        }
    }
}

/* The guest's mouse cursor, as QEMU describes it (non-premultiplied B8G8R8A8). */
public class CursorShape : Object {
    public int width { get; construct; }
    public int height { get; construct; }
    public int hot_x { get; construct; }
    public int hot_y { get; construct; }
    public uint8[] data;

    public CursorShape (int width, int height, int hot_x, int hot_y, uint8[] data) {
        Object (width: width, height: height, hot_x: hot_x, hot_y: hot_y);
        this.data = data;
    }

    /* A cursor that is fully transparent (or has no pixels) hides the pointer. */
    public bool is_blank () {
        if (width <= 0 || height <= 0 || data.length < width * height * 4) {
            return true;
        }
        for (int i = 3; i < width * height * 4; i += 4) {
            if (data[i] != 0) {
                return false;
            }
        }
        return true;
    }
}

// ---- resizing the guest to the window -------------------------------------------------------------

/* Decides when to ask the guest for a new screen size. Pure: the caller supplies the window size and the
 * clock, so the debouncing can be tested without a window or a timer.
 *
 * A window being dragged produces dozens of sizes a second; every one sent to the guest would redo its
 * whole desktop layout. So a size is sent only once the window has stopped changing for `quiet_us`, never
 * more often than every `min_gap_us`, and not at all when it is within `tolerance` pixels of the size the
 * guest already has or was last asked for. */
public class ResizePlanner : Object {
    public int min_width { get; set; default = 640; }
    public int min_height { get; set; default = 480; }
    public int max_width { get; set; default = 7680; }
    public int max_height { get; set; default = 4320; }
    public int align { get; set; default = 8; }
    public int tolerance { get; set; default = 16; }
    public int64 quiet_us { get; set; default = 400000; }
    public int64 min_gap_us { get; set; default = 1000000; }

    private int want_w = 0;
    private int want_h = 0;
    private int64 want_since = 0;
    private bool have_want = false;
    private int sent_w = 0;
    private int sent_h = 0;
    private int64 sent_at = 0;
    private bool have_sent = false;
    private int seen_w = 0;
    private int seen_h = 0;

    /* The guest screen size for a window of this size: rounded down to the alignment, clamped to the limits. */
    public void snap (int w, int h, out int sw, out int sh) {
        int a = int.max (align, 1);
        sw = (w / a) * a;
        sh = (h / a) * a;
        sw = sw.clamp (min_width, max_width);
        sh = sh.clamp (min_height, max_height);
    }

    /* Physical size in millimetres of a screen this many pixels wide at 96 dpi (SetUIInfo asks for it). */
    public static uint16 mm_for (int pixels) {
        int mm = (pixels * 254 + 480) / 960;
        return (uint16) mm.clamp (1, 65535);
    }

    /* The window is this big now (in pixels the guest should get). */
    public void request (int w, int h, int64 now_us) {
        if (w <= 0 || h <= 0) {
            return;
        }
        int sw, sh;
        snap (w, h, out sw, out sh);
        if (have_want && sw == want_w && sh == want_h) {
            return;   // same as before: the quiet period keeps running
        }
        want_w = sw;
        want_h = sh;
        want_since = now_us;
        have_want = true;
    }

    /* The guest reported its own screen size (a Scanout), which it may have chosen itself. */
    public void guest_size (int w, int h) {
        seen_w = w;
        seen_h = h;
    }

    /* Is it time to send? True once per wanted size, with the size to send. */
    public bool due (int64 now_us, out int w, out int h) {
        w = 0;
        h = 0;
        if (!have_want) {
            return false;
        }
        if (now_us - want_since < quiet_us) {
            return false;   // still changing
        }
        if (have_sent && now_us - sent_at < min_gap_us) {
            return false;
        }
        int ref_w = have_sent ? sent_w : seen_w;
        int ref_h = have_sent ? sent_h : seen_h;
        if (ref_w > 0 && (want_w - ref_w).abs () < tolerance && (want_h - ref_h).abs () < tolerance) {
            have_want = false;   // nothing to do
            return false;
        }
        w = want_w;
        h = want_h;
        return true;
    }

    /* The size was sent (successfully or not: do not retry the same size in a loop). */
    public void sent (int w, int h, int64 now_us) {
        sent_w = w;
        sent_h = h;
        sent_at = now_us;
        have_sent = true;
        have_want = false;
    }

    /* A new session with the guest (the machine restarted): nothing was sent yet. */
    public void reset () {
        have_want = false;
        have_sent = false;
        seen_w = 0;
        seen_h = 0;
    }
}

/* App-wide display preferences (~/.config/machine-lab/settings.ini, next to the clipboard ones). */
public class DisplaySettings : Object {
    public signal void changed ();

    private bool _resize_guest = true;

    /* Ask the guest to match the Display tab's size. */
    public bool resize_guest {
        get { return _resize_guest; }
        set {
            if (_resize_guest != value) {
                _resize_guest = value;
                changed ();
            }
        }
    }

    private static DisplaySettings? instance = null;

    public static DisplaySettings get_default () {
        if (instance == null) {
            instance = new DisplaySettings ();
            instance.load_from (default_path ());
        }
        return instance;
    }

    public static string default_path () {
        return Path.build_filename (Environment.get_user_config_dir (), "machine-lab", "settings.ini");
    }

    public void load_from (string path) {
        var kf = new KeyFile ();
        try {
            kf.load_from_file (path, KeyFileFlags.NONE);
            if (kf.has_key ("display", "resize_guest")) {
                resize_guest = kf.get_boolean ("display", "resize_guest");
            }
        } catch (Error e) {
            // No file yet, or unreadable: keep the default.
        }
    }

    public bool save_to (string path) {
        var kf = new KeyFile ();
        try {
            try {
                kf.load_from_file (path, KeyFileFlags.NONE);
            } catch (Error e) {
                // A new file.
            }
            kf.set_boolean ("display", "resize_guest", resize_guest);
            DirUtils.create_with_parents (Path.get_dirname (path), 0755);
            kf.save_to_file (path);
            return true;
        } catch (Error e) {
            warning ("Could not save display settings: %s", e.message);
            return false;
        }
    }

    public void save () {
        save_to (default_path ());
    }
}

// ---- the D-Bus listener ----------------------------------------------------------------------------

/* Our side of the display connection: QEMU calls it with every screen change. */
[DBus (name = "org.qemu.Display1.Listener")]
public class DisplayListener : Object {
    private weak DisplayBridge bridge;

    public DisplayListener (DisplayBridge bridge) {
        this.bridge = bridge;
    }

    public string[] interfaces {
        owned get { return new string[0]; }
    }

    public void scanout (uint width, uint height, uint stride, uint pixman_format, uint8[] data) throws Error {
        bridge.on_scanout (width, height, stride, pixman_format, data);
    }

    public void update (int x, int y, int width, int height, uint stride, uint pixman_format, uint8[] data) throws Error {
        bridge.on_update (x, y, width, height, stride, pixman_format, data);
    }

    public void disable () throws Error {
        bridge.on_disable ();
    }

    public void mouse_set (int x, int y, int on) throws Error {
        bridge.on_mouse_set (x, y, on != 0);
    }

    public void cursor_define (int width, int height, int hot_x, int hot_y, uint8[] data) throws Error {
        bridge.on_cursor_define (width, height, hot_x, hot_y, data);
    }
}

/* The guest screen from QEMU. One per machine while the Display tab is showing. */
public class DisplayBridge : Object {
    /* The picture or its size changed. */
    public signal void frame_changed ();
    public signal void cursor_changed (CursorShape shape);
    /* The guest pointer's visibility changed (position is not used: the host pointer drives the guest). */
    public signal void pointer_visibility (bool visible);
    /* The listener connection went away (the machine stopped, or QEMU closed the display). */
    public signal void ended ();

    public ScreenBuffer screen { get; private set; default = new ScreenBuffer (); }
    public bool resize_supported { get; private set; default = true; }
    public bool active { get { return listener_conn != null; } }
    public string failure { get; private set; default = ""; }
    public int scanouts { get; private set; default = 0; }
    public int updates { get; private set; default = 0; }
    public int rejected { get; private set; default = 0; }
    public int sent_width { get; private set; default = 0; }
    public int sent_height { get; private set; default = 0; }

    private DBusConnection? control = null;
    private DBusConnection? listener_conn = null;
    private string console_path = "";
    private uint registration = 0;

    /* Find the guest's graphic console on the control connection and register as its display listener. */
    public async bool attach (DBusConnection control_connection) {
        if (listener_conn != null) {
            return true;
        }
        control = control_connection;
        int[] fds = new int[2];
        try {
            int64 id = yield find_console (control_connection);
            if (id < 0) {
                failure = "The machine has no graphic console on its D-Bus display";
                return false;
            }
            console_path = "/org/qemu/Display1/Console_%u".printf ((uint) id);

            if (Posix.socketpair (Posix.AF_UNIX, Posix.SOCK_STREAM, 0, fds) != 0) {
                failure = "Could not create a socket pair";
                return false;
            }
            var list = new UnixFDList ();
            list.append (fds[1]);
            Posix.close (fds[1]);
            fds[1] = -1;
            // Hands QEMU one end; it then connects to us as a D-Bus server on that socket.
            yield control_connection.call_with_unix_fd_list (null, console_path, "org.qemu.Display1.Console",
                "RegisterListener", new Variant ("(h)", 0), null, DBusCallFlags.NONE, 10000, list, null, null);

            var stream = SocketConnection.factory_create_connection (new Socket.from_fd (fds[0]));
            fds[0] = -1;
            var conn = yield new DBusConnection (stream, null,
                DBusConnectionFlags.AUTHENTICATION_CLIENT | DBusConnectionFlags.DELAY_MESSAGE_PROCESSING, null, null);
            registration = conn.register_object ("/org/qemu/Display1/Listener", new DisplayListener (this));
            listener_conn = conn;
            conn.start_message_processing ();
            conn.notify["closed"].connect (on_listener_closed);
        } catch (Error e) {
            failure = e.message;
            if (fds[0] >= 0) {
                Posix.close (fds[0]);
            }
            if (fds[1] >= 0) {
                Posix.close (fds[1]);
            }
            stop ();
            return false;
        }
        return true;
    }

    private async int64 find_console (DBusConnection c) throws Error {
        var reply = yield c.call (null, "/org/qemu/Display1/VM", "org.freedesktop.DBus.Properties", "Get",
            new Variant ("(ss)", "org.qemu.Display1.VM", "ConsoleIDs"), new VariantType ("(v)"), DBusCallFlags.NONE, 5000);
        Variant ids;
        reply.get ("(v)", out ids);
        for (size_t i = 0; i < ids.n_children (); i++) {
            uint32 id = ids.get_child_value (i).get_uint32 ();
            try {
                var t = yield c.call (null, "/org/qemu/Display1/Console_%u".printf (id), "org.freedesktop.DBus.Properties", "Get",
                    new Variant ("(ss)", "org.qemu.Display1.Console", "Type"), new VariantType ("(v)"), DBusCallFlags.NONE, 5000);
                Variant tv;
                t.get ("(v)", out tv);
                if (tv.get_string () == "Graphic") {
                    return id;
                }
            } catch (Error e) {
                debug ("console %u: %s", id, e.message);
            }
        }
        return -1;
    }

    /* Ask the guest for this screen size (QEMU puts it in the virtual monitor's EDID). False when the guest's
     * display device cannot do that (ramfb, for instance) or the call failed. */
    public async bool resize (int w, int h) {
        if (!resize_supported || control == null || console_path == "") {
            return false;
        }
        try {
            yield control.call (null, console_path, "org.qemu.Display1.Console", "SetUIInfo",
                new Variant ("(qqiiuu)", ResizePlanner.mm_for (w), ResizePlanner.mm_for (h), 0, 0, (uint32) w, (uint32) h),
                null, DBusCallFlags.NONE, 5000);
            sent_width = w;
            sent_height = h;
            return true;
        } catch (Error e) {
            string? remote = DBusError.get_remote_error (e);
            if ((remote != null && remote.has_suffix ("Unsupported")) || e.message.contains ("not supported")) {
                resize_supported = false;
            }
            debug ("SetUIInfo %dx%d failed: %s", w, h, e.message);
            return false;
        }
    }

    public void stop () {
        var c = listener_conn;
        if (c != null && registration != 0) {
            c.unregister_object (registration);
        }
        registration = 0;
        listener_conn = null;
        control = null;
        if (c != null && !c.closed) {
            c.close.begin (null);
        }
    }

    private void on_listener_closed () {
        if (listener_conn == null || !listener_conn.closed) {
            return;
        }
        listener_conn = null;
        registration = 0;
        ended ();
    }

    // ---- calls from QEMU ----

    public void on_scanout (uint width, uint height, uint stride, uint format, uint8[] data) {
        if (screen.scanout ((int) width, (int) height, (int) stride, format, data)) {
            scanouts++;
            frame_changed ();
        } else {
            rejected++;
            debug ("rejected Scanout %ux%u stride %u format 0x%x with %d bytes", width, height, stride, format, data.length);
        }
    }

    public void on_update (int x, int y, int width, int height, uint stride, uint format, uint8[] data) {
        if (screen.update (x, y, width, height, (int) stride, format, data)) {
            updates++;
            frame_changed ();
        } else {
            rejected++;
        }
    }

    public void on_disable () {
        screen.disable ();
        frame_changed ();
    }

    public void on_mouse_set (int x, int y, bool on) {
        pointer_visibility (on);
    }

    public void on_cursor_define (int width, int height, int hot_x, int hot_y, uint8[] data) {
        if (width < 0 || height < 0 || width > 512 || height > 512 || data.length < width * height * 4) {
            return;
        }
        uint8[] copy = new uint8[data.length];
        Memory.copy (copy, data, data.length);
        cursor_changed (new CursorShape (width, height, hot_x, hot_y, copy));
    }
}
