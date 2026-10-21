/* Clipboard sharing with a guest over QEMU's D-Bus display
 * (org.qemu.Display1.Clipboard). QEMU speaks the SPICE agent protocol to
 * spice-vdagent in the guest; here we are the D-Bus peer that mirrors it to
 * the Gdk clipboard. Text and PNG images travel both ways. Off by default. */

const string CLIP_TEXT = "text/plain;charset=utf-8";
const string CLIP_PNG = "image/png";

/* QEMU's side: we call it to announce host clipboard changes and to fetch guest data. */
[DBus (name = "org.qemu.Display1.Clipboard")]
public interface ClipboardPeer : Object {
    [DBus (name = "Register")]
    public abstract async void register_client () throws Error;
    [DBus (name = "Unregister")]
    public abstract async void unregister_client () throws Error;
    public abstract async void grab (uint selection, uint serial, string[] mimes) throws Error;
    public abstract async void release (uint selection) throws Error;
    public abstract async void request (uint selection, string[] mimes, out string reply_mime, out uint8[] data) throws Error;
}

/* Our side: QEMU calls it when the guest copies, and when the guest pastes host data. */
[DBus (name = "org.qemu.Display1.Clipboard")]
public class ClipboardService : Object {
    private weak ClipboardBridge bridge;

    public ClipboardService (ClipboardBridge bridge) {
        this.bridge = bridge;
    }

    public string[] interfaces {
        owned get { return new string[0]; }
    }

    [DBus (name = "Register")]
    public void register_client () throws Error {
    }

    [DBus (name = "Unregister")]
    public void unregister_client () throws Error {
    }

    public void grab (uint selection, uint serial, string[] mimes) throws Error {
        bridge.on_guest_grab (selection, serial, mimes);
    }

    public void release (uint selection) throws Error {
        bridge.on_guest_release (selection);
    }

    public async void request (uint selection, string[] mimes, out string reply_mime, out uint8[] data) throws Error {
        string m = "";
        uint8[] d = new uint8[0];
        yield bridge.provide (selection, mimes, out m, out d);
        reply_mime = m;
        data = d;
    }
}

public class ClipboardBridge : Object {
    public signal void status (string message);

    private Machine machine;
    private DBusConnection? bus = null;
    private ClipboardPeer? peer = null;
    private uint registration = 0;
    private uint serial = 0;          // our grab counter (QEMU's clipboard serial rules)
    private uint peer_serial = 0;
    private Gdk.Clipboard clip;
    private ulong clip_handler = 0;
    private bool applying = false;

    public ClipboardBridge (Machine machine) {
        this.machine = machine;
        this.clip = Gdk.Display.get_default ().get_clipboard ();
    }

    public bool active { get { return bus != null; } }

    /* Connect to the running guest. False if QEMU was started without the D-Bus display. */
    public async bool start () {
        if (bus != null) {
            return true;
        }
        int fd = machine.qmp_add_dbus_client ();
        if (fd < 0) {
            return false;
        }
        try {
            var stream = SocketConnection.factory_create_connection (new Socket.from_fd (fd));
            bus = new DBusConnection.sync (stream, null,
                DBusConnectionFlags.AUTHENTICATION_CLIENT | DBusConnectionFlags.DELAY_MESSAGE_PROCESSING, null, null);
            registration = bus.register_object ("/org/qemu/Display1/Clipboard", new ClipboardService (this));
            bus.start_message_processing ();
            peer = bus.get_proxy_sync (null, "/org/qemu/Display1/Clipboard", DBusProxyFlags.DO_NOT_LOAD_PROPERTIES, null);
            // Async: QEMU calls back into us while handling Register (it resets the session),
            // and a blocking call here would deadlock the main loop that serves those calls.
            yield peer.register_client ();
        } catch (Error e) {
            status ("Clipboard sharing could not start: " + e.message);
            stop ();
            return false;
        }
        clip_handler = clip.notify["formats"].connect (() => on_host_changed ());
        bus.notify["closed"].connect (() => { bus = null; peer = null; });
        return true;
    }

