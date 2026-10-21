// Podman support for Orchard. Podman is driven through its rootless CLI with JSON output, so the
// user's own containers appear without enabling a socket service. $ORCHARD_PODMAN overrides the binary.

public class PodmanContainer : Object {
    public string id { get; set; default = ""; }
    public string name { get; set; default = ""; }
    public string image { get; set; default = ""; }
    public string state { get; set; default = ""; }
    public string status { get; set; default = ""; }
    public string ports { get; set; default = ""; }
    public string pod { get; set; default = ""; }
    public int64 created { get; set; default = 0; }
    public bool running { get { return state == "running"; } }
    public bool paused { get { return state == "paused"; } }

    public static PodmanContainer from_json (Json.Object o) {
        var c = new PodmanContainer ();
        c.id = o.get_string_member_with_default ("Id", "");
        c.name = PodmanClient.first_string (o, "Names");
        if (c.name == "") c.name = c.id.length > 12 ? c.id.substring (0, 12) : c.id;
        c.image = o.get_string_member_with_default ("Image", "");
        c.state = o.get_string_member_with_default ("State", "");
        c.status = o.get_string_member_with_default ("Status", "");
        c.pod = o.get_string_member_with_default ("PodName", "");
        c.created = o.get_int_member_with_default ("Created", 0);
        c.ports = PodmanClient.ports_text (o);
        return c;
    }
}

public class PodmanImage : Object {
    public string id { get; set; default = ""; }
    public string name { get; set; default = ""; }
    public int64 size { get; set; default = 0; }
    public int64 created { get; set; default = 0; }
    public int64 containers { get; set; default = 0; }

    public static PodmanImage from_json (Json.Object o) {
        var i = new PodmanImage ();
        i.id = o.get_string_member_with_default ("Id", "");
        var short_id = i.id.length > 12 ? i.id.substring (0, 12) : i.id;
        i.name = PodmanClient.first_string (o, "Names");
        if (i.name == "") i.name = "<untagged> " + short_id;
        i.size = o.get_int_member_with_default ("Size", 0);
        i.created = o.get_int_member_with_default ("Created", 0);
        i.containers = o.get_int_member_with_default ("Containers", 0);
        return i;
    }
}

public class PodmanVolume : Object {
    public string name { get; set; default = ""; }
    public string driver { get; set; default = ""; }
    public string mountpoint { get; set; default = ""; }

    public static PodmanVolume from_json (Json.Object o) {
        var v = new PodmanVolume ();
        v.name = o.get_string_member_with_default ("Name", "");
        v.driver = o.get_string_member_with_default ("Driver", "");
        v.mountpoint = o.get_string_member_with_default ("Mountpoint", "");
        return v;
    }
}

// One row of `podman stats --no-stream`. Podman reports human-readable strings; the numeric
// accessors parse them so graphs and sorting work without a second format.
public class PodmanStats : Object {
    public string id { get; set; default = ""; }
    public string name { get; set; default = ""; }
    public string cpu_percent { get; set; default = ""; }
    public string mem_usage { get; set; default = ""; }
    public string mem_percent { get; set; default = ""; }
    public string net_io { get; set; default = ""; }
    public string block_io { get; set; default = ""; }
    public string pids { get; set; default = ""; }
    public double cpu { get { return PodmanClient.parse_percent (cpu_percent); } }
    public int64 memory_bytes { get { return PodmanClient.parse_bytes (mem_usage); } }

    public static PodmanStats from_json (Json.Object o) {
        var s = new PodmanStats ();
        s.id = o.get_string_member_with_default ("id", "");
        s.name = o.get_string_member_with_default ("name", "");
        s.cpu_percent = o.get_string_member_with_default ("cpu_percent", "");
        s.mem_usage = o.get_string_member_with_default ("mem_usage", "");
        s.mem_percent = o.get_string_member_with_default ("mem_percent", "");
        s.net_io = o.get_string_member_with_default ("net_io", "");
        s.block_io = o.get_string_member_with_default ("block_io", "");
        s.pids = o.get_string_member_with_default ("pids", "");
        return s;
    }
}

