// Details window for one Podman container: image, state, ports, mounts, live CPU/memory and the
// raw `podman inspect` document. Counters refresh every few seconds while the window is open.

public class PodmanDetails : Gtk.Window {
    public signal void changed ();

    private PodmanClient client;
    private string container_id;
    private string container_name;
    private Gtk.Label message;
    private Gtk.Label container_text;
    private Gtk.Label network_text;
    private Gtk.Label mounts_text;
    private Gtk.Label resources_text;
    private OrchardSparkline cpu_graph = new OrchardSparkline (1200);
    private OrchardSparkline memory_graph = new OrchardSparkline (1200);
    private Gtk.TextView inspect;
    private Gtk.Stack stack;
    private Gtk.Button toggle;
    private Gtk.Button restart;
    private uint stats_timer = 0;
    private bool stats_busy = false;
    private bool state_busy = false;
    private bool running = false;

    public PodmanDetails (Gtk.Window parent, PodmanClient api, PodmanContainer container) {
        Object (transient_for: parent, title: container.name, default_width: 720, default_height: 560);
        client = api;
        container_id = container.id;
        container_name = container.name;
        running = container.running || container.paused;

        var header = new Gtk.HeaderBar ();
        var reload = new Gtk.Button.from_icon_name ("view-refresh-symbolic") { tooltip_text = "Refresh details" };
        reload.clicked.connect (() => load.begin ());
        header.pack_end (reload);
        toggle = new Gtk.Button.with_label (running ? "Stop" : "Start");
        toggle.clicked.connect (() => state_action.begin (running ? "stop" : "start"));
        header.pack_start (toggle);
        restart = new Gtk.Button.with_label ("Restart") { sensitive = running };
        restart.clicked.connect (() => state_action.begin ("restart"));
        header.pack_start (restart);
        set_titlebar (header);

        stack = new Gtk.Stack () { vexpand = true };
        var switcher = new Gtk.StackSwitcher () { stack = stack, halign = Gtk.Align.CENTER, margin_top = 12 };

        var overview = new Gtk.Box (Gtk.Orientation.VERTICAL, 12) { margin_top = 12, margin_bottom = 20, margin_start = 24, margin_end = 24 };
        overview.append (card ("Container", out container_text));
        overview.append (card ("Network", out network_text));
        overview.append (card ("Mounts", out mounts_text));
        var resources = card ("Resources", out resources_text);
        var graphs = new Gtk.Box (Gtk.Orientation.HORIZONTAL, 12) { homogeneous = true, margin_top = 6 };
        graphs.append (graph_box ("CPU %", cpu_graph));
        graphs.append (graph_box ("Memory", memory_graph));
        resources.append (graphs);
        overview.append (resources);
        stack.add_titled (new Gtk.ScrolledWindow () { child = overview }, "overview", "Overview");

        inspect = new Gtk.TextView ();
        var inspect_box = new Gtk.Box (Gtk.Orientation.VERTICAL, 0) { margin_top = 12, margin_bottom = 20, margin_start = 24, margin_end = 24 };
        inspect_box.append (OrchardUi.console_frame (inspect));
        stack.add_titled (inspect_box, "inspect", "Inspect");

        message = new Gtk.Label ("") { xalign = 0, wrap = true, margin_start = 24, margin_end = 24, margin_bottom = 12 };
        message.add_css_class ("ml-fineprint");
        var outer = new Gtk.Box (Gtk.Orientation.VERTICAL, 8);
        outer.append (switcher); outer.append (stack); outer.append (message);
        child = outer;

        weak PodmanDetails window = this;
        stats_timer = Timeout.add_seconds (3, () => { if (window == null) return Source.REMOVE; window.refresh_stats.begin (); return Source.CONTINUE; });
        close_request.connect (() => { if (stats_timer != 0) { Source.remove (stats_timer); stats_timer = 0; } return false; });
        load.begin ();
    }

    private Gtk.Box card (string title, out Gtk.Label body) {
        var box = new Gtk.Box (Gtk.Orientation.VERTICAL, 6);
        box.add_css_class ("ml-card");
        box.add_css_class ("ml-spec");
        var heading = new Gtk.Label (title) { xalign = 0 };
        heading.add_css_class ("ml-spec-value");
        body = new Gtk.Label ("Loading…") { xalign = 0, wrap = true, selectable = true };
        box.append (heading);
        box.append (body);
        return box;
    }

