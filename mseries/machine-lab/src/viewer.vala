/* The machine's screen inside Machine Lab: frames streamed from QEMU's D-Bus display when the machine has it
 * (DisplayBridge: only the changed rectangles, the guest cursor, resize to this window), else polled with
 * QMP screendump. Mouse and keyboard go back over QMP. */
using Gtk;

public class Viewer : Gtk.Box {
    public Machine machine { get; construct; }
    public signal void toast (string message);
    public signal void fullscreen_toggled (bool on);
    public bool fullscreen { get; private set; default = false; }
    private Gtk.Box exit_bar;
    private Gtk.Box toolbar;
    private uint hide_timer = 0;

    private Gtk.Picture picture;
    private Gtk.Stack stack;
    private Gtk.Label hint;
    private Gtk.Label size_label;
    private uint timer = 0;
    private bool active = false;
    private bool captured = false;
    private int tex_w = 0;
    private int tex_h = 0;
    private bool ctrl_down = false;
    private bool alt_down = false;
    private double last_x = -1;
    private double last_y = -1;
    private int64 last_move = 0;

    // D-Bus display stream (see display.vala); polling stays as the fallback.
    private DisplayBridge? stream = null;
    private bool stream_starting = false;
    private bool stream_live = false;       // a streamed frame has arrived, so polling is paused
    private uint stream_retry = 0;
    private int stream_tries = 0;
    private uint paint_source = 0;
    private int64 last_paint = 0;
    private uint resize_timer = 0;
    private ResizePlanner planner = new ResizePlanner ();
    private Gtk.ToggleButton fit_button;

    // evdev scancode (GDK keycode - 8) -> QEMU qcode
    private static HashTable<int, string>? keymap = null;

    public Viewer (Machine machine) {
        Object (machine: machine, orientation: Gtk.Orientation.VERTICAL, spacing: 0);
    }

