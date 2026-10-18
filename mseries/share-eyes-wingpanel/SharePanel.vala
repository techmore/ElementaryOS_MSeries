/* Screen share section for the Quick Settings popover (top-right menu): status, approve/remove watchers, stop,
 * links and login. Hidden unless the share launcher is running. See ShareState for the launcher contract. */
using Gtk;

namespace MSeries {
    public class SharePanel : Gtk.Box {
        private Gtk.Image eyes;
        private Gtk.Box content;
        private ShareState state = new ShareState ();
        private ShareClient client = new ShareClient ();
        private string path = ShareState.default_path ();
        private string last_digest = "";
        private string toast = "";
        private uint poll_source = 0;
        private bool busy = false;
        private bool details_open = false;
        private int tick_count = 0;
        private bool dock_check_busy = false;

        /* Fired after every poll: what a dock badge or a notification needs to know. offering = a link exists or a share is live. */
        public signal void status_changed (bool running, bool offering, int waiting, int watching);
        /* In Quick Settings this is true: while a share is offered it starts the dock app (eyes in the dock). The app itself sets it false. */
        public bool spawn_dock_app { get; set; default = false; }

        construct {
            eyes = new Gtk.Image.from_icon_name ("mseries-share-eyes-symbolic") { pixel_size = 18 };
            eyes.add_css_class ("mseries-eyes");
            eyes.set_tooltip_text (state.tooltip ());
            orientation = Gtk.Orientation.VERTICAL;
            visible = false;
            add_css_class ("mseries-share");
            margin_top = 6; margin_bottom = 6; margin_start = 6; margin_end = 6;

            content = new Gtk.Box (Gtk.Orientation.VERTICAL, 8);
            install_style (content.get_display ());
            append (content);
            // The list is rebuilt as soon as the menu is shown, and polled while it stays open.
            map.connect (() => { last_digest = ""; tick.begin (); });

            tick.begin ();
            poll_source = GLib.Timeout.add_seconds (2, () => { tick.begin (); return GLib.Source.CONTINUE; });
        }

        ~SharePanel () {
            if (poll_source != 0) {
                GLib.Source.remove (poll_source);
            }
        }

        private async void tick () {
            if (busy) return;
            busy = true;
            string? text = null;
            try {
                string contents;
                GLib.FileUtils.get_contents (path, out contents);
                text = contents;
            } catch (GLib.Error e) {
                text = null;
            }
            state.parse (text, GLib.get_real_time () / 1000000);
            visible = state.running;
            if (state.running) {
                client.configure (state.local_url, state.email, state.password);
                yield client.refresh ();
            }
            // Watchers come from the server itself; the file only says whether a launcher is running.
            int watching = 0;
            foreach (var v in client.viewers) if (v.state == "admitted") watching++;
            int waiting = 0;
            foreach (var v in client.viewers) if (v.state == "pending") waiting++;
            string tip = !state.running ? state.tooltip ()
                : waiting > 0 ? "Someone wants to watch your screen"
                : client.live ? (watching == 1 ? "Sharing your screen · 1 person watching"
                    : watching == 0 ? "Sharing your screen · nobody watching yet"
                    : "Sharing your screen · %d people watching".printf (watching))
                : "Screen share ready · not sharing yet";
            bool offering = state.running && client.reachable && (client.live || client.link_count > 0);
            status_changed (state.running, offering, waiting, watching);
            if (spawn_dock_app && offering && tick_count++ % 3 == 0) ensure_dock_app.begin ();
            eyes.set_tooltip_text (tip);
            eyes.remove_css_class ("live");
            eyes.remove_css_class ("ask");
            if (waiting > 0) eyes.add_css_class ("ask"); else if (state.running && client.live) eyes.add_css_class ("live");
            var digest = state.running.to_string () + client.digest () + state.password + toast;
            if (digest != last_digest) {
                last_digest = digest;
                rebuild (tip);
            }
            busy = false;
        }