// The parts of `podman inspect` the details window shows; `raw` keeps the full document.
public class PodmanInspect : Object {
    public string id { get; set; default = ""; }
    public string name { get; set; default = ""; }
    public string image_name { get; set; default = ""; }
    public string image_id { get; set; default = ""; }
    public string status { get; set; default = ""; }
    public string created { get; set; default = ""; }
    public string started_at { get; set; default = ""; }
    public string finished_at { get; set; default = ""; }
    public int64 exit_code { get; set; default = 0; }
    public int64 pid { get; set; default = 0; }
    public int64 restart_count { get; set; default = 0; }
    public string restart_policy { get; set; default = ""; }
    public string command { get; set; default = ""; }
    public string pod { get; set; default = ""; }
    public int64 memory_limit { get; set; default = 0; }
    public int64 nano_cpus { get; set; default = 0; }
    public string[] mounts { get; set; default = {}; }
    public string[] ports { get; set; default = {}; }
    public string[] networks { get; set; default = {}; }
    public string[] env { get; set; default = {}; }
    public string raw { get; set; default = ""; }

    public static PodmanInspect from_json (Json.Object o) {
        var d = new PodmanInspect ();
        d.id = o.get_string_member_with_default ("Id", "");
        d.name = o.get_string_member_with_default ("Name", "");
        d.image_name = o.get_string_member_with_default ("ImageName", "");
        d.image_id = o.get_string_member_with_default ("Image", "");
        d.created = o.get_string_member_with_default ("Created", "");
        d.restart_count = o.get_int_member_with_default ("RestartCount", 0);
        d.pod = o.get_string_member_with_default ("Pod", "");
        var state = PodmanClient.object_member (o, "State");
        if (state != null) {
            d.status = state.get_string_member_with_default ("Status", "");
            d.started_at = state.get_string_member_with_default ("StartedAt", "");
            d.finished_at = state.get_string_member_with_default ("FinishedAt", "");
            d.exit_code = state.get_int_member_with_default ("ExitCode", 0);
            d.pid = state.get_int_member_with_default ("Pid", 0);
        }
        var config = PodmanClient.object_member (o, "Config");
        if (config != null) {
            string[] argv = {};
            foreach (var part in PodmanClient.strings (config, "Entrypoint")) argv += part;
            foreach (var part in PodmanClient.strings (config, "Cmd")) argv += part;
            d.command = string.joinv (" ", argv);
            d.env = PodmanClient.strings (config, "Env");
        }
        var host = PodmanClient.object_member (o, "HostConfig");
        if (host != null) {
            d.memory_limit = host.get_int_member_with_default ("Memory", 0);
            d.nano_cpus = host.get_int_member_with_default ("NanoCpus", 0);
            var policy = PodmanClient.object_member (host, "RestartPolicy");
            if (policy != null) d.restart_policy = policy.get_string_member_with_default ("Name", "");
        }
        string[] mounts = {};
        if (o.has_member ("Mounts") && o.get_member ("Mounts").get_node_type () == Json.NodeType.ARRAY) {
            foreach (var n in o.get_array_member ("Mounts").get_elements ()) {
                if (n.get_node_type () != Json.NodeType.OBJECT) continue;
                var m = n.get_object ();
                var kind = m.get_string_member_with_default ("Type", "");
                var source = kind == "volume" ? m.get_string_member_with_default ("Name", "") : m.get_string_member_with_default ("Source", "");
                var rw = m.has_member ("RW") && m.get_member ("RW").get_node_type () == Json.NodeType.VALUE && m.get_boolean_member ("RW");
                mounts += "%s%s → %s (%s)".printf (kind != "" ? kind + " " : "", source, m.get_string_member_with_default ("Destination", ""), rw ? "rw" : "ro");
            }
        }
        d.mounts = mounts;
        var network = PodmanClient.object_member (o, "NetworkSettings");
        if (network != null) {
            string[] ports = {};
            var published = PodmanClient.object_member (network, "Ports");
            if (published != null) {
                foreach (var member in published.get_members ()) {
                    if (published.get_member (member).get_node_type () != Json.NodeType.ARRAY) continue;
                    foreach (var n in published.get_array_member (member).get_elements ()) {
                        if (n.get_node_type () != Json.NodeType.OBJECT) continue;
                        var b = n.get_object ();
                        var ip = b.get_string_member_with_default ("HostIp", "");
                        ports += "%s%s → %s".printf (ip != "" ? ip + ":" : "", b.get_string_member_with_default ("HostPort", ""), member);
                    }
                }
            }
            d.ports = ports;
            string[] networks = {};
            var ip = network.get_string_member_with_default ("IPAddress", "");
            var nets = PodmanClient.object_member (network, "Networks");
            if (nets != null) {
                foreach (var member in nets.get_members ()) {
                    var entry = PodmanClient.object_member (nets, member);
                    var address = entry != null ? entry.get_string_member_with_default ("IPAddress", "") : "";
                    networks += address != "" ? "%s · %s".printf (member, address) : member;
                }
            }
            if (networks.length == 0 && ip != "") networks += ip;
            d.networks = networks;
        }
        return d;
    }
}