    construct {
        build_keymap ();
        margin_start = 24;
        margin_end = 24;
        margin_bottom = 16;
        margin_top = 4;

        picture = new Gtk.Picture ();
        picture.content_fit = Gtk.ContentFit.CONTAIN;
        picture.can_shrink = true;
        picture.hexpand = true;
        picture.vexpand = true;
        picture.focusable = true;
        picture.add_css_class ("ml-screen");

        // Placeholder shown while the machine is off.
        var off = new Gtk.Box (Gtk.Orientation.VERTICAL, 8);
        off.valign = Gtk.Align.CENTER;
        off.halign = Gtk.Align.CENTER;
        var icon = new Gtk.Image.from_icon_name ("video-display-symbolic");
        icon.pixel_size = 64;
        icon.opacity = 0.5;
        off.append (icon);
        var t = new Gtk.Label ("The machine is off");
        t.add_css_class ("title-3");
        off.append (t);
        var d = new Gtk.Label ("Start it and its desktop appears here.");
        d.add_css_class ("dim-label");
        off.append (d);

        stack = new Gtk.Stack ();
        stack.vexpand = true;
        stack.add_named (off, "off");
        stack.add_named (picture, "screen");
        stack.add_css_class ("ml-screen-frame");

        // Floating exit controls, shown in full screen.
        exit_bar = new Gtk.Box (Gtk.Orientation.HORIZONTAL, 8);
        exit_bar.halign = Gtk.Align.CENTER;
        exit_bar.valign = Gtk.Align.START;
        exit_bar.margin_top = 64;
        exit_bar.add_css_class ("ml-fs-bar");
        exit_bar.visible = false;
        var exit_btn = new Gtk.Button.with_label ("Exit Full Screen");
        exit_btn.add_css_class ("suggested-action");
        exit_btn.clicked.connect (() => go_fullscreen (false));
        exit_bar.append (exit_btn);
        var rel_btn = new Gtk.Button.with_label ("Release Keyboard");
        rel_btn.tooltip_text = "Give the keyboard and mouse back (Ctrl+Alt+G)";
        rel_btn.clicked.connect (() => {
            release_modifiers ();
            captured = false;
            update_hint ();
            toast ("Keyboard released. Ctrl+Alt+F or F11 also leaves full screen.");
        });
        exit_bar.append (rel_btn);
        var overlay = new Gtk.Overlay ();
        overlay.child = stack;
        overlay.add_overlay (exit_bar);
        append (overlay);

        var bar = new Gtk.Box (Gtk.Orientation.HORIZONTAL, 8);
        toolbar = bar;
        bar.margin_top = 10;
        hint = new Gtk.Label ("Click the screen to use the keyboard and mouse in the machine. Ctrl+Alt+G gives them back.");
        hint.hexpand = true;
        hint.xalign = 0;
        hint.wrap = true;
        hint.add_css_class ("ml-fineprint");
        bar.append (hint);
        size_label = new Gtk.Label ("");
        size_label.add_css_class ("ml-fineprint");
        bar.append (size_label);
        fit_button = new Gtk.ToggleButton ();
        fit_button.icon_name = "zoom-fit-best-symbolic";
        fit_button.tooltip_text = "Match the machine's screen size to this window";
        fit_button.active = DisplaySettings.get_default ().resize_guest;
        fit_button.toggled.connect (() => {
            var ds = DisplaySettings.get_default ();
            if (ds.resize_guest != fit_button.active) {
                ds.resize_guest = fit_button.active;
                ds.save ();
                toast (fit_button.active ? "The machine's screen will follow this window's size" : "The machine keeps its current screen size");
            }
        });
        bar.append (fit_button);
        var fs = new Gtk.Button.from_icon_name ("view-fullscreen-symbolic");
        fs.tooltip_text = "Full screen (F11)";
        fs.clicked.connect (() => go_fullscreen (!fullscreen));
        bar.append (fs);
        var cad = new Gtk.Button.with_label ("Ctrl+Alt+Del");
        cad.clicked.connect (() => {
            foreach (var k in new string[] { "ctrl", "alt", "delete" }) machine.send_key (k, true);
            foreach (var k in new string[] { "delete", "alt", "ctrl" }) machine.send_key (k, false);
        });
        bar.append (cad);
        var shot = new Gtk.Button.from_icon_name ("camera-photo-symbolic");
        shot.tooltip_text = "Save a screenshot to Pictures";
        shot.clicked.connect (save_screenshot);
        bar.append (shot);
        append (bar);

        // Mouse
        var click = new Gtk.GestureClick ();
        click.button = 0;
        click.pressed.connect ((n, x, y) => {
            picture.grab_focus ();
            captured = true;
            update_hint ();
            move_pointer (x, y, true);
            machine.send_button (button_name (click.get_current_button ()), true);
        });
        click.released.connect ((n, x, y) => {
            machine.send_button (button_name (click.get_current_button ()), false);
        });
        picture.add_controller (click);

        var motion = new Gtk.EventControllerMotion ();
        motion.motion.connect ((x, y) => move_pointer (x, y, false));
        picture.add_controller (motion);

        var scroll = new Gtk.EventControllerScroll (Gtk.EventControllerScrollFlags.VERTICAL);
        scroll.scroll.connect ((dx, dy) => {
            string b = dy < 0 ? "wheel-up" : "wheel-down";
            machine.send_button (b, true);
            machine.send_button (b, false);
            return true;
        });
        picture.add_controller (scroll);

        // Keyboard: capture phase so window shortcuts don't steal keys while captured.
        var keys = new Gtk.EventControllerKey ();
        keys.propagation_phase = Gtk.PropagationPhase.CAPTURE;
        keys.key_pressed.connect ((keyval, keycode, state) => handle_key (keyval, keycode, true));
        keys.key_released.connect ((keyval, keycode, state) => { handle_key (keyval, keycode, false); });
        picture.add_controller (keys);

        var focus = new Gtk.EventControllerFocus ();
        focus.leave.connect (() => { captured = false; release_modifiers (); update_hint (); });
        picture.add_controller (focus);

        machine.frame_ready.connect (on_frame);
        machine.state_changed.connect (sync_state);
        sync_state ();
    }

