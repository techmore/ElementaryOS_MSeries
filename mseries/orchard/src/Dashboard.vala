private class MetricRow : Object {
    public string name;
    public int64 memory;
    public int64 disk;
    public double cpu;
    public double network;
    public bool baseline;
    public bool cpu_known;
    public bool network_known;
    public bool memory_known;
    public bool disk_known;
}


public class Dashboard : Gtk.Box {
    private Gtk.Label headline;
    private Gtk.FlowBox metrics;
    private Gtk.Label memory;
    private Gtk.Label cpu;
    private Gtk.Label network;
    private Gtk.Label disk;
    private OrchardSparkline memory_graph = new OrchardSparkline ();
    private OrchardSparkline cpu_graph = new OrchardSparkline ();
    private OrchardSparkline network_graph = new OrchardSparkline ();
    private HashTable<string, Instance> previous = new HashTable<string, Instance> (str_hash, str_equal);
    private int64 last_time = 0;
    private string history_file;
    private Json.Array history = new Json.Array ();
    private int writes = 0;
    private Gtk.Label history_status;
    private Gtk.Box table;
    private Gtk.Label storage;
    private List<MetricRow> rows = new List<MetricRow> ();
    private int sort_column = 0;
    private bool reverse = false;
    private Preferences preferences = new Preferences ();

