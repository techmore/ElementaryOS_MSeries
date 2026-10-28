/* SPDX-License-Identifier: GPL-3.0
 * Taskbar clock → datetime indicator popover. Args: MODE (light|dark|missing) [SCREENSHOT.png] [PAGE] */
Gtk.Stack? find_stack (Gtk.Widget widget) {
    if (widget is Gtk.Stack && ((Gtk.Stack) widget).get_child_by_name ("tasks") != null) {
        return (Gtk.Stack) widget;
    }
    for (var child = widget.get_first_child (); child != null; child = child.get_next_sibling ()) {
        var found = find_stack (child);
        if (found != null) {
            return found;
        }
    }
    return null;
}

int main (string[] args) {
    Gtk.init ();
    Granite.init ();
    var mode = args.length > 1 ? args[1] : "light";
    var shot = args.length > 2 ? args[2] : null;
    var page = args.length > 3 ? args[3] : null;
    var gtk_settings = Gtk.Settings.get_default ();
    gtk_settings.gtk_theme_name = "io.elementary.stylesheet.blueberry";
    gtk_settings.gtk_icon_theme_name = "elementary";
    gtk_settings.gtk_application_prefer_dark_theme = mode == "dark";
    if (mode == "missing") {
        Environment.set_variable ("MSERIES_DATETIME_INDICATOR", "/nonexistent/libdatetime.so", true);
    }

    var window = new Gtk.Window () { default_width = 1280, default_height = 860, decorated = false };
    var clock = new Gtk.Button.with_label (new DateTime.now_local ().format ("%l:%M %p\n%x").strip ()) {
        halign = Gtk.Align.END, valign = Gtk.Align.END, margin_end = 8, margin_bottom = 6
    };
    clock.add_css_class ("taskbar-clock");
    var bar = new Gtk.Box (Gtk.Orientation.HORIZONTAL, 0) { valign = Gtk.Align.END, height_request = 52 };
    bar.add_css_class ("toolbar");
    clock.hexpand = true;
    bar.append (clock);
    var root = new Gtk.Box (Gtk.Orientation.VERTICAL, 0);
    root.append (new Gtk.Box (Gtk.Orientation.VERTICAL, 0) { vexpand = true });
    root.append (bar);
    window.child = root;
    var calendar = new Dock.TaskbarCalendar (clock);
    var loop = new MainLoop ();
    int status = 1;
    window.present ();

    Timeout.add (500, () => {
        if (mode == "missing") {
            status = calendar.toggle () ? 1 : 0;
            stdout.printf (status == 0 ? "PASS missing indicator falls back to the Calendar app\n" : "FAIL\n");
            loop.quit ();
            return Source.REMOVE;
        }
        if (!calendar.toggle () || !calendar.is_open) {
            stdout.printf ("FAIL datetime indicator did not open\n");
            loop.quit ();
            return Source.REMOVE;
        }
        if (page != null) {
            var stack = find_stack (clock.get_last_child ());
            if (stack == null) {
                stdout.printf ("FAIL no agenda stack in the popover\n");
                loop.quit ();
                return Source.REMOVE;
            }
            stack.visible_child_name = page;
        }
        // Let EDS fill Events and Tasks before capturing.
        Timeout.add_seconds (shot != null ? 4 : 1, () => {
            if (shot != null) {
                try {
                    Process.spawn_command_line_sync ("import -window root " + Shell.quote (shot));
                } catch (Error e) {
                    warning ("%s", e.message);
                }
            }
            calendar.toggle ();
            Timeout.add (300, () => {
                status = calendar.is_open ? 1 : 0;
                stdout.printf (status == 0 ? "PASS clock opens and closes the datetime indicator (%s)\n" : "FAIL popover stayed open\n", mode);
                loop.quit ();
                return Source.REMOVE;
            });
            return Source.REMOVE;
        });
        return Source.REMOVE;
    });
    loop.run ();
    return status;
}