    ~Viewer () {
        if (timer != 0) {
            Source.remove (timer);
        }
        if (paint_source != 0) {
            Source.remove (paint_source);
        }
        if (resize_timer != 0) {
            Source.remove (resize_timer);
        }
        if (stream_retry != 0) {
            Source.remove (stream_retry);
        }
    }

    public void go_fullscreen (bool on) {
        if (fullscreen == on) {
            return;
        }
        fullscreen = on;
        toolbar.visible = !on;
        margin_start = on ? 0 : 24;
        margin_end = on ? 0 : 24;
        margin_bottom = on ? 0 : 16;
        margin_top = on ? 0 : 4;
        exit_bar.visible = on;
        exit_bar.opacity = 1.0;
        if (on) {
            toast ("Full screen: move the pointer to the top for the exit button, or press F11 / Ctrl+Alt+F");
            arm_hide ();
        }
        fullscreen_toggled (on);
    }

    private void arm_hide () {
        if (hide_timer != 0) {
            Source.remove (hide_timer);
        }
        hide_timer = Timeout.add (3000, () => {
            hide_timer = 0;
            if (fullscreen) {
                exit_bar.opacity = 0.0;   // fades; still clickable once shown again
            }
            return Source.REMOVE;
        });
    }

    /* Only fetch frames while this tab is on screen. With the D-Bus display QEMU pushes the changed rectangles;
     * otherwise poll: ~30 fps while the screen changes, ~7 fps once it has been still for a moment. */
    public void set_active (bool on) {
        active = on;
        if (on) {
            if (timer == 0 && !stream_live) {
                schedule (0);
            }
            stream_tries = 0;
            start_stream ();
            if (resize_timer == 0) {
                resize_timer = Timeout.add (150, () => {
                    check_resize ();
                    return Source.CONTINUE;
                });
            }
        } else {
            if (timer != 0) {
                Source.remove (timer);
                timer = 0;
            }
            if (resize_timer != 0) {
                Source.remove (resize_timer);
                resize_timer = 0;
            }
            if (stream_retry != 0) {
                Source.remove (stream_retry);
                stream_retry = 0;
            }
            stop_stream ();
        }
    }

    private void schedule (uint ms) {
        timer = Timeout.add (ms, () => {
            timer = 0;
            if (!active || stream_live) {
                return Source.REMOVE;
            }
            if (machine.running) {
                machine.request_frame ();
            }
            schedule (still > 20 ? 150 : 33);
            return Source.REMOVE;
        });
    }

    // ---- D-Bus display stream ----

    private void start_stream () {
        if (stream != null || stream_starting || !active || !machine.running) {
            return;
        }
        stream_starting = true;
        machine.qemu_connection.begin ((o, r) => {
            var conn = machine.qemu_connection.end (r);
            if (conn == null || !active || !machine.running) {
                stream_starting = false;
                retry_stream ();
                return;
            }
            var b = new DisplayBridge ();
            b.frame_changed.connect (on_stream_frame);
            b.cursor_changed.connect (on_guest_cursor);
            b.ended.connect (() => {
                if (stream == b) {
                    stop_stream ();
                    if (active) {
                        retry_stream ();
                    }
                }
            });
            b.attach.begin (conn, (o2, r2) => {
                stream_starting = false;
                if (!b.attach.end (r2)) {
                    debug ("display stream unavailable: %s", b.failure);
                    retry_stream ();
                } else if (!active || !machine.running) {
                    b.stop ();
                } else {
                    stream = b;
                    planner.guest_size (0, 0);
                }
            });
        });
    }

    /* The machine may still be starting (QEMU not listening yet): try a few times, then stay on polling. */
    private void retry_stream () {
        if (stream_retry != 0 || !active || !machine.running || stream_tries >= 10) {
            return;
        }
        stream_tries++;
        stream_retry = Timeout.add_seconds (2, () => {
            stream_retry = 0;
            start_stream ();
            return Source.REMOVE;
        });
    }