public class PodmanClient : Object {
    private string binary;
    private uint timeout_seconds;

    public PodmanClient (uint timeout_seconds = 20) {
        binary = Environment.get_variable ("ORCHARD_PODMAN") ?? "podman";
        this.timeout_seconds = timeout_seconds;
    }

    public bool installed () {
        return Path.is_absolute (binary) ? FileUtils.test (binary, FileTest.IS_EXECUTABLE) : Environment.find_program_in_path (binary) != null;
    }

    // Runs `podman args…`, returning stdout. Kills the process when it outlives the timeout.
    public async string run (string[] args, uint timeout_override = 0) throws Error {
        string[] argv = { binary };
        foreach (var a in args) argv += a;
        Subprocess process;
        try {
            process = new Subprocess.newv (argv, SubprocessFlags.STDOUT_PIPE | SubprocessFlags.STDERR_PIPE);
        } catch (Error e) {
            throw new IOError.NOT_FOUND ("Podman is not available: %s".printf (e.message));
        }
        bool timed_out = false;
        var wait = timeout_override == 0 ? timeout_seconds : timeout_override;
        var timer = Timeout.add_seconds (wait, () => { timed_out = true; process.force_exit (); return Source.REMOVE; });
        string? out_text = null, err_text = null;
        try {
            yield process.communicate_utf8_async (null, null, out out_text, out err_text);
        } finally {
            Source.remove (timer);
        }
        if (timed_out) throw new IOError.TIMED_OUT ("podman %s timed out after %us".printf (args.length > 0 ? args[0] : "", wait));
        if (!process.get_successful ()) {
            var message = (err_text ?? "").strip ();
            if (message == "") message = (out_text ?? "").strip ();
            throw new IOError.FAILED (message == "" ? "podman %s failed".printf (args.length > 0 ? args[0] : "") : message);
        }
        return out_text ?? "";
    }

    public async PodmanContainer[] list_containers () throws Error {
        return parse_containers (yield run ({ "ps", "-a", "--format", "json" }));
    }

    public async PodmanImage[] list_images () throws Error {
        return parse_images (yield run ({ "images", "--format", "json" }));
    }

    public async PodmanVolume[] list_volumes () throws Error {
        return parse_volumes (yield run ({ "volume", "ls", "--format", "json" }));
    }

    // Live counters for running containers; stopped containers are not reported.
    public async PodmanStats[] list_stats () throws Error {
        return parse_stats (yield run ({ "stats", "--no-stream", "--format", "json" }));
    }

