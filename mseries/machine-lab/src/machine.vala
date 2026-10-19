/* Machine model, persistence and QEMU process control. */

public class Machine : Object {
    public string id { get; set; }
    public string name { get; set; default = "New Machine"; }
    public int cpus { get; set; default = 4; }
    public int mem_gib { get; set; default = 6; }
    public int disk_gib { get; set; default = 64; }
    public int ssh_port { get; set; default = 2222; }
    public int color { get; set; default = 0; }
    public string? installer { get; set; default = null; }

    public Subprocess? proc { get; private set; default = null; }
    public DateTime? started { get; private set; default = null; }
    public Gtk.TextBuffer log { get; private set; default = new Gtk.TextBuffer (null); }

    public signal void state_changed ();
    public signal void finished (int code);

    public bool running { get { return proc != null; } }

    public string dir {
        owned get {
            return Path.build_filename (Environment.get_user_data_dir (), "machine-lab", id);
        }
    }

    public bool has_disk () {
        return FileUtils.test (Path.build_filename (dir, "disk.qcow2"), FileTest.EXISTS);
    }

    public int64 disk_used_bytes () {
        try {
            var info = File.new_for_path (Path.build_filename (dir, "disk.qcow2"))
                .query_info ("standard::allocated-size", FileQueryInfoFlags.NONE);
            return (int64) info.get_attribute_uint64 ("standard::allocated-size");
        } catch (Error e) {
            return 0;
        }
    }

    public void start (string launcher) throws Error {
        if (running) {
            return;
        }
        var l = new SubprocessLauncher (SubprocessFlags.STDOUT_PIPE | SubprocessFlags.STDERR_MERGE);
        l.setenv ("MACHINE_CPUS", cpus.to_string (), true);
        l.setenv ("MACHINE_MEM_GIB", mem_gib.to_string (), true);
        l.setenv ("MACHINE_DISK_GIB", disk_gib.to_string (), true);
        l.setenv ("MACHINE_SSH_PORT", ssh_port.to_string (), true);
        l.setenv ("MACHINE_NAME", name, true);
        string[] argv = { launcher, installer ?? "-", dir };
        proc = l.spawnv (argv);
        started = new DateTime.now_local ();
        log.text = "";
        append_log ("$ %s\n".printf (string.joinv (" ", argv)));
        read_output.begin (proc);
        watch.begin (proc);
        state_changed ();
    }

    public void stop () {
        if (proc != null) {
            proc.force_exit ();
        }
    }

    private void append_log (string text) {
        Gtk.TextIter end;
        log.get_end_iter (out end);
        log.insert (ref end, text, -1);
    }

    private async void read_output (Subprocess p) {
        var stream = new DataInputStream (p.get_stdout_pipe ());
        try {
            string? line;
            while ((line = yield stream.read_line_async ()) != null) {
                append_log (line + "\n");
            }
        } catch (Error e) {
            append_log ("[log: %s]\n".printf (e.message));
        }
    }

    private async void watch (Subprocess p) {
        try {
            yield p.wait_async ();
        } catch (Error e) {
            append_log ("[wait: %s]\n".printf (e.message));
        }
        int code = p.get_if_exited () ? p.get_exit_status () : -1;
        append_log ("\n[machine exited with status %d]\n".printf (code));
        proc = null;
        started = null;
        state_changed ();
        finished (code);
    }

    public void delete_files () {
        foreach (var f in new string[] { "disk.qcow2", "efi-vars.fd" }) {
            FileUtils.remove (Path.build_filename (dir, f));
        }
        DirUtils.remove (dir);
    }
}

public class MachineStore : Object {
    public static string config_path () {
        return Path.build_filename (Environment.get_user_config_dir (), "machine-lab", "machines.ini");
    }

    public static GenericArray<Machine> load () {
        var list = new GenericArray<Machine> ();
        var kf = new KeyFile ();
        try {
            kf.load_from_file (config_path (), KeyFileFlags.NONE);
            foreach (var id in kf.get_groups ()) {
                var m = new Machine ();
                m.id = id;
                m.name = kf.get_string (id, "name");
                m.cpus = kf.get_integer (id, "cpus");
                m.mem_gib = kf.get_integer (id, "mem_gib");
                m.disk_gib = kf.get_integer (id, "disk_gib");
                m.ssh_port = kf.get_integer (id, "ssh_port");
                if (kf.has_key (id, "color")) {
                    m.color = kf.get_integer (id, "color");
                }
                if (kf.has_key (id, "installer")) {
                    m.installer = kf.get_string (id, "installer");
                }
                list.add (m);
            }
        } catch (Error e) {
            // First run, or unreadable file: start from the default profile below.
        }
        if (list.length == 0 && !FileUtils.test (config_path (), FileTest.EXISTS)) {
            var m = new Machine ();
            m.id = "omarchy-arm64"; // keeps the disk made by the earlier prototype
            m.name = "Omarchy";
            list.add (m);
        }
        return list;
    }

    public static void save (GenericArray<Machine> list) {
        var kf = new KeyFile ();
        foreach (var m in list.data) {
            kf.set_string (m.id, "name", m.name);
            kf.set_integer (m.id, "cpus", m.cpus);
            kf.set_integer (m.id, "mem_gib", m.mem_gib);
            kf.set_integer (m.id, "disk_gib", m.disk_gib);
            kf.set_integer (m.id, "ssh_port", m.ssh_port);
            kf.set_integer (m.id, "color", m.color);
            if (m.installer != null) {
                kf.set_string (m.id, "installer", m.installer);
            }
        }
        try {
            DirUtils.create_with_parents (Path.get_dirname (config_path ()), 0755);
            kf.save_to_file (config_path ());
        } catch (Error e) {
            warning ("Could not save machines: %s", e.message);
        }
    }
}

/* Checks the host has what the launcher needs. */
public class Readiness : Object {
    public static string[] problems () {
        string[] out = {};
        if (Environment.find_program_in_path ("qemu-system-aarch64") == null) {
            out += "QEMU is missing. Install qemu-system-arm.";
        }
        if (Environment.find_program_in_path ("qemu-img") == null) {
            out += "qemu-img is missing. Install qemu-utils.";
        }
        if (!FileUtils.test ("/usr/share/AAVMF/AAVMF_CODE.fd", FileTest.EXISTS)) {
            out += "UEFI firmware is missing. Install qemu-efi-aarch64.";
        }
        if (Posix.access ("/dev/kvm", Posix.R_OK | Posix.W_OK) != 0) {
            out += "No access to /dev/kvm. Add your user to the kvm group.";
        }
        return out;
    }
}
