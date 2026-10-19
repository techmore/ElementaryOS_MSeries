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
        /* In Quick Settings: a desktop notification when a viewer starts waiting, so it is noticed without opening the menu. */
        public bool notify_waiting { get; set; default = false; }
        /* In Quick Settings the section is always there; when no share server runs it offers to start one. */
        public bool always_visible { get; set; default = false; }
        private int last_waiting = 0;
        private int last_watching = 0;
        private bool auto_allow = FileUtils.test (GLib.Path.build_filename (GLib.Environment.get_user_config_dir (), "rupert-share", "auto-allow"), FileTest.EXISTS);
        private uint32 notification_id = 0;

        construct {
            eyes = new Gtk.Image.from_icon_name ("mseries-share-eyes-symbolic") { pixel_size = 18 };
            eyes.add_css_class ("mseries-eyes");
            eyes.set_tooltip_text (state.tooltip ());
            orientation = Gtk.Orientation.VERTICAL;
            visible = false;
            add_css_class ("mseries-share");
            
            content = new Gtk.Box (Gtk.Orientation.VERTICAL, 0);
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
            visible = state.running || always_visible;
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
            if (notify_waiting && waiting > last_waiting) notify_viewer.begin ("Someone wants to watch your screen", "Open the eyes menu to allow or deny.");
            if (notify_waiting && watching > last_watching && client.link_auto) notify_viewer.begin ("Someone joined your screen share", "Their link lets people in without asking. Open the eyes menu to remove them.");
            last_waiting = waiting;
            last_watching = watching;
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

        private async void notify_viewer (string summary, string body) {
            try {
                var bus = yield GLib.Bus.get (GLib.BusType.SESSION);
                var args = new GLib.VariantBuilder (new GLib.VariantType ("(susssasa{sv}i)"));
                args.add ("s", "Screen Share");
                args.add ("u", notification_id);
                args.add ("s", "mseries-share-eyes-symbolic");
                args.add ("s", summary);
                args.add ("s", body);
                args.add_value (new GLib.Variant.array (new GLib.VariantType ("s"), {}));
                args.add_value (new GLib.Variant.array (new GLib.VariantType ("{sv}"), {}));
                args.add ("i", 15000);
                var r = yield bus.call ("org.freedesktop.Notifications", "/org/freedesktop/Notifications", "org.freedesktop.Notifications", "Notify",
                    args.end (), new GLib.VariantType ("(u)"), GLib.DBusCallFlags.NONE, 2000);
                r.get ("(u)", out notification_id);
            } catch (GLib.Error e) {
                warning ("notification: %s", e.message);
            }
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

        /* Only what the theme cannot give: the live/ask colours (theme named colours, so dark mode follows) and a monospace value. */
        private static void install_style (Gdk.Display display) {
            var style = new Gtk.CssProvider ();
            style.load_from_string (
                ".mseries-eyes.live { color: @success_color; } " +
                ".mseries-eyes.ask { color: @warning_color; } " +
                ".mseries-share .mono { font-family: monospace; } ");
            Gtk.StyleContext.add_provider_for_display (display, style, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION);
        }

        private Gtk.Widget dim (string text) {
            var l = new Gtk.Label (text) { halign = Gtk.Align.START, wrap = true, xalign = 0, max_width_chars = 40 };
            l.add_css_class (Granite.CssClass.DIM);
            l.add_css_class ("caption");
            return l;
        }

        /* Section title, as in Sound Output. */
        private Gtk.Widget section (string title) {
            return new Granite.HeaderLabel (title) { margin_top = 6 };
        }

        /* A row inset like the Bluetooth device list. */
        private Gtk.Box inset_row (int spacing = 8) {
            return new Gtk.Box (Gtk.Orientation.HORIZONTAL, spacing) { margin_start = 12, margin_end = 12, margin_top = 3, margin_bottom = 3 };
        }

        private static void name_button (Gtk.Button b, string name) {
            b.update_property (Gtk.AccessibleProperty.LABEL, name, -1);
        }

        /* label on the left, value in the middle, an icon button on the right. */
        private Gtk.Widget field_row (string label, string value, string tip, bool mono = true, string? shown = null) {
            var row = inset_row ();
            var name = new Gtk.Label (label) { halign = Gtk.Align.START, width_chars = 8, xalign = 0 };
            name.add_css_class (Granite.CssClass.DIM);
            var val = new Gtk.Label (shown ?? value) { halign = Gtk.Align.START, hexpand = true, xalign = 0, ellipsize = Pango.EllipsizeMode.MIDDLE };
            if (mono) val.add_css_class ("mono");
            row.append (name);
            row.append (val);
            var cp = new Gtk.Button.from_icon_name ("edit-copy-symbolic") { tooltip_text = tip };
            cp.add_css_class ("flat");
            name_button (cp, tip);
            cp.clicked.connect (() => copy (value, label));
            row.append (cp);
            return row;
        }

        private void act () {
            last_digest = "";
            tick.begin ();
        }

        /* An icon + label row that is one flat button, like a menu item, with a dim detail on the right. */
        private Gtk.Button item (string icon, string label, string? detail, string tip) {
            var row = new Gtk.Box (Gtk.Orientation.HORIZONTAL, 6);
            row.append (new Gtk.Image.from_icon_name (icon) { pixel_size = 16 });
            row.append (new Gtk.Label (label) { halign = Gtk.Align.START, hexpand = true, xalign = 0, ellipsize = Pango.EllipsizeMode.END });
            if (detail != null) {
                var d = new Gtk.Label (detail) { ellipsize = Pango.EllipsizeMode.END };
                d.add_css_class (Granite.CssClass.DIM);
                d.add_css_class ("caption");
                row.append (d);
            }
            var b = new Gtk.Button () { child = row, tooltip_text = tip, margin_start = 6, margin_end = 6 };
            b.add_css_class ("flat");
            name_button (b, label);
            return b;
        }

        /* A full-width action under the status, inset like the sibling rows. */
        private Gtk.Button primary_button (string label, string style, string? tip = null) {
            var b = new Gtk.Button.with_label (label) { margin_start = 12, margin_end = 12, margin_top = 3, margin_bottom = 3, tooltip_text = tip };
            b.add_css_class (style);
            return b;
        }

        private Gtk.Widget viewers_list () {
            var w = new Gtk.Box (Gtk.Orientation.VERTICAL, 0);
            foreach (var v in client.viewers) {
                var row = inset_row ();
                row.append (new Gtk.Image.from_icon_name (v.state == "pending" ? "avatar-default-symbolic" : "view-reveal-symbolic") { pixel_size = 16 });
                var names = new Gtk.Box (Gtk.Orientation.VERTICAL, 0) { hexpand = true, valign = Gtk.Align.CENTER };
                names.append (new Gtk.Label (v.state == "pending" ? "Wants to watch" : "Watching") { halign = Gtk.Align.START, xalign = 0 });
                var where = new Gtk.Label (v.ip) { halign = Gtk.Align.START, xalign = 0, ellipsize = Pango.EllipsizeMode.END };
                where.add_css_class (Granite.CssClass.DIM);
                where.add_css_class ("caption");
                names.append (where);
                row.append (names);
                var vid = v.vid;
                if (v.state == "pending") {
                    var deny = new Gtk.Button.with_label ("Deny");
                    deny.clicked.connect (() => client.viewer_action.begin (vid, "deny", (o, r) => { client.viewer_action.end (r); act (); }));
                    var allow = new Gtk.Button.with_label ("Allow");
                    allow.add_css_class (Granite.CssClass.SUGGESTED);
                    allow.clicked.connect (() => client.viewer_action.begin (vid, "admit", (o, r) => { client.viewer_action.end (r); act (); }));
                    row.append (deny);
                    row.append (allow);
                } else {
                    // Letting someone go is routine, not dangerous: a plain button (destructive is kept for Stop Sharing).
                    var rm = new Gtk.Button.with_label ("Remove");
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

            // Status: one row like a Sound Output entry (16px icon, title, dim caption). A copy confirmation replaces the caption for a moment.
            content.append (section ("Screen Share"));
            var head = inset_row (8);
            var status_icon = new Gtk.Image.from_icon_name ("mseries-share-eyes-symbolic") { pixel_size = 16, valign = Gtk.Align.CENTER };
            status_icon.add_css_class ("mseries-eyes");
            if (waiting > 0) status_icon.add_css_class ("ask"); else if (state.running && client.live) status_icon.add_css_class ("live");
            head.append (status_icon);
            var texts = new Gtk.Box (Gtk.Orientation.VERTICAL, 0) { hexpand = true, valign = Gtk.Align.CENTER };
            texts.append (new Gtk.Label (!state.running ? "Screen sharing is off" : !client.reachable ? "Screen share isn't responding" : waiting > 0 ? "Someone wants to watch" : client.live ? "Sharing your screen" : "Ready to share") {
                halign = Gtk.Align.START, xalign = 0 });
            texts.append (dim (toast != "" ? toast + (toast == "Starting" ? "…" : " ✓")
                : !state.running ? (always_visible ? "Nothing is being shared" : "Start the demo with core/scripts/share-demo.sh.")
                : !client.reachable ? "Try again in a moment"
                : waiting > 0 ? "Nothing is shown until you allow"
                : client.live ? (watching == 0 ? "Nobody is watching yet" : watching == 1 ? "1 person watching" : "%d people watching".printf (watching))
                : "Choose what to share to begin"));
            head.append (texts);
            content.append (head);
            if (!state.running) {
                if (always_visible) {
                    var go = primary_button ("Start Screen Share", Granite.CssClass.SUGGESTED);
                    go.clicked.connect (() => {
                        try {
                            new GLib.Subprocess (GLib.SubprocessFlags.STDOUT_SILENCE | GLib.SubprocessFlags.STDERR_SILENCE, "mseries-share-start");
                            toast = "Starting";
                        } catch (GLib.Error e) {
                            toast = "Could not start";
                            warning ("%s", e.message);
                        }
                        act ();
                    });
                    content.append (go);
                }
                return;
            }
            if (!client.reachable) return;

            // Main action, straight under the status.
            if (client.live) {
                var stop = primary_button ("Stop Sharing", Granite.CssClass.DESTRUCTIVE);
                stop.clicked.connect (() => client.stop.begin ((o, r) => { client.stop.end (r); act (); }));
                content.append (stop);
            } else {
                var open = primary_button ("Choose What to Share…", Granite.CssClass.SUGGESTED,
                    "Opens the share page, already signed in. Press Start sharing there, then pick a window.");
                open.clicked.connect (() => {
                    try { GLib.AppInfo.launch_default_for_uri (state.login_url (), null); } catch (GLib.Error e) { warning ("%s", e.message); }
                });
                content.append (open);
            }

            // Anyone waiting is the one thing that needs you, so the list is above the links.
            if (waiting > 0 || watching > 0) {
                content.append (section ("Viewers"));
                content.append (viewers_list ());
            }

            // Invite: the Internet link first when there is one (it is the one to send), then the local one.
            content.append (section ("Invite Viewers"));
            var bases = state.link_bases ();
            for (int bi = 0; bi < bases.length[0]; bi++) {
                var label = bases[bi, 0];
                var origin = bases[bi, 1];
                var link = client.viewer_link (origin);
                if (link != null) {
                    var cv = item ("insert-link-symbolic", "Copy %s Link".printf (label),
                        bi == 0 ? "until " + new GLib.DateTime.from_unix_local (client.link_expires).format ("%H:%M") : null,
                        "Copy the " + label.down () + " link to send to your viewer");
                    cv.clicked.connect (() => copy (link, label + " link"));
                    content.append (cv);
                }
            }
            if (client.viewer_link (state.viewer_base) == null) {
                var mk = item ("list-add-symbolic", "Create Viewer Link", null, "Make a link to send to your viewer");
                mk.clicked.connect (() => { auto_allow = FileUtils.test (GLib.Path.build_filename (GLib.Environment.get_user_config_dir (), "rupert-share", "auto-allow"), FileTest.EXISTS); client.create_link.begin (auto_allow, (o, r) => { client.create_link.end (r); act (); }); });
                content.append (mk);
            }
            // Opt-in, per link: people who open a link made while this is on skip the Allow step (you are still notified).
            var auto_switch = new Granite.SwitchModelButton ("Admit Viewers Automatically");
            auto_switch.description = client.link_auto ? "This link lets anyone who opens it in" : "Applies to the next link you create";
            // Granite shows the description only while the switch is on, like the Bluetooth and charge-limit rows.
            auto_switch.active = auto_allow;
            auto_switch.notify["active"].connect (() => {
                auto_allow = auto_switch.active;
                var f = GLib.Path.build_filename (GLib.Environment.get_user_config_dir (), "rupert-share", "auto-allow");
                try {
                    if (auto_allow) {
                        GLib.DirUtils.create_with_parents (GLib.Path.get_dirname (f), 0700);
                        GLib.FileUtils.set_contents (f, "1");
                    } else {
                        GLib.FileUtils.unlink (f);
                    }
                } catch (GLib.Error e) {
                    warning ("%s", e.message);
                }
                act ();
            });
            content.append (auto_switch);

            // For this computer only: kept apart from the links you send.
            content.append (section ("This Computer"));
            var cs = item ("dialog-password-symbolic", "Copy Sign-in Link", null,
                "Opens the share page already signed in. Never send it to your viewer.");
            cs.clicked.connect (() => copy (state.login_url (), "Sign-in link"));
            content.append (cs);

            // Raw login is a fallback for another browser, so it is tucked away.
            var more = new Gtk.Expander ("Sign-in Details") { margin_start = 12, margin_end = 12, margin_top = 3, margin_bottom = 3 };
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