        /* Starts the dock app when nothing owns its bus name. It is not started twice: a second launch would raise its window. */
        private async void ensure_dock_app () {
            if (dock_check_busy) return;
            dock_check_busy = true;
            try {
                var bus = yield GLib.Bus.get (GLib.BusType.SESSION);
                var r = yield bus.call ("org.freedesktop.DBus", "/org/freedesktop/DBus", "org.freedesktop.DBus", "NameHasOwner",
                    new GLib.Variant ("(s)", "io.github.techmore.ShareEyes"), new GLib.VariantType ("(b)"), GLib.DBusCallFlags.NONE, 2000);
                bool owned;
                r.get ("(b)", out owned);
                if (!owned) {
                    new GLib.Subprocess.newv ({ "mseries-share-eyes" }, GLib.SubprocessFlags.STDOUT_SILENCE | GLib.SubprocessFlags.STDERR_SILENCE);
                }
            } catch (GLib.Error e) {
                warning ("share dock app: %s", e.message);
            }
            dock_check_busy = false;
        }

        private void copy (string text, string what) {
            eyes.get_clipboard ().set_text (text);
            toast = what + " copied";
            last_digest = "";
            GLib.Timeout.add_seconds (3, () => { toast = ""; last_digest = ""; return GLib.Source.REMOVE; });
            tick.begin ();
        }

        // Same visual language as the CodexBar panel: 9pt text, rounded translucent cards, pill chips.
        private static void install_style (Gdk.Display display) {
            var style = new Gtk.CssProvider ();
            style.load_from_string (
                ".mseries-eyes.live { color: @success_color; } " +
                ".mseries-eyes.ask { color: @warning_color; } " +
                ".mseries-share { font-size: 9pt; } " +
                ".mseries-share .caption { font-size: 8pt; } " +
                ".mseries-share .card { padding: 4px 10px; border-radius: 8px; background: alpha(currentColor, 0.06); } " +
                ".mseries-share .card-title { font-weight: 700; font-size: 8pt; opacity: 0.7; margin-top: 2px; } " +
                ".mseries-share .chip { padding: 1px 8px; border-radius: 99px; font-size: 7.5pt; font-weight: 700; " +
                "  background: alpha(currentColor, 0.1); } " +
                ".mseries-share .chip.live { background: alpha(@success_color, 0.22); color: @success_color; } " +
                ".mseries-share .chip.ask { background: alpha(@warning_color, 0.22); color: @warning_color; } " +
                ".mseries-share .state-title { font-weight: 700; font-size: 10pt; } " +
                ".mseries-share .mono { font-family: monospace; } " +
                ".mseries-share button { padding: 3px 8px; min-height: 0; } " +
                ".mseries-share button.flat { padding: 3px 5px; } " +
                ".mseries-share button.primary-wide { padding: 6px 10px; border-radius: 9px; font-weight: 600; } ");
            Gtk.StyleContext.add_provider_for_display (display, style, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION);
        }

        private Gtk.Widget dim (string text) {
            var l = new Gtk.Label (text) { halign = Gtk.Align.START, wrap = true, xalign = 0, max_width_chars = 40 };
            l.add_css_class ("dim-label");
            l.add_css_class ("caption");
            return l;
        }

        private Gtk.Box card (string? title) {
            var c = new Gtk.Box (Gtk.Orientation.VERTICAL, 2);
            c.add_css_class ("card");
            if (title != null) {
                var t = new Gtk.Label (title.up ()) { halign = Gtk.Align.START, xalign = 0 };
                t.add_css_class ("card-title");
                c.append (t);
            }
            return c;
        }

        /* label on the left, value in the middle, an icon button on the right. */
        private Gtk.Widget field_row (string label, string value, string tip, bool mono = true, string? shown = null) {
            var row = new Gtk.Box (Gtk.Orientation.HORIZONTAL, 8);
            var name = new Gtk.Label (label) { halign = Gtk.Align.START, width_chars = 8, xalign = 0 };
            name.add_css_class ("dim-label");
            var val = new Gtk.Label (shown ?? value) { halign = Gtk.Align.START, hexpand = true, xalign = 0, ellipsize = Pango.EllipsizeMode.MIDDLE };
            if (mono) val.add_css_class ("mono");
            row.append (name);
            row.append (val);
            var cp = new Gtk.Button.from_icon_name ("edit-copy-symbolic") { tooltip_text = tip };
            cp.add_css_class ("flat");
            cp.clicked.connect (() => copy (value, label));
            row.append (cp);
            return row;
        }

