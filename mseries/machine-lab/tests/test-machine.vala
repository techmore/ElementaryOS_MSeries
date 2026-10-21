/* Logic tests for Machine Lab: persistence, mseries-vm discovery, QMP transport. */

string tmp_dir;

void write_file (string path, string text) {
    DirUtils.create_with_parents (Path.get_dirname (path), 0755);
    try {
        FileUtils.set_contents (path, text);
    } catch (Error e) {
        error ("write %s: %s", path, e.message);
    }
}

void test_store_round_trip () {
    var list = new GenericArray<Machine> ();
    var m = new Machine ();
    m.id = "machine-test1";
    m.name = "Test Box";
    m.cpus = 3;
    m.mem_gib = 5;
    m.disk_gib = 20;
    m.ssh_port = 2230;
    m.color = 6;
    m.installer = "/tmp/x.iso";
    m.recipe = "omarchy";
    m.clipboard = true;
    m.arch = "x86_64";
    list.add (m);
    var managed = new Machine ();      // managed guests are rediscovered, never saved
    managed.id = "vm-omarchy";
    managed.kind = "managed";
    managed.vm_name = "omarchy";
    list.add (managed);
    MachineStore.save (list);

    var back = MachineStore.load ();
    assert_cmpint (back.length, CompareOperator.EQ, 1);
    assert_cmpstr (back[0].name, CompareOperator.EQ, "Test Box");
    assert_cmpint (back[0].cpus, CompareOperator.EQ, 3);
    assert_cmpint (back[0].mem_gib, CompareOperator.EQ, 5);
    assert_cmpint (back[0].disk_gib, CompareOperator.EQ, 20);
    assert_cmpint (back[0].ssh_port, CompareOperator.EQ, 2230);
    assert_cmpint (back[0].color, CompareOperator.EQ, 6);
    assert_cmpstr (back[0].installer, CompareOperator.EQ, "/tmp/x.iso");
    assert_cmpstr (back[0].recipe, CompareOperator.EQ, "omarchy");
    assert_true (back[0].clipboard);
    assert_cmpstr (back[0].arch, CompareOperator.EQ, "x86_64");
    assert_true (back[0].emulated);
    assert_cmpstr (back[0].arch_label, CompareOperator.EQ, "x86-64");
}

void test_discovery () {
    var vms = Path.build_filename (tmp_dir, "vms");
    write_file (Path.build_filename (vms, "omarchy", "vm.conf"),
        "# comment\nGUEST=omarchy\nCPUS=4\nMEMORY_MB=4096\nISO=\nBOOT=disk\nCLIPBOARD=on\n");
    write_file (Path.build_filename (vms, "elementary", "vm.conf"),
        "GUEST=elementary\nCPUS=2\nMEMORY_MB=3000\nISO=/x/y/elementaryos.iso\n");
    DirUtils.create_with_parents (Path.build_filename (vms, "downloads"), 0755);   // not a VM
    Environment.set_variable ("MSERIES_VM_DIR", vms, true);

    var list = new GenericArray<Machine> ();
    MachineStore.discover (list);
    assert_cmpint (list.length, CompareOperator.EQ, 2);   // downloads/ is ignored

    Machine? omarchy = null, elem = null;
    foreach (var m in list.data) {
        if (m.vm_name == "omarchy") omarchy = m;
        if (m.vm_name == "elementary") elem = m;
    }
    assert_nonnull (omarchy);
    assert_nonnull (elem);
    assert_true (omarchy.managed);
    assert_cmpstr (omarchy.name, CompareOperator.EQ, "Omarchy");
    assert_cmpint (omarchy.cpus, CompareOperator.EQ, 4);
    assert_cmpint (omarchy.mem_gib, CompareOperator.EQ, 4);
    assert_true (omarchy.clipboard);
    assert_null (omarchy.installer);
    assert_cmpint (elem.mem_gib, CompareOperator.EQ, 3);              // 3000 MiB rounds to 3 GiB
    assert_cmpstr (elem.installer, CompareOperator.EQ, "/x/y/elementary.iso".replace ("elementary.iso", "elementaryos.iso"));
    assert_true (omarchy.is_fresh ());                                // no real disk yet
    assert_false (omarchy.installed ());
}

void test_installed_needs_real_data () {
    var m = new Machine ();
    m.id = "machine-disk";
    assert_false (m.installed ());
    write_file (Path.build_filename (m.dir, "disk.qcow2"), "tiny");   // a placeholder is not an install
    assert_true (m.has_disk ());
    assert_false (m.installed ());
    assert_true (m.is_fresh ());
}

