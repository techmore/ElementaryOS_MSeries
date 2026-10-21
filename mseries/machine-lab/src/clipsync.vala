/* Clipboard sync with a guest over QEMU's D-Bus display (org.qemu.Display1.Clipboard).
 *
 * No GTK in this file so the whole state machine can be tested against a fake QEMU on a
 * socketpair (tests/test-clipboard.vala). QEMU speaks the SPICE agent protocol to
 * spice-vdagent in the guest; we are the D-Bus peer on the other side of it.
 *
 * Why the serial counter matters (this is what kept host to guest paste from working):
 * QEMU forwards our Grab serial unchanged to the guest's spice-vdagentd, and vdagentd only
 * accepts a client grab whose serial is exactly its own counter N (then N++), or N-1 (the
 * client wins a tie). Any other serial is silently dropped ("grab discard, serial %u !=
 * session serial %u"), so the guest never claims the selection and never asks for the data.
 * The counter is 0 on a fresh agent connection, and QEMU tells us about every fresh
 * connection by calling our Register, so: reset to 0 there, use the counter value as the
 * serial of our next grab, and follow the guest's serial when it grabs. */

public const string CLIP_TEXT = "text/plain;charset=utf-8";
public const uint CLIP_SELECTION = 0;              // the regular clipboard; PRIMARY and SECONDARY are not shared
public const int CLIP_DEFAULT_MAX_BYTES = 1048576;  // text larger than this is not transferred in either direction

public enum ClipOwner {
    NONE,
    HOST,
    GUEST
}

/* The serial and ownership rules. Pure: no D-Bus, no GDK. */
public class ClipboardSync : Object {
    public ClipOwner owner { get; private set; default = ClipOwner.NONE; }
    /* The serial our next grab will carry (the number of grabs seen so far in this session). */
    public int64 next_serial { get; private set; default = 0; }
    /* Bumped whenever ownership changes, so an in-flight transfer can tell it was superseded. */
    public uint generation { get; private set; default = 0; }

    /* A fresh session (QEMU called Register): the counter restarts and nobody owns anything. */
    public void reset () {
        next_serial = 0;
        owner = ClipOwner.NONE;
        generation++;
    }

    /* The host copied: returns the serial to put on the Grab. */
    public uint claim_for_host () {
        uint serial = (uint) next_serial;
        next_serial++;
        owner = ClipOwner.HOST;
        generation++;
        return serial;
    }

    /* The host clipboard went empty: true when a Release should be sent. */
    public bool release_host () {
        if (owner != ClipOwner.HOST) {
            return false;
        }
        owner = ClipOwner.NONE;
        generation++;
        return true;
    }

    /* The guest copied. False when the grab must be ignored: lower serial than ours (stale), or the same
     * serial as our own latest grab (a tie goes to the client, which is us). */
    public bool accept_guest_grab (uint serial) {
        int64 s = serial;
        if (s < next_serial - 1) {
            return false;
        }
        if (s == next_serial - 1 && owner == ClipOwner.HOST) {
            return false;
        }
        next_serial = s + 1;
        owner = ClipOwner.GUEST;
        generation++;
        return true;
    }

    /* The guest let go of the clipboard. */
    public void guest_released () {
        if (owner == ClipOwner.GUEST) {
            owner = ClipOwner.NONE;
            generation++;
        }
    }
}

/* The host's clipboard, as the bridge needs it. GdkHostClipboard in clipboard.vala is the real one. */
public interface HostClipboard : Object {
    /* The content or owner changed (may fire more than once per copy, and may fire for our own writes). */
    public signal void changed ();

    /* The current content was put there by this process. */
    public abstract bool is_local { get; }
    public abstract bool has_text { get; }
    public abstract async string? read_text (Cancellable? cancellable = null) throws Error;
    public abstract void write_text (string text);
}

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

/* Our side: QEMU calls it when the guest copies, when the guest pastes host data, and to restart the session. */
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
        bridge.on_session_reset ();
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

/* App-wide clipboard preferences (kept in ~/.config/machine-lab/settings.ini). The per-machine
 * "Share clipboard" switch decides whether a machine is started with the channel at all; these two
 * switch a direction off or on while it runs. */
public class ClipboardSettings : Object {
    public signal void changed ();

    private bool _host_to_guest = true;
    private bool _guest_to_host = true;

    public bool host_to_guest {
        get { return _host_to_guest; }
        set {
            if (_host_to_guest != value) {
                _host_to_guest = value;
                changed ();
            }
        }
    }

    public bool guest_to_host {
        get { return _guest_to_host; }
        set {
            if (_guest_to_host != value) {
                _guest_to_host = value;
                changed ();
            }
        }
    }

    private static ClipboardSettings? instance = null;