        private delegate void RowAction ();

        private Gtk.Widget action_row (string label, string icon, string tip, RowAction cb) {
            var row = new Gtk.Box (Gtk.Orientation.HORIZONTAL, 8);
            var name = new Gtk.Label (label) { halign = Gtk.Align.START, hexpand = true, xalign = 0 };
            row.append (name);
            var b = new Gtk.Button.from_icon_name (icon) { tooltip_text = tip };
            b.add_css_class ("flat");
            b.clicked.connect (() => cb ());
            row.append (b);
            return row;
        }

        private void act () {
            last_digest = "";
            tick.begin ();
        }

        /* An icon + label row that is one flat button, like a menu item, with a dim detail on the right. */
        private Gtk.Button item (string icon, string label, string? detail, string tip) {
            var row = new Gtk.Box (Gtk.Orientation.HORIZONTAL, 9);
            row.append (new Gtk.Image.from_icon_name (icon));
            row.append (new Gtk.Label (label) { halign = Gtk.Align.START, hexpand = true, xalign = 0, ellipsize = Pango.EllipsizeMode.END });
            if (detail != null) {
                var d = new Gtk.Label (detail);
                d.add_css_class ("dim-label");
                d.add_css_class ("caption");
                row.append (d);
            }
            var b = new Gtk.Button () { child = row, tooltip_text = tip };
            b.add_css_class ("flat");
            return b;
        }

        private Gtk.Widget watchers_card () {
            var w = card ("Watchers");
            foreach (var v in client.viewers) {
                var row = new Gtk.Box (Gtk.Orientation.HORIZONTAL, 8);
                row.append (new Gtk.Image.from_icon_name (v.state == "pending" ? "avatar-default-symbolic" : "view-reveal-symbolic"));
                var names = new Gtk.Box (Gtk.Orientation.VERTICAL, 0) { hexpand = true, valign = Gtk.Align.CENTER };
                names.append (new Gtk.Label (v.state == "pending" ? "Wants to watch" : "Watching") { halign = Gtk.Align.START, xalign = 0 });
                var where = new Gtk.Label (v.ip) { halign = Gtk.Align.START, xalign = 0 };
                where.add_css_class ("dim-label");
                where.add_css_class ("caption");
                names.append (where);
                row.append (names);
                var vid = v.vid;
                if (v.state == "pending") {
                    var deny = new Gtk.Button.with_label ("Deny");
                    deny.clicked.connect (() => client.viewer_action.begin (vid, "deny", (o, r) => { client.viewer_action.end (r); act (); }));
                    var allow = new Gtk.Button.with_label ("Allow");
                    allow.add_css_class ("suggested-action");
                    allow.clicked.connect (() => client.viewer_action.begin (vid, "admit", (o, r) => { client.viewer_action.end (r); act (); }));
                    row.append (deny);
                    row.append (allow);
                } else {
                    var rm = new Gtk.Button.with_label ("Remove");
                    rm.add_css_class ("destructive-action");
                    rm.clicked.connect (() => client.viewer_action.begin (vid, "kick", (o, r) => { client.viewer_action.end (r); act (); }));
                    row.append (rm);
                }
                w.append (row);
            }
            return w;
        }