void test_free_space () {
    assert_true (Readiness.free_gib () >= 0);
}

void test_readiness_is_per_arch () {
    // The emulated x86-64 check never asks for KVM, and each architecture names its own emulator.
    foreach (var line in Readiness.problems ("x86_64")) {
        assert_false (line.contains ("/dev/kvm"));
    }
    foreach (var line in Readiness.problems ("aarch64")) {
        assert_false (line.contains ("qemu-system-x86"));
    }
}

void test_mask_is_page_level () {
    // masking lives in MachinePage; here we just make sure the credentials file is read and trimmed
    var m = new Machine ();
    m.id = "machine-creds";
    write_file (Path.build_filename (m.dir, "credentials.txt"), "Username: a\nPassword: b\n");
    assert_cmpstr (m.credentials (), CompareOperator.EQ, "Username: a  ·  Password: b");
}

void stop_fake_qmp (Subprocess peer) {
    // force_exit alone can race the test process exiting: the worker may not
    // deliver the signal before main returns. Reap our peer and retain errors
    // on private pipes instead of letting it hold Meson's output pipes open.
    peer.force_exit ();
    try {
        string output, diagnostic;
        peer.communicate_utf8 (null, null, out output, out diagnostic);
        if (output != "") Test.message ("Fake QMP output: %s", output);
        if (diagnostic != "") Test.message ("Fake QMP diagnostic: %s", diagnostic);
        assert_true (peer.get_if_signaled ());
    } catch (Error e) {
        error ("reap fake QMP: %s", e.message);
    }
}

void test_qmp_transport () {
    var m = new Machine ();
    m.id = "machine-qmp";
    var dir = m.dir;
    DirUtils.create_with_parents (dir, 0755);
    var counter_ctl = Path.build_filename (tmp_dir, "ctl.count");
    var counter_view = Path.build_filename (tmp_dir, "view.count");
    string[] a = { "python3", "-I", Environment.get_variable ("FAKE_QMP"), Path.build_filename (dir, "qmp.sock"), counter_ctl };
    string[] b = { "python3", "-I", Environment.get_variable ("FAKE_QMP"), Path.build_filename (dir, "qmp-view.sock"), counter_view };
    Subprocess ctl, view;
    try {
        ctl = new Subprocess.newv (a, SubprocessFlags.STDOUT_PIPE | SubprocessFlags.STDERR_PIPE);
        view = new Subprocess.newv (b, SubprocessFlags.STDOUT_PIPE | SubprocessFlags.STDERR_PIPE);
    } catch (Error e) {
        error ("%s", e.message);
    }
    for (int i = 0; i < 100 && !(FileUtils.test (Path.build_filename (dir, "qmp.sock"), FileTest.EXISTS)
                                  && FileUtils.test (Path.build_filename (dir, "qmp-view.sock"), FileTest.EXISTS)); i++) {
        Thread.usleep (50000);
    }

    // Control calls hang up after each command (so mseries-vm can connect between them) ...
    var r1 = m.qmp_raw ("{\"execute\":\"query-status\"}");
    var r2 = m.qmp_raw ("{\"execute\":\"query-status\"}");
    assert_nonnull (r1);
    assert_true (r1.contains ("paused"));         // the RESUME event before it was skipped
    assert_nonnull (r2);
    string c;
    try { FileUtils.get_contents (counter_ctl, out c); } catch (Error e) { c = ""; }
    assert_cmpstr (c, CompareOperator.EQ, "2");

    // ... while the display keeps one connection on its own socket.
    m.qmp_raw ("{\"execute\":\"screendump\"}", true);
    m.qmp_raw ("{\"execute\":\"screendump\"}", true);
    m.qmp_raw ("{\"execute\":\"screendump\"}", true);
    try { FileUtils.get_contents (counter_view, out c); } catch (Error e) { c = ""; }
    assert_cmpstr (c, CompareOperator.EQ, "1");

    stop_fake_qmp (ctl);
    stop_fake_qmp (view);
}

const string INCUS_FIXTURE = """[{"architecture":"aarch64","config":{"image.description":"Alpine edge arm64","limits.cpu":"2","limits.memory":"1GiB"},"created_at":"2026-10-15T18:15:56Z","name":"orchard-test","status":"Running","type":"container","state":{"pid":4242,"memory":{"usage":6864896,"total":32401488000},"disk":{"root":{"usage":3145728}},"network":{"eth0":{"addresses":[{"family":"inet","address":"10.169.229.233","netmask":"24","scope":"global"},{"family":"inet6","address":"fd42::1","netmask":"64","scope":"global"}]},"lo":{"addresses":[{"family":"inet","address":"127.0.0.1","netmask":"8","scope":"local"}]}}},"snapshots":[{"name":"s1"},{"name":"s2"}]},{"architecture":"aarch64","config":{"image.description":"Ubuntu noble arm64"},"created_at":"2026-10-16T01:00:00Z","name":"vm-one","status":"Stopped","type":"virtual-machine","state":null,"snapshots":null}]""";