    public static ClipboardSettings get_default () {
        if (instance == null) {
            instance = new ClipboardSettings ();
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
            if (kf.has_key ("clipboard", "host_to_guest")) {
                host_to_guest = kf.get_boolean ("clipboard", "host_to_guest");
            }
            if (kf.has_key ("clipboard", "guest_to_host")) {
                guest_to_host = kf.get_boolean ("clipboard", "guest_to_host");
            }
        } catch (Error e) {
            // No file yet, or unreadable: keep the defaults (both directions on).
        }
    }

    public bool save_to (string path) {
        var kf = new KeyFile ();
        try {
            // Keep keys other parts of the app may write to the same file.
            try {
                kf.load_from_file (path, KeyFileFlags.NONE);
            } catch (Error e) {
            }
            kf.set_boolean ("clipboard", "host_to_guest", host_to_guest);
            kf.set_boolean ("clipboard", "guest_to_host", guest_to_host);
            DirUtils.create_with_parents (Path.get_dirname (path), 0755);
            kf.save_to_file (path);
            return true;
        } catch (Error e) {
            warning ("Could not save clipboard settings: %s", e.message);
            return false;
        }
    }

    public void save () {
        save_to (default_path ());
    }
}

public class ClipboardBridge : Object {
    public signal void status (string message);
    /* The connection to QEMU went away (the machine stopped or QEMU closed the display). */
    public signal void ended ();

    public ClipboardSync sync { get; private set; default = new ClipboardSync (); }
    public int max_bytes { get; set; default = CLIP_DEFAULT_MAX_BYTES; }
    /* Wait this long after a host change before announcing it; GDK reports one copy several times. */
    public uint debounce_ms { get; set; default = 40; }
    /* How long QEMU may wait for host data: its main loop is blocked while it waits, so keep it short. */
    public uint provide_timeout_ms { get; set; default = 3000; }

    private bool _host_to_guest = true;
    private bool _guest_to_host = true;

    public bool host_to_guest {
        get { return _host_to_guest; }
        set {
            if (_host_to_guest == value) {
                return;
            }
            _host_to_guest = value;
            if (!value) {
                withdraw_host_grab ();
            } else {
                announce_soon ();
            }
        }
    }

    public bool guest_to_host {
        get { return _guest_to_host; }
        set { _guest_to_host = value; }
    }

    private HostClipboard host;
    private DBusConnection? bus = null;
    private ClipboardPeer? peer = null;
    private uint registration = 0;
    private ulong host_handler = 0;
    private uint announce_source = 0;
    private bool applying = false;       // we are writing guest data into the host clipboard
    private string? echo_text = null;    // the last text the guest gave us: not to be sent back
    private string? served_text = null;  // the last text we gave the guest: not to be fetched back

    // Counters, for tests and for the log.
    public int host_grabs { get; private set; default = 0; }
    public int guest_fetches { get; private set; default = 0; }

    public ClipboardBridge (HostClipboard host) {
        this.host = host;
    }

    public bool active { get { return bus != null; } }

