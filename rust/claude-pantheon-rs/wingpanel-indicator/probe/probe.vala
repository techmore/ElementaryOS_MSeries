/*
 * Headless probe: builds the indicator from a status.json fixture at a fixed time, checks the texts it
 * shows, and writes a PNG of the popover and the panel widget when PROBE_SHOT is set. Run under Xvfb:
 *
 *   xvfb-run -a env PROBE_SHOT=docs/screenshot-indicator.png build/probe probe/status-fixture.json
 */

static void collect (Gtk.Widget w, Gee.ArrayList<string> acc) {
    if (w is Gtk.Label) acc.add (((Gtk.Label) w).label);
    Gtk.Widget? c = w.get_first_child ();
    while (c != null) {
        collect (c, acc);
        c = c.get_next_sibling ();
    }
}

static void collect_last_known_buttons (Gtk.Widget w, Gee.ArrayList<bool> enabled) {
    if (w is Gtk.Button) {
        var button = (Gtk.Button) w;
        var child = button.child;
        if (child is Gtk.Label && ((Gtk.Label) child).label.has_prefix ("Last known ·")) {
            enabled.add (button.sensitive);
        }
    }
    Gtk.Widget? c = w.get_first_child ();
    while (c != null) {
        collect_last_known_buttons (c, enabled);
        c = c.get_next_sibling ();
    }
}

static void pump (int ms) {
    var until = get_monotonic_time () + ms * 1000;
    while (get_monotonic_time () < until) {
        while (MainContext.default ().iteration (false)) { }
        Thread.usleep (5000);
    }
}