void test_incus_parse () {
    GenericArray<IncusInstance> list = null;
    try {
        list = IncusClient.parse_list (INCUS_FIXTURE);
    } catch (Error e) {
        error ("parse: %s", e.message);
    }
    assert_cmpint (list.length, CompareOperator.EQ, 2);
    var c = list[0];
    assert_cmpstr (c.name, CompareOperator.EQ, "orchard-test");
    assert_false (c.is_vm);
    assert_true (c.running);
    assert_cmpstr (c.kind_label, CompareOperator.EQ, "Container");
    assert_cmpstr (c.arch, CompareOperator.EQ, "aarch64");
    assert_cmpstr (c.image, CompareOperator.EQ, "Alpine edge arm64");
    assert_cmpstr (c.first_ip, CompareOperator.EQ, "10.169.229.233");   // loopback and IPv6 are skipped
    assert_cmpint (c.ipv4.length, CompareOperator.EQ, 1);
    assert_cmpint ((int) c.memory_usage, CompareOperator.EQ, 6864896);
    assert_cmpint ((int) c.disk_usage, CompareOperator.EQ, 3145728);
    assert_cmpstr (c.limit_cpu, CompareOperator.EQ, "2");
    assert_cmpstr (c.limit_memory, CompareOperator.EQ, "1GiB");
    assert_cmpint (c.snapshots, CompareOperator.EQ, 2);
    assert_cmpint ((int) c.pid, CompareOperator.EQ, 4242);
    var v = list[1];
    assert_true (v.is_vm);
    assert_false (v.running);                 // null state and null snapshots must not crash
    assert_cmpstr (v.first_ip, CompareOperator.EQ, "");
    assert_cmpint (v.snapshots, CompareOperator.EQ, 0);
}

void test_incus_empty_and_bad_json () {
    try {
        assert_cmpint (IncusClient.parse_list ("[]").length, CompareOperator.EQ, 0);
        assert_cmpint (IncusClient.parse_list ("{}").length, CompareOperator.EQ, 0);
    } catch (Error e) {
        error ("%s", e.message);
    }
    bool threw = false;
    try {
        IncusClient.parse_list ("not json");
    } catch (Error e) {
        threw = true;
    }
    assert_true (threw);
}

void test_snapshot_parse_and_tags () {
    string listing = "Snapshot list:\nID        TAG               VM SIZE                DATE     VM CLOCK     ICOUNT\n"
        + "1         before-upgrade       0 B 2026-10-19 21:40:11  0:00:00.000          0\n"
        + "2         clean.install    1.5 MiB 2026-10-19 22:01:09  0:00:00.000          0\n";
    var list = Snapshots.parse (listing);
    assert_cmpint (list.length, CompareOperator.EQ, 2);
    assert_cmpstr (list[0].tag, CompareOperator.EQ, "before-upgrade");
    assert_cmpstr (list[0].size, CompareOperator.EQ, "0 B");
    assert_cmpstr (list[1].size, CompareOperator.EQ, "1.5 MiB");
    assert_cmpstr (list[1].taken, CompareOperator.EQ, "2026-10-19 22:01:09");
    assert_cmpint (Snapshots.parse ("").length, CompareOperator.EQ, 0);
    assert_cmpint (Snapshots.parse ("Snapshot list:\n").length, CompareOperator.EQ, 0);
    assert_true (Snapshots.valid_tag ("pre-1.2_final"));
    assert_false (Snapshots.valid_tag (""));
    assert_false (Snapshots.valid_tag ("has space"));
    assert_false (Snapshots.valid_tag ("semi;colon"));
    assert_false (Snapshots.valid_tag (string.nfill (49, 'a')));
}

async int snapshot_flow (string disk) {
    string o;
    bool ok = yield Snapshots.run (disk, { "-c", "one" }, out o);
    assert_true (ok);
    ok = yield Snapshots.run (disk, { "-c", "two" }, out o);
    assert_true (ok);
    ok = yield Snapshots.run (disk, { "-d", "one" }, out o);
    assert_true (ok);
    yield Snapshots.run (disk, { "-l" }, out o);
    int n = Snapshots.parse (o).length;
    ok = yield Snapshots.run (disk, { "-a", "missing" }, out o);
    assert_false (ok);
    return n;
}

