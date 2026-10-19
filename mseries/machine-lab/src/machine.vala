/* Machine model, persistence, discovery of mseries-vm guests, and process control. */

public class Machine : Object {
    public string id { get; set; }
    public string name { get; set; default = "New Machine"; }
    public string kind { get; set; default = "native"; }   // "native" = ours, "managed" = mseries-vm guest
    public string vm_name { get; set; default = ""; }      // managed: directory name under ~/vms
    public int cpus { get; set; default = 4; }
    public int mem_gib { get; set; default = 6; }
    public int disk_gib { get; set; default = 64; }
    public int ssh_port { get; set; default = 2222; }
    public int color { get; set; default = 0; }
    public string? url { get; set; default = null; }       // where to get an installer
    public string? installer { get; set; default = null; }
    public string? recipe { get; set; default = null; }      // "omarchy": download and install unattended

    // Live information, not persisted.
    public bool paused { get; private set; default = false; }
    public string status_text { get; private set; default = ""; }
    public string? check_summary { get; private set; default = null; }
    public bool check_ok { get; private set; default = false; }
    public bool checking { get; private set; default = false; }

    public Subprocess? proc { get; private set; default = null; }
    public DateTime? started { get; private set; default = null; }
    public Gtk.TextBuffer log { get; private set; default = new Gtk.TextBuffer (null); }
    private bool managed_running = false;

    public signal void state_changed ();
    public signal void finished (int code);
    public signal void installer_detached ();

    public bool managed { get { return kind == "managed"; } }
    public bool running { get { return managed ? managed_running : proc != null; } }

    public string dir {
        owned get {
            if (managed) {
                return Path.build_filename (vms_dir (), vm_name);
            }
            return Path.build_filename (Environment.get_user_data_dir (), "machine-lab", id);
        }
    }

    public static string vms_dir () {
        return Environment.get_variable ("MSERIES_VM_DIR") ?? Path.build_filename (Environment.get_home_dir (), "vms");
    }

    /* An empty disk file is just a placeholder: installed means the guest wrote real data. */
    public bool installed () {
        return disk_used_bytes () >= 1073741824;
    }

