public class HostCapabilities : Object {
    public uint64 available_bytes { get; private set; default = 0; }
    public bool has_render_node { get; private set; default = false; }

    public static HostCapabilities capture () {
        var snapshot = new HostCapabilities ();
        try {
            string contents;
            FileUtils.get_contents ("/proc/meminfo", out contents);
            snapshot.available_bytes = parse_mem_available (contents);
        } catch (Error e) {
            warning ("Unable to read available memory: %s", e.message);
        }

        try {
            var directory = Dir.open ("/dev/dri");
            string? entry;
            while ((entry = directory.read_name ()) != null) {
                if (entry.has_prefix ("renderD")) {
                    snapshot.has_render_node = true;
                    break;
                }
            }
        } catch (Error e) {
            // Missing DRM nodes are a valid state on systems without a GPU device.
        }
        return snapshot;
    }

    public static uint64 parse_mem_available (string contents) {
        foreach (var line in contents.split ("\n")) {
            if (!line.has_prefix ("MemAvailable:")) continue;
            var fields = line.split (" ");
            string? value = null;
            foreach (var field in fields) {
                if (field.strip () != "") {
                    if (field.has_suffix (":")) continue;
                    value = field.strip ();
                    break;
                }
            }
            if (value == null) return 0;
            uint64 kib;
            if (!uint64.try_parse (value, out kib)) return 0;
            return kib * 1024;
        }
        return 0;
    }

    public double available_gib () {
        return (double) available_bytes / (1024.0 * 1024.0 * 1024.0);
    }

    public bool desktop_reserve_met () {
        return available_bytes >= GenerationGate.DESKTOP_RESERVE_BYTES;
    }

    public string memory_summary () {
        if (available_bytes == 0) return "Available memory could not be measured.";
        return "%.1f GiB available now".printf (available_gib ());
    }

    public string accelerator_summary () {
        if (!has_render_node) return "No DRM render device detected; image support is unverified.";
        return "A render device is present; model/runtime support is unverified.";
    }
}