void test_snapshot_roundtrip () {
    if (Environment.find_program_in_path ("qemu-img") == null) {
        Test.skip ("qemu-img not installed");
        return;
    }
    string dir = "";
    try {
        dir = DirUtils.make_tmp ("ml-snap-XXXXXX");
    } catch (Error e) {
        Test.fail ();
        return;
    }
    string disk = Path.build_filename (dir, "disk.qcow2");
    try {
        Process.spawn_sync (null, { "qemu-img", "create", "-f", "qcow2", disk, "64M" }, null,
            SpawnFlags.SEARCH_PATH | SpawnFlags.STDOUT_TO_DEV_NULL, null);
    } catch (Error e) {
        Test.fail ();
        return;
    }
    var loop = new MainLoop ();
    int count = -1;
    snapshot_flow.begin (disk, (obj, res) => {
        count = snapshot_flow.end (res);
        loop.quit ();
    });
    loop.run ();
    assert_cmpint (count, CompareOperator.EQ, 1);
    FileUtils.unlink (disk);
    DirUtils.remove (dir);
}

string img_tmp () {
    try {
        return DirUtils.make_tmp ("ml-img-XXXXXX");
    } catch (Error e) {
        Test.fail ();
        return "";
    }
}

void sh (string cmd) {
    try {
        Process.spawn_command_line_sync ("sh -c '" + cmd.replace ("'", "'\\''") + "'");
    } catch (Error e) {
        Test.fail ();
    }
}

void test_images_helpers () {
    assert_cmpstr (DiskImages.kind_of ("a.qcow2.xz"), CompareOperator.EQ, "xz");
    assert_cmpstr (DiskImages.kind_of ("A.ZIP"), CompareOperator.EQ, "zip");
    assert_cmpstr (DiskImages.kind_of ("a.img"), CompareOperator.EQ, "disk");
    assert_true (DiskImages.is_disk_name ("Data/ABC.QCOW2"));
    assert_false (DiskImages.is_disk_name ("config.plist"));
    string listing = "Archive:  x.zip\n"
        + "drwxr-xr-x  3.0 unx        0 bx stor 25-01-01 10:00 Omarchy.utm/\n"
        + "-rw-r--r--  3.0 unx     2048 bx defN 25-01-01 10:00 Omarchy.utm/config.plist\n"
        + "-rw-r--r--  3.0 unx  4194304 bx defN 25-01-01 10:00 Omarchy.utm/Data/efi_vars.qcow2\n"
        + "-rw-r--r--  3.0 unx 34359738368 b- 3922294645 defF 25-Jan-01 10:00 Omarchy 4.utm/Data/disk one.qcow2\n";
    assert_cmpstr (DiskImages.pick_zip_entry (listing), CompareOperator.EQ, "Omarchy 4.utm/Data/disk one.qcow2");
    assert_null (DiskImages.pick_zip_entry ("Archive: x\n"));
    var i = DiskImages.parse_info ("{\"format\":\"qcow2\",\"virtual-size\":1073741824}");
    assert_true (i != null);
    assert_cmpstr (i.format, CompareOperator.EQ, "qcow2");
    assert_false (i.has_backing);
    var b = DiskImages.parse_info ("{\"format\":\"qcow2\",\"virtual-size\":1,\"backing-filename\":\"/etc/x\"}");
    assert_true (b.has_backing);
    assert_true (DiskImages.parse_info ("nope") == null);
}

async bool img_flow (string src, string dir, out string msg) {
    return yield DiskImages.import_image (src, dir, out msg);
}

bool run_import (string src, string dir, out string msg) {
    var loop = new MainLoop ();
    bool ok = false;
    string m = "";
    img_flow.begin (src, dir, (obj, res) => {
        ok = img_flow.end (res, out m);
        loop.quit ();
    });
    loop.run ();
    msg = m;
    return ok;
}

