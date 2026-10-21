/* SPDX-License-Identifier: GPL-3.0
 * Remote Desktop status anchor for the Windows Work Mode taskbar. Embeds the same
 * Wingpanel indicator class the native session uses, so the consent indicator and
 * its menu are identical in both modes. Invisible until remote access is turned on. */
public class Dock.TaskbarRemote : Gtk.Box {
    private MSeries.Remote.Indicator indicator;
    private Gtk.Popover popup;
    private uint open_timer = 0;
    private uint close_timer = 0;
    private bool pinned = false;

    construct {
        orientation = Gtk.Orientation.VERTICAL;
        valign = Gtk.Align.CENTER;
        var button = new Gtk.Button () { valign = Gtk.Align.CENTER };
        button.add_css_class ("flat");
        button.add_css_class ("taskbar-remote-button");
        button.update_property (Gtk.AccessibleProperty.LABEL, _("Remote Desktop"), -1);
        indicator = new MSeries.Remote.Indicator ();
        var readout = indicator.get_display_widget ();
        if (readout is Gtk.Image) ((Gtk.Image) readout).pixel_size = 24;
        button.child = readout;
        append (button);
        // Nothing to show until sharing is on; never reserve taskbar space.
        indicator.bind_property ("visible", this, "visible", BindingFlags.SYNC_CREATE);

        popup = new Gtk.Popover () {
            position = Gtk.PositionType.TOP,
            autohide = false,
            has_arrow = false
        };
        popup.set_offset (0, -1);
        popup.add_css_class (Granite.STYLE_CLASS_MENU);
        popup.set_parent (button);
        indicator.close.connect (() => { popup.popdown (); });

        var motion = new Gtk.EventControllerMotion ();
        motion.enter.connect (() => {
            cancel_close ();
            if (open_timer == 0 && !popup.visible) {
                open_timer = Timeout.add (250, () => {
                    open_timer = 0;
                    show_popup (false);
                    return Source.REMOVE;
                });
            }
        });
        motion.leave.connect (() => {
            cancel_open ();
            schedule_close ();
        });
        button.add_controller (motion);
        var popup_motion = new Gtk.EventControllerMotion ();
        popup_motion.enter.connect (cancel_close);
        popup_motion.leave.connect (schedule_close);
        ((Gtk.Widget) popup).add_controller (popup_motion);
        button.clicked.connect (() => {
            cancel_open ();
            if (popup.visible && pinned) popup.popdown ();
            else show_popup (true);
        });
        popup.closed.connect (() => {
            pinned = false;
            cancel_close ();
            indicator.closed ();
        });
        var keys = new Gtk.EventControllerKey ();
        keys.key_pressed.connect ((key) => {
            if (key != Gdk.Key.Escape) return false;
            popup.popdown ();
            return true;
        });
        ((Gtk.Widget) popup).add_controller (keys);
        unmap.connect (() => { cancel_open (); cancel_close (); popup.popdown (); });
    }

    private void show_popup (bool interactive) {
        cancel_close ();
        if (popup.child == null) popup.child = indicator.get_widget ();
        if (popup.visible && popup.autohide != interactive) popup.popdown ();
        pinned = interactive;
        // Hover opens without a grab or keyboard focus change; a click pins it.
        popup.autohide = interactive;
        indicator.opened ();
        popup.popup ();
    }

    private void cancel_open () {
        if (open_timer != 0) { Source.remove (open_timer); open_timer = 0; }
    }

    private void cancel_close () {
        if (close_timer != 0) { Source.remove (close_timer); close_timer = 0; }
    }

    private void schedule_close () {
        cancel_close ();
        if (pinned) return;
        close_timer = Timeout.add (450, () => {
            close_timer = 0;
            popup.popdown ();
            return Source.REMOVE;
        });
    }

    public override void dispose () {
        cancel_open ();
        cancel_close ();
        if (popup != null && popup.get_parent () != null) popup.unparent ();
        base.dispose ();
    }
}