    private void stop_stream () {
        if (stream != null) {
            stream.stop ();
            stream = null;
        }
        stream_live = false;
        picture.cursor = null;
        if (paint_source != 0) {
            Source.remove (paint_source);
            paint_source = 0;
        }
        if (active && machine.running && timer == 0) {
            schedule (0);   // back to polling
        }
    }

    private void on_stream_frame () {
        if (stream == null) {
            return;
        }
        stream_live = true;   // the polling chain ends at its next tick
        if (paint_source != 0) {
            return;
        }
        // Several updates can arrive per displayed frame: paint at most about 60 times a second.
        int64 since = (get_monotonic_time () - last_paint) / 1000;
        uint delay = since >= 16 ? 0 : (uint) (16 - since);
        paint_source = Timeout.add (delay, () => {
            paint_source = 0;
            paint_stream ();
            return Source.REMOVE;
        });
    }

    private void paint_stream () {
        if (stream == null || stream.screen.width <= 0 || stream.screen.height <= 0) {
            return;
        }
        last_paint = get_monotonic_time ();
        var screen = stream.screen;
        int w = screen.width;
        int h = screen.height;
        var bytes = new Bytes.take (screen.snapshot ());
        picture.paintable = new Gdk.MemoryTexture (w, h, Gdk.MemoryFormat.B8G8R8A8_PREMULTIPLIED, bytes, w * 4);
        if (w != tex_w || h != tex_h) {
            size_label.label = "%d × %d".printf (w, h);
        }
        tex_w = w;
        tex_h = h;
        planner.guest_size (w, h);
        stack.visible_child_name = "screen";
    }

    /* The guest draws its own pointer (a hardware cursor never appears in the picture): show its shape as the
     * pointer over the screen, which also hides the latency of waiting for the guest to draw it. */
    private void on_guest_cursor (CursorShape shape) {
        if (shape.is_blank ()) {
            picture.cursor = new Gdk.Cursor.from_name ("none", null);
            return;
        }
        var tex = new Gdk.MemoryTexture (shape.width, shape.height, Gdk.MemoryFormat.B8G8R8A8,
            new Bytes (shape.data), shape.width * 4);
        picture.cursor = new Gdk.Cursor.from_texture (tex, shape.hot_x, shape.hot_y, null);
    }

    /* Keep the guest's screen the size of this window, once the window stops changing. */
    private void check_resize () {
        bool want = DisplaySettings.get_default ().resize_guest;
        if (fit_button.active != want) {
            fit_button.active = want;
        }
        if (stream == null || !stream.active) {
            return;
        }
        if (!stream.resize_supported) {
            fit_button.sensitive = false;
            fit_button.tooltip_text = "This machine's display cannot change size (it has no resizable virtual monitor)";
            return;
        }
        fit_button.sensitive = true;
        if (!want) {
            return;
        }
        int w = picture.get_width ();
        int h = picture.get_height ();
        if (w < 64 || h < 64) {
            return;   // not laid out yet
        }
        int64 now = get_monotonic_time ();
        planner.request (w, h, now);
        int tw, th;
        if (planner.due (now, out tw, out th)) {
            planner.sent (tw, th, now);
            stream.resize.begin (tw, th);
        }
    }

    private void sync_state () {
        stack.visible_child_name = machine.running ? "screen" : "off";
        if (!machine.running) {
            captured = false;
            update_hint ();
            stop_stream ();
            planner.reset ();
        } else if (active) {
            stream_tries = 0;
            start_stream ();
        }
    }

    private Bytes? last_frame = null;
    private int still = 0;

