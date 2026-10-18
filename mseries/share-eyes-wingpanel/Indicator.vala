/* Screen share in Wingpanel: a pair of eyes whose popover is the whole interaction
 * (login to copy, viewer link, approve or remove watchers, stop). See ShareState for the launcher contract. */
using Gtk;
using Wingpanel;

namespace MSeries {
    public class ShareEyesIndicator : Wingpanel.Indicator {
        private Gtk.Image eyes;
        private Gtk.Box menu;
        private Gtk.Box content;
        private ShareState state = new ShareState ();
        private ShareClient client = new ShareClient ();
        private string path = ShareState.default_path ();
        private string last_digest = "";
        private string toast = "";
        private uint poll_source = 0;
        private bool busy = false;

        public ShareEyesIndicator () {
            GLib.Object (code_name: "mseries-share-eyes");
        }

        construct {
            eyes = new Gtk.Image.from_icon_name ("mseries-share-eyes-symbolic") { pixel_size = 18 };
            eyes.set_tooltip_text (state.tooltip ());
            this.visible = false;

            content = new Gtk.Box (Gtk.Orientation.VERTICAL, 6);
            menu = new Gtk.Box (Gtk.Orientation.VERTICAL, 0) {
                margin_top = 10, margin_bottom = 10, margin_start = 12, margin_end = 12, width_request = 320
            };
            menu.append (content);

            tick.begin ();
            poll_source = GLib.Timeout.add_seconds (2, () => { tick.begin (); return GLib.Source.CONTINUE; });
        }

        ~ShareEyesIndicator () {
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
            this.visible = state.running;
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
            eyes.set_tooltip_text (tip);
            if (waiting > 0) eyes.add_css_class ("accent"); else eyes.remove_css_class ("accent");
            var digest = state.running.to_string () + client.digest () + state.password + toast;
            if (digest != last_digest) {
                last_digest = digest;
                rebuild (tip);
            }
            busy = false;
        }

        private void copy (string text, string what) {
            eyes.get_clipboard ().set_text (text);
            toast = what + " copied";
            last_digest = "";
            GLib.Timeout.add_seconds (3, () => { toast = ""; last_digest = ""; return GLib.Source.REMOVE; });
            tick.begin ();
        }

        private Gtk.Widget header (string text) {
            var l = new Gtk.Label (text.up ()) { halign = Gtk.Align.START, margin_top = 6, margin_bottom = 2 };
            l.add_css_class ("dim-label");
            l.add_css_class ("caption-heading");
            return l;
        }

        private Gtk.Widget dim (string text) {
            var l = new Gtk.Label (text) { halign = Gtk.Align.START, wrap = true, xalign = 0, max_width_chars = 38 };
            l.add_css_class ("dim-label");
            l.add_css_class ("caption");
            return l;
        }

        private Gtk.Widget separator () {
            return new Gtk.Separator (Gtk.Orientation.HORIZONTAL) { margin_top = 6, margin_bottom = 6 };
        }

        /* A flat, full-width menu row: icon, label, optional detail, like Wingpanel's own menu items. */
        private Gtk.Button menu_row (string icon, string label, string? detail = null) {
            var row = new Gtk.Box (Gtk.Orientation.HORIZONTAL, 9);
            row.append (new Gtk.Image.from_icon_name (icon));
            var l = new Gtk.Label (label) { halign = Gtk.Align.START, hexpand = true, xalign = 0, ellipsize = Pango.EllipsizeMode.END };
            row.append (l);
            if (detail != null) {
                var d = new Gtk.Label (detail) { halign = Gtk.Align.END };
                d.add_css_class ("dim-label");
                row.append (d);
            }
            var b = new Gtk.Button () { child = row };
            b.add_css_class ("flat");
            return b;
        }

        private Gtk.Widget field_row (string label, string value) {
            var row = new Gtk.Box (Gtk.Orientation.HORIZONTAL, 8);
            var name = new Gtk.Label (label) { halign = Gtk.Align.START, width_chars = 9, xalign = 0 };
            name.add_css_class ("dim-label");
            var val = new Gtk.Label (value) { halign = Gtk.Align.START, hexpand = true, xalign = 0, selectable = true, ellipsize = Pango.EllipsizeMode.MIDDLE };
            val.add_css_class ("monospace");
            row.append (name);
            row.append (val);
            var cp = new Gtk.Button.from_icon_name ("edit-copy-symbolic") { tooltip_text = "Copy " + label.down () };
            cp.add_css_class ("flat");
            cp.clicked.connect (() => copy (value, label));
            row.append (cp);
            return row;
        }

