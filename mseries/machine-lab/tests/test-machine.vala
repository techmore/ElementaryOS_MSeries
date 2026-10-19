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
}

void test_discovery () {
    var vms = Path.build_filename (tmp_dir, "vms");
    write_file (Path.build_filename (vms, "omarchy", "vm.conf"),
        "# comment\nGUEST=omarchy\nCPUS=4\nMEMORY_MB=4096\nISO=\nBOOT=disk\n");
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

void test_mask_is_page_level () {
    // masking lives in MachinePage; here we just make sure the credentials file is read and trimmed
    var m = new Machine ();
    m.id = "machine-creds";
    write_file (Path.build_filename (m.dir, "credentials.txt"), "Username: a\nPassword: b\n");
    assert_cmpstr (m.credentials (), CompareOperator.EQ, "Username: a  ·  Password: b");
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
        ctl = new Subprocess.newv (a, SubprocessFlags.NONE);
        view = new Subprocess.newv (b, SubprocessFlags.NONE);
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

    ctl.force_exit ();
    view.force_exit ();
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
    Test.add_func ("/machine/credentials", test_mask_is_page_level);
    Test.add_func ("/qmp/transport", test_qmp_transport);
    return Test.run ();
}