    private Gtk.Box graph_box (string title, OrchardSparkline graph) {
        var box = new Gtk.Box (Gtk.Orientation.VERTICAL, 4);
        var label = new Gtk.Label (title) { xalign = 0 };
        label.add_css_class ("ml-spec-label");
        box.append (label);
        box.append (graph);
        return box;
    }

    private async void load () {
        message.label = "Loading…";
        try {
            var d = yield client.inspect_container (container_id);
            running = d.status == "running" || d.status == "paused";
            toggle.label = running ? "Stop" : "Start";
            restart.sensitive = running;
            string[] lines = {};
            lines += "Image: " + (d.image_name != "" ? d.image_name : d.image_id);
            if (d.image_name != "" && d.image_id != "") lines += "Image ID: " + short_id (d.image_id);
            lines += "ID: " + short_id (d.id);
            lines += "State: " + d.status + (d.status != "running" && d.finished_at != "" && !d.finished_at.has_prefix ("0001") ? " · exit code %lld".printf (d.exit_code) : "") + (d.pid > 0 ? " · PID %lld".printf (d.pid) : "");
            lines += "Created: " + d.created;
            if (d.started_at != "" && !d.started_at.has_prefix ("0001")) lines += "Started: " + d.started_at;
            if (d.command != "") lines += "Command: " + d.command;
            if (d.pod != "") lines += "Pod: " + d.pod;
            lines += "Restart policy: %s · restarted %lld times".printf (d.restart_policy != "" ? d.restart_policy : "no", d.restart_count);
            lines += "Environment: %d variables (see Inspect)".printf (d.env.length);
            container_text.label = string.joinv ("\n", lines);
            string[] net = {};
            net += d.ports.length == 0 ? "No published ports." : "Ports: " + string.joinv (", ", d.ports);
            net += d.networks.length == 0 ? "No network address reported (rootless user-mode networking)." : "Networks: " + string.joinv (", ", d.networks);
            network_text.label = string.joinv ("\n", net);
            mounts_text.label = d.mounts.length == 0 ? "No mounts." : string.joinv ("\n", d.mounts);
            inspect.buffer.text = d.raw;
            var limits = d.memory_limit > 0 ? "Memory limit " + format_size ((uint64) d.memory_limit) : "No memory limit";
            limits += d.nano_cpus > 0 ? " · CPU limit %.2f".printf (d.nano_cpus / 1e9) : " · no CPU limit";
            resources_text.label = limits + (running ? "\nCollecting counters…" : "\nCounters are reported only while the container runs.");
            message.label = "Reported by the local Podman.";
            yield refresh_stats ();
        } catch (Error e) { message.label = e.message; }
    }

    private async void refresh_stats () {
        if (stats_busy || !running) return;
        stats_busy = true;
        try {
            var stats = yield client.list_stats ();
            var mine = PodmanClient.stats_by_name (stats).lookup (container_name);
            if (mine == null) {
                resources_text.label = first_line (resources_text.label) + "\nNo counters reported; the container may have stopped.";
            } else {
                resources_text.label = first_line (resources_text.label) + "\nCPU %s · Memory %s (%s) · Network %s · Block I/O %s · PIDs %s".printf (
                    mine.cpu_percent, mine.mem_usage, mine.mem_percent, mine.net_io, mine.block_io, mine.pids);
                cpu_graph.record (mine.cpu);
                memory_graph.record ((double) mine.memory_bytes);
            }
        } catch (Error e) { message.label = "Counters unavailable: " + e.message; }
        stats_busy = false;
    }

    private static string first_line (string text) {
        var cut = text.index_of ("\n");
        return cut < 0 ? text : text.substring (0, cut);
    }

    private static string short_id (string id) {
        return id.length > 12 ? id.substring (0, 12) : id;
    }

    private async void state_action (string verb) {
        if (state_busy) return;
        state_busy = true;
        toggle.sensitive = false; restart.sensitive = false;
        message.label = "%s %s…".printf (verb, container_name);
        try {
            yield client.container_action (container_id, verb);
            message.label = "%s: %s complete".printf (container_name, verb);
        } catch (Error e) { message.label = e.message; }
        state_busy = false;
        toggle.sensitive = true;
        changed ();
        yield load ();
    }
}
