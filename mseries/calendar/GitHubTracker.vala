/* Copyright 2026 M-Series contributors. SPDX-License-Identifier: GPL-3.0-or-later */
public class DateTime.GitHubTracker : Gtk.Box {
    public signal void link_opened ();
    private Gtk.Box cards;
    private Gtk.Label status;
    private Gtk.Button refresh_button;
    private bool busy = false;
    private uint timer = 0;

    public GitHubTracker () {
        Object (orientation: Gtk.Orientation.VERTICAL, spacing: 6, name: "github-tracker",
            margin_start: 6, margin_end: 6, margin_bottom: 6);
        var header = new Gtk.Box (Gtk.Orientation.HORIZONTAL, 6);
        status = label (_("Deployment outcomes · read-only"));
        status.name = "github-status";
        status.hexpand = true;
        header.append (status);
        refresh_button = new Gtk.Button.from_icon_name ("view-refresh-symbolic") {
            name = "github-refresh", tooltip_text = _("Refresh GitHub progress and CI")
        };
        refresh_button.update_property (Gtk.AccessibleProperty.LABEL, _("Refresh GitHub progress and CI"), -1);
        refresh_button.clicked.connect (() => refresh.begin ());
        header.append (refresh_button);
        append (header);
        cards = new Gtk.Box (Gtk.Orientation.VERTICAL, 9);
        append (new Gtk.ScrolledWindow () {
            child = cards, hscrollbar_policy = Gtk.PolicyType.NEVER,
            min_content_width = 300, max_content_width = 340, propagate_natural_width = true,
            min_content_height = 220, max_content_height = 320, propagate_natural_height = true, vexpand = true
        });
        map.connect (() => {
            load_cache ();
            refresh.begin ();
            if (timer == 0) timer = Timeout.add_seconds (300, () => { refresh.begin (); return Source.CONTINUE; });
        });
        unmap.connect (() => {
            if (timer != 0) { Source.remove (timer); timer = 0; }
        });
    }

    private static Gtk.Label label (string text) {
        return new Gtk.Label (text) { xalign = 0, wrap = true, max_width_chars = 36, selectable = false };
    }

    private void link (Gtk.Box box, string title, string uri) {
        // Only GitHub HTTPS links are ever opened, including cached content.
        if (!uri.has_prefix ("https://github.com/")) return;
        var button = new Gtk.Button.with_label (title) { halign = Gtk.Align.START, tooltip_text = title };
        var caption = button.child as Gtk.Label;
        if (caption != null) { caption.ellipsize = Pango.EllipsizeMode.END; caption.max_width_chars = 34; }
        button.add_css_class ("flat");
        button.clicked.connect (() => {
            try { AppInfo.launch_default_for_uri (uri, null); link_opened (); }
            catch (Error e) { status.label = _("Could not open GitHub. Try again."); }
        });
        box.append (button);
    }

    private static string text (Json.Object obj, string key, string fallback = "") {
        var node = obj.get_member (key);
        return node != null && node.get_value_type () == typeof (string) ? node.get_string () : fallback;
    }

    private void load_cache () {
        try {
            string data;
            FileUtils.get_contents (Path.build_filename (Environment.get_user_cache_dir (), "mseries", "github-tracker.json"), out data);
            render (data);
        } catch (Error e) {
            if (cards.get_first_child () == null) cards.append (label (_("Connecting to GitHub… Uses your existing gh sign-in.")));
        }
    }