void test_images_import_export () {
    foreach (var tool in new string[] { "qemu-img", "xz" }) {
        if (Environment.find_program_in_path (tool) == null) {
            Test.skip (tool + " not installed");
            return;
        }
    }
    string w = img_tmp ();
    string msg;
    sh ("qemu-img create -q -f raw '%s/plain.img' 8M".printf (w));
    sh ("qemu-img create -q -f qcow2 '%s/base.qcow2' 8M && qemu-img create -q -f qcow2 -b '%s/base.qcow2' -F qcow2 '%s/over.qcow2'".printf (w, w, w));
    sh ("cp '%s/plain.img' '%s/packed.img' && xz -f '%s/packed.img'".printf (w, w, w));
    sh ("echo hello > '%s/junk.img'".printf (w));

    // A plain raw disk is converted to qcow2 and the machine counts as installed.
    string d1 = Path.build_filename (w, "m1");
    DiskImages.margin_bytes = 0;   // /tmp may be small; the margin is not what is under test
    assert_true (run_import (Path.build_filename (w, "plain.img"), d1, out msg));
    assert_true (FileUtils.test (Path.build_filename (d1, "disk.qcow2"), FileTest.EXISTS));
    assert_true (FileUtils.test (Path.build_filename (d1, "imported"), FileTest.EXISTS));
    assert_false (FileUtils.test (Path.build_filename (d1, ".import"), FileTest.EXISTS));

    // A compressed disk is unpacked first.
    string d2 = Path.build_filename (w, "m2");
    assert_true (run_import (Path.build_filename (w, "packed.img.xz"), d2, out msg));
    assert_true (FileUtils.test (Path.build_filename (d2, "disk.qcow2"), FileTest.EXISTS));

    // An image that leans on another file is refused, and nothing is left behind.
    string d3 = Path.build_filename (w, "m3");
    assert_false (run_import (Path.build_filename (w, "over.qcow2"), d3, out msg));
    assert_true (msg.contains ("depends on another file"));
    assert_false (FileUtils.test (Path.build_filename (d3, "disk.qcow2"), FileTest.EXISTS));

    // Garbage is refused with a clear message.
    string d4 = Path.build_filename (w, "m4");
    assert_false (run_import (Path.build_filename (w, "junk.img"), d4, out msg));
    assert_false (FileUtils.test (Path.build_filename (d4, "disk.qcow2"), FileTest.EXISTS));

    // Export writes a readable qcow2.
    var loop = new MainLoop ();
    bool ok = false;
    string em = "";
    string dest = Path.build_filename (w, "saved.qcow2");
    export_flow.begin (d1, dest, (obj, res) => {
        ok = export_flow.end (res, out em);
        loop.quit ();
    });
    loop.run ();
    assert_true (ok);
    string info = "";
    try {
        Process.spawn_command_line_sync ("qemu-img info --output=json '%s'".printf (dest), out info);
    } catch (Error e) {
        Test.fail ();
    }
    assert_true (info.contains ("\"format\": \"qcow2\""));

    sh ("rm -rf '%s'".printf (w));
}

async bool export_flow (string dir, string dest, out string msg) {
    return yield DiskImages.export_image (dir, dest, out msg);
}

void test_incus_names () {
    assert_true (IncusClient.valid_name ("lab-1"));
    assert_true (IncusClient.valid_name ("a"));
    assert_false (IncusClient.valid_name (""));
    assert_false (IncusClient.valid_name ("1lab"));          // must start with a letter
    assert_false (IncusClient.valid_name ("Lab"));           // lower case only
    assert_false (IncusClient.valid_name ("lab_1"));
    assert_false (IncusClient.valid_name ("lab-"));
    assert_false (IncusClient.valid_name ("lab; rm -rf"));
    assert_false (IncusClient.valid_name ("x".replace ("x", string.nfill (64, 'a'))));
}

int main (string[] args) {
    Test.init (ref args);
    try {
        tmp_dir = DirUtils.make_tmp ("machine-lab-test-XXXXXX");
    } catch (Error e) {
        error ("tmp: %s", e.message);
    }
    Environment.set_variable ("XDG_CONFIG_HOME", Path.build_filename (tmp_dir, "config"), true);
    Environment.set_variable ("XDG_DATA_HOME", Path.build_filename (tmp_dir, "data"), true);
    Test.add_func ("/store/round-trip", test_store_round_trip);
    Test.add_func ("/discovery/mseries-vm", test_discovery);
    Test.add_func ("/machine/installed-needs-real-data", test_installed_needs_real_data);
    Test.add_func ("/readiness/free-space", test_free_space);
    Test.add_func ("/readiness/per-arch", test_readiness_is_per_arch);
    Test.add_func ("/machine/credentials", test_mask_is_page_level);
    Test.add_func ("/qmp/transport", test_qmp_transport);
    Test.add_func ("/incus/parse", test_incus_parse);
    Test.add_func ("/incus/empty-and-bad-json", test_incus_empty_and_bad_json);
    Test.add_func ("/incus/names", test_incus_names);
    Test.add_func ("/snapshots/parse-and-tags", test_snapshot_parse_and_tags);
    Test.add_func ("/snapshots/roundtrip", test_snapshot_roundtrip);
    Test.add_func ("/images/helpers", test_images_helpers);
    Test.add_func ("/images/import-export", test_images_import_export);
    return Test.run ();
}
