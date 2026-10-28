/* SPDX-License-Identifier: GPL-3.0-or-later
 * SPDX-FileCopyrightText: 2026 ElementaryOS_MSeries
 * Tailscale in the top panel: status, this device, and every tailnet device with
 * one-click "Copy IP" / "Copy ssh command". The menu itself is TailscalePanel.vala,
 * shared with the Work Mode taskbar.
 */
namespace MSeries.Tailscale {
    public class Indicator : Wingpanel.Indicator {
        private Gtk.Image icon;
        private Panel? panel = null;

        public Indicator () {
            Object (code_name: "mseries-tailscale");
        }

        construct {
            icon = new Gtk.Image.from_icon_name ("mseries-tailscale-symbolic");
            icon.update_property (Gtk.AccessibleProperty.LABEL, "Tailscale", -1);
            // Created up front so its light timer keeps the icon state current.
            panel = new Panel ();
            panel.close_request.connect (() => close ());
            panel.notify["state"].connect (update_icon);
            update_icon ();
            visible = true;
        }

        private void update_icon () {
            // Tailscale's own on/off look: the logo when connected, all-grey dots when not.
            var on = panel.state == State.CONNECTED;
            icon.icon_name = on ? "mseries-tailscale-symbolic" : "mseries-tailscale-offline-symbolic";
            icon.tooltip_markup = "Tailscale\n" + Granite.TOOLTIP_SECONDARY_TEXT_MARKUP.printf (on ? "Connected" : "Not connected");
        }

        public override Gtk.Widget get_display_widget () {
            return icon;
        }

        public override Gtk.Widget? get_widget () {
            return panel;
        }

        public override void opened () {
            panel.refresh.begin ();
        }

        public override void closed () {}
    }
}

public Wingpanel.Indicator? get_indicator (Module module, Wingpanel.ServerType server_type) {
    if (server_type != Wingpanel.ServerType.SESSION) return null;
    return new MSeries.Tailscale.Indicator ();
}