    public bool is_fresh () {
        return !running && !installed ();
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

    /* Sign-in details the unattended installer saved for the guest. */
    public string? credentials () {
        try {
            string text;
            FileUtils.get_contents (Path.build_filename (dir, "credentials.txt"), out text);
            return text.strip ().replace ("\n", "  ·  ");
        } catch (Error e) {
            return null;
        }
    }

    public static string cache_dir () {
        return Path.build_filename (Environment.get_user_data_dir (), "machine-lab", "cache", "omarchy-arm64");
    }

    /* Find a helper script: installed beside the app, or in the source tree. */
    public static string? find_runtime (string installed_name, string source_name) {
        string exe_dir = "";
        try {
            exe_dir = Path.get_dirname (FileUtils.read_link ("/proc/self/exe"));
        } catch (Error e) {}
        string[] candidates = {
            Path.build_filename (Environment.get_home_dir (), ".local", "bin", installed_name),
            "/usr/bin/" + installed_name,
            Path.build_filename (exe_dir, installed_name),
            Path.build_filename (exe_dir, "..", "launcher", source_name)
        };
        foreach (var c in candidates) {
            if (FileUtils.test (c, FileTest.IS_EXECUTABLE)) {
                return c;
            }
        }
        return null;
    }

    // ---- QMP: pause and resume ----

    // QEMU serves one QMP client per socket, so a connection held open would
    // block `mseries-vm stop`, key, screenshot and friends. Control calls
    // (status, pause) therefore connect, ask and hang up. The display uses its
    // own socket (qmp-view.sock) and may stay connected; guests started before
    // that socket existed fall back to short connections on qmp.sock.
    private Mutex qmp_lock = Mutex ();
    private SocketConnection? view_conn = null;
    private DataInputStream? view_in = null;

    private void view_close () {
        try {
            if (view_conn != null) {
                view_conn.close ();
            }
        } catch (Error e) {}
        view_conn = null;
        view_in = null;
    }

    private string? qmp_exchange (SocketConnection conn, DataInputStream din, string json) throws Error {
        conn.output_stream.write ((json + "\n").data);
        string? reply = din.read_line ();
        // Events can arrive before the return value.
        while (reply != null && !reply.contains ("\"return\"") && !reply.contains ("\"error\"")) {
            reply = din.read_line ();
        }
        return reply;
    }

    private bool qmp_handshake (SocketConnection conn, DataInputStream din) throws Error {
        din.read_line ();   // greeting
        conn.output_stream.write ("{\"execute\":\"qmp_capabilities\"}\n".data);
        din.read_line ();
        return true;
    }

    /* Send one QMP command (a full JSON object) and return its reply line.
     * With view = true, use the display's dedicated socket when there is one. */
    public string? qmp_raw (string json, bool view = false) {
        qmp_lock.lock ();
        string? reply = null;
        string view_sock = Path.build_filename (dir, "qmp-view.sock");
        bool dedicated = view && FileUtils.test (view_sock, FileTest.EXISTS);
        string sock = dedicated ? view_sock : Path.build_filename (dir, "qmp.sock");
        if (FileUtils.test (sock, FileTest.EXISTS)) {
            for (int attempt = 0; attempt < 2 && reply == null; attempt++) {
                SocketConnection? conn = null;
                DataInputStream? din = null;
                try {
                    if (dedicated && view_conn != null) {
                        conn = view_conn;
                        din = view_in;
                    } else {
                        var client = new SocketClient ();
                        client.timeout = 3;
                        conn = client.connect (new UnixSocketAddress (sock));
                        din = new DataInputStream (conn.input_stream);
                        qmp_handshake (conn, din);
                        if (dedicated) {
                            view_conn = conn;
                            view_in = din;
                        }
                    }
                    reply = qmp_exchange (conn, din, json);
                } catch (Error e) {
                    reply = null;
                }
                if (reply == null && dedicated) {
                    view_close ();   // stale socket (machine restarted): reconnect once
                }
                if (!dedicated && conn != null) {
                    try { conn.close (); } catch (Error e) {}
                }
            }
        }
        qmp_lock.unlock ();
        return reply;
    }

    private string? qmp (string command) {
        return qmp_raw ("{\"execute\":\"%s\"}".printf (command));
    }

    // ---- Display: frames and input over QMP ----

    public signal void frame_ready (string path);

    private AsyncQueue<string>? input_queue = null;
    private bool frame_busy = false;

    public string frame_path () {
        var d = Path.build_filename (Environment.get_user_runtime_dir (), "machine-lab");
        DirUtils.create_with_parents (d, 0700);
        return Path.build_filename (d, id + ".ppm");
    }

    /* Ask QEMU for the current screen. At most one request is in flight. */
    public void request_frame () {
        if (!running || frame_busy) {
            return;
        }
        frame_busy = true;
        string path = frame_path ();
        new Thread<void> ("ml-frame", () => {
            var reply = qmp_raw ("{\"execute\":\"screendump\",\"arguments\":{\"filename\":\"%s\",\"format\":\"ppm\"}}".printf (path), true);
            bool ok = reply != null && reply.contains ("\"return\"");
            Idle.add (() => {
                frame_busy = false;
                if (ok) {
                    frame_ready (path);
                }
                return Source.REMOVE;
            });
        });
    }

    /* Queue an input event; a worker thread sends them in order. */
    public void send_input (string events_json) {
        if (!running) {
            return;
        }
        if (input_queue == null) {
            input_queue = new AsyncQueue<string> ();
            var q = input_queue;
            new Thread<void> ("ml-input", () => {
                while (true) {
                    string cmd = q.pop ();
                    if (cmd == "") {
                        break;
                    }
                    qmp_raw ("{\"execute\":\"input-send-event\",\"arguments\":{\"events\":%s}}".printf (cmd), true);
                }
            });
        }
        input_queue.push (events_json);
    }

    public void send_pointer (double fx, double fy) {
        int x = (int) (fx.clamp (0.0, 1.0) * 32767);
        int y = (int) (fy.clamp (0.0, 1.0) * 32767);
        send_input ("[{\"type\":\"abs\",\"data\":{\"axis\":\"x\",\"value\":%d}},{\"type\":\"abs\",\"data\":{\"axis\":\"y\",\"value\":%d}}]".printf (x, y));
    }

    public void send_button (string button, bool down) {
        send_input ("[{\"type\":\"btn\",\"data\":{\"button\":\"%s\",\"down\":%s}}]".printf (button, down ? "true" : "false"));
    }

    public void send_key (string qcode, bool down) {
        send_input ("[{\"type\":\"key\",\"data\":{\"down\":%s,\"key\":{\"type\":\"qcode\",\"data\":\"%s\"}}}]".printf (down ? "true" : "false", qcode));
    }

    public void pause () {
        if (running && qmp ("stop") != null) {
            sync_paused ();
        }
    }

    public void resume () {
        if (running && qmp ("cont") != null) {
            sync_paused ();
        }
    }

    private void sync_paused () {
        var reply = qmp ("query-status");
        bool now = reply != null && reply.contains ("\"status\": \"paused\"");
        if (reply != null && !now) {
            now = reply.contains ("\"status\":\"paused\"");
        }
        if (now != paused) {
            paused = now;
            state_changed ();
        }
    }

    // ---- Unattended Omarchy: latest-version check ----

    public async void check_latest () {
        if (recipe != "omarchy" || checking) {
            return;
        }
        string? updater = find_runtime ("machine-lab-prepare-omarchy", "prepare-latest-omarchy.py");
        if (updater == null) {
            return;
        }
        checking = true;
        check_summary = "Checking Omarchy's latest ARM64 nightly…";
        state_changed ();
        try {
            var l = new SubprocessLauncher (SubprocessFlags.STDOUT_PIPE | SubprocessFlags.STDERR_SILENCE);
            var p = l.spawnv ({ "python3", updater, "--check", dir, cache_dir () });
            var stream = new DataInputStream (p.get_stdout_pipe ());
            string? line;
            check_ok = false;
            check_summary = "Couldn't reach nightly.omarchy.org. Choose your own ISO instead.";
            while ((line = yield stream.read_line_async ()) != null) {
                var f = line.split ("\t");
                if (f[0] == "CHECK" && f.length >= 14) {
                    double size_gib = double.parse (f[4]) / 1073741824.0;
                    bool enough = f[11] == "1";
                    string problems = f[13];
                    check_ok = enough && problems == "-";
                    if (problems != "-") {
                        check_summary = "Fix first: " + problems;
                    } else if (!enough) {
                        check_summary = "Latest nightly %s · not enough free space (needs %.0f GiB free).".printf (
                            f[1], (double.parse (f[9]) / 1073741824.0));
                    } else {
                        check_summary = "Latest nightly %s · Omarchy %s · %.1f GiB download · space OK".printf (
                            f[1], f[3], size_gib);
                    }
                } else if (f[0] == "STATUS" && f.length > 1) {
                    check_summary = f[1];
                }
            }
            yield p.wait_async ();
        } catch (Error e) {
            check_summary = "Couldn't check the latest version: " + e.message;
        }
        checking = false;
        state_changed ();
    }

    // ---- Native ----

    public void start (string launcher) throws Error {
        if (running) {
            return;
        }
        var l = new SubprocessLauncher (SubprocessFlags.STDOUT_PIPE | SubprocessFlags.STDERR_MERGE);
        string[] argv;
        if (managed) {
            argv = { launcher, "start", vm_name, "--headless" };
        } else {
            l.setenv ("MACHINE_CPUS", cpus.to_string (), true);
            l.setenv ("MACHINE_MEM_GIB", mem_gib.to_string (), true);
            l.setenv ("MACHINE_DISK_GIB", disk_gib.to_string (), true);
            l.setenv ("MACHINE_SSH_PORT", ssh_port.to_string (), true);
            l.setenv ("MACHINE_NAME", name, true);
            l.setenv ("MACHINE_DISPLAY", "none", true);   // the app shows the screen itself
            if (recipe == "omarchy" && installer == null) {
                string? updater = find_runtime ("machine-lab-prepare-omarchy", "prepare-latest-omarchy.py");
                if (updater == null) {
                    throw new IOError.NOT_FOUND ("The Omarchy installer helper (machine-lab-prepare-omarchy) was not found.");
                }
                argv = { "python3", updater, launcher, dir, cache_dir () };
            } else {
                argv = { launcher, installer ?? "-", dir };
            }
        }
        var p = l.spawnv (argv);
        log.text = "";
        status_text = "";
        paused = false;
        append_log ("$ %s\n".printf (string.joinv (" ", argv)));
        read_output.begin (p);
        if (managed) {
            watch_managed_start.begin (p);
        } else {
            proc = p;
            started = new DateTime.now_local ();
            watch.begin (p);
        }
        state_changed ();
    }

    public void stop () {
        if (managed) {
            stop_managed.begin ();
        } else if (proc != null) {
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
                if (line.has_prefix ("STATUS\t")) {
                    status_text = line.substring (7);
                    append_log (status_text + "\n");
                    state_changed ();
                } else if (line.has_prefix ("CREDENTIAL\t")) {
                    append_log ("Sign-in: " + line.substring (11) + "\n");
                    state_changed ();
                } else {
                    append_log (line + "\n");
                }
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
        paused = false;
        // The installer did its job once a disk exists: next start boots the disk.
        if (installer != null && installed ()) {
            installer = null;
            installer_detached ();
        }
        state_changed ();
        finished (code);
    }

    public void delete_files () {
        foreach (var f in new string[] { "disk.qcow2", "efi-vars.fd" }) {
            FileUtils.remove (Path.build_filename (dir, f));
        }
        DirUtils.remove (dir);
    }

    // ---- Managed (mseries-vm) ----

    private async void watch_managed_start (Subprocess p) {
        try {
            yield p.wait_async ();
        } catch (Error e) {
            append_log ("[wait: %s]\n".printf (e.message));
        }
        int code = p.get_if_exited () ? p.get_exit_status () : -1;
        poll ();
        if (code != 0) {
            finished (code);
        }
    }

    private async void stop_managed () {
        string? tool = Machine.find_mseries_vm ();
        if (tool == null) {
            return;
        }
        try {
            var l = new SubprocessLauncher (SubprocessFlags.STDOUT_PIPE | SubprocessFlags.STDERR_MERGE);
            var p = l.spawnv ({ tool, "stop", vm_name });
            append_log ("\n$ mseries-vm stop %s (asks the guest to power off)\n".printf (vm_name));
            read_output.begin (p);
            yield p.wait_async ();
        } catch (Error e) {
            append_log ("[stop: %s]\n".printf (e.message));
        }
        poll ();
        finished (0);
    }

    public static string? find_mseries_vm () {
        var env = Environment.get_variable ("MSERIES_VM_TOOL");
        if (env != null && FileUtils.test (env, FileTest.IS_EXECUTABLE)) {
            return env;
        }
        string exe_dir = "";
        try {
            exe_dir = Path.get_dirname (FileUtils.read_link ("/proc/self/exe"));
        } catch (Error e) {}
        string[] candidates = {
            Path.build_filename (exe_dir, "..", "..", "vms", "mseries-vm"),
            Path.build_filename (Environment.get_home_dir (), "ElementaryOS_MSeries", "mseries", "vms", "mseries-vm")
        };
        foreach (var c in candidates) {
            if (FileUtils.test (c, FileTest.IS_EXECUTABLE)) {
                return c;
            }
        }
        return Environment.find_program_in_path ("mseries-vm");
    }

    /* Refresh run state from the guest's qemu.pid, and tail its serial log. */
    public void poll () {
        if (!managed) {
            if (running) {
                sync_paused ();
            }
            return;
        }
        bool now = false;
        DateTime? since = null;
        string pidfile = Path.build_filename (dir, "qemu.pid");
        try {
            string pid;
            FileUtils.get_contents (pidfile, out pid);
            pid = pid.strip ();
            string cmdline;
            FileUtils.get_contents ("/proc/%s/cmdline".printf (pid), out cmdline);
            now = cmdline.contains ("qemu-system");
            if (now) {
                var info = File.new_for_path (pidfile).query_info ("time::modified", FileQueryInfoFlags.NONE);
                since = info.get_modification_date_time ().to_local ();
            }
        } catch (Error e) {
            now = false;
        }
        bool changed = now != managed_running;
        managed_running = now;
        started = now ? since : null;
        if (now) {
            load_serial_tail ();
            sync_paused ();
        } else if (paused) {
            paused = false;
        }
        if (changed) {
            state_changed ();
        }
        if (changed && !now && installer != null && installed ()) {
            detach_managed_installer.begin ();
        }
    }

    /* The guest has real data on its disk: stop booting the installer ISO. */
    private async void detach_managed_installer () {
        string? tool = find_mseries_vm ();
        if (tool == null) {
            return;
        }
        try {
            var l = new SubprocessLauncher (SubprocessFlags.STDOUT_SILENCE | SubprocessFlags.STDERR_SILENCE);
            yield l.spawnv ({ tool, "set", vm_name, "ISO", "" }).wait_async ();
            yield l.spawnv ({ tool, "set", vm_name, "BOOT", "disk" }).wait_async ();
            installer = null;
            installer_detached ();
            state_changed ();
        } catch (Error e) {
            append_log ("[could not detach installer: %s]\n".printf (e.message));
        }
    }

    private void load_serial_tail () {
        try {
            var f = File.new_for_path (Path.build_filename (dir, "serial.log"));
            var stream = f.read ();
            var info = stream.query_info ("standard::size");
            int64 size = info.get_size ();
            int64 max = 12000;
            if (size > max) {
                stream.seek (size - max, SeekType.SET);
            }
            var bytes = stream.read_bytes ((size_t) int64.min (size, max));
            string text = ((string) bytes.get_data ()).make_valid ((ssize_t) bytes.length);
            try {
                text = new Regex ("\\x1b\\[[0-9;?]*[ -/]*[@-~]|\\x1b\\][^\\x07\\x1b]*(\\x07|\\x1b\\\\)|\\x1b[()][A-Z0-9]|[\\x00-\\x08\\x0b\\x0c\\x0e-\\x1f]").replace (text, -1, 0, "");
            } catch (RegexError e) {}
            log.text = text;
        } catch (Error e) {
            // no serial log yet
        }
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
                if (kf.has_key (id, "url")) {
                    m.url = kf.get_string (id, "url");
                }
                if (kf.has_key (id, "recipe")) {
                    m.recipe = kf.get_string (id, "recipe");
                }
                if (kf.has_key (id, "installer")) {
                    m.installer = kf.get_string (id, "installer");
                }
                list.add (m);
            }
        } catch (Error e) {
            // First run: no machines until the user creates one.
        }
        return list;
    }

