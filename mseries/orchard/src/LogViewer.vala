public class LogPane : Gtk.Box {
    private IncusClient client;
    private string instance;
    private Gtk.TextView view;
    private Gtk.SearchEntry query;
    private Gtk.CheckButton matching;
    private Gtk.DropDown filename;
    private Gtk.Label status;
    private string raw = "";
    private bool busy = false;
    private uint timer = 0;
    public LogPane (string name, uint colour) {
        Object (orientation: Gtk.Orientation.VERTICAL, spacing: 8, width_request: 360, hexpand: true);
        client = new IncusClient (15); instance = name;
        var header = new Gtk.Box (Gtk.Orientation.HORIZONTAL, 8);
        var title = new Gtk.Label (name) { xalign = 0, hexpand = true };
        title.add_css_class ("heading"); title.add_css_class ("orchard-log-" + (colour % 4).to_string ()); header.append (title);
        var remove = new Gtk.Button.from_icon_name ("window-close-symbolic") { tooltip_text = "Close log pane" };
        remove.clicked.connect (() => { var parent = get_parent () as Gtk.Box; if (parent != null) parent.remove (this); }); header.append (remove); append (header);
        filename = new Gtk.DropDown.from_strings ({ "lxc.log", "console.log", "qemu.log", "System journal (manual refresh)" });
        filename.notify["selected"].connect (() => reload.begin ()); append (filename);
        query = new Gtk.SearchEntry () { placeholder_text = "Search and highlight…" }; query.search_changed.connect (render); append (query);
        matching = new Gtk.CheckButton.with_label ("Only matching lines"); matching.toggled.connect (render); append (matching);
        view = new Gtk.TextView () { editable = false, monospace = true, left_margin = 8, right_margin = 8 };
        view.buffer.create_tag ("match", "background", "#ffe16b", "foreground", "#151515", null);
        append (new Gtk.ScrolledWindow () { child = view, vexpand = true });
        var refresh = new Gtk.Button.with_label ("Refresh now"); refresh.clicked.connect (() => reload.begin ()); append (refresh);
        status = new Gtk.Label ("") { xalign = 0, wrap = true }; append (status);
        weak LogPane pane = this;
        timer = Timeout.add_seconds (3, () => { if (pane == null) return Source.REMOVE; if (pane.filename.selected < 3) pane.reload.begin (); return Source.CONTINUE; });
        reload.begin ();
    }
    private async void reload () {
        if (busy) return;
        busy = true;
        uint selection = filename.selected;
        try {
            var selected = (Gtk.StringObject) filename.selected_item;
            var text = filename.selected == 3 ? yield client.journal (instance) : yield client.read_log (instance, selected.string);
            if (selection != filename.selected) { busy = false; reload.begin (); return; }
            if (text.length > 1048576) text = text.substring (text.length - 1048576).make_valid ();
            var ansi = new Regex ("\\x1b\\[[0-?]*[ -/]*[@-~]|\\x1b\\][^\\x07\\x1b]*(?:\\x07|\\x1b\\\\)");
            raw = ansi.replace (text, -1, 0, "");
            render ();
            status.label = "Updated " + new DateTime.now_local ().format ("%H:%M:%S") + (filename.selected == 3 ? " · journal refresh is manual" : " · refreshes every 3s");
        } catch (Error e) { status.label = e.message; }
        busy = false;
    }
    private void render () {
        var text = new StringBuilder ();
        foreach (var line in raw.split ("\n")) if (!matching.active || query.text == "" || line.down ().contains (query.text.down ())) text.append (line + "\n");
        view.buffer.text = text.str;
        if (query.text == "") return;
        Gtk.TextIter cursor; view.buffer.get_start_iter (out cursor);
        Gtk.TextIter start; Gtk.TextIter end;
        while (cursor.forward_search (query.text, Gtk.TextSearchFlags.CASE_INSENSITIVE | Gtk.TextSearchFlags.TEXT_ONLY, out start, out end, null)) {
            view.buffer.apply_tag_by_name ("match", start, end); cursor = end;
        }
    }
    public override void dispose () {
        if (timer != 0) { Source.remove (timer); timer = 0; }
        base.dispose ();
    }
}

public class LogViewer : Gtk.Window {
    private IncusClient client;
    private Gtk.Box panes;
    private Gtk.DropDown names;
    private Gtk.Label status;
    private uint colours = 0;
    private string initial;
    public LogViewer (Gtk.Window parent, IncusClient api, string initial_name = "") {
        Object (transient_for: parent, title: "Instance logs", default_width: 1100, default_height: 620);
        client = api; initial = initial_name;
        var box = new Gtk.Box (Gtk.Orientation.VERTICAL, 12) { margin_top = 12, margin_bottom = 12, margin_start = 12, margin_end = 12 };
        var controls = new Gtk.Box (Gtk.Orientation.HORIZONTAL, 8);
        names = new Gtk.DropDown.from_strings ({ "Loading instances…" }); controls.append (names);
        var add = new Gtk.Button.with_label ("Add log pane"); add.clicked.connect (() => {
            var chosen = names.selected_item as Gtk.StringObject;
            if (chosen != null && chosen.string != "Loading instances…") append_pane (chosen.string);
        }); controls.append (add); box.append (controls);
        panes = new Gtk.Box (Gtk.Orientation.HORIZONTAL, 16) { homogeneous = true };
        box.append (new Gtk.ScrolledWindow () { child = panes, vexpand = true });
        status = new Gtk.Label ("Kernel/console logs refresh every three seconds. Systemd journals are available as explicit snapshots.") { xalign = 0, wrap = true }; box.append (status); child = box;
        var style = new Gtk.CssProvider ();
        style.load_from_string (".orchard-log-0 { color: #3689e6; } .orchard-log-1 { color: #68b723; } .orchard-log-2 { color: #a56de2; } .orchard-log-3 { color: #f37329; }");
        Gtk.StyleContext.add_provider_for_display (get_display (), style, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION);
        load.begin ();
    }
    private void append_pane (string name) { panes.append (new LogPane (name, colours++)); }
    private async void load () {
        try {
            var items = yield client.list_instances ();
            string[] choices = {};
            foreach (var item in items) choices += item.name;
            names.model = new Gtk.StringList (choices);
            if (initial != "") append_pane (initial);
            else if (choices.length > 0) append_pane (choices[0]);
        } catch (Error e) { status.label = e.message; }
    }
}