    /* Frames arrive as binary PPM (P6): no compression on either end, which is
     * far cheaper than PNG and lets the view run near 30 fps. */
    private void on_frame (string path) {
        uint8[] data;
        try {
            FileUtils.get_data (path, out data);
        } catch (Error e) {
            return;
        }
        if (data.length < 16 || data[0] != 'P' || data[1] != '6') {
            return;
        }
        // Header: "P6 <w> <h> <maxval>" then one whitespace byte, then RGB.
        int pos = 2;
        int[] header = {};
        while (header.length < 3 && pos < data.length) {
            while (pos < data.length && (data[pos] == ' ' || data[pos] == '\n' || data[pos] == '\r' || data[pos] == '\t')) pos++;
            if (pos < data.length && data[pos] == '#') {
                while (pos < data.length && data[pos] != '\n') pos++;
                continue;
            }
            int v = 0;
            int start = pos;
            while (pos < data.length && data[pos] >= '0' && data[pos] <= '9') {
                v = v * 10 + (data[pos] - '0');
                pos++;
            }
            if (pos == start) return;
            header += v;
        }
        pos++;
        int w = header[0];
        int h = header[1];
        if (w <= 0 || h <= 0 || data.length - pos < w * h * 3) {
            return;   // caught mid-write; the next frame will do
        }
        var whole = new Bytes (data);
        if (last_frame != null && last_frame.compare (whole) == 0) {
            still++;   // nothing changed: let the poller slow down
            return;
        }
        last_frame = whole;
        still = 0;
        tex_w = w;
        tex_h = h;
        picture.paintable = new Gdk.MemoryTexture (w, h, Gdk.MemoryFormat.R8G8B8,
            whole.slice (pos, pos + w * h * 3), w * 3);
        size_label.label = "%d × %d".printf (w, h);
        stack.visible_child_name = "screen";
    }

    private void update_hint () {
        hint.label = captured
            ? "Keyboard and mouse are in the machine. Press Ctrl+Alt+G to get them back."
            : "Click the screen to use the keyboard and mouse in the machine. Ctrl+Alt+G gives them back.";
    }

    // Pointer position inside the picture's displayed image, as 0..1.
    private void move_pointer (double x, double y, bool force) {
        if (fullscreen && y < 140) {
            exit_bar.opacity = 1.0;
            arm_hide ();
        }
        if (tex_w == 0 || tex_h == 0) {
            return;
        }
        int64 now = get_monotonic_time ();
        if (!force && now - last_move < 16000) {
            return;   // ~60 Hz is plenty
        }
        last_move = now;
        double w = picture.get_width ();
        double h = picture.get_height ();
        double scale = double.min (w / tex_w, h / tex_h);
        double iw = tex_w * scale;
        double ih = tex_h * scale;
        double ox = (w - iw) / 2;
        double oy = (h - ih) / 2;
        double fx = (x - ox) / iw;
        double fy = (y - oy) / ih;
        if (fx < 0 || fx > 1 || fy < 0 || fy > 1) {
            return;
        }
        machine.send_pointer (fx, fy);
    }

    private string button_name (uint b) {
        switch (b) {
            case 2: return "middle";
            case 3: return "right";
            case 8: return "side";
            case 9: return "extra";
            default: return "left";
        }
    }

    // Broadway reports browser key codes, not evdev, so map by key name there.
    private static string? qcode_from_keyval (uint keyval) {
        string? n = Gdk.keyval_name (keyval);
        if (n == null) return null;
        n = n.down ();
        if (n.length == 1 && (n[0].isalnum ())) return n;
        switch (n) {
            case "return": return "ret";
            case "space": return "spc";
            case "backspace": return "backspace";
            case "tab": return "tab";
            case "escape": return "esc";
            case "minus": return "minus";
            case "equal": return "equal";
            case "comma": return "comma";
            case "period": return "dot";
            case "slash": return "slash";
            case "semicolon": return "semicolon";
            case "apostrophe": return "apostrophe";
            case "up": return "up";
            case "down": return "down";
            case "left": return "left";
            case "right": return "right";
            case "delete": return "delete";
            case "home": return "home";
            case "end": return "end";
            case "shift_l": return "shift";
            case "shift_r": return "shift_r";
            case "control_l": return "ctrl";
            case "control_r": return "ctrl_r";
            case "alt_l": return "alt";
            case "alt_r": return "alt_r";
            default: return null;
        }
    }

