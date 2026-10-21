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