    public async PodmanInspect inspect_container (string id) throws Error {
        return parse_inspect (yield run ({ "inspect", "--type", "container", "--format", "json", id }));
    }

    // verb: start | stop | restart | pause | unpause
    public async void container_action (string id, string verb) throws Error {
        switch (verb) {
        case "start": case "stop": case "restart": case "pause": case "unpause": break;
        default: throw new IOError.INVALID_ARGUMENT ("Unknown container action: " + verb);
        }
        yield run ({ verb, id }, 60);
    }

    // Never forced: a running container must be stopped first so work is not lost by accident.
    public async void remove_container (string id) throws Error { yield run ({ "rm", id }, 60); }
    public async void remove_image (string id) throws Error { yield run ({ "rmi", id }, 60); }
    public async void remove_volume (string name) throws Error { yield run ({ "volume", "rm", name }, 60); }

    // ------------------------------------------------------------ parsing (display-free, covered by tests)

    private static Json.Array parse_array (string text) throws Error {
        var trimmed = text.strip ();
        // Older Podman prints `null` for an empty list.
        if (trimmed == "" || trimmed == "null") return new Json.Array ();
        var parser = new Json.Parser ();
        parser.load_from_data (trimmed);
        if (parser.get_root ().get_node_type () != Json.NodeType.ARRAY) throw new IOError.INVALID_DATA ("Podman returned an unexpected response.");
        return parser.get_root ().get_array ();
    }

    public static PodmanContainer[] parse_containers (string text) throws Error {
        var out = new PodmanContainer[0];
        foreach (var n in parse_array (text).get_elements ()) {
            if (n.get_node_type () == Json.NodeType.OBJECT) out += PodmanContainer.from_json (n.get_object ());
        }
        return out;
    }

    public static PodmanImage[] parse_images (string text) throws Error {
        var out = new PodmanImage[0];
        foreach (var n in parse_array (text).get_elements ()) {
            if (n.get_node_type () == Json.NodeType.OBJECT) out += PodmanImage.from_json (n.get_object ());
        }
        return out;
    }

    public static PodmanVolume[] parse_volumes (string text) throws Error {
        var out = new PodmanVolume[0];
        foreach (var n in parse_array (text).get_elements ()) {
            if (n.get_node_type () == Json.NodeType.OBJECT) out += PodmanVolume.from_json (n.get_object ());
        }
        return out;
    }

    public static PodmanStats[] parse_stats (string text) throws Error {
        var out = new PodmanStats[0];
        foreach (var n in parse_array (text).get_elements ()) {
            if (n.get_node_type () == Json.NodeType.OBJECT) out += PodmanStats.from_json (n.get_object ());
        }
        return out;
    }

    // `podman inspect` returns a one-element array; the full document is kept pretty-printed.
    public static PodmanInspect parse_inspect (string text) throws Error {
        var array = parse_array (text);
        if (array.get_length () == 0 || array.get_element (0).get_node_type () != Json.NodeType.OBJECT) throw new IOError.NOT_FOUND ("Podman did not return this container.");
        var details = PodmanInspect.from_json (array.get_object_element (0));
        var generator = new Json.Generator () { pretty = true, indent = 2 };
        generator.set_root (array.get_element (0));
        details.raw = generator.to_data (null);
        return details;
    }

    // Stats keyed by container name; the stats id is a short prefix of the container id.
    public static HashTable<string, PodmanStats> stats_by_name (PodmanStats[] stats) {
        var table = new HashTable<string, PodmanStats> (str_hash, str_equal);
        foreach (var s in stats) table.insert (s.name, s);
        return table;
    }

    // "18.22%" → 18.22; anything unparsable → 0.
    public static double parse_percent (string text) {
        var trimmed = text.strip ();
        if (trimmed.has_suffix ("%")) trimmed = trimmed.substring (0, trimmed.length - 1);
        return double.parse (trimmed.strip ());
    }