    private bool is_broadway () {
        return get_display ().get_class ().get_name ().contains ("Broadway");
    }

    private bool handle_key (uint keyval, uint keycode, bool down) {
        int evdev = (int) keycode - 8;
        if (is_broadway ()) {
            string? q = qcode_from_keyval (keyval);
            if (!captured || q == null) return false;
            machine.send_key (q, down);
            return true;
        }
        if (evdev == 29 || evdev == 97) ctrl_down = down;
        if (evdev == 56 || evdev == 100) alt_down = down;
        if (!captured) {
            return false;
        }
        // Ctrl+Alt+F toggles full screen even while the keyboard is captured.
        if (evdev == 33 && ctrl_down && alt_down) {
            if (down) {
                release_modifiers ();
                go_fullscreen (!fullscreen);
            }
            return true;
        }
        // Ctrl+Alt+G releases the keyboard back to Machine Lab.
        if (evdev == 34 && ctrl_down && alt_down) {
            if (down) {
                release_modifiers ();
                captured = false;
                update_hint ();
                ((Gtk.Widget) this.get_root ()).grab_focus ();
            }
            return true;
        }
        string? q = keymap[evdev];
        if (q == null) {
            return false;
        }
        machine.send_key (q, down);
        return true;
    }

    private void release_modifiers () {
        foreach (var k in new string[] { "ctrl", "alt", "shift", "shift_r", "ctrl_r", "alt_r", "meta_l" }) {
            if (machine.running) machine.send_key (k, false);
        }
        ctrl_down = false;
        alt_down = false;
    }

    private void save_screenshot () {
        var tex = picture.paintable as Gdk.Texture;
        if (tex == null) {
            toast ("No screen to save yet");
            return;
        }
        var pictures = Environment.get_user_special_dir (UserDirectory.PICTURES) ?? Environment.get_home_dir ();
        var stamp = new DateTime.now_local ().format ("%Y-%m-%d %H.%M.%S");
        var dest = Path.build_filename (pictures, "%s %s.png".printf (machine.name, stamp));
        if (tex.save_to_png (dest)) {
            toast ("Saved to Pictures");
        } else {
            toast ("Couldn't save the screenshot");
        }
    }

    private static void build_keymap () {
        if (keymap != null) {
            return;
        }
        keymap = new HashTable<int, string> (direct_hash, direct_equal);
        string[] row = {
            "1:esc", "2:1", "3:2", "4:3", "5:4", "6:5", "7:6", "8:7", "9:8", "10:9", "11:0", "12:minus", "13:equal",
            "14:backspace", "15:tab", "16:q", "17:w", "18:e", "19:r", "20:t", "21:y", "22:u", "23:i", "24:o", "25:p",
            "26:bracket_left", "27:bracket_right", "28:ret", "29:ctrl", "30:a", "31:s", "32:d", "33:f", "34:g",
            "35:h", "36:j", "37:k", "38:l", "39:semicolon", "40:apostrophe", "41:grave_accent", "42:shift",
            "43:backslash", "44:z", "45:x", "46:c", "47:v", "48:b", "49:n", "50:m", "51:comma", "52:dot",
            "53:slash", "54:shift_r", "55:kp_multiply", "56:alt", "57:spc", "58:caps_lock", "59:f1", "60:f2",
            "61:f3", "62:f4", "63:f5", "64:f6", "65:f7", "66:f8", "67:f9", "68:f10", "87:f11", "88:f12",
            "97:ctrl_r", "100:alt_r", "102:home", "103:up", "104:pgup", "105:left", "106:right", "107:end",
            "108:down", "109:pgdn", "110:insert", "111:delete", "125:meta_l", "126:meta_r", "127:menu"
        };
        foreach (var e in row) {
            var parts = e.split (":");
            keymap[int.parse (parts[0])] = parts[1];
        }
    }
}
