/* SPDX-License-Identifier: GPL-3.0
 * AirDrop controls in the Windows taskbar status area. */
public class Dock.TaskbarAirDrop : Gtk.Button {
    private Gtk.Popover popup;
    private MSeries.AirDropPanel? panel = null;

    construct {
        valign = Gtk.Align.CENTER;
        tooltip_text = _("AirDrop");
        update_property (Gtk.AccessibleProperty.LABEL, _("AirDrop"), -1);
        child = new Gtk.Image.from_icon_name ("mseries-airdrop-symbolic");

        popup = new Gtk.Popover () {
            position = Gtk.PositionType.TOP,
            autohide = true,
            has_arrow = false
        };
        popup.set_offset (0, -1);
        popup.add_css_class ("taskbar-airdrop-popup");
        popup.set_parent (this);

        clicked.connect (() => {
            if (popup.visible) {
                popup.popdown ();
                return;
            }
            if (panel == null) {
                panel = new MSeries.AirDropPanel ();
                panel.width_request = 300;
                popup.child = panel;
            }
            popup.popup ();
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

    public override void dispose () {
        if (popup != null && popup.get_parent () != null) popup.unparent ();
        base.dispose ();
    }
}