    // Guests already set up with mseries-vm: one vm.conf per directory under ~/vms.
    public static void discover (GenericArray<Machine> list) {
        try {
            var d = Dir.open (Machine.vms_dir ());
            string? entry;
            string[] names = {};
            while ((entry = d.read_name ()) != null) {
                names += entry;
            }
            qsort_with_data<string> (names, sizeof (string), (a, b) => strcmp (a, b));
            foreach (var n in names) {
                string conf;
                string path = Path.build_filename (Machine.vms_dir (), n, "vm.conf");
                var kf = new KeyFile ();
                try {
                    FileUtils.get_contents (path, out conf);
                    kf.load_from_data ("[c]\n" + conf, -1, KeyFileFlags.NONE);
                } catch (Error e) {
                    continue;   // not a VM directory (downloads, trials, ...)
                }
                var m = new Machine ();
                m.kind = "managed";
                m.vm_name = n;
                m.id = "vm-" + n;
                string guest = kf.has_key ("c", "GUEST") ? kf.get_string ("c", "GUEST") : n;
                switch (guest) {
                    case "omarchy": m.name = "Omarchy"; m.color = 7; break;
                    case "elementary": m.name = "elementary OS"; m.color = 0; break;
                    case "windows": m.name = "Windows 11"; m.color = 3; break;
                    default: m.name = n; m.color = 1; break;
                }
                if (kf.has_key ("c", "ISO") && kf.get_string ("c", "ISO") != "") {
                    m.installer = kf.get_string ("c", "ISO");
                }
                if (kf.has_key ("c", "CPUS")) {
                    m.cpus = kf.get_integer ("c", "CPUS");
                }
                if (kf.has_key ("c", "MEMORY_MB")) {
                    m.mem_gib = int.max (1, (kf.get_integer ("c", "MEMORY_MB") + 512) / 1024);
                }
                m.disk_gib = virtual_size_gib (Path.build_filename (Machine.vms_dir (), n, "disk.qcow2"));
                list.add (m);
            }
        } catch (Error e) {
            // No ~/vms directory: nothing to import.
        }
    }

