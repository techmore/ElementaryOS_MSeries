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
            var l = new Gtk.Label (text) { halign = Gtk.Align.START, margin_top = 8 };
            l.add_css_class ("h4");
            return l;
        }

        private Gtk.Widget dim (string text) {
            var l = new Gtk.Label (text) { halign = Gtk.Align.START, wrap = true, xalign = 0 };
            l.add_css_class ("dim-label");
            return l;
        }

        private Gtk.Widget field_row (string label, string value, bool secret) {
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

        private void rebuild (string tip) {
            Gtk.Widget? child;
            while ((child = content.get_first_child ()) != null) content.remove (child);

            var title = new Gtk.Label (state.running ? (client.live ? "Sharing your screen" : "Screen share") : "Screen share is off") { halign = Gtk.Align.START };
            title.add_css_class ("title-3");
            content.append (title);
            content.append (dim (state.running ? tip : "Start the demo with core/scripts/share-demo.sh."));
            if (!state.running) return;
            if (!client.reachable) {
                content.append (dim ("The share server is not answering."));
                return;
            }

            // 1. Start / stop
            if (!client.live) {
                content.append (dim ("Open the share page, sign in with the login below and click Start sharing. The browser asks which window to share."));
                var open = new Gtk.Button.with_label ("Open share page");
                open.add_css_class ("suggested-action");
                open.clicked.connect (() => {
                    try { GLib.AppInfo.launch_default_for_uri (state.share_page, null); } catch (GLib.Error e) { warning ("%s", e.message); }
                });
                content.append (open);
            }

            // 2. Login
            content.append (header ("Login"));
            content.append (field_row ("Username", state.email, false));
            content.append (field_row ("Password", state.password, true));
            var copy_login = new Gtk.Button.with_label ("Copy login");
            copy_login.clicked.connect (() => copy (state.login_text (), "Login"));
            content.append (copy_login);

            // 3. Link for the watcher
            content.append (header ("Link for your viewer"));
            var link = client.viewer_link (state.viewer_base);
            if (link != null) {
                content.append (field_row ("Link", link, false));
                content.append (dim ("Valid until " + new GLib.DateTime.from_unix_local (client.link_expires).format ("%a %H:%M")
                    + ". Anyone with it can ask to watch; you still approve them."));
            } else {
                var mk = new Gtk.Button.with_label ("Create viewer link");
                mk.clicked.connect (() => { client.create_link.begin ((o, r) => { client.create_link.end (r); last_digest = ""; tick.begin (); }); });
                content.append (mk);
            }

            // 4. Watchers
            content.append (header ("Watchers"));
            if (client.viewers.length == 0) {
                content.append (dim ("Nobody yet."));
            }
            foreach (var v in client.viewers) {
                var row = new Gtk.Box (Gtk.Orientation.HORIZONTAL, 6);
                var who = new Gtk.Label (v.state == "pending" ? "Wants to watch · " + v.ip : "Watching · " + v.ip)
                    { halign = Gtk.Align.START, hexpand = true, xalign = 0, ellipsize = Pango.EllipsizeMode.END };
                row.append (who);
                var vid = v.vid;
                if (v.state == "pending") {
                    var deny = new Gtk.Button.with_label ("Deny");
                    deny.clicked.connect (() => client.viewer_action.begin (vid, "deny", (o, r) => { client.viewer_action.end (r); last_digest = ""; tick.begin (); }));
                    var allow = new Gtk.Button.with_label ("Allow");
                    allow.add_css_class ("suggested-action");
                    allow.clicked.connect (() => client.viewer_action.begin (vid, "admit", (o, r) => { client.viewer_action.end (r); last_digest = ""; tick.begin (); }));
                    row.append (deny);
                    row.append (allow);
                } else {
                    var rm = new Gtk.Button.with_label ("Remove");
                    rm.add_css_class ("destructive-action");
                    rm.clicked.connect (() => client.viewer_action.begin (vid, "kick", (o, r) => { client.viewer_action.end (r); last_digest = ""; tick.begin (); }));
                    row.append (rm);
                }
                content.append (row);
            }

            if (client.live) {
                var stop = new Gtk.Button.with_label ("Stop sharing") { margin_top = 8 };
                stop.add_css_class ("destructive-action");
                stop.clicked.connect (() => client.stop.begin ((o, r) => { client.stop.end (r); last_digest = ""; tick.begin (); }));
                content.append (stop);
            }
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
