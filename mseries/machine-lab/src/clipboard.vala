/* The GTK and machine-specific halves of clipboard sharing. The protocol and the sync rules are in
 * clipsync.vala (testable without a display). Text only: QEMU's D-Bus clipboard carries nothing else
 * (see experiments/clipboard/README.md). Off by default. */

/* The Gdk clipboard of this session as a HostClipboard. */
public class GdkHostClipboard : Object, HostClipboard {
    private Gdk.Clipboard clip;

    public GdkHostClipboard () {
        clip = Gdk.Display.get_default ().get_clipboard ();
        clip.notify["formats"].connect (() => changed ());
    }

    public bool is_local {
        get { return clip.is_local (); }
    }

    public bool has_text {
        get { return clip.get_formats ().contain_gtype (typeof (string)); }
    }

    public async string? read_text (Cancellable? cancellable = null) throws Error {
        return yield clip.read_text_async (cancellable);
    }

    public void write_text (string text) {
        clip.set_text (text);
    }
}

namespace ClipboardLink {
    /* Connect a bridge to a running machine: hand QEMU one end of a socketpair as a D-Bus display client
     * (see Machine.qmp_add_dbus_client). False if QEMU was started without the D-Bus display. */
    public async bool connect_machine (ClipboardBridge bridge, Machine machine) {
        if (bridge.active) {
            return true;
        }
        int fd = machine.qmp_add_dbus_client ();
        if (fd < 0) {
            return false;
        }
        DBusConnection connection;
        try {
            var stream = SocketConnection.factory_create_connection (new Socket.from_fd (fd));
            connection = new DBusConnection.sync (stream, null,
                DBusConnectionFlags.AUTHENTICATION_CLIENT | DBusConnectionFlags.DELAY_MESSAGE_PROCESSING, null, null);
        } catch (Error e) {
            bridge.status ("Clipboard sharing could not start: " + e.message);
            return false;
        }
        return yield bridge.attach (connection);
    }
}