    // "76.94MB / 33.22GB" → 76940000; the first value only. Podman uses decimal units.
    public static int64 parse_bytes (string text) {
        var parts = text.split ("/");
        if (parts.length == 0) return 0;
        var first = parts[0].strip ().down ();
        if (first == "") return 0;
        int cut = 0;
        while (cut < first.length && (first[cut].isdigit () || first[cut] == '.')) cut++;
        var number = double.parse (first.substring (0, cut));
        var unit = first.substring (cut).strip ();
        double scale = 1;
        switch (unit) {
        case "kb": case "k": scale = 1e3; break;
        case "mb": case "m": scale = 1e6; break;
        case "gb": case "g": scale = 1e9; break;
        case "tb": case "t": scale = 1e12; break;
        case "kib": scale = 1024.0; break;
        case "mib": scale = 1024.0 * 1024; break;
        case "gib": scale = 1024.0 * 1024 * 1024; break;
        default: scale = 1; break;
        }
        return (int64) (number * scale);
    }

    public static Json.Object? object_member (Json.Object o, string member) {
        if (!o.has_member (member) || o.get_member (member).get_node_type () != Json.NodeType.OBJECT) return null;
        return o.get_object_member (member);
    }

    // All strings of an array member that may be missing or null.
    public static string[] strings (Json.Object o, string member) {
        string[] out = {};
        if (!o.has_member (member) || o.get_member (member).get_node_type () != Json.NodeType.ARRAY) return out;
        foreach (var n in o.get_array_member (member).get_elements ()) {
            if (n.get_node_type () == Json.NodeType.VALUE && n.get_value_type () == typeof (string)) out += n.get_string ();
        }
        return out;
    }

    // First string of an array member that may be missing, null or empty.
    public static string first_string (Json.Object o, string member) {
        if (!o.has_member (member) || o.get_member (member).get_node_type () != Json.NodeType.ARRAY) return "";
        var arr = o.get_array_member (member);
        if (arr.get_length () == 0 || arr.get_element (0).get_node_type () != Json.NodeType.VALUE) return "";
        return arr.get_string_element (0);
    }

    // "127.0.0.1:3291→3000/tcp, 6969→6969/udp"; empty when nothing is published.
    public static string ports_text (Json.Object o) {
        if (!o.has_member ("Ports") || o.get_member ("Ports").get_node_type () != Json.NodeType.ARRAY) return "";
        string[] parts = {};
        foreach (var n in o.get_array_member ("Ports").get_elements ()) {
            if (n.get_node_type () != Json.NodeType.OBJECT) continue;
            var p = n.get_object ();
            var host = p.get_string_member_with_default ("host_ip", "");
            var host_port = p.get_int_member_with_default ("host_port", 0);
            var container_port = p.get_int_member_with_default ("container_port", 0);
            var range = p.get_int_member_with_default ("range", 1);
            var proto = p.get_string_member_with_default ("protocol", "tcp");
            var left = (host != "" ? host + ":" : "") + (range > 1 ? "%lld-%lld".printf (host_port, host_port + range - 1) : "%lld".printf (host_port));
            var right = range > 1 ? "%lld-%lld".printf (container_port, container_port + range - 1) : "%lld".printf (container_port);
            parts += "%s→%s/%s".printf (left, right, proto);
        }
        return string.joinv (", ", parts);
    }

    // Running containers first, then by name.
    public static PodmanContainer[] sorted_containers (PodmanContainer[] input) {
        var list = new GenericArray<PodmanContainer> ();
        foreach (var c in input) list.add (c);
        list.sort (compare_containers);
        var out = new PodmanContainer[0];
        foreach (var c in list.data) out += c;
        return out;
    }

    // Sort order shared by the page and the tests: running first, then by name.
    public static int compare_containers (PodmanContainer a, PodmanContainer b) {
        if (a.running != b.running) return a.running ? -1 : 1;
        return a.name.collate (b.name);
    }
}
