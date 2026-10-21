// Podman page for the main window: containers, images and volumes from the user's rootless Podman.
// Refreshes only while it is visible, and rebuilds the list only when the data actually changed.

public class PodmanPage : Gtk.Box {
    public signal void notice (string text);

    private PodmanClient client = new PodmanClient ();
    private Gtk.DropDown category;
    private Gtk.SearchEntry search;
    private Gtk.Label summary;
    private Gtk.Label status;
    private Gtk.ListBox list;
    private PodmanContainer[] containers = {};
    private PodmanImage[] images = {};
    private PodmanVolume[] volumes = {};
    private HashTable<string, PodmanStats> stats = new HashTable<string, PodmanStats> (str_hash, str_equal);
    private HashTable<string, Gtk.Label> stat_labels = new HashTable<string, Gtk.Label> (str_hash, str_equal);
    private string signature = "";
    private bool loading = false;
    private bool reload_again = false;
    private bool unavailable = false;
    private uint poll_id = 0;
    private GenericSet<string> pending = new GenericSet<string> (str_hash, str_equal);

    public PodmanPage () {
        Object (orientation: Gtk.Orientation.VERTICAL, spacing: 0);
        var filters = new Gtk.Box (Gtk.Orientation.HORIZONTAL, 8) { margin_start = 12, margin_end = 12, margin_top = 8, margin_bottom = 8 };
        category = new Gtk.DropDown.from_strings ({ "Containers", "Images", "Volumes" });
        search = new Gtk.SearchEntry () { hexpand = true, placeholder_text = "Search Podman…" };
        category.update_property (Gtk.AccessibleProperty.LABEL, "Podman resource type", -1);
        search.update_property (Gtk.AccessibleProperty.LABEL, "Search Podman resources", -1);
        filters.append (category);
        filters.append (search);
        append (filters);

        summary = new Gtk.Label ("") { xalign = 0, margin_start = 12, margin_end = 12, margin_bottom = 6, wrap = true };
        summary.add_css_class ("dim-label");
        append (summary);

        list = new Gtk.ListBox () { selection_mode = Gtk.SelectionMode.NONE };
        list.add_css_class ("rich-list");
        list.add_css_class ("orchard-list");
        // Rows must fit the window width so the action buttons never scroll out of view.
        append (new Gtk.ScrolledWindow () { child = list, vexpand = true, hscrollbar_policy = Gtk.PolicyType.NEVER });

        status = new Gtk.Label ("") { margin_top = 6, margin_bottom = 6, margin_start = 12, xalign = 0, wrap = true };
        status.add_css_class ("h4");
        append (status);

        category.notify["selected"].connect (() => { render (); });
        search.search_changed.connect (() => { render (); });
        map.connect (() => {
            reload.begin ();
            if (poll_id == 0) poll_id = Timeout.add_seconds (5, () => { reload.begin (); return Source.CONTINUE; });
        });
        unmap.connect (stop_polling);
        destroy.connect (stop_polling);
    }

    private void stop_polling () {
        if (poll_id != 0) { Source.remove (poll_id); poll_id = 0; }
    }

    public async void reload () {
        if (loading) { reload_again = true; return; }
        loading = true;
        try {
            if (!client.installed ()) {
                unavailable = true;
                status.label = "Podman is not installed. Install it with: sudo apt install podman";
                summary.label = "";
                clear_list ();
                signature = "";
                loading = false;
                return;
            }
            unavailable = false;
            var next_containers = yield client.list_containers ();
            var next_images = yield client.list_images ();
            var next_volumes = yield client.list_volumes ();
            var next = make_signature (next_containers, next_images, next_volumes);
            containers = next_containers; images = next_images; volumes = next_volumes;
            if (next != signature) { signature = next; render (); } else update_summary ();
            // Counters change every poll, so they are written into the existing rows instead of rebuilding the list.
            bool any_running = false;
            foreach (var c in containers) if (c.running) { any_running = true; break; }
            try {
                stats = any_running ? PodmanClient.stats_by_name (yield client.list_stats ()) : new HashTable<string, PodmanStats> (str_hash, str_equal);
            } catch (Error e) {
                stats = new HashTable<string, PodmanStats> (str_hash, str_equal);
            }
            update_stats ();
        } catch (Error e) {
            status.label = "Cannot reach Podman: " + e.message;
        }
        loading = false;
        if (reload_again) { reload_again = false; yield reload (); }
    }

