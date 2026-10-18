/* A pair of eyes in Wingpanel while this machine's screen is being shared (see ShareState for the file contract). */
using Gtk;
using Wingpanel;

namespace MSeries {
    public class ShareEyesIndicator : Wingpanel.Indicator {
        private Gtk.Image eyes;
        private Gtk.Box menu;
        private Gtk.Label status_label;
        private ShareState state = new ShareState ();
        private string path = ShareState.default_path ();
        private uint poll_source = 0;

        public ShareEyesIndicator () {
            GLib.Object (code_name: "mseries-share-eyes");
        }

        construct {
            eyes = new Gtk.Image.from_icon_name ("mseries-share-eyes-symbolic") { pixel_size = 18 };
            eyes.set_tooltip_text (state.tooltip ());
            this.visible = false;

            status_label = new Gtk.Label ("") { halign = Gtk.Align.START, margin_bottom = 4 };
            var open = new Gtk.Button.with_label ("Open the share page to stop") { halign = Gtk.Align.FILL };
            open.clicked.connect (() => {
                try {
                    GLib.AppInfo.launch_default_for_uri ("http://127.0.0.1:8799/share", null);
                } catch (GLib.Error e) {
                    warning ("could not open the share page: %s", e.message);
                }
            });
            menu = new Gtk.Box (Gtk.Orientation.VERTICAL, 4) {
                margin_top = 8, margin_bottom = 8, margin_start = 12, margin_end = 12, width_request = 240
            };
            menu.append (status_label);
            menu.append (open);

            refresh ();
            poll_source = GLib.Timeout.add_seconds (2, () => { refresh (); return GLib.Source.CONTINUE; });
        }

        ~ShareEyesIndicator () {
            if (poll_source != 0) {
                GLib.Source.remove (poll_source);
            }
        }

        private void refresh () {
            string? text = null;
            try {
                string contents;
                GLib.FileUtils.get_contents (path, out contents);
                text = contents;
            } catch (GLib.Error e) {
                text = null;
            }
            state.parse (text, GLib.get_real_time () / 1000000);
            this.visible = state.live;
            eyes.set_tooltip_text (state.tooltip ());
            status_label.set_text (state.tooltip ());
        }

        public override Gtk.Widget get_display_widget () {
            return eyes;
        }

        public override Gtk.Widget? get_widget () {
            return menu;
        }

        public override void opened () {
            refresh ();
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
