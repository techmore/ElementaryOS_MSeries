/* SPDX-License-Identifier: GPL-3.0
 * Tailscale in the Windows taskbar status area. Work Mode hides the top panel, so this
 * opens the same menu (mseries/tailscale-wingpanel/TailscalePanel.vala) above the taskbar. */
public class Dock.TaskbarTailscale : Gtk.Button {
    private Gtk.Popover popup;
    private Gtk.Image icon;
    private MSeries.Tailscale.Panel panel;

    construct {
        valign = Gtk.Align.CENTER;
        update_property (Gtk.AccessibleProperty.LABEL, "Tailscale", -1);
        icon = new Gtk.Image.from_icon_name ("mseries-tailscale-symbolic");
        child = icon;

        // Built now so its light timer switches the icon when disconnected.
        panel = new MSeries.Tailscale.Panel ();
        panel.notify["state"].connect (update_icon);
        update_icon ();

        popup = new Gtk.Popover () {
            position = Gtk.PositionType.TOP,
            autohide = true,
            has_arrow = false,
            child = panel
        };
        popup.set_offset (0, -1);
        popup.add_css_class ("taskbar-tailscale-popup");
        popup.set_parent (this);
        panel.close_request.connect (() => popup.popdown ());

        clicked.connect (() => {
            if (popup.visible) popup.popdown ();
            else popup.popup ();
        });

        var keys = new Gtk.EventControllerKey ();
        keys.key_pressed.connect ((key) => {
            if (key != Gdk.Key.Escape) return false;
            popup.popdown ();
            return true;
        });
        ((Gtk.Widget) popup).add_controller (keys);
        unmap.connect (() => popup.popdown ());
    }

    private void update_icon () {
        var on = panel.state == MSeries.Tailscale.State.CONNECTED;
        icon.icon_name = on ? "mseries-tailscale-symbolic" : "mseries-tailscale-offline-symbolic";
        tooltip_text = on ? "Tailscale: connected" : "Tailscale: not connected";
    }

    public override void dispose () {
        if (popup != null && popup.get_parent () != null) popup.unparent ();
        base.dispose ();
    }
}
