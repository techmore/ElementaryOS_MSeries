public class Instance : Object {
    public string name { get; set; }
    public string kind { get; set; }     // "container" or "virtual-machine"
    public string status { get; set; }   // "Running", "Stopped", "Frozen", ...
    public string ipv4 { get; set; default = ""; }
    public string image { get; set; default = ""; }
    public string arch { get; set; default = ""; }
    public string created { get; set; default = ""; }
    public string limit_cpu { get; set; default = ""; }
    public string limit_memory { get; set; default = ""; }
    public bool ephemeral { get; set; default = false; }
    public int64 pid { get; set; default = 0; }
    public int64 memory_bytes { get; set; default = 0; }
    public HashTable<string, string> labels = new HashTable<string, string> (str_hash, str_equal);
    public bool cpu_available { get; set; default = false; }
    public bool memory_available { get; set; default = false; }
    public bool network_available { get; set; default = false; }
    public bool disk_available { get; set; default = false; }
    public int64 cpu_ns { get; set; default = 0; }
    public int64 network_bytes { get; set; default = 0; }
    public int64 disk_bytes { get; set; default = 0; }
    public int snapshots { get; set; default = 0; }

    public bool running { get { return status == "Running"; } }
    public bool frozen { get { return status == "Frozen"; } }
    public bool is_vm { get { return kind == "virtual-machine"; } }
    public string kind_label { get { return is_vm ? "Virtual machine" : "Container"; } }

    public static Instance from_json (Json.Object o) {
        var i = new Instance ();
        i.name = o.get_string_member ("name");
        i.kind = o.get_string_member_with_default ("type", "container");
        i.status = o.get_string_member_with_default ("status", "Unknown");
        i.arch = o.get_string_member_with_default ("architecture", "");
        i.created = o.get_string_member_with_default ("created_at", "");
        i.ephemeral = o.get_boolean_member_with_default ("ephemeral", false);
        if (object_member (o, "config")) {
            var cfg = o.get_object_member ("config");
            i.image = cfg.get_string_member_with_default ("image.description", "");
            i.limit_cpu = cfg.get_string_member_with_default ("limits.cpu", "");
            i.limit_memory = cfg.get_string_member_with_default ("limits.memory", "");
            foreach (var key in cfg.get_members ()) if (key.has_prefix ("user.")) i.labels.insert (key, cfg.get_string_member (key));
        }
        if (o.has_member ("snapshots") && o.get_member ("snapshots").get_node_type () == Json.NodeType.ARRAY) {
            i.snapshots = (int) o.get_array_member ("snapshots").get_length ();
        }
        if (object_member (o, "state")) {
            var st = o.get_object_member ("state");
            i.pid = st.get_int_member_with_default ("pid", 0);
            if (object_member (st, "cpu") && st.get_object_member ("cpu").has_member ("usage")) { i.cpu_ns = st.get_object_member ("cpu").get_int_member ("usage"); i.cpu_available = true; }
            if (object_member (st, "disk")) {
                var disks = st.get_object_member ("disk");
                if (object_member (disks, "root") && disks.get_object_member ("root").has_member ("usage")) { i.disk_bytes = int64.max (0, disks.get_object_member ("root").get_int_member ("usage")); i.disk_available = true; }
            }
            if (object_member (st, "memory")) {
                i.memory_bytes = int64.max (0, st.get_object_member ("memory").get_int_member_with_default ("usage", 0));
                i.memory_available = st.get_object_member ("memory").has_member ("usage");
            }
            if (object_member (st, "network")) {
                st.get_object_member ("network").foreach_member ((obj, nic, node) => {
                    if (nic == "lo" || node.get_node_type () != Json.NodeType.OBJECT) return;
                    if (object_member (node.get_object (), "counters")) {
                        var counters = node.get_object ().get_object_member ("counters");
                        i.network_available = i.network_available || counters.has_member ("bytes_received") && counters.has_member ("bytes_sent");
                        i.network_bytes += counters.get_int_member_with_default ("bytes_received", 0) + counters.get_int_member_with_default ("bytes_sent", 0);
                    }
                    if (i.ipv4 != "") return;
                    if (!node.get_object ().has_member ("addresses") || node.get_object ().get_member ("addresses").get_node_type () != Json.NodeType.ARRAY) return;
                    var addrs = node.get_object ().get_array_member ("addresses");
                    foreach (var a in addrs.get_elements ()) {
                        if (a.get_node_type () != Json.NodeType.OBJECT) continue;
                        var ao = a.get_object ();
                        if (ao.get_string_member_with_default ("family", "") == "inet" && ao.get_string_member_with_default ("scope", "") == "global") {
                            i.ipv4 = ao.get_string_member ("address");
                            break;
                        }
                    }
                });
            }
        }
        return i;
    }
    private static bool object_member (Json.Object object, string key) { return object.has_member (key) && object.get_member (key).get_node_type () == Json.NodeType.OBJECT; }
}