int main (string[] args) {
    Gtk.init ();
    Granite.init ();
    var fixture = args.length > 1 ? args[1] : "probe/status-fixture.json";
    bool unknown_selection = args.length > 2 && args[2] == "unknown-selection";
    var indicator = new ClaudePantheon.Indicator (fixture);
    var panel = indicator.get_display_widget ();
    var popover = indicator.get_widget ();
    // Render the fixture at a fixed instant so the countdowns are deterministic.
    var now = new DateTime.from_iso8601 ("2026-10-22T00:36:00Z", new TimeZone.utc ());
    var feed = ClaudePantheon.Feed.load (fixture);
    indicator.render (feed, now);

    var texts = new Gee.ArrayList<string> ();
    collect (popover, texts);
    collect (panel, texts);
    if (panel.tooltip_text != null) texts.add (panel.tooltip_text);
    if (unknown_selection) {
        if (feed.windows.size != 0) {
            stderr.printf ("FAIL: unknown provider selection exposed %d account windows\n", feed.windows.size);
            return 1;
        }
        foreach (var hidden in new string[] { "Codex", "Claude", "Grok" }) {
            foreach (var text in texts) {
                if (text.contains (hidden)) {
                    stderr.printf ("FAIL: unknown provider selection leaked '%s' in %s\n", hidden, string.joinv (" | ", texts.to_array ()));
                    return 1;
                }
            }
        }
        bool asks_to_select = false;
        foreach (var text in texts) if (text.contains ("Select a provider in chat")) asks_to_select = true;
        if (!asks_to_select) {
            stderr.printf ("FAIL: unknown provider selection should direct the user to chat in %s\n", string.joinv (" | ", texts.to_array ()));
            return 1;
        }
        stdout.printf ("PASS: unknown provider selection hides all account usage\n");
        return 0;
    }
    bool live = feed.connected && !feed.stale;
    string[] expect = live
        ? new string[] { "Codex session 59%", "resets in 1 h 24 min", "Codex · Weekly", "needs you", "2", "permission prompt" }
        : new string[] { "Last known", "Offline", "Last sync showed 2 active item(s)" };
    foreach (var e in expect) {
        bool found = false;
        foreach (var t in texts) if (t.contains (e)) found = true;
        if (!found) {
            stderr.printf ("FAIL: expected '%s' in %s\n", e, string.joinv (" | ", texts.to_array ()));
            return 1;
        }
    }
    foreach (var hidden in new string[] { "Claude session", "Grok · Weekly", "next task" }) {
        foreach (var t in texts) {
            if (t.contains (hidden)) {
                stderr.printf ("FAIL: selected-provider panel leaked '%s' in %s\n", hidden, string.joinv (" | ", texts.to_array ()));
                return 1;
            }
        }
    }
    if (!live) {
        foreach (var hidden in new string[] { "needs you", "permission prompt", "waiting" }) {
            foreach (var t in texts) {
                if (t.contains (hidden)) {
                    stderr.printf ("FAIL: offline panel presented stale '%s' as live in %s\n", hidden, string.joinv (" | ", texts.to_array ()));
                    return 1;
                }
            }
        }
        var stale_actions = new Gee.ArrayList<bool> ();
        collect_last_known_buttons (popover, stale_actions);
        if (stale_actions.size != 2) {
            stderr.printf ("FAIL: expected two stale activity rows, found %d\n", stale_actions.size);
            return 1;
        }
        foreach (bool enabled in stale_actions) {
            if (enabled) {
                stderr.printf ("FAIL: stale activity row is still actionable\n");
                return 1;
            }
        }
    }
    if (live) {
        // A missing GApplication bus owner means the last connected snapshot may
        // be left behind by a crash before the client's shutdown callback runs.
        indicator.render (feed, now, false);
        var crashed_texts = new Gee.ArrayList<string> ();
        collect (popover, crashed_texts);
        collect (panel, crashed_texts);
        foreach (var expected in new string[] { "Last known", "Offline", "Last known · Fix flaky render test", "Last known · Release pipeline" }) {
            bool found = false;
            foreach (var t in crashed_texts) if (t.contains (expected)) found = true;
            if (!found) {
                stderr.printf ("FAIL: crashed client should show '%s' in %s\n", expected, string.joinv (" | ", crashed_texts.to_array ()));
                return 1;
            }
        }
        foreach (var hidden in new string[] { "needs you", "permission prompt", "waiting" }) {
            foreach (var t in crashed_texts) {
                if (t.contains (hidden)) {
                    stderr.printf ("FAIL: crashed client presented '%s' as live in %s\n", hidden, string.joinv (" | ", crashed_texts.to_array ()));
                    return 1;
                }
            }
        }
        var crashed_actions = new Gee.ArrayList<bool> ();
        collect_last_known_buttons (popover, crashed_actions);
        if (crashed_actions.size != 2) {
            stderr.printf ("FAIL: expected two cached activity rows after client exit, found %d\n", crashed_actions.size);
            return 1;
        }
        foreach (bool enabled in crashed_actions) {
            if (enabled) {
                stderr.printf ("FAIL: crashed-client activity row is still actionable\n");
                return 1;
            }
        }
        indicator.render (feed, now, true);
    }
    var shot = Environment.get_variable ("PROBE_SHOT");
    if (shot != null) {
        var window = new Gtk.Window () { default_width = 360, default_height = 320 };
        var column = new Gtk.Box (Gtk.Orientation.VERTICAL, 12);
        var panel_row = new Gtk.Box (Gtk.Orientation.HORIZONTAL, 0) { halign = Gtk.Align.END, margin_end = 12, margin_top = 6 };
        panel_row.append (panel);
        column.append (panel_row);
        column.append (popover);
        window.child = column;
        window.present ();
        pump (300);
        var paintable = new Gtk.WidgetPaintable (window);
        var snapshot = new Gtk.Snapshot ();
        paintable.snapshot (snapshot, window.get_width (), window.get_height ());
        var node = snapshot.to_node ();
        if (node == null) {
            stderr.printf ("FAIL: nothing painted\n");
            return 1;
        }
        var texture = window.get_native ().get_renderer ().render_texture (node, null);
        texture.save_to_png (shot);
        stdout.printf ("wrote %s\n", shot);
        window.destroy ();
    }
    stdout.printf ("PASS: indicator probe (%d labels)\n", texts.size);
    return 0;
}