        private void rebuild (string tip) {
            Gtk.Widget? child;
            while ((child = content.get_first_child ()) != null) content.remove (child);

            int waiting = 0, watching = 0;
            foreach (var v in client.viewers) {
                if (v.state == "pending") waiting++; else if (v.state == "admitted") watching++;
            }

            // Header: what is happening now, in one glance. A copy confirmation replaces the subtitle for a moment.
            var head = new Gtk.Box (Gtk.Orientation.HORIZONTAL, 10);
            head.append (new Gtk.Image.from_icon_name ("mseries-share-eyes-symbolic") { pixel_size = 28, valign = Gtk.Align.CENTER });
            var texts = new Gtk.Box (Gtk.Orientation.VERTICAL, 1) { hexpand = true, valign = Gtk.Align.CENTER };
            var title = new Gtk.Label (!state.running ? "Screen share is off" : waiting > 0 ? "Someone wants to watch" : client.live ? "Sharing your screen" : "Ready to share") {
                halign = Gtk.Align.START, xalign = 0 };
            title.add_css_class ("state-title");
            texts.append (title);
            texts.append (dim (toast != "" ? toast + " ✓"
                : !state.running ? "Start the demo with core/scripts/share-demo.sh."
                : !client.reachable ? "The share server is not answering."
                : waiting > 0 ? "Allow or deny below. Nothing is sent until you allow."
                : client.live ? (watching == 0 ? "Nobody is watching yet" : watching == 1 ? "1 person watching" : "%d people watching".printf (watching))
                : "Click Start sharing on the page, then pick one window"));
            head.append (texts);
            if (state.running && client.reachable) {
                var chip = new Gtk.Label (waiting > 0 ? "WAITING" : client.live ? "LIVE" : "READY") { valign = Gtk.Align.CENTER };
                chip.add_css_class ("chip");
                if (waiting > 0) chip.add_css_class ("ask"); else if (client.live) chip.add_css_class ("live");
                head.append (chip);
            }
            content.append (head);
            if (!state.running || !client.reachable) return;

            // Anyone waiting is the one thing that needs you: it goes straight under the header.
            if (waiting > 0) content.append (watchers_card ());

            if (client.live) {
                var stop = new Gtk.Button.with_label ("Stop sharing");
                stop.add_css_class ("destructive-action");
                stop.add_css_class ("primary-wide");
                stop.clicked.connect (() => client.stop.begin ((o, r) => { client.stop.end (r); act (); }));
                content.append (stop);
            } else {
                var open = new Gtk.Button.with_label ("Open share page and sign in");
                open.add_css_class ("suggested-action");
                open.add_css_class ("primary-wide");
                open.clicked.connect (() => {
                    try { GLib.AppInfo.launch_default_for_uri (state.login_url (), null); } catch (GLib.Error e) { warning ("%s", e.message); }
                });
                content.append (open);
            }

            if (waiting == 0 && watching > 0) content.append (watchers_card ());

            // Links: one flat menu-style item each, so the card reads as a short list.
            var links = card (null);
            var bases = state.link_bases ();
            for (int bi = 0; bi < bases.length[0]; bi++) {
                var label = bases[bi, 0];
                var origin = bases[bi, 1];
                var link = client.viewer_link (origin);
                if (link != null) {
                    var cv = item ("insert-link-symbolic", "Copy %s link".printf (label.down ()),
                        bi == 0 ? "until " + new GLib.DateTime.from_unix_local (client.link_expires).format ("%H:%M") : null, "Copy the " + label.down () + " link for your viewer");
                    cv.clicked.connect (() => copy (link, label + " link"));
                    links.append (cv);
                }
            }
            if (client.viewer_link (state.viewer_base) == null) {
                var mk = item ("list-add-symbolic", "Create viewer link", null, "Make a link to send to your viewer");
                mk.clicked.connect (() => { client.create_link.begin ((o, r) => { client.create_link.end (r); act (); }); });
                links.append (mk);
            }
            var cs = item ("dialog-password-symbolic", "Copy sign-in link", "this computer only",
                "Opens the share page already signed in. Never send it to your viewer.");
            cs.clicked.connect (() => copy (state.login_url (), "Sign-in link"));
            links.append (cs);
            content.append (links);

            // Raw login is a fallback for another browser, so it is tucked away.
            var more = new Gtk.Expander ("Login details") { margin_top = 2 };
            var box = new Gtk.Box (Gtk.Orientation.VERTICAL, 2) { margin_top = 4 };
            box.append (field_row ("Username", state.email, "Copy username"));
            box.append (field_row ("Password", state.password, "Copy password"));
            more.child = box;
            more.expanded = details_open;
            more.notify["expanded"].connect (() => { details_open = more.expanded; });
            content.append (more);
        }
    }
}
