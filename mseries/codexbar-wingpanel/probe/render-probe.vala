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

Gtk.Label? find_label (Gtk.Widget widget, string text) {
    var label = widget as Gtk.Label;
    if (label != null && label.get_text ().contains (text)) return label;
    for (var child = widget.get_first_child (); child != null; child = child.get_next_sibling ()) {
        var found = find_label (child, text);
        if (found != null) return found;
    }
    return null;
}

void assert_quota_bar_colors (Gtk.Widget widget) {
    var bar = widget as Gtk.ProgressBar;
    if (bar != null && bar.sensitive) {
        var level = MSeries.Presentation.visual_level (bar.fraction * 100);
        assert (bar.has_css_class (level == MSeries.QuotaLevel.OK ? "level-ok" :
            level == MSeries.QuotaLevel.LOW ? "level-low" : "level-critical"));
    }
    for (var child = widget.get_first_child (); child != null; child = child.get_next_sibling ())
        assert_quota_bar_colors (child);
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
    if (Environment.get_variable ("CB_HIDE_PANEL") == null) root.append (bar);
    root.append (popover_body);
    var window = new Gtk.Window () { child = root, decorated = false };
    bool compact_probe = Environment.get_variable ("CB_ASSERT_COMPACT") != null;
    if (!compact_probe) window.present ();

    var loop = new MainLoop ();
    Timeout.add (delay, () => {
        if (Environment.get_variable ("CB_ASSERT_LOCAL") != null) {
            var text = local_label_text (bar);
            assert (!text.contains ("local"));
            assert (text.contains ("42.0M tok"));
            assert (text.contains ("31.2M tok"));
            assert (text.contains ("121M tok"));
            string[] counts = { "42.0M tok", "31.2M tok", "121M tok" };
            string[] quotas = { "72%", "80%", "83%" };
            for (int i = 0; i < counts.length; i++) {
                var tokens = find_label (bar, counts[i]);
                var quota = find_label (bar, quotas[i]);
                assert (tokens != null && quota != null);
                Graphene.Rect token_bounds, quota_bounds;
                assert (tokens.compute_bounds (bar, out token_bounds));
                assert (quota.compute_bounds (bar, out quota_bounds));
                if (i < 2) {
                    assert (token_bounds.origin.y < quota_bounds.origin.y);
                    var weekly = find_label (bar, i == 0 ? "7D 64%" : "7D 55%");
                    assert (weekly != null && weekly.get_parent () == tokens.get_parent ());
                    bool has_reset = false;
                    for (var child = tokens.get_parent ().get_first_child (); child != null; child = child.get_next_sibling ()) {
                        if (child.has_css_class ("seg-reset")) has_reset = true;
                    }
                    assert (has_reset);
                } else assert (token_bounds.origin.y > quota_bounds.origin.y);
            }
            int min, nat;
            bar.measure (Gtk.Orientation.VERTICAL, -1, out min, out nat, null, null);
            assert (nat <= 32); // Provider totals and alternate accounts still fit two rows.
        }
        if (Environment.get_variable ("CB_ASSERT_HIDDEN_TOKENS") != null) {
            var text = local_label_text (bar);
            assert (!text.contains ("tok"));
            assert (text.contains ("7D 64%") && text.contains ("7D 55%"));
            var menu_text = local_label_text (popover_body);
            assert (menu_text.contains ("42.0M tokens") && menu_text.contains ("31.2M tokens") && menu_text.contains ("121M tokens"));
        }
        if (Environment.get_variable ("CB_ASSERT_DOTS") != null) {
            var text = local_label_text (bar);
            assert (text.contains ("7D ●") && text.contains ("5H ●"));
            assert (!text.contains ("7D 64%") && !text.contains ("5H 72%"));
            assert (!text.contains ("7D 62%") && !text.contains ("7D 72%"));
            assert (text.contains ("5H ● 5%") && text.contains ("5H ● 0%"));
            var weekly = find_label (bar, "7D ●");
            assert (weekly != null && weekly.tooltip_text.contains ("% remaining") && weekly.tooltip_text.contains ("Resets in"));
            var primary = find_label (bar, "5H ●");
            assert (primary != null && primary.tooltip_text.contains ("Resets in"));
            assert (primary.get_parent () == weekly.get_parent ());
            var alternate = find_label (bar, "5H ● 5%");
            assert (alternate != null && alternate.get_parent () != primary.get_parent ());
            assert (alternate.label.contains ("weight=\"bold\"") && alternate.label.contains ("foreground="));
            Graphene.Rect primary_bounds, alternate_bounds;
            assert (primary.compute_bounds (bar, out primary_bounds));
            assert (alternate.compute_bounds (bar, out alternate_bounds));
            assert (primary_bounds.origin.y < alternate_bounds.origin.y);
            assert (!text.contains ("↻") && !text.contains ("3d11h") && !text.contains ("3h09m"));
            int minimum, natural;
            bar.measure (Gtk.Orientation.VERTICAL, -1, out minimum, out natural, null, null);
            assert (natural <= 32);
        }
        if (Environment.get_variable ("CB_ASSERT_GROK") != null) {
            // Bar: Grok follows Codex and Claude, token-first with its weekly credits beside the count.
            var text = local_label_text (bar);
            assert (text.contains ("763K tok") && text.contains ("7D 76%"));
            var grok_tokens = find_label (bar, "763K tok");
            var claude_tokens = find_label (bar, "31.2M tok");
            Graphene.Rect grok_bounds, claude_bounds;
            assert (grok_tokens.compute_bounds (bar, out grok_bounds));
            assert (claude_tokens.compute_bounds (bar, out claude_bounds));
            assert (grok_bounds.origin.x > claude_bounds.origin.x);
            assert (find_label (bar, "7D 76%").get_parent () == grok_tokens.get_parent ());
            // Menu: tier, product shares and reset credits; malformed sections are skipped.
            var menu = local_label_text (popover_body);
            assert (menu.contains ("SuperGrok") && menu.contains ("me@grok.example"));
            // Its only window is weekly and already sits beside the token count: no repeated lower row.
            assert (text.index_of ("7D 76%") == text.last_index_of ("7D 76%"));
            assert (menu.contains ("Usage breakdown · Grok Build 18% · Grok Chat 6%"));
            assert (menu.contains ("Limit Reset Credits · Available 1 available"));
            assert (!menu.contains ("Malformed") && !menu.contains ("not an object"));
            assert (menu.contains ("763K tokens"));
        }
        if (Environment.get_variable ("CB_ASSERT_GROK_FREE") != null) {
            var menu = local_label_text (popover_body);
            assert (menu.contains ("Signed in as me@grok.example on the Free plan"));
            assert (!menu.contains ("run grok login"));
            assert (find_button (popover_body, "Sign in…") == null);
        }
        if (Environment.get_variable ("CB_ASSERT_GROK_SIGNIN") != null) {
            var menu = local_label_text (popover_body);
            assert (menu.contains ("If you are signed out, run grok login"));
            var sign_in = find_button (popover_body, "Sign in…");
            assert (sign_in != null);
            assert (find_button (popover_body, "Open Settings…") == null);
            sign_in.clicked ();
            var log = GLib.Path.build_filename (Environment.get_home_dir (), "terminal.log");
            // Checked before the 1 s capture ends the probe; the fake launcher only appends one line.
            Timeout.add (500, () => {
                string contents;
                try {
                    FileUtils.get_contents (log, out contents);
                } catch (Error e) {
                    contents = "";
                }
                var expected = GLib.Path.build_filename (Environment.get_home_dir (), ".grok/bin/grok") + " login";
                if (!contents.contains (expected)) {
                    stderr.printf ("grok login was not launched; terminal log: %s\n", contents);
                    render_failed = true;
                }
                return Source.REMOVE;
            });
        }
        assert_quota_bar_colors (popover_body);
        var page = Environment.get_variable ("CB_PAGE");
        var pages = find_pages (root);
        if (page != null && pages != null) {
            pages.set_visible_child_name (page);
        }
        // No window manager under Xvfb, so size the window to the content ourselves.
        int min, nat;
        int target_width = compact_probe ? 280 : 360;
        root.measure (Gtk.Orientation.VERTICAL, target_width, out min, out nat, null, null);
        if (compact_probe) {
            // Size the first realization after fixture data has populated the UI.
            window.set_default_size (target_width, nat);
            window.present ();
        } else {
            // Preserve the original timing for panel token-layout probes.
            window.set_default_size (target_width, nat);
        }
        Timeout.add (800, () => {
            if (Environment.get_variable ("CB_SCROLL") == "end") {
                var scroll = find_scroll (root);
                if (scroll != null) {
                    var adjustment = scroll.get_vadjustment ();
                    adjustment.value = adjustment.upper - adjustment.page_size;
                }
            }
            Timeout.add (200, () => { capture (root, window, args[1], loop); return Source.REMOVE; });
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
    if (Environment.get_variable ("CB_ASSERT_COMPACT") != null) {
        int min_width, natural_width;
        root.measure (Gtk.Orientation.HORIZONTAL, -1, out min_width, out natural_width, null, null);
        assert (natural_width <= 280);
        assert (root.get_width () <= 300);
    }

    {
        var requested_scale = Environment.get_variable ("GDK_SCALE");
        assert (requested_scale == null || window.get_scale_factor () == int.parse (requested_scale));
        try {
            FileUtils.set_contents (path + ".json",
                "{\"gdkScale\":%d,\"logicalWidth\":%d,\"logicalHeight\":%d}\n".printf (
                    window.get_scale_factor (), root.get_width (), root.get_height ()));
        } catch (Error e) { error ("%s", e.message); }
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

Gtk.ScrolledWindow? find_scroll (Gtk.Widget root) {
    if (root is Gtk.ScrolledWindow) return (Gtk.ScrolledWindow) root;
    for (var child = root.get_first_child (); child != null; child = child.get_next_sibling ()) {
        var found = find_scroll (child);
        if (found != null) return found;
    }
    return null;
}

Gtk.Button? find_button (Gtk.Widget widget, string text) {
    var button = widget as Gtk.Button;
    if (button != null && button.label == text) return button;
    for (var child = widget.get_first_child (); child != null; child = child.get_next_sibling ()) {
        var found = find_button (child, text);
        if (found != null) return found;
    }
    return null;
}

string local_label_text (Gtk.Widget widget) {
    var text = (widget is Gtk.Label) ? ((Gtk.Label) widget).get_text () : "";
    for (var child = widget.get_first_child (); child != null; child = child.get_next_sibling ())
        text += " " + local_label_text (child);
    return text;
}