    private static string make_signature (PodmanContainer[] c, PodmanImage[] i, PodmanVolume[] v) {
        var s = new StringBuilder ();
        foreach (var x in c) s.append ("c|%s|%s|%s|%s|%s\n".printf (x.id, x.name, x.state, x.status, x.ports));
        foreach (var x in i) s.append ("i|%s|%s|%lld|%lld\n".printf (x.id, x.name, x.size, x.containers));
        foreach (var x in v) s.append ("v|%s|%s\n".printf (x.name, x.mountpoint));
        return s.str;
    }

    private void clear_list () {
        while (list.get_first_child () != null) list.remove (list.get_first_child ());
        stat_labels.remove_all ();
    }

    private void update_stats () {
        stat_labels.foreach ((name, label) => {
            var s = stats.lookup (name);
            label.label = s == null ? "" : "CPU %s · Memory %s · PIDs %s".printf (s.cpu_percent, s.mem_usage.split ("/")[0].strip (), s.pids);
            label.visible = s != null;
        });
    }

    private void update_summary () {
        int running = 0;
        foreach (var c in containers) if (c.running) running++;
        // Image sizes are not summed: images share layers, so a total would overstate real disk use.
        summary.label = "%d of %d containers running · %d images · %d volumes".printf (
            running, containers.length, images.length, volumes.length);
    }

    private bool matches (string text) {
        return PaletteMatch.score (search.text, text) >= 0;
    }

    private void render () {
        if (unavailable) return;
        clear_list ();
        update_summary ();
        int shown = 0;
        switch (category.selected) {
        case 0:
            foreach (var c in PodmanClient.sorted_containers (containers)) if (matches (c.name + " " + c.image + " " + c.state + " " + c.ports)) { list.append (container_row (c)); shown++; }
            break;
        case 1:
            foreach (var i in images) if (matches (i.name)) { list.append (image_row (i)); shown++; }
            break;
        default:
            foreach (var v in volumes) if (matches (v.name + " " + v.mountpoint)) { list.append (volume_row (v)); shown++; }
            break;
        }
        status.label = shown == 0 ? (search.text.strip () == "" ? "Nothing here." : "No matches.") : "Resources reported by the local Podman.";
        update_stats ();
    }

    private Gtk.Box row_shell (string title, string detail, out Gtk.Box actions) {
        var row = new Gtk.Box (Gtk.Orientation.HORIZONTAL, 12) { margin_top = 8, margin_bottom = 8, margin_start = 12, margin_end = 12 };
        var labels = new Gtk.Box (Gtk.Orientation.VERTICAL, 3) { hexpand = true };
        var name = new Gtk.Label (title) { xalign = 0, ellipsize = Pango.EllipsizeMode.MIDDLE, max_width_chars = 42, selectable = true };
        name.add_css_class ("h3");
        var note = new Gtk.Label (detail) { xalign = 0, wrap = true, wrap_mode = Pango.WrapMode.WORD_CHAR, selectable = true };
        note.add_css_class ("dim-label");
        labels.append (name);
        labels.append (note);
        row.append (labels);
        actions = new Gtk.Box (Gtk.Orientation.HORIZONTAL, 6) { valign = Gtk.Align.CENTER };
        row.append (actions);
        return row;
    }

    private Gtk.Widget container_row (PodmanContainer c) {
        Gtk.Box actions;
        var parts = new string[0];
        parts += c.image;
        parts += c.status != "" ? c.status : c.state;
        if (c.ports != "") parts += c.ports;
        if (c.pod != "") parts += "pod " + c.pod;
        var row = row_shell (c.name, string.joinv (" · ", parts), out actions);
        // Live counters sit under the detail line so the action buttons keep a fixed width.
        var live = new Gtk.Label ("") { xalign = 0, visible = false, ellipsize = Pango.EllipsizeMode.END };
        live.add_css_class ("dim-label");
        live.update_property (Gtk.AccessibleProperty.LABEL, "Live CPU and memory for " + c.name, -1);
        ((Gtk.Box) row.get_first_child ()).append (live);
        stat_labels.insert (c.name, live);
        var dot = new Gtk.Image.from_icon_name ("media-record-symbolic");
        dot.add_css_class (c.running ? "success" : "dim-label");
        row.prepend (dot);
        var busy = pending.contains (c.id);
        var toggle = new Gtk.Button.with_label (c.running || c.paused ? "Stop" : "Start") { sensitive = !busy };
        toggle.clicked.connect (() => { act.begin (c, c.running || c.paused ? "stop" : "start"); });
        actions.append (toggle);
        if (c.running || c.paused) {
            var restart = new Gtk.Button.with_label ("Restart") { sensitive = !busy };
            restart.clicked.connect (() => { act.begin (c, "restart"); });
            actions.append (restart);
        }
        var remove = trash_button ("Remove container " + c.name);
        remove.sensitive = !busy && !c.running && !c.paused;
        remove.tooltip_text = c.running || c.paused ? "Stop the container before removing it" : "Remove container";
        remove.clicked.connect (() => {
            confirm ("Remove %s?".printf (c.name), "The container and its writable layer are deleted. Images and named volumes are kept.", "Remove",
                     () => { remove_item.begin (c.id, c.name, "container"); });
        });
        actions.append (remove);
        var info = new Gtk.Button.from_icon_name ("document-properties-symbolic") { tooltip_text = "Image, ports, mounts, CPU and memory" };
        info.update_property (Gtk.AccessibleProperty.LABEL, "Container details", -1);
        info.clicked.connect (() => { open_details (c); });
        actions.append (info);
        return row;
    }

