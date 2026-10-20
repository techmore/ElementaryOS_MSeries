/* SPDX-License-Identifier: GPL-3.0
 * Synthetic GTK interactions on a private test bus; no live history. */
Gtk.Widget? find_label (Gtk.Widget root, string text) {
    if (root is Gtk.Label && ((Gtk.Label) root).label == text) return root;
    for (var child = root.get_first_child (); child != null; child = child.get_next_sibling ()) {
        var found = find_label (child, text);
        if (found != null) return found;
    }
    return null;
}
// Optional fixture-only export. Captures native widget rendering, not the desktop.
void capture (Gtk.Widget button, string name) {
    var directory = Environment.get_variable ("MSERIES_NOTIFICATION_PROBE_EXPORT");
    if (directory == null) return;
    for (var child = button.get_first_child (); child != null; child = child.get_next_sibling ()) {
        if (!(child is Gtk.Popover) || !child.visible) continue;
        var popup = (Gtk.Popover) child;
        var paintable = new Gtk.WidgetPaintable (popup);
        var snapshot = new Gtk.Snapshot ();
        paintable.snapshot (snapshot, popup.get_width (), popup.get_height ());
        var node = snapshot.to_node ();
        assert (node != null);
        var renderer = popup.get_native ().get_renderer ();
        var texture = renderer.render_texture (node, null);
        assert (texture.save_to_png (Path.build_filename (directory, name + ".png")));
    }
}

void capture_bell (Gtk.Button button) {
    var directory = Environment.get_variable ("MSERIES_NOTIFICATION_PROBE_EXPORT");
    if (directory == null) return;
    var paintable = new Gtk.WidgetPaintable (button.child);
    var snapshot = new Gtk.Snapshot ();
    paintable.snapshot (snapshot, button.child.get_width (), button.child.get_height ());
    var node = snapshot.to_node ();
    assert (node != null);
    var texture = button.get_native ().get_renderer ().render_texture (node, null);
    assert (texture.save_to_png (Path.build_filename (directory, "bell.png")));
}

int main () {
    Gtk.init ();
    Gtk.Settings.get_default ().gtk_application_prefer_dark_theme =
        Environment.get_variable ("MSERIES_NOTIFICATION_PROBE_DARK") == "1";
    var window = new Gtk.Window () { default_width = 500, default_height = 120 };
    var widget = new Dock.TaskbarNotifications ();
    window.child = widget;
    window.present ();
    var button = (Gtk.Button) widget.get_first_child ();
    var loop = new MainLoop ();
    int step = 0;
    Timeout.add (500, () => {
        switch (step++) {
        case 0:
            if (Environment.get_variable ("UNAVAILABLE") != null) {
                assert (button.tooltip_text == "Notifications unavailable");
                button.clicked ();
                assert (find_label (button, "Notifications") != null);
                print ("PASS unavailable service retains Notifications title\n");
                loop.quit (); return Source.REMOVE;
            }
            assert (button.tooltip_text.contains ("2 unread"));
            assert (button.tooltip_text.contains ("Do Not Disturb"));
            button.clicked ();
            break;
        case 1:
            capture_bell (button);
            capture (button, "history");
            var reply = find_label (button, "Reply");
            assert (reply != null);
            ((Gtk.Button) reply.get_parent ()).clicked ();
            break;
        case 2:
            var label = find_label (button, "Open");
            assert (label != null);
            ((Gtk.Button) label.get_parent ()).clicked ();
            break;
        case 3:
            var controllers = button.observe_controllers ();
            for (uint i=0; i<controllers.get_n_items (); i++) {
                var controller = controllers.get_item (i);
                if (controller is Gtk.GestureClick && ((Gtk.GestureClick) controller).button == Gdk.BUTTON_SECONDARY)
                    ((Gtk.GestureClick) controller).pressed (1, 2, 2);
            }
            break;
        case 4:
            capture (button, "menu");
            var mark = (Gtk.Button) find_label (button, "Mark all as read").get_parent ();
            var menu = mark.get_parent ();
            var row = mark.get_next_sibling ();
            var toggle = (Gtk.Switch) row.get_last_child ();
            assert (toggle.active && toggle.state);
            toggle.activate ();
            break;
        case 5:
            var mark = (Gtk.Button) find_label (button, "Mark all as read").get_parent ();
            var toggle = (Gtk.Switch) mark.get_next_sibling ().get_last_child ();
            // The fixture rejects the first DND write. The confirmed true
            // value must survive, with the failure visible in the context menu.
            assert (toggle.active && toggle.state);
            var error = find_label (mark.get_parent (), "Could not update notifications");
            assert (error != null && error.visible);
            assert (error.get_parent ().get_parent ().visible);
            capture (button, "menu-error");
            toggle.activate ();
            break;
        case 6:
            var mark = (Gtk.Button) find_label (button, "Mark all as read").get_parent ();
            var toggle = (Gtk.Switch) mark.get_next_sibling ().get_last_child ();
            assert (!toggle.active && !toggle.state);
            assert (find_label (mark.get_parent (), "Could not update notifications") == null);
            mark.clicked ();
            break;
        case 7:
            assert (button.tooltip_text.contains ("0 unread"));
            button.clicked ();
            break;
        case 8:
            assert (find_label (button, "No notifications") != null);
            capture (button, "empty");
            print ("PASS unread, DND failure/confirmation, context error clearing, Open, Reply, local mark-all-read and empty history\n");
            loop.quit (); return Source.REMOVE;
        }
        return Source.CONTINUE;
    });
    loop.run ();
    window.destroy ();
    return 0;
}
