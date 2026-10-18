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

            content = new Gtk.Box (Gtk.Orientation.VERTICAL, 8);
            install_style (content.get_display ());
            menu = new Gtk.Box (Gtk.Orientation.VERTICAL, 0) {
                margin_top = 8, margin_bottom = 8, margin_start = 8, margin_end = 8, width_request = 320
            };
            menu.add_css_class ("mseries-share");
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

        // Same visual language as the CodexBar panel: 9pt text, rounded translucent cards, pill chips.
        private static void install_style (Gdk.Display display) {
            var style = new Gtk.CssProvider ();
            style.load_from_string (
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

        private void rebuild (string tip) {
            Gtk.Widget? child;
            while ((child = content.get_first_child ()) != null) content.remove (child);

            int waiting = 0;
            foreach (var v in client.viewers) if (v.state == "pending") waiting++;

            // Header: icon, state, a pill chip, and one line about what to do.
            var head = new Gtk.Box (Gtk.Orientation.HORIZONTAL, 10);
            head.append (new Gtk.Image.from_icon_name ("mseries-share-eyes-symbolic") { pixel_size = 28, valign = Gtk.Align.CENTER });
            var texts = new Gtk.Box (Gtk.Orientation.VERTICAL, 1) { hexpand = true, valign = Gtk.Align.CENTER };
            var title = new Gtk.Label (!state.running ? "Screen share is off" : waiting > 0 ? "Someone wants to watch" : client.live ? "Sharing your screen" : "Ready to share") { halign = Gtk.Align.START, xalign = 0 };
            title.add_css_class ("state-title");
            texts.append (title);
            int watching = 0;
            foreach (var v in client.viewers) if (v.state == "admitted") watching++;
            texts.append (dim (!state.running ? "Start the demo with core/scripts/share-demo.sh."
                : client.live ? (watching == 0 ? "Nobody is watching yet" : watching == 1 ? "1 person watching" : "%d people watching".printf (watching))
                : "Not sharing anything yet"));
            head.append (texts);
            if (state.running && client.reachable) {
                var chip = new Gtk.Label (waiting > 0 ? "WAITING" : client.live ? "LIVE" : "READY") { valign = Gtk.Align.CENTER };
                chip.add_css_class ("chip");
                if (waiting > 0) chip.add_css_class ("ask"); else if (client.live) chip.add_css_class ("live");
                head.append (chip);
            }
            content.append (head);
            if (!state.running) return;
            if (!client.reachable) {
                content.append (dim ("The share server is not answering."));
                return;
            }

            if (!client.live) {
                var open = new Gtk.Button.with_label ("Open share page and sign in");
                open.add_css_class ("suggested-action");
                open.add_css_class ("primary-wide");
                open.clicked.connect (() => {
                    try { GLib.AppInfo.launch_default_for_uri (state.login_url (), null); } catch (GLib.Error e) { warning ("%s", e.message); }
                });
                content.append (open);
                content.append (dim ("Click Start sharing there, then pick one window."));
            } else {
                var stop = new Gtk.Button.with_label ("Stop sharing");
                stop.add_css_class ("destructive-action");
                stop.add_css_class ("primary-wide");
                stop.clicked.connect (() => client.stop.begin ((o, r) => { client.stop.end (r); act (); }));
                content.append (stop);
            }

            var watchers = card ("Watchers");
            if (client.viewers.length == 0) {
                watchers.append (dim ("Nobody yet."));
            }
            foreach (var v in client.viewers) {
                var row = new Gtk.Box (Gtk.Orientation.HORIZONTAL, 8);
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
                watchers.append (row);
            }
            content.append (watchers);

            var links = card ("Links");
            var link = client.viewer_link (state.viewer_base);
            if (link != null) {
                links.append (field_row ("Viewer", link, "Copy the link for your viewer", false, "Link for your buddy"));
            } else {
                links.append (action_row ("Viewer link", "list-add-symbolic", "Create a link for your viewer", () => {
                    client.create_link.begin ((o, r) => { client.create_link.end (r); act (); });
                }));
            }
            links.append (field_row ("Sign-in", state.login_url (), "Copy a link that signs in on this computer. Never send it to your viewer.", false, "This computer only"));
            content.append (links);

            var login = card ("Login");
            login.append (field_row ("Username", state.email, "Copy username"));
            login.append (field_row ("Password", state.password, "Copy password"));
            content.append (login);
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