        private void act (owned GLib.AsyncReadyCallback? cb = null) {
            last_digest = "";
            tick.begin ();
        }

        private void rebuild (string tip) {
            Gtk.Widget? child;
            while ((child = content.get_first_child ()) != null) content.remove (child);

            // Status card: the icon says it at a glance, the line under it says what to do.
            var head = new Gtk.Box (Gtk.Orientation.HORIZONTAL, 10) { margin_bottom = 2 };
            var big = new Gtk.Image.from_icon_name ("mseries-share-eyes-symbolic") { pixel_size = 32, valign = Gtk.Align.START };
            if (client.live) big.add_css_class ("accent");
            head.append (big);
            var texts = new Gtk.Box (Gtk.Orientation.VERTICAL, 2) { hexpand = true };
            var title = new Gtk.Label (!state.running ? "Screen share is off" : client.live ? "Sharing your screen" : "Screen share")
                { halign = Gtk.Align.START, xalign = 0 };
            title.add_css_class ("title-4");
            texts.append (title);
            texts.append (dim (state.running ? tip : "Start the demo with core/scripts/share-demo.sh."));
            head.append (texts);
            content.append (head);
            if (!state.running) return;
            if (!client.reachable) {
                content.append (dim ("The share server is not answering."));
                return;
            }

            if (!client.live) {
                var open = new Gtk.Button.with_label ("Open share page and sign in") { margin_top = 6 };
                open.add_css_class ("suggested-action");
                open.clicked.connect (() => {
                    try { GLib.AppInfo.launch_default_for_uri (state.login_url (), null); } catch (GLib.Error e) { warning ("%s", e.message); }
                });
                content.append (open);
                content.append (dim ("Then click Start sharing and pick one window."));
            } else {
                var stop = new Gtk.Button.with_label ("Stop sharing") { margin_top = 6 };
                stop.add_css_class ("destructive-action");
                stop.clicked.connect (() => client.stop.begin ((o, r) => { client.stop.end (r); act (); }));
                content.append (stop);
            }

            // Watchers first once someone is waiting: that is the thing you have to act on.
            content.append (separator ());
            content.append (header ("Watchers"));
            if (client.viewers.length == 0) {
                content.append (dim ("Nobody yet."));
            }
            foreach (var v in client.viewers) {
                var row = new Gtk.Box (Gtk.Orientation.HORIZONTAL, 8);
                row.append (new Gtk.Image.from_icon_name (v.state == "pending" ? "avatar-default-symbolic" : "view-reveal-symbolic"));
                var who = new Gtk.Label (v.state == "pending" ? "Wants to watch" : "Watching")
                    { halign = Gtk.Align.START, xalign = 0 };
                var where = new Gtk.Label (v.ip) { halign = Gtk.Align.START, hexpand = true, xalign = 0, ellipsize = Pango.EllipsizeMode.END };
                where.add_css_class ("dim-label");
                var names = new Gtk.Box (Gtk.Orientation.VERTICAL, 0) { hexpand = true };
                names.append (who);
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
                content.append (row);
            }

            content.append (separator ());
            content.append (header ("Share"));
            var link = client.viewer_link (state.viewer_base);
            if (link != null) {
                var cl = menu_row ("insert-link-symbolic", "Copy viewer link",
                    "until " + new GLib.DateTime.from_unix_local (client.link_expires).format ("%H:%M"));
                cl.clicked.connect (() => copy (link, "Viewer link"));
                content.append (cl);
            } else {
                var mk = menu_row ("list-add-symbolic", "Create viewer link");
                mk.clicked.connect (() => { client.create_link.begin ((o, r) => { client.create_link.end (r); act (); }); });
                content.append (mk);
            }
            var cll = menu_row ("dialog-password-symbolic", "Copy login link");
            cll.tooltip_text = "Opens the share page already signed in. For this computer only; never send it to your viewer.";
            cll.clicked.connect (() => copy (state.login_url (), "Login link"));
            content.append (cll);

            content.append (separator ());
            content.append (header ("Login"));
            content.append (field_row ("Username", state.email));
            content.append (field_row ("Password", state.password));
            if (toast != "") content.append (dim (toast));
        }

        public override Gtk.Widget get_display_widget () {
            return eyes;
        }

        public override Gtk.Widget? get_widget () {
            return menu;
        }

        public override void opened () {
            last_digest = "";
            tick.begin ();
        }

        public override void closed () {
        }
    }
}

public Wingpanel.Indicator? get_indicator (Module module, Wingpanel.ServerType server_type) {
    if (server_type != Wingpanel.ServerType.SESSION) {
        return null;
    }
    return new MSeries.ShareEyesIndicator ();
}