    public void open_details (PodmanContainer c) {
        var window = new PodmanDetails (get_root () as Gtk.Window, client, c);
        window.changed.connect (() => { signature = ""; reload.begin (); });
        window.present ();
    }

    private Gtk.Widget image_row (PodmanImage i) {
        Gtk.Box actions;
        var detail = "%s · %s".printf (format_size ((uint64) i.size), i.containers == 1 ? "1 container" : "%lld containers".printf (i.containers));
        var row = row_shell (i.name, detail, out actions);
        var remove = trash_button ("Remove image " + i.name);
        remove.sensitive = i.containers == 0 && !pending.contains (i.id);
        remove.tooltip_text = i.containers == 0 ? "Remove image" : "Remove the containers using this image first";
        remove.clicked.connect (() => {
            confirm ("Remove image %s?".printf (i.name), "It can be pulled again when needed.", "Remove",
                     () => { remove_item.begin (i.id, i.name, "image"); });
        });
        actions.append (remove);
        return row;
    }

    private Gtk.Widget volume_row (PodmanVolume v) {
        Gtk.Box actions;
        var row = row_shell (v.name, "%s · %s".printf (v.driver, v.mountpoint), out actions);
        var remove = trash_button ("Remove volume " + v.name);
        remove.sensitive = !pending.contains (v.name);
        remove.clicked.connect (() => {
            confirm ("Remove volume %s?".printf (v.name), "Its data is permanently deleted. Podman refuses if a container still uses it.", "Remove",
                     () => { remove_item.begin (v.name, v.name, "volume"); });
        });
        actions.append (remove);
        return row;
    }

    private Gtk.Button trash_button (string label) {
        var button = new Gtk.Button.from_icon_name ("edit-delete-symbolic") { tooltip_text = label };
        button.add_css_class ("destructive-action");
        button.update_property (Gtk.AccessibleProperty.LABEL, label, -1);
        return button;
    }

    private delegate void Confirmed ();

    private void confirm (string title, string detail, string verb, owned Confirmed yes) {
        var question = new Gtk.AlertDialog (title) { detail = detail, buttons = { "Cancel", verb }, cancel_button = 0, default_button = 0 };
        question.choose.begin (get_root () as Gtk.Window, null, (obj, result) => {
            try { if (question.choose.end (result) == 1) yes (); } catch (Error e) { }
        });
    }

    private async void act (PodmanContainer c, string verb) {
        if (pending.contains (c.id)) return;
        pending.add (c.id);
        render ();
        try {
            notice ("%s %s…".printf (verb, c.name));
            yield client.container_action (c.id, verb);
            notice ("%s: %s complete".printf (c.name, verb));
        } catch (Error e) {
            notice (e.message);
        }
        pending.remove (c.id);
        signature = "";
        yield reload ();
    }

    private async void remove_item (string id, string label, string kind) {
        if (pending.contains (id)) return;
        pending.add (id);
        render ();
        try {
            switch (kind) {
            case "container": yield client.remove_container (id); break;
            case "image": yield client.remove_image (id); break;
            default: yield client.remove_volume (id); break;
            }
            notice ("Removed %s %s".printf (kind, label));
        } catch (Error e) {
            notice (e.message);
        }
        pending.remove (id);
        signature = "";
        yield reload ();
    }
}
