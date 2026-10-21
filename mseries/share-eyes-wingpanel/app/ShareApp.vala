/* "Screen Share" dock app: a small elementary-style window around the same panel as the Quick Settings section.
 * Quick Settings starts it when a share is offered; it sits minimized in the dock with the eyes icon, shows a badge
 * when someone is waiting, and quits when no link and no live share is left. Clicking the dock icon opens it. */
public class ShareApp : Gtk.Application {
    private const string APP_ID = "io.github.techmore.ShareEyes";
    private MSeries.SharePanel panel;
    private Gtk.ApplicationWindow? win = null;
    private int idle_ticks = 0;
    private DBusConnection? bus = null;
    private int last_count = -1;
    private uint initial_minimize_source = 0;

    public ShareApp () {
        Object (application_id: APP_ID, flags: ApplicationFlags.DEFAULT_FLAGS);
    }

    protected override void activate () {
        if (win != null) {
            if (initial_minimize_source != 0) {
                Source.remove (initial_minimize_source);
                initial_minimize_source = 0;
            }
            win.unminimize ();
            win.present ();
            return;
        }
        Granite.init ();
        panel = new MSeries.SharePanel ();
        panel.margin_start = 6; panel.margin_end = 6; panel.margin_top = 6; panel.margin_bottom = 8;
        var header = new Gtk.HeaderBar ();
        header.add_css_class ("flat");
        win = new Gtk.ApplicationWindow (this) {
            title = "Screen Share",
            default_width = 360,
            default_height = 520,
            titlebar = header,
            child = new Gtk.ScrolledWindow () { child = panel, hscrollbar_policy = Gtk.PolicyType.NEVER, propagate_natural_height = true }
        };
        win.close_request.connect (() => { win.minimize (); return true; });
        try { bus = Bus.get_sync (BusType.SESSION); } catch (Error e) { bus = null; }
        panel.status_changed.connect (on_status);
        win.present ();
        // The compositor must have processed the initial map before minimizing.
        initial_minimize_source = Timeout.add (250, () => {
            initial_minimize_source = 0;
            if (win != null) win.minimize ();
            return Source.REMOVE;
        });
        hold ();
    }

    private void on_status (bool running, bool offering, int waiting, int watching) {
        if (waiting != last_count) {
            last_count = waiting;
            set_badge (waiting);
        }
        // Quit a few polls after the offer ends, so a brief hiccup does not drop the dock icon.
        idle_ticks = offering ? 0 : idle_ticks + 1;
        if (idle_ticks >= 3) {
            release ();
            quit ();
        }
    }

    /* Unity LauncherEntry: the dock shows a count badge and marks the app urgent. */
    private void set_badge (int count) {
        if (bus == null) return;
        var props = new VariantBuilder (new VariantType ("a{sv}"));
        props.add ("{sv}", "count", new Variant.int64 (count));
        props.add ("{sv}", "count-visible", new Variant.boolean (count > 0));
        props.add ("{sv}", "urgent", new Variant.boolean (count > 0));
        try {
            bus.emit_signal (null, "/com/canonical/unity/launcherentry/1", "com.canonical.Unity.LauncherEntry", "Update",
                new Variant ("(sa{sv})", "application://" + APP_ID + ".desktop", props));
        } catch (Error e) {
            warning ("badge: %s", e.message);
        }
    }

    public static int main (string[] args) {
        return new ShareApp ().run (args);
    }
}
