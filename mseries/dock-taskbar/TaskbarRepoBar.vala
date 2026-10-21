/* SPDX-License-Identifier: GPL-3.0
 * RepoBar native GitHub menu, anchored beside CodexBar in the Windows taskbar status area. */
public class Dock.TaskbarRepoBar : Gtk.Box {
    private MSeries.RepoBarIndicator indicator;
    private Gtk.Popover popup;
    private uint open_timer = 0;
    private uint close_timer = 0;
    private bool pinned = false;

    construct {
        orientation = Gtk.Orientation.VERTICAL;
        var button = new Gtk.Button () { valign = Gtk.Align.CENTER };
        button.add_css_class ("flat");
        button.add_css_class ("taskbar-repobar-button");
        button.update_property (Gtk.AccessibleProperty.LABEL, "RepoBar", -1);
        indicator = new MSeries.RepoBarIndicator ();
        var readout = indicator.get_display_widget ();
        enlarge_marks (readout);
        button.child = readout;
        append (button);
        valign = Gtk.Align.CENTER;
        popup = new Gtk.Popover () {
            position = Gtk.PositionType.TOP,
            autohide = false,
            has_arrow = false
        };
        popup.set_offset (0, -1);
        popup.add_css_class (Granite.STYLE_CLASS_MENU);
        popup.add_css_class ("taskbar-repobar-popup");
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
        if (popup.child == null) {
            popup.child = indicator.get_widget ();
            popup.child.width_request = 400;
            expand_scroll_area (popup.child);
        }
        if (popup.visible && popup.autohide != interactive) popup.popdown ();
        pinned = interactive;
        // Hover opens without a grab or keyboard focus change. Click pins the
        // menu and enables the usual outside-click/Escape dismissal.
        popup.autohide = interactive;
        indicator.opened ();
        popup.popup ();
    }
    /* The panel readout is sized for Wingpanel; the taskbar is taller, so its marks scale up (CodexBar's is 28 px). */
    private void enlarge_marks (Gtk.Widget widget) {
        if (widget is Gtk.Image) {
            var image = (Gtk.Image) widget;
            // The GitHub mark (16) matches CodexBar's 28 px icon; the small count marks stay compact so two rows fit.
            image.pixel_size = image.pixel_size >= 16 ? (int) Math.round (image.pixel_size * 1.75) : (int) Math.round (image.pixel_size * 1.6);
        }
        for (var child = widget.get_first_child (); child != null; child = child.get_next_sibling ()) {
            enlarge_marks (child);
        }
    }
    private void expand_scroll_area (Gtk.Widget widget) {
        if (widget is Gtk.ScrolledWindow) {
            ((Gtk.ScrolledWindow) widget).max_content_height = 480;
        }
        for (var child = widget.get_first_child (); child != null; child = child.get_next_sibling ()) {
            expand_scroll_area (child);
        }
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
