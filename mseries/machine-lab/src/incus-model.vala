/* Incus: containers and virtual machines, read and driven through the `incus`
 * command line (JSON output), so it works wherever the CLI works for this user. */

public class IncusInstance : Object {
    public string name { get; set; default = ""; }
    public string kind { get; set; default = "container"; }      // "container" or "virtual-machine"
    public string status { get; set; default = "Stopped"; }      // Running, Stopped, Frozen, ...
    public string arch { get; set; default = ""; }
    public string image { get; set; default = ""; }
    public string[] ipv4 = {};
    public int64 memory_usage { get; set; default = 0; }
    public int64 memory_total { get; set; default = 0; }
    public int64 disk_usage { get; set; default = 0; }
    public string limit_cpu { get; set; default = ""; }
    public string limit_memory { get; set; default = ""; }
    public int snapshots { get; set; default = 0; }
    public int64 pid { get; set; default = 0; }
    public string created { get; set; default = ""; }

    public bool is_vm { get { return kind == "virtual-machine"; } }
    public bool running { get { return status == "Running"; } }
    public bool frozen { get { return status == "Frozen"; } }
    public string kind_label { get { return is_vm ? "Virtual machine" : "Container"; } }
    public string first_ip { owned get { return ipv4.length > 0 ? ipv4[0] : ""; } }
}

public class IncusClient : Object {
    /* Parse `incus list --format json` output. Throws on malformed JSON. */
    public static GenericArray<IncusInstance> parse_list (string text) throws Error {
        var list = new GenericArray<IncusInstance> ();
        var parser = new Json.Parser ();
        parser.load_from_data (text, -1);
        var root = parser.get_root ();
        if (root == null || root.get_node_type () != Json.NodeType.ARRAY) {
            return list;
        }
        foreach (var node in root.get_array ().get_elements ()) {
            if (node.get_node_type () != Json.NodeType.OBJECT) {
                continue;
            }
            var o = node.get_object ();
            var i = new IncusInstance ();
            i.name = str (o, "name");
            i.kind = str (o, "type", "container");
            i.status = str (o, "status", "Stopped");
            i.arch = str (o, "architecture");
            i.created = str (o, "created_at");
            var cfg = obj (o, "config");
            if (cfg != null) {
                i.image = str (cfg, "image.description");
                i.limit_cpu = str (cfg, "limits.cpu");
                i.limit_memory = str (cfg, "limits.memory");
            }
            if (o.has_member ("snapshots") && !o.get_null_member ("snapshots")) {
                i.snapshots = (int) o.get_array_member ("snapshots").get_length ();
            }
            var st = obj (o, "state");
            if (st != null) {
                i.pid = st.has_member ("pid") ? st.get_int_member ("pid") : 0;
                var mem = obj (st, "memory");
                if (mem != null) {
                    i.memory_usage = mem.has_member ("usage") ? mem.get_int_member ("usage") : 0;
                    i.memory_total = mem.has_member ("total") ? mem.get_int_member ("total") : 0;
                }
                var disk = obj (st, "disk");
                if (disk != null) {
                    var root_disk = obj (disk, "root");
                    if (root_disk != null && root_disk.has_member ("usage")) {
                        i.disk_usage = root_disk.get_int_member ("usage");
                    }
                }
                var net = obj (st, "network");
                if (net != null) {
                    string[] addrs = {};
                    foreach (var dev in net.get_members ()) {
                        if (dev == "lo") {
                            continue;
                        }
                        var d = net.get_object_member (dev);
                        if (d == null || !d.has_member ("addresses")) {
                            continue;
                        }
                        foreach (var an in d.get_array_member ("addresses").get_elements ()) {
                            var a = an.get_object ();
                            if (str (a, "family") == "inet" && str (a, "scope") == "global") {
                                addrs += str (a, "address");
                            }
                        }
                    }
                    i.ipv4 = addrs;
                }
            }
            list.add (i);
        }
        return list;
    }

    private static string str (Json.Object o, string key, string fallback = "") {
        if (!o.has_member (key) || o.get_null_member (key)) {
            return fallback;
        }
        return o.get_string_member (key) ?? fallback;
    }

    private static unowned Json.Object? obj (Json.Object o, string key) {
        if (!o.has_member (key) || o.get_null_member (key)) {
            return null;
        }
        return o.get_object_member (key);
    }

    /* Instance names are DNS labels: letters, digits and hyphens, starting with a letter. */
    public static bool valid_name (string name) {
        if (name.length == 0 || name.length > 63 || !name[0].isalpha ()) {
            return false;
        }
        for (int i = 0; i < name.length; i++) {
            char c = name[i];
            if (!(c.isalnum () || c == '-') || c.isupper ()) {
                return false;
            }
        }
        return !name.has_suffix ("-");
    }

    // ---- running the CLI ----

    /* Run `incus ARGS...`; returns the exit status and the merged output. */
    public static async int run (string[] args, out string output) {
        string[] argv = { "incus" };
        foreach (var a in args) {
            argv += a;
        }
        output = "";
        try {
            var p = new Subprocess.newv (argv, SubprocessFlags.STDOUT_PIPE | SubprocessFlags.STDERR_MERGE);
            string? so;
            string? se;
            yield p.communicate_utf8_async (null, null, out so, out se);
            output = so ?? "";
            return p.get_if_exited () ? p.get_exit_status () : -1;
        } catch (Error e) {
            output = e.message;
            return -1;
        }
    }

    /* Why Incus can't be used, or null when it works. */
    public static async string? problem () {
        if (Environment.find_program_in_path ("incus") == null) {
            return "Incus is not installed. Install the incus package.";
        }
        string out_text;
        int code = yield run ({ "version" }, out out_text);
        if (code != 0) {
            return "The incus command failed: " + out_text.strip ();
        }
        if (out_text.contains ("unreachable") || out_text.contains ("Error")) {
            return "The Incus service is not reachable. Start it with: sudo systemctl start incus (and add your user to the incus-admin group).";
        }
        return null;
    }

    public static async GenericArray<IncusInstance>? list_instances (out string? error) {
        string text;
        int code = yield run ({ "list", "--format", "json" }, out text);
        error = null;
        if (code != 0) {
            error = text.strip ();
            return null;
        }
        try {
            return parse_list (text);
        } catch (Error e) {
            error = e.message;
            return null;
        }
    }
}