    /* Take over a connection to QEMU's D-Bus display (made with DELAY_MESSAGE_PROCESSING) and register as the
     * clipboard peer. */
    public async bool attach (DBusConnection connection) {
        if (bus != null) {
            return true;
        }
        bus = connection;
        try {
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
        host_handler = host.changed.connect (on_host_changed);
        bus.notify["closed"].connect (on_bus_closed);
        // A copy made before the guest agent was up is offered as soon as it is.
        announce_soon ();
        return true;
    }

    private void on_bus_closed () {
        bool was_active = bus != null;
        teardown ();
        if (was_active) {
            ended ();
        }
    }

    public void stop () {
        if (peer != null && bus != null && !bus.closed) {
            peer.unregister_client.begin ();
        }
        var b = bus;
        teardown ();
        if (b != null && !b.closed) {
            b.close.begin (null);
        }
    }

    private void teardown () {
        if (host_handler != 0) {
            host.disconnect (host_handler);
            host_handler = 0;
        }
        if (announce_source != 0) {
            Source.remove (announce_source);
            announce_source = 0;
        }
        if (bus != null && registration != 0) {
            bus.unregister_object (registration);
        }
        registration = 0;
        bus = null;
        peer = null;
        sync.reset ();
    }

    // ---- session ----

    /* QEMU restarted the session (the guest agent connected or reconnected): the serial counter starts over,
     * and the guest forgot whatever we had offered, so offer the current host clipboard again. */
    public void on_session_reset () {
        debug ("clipboard session reset by QEMU");
        sync.reset ();
        announce_soon ();
    }

    // ---- host -> guest ----

    private void on_host_changed () {
        if (applying || peer == null) {
            return;   // our own write (from the guest), not a host copy
        }
        announce_soon ();
    }

    private void announce_soon () {
        if (peer == null || announce_source != 0) {
            return;
        }
        announce_source = Timeout.add (debounce_ms, () => {
            announce_source = 0;
            announce_host.begin ();
            return Source.REMOVE;
        });
    }

    private void withdraw_host_grab () {
        if (peer != null && sync.release_host ()) {
            send_release.begin ();
        }
    }

    private async void announce_host () {
        if (peer == null || !_host_to_guest) {
            return;
        }
        if (!host.has_text) {
            // Nothing the guest could paste (an image, files, or nothing at all).
            echo_text = null;
            served_text = null;
            withdraw_host_grab ();
            return;
        }
        if (host.is_local && echo_text != null) {
            // Our own write of what the guest copied reports back as a host change; recognise it by content.
            try {
                var current = yield host.read_text (null);
                if (current != null && current == echo_text) {
                    return;
                }
            } catch (Error e) {
                // Cannot tell: treat it as a host copy.
            }
            if (peer == null || !_host_to_guest) {
                return;
            }
        }
        // A genuine host copy: what the guest gave us earlier no longer describes the clipboard.
        echo_text = null;
        served_text = null;
        uint serial = sync.claim_for_host ();
        host_grabs++;
        debug ("host clipboard changed: grab serial %u", serial);
        try {
            yield peer.grab (CLIP_SELECTION, serial, { CLIP_TEXT });
        } catch (Error e) {
            status ("Clipboard: " + e.message);
        }
    }

    private async void send_release () {
        try {
            yield peer.release (CLIP_SELECTION);
        } catch (Error e) {
            status ("Clipboard: " + e.message);
        }
    }

    /* The guest pastes: QEMU asks for the host clipboard. QEMU's main loop waits for the answer. */
    public async void provide (uint selection, string[] mimes, out string reply_mime, out uint8[] data) throws Error {
        reply_mime = "";
        data = new uint8[0];
        if (!_host_to_guest) {
            throw new IOError.PERMISSION_DENIED ("Sending the host clipboard to the guest is turned off");
        }
        if (selection != CLIP_SELECTION || sync.owner != ClipOwner.HOST) {
            throw new IOError.NOT_FOUND ("Empty clipboard");
        }
        bool wanted = false;
        foreach (var mime in mimes) {
            if (mime == CLIP_TEXT || mime.has_prefix ("text/plain")) {
                wanted = true;
                break;
            }
        }
        if (!wanted) {
            throw new IOError.NOT_SUPPORTED ("The host clipboard only offers text");
        }
        var cancel = new Cancellable ();
        uint timer = 0;
        timer = Timeout.add (provide_timeout_ms, () => {
            timer = 0;
            cancel.cancel ();
            return Source.REMOVE;
        });
        string? text = null;
        try {
            text = yield host.read_text (cancel);
        } finally {
            if (timer != 0) {
                Source.remove (timer);
            }
        }
        if (text == null) {
            throw new IOError.NOT_FOUND ("The host clipboard has no text");
        }
        if (text.length > max_bytes) {
            status ("Clipboard: %s of text on this computer is over the %s limit, so it was not sent to the machine.".printf (
                format_size (text.length), format_size (max_bytes)));
            throw new IOError.MESSAGE_TOO_LARGE ("Clipboard text is over the size limit");
        }
        served_text = text;
        reply_mime = CLIP_TEXT;
        data = text.data;
    }

    // ---- guest -> host ----

    public void on_guest_grab (uint selection, uint serial, string[] mimes) {
        if (selection != CLIP_SELECTION || !sync.accept_guest_grab (serial)) {
            debug ("ignored guest grab: selection %u, serial %u", selection, serial);
            return;
        }
        debug ("guest grab: serial %u, %s", serial, string.joinv (", ", mimes));
        if (!_guest_to_host || !(CLIP_TEXT in mimes)) {
            return;   // nothing we may or can take
        }
        fetch_from_guest.begin (sync.generation);
    }

    public void on_guest_release (uint selection) {
        if (selection == CLIP_SELECTION) {
            // The host keeps the last content until the user copies something else.
            sync.guest_released ();
        }
    }

    private async void fetch_from_guest (uint generation) {
        if (peer == null) {
            return;
        }
        try {
            string reply;
            uint8[] data;
            yield peer.request (CLIP_SELECTION, { CLIP_TEXT }, out reply, out data);
            if (generation != sync.generation || !_guest_to_host) {
                return;   // the host copied something newer meanwhile, or the direction was switched off
            }
            if (reply != CLIP_TEXT) {
                return;
            }
            guest_fetches++;
            if (data.length > max_bytes) {
                status ("Clipboard: %s of text from the machine is over the %s limit, so it was not copied.".printf (
                    format_size (data.length), format_size (max_bytes)));
                return;
            }
            string text = ((string) data).make_valid (data.length);
            if (text == echo_text || text == served_text) {
                return;   // what we already have (a guest clipboard manager re-owning our own text)
            }
            debug ("fetched %d bytes of text from the guest", data.length);
            echo_text = text;
            applying = true;
            host.write_text (text);
            applying = false;
        } catch (Error e) {
            applying = false;
            warning ("clipboard fetch from the guest failed: %s", e.message);
            status ("Clipboard: " + e.message);
        }
    }
}
