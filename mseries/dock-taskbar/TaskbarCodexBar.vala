/* SPDX-License-Identifier: GPL-3.0
 * Native T3 provider/account monitor in the Dock's status area. */
public class Dock.TaskbarCodexBar : Gtk.Box {
    private TaskbarT3RPopover? indicator;
    private Gtk.Button button;
    private Gtk.Popover popup;
    private uint open_timer = 0;
    private uint close_timer = 0;
    private bool pinned = false;

    construct {
        orientation = Gtk.Orientation.VERTICAL;
        button = new Gtk.Button () { valign = Gtk.Align.CENTER };
        button.add_css_class ("flat");
        button.add_css_class ("taskbar-codexbar-button");
        button.update_property (Gtk.AccessibleProperty.LABEL, "T3 provider usage and accounts", -1);
        var image = new Gtk.Image.from_icon_name ("io.github.techmore.ClaudePantheonRs");
        image.pixel_size = 28;
        button.child = image;
        append (button);
        valign = Gtk.Align.CENTER;
        popup = new Gtk.Popover () {
            position = Gtk.PositionType.TOP,
            autohide = false,
            has_arrow = false
        };
        popup.set_offset (0, -1);
        popup.add_css_class (Granite.STYLE_CLASS_MENU);
        popup.add_css_class ("taskbar-codexbar-popup");
        popup.set_parent (button);
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
        if (indicator == null) {
            var desktop = new GLib.DesktopAppInfo ("io.github.techmore.ClaudePantheonRs.desktop");
            if (desktop == null) {
                popup.child = new Gtk.Label ("Install the native T3 client to read provider usage.") { wrap = true };
            } else {
                indicator = new TaskbarT3RPopover (button, desktop, true);
                indicator.dismiss_requested.connect (() => popup.popdown ());
                popup.child = indicator.get_widget ();
            }
        }
        if (popup.visible && popup.autohide != interactive) popup.popdown ();
        pinned = interactive;
        // Hover opens without a grab or keyboard focus change. Click pins the
        // menu and enables the usual outside-click/Escape dismissal.
        popup.autohide = interactive;
        if (indicator != null) indicator.opened ();
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