    public void stop () {
        if (clip_handler != 0) {
            clip.disconnect (clip_handler);
            clip_handler = 0;
        }
        if (peer != null) {
            peer.unregister_client.begin ();
        }
        if (bus != null) {
            if (registration != 0) {
                bus.unregister_object (registration);
                registration = 0;
            }
            bus.close.begin (null);
        }
        bus = null;
        peer = null;
    }

    // ---- host -> guest ----

    private void on_host_changed () {
        if (applying || peer == null) {
            return;   // our own write (from the guest), not a host copy
        }
        var formats = clip.get_formats ();
        string[] mimes = {};
        if (formats.contain_gtype (typeof (string))) {
            mimes += CLIP_TEXT;
        }
        if (formats.contain_gtype (typeof (Gdk.Texture))) {
            mimes += CLIP_PNG;
        }
        debug ("host clipboard changed: %s", string.joinv (", ", mimes));
        send_host_grab.begin (mimes);
    }

    private async void send_host_grab (string[] mimes) {
        try {
            if (mimes.length == 0) {
                yield peer.release (0);
            } else {
                // QEMU keeps one grab counter for both sides: the highest serial owns the
                // clipboard (ties go to the client), so always outbid what we have seen.
                serial = uint.max (serial, peer_serial) + 1;
                yield peer.grab (0, serial, mimes);
            }
        } catch (Error e) {
            status ("Clipboard: " + e.message);
        }
    }

    /* The guest pastes: hand it the host clipboard in the first MIME type we can produce. */
    public async void provide (uint selection, string[] mimes, out string reply_mime, out uint8[] data) throws Error {
        reply_mime = "";
        data = new uint8[0];
        debug ("guest pastes: wants %s", string.joinv (", ", mimes));
        foreach (var mime in mimes) {
            if (mime == CLIP_TEXT || mime.has_prefix ("text/plain")) {
                var text = yield clip.read_text_async (null);
                if (text != null) {
                    reply_mime = CLIP_TEXT;
                    data = text.data;
                    return;
                }
            } else if (mime == CLIP_PNG) {
                var tex = yield clip.read_texture_async (null);
                if (tex != null) {
                    var bytes = tex.save_to_png_bytes ();
                    reply_mime = CLIP_PNG;
                    data = bytes.get_data ();
                    return;
                }
            }
        }
        throw new IOError.NOT_FOUND ("The host clipboard has none of the requested types");
    }

    // ---- guest -> host ----

    public void on_guest_grab (uint selection, uint serial, string[] mimes) {
        if (selection != 0 || serial < peer_serial) {
            return;   // only the regular clipboard; discard stale grabs
        }
        peer_serial = serial;
        debug ("guest grab: serial %u, %s", serial, string.joinv (", ", mimes));
        string? want = null;
        foreach (var m in mimes) {
            if (m == CLIP_TEXT) {
                want = m;
                break;
            }
        }
        if (want == null) {
            foreach (var m in mimes) {
                if (m == CLIP_PNG) {
                    want = m;
                }
            }
        }
        if (want != null) {
            fetch_from_guest.begin (want);
        }
    }

    public void on_guest_release (uint selection) {
        // Nothing to do: the host keeps the last content until the user copies something else.
    }

    private async void fetch_from_guest (string mime) {
        if (peer == null) {
            return;
        }
        try {
            string reply;
            uint8[] data;
            yield peer.request (0, { mime }, out reply, out data);
            debug ("fetched %d bytes of %s from the guest", data.length, reply);
            applying = true;
            if (reply == CLIP_TEXT) {
                clip.set_text (((string) data).make_valid (data.length));
            } else if (reply == CLIP_PNG) {
                clip.set_texture (Gdk.Texture.from_bytes (new Bytes (data)));
            }
        } catch (Error e) {
            warning ("clipboard fetch from the guest failed: %s", e.message);
            status ("Clipboard: " + e.message);
        }
        // Keep ignoring change notifications until the main loop has delivered ours.
        Idle.add (() => {
            applying = false;
            return Source.REMOVE;
        });
    }
}
