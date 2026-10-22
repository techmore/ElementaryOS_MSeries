public class PaletteEntry : Object {
    public string title;
    public string action;
    public string target;
    public int rank = 0;
    public PaletteEntry (string label, string verb, string id = "") { title = label; action = verb; target = id; }
}

public class CommandPalette : Gtk.Window {
    private IncusClient client;
    private Gtk.SearchEntry query;
    private Gtk.ListBox list;
    private List<PaletteEntry> catalog = new List<PaletteEntry> ();
    public signal void selected (string action, string target);
    public CommandPalette (Gtk.Window parent, IncusClient api) {
        Object (transient_for: parent, modal: true, title: "Commands and resources", default_width: 620, default_height: 440);
        client = api;
        var box = new Gtk.Box (Gtk.Orientation.VERTICAL, 8) { margin_top = 12, margin_bottom = 12, margin_start = 12, margin_end = 12 };
        query = new Gtk.SearchEntry () { placeholder_text = "Search resources, or type stop db, logs web, shell api…" };
        list = new Gtk.ListBox () { selection_mode = Gtk.SelectionMode.SINGLE };
        list.row_activated.connect ((row) => {
            var entry = row.get_data<PaletteEntry> ("command");
            selected (entry.action, entry.target); destroy ();
        });
        query.search_changed.connect (refresh);
        query.activate.connect (() => { var row = list.get_selected_row (); if (row != null) row.activate (); });
        box.append (query); box.append (new Gtk.ScrolledWindow () { child = list, vexpand = true }); child = box;
        catalog.append (new PaletteEntry ("Open Dashboard", "dashboard"));
        catalog.append (new PaletteEntry ("Open Local AI Models", "models"));
        catalog.append (new PaletteEntry ("Open Model Sandboxes", "sandboxes"));
        catalog.append (new PaletteEntry ("Open Incus System and Daemon Logs", "system"));
        catalog.append (new PaletteEntry ("Create Container or VM…", "create"));
        catalog.append (new PaletteEntry ("Open Resources", "resources"));
        catalog.append (new PaletteEntry ("Open Instance Mounts", "mounts"));
        catalog.append (new PaletteEntry ("Open Preferences", "preferences"));
        catalog.append (new PaletteEntry ("Refresh", "refresh"));
        refresh (); load.begin ();
        query.grab_focus ();
    }
    private async void load () {
        try {
            var items = yield client.list_instances ();
            foreach (var item in items) {
                catalog.append (new PaletteEntry ("Inspect " + item.name, "inspect", item.name));
                catalog.append (new PaletteEntry ("Logs " + item.name, "logs", item.name));
                catalog.append (new PaletteEntry ("Shell " + item.name, "shell", item.name));
                catalog.append (new PaletteEntry ("Console " + item.name, "shell", item.name));
                catalog.append (new PaletteEntry ((item.running ? "Stop " : "Start ") + item.name, item.running ? "stop" : "start", item.name));
                if (item.running) catalog.append (new PaletteEntry ("Restart " + item.name, "restart", item.name));
            }
            string[] kinds = { "images", "networks", "profiles", "projects", "network-zones" };
            foreach (var kind in kinds) {
                try {
                    var response = yield client.call ("GET", "/1.0/" + kind + "?recursion=1");
                    foreach (var node in response.get_array_member ("metadata").get_elements ()) {
                        var data = node.get_object ();
                        string name = data.get_string_member_with_default (kind == "images" ? "fingerprint" : "name", "");
                        catalog.append (new PaletteEntry (kind + " " + name, kind, name));
                    }
                } catch (Error e) { /* Other catalogs remain usable if a capability is unavailable. */ }
            }
        } catch (Error e) { catalog.append (new PaletteEntry ("Incus unavailable — Refresh", "refresh")); }
        refresh ();
    }
    private void refresh () {
        while (list.get_first_child () != null) list.remove (list.get_first_child ());
        var matches = new List<PaletteEntry> ();
        foreach (var entry in catalog) {
            entry.rank = PaletteMatch.score (query.text, entry.title);
            if (entry.rank >= 0) matches.append (entry);
        }
        matches.sort ((a, b) => b.rank == a.rank ? a.title.collate (b.title) : b.rank - a.rank);
        int count = 0;
        foreach (var entry in matches) {
            if (++count > 50) break;
            var row = new Gtk.ListBoxRow () { child = new Gtk.Label (entry.title) { xalign = 0, margin_top = 8, margin_bottom = 8, margin_start = 8, ellipsize = Pango.EllipsizeMode.MIDDLE } };
            row.set_data<PaletteEntry> ("command", entry); list.append (row);
        }
        list.select_row (list.get_row_at_index (0));
    }
}
