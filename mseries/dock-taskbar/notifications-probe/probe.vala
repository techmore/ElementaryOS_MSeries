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
int main () {
    Gtk.init ();
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
            var reply = find_label (button, "Reply");
            assert (reply != null);
            ((Gtk.Button) reply.get_parent ()).clicked ();
            break;
        case 2:
            var label = find_label (button, "Fixture");
            assert (label != null);
            ((Gtk.Button) label.get_parent ().get_parent ()).clicked ();
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
            print ("PASS unread, DND failure/confirmation, context error clearing, Open, Reply, local mark-all-read and empty history\n");
            loop.quit (); return Source.REMOVE;
        }
        return Source.CONTINUE;
    });
    loop.run ();
    window.destroy ();
    return 0;
}
