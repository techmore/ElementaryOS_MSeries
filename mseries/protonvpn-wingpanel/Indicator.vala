using GLib;
using Gtk;
using Wingpanel;

namespace MSeries {
    public class ProtonVpnIndicator : Wingpanel.Indicator {
        private Gtk.Box panel_widget;
        private Gtk.Box menu_widget;

        public ProtonVpnIndicator () {
            GLib.Object (code_name: "mseries-protonvpn");
        }

        construct {
            panel_widget = new Gtk.Box (Gtk.Orientation.HORIZONTAL, 0);
            var icon_button = new Gtk.Button () {
                child = new Gtk.Image.from_icon_name ("com.protonvpn.www") { pixel_size = 16 },
                tooltip_text = "Proton VPN"
            };
            icon_button.add_css_class ("flat");
            icon_button.clicked.connect (() => launch_proton_vpn ());
            panel_widget.append (icon_button);

            menu_widget = new Gtk.Box (Gtk.Orientation.VERTICAL, 8) {
                margin_top = 8,
                margin_bottom = 8,
                margin_start = 8,
                margin_end = 8,
                width_request = 220
            };
            var title = new Gtk.Label ("Proton VPN") {
                xalign = 0,
                hexpand = true
            };
            title.add_css_class ("heading");
            menu_widget.append (title);

            var open_button = new Gtk.Button.with_label ("Open Proton VPN") {
                hexpand = true
            };
            open_button.clicked.connect (() => {
                popdown_menu (open_button);
                launch_proton_vpn ();
            });
            menu_widget.append (open_button);
            visible = true;
        }

        public override Gtk.Widget get_display_widget () {
            return panel_widget;
        }

        public override Gtk.Widget? get_widget () {
            return menu_widget;
        }

        public override void opened () {}
        public override void closed () {}

        private static void popdown_menu (Gtk.Widget widget) {
            var popover = widget.get_ancestor (typeof (Gtk.Popover)) as Gtk.Popover;
            if (popover != null) {
                popover.popdown ();
            }
        }

        private static void launch_proton_vpn () {
            try {
                Pid child_pid;
                string[] command = { "flatpak", "run", "--user", "com.protonvpn.www" };
                Process.spawn_async (
                    null,
                    command,
                    null,
                    SpawnFlags.SEARCH_PATH | SpawnFlags.STDOUT_TO_DEV_NULL | SpawnFlags.STDERR_TO_DEV_NULL,
                    null,
                    out child_pid
                );
            } catch (Error error) {
                warning ("Could not open Proton VPN: %s", error.message);
            }
        }
    }
}

public Wingpanel.Indicator? get_indicator (Module module, Wingpanel.ServerType server_type) {
    if (server_type != Wingpanel.ServerType.SESSION) {
        return null;
    }
    return new MSeries.ProtonVpnIndicator ();
}