    private static int virtual_size_gib (string disk) {
        try {
            string output;
            Process.spawn_sync (null, { "qemu-img", "info", "--output=json", disk }, null,
                SpawnFlags.SEARCH_PATH | SpawnFlags.STDERR_TO_DEV_NULL, null, out output);
            Regex r = new Regex ("\\n    \"virtual-size\":\\s*(\\d+)");
            MatchInfo mi;
            if (r.match (output, 0, out mi)) {
                return (int) (int64.parse (mi.fetch (1)) / 1073741824);
            }
        } catch (Error e) {}
        return 0;
    }

    public static void save (GenericArray<Machine> list) {
        var kf = new KeyFile ();
        foreach (var m in list.data) {
            if (m.managed) {
                continue;
            }
            kf.set_string (m.id, "name", m.name);
            kf.set_integer (m.id, "cpus", m.cpus);
            kf.set_integer (m.id, "mem_gib", m.mem_gib);
            kf.set_integer (m.id, "disk_gib", m.disk_gib);
            kf.set_integer (m.id, "ssh_port", m.ssh_port);
            kf.set_integer (m.id, "color", m.color);
            if (m.url != null) {
                kf.set_string (m.id, "url", m.url);
            }
            if (m.recipe != null) {
                kf.set_string (m.id, "recipe", m.recipe);
            }
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
        string[] found = {};
        if (Environment.find_program_in_path ("qemu-system-aarch64") == null) {
            found += "QEMU is missing. Install qemu-system-arm.";
        }
        if (Environment.find_program_in_path ("qemu-img") == null) {
            found += "qemu-img is missing. Install qemu-utils.";
        }
        if (!FileUtils.test ("/usr/share/AAVMF/AAVMF_CODE.fd", FileTest.EXISTS)) {
            found += "UEFI firmware is missing. Install qemu-efi-aarch64.";
        }
        if (Posix.access ("/dev/kvm", Posix.R_OK | Posix.W_OK) != 0) {
            found += "No access to /dev/kvm. Add your user to the kvm group.";
        }
        return found;
    }

    /* Free space, in GiB, on the volume that holds machine disks. */
    public static int64 free_gib () {
        try {
            // The data folder may not exist yet: ask about the nearest folder that does.
            var dir = File.new_for_path (Environment.get_user_data_dir ());
            while (!dir.query_exists () && dir.get_parent () != null) {
                dir = dir.get_parent ();
            }
            var info = dir.query_filesystem_info ("filesystem::free");
            return (int64) (info.get_attribute_uint64 ("filesystem::free") / 1073741824);
        } catch (Error e) {
            return -1;
        }
    }
}
