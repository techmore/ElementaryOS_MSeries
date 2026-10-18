/* Headless render probe: loads the real indicator and writes the bar + popover to a PNG.
 * Usage: render-probe OUT.png   (run under Xvfb with a fake HOME; see run-probe.sh) */
void dump (Gtk.Widget widget, int depth) {
    int min, nat;
    widget.measure (Gtk.Orientation.VERTICAL, widget.get_width (), out min, out nat, null, null);
    if (widget is Gtk.ScrolledWindow || widget is Gtk.Stack || widget is Gtk.Viewport || depth < 2) {
        stderr.printf ("%*s%s alloc=%dx%d v-min=%d v-nat=%d\n", depth * 2, "", widget.get_type ().name (),
            widget.get_width (), widget.get_height (), min, nat);
    }
    for (var child = widget.get_first_child (); child != null; child = child.get_next_sibling ()) {
        dump (child, depth + 1);
    }
}

Gtk.Stack? find_pages (Gtk.Widget widget) {
    var stack = widget as Gtk.Stack;
    if (stack != null && stack.get_child_by_name ("quota") != null) {
        return stack;
    }
    for (var child = widget.get_first_child (); child != null; child = child.get_next_sibling ()) {
        var found = find_pages (child);
        if (found != null) {
            return found;
        }
    }
    return null;
}

int main (string[] args) {
    if (args.length < 2) {
        stderr.printf ("usage: render-probe OUT.png [delay-ms]\n");
        return 2;
    }
    Gtk.init ();
    Granite.init ();
    var delay = args.length > 2 ? int.parse (args[2]) : 1500;
    var dialog_scenario = Environment.get_variable ("CB_DIALOG");
    if (dialog_scenario != null) {
        MSeries.AccountDialog dialog;
        if (dialog_scenario == "claude" || dialog_scenario == "opencode") {
            bool claude = dialog_scenario == "claude";
            dialog = new MSeries.AccountDialog.prompt (
                claude ? "Add a Claude account" : "Sign in to OpenCode Go",
                claude ? "Add another Claude Code account to CodexBar." : "Connect your OpenCode Go usage to CodexBar.",
                "mseries-codexbar-%s-symbolic".printf (dialog_scenario), dialog_scenario,
                claude ? "Sign in with browser" : "Continue");
        } else {
            string[] command = dialog_scenario == "codex-wait" ? new string[] { "/bin/sleep", "30" }
                : dialog_scenario == "codex-error" ? new string[] { "/bin/sh", "-c", "echo 'Browser sign-in timed out. Please try again.'; exit 1" }
                : new string[] { "/bin/true" };
            dialog = new MSeries.AccountDialog ("Add a Codex account",
                "Connect another ChatGPT account to CodexBar.",
                "mseries-codexbar-openai-symbolic", command);
        }
        dialog.present ();
        if (dialog_scenario.has_prefix ("codex-")) {
            Timeout.add (100, () => { dialog.response (Gtk.ResponseType.ACCEPT); return Source.REMOVE; });
        }
        var loop = new MainLoop ();
        Timeout.add (delay, () => { capture (dialog, dialog, args[1], loop); return Source.REMOVE; });
        loop.run ();
        dialog.close ();
        return render_failed ? 1 : 0;
    }

    var indicator = new MSeries.CodexBarIndicator ();
    var bar = new Gtk.Box (Gtk.Orientation.HORIZONTAL, 0) { height_request = 28, margin_start = 8, margin_end = 8 };
    bar.append (indicator.get_display_widget ());
    var popover_body = new Gtk.Box (Gtk.Orientation.VERTICAL, 0);
    popover_body.add_css_class ("background");
    popover_body.append (indicator.get_widget ());
    var root = new Gtk.Box (Gtk.Orientation.VERTICAL, 6) { margin_top = 6, margin_bottom = 6, margin_start = 6, margin_end = 6 };
    root.add_css_class ("background");
    root.append (bar);
    root.append (popover_body);
    var window = new Gtk.Window () { child = root, decorated = false };
    window.present ();

    var loop = new MainLoop ();
    Timeout.add (delay, () => {
        var page = Environment.get_variable ("CB_PAGE");
        var pages = find_pages (root);
        if (page != null && pages != null) {
            pages.set_visible_child_name (page);
        }
        // No window manager under Xvfb, so size the window to the content ourselves.
        int min, nat;
        root.measure (Gtk.Orientation.VERTICAL, 360, out min, out nat, null, null);
        window.set_default_size (360, nat);
        Timeout.add (800, () => {
            capture (root, window, args[1], loop);
            return Source.REMOVE;
        });
        if (Environment.get_variable ("CB_STABILITY") != null) {
            var tagged = first_card (root);
            if (tagged != null) {
                tagged.set_data<int> ("probe-seen", 1);
            }
            // Two or more five-second polls of an unchanged snapshot must not rebuild the page.
            Timeout.add (11000, () => {
                var current = first_card (root);
                var same = tagged != null && current != null && current.get_data<int> ("probe-seen") == 1;
                stdout.printf ("stability: %s\n", same ? "stable" : "REBUILT");
                if (!same) {
                    render_failed = true;
                }
                return Source.REMOVE;
            });
        }
        return Source.REMOVE;
    });
    loop.run ();
    return render_failed ? 1 : 0;
}

bool render_failed = false;

/* The first quota card; a rebuilt popover replaces it (visible as flicker), losing any tag set on it. */
Gtk.Widget? first_card (Gtk.Widget root) {
    var pages = find_pages (root);
    var quota = pages != null ? pages.get_child_by_name ("quota") : null;
    return quota != null ? quota.get_first_child () : null;
}

void capture (Gtk.Widget root, Gtk.Window window, string path, MainLoop loop) {
    {
        var paintable = new Gtk.WidgetPaintable (root);
        var snapshot = new Gtk.Snapshot ();
        paintable.snapshot (snapshot, root.get_width (), root.get_height ());
        var node = snapshot.to_node ();
        var renderer = window.get_native ().get_renderer ();
        if (node == null || renderer == null) {
            stderr.printf ("nothing to render\n");
            render_failed = true;
        } else {
            var texture = renderer.render_texture (node, null);
            texture.save_to_png (path);
        }
        if (Environment.get_variable ("CB_DEBUG") != null) {
            dump (root, 0);
        }
        if (Environment.get_variable ("CB_STABILITY") == null) {
            loop.quit ();
        } else {
            Timeout.add (11500, () => { loop.quit (); return Source.REMOVE; });
        }
    }
}