    private void render (string data) throws Error {
        if (data.length > 1024 * 1024) throw new IOError.INVALID_DATA ("Snapshot too large");
        var parser = new Json.Parser ();
        parser.load_from_data (data);
        var root = parser.get_root ();
        if (root == null || root.get_node_type () != Json.NodeType.OBJECT) throw new IOError.INVALID_DATA ("Invalid snapshot");
        var obj = root.get_object ();
        var outcomes = obj.get_member ("outcomes");
        if (outcomes == null || outcomes.get_node_type () != Json.NodeType.ARRAY) throw new IOError.INVALID_DATA ("Missing outcomes");
        var child = cards.get_first_child ();
        while (child != null) { cards.remove (child); child = cards.get_first_child (); }
        var rows = outcomes.get_array ();
        status.label = text (obj, "error", _("Deployment outcomes · read-only"));
        for (uint i = 0; i < uint.min (rows.get_length (), 20); i++) {
            var node = rows.get_element (i);
            if (node.get_node_type () != Json.NodeType.OBJECT) continue;
            var row = node.get_object ();
            var card = new Gtk.Box (Gtk.Orientation.VERTICAL, 3);
            var title = label (text (row, "title", _("Tracked outcome")));
            title.add_css_class ("heading");
            card.append (title);
            var stamp = text (row, "observed_at");
            var when = stamp == "" ? null : new GLib.DateTime.from_iso8601 (stamp, null);
            bool stale = when == null || new GLib.DateTime.now_utc ().difference (when) > 10 * TimeSpan.MINUTE ||
                new GLib.DateTime.now_utc ().difference (when) < -TimeSpan.MINUTE;
            var error = text (row, "error");
            if (error != "" || stale) card.append (label (error != "" ? error : _("Evidence is stale. Refresh to verify.")));
            if (when != null) card.append (label (_("Observed %s").printf (when.to_local ().format ("%b %e, %Y %H:%M"))));
            var gates_node = row.get_member ("gates");
            if (gates_node != null && gates_node.get_node_type () == Json.NodeType.ARRAY) {
                var gates = gates_node.get_array ();
                uint completed = 0;
                var details = new Gtk.Box (Gtk.Orientation.VERTICAL, 2);
                for (uint j = 0; j < uint.min (gates.get_length (), 100); j++) {
                    var gate_node = gates.get_element (j);
                    if (gate_node.get_node_type () != Json.NodeType.OBJECT) continue;
                    var gate = gate_node.get_object ();
                    bool done = text (gate, "state") == "CLOSED" && text (gate, "stateReason") == "COMPLETED";
                    if (done) completed++;
                    link (details, (done ? "✓ " : "○ ") + text (gate, "title"), text (gate, "url"));
                }
                var summary = _("%u of %u gates complete").printf (completed, gates.get_length ());
                var truncated = row.get_member ("truncated");
                if (truncated != null && truncated.get_value_type () == typeof (bool) && truncated.get_boolean ()) summary += _(" · partial list");
                card.append (new Gtk.Expander (summary) { child = details });
            }
            var done_node = row.get_member ("done");
            bool done = done_node != null && done_node.get_value_type () == typeof (bool) && done_node.get_boolean ();
            card.append (label (done ? _("Outcome closed · gates completed") :
                _("Next: %s").printf (text (row, "next", _("Open the blueprint to review blockers")))));
            var ci_status = text (row, "ci", "unknown");
            card.append (label (_("%s CI: %s%s").printf (text (row, "branch", "main"), ci_status,
                stale || error != "" ? _(" · last observed") : "")));
            var sha = text (row, "sha");
            if (sha.length >= 7) card.append (label (_("Commit %s").printf (sha.substring (0, 7))));
            link (card, _("Open blueprint and blockers"), text (row, "url",
                "https://github.com/" + text (row, "repo") + "/issues"));
            var milestone = row.get_member ("milestone");
            if (milestone != null && milestone.get_node_type () == Json.NodeType.OBJECT)
                link (card, _("Open milestone"), text (milestone.get_object (), "url"));
            var prs = row.get_member ("prs");
            if (prs != null && prs.get_node_type () == Json.NodeType.ARRAY) {
                var pr_rows = prs.get_array ();
                for (uint j = 0; j < uint.min (pr_rows.get_length (), 10); j++) {
                    var pr_node = pr_rows.get_element (j);
                    if (pr_node.get_node_type () != Json.NodeType.OBJECT) continue;
                    var pr = pr_node.get_object ();
                    link (card, text (pr, "title") + " · CI " + text (pr, "ci", "unknown"), text (pr, "url"));
                }
            }
            link (card, _("Review repository pull requests"), "https://github.com/" + text (row, "repo") + "/pulls");
            card.append (label (_("Linked PRs use closing references; latest 10 reviewed.")));
            if (!done) card.append (label (_("Release acceptance still required.")));
            cards.append (card);
        }
    }

    private async void refresh () {
        if (busy) return;
        busy = true;
        refresh_button.sensitive = false;
        status.label = _("Refreshing GitHub…");
        try {
            var script = resources_lookup_data ("/io/elementary/desktop/wingpanel/datetime/github-tracker.py", ResourceLookupFlags.NONE);
            var process = new Subprocess.newv ({ "python3", "-c", (string) script.get_data () },
                SubprocessFlags.STDOUT_PIPE | SubprocessFlags.STDERR_SILENCE);
            string output;
            yield process.communicate_utf8_async (null, null, out output, null);
            render (output);
        } catch (Error e) {
            status.label = _("Refresh unavailable. Showing last observed evidence.");
        }
        refresh_button.sensitive = true;
        busy = false;
    }
}