    public Dashboard (string scope = "aggregate", bool with_intro = true) {
        Object (orientation: Gtk.Orientation.VERTICAL, spacing: 16, margin_top: with_intro ? 24 : 8, margin_bottom: 24, margin_start: 32, margin_end: 32);
        headline = new Gtk.Label ("Waiting for a sample…") { xalign = 0 };
        headline.add_css_class (with_intro ? "title-2" : "title-4");
        headline.wrap = true;
        if (with_intro) {
            var intro = new Gtk.Box (Gtk.Orientation.HORIZONTAL, 12);
            intro.append (new Gtk.Image.from_icon_name ("orchard-incus-symbolic") { pixel_size = 32 });
            var titles = new Gtk.Box (Gtk.Orientation.VERTICAL, 4);
            titles.append (headline);
            var subtitle = new Gtk.Label ("Your local containers and virtual machines") { xalign = 0, wrap = true };
            subtitle.add_css_class ("dim-label"); titles.append (subtitle);
            intro.append (titles); append (intro);
        } else {
            append (headline);
        }
        metrics = new Gtk.FlowBox () {
            selection_mode = Gtk.SelectionMode.NONE, homogeneous = true,
            min_children_per_line = 1, max_children_per_line = 2,
            column_spacing = 8, row_spacing = 8
        };
        append (metrics);
        cpu = metric ("CPU usage", cpu_graph);
        memory = metric ("Memory usage", memory_graph);
        network = metric ("Network throughput", network_graph);
        disk = new Gtk.Label ("Root-disk usage · waiting for data") { xalign = 0, wrap = true, max_width_chars = 24 };
        storage = new Gtk.Label ("Storage accounting is loading…") { xalign = 0, wrap = true, max_width_chars = 24 };
        storage.add_css_class ("dim-label");
        var storage_card = new Gtk.Box (Gtk.Orientation.VERTICAL, 8) { width_request = 200 };
        storage_card.add_css_class ("ml-card"); storage_card.add_css_class ("ml-spec");
        var storage_title = new Gtk.Label ("Storage") { xalign = 0 };
        storage_title.add_css_class ("heading");
        storage_card.append (storage_title); storage_card.append (disk); storage_card.append (storage);
        metrics.insert (storage_card, -1);
        int.try_parse (preferences.read ("stats-sort", "0"), out sort_column);
        reverse = preferences.read ("stats-reverse", "false") == "true";
        var table_title = new Gtk.Label ("Instance activity") { xalign = 0, margin_top = 8 };
        table_title.add_css_class ("title-4"); append (table_title);
        var headings = new Gtk.Box (Gtk.Orientation.HORIZONTAL, 8) { homogeneous = true };
        string[] columns = { "Instance", "Memory", "CPU cores", "Network /s", "Root disk" };
        for (int i = 0; i < columns.length; i++) {
            int column = i; var button = new Gtk.Button.with_label (columns[i]);
            button.clicked.connect (() => {
                reverse = sort_column == column ? !reverse : false; sort_column = column;
                try { preferences.write ("stats-sort", column.to_string ()); preferences.write ("stats-reverse", reverse ? "true" : "false"); } catch (Error e) { }
                render_table ();
            }); headings.append (button);
        }
        append (headings); table = new Gtk.Box (Gtk.Orientation.VERTICAL, 6);
        append (table);
        var note = new Gtk.Label ("Live Incus measurements. Graphs retain up to 24 hours of recorded samples; gaps are left disconnected. CPU is measured in core equivalents; rates omit baseline samples and counter resets.") { wrap = true, xalign = 0 };
        note.add_css_class ("ml-fineprint"); append (note);
        history_status = new Gtk.Label ("") { xalign = 0, wrap = true }; history_status.add_css_class ("ml-fineprint"); append (history_status);
        var directory = Path.build_filename (Environment.get_user_state_dir (), "orchard-incus", "metrics");
        DirUtils.create_with_parents (directory, 0700);
        history_file = Path.build_filename (directory, Uri.escape_string (scope, null, false) + ".json");
        restore_history ();
        map.connect (() => { if (labels_stale) apply_labels (); if (table_stale) render_table (); });
    }
    private Gtk.Label metric (string title, OrchardSparkline graph) {
        var label = new Gtk.Label (title) { xalign = 0, wrap = true, max_width_chars = 24 };
        var card = new Gtk.Box (Gtk.Orientation.VERTICAL, 8) { width_request = 200 };
        card.add_css_class ("ml-card"); card.add_css_class ("ml-spec");
        label.add_css_class ("heading");
        graph.content_height = 64;
        card.append (label); card.append (graph);
        metrics.insert (card, -1);
        return label;
    }
    public void update (Instance[] items) {
        int running = 0;
        int known_memory = 0;
        int known_disk = 0;
        int cpu_pairs = 0;
        int network_pairs = 0;
        int64 bytes = 0;
        int64 disk_bytes = 0;
        double cores = 0;
        double network_rate = 0;
        int64 now = get_monotonic_time ();
        double seconds = (now - last_time) / 1000000.0;
        rows = new List<MetricRow> ();
        foreach (var item in items) {
            var row = new MetricRow (); row.name = item.name; row.memory = item.memory_bytes; row.disk = item.disk_bytes; row.baseline = true; row.memory_known = item.memory_available; row.disk_known = item.disk_available; rows.append (row);
            if (!item.running) continue;
            running++;
            bytes += item.memory_bytes;
            disk_bytes += item.disk_bytes;
            if (item.memory_available) known_memory++;
            if (item.disk_available) known_disk++;
            var old = previous.lookup (item.name);
            if (last_time != 0 && seconds > 0 && old != null && old.running) {
                row.baseline = !(item.cpu_available && old.cpu_available && item.network_available && old.network_available);
                if (item.cpu_available && old.cpu_available && item.cpu_ns >= old.cpu_ns) { row.cpu = (item.cpu_ns - old.cpu_ns) / 1000000000.0 / seconds; row.cpu_known = true; cpu_pairs++; }
                if (item.network_available && old.network_available && item.network_bytes >= old.network_bytes) { row.network = (item.network_bytes - old.network_bytes) / seconds; row.network_known = true; network_pairs++; }
                cores += row.cpu; network_rate += row.network;
            }
        }
        headline_text = "%d instances · %d running".printf (items.length, running);
        memory_text = running > 0 && known_memory == 0 ? "Memory · unavailable" : "Reported memory · " + format_size ((uint64) bytes) + (known_memory < running ? " (some instances unavailable)" : "");
        disk_text = known_disk == 0 ? "Running root-disk usage · unavailable" : "Reported running root disks · " + format_size ((uint64) disk_bytes) + (known_disk < running ? " (some instances unavailable)" : "");
        history_text = "Updated " + new DateTime.now_local ().format ("%H:%M:%S");
        cpu_text = last_time == 0 ? "CPU · collecting baseline…" : cpu_pairs == 0 && running > 0 ? "CPU · unavailable / collecting baseline" : "Reported CPU · %.2f cores".printf (cores);
        network_text = last_time == 0 ? "Network · collecting baseline…" : network_pairs == 0 && running > 0 ? "Network · unavailable / collecting baseline" : "Reported network · " + format_size ((uint64) network_rate) + "/s";
        int64 timestamp = new DateTime.now_utc ().to_unix ();
        var point = new Json.Object (); point.set_int_member ("time", timestamp);
        if (known_memory > 0 || running == 0) { point.set_int_member ("memory", bytes); memory_graph.record (bytes, timestamp); }
        if (last_time != 0 && (cpu_pairs > 0 || running == 0)) { cpu_graph.record (cores, timestamp); point.set_double_member ("cpu", cores); }
        if (last_time != 0 && (network_pairs > 0 || running == 0)) { network_graph.record (network_rate, timestamp); point.set_double_member ("network", network_rate); }
        var retained = new Json.Array ();
        uint start = history.get_length () > 28799 ? history.get_length () - 28799 : 0;
        for (uint i = start; i < history.get_length (); i++) {
            var old_point = history.get_object_element (i);
            if (old_point.get_int_member ("time") >= timestamp - 86400) retained.add_object_element (old_point);
        }
        retained.add_object_element (point); history = retained;
        if (++writes % 20 == 0) save_history ();
        previous.remove_all ();
        foreach (var item in items) previous.insert (item.name, item);
        last_time = now;
        apply_labels ();
        render_table ();
    }
    private string headline_text = "";
    private string memory_text = "";
    private string disk_text = "";
    private string history_text = "";
    private string cpu_text = "";
    private string network_text = "";
    private bool labels_stale = false;
    /* Widgets change only while the dashboard is on screen; a hidden page keeps recording without relayouts. */
    private void apply_labels () {
        if (!get_mapped ()) { labels_stale = true; return; }
        labels_stale = false;
        headline.label = headline_text; memory.label = memory_text; disk.label = disk_text;
        history_status.label = history_text; cpu.label = cpu_text; network.label = network_text;
    }
    private void restore_history () {
        try {
            var file = File.new_for_path (history_file);
            if (file.query_info (FileAttribute.STANDARD_SIZE, FileQueryInfoFlags.NONE).get_size () > 10485760) return;
            var parser = new Json.Parser (); parser.load_from_file (history_file);
            if (parser.get_root ().get_node_type () != Json.NodeType.ARRAY) return;
            var array = parser.get_root ().get_array ();
            int64 cutoff = new DateTime.now_utc ().to_unix () - 86400;
            uint start = array.get_length () > 28800 ? array.get_length () - 28800 : 0;
            for (uint i = start; i < array.get_length (); i++) {
                if (array.get_element (i).get_node_type () != Json.NodeType.OBJECT) continue;
                var point = array.get_object_element (i);
                if (!point.has_member ("time") || point.get_member ("time").get_value_type () != typeof (int64)) continue;
                int64 time = point.get_int_member ("time"); if (time < cutoff || time > cutoff + 86400) continue;
                history.add_object_element (point);
                if (point.has_member ("memory") && point.get_member ("memory").get_value_type () == typeof (int64)) memory_graph.record (point.get_int_member ("memory"), time);
                if (point.has_member ("cpu") && (point.get_member ("cpu").get_value_type () == typeof (double) || point.get_member ("cpu").get_value_type () == typeof (int64))) cpu_graph.record (point.get_double_member ("cpu"), time);
                if (point.has_member ("network") && (point.get_member ("network").get_value_type () == typeof (double) || point.get_member ("network").get_value_type () == typeof (int64))) network_graph.record (point.get_double_member ("network"), time);
            }
        } catch (Error e) { /* Missing/corrupt history never prevents live metrics. */ }
    }
    private void save_history () {
        try {
            var node = new Json.Node (Json.NodeType.ARRAY); node.set_array (history);
            var generator = new Json.Generator () { root = node };
            FileUtils.set_contents (history_file, generator.to_data (null));
            history_status.label = "Recorded history saved locally.";
        } catch (Error e) { history_status.label = "History could not be saved: " + e.message; }
    }
    public override void dispose () { if (history_file != null) save_history (); base.dispose (); }
    private bool table_stale = false;
    private void render_table () {
        // Rebuilding the rows every sample is wasted work while the dashboard is off screen:
        // remember that it is stale and render once it is mapped again.
        if (!get_mapped ()) { table_stale = true; return; }
        table_stale = false;
        while (table.get_first_child () != null) table.remove (table.get_first_child ());
        rows.sort_with_data ((a, b) => {
            int order = a.name.collate (b.name);
            double left = sort_column == 1 ? a.memory : sort_column == 2 ? a.cpu : sort_column == 3 ? a.network : a.disk;
            double right = sort_column == 1 ? b.memory : sort_column == 2 ? b.cpu : sort_column == 3 ? b.network : b.disk;
            if (sort_column != 0 && left != right) order = left > right ? -1 : 1;
            return reverse ? -order : order;
        });
        if (rows == null) {
            var empty = new Gtk.Label ("Start an instance to see its resource activity here.") { xalign = 0, wrap = true, margin_top = 8, margin_bottom = 8 };
            empty.add_css_class ("dim-label"); table.append (empty);
        }
        foreach (var sample in rows) {
            var row = new Gtk.Box (Gtk.Orientation.HORIZONTAL, 8) { homogeneous = true };
            string[] values = { sample.name, sample.memory_known ? format_size ((uint64) sample.memory) : "—", !sample.cpu_known ? "—" : "%.2f".printf (sample.cpu), !sample.network_known ? "—" : format_size ((uint64) sample.network), sample.disk_known ? format_size ((uint64) sample.disk) : "—" };
            foreach (var value in values) row.append (new Gtk.Label (value) { xalign = 0, ellipsize = Pango.EllipsizeMode.END });
            table.append (row);
        }
    }
    public void set_storage (string description) { storage.label = description; }
    public void set_error (string error) { history_status.label = "Statistics are stale: " + error; }
}
