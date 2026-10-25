/* Tests for the Windows answer-file generator, the virtio-win download policy and the answer-file disc. */

string tmp_dir;

// ---- A small recording XML parser (GLib's MarkupParser: fails on anything that is not well formed) ----

string cur_pass;
string cur_component;
GenericArray<string> stack;
GenericArray<string> doc_paths;        // "pass|component|path" for every DriverPaths <Path>
GenericArray<string> doc_keyvalues;    // "pass|component|keyValue"
GenericArray<string> doc_components;   // "pass|component|processorArchitecture"
GenericArray<string> doc_elements;     // every element name seen
GenericArray<string> doc_texts;        // "a/b/c=text" for every non-blank text node
GenericArray<string> doc_commands;     // RunSynchronous <Path> texts

void on_start (MarkupParseContext ctx, string name, string[] attr_names, string[] attr_values) throws MarkupError {
    stack.add (name);
    doc_elements.add (name);
    for (int i = 0; i < attr_names.length; i++) {
        if (name == "settings" && attr_names[i] == "pass") {
            cur_pass = attr_values[i];
        } else if (name == "component" && attr_names[i] == "name") {
            cur_component = attr_values[i];
        } else if (attr_names[i] == "wcm:keyValue") {
            doc_keyvalues.add ("%s|%s|%s".printf (cur_pass, cur_component, attr_values[i]));
        }
    }
    if (name == "component") {
        for (int i = 0; i < attr_names.length; i++) {
            if (attr_names[i] == "processorArchitecture") {
                doc_components.add ("%s|%s|%s".printf (cur_pass, cur_component, attr_values[i]));
            }
        }
    }
}

void on_end (MarkupParseContext ctx, string name) throws MarkupError {
    stack.remove_index (stack.length - 1);
}

void on_text (MarkupParseContext ctx, string text, size_t len) throws MarkupError {
    string t = text.strip ();
    if (t == "") {
        return;
    }
    var sb = new StringBuilder ();
    foreach (var s in stack.data) {
        sb.append (s).append ("/");
    }
    string path = sb.str;
    doc_texts.add ("%s=%s".printf (path, t));
    if (path.has_suffix ("PathAndCredentials/Path/")) {
        doc_paths.add ("%s|%s|%s".printf (cur_pass, cur_component, t));
    } else if (path.has_suffix ("RunSynchronousCommand/Path/")) {
        doc_commands.add (t);
    }
}

/* Parses `xml`; returns null when it is well formed, otherwise the parser's complaint. */
string? parse (string xml) {
    stack = new GenericArray<string> ();
    doc_paths = new GenericArray<string> ();
    doc_keyvalues = new GenericArray<string> ();
    doc_components = new GenericArray<string> ();
    doc_elements = new GenericArray<string> ();
    doc_texts = new GenericArray<string> ();
    doc_commands = new GenericArray<string> ();
    cur_pass = "";
    cur_component = "";
    MarkupParser parser = MarkupParser () {
        start_element = on_start,
        end_element = on_end,
        text = on_text
    };
    var ctx = new MarkupParseContext (parser, 0, null, null);
    try {
        ctx.parse (xml, -1);
        ctx.end_parse ();
    } catch (MarkupError e) {
        return e.message;
    }
    return null;
}

bool has_path (string pass, string component, string path) {
    return contains (doc_paths, "%s|%s|%s".printf (pass, component, path));
}

bool contains (GenericArray<string> list, string needle) {
    foreach (var s in list.data) {
        if (s == needle) {
            return true;
        }
    }
    return false;
}

const string[] KNOWN_ELEMENTS = {
    "unattend", "settings", "component", "SetupUILanguage", "UILanguage", "InputLocale", "SystemLocale", "UserLocale",
    "DiskConfiguration", "Disk", "DiskID", "WillWipeDisk", "CreatePartitions", "CreatePartition", "Order", "Type", "Size", "Extend",
    "ModifyPartitions", "ModifyPartition", "PartitionID", "Label", "Format", "Letter", "WillShowUI",
    "ImageInstall", "OSImage", "InstallTo", "DriverPaths", "PathAndCredentials", "Path",
    "RunSynchronous", "RunSynchronousCommand", "Description",
    "OOBE", "HideLocalAccountScreen", "HideOnlineAccountScreens", "HideWirelessSetupInOOBE",
    "UserAccounts", "LocalAccounts", "LocalAccount", "Password", "Value", "PlainText", "DisplayName", "Group", "Name"
};

UnattendOptions opts (string arch, string account = "", string password = "", bool skip = false, bool wipe = false) {
    var o = new UnattendOptions ();
    o.arch = arch;
    o.account = account;
    o.password = password;
    o.skip_network = skip;
    o.wipe_disk = wipe;
    return o;
}

string gen (UnattendOptions o) {
    string err;
    string? xml = WindowsUnattend.generate (o, out err);
    if (xml == null) {
        error ("generate failed: %s", err);
    }
    return xml;
}

// ---- driver paths ----

void test_driver_paths_per_arch () {
    var arm = WindowsUnattend.driver_paths ("aarch64", WindowsUnattend.SETUP_DRIVERS);
    assert_cmpint (arm.length, CompareOperator.EQ, WindowsUnattend.SETUP_DRIVERS.length * WindowsUnattend.DRIVE_LETTERS.length);
    foreach (var p in arm) {
        assert_true (p.has_suffix ("\\w11\\ARM64"));
        assert_false (p.down ().contains ("amd64"));
    }
    assert_true (strv_contains (arm, "D:\\NetKVM\\w11\\ARM64"));
    assert_true (strv_contains (arm, "E:\\vioscsi\\w11\\ARM64"));
    assert_true (strv_contains (arm, "K:\\viostor\\w11\\ARM64"));

    var amd = WindowsUnattend.driver_paths ("x86_64", WindowsUnattend.SYSTEM_DRIVERS);
    foreach (var p in amd) {
        assert_true (p.has_suffix ("\\w11\\amd64"));
        assert_false (p.down ().contains ("arm64"));
    }
    assert_true (strv_contains (amd, "D:\\viogpudo\\w11\\amd64"));
    assert_true (strv_contains (amd, "F:\\Balloon\\w11\\amd64"));

    assert_cmpint (WindowsUnattend.driver_paths ("riscv64", WindowsUnattend.SETUP_DRIVERS).length, CompareOperator.EQ, 0);
    assert_cmpstr (WindowsUnattend.processor_arch ("aarch64"), CompareOperator.EQ, "arm64");
    assert_cmpstr (WindowsUnattend.processor_arch ("x86_64"), CompareOperator.EQ, "amd64");
    assert_null (WindowsUnattend.processor_arch ("i386"));
    assert_cmpstr (WindowsUnattend.virtio_arch ("aarch64"), CompareOperator.EQ, "ARM64");
    assert_cmpstr (WindowsUnattend.virtio_arch ("x86_64"), CompareOperator.EQ, "amd64");
}

/* The folders the generator names must be real folders of the virtio-win ISO: this is the layout of
 * virtio-win 0.1.302 (checked with isoinfo against the pinned ISO). */
void test_driver_folders_exist_in_virtio_layout () {
    string[] arm_layout = { "Balloon", "NetKVM", "pvpanic", "viofs", "viogpudo", "vioinput", "viomem", "viorng", "vioscsi", "vioserial", "viosock", "viostor" };
    foreach (var d in WindowsUnattend.SYSTEM_DRIVERS) {
        assert_true (strv_contains (arm_layout, d));
    }
    foreach (var d in WindowsUnattend.SETUP_DRIVERS) {
        assert_true (strv_contains (WindowsUnattend.SYSTEM_DRIVERS, d));   // Setup drivers are a subset
    }
}

// ---- the answer file ----

void test_xml_is_valid_for_every_option_combination () {
    string[] arches = { "aarch64", "x86_64" };
    string[] accounts = { "", "lab" };
    bool[] flags = { false, true };
    foreach (var arch in arches) {
        foreach (var acct in accounts) {
            foreach (var skip in flags) {
                foreach (var wipe in flags) {
                    string xml = gen (opts (arch, acct, acct == "" ? "" : "pw", skip, wipe));
                    string? bad = parse (xml);
                    if (bad != null) {
                        error ("not well formed (%s %s skip=%s wipe=%s): %s", arch, acct, skip.to_string (), wipe.to_string (), bad);
                    }
                    // Only elements of Microsoft's unattend vocabulary.
                    foreach (var e in doc_elements.data) {
                        if (!strv_contains (KNOWN_ELEMENTS, e)) {
                            error ("unexpected element <%s>", e);
                        }
                    }
                    // Every component names the guest's architecture, and nothing else.
                    string pa = arch == "aarch64" ? "arm64" : "amd64";
                    assert_true (doc_components.length >= 4);
                    foreach (var c in doc_components.data) {
                        assert_true (c.has_suffix ("|" + pa));
                    }
                    // wcm:keyValue is 1..n without repeats inside each DriverPaths list.
                    var seen = new GenericArray<string> ();
                    foreach (var k in doc_keyvalues.data) {
                        assert_false (contains (seen, k));
                        seen.add (k);
                    }
                    assert_true (xml.has_prefix ("<?xml version=\"1.0\" encoding=\"utf-8\"?>"));
                    assert_true (xml.contains ("urn:schemas-microsoft-com:unattend"));
                }
            }
        }
    }
}

void test_driver_paths_in_passes () {
    string xml = gen (opts ("aarch64"));
    assert_null (parse (xml));
    // windowsPE: storage, network, input; ARM64 folders only; no display driver yet.
    assert_true (has_path ("windowsPE", "Microsoft-Windows-PnpCustomizationsWinPE", "E:\\vioscsi\\w11\\ARM64"));
    assert_true (has_path ("windowsPE", "Microsoft-Windows-PnpCustomizationsWinPE", "D:\\viostor\\w11\\ARM64"));
    assert_true (has_path ("windowsPE", "Microsoft-Windows-PnpCustomizationsWinPE", "F:\\NetKVM\\w11\\ARM64"));
    assert_false (has_path ("windowsPE", "Microsoft-Windows-PnpCustomizationsWinPE", "D:\\viogpudo\\w11\\ARM64"));
    // specialize: the full set.
    assert_true (has_path ("specialize", "Microsoft-Windows-PnpCustomizationsNonWinPE", "D:\\viogpudo\\w11\\ARM64"));
    assert_true (has_path ("specialize", "Microsoft-Windows-PnpCustomizationsNonWinPE", "G:\\Balloon\\w11\\ARM64"));
    assert_true (has_path ("specialize", "Microsoft-Windows-PnpCustomizationsNonWinPE", "D:\\NetKVM\\w11\\ARM64"));
    foreach (var p in doc_paths.data) {
        assert_false (p.contains ("amd64"));
    }
    assert_cmpint (doc_paths.length, CompareOperator.EQ,
        (WindowsUnattend.SETUP_DRIVERS.length + WindowsUnattend.SYSTEM_DRIVERS.length) * WindowsUnattend.DRIVE_LETTERS.length);

    // x86-64 guests get amd64 folders.
    assert_null (parse (gen (opts ("x86_64"))));
    assert_true (has_path ("windowsPE", "Microsoft-Windows-PnpCustomizationsWinPE", "D:\\vioscsi\\w11\\amd64"));
    foreach (var p in doc_paths.data) {
        assert_false (p.contains ("ARM64"));
    }
}

void test_pnputil_fallback_per_driver () {
    assert_null (parse (gen (opts ("aarch64"))));
    assert_cmpint (doc_commands.length, CompareOperator.EQ, WindowsUnattend.SYSTEM_DRIVERS.length);
    bool found_netkvm = false;
    foreach (var c in doc_commands.data) {
        assert_true (c.has_prefix ("cmd /c for %i in (D E F G H I J K) do"));
        assert_true (c.contains ("pnputil /add-driver"));
        assert_true (c.contains ("\\w11\\ARM64"));
        if (c.contains ("\\NetKVM\\w11\\ARM64\\*.inf /install")) {
            found_netkvm = true;
        }
    }
    assert_true (found_netkvm);
}

void test_default_is_non_destructive () {
    string xml = gen (opts ("aarch64"));
    assert_null (parse (xml));
    assert_false (contains (doc_elements, "DiskConfiguration"));
    assert_false (contains (doc_elements, "WillWipeDisk"));
    assert_false (contains (doc_elements, "CreatePartition"));
    assert_false (contains (doc_elements, "ImageInstall"));
    assert_false (xml.contains ("Format"));
    assert_false (contains (doc_elements, "LocalAccount"));
    assert_false (xml.contains ("HideEULAPage"));       // accepting the licence is the owner's call
    assert_false (xml.contains ("AcceptEula"));
    assert_false (xml.contains ("ProductKey"));
    assert_false (xml.contains ("BypassNRO"));          // opt in
}

void test_wipe_is_explicit () {
    string xml = gen (opts ("aarch64", "", "", false, true));
    assert_null (parse (xml));
    assert_true (contains (doc_elements, "DiskConfiguration"));
    assert_true (contains (doc_texts, "unattend/settings/component/DiskConfiguration/Disk/WillWipeDisk/=true"));
    assert_true (contains (doc_texts, "unattend/settings/component/ImageInstall/OSImage/InstallTo/PartitionID/=3"));
    assert_true (contains (doc_texts, "unattend/settings/component/DiskConfiguration/Disk/DiskID/=0"));
}

void test_account_and_escaping () {
    string tricky = "p&ss<w>\"o'rd";
    string xml = gen (opts ("aarch64", "lab", tricky, true));
    assert_false (xml.contains (tricky));                 // must be escaped in the file
    assert_null (parse (xml));
    assert_true (contains (doc_texts, "unattend/settings/component/UserAccounts/LocalAccounts/LocalAccount/Password/Value/=" + tricky));
    assert_true (contains (doc_texts, "unattend/settings/component/UserAccounts/LocalAccounts/LocalAccount/Name/=lab"));
    assert_true (contains (doc_texts, "unattend/settings/component/UserAccounts/LocalAccounts/LocalAccount/Group/=Administrators"));
    assert_true (contains (doc_texts, "unattend/settings/component/OOBE/HideOnlineAccountScreens/=true"));
    assert_true (xml.contains ("<PlainText>true</PlainText>"));
    // BypassNRO is the first command of the specialize RunSynchronous list.
    assert_true (doc_commands.length == WindowsUnattend.SYSTEM_DRIVERS.length + 1);
    assert_true (doc_commands[0].contains ("BypassNRO"));
    assert_true (xml.contains ("<Order>1</Order>\n          <Path>reg add"));
}

void test_invalid_options () {
    string err;
    assert_null (WindowsUnattend.generate (opts ("mips"), out err));
    assert_true (err.contains ("architecture"));
    assert_null (WindowsUnattend.generate (opts ("aarch64", "bad:name", "x"), out err));
    assert_true (err.contains ("account name"));
    assert_null (WindowsUnattend.generate (opts ("aarch64", "lab", ""), out err));
    assert_true (err.contains ("password"));
    assert_null (WindowsUnattend.generate (opts ("aarch64", "", "orphan-password"), out err));   // password without an account
    assert_null (WindowsUnattend.generate (opts ("aarch64", "lab", "tab\there"), out err));
    var o = opts ("aarch64");
    o.locale = "en_US; rm";
    assert_null (WindowsUnattend.generate (o, out err));
    assert_true (err.contains ("language tag"));

    assert_true (WindowsUnattend.valid_account_name ("lab"));
    assert_true (WindowsUnattend.valid_account_name ("Zoë.User-1"));
    assert_true (WindowsUnattend.valid_account_name ("exactly-twenty-chars"));
    assert_false (WindowsUnattend.valid_account_name ("exactly-twenty-one-chs"));
    assert_false (WindowsUnattend.valid_account_name (""));
    assert_false (WindowsUnattend.valid_account_name ("..."));
    assert_false (WindowsUnattend.valid_account_name ("a@b"));
    assert_false (WindowsUnattend.valid_account_name ("a/b"));
    assert_false (WindowsUnattend.valid_account_name ("a\\b"));
    assert_true (WindowsUnattend.valid_locale ("en-US"));
    assert_true (WindowsUnattend.valid_locale ("zh-Hans-CN"));
    assert_false (WindowsUnattend.valid_locale ("english"));
}

void test_locale_flows_through () {
    var o = opts ("aarch64");
    o.locale = "de-DE";
    string xml = gen (o);
    assert_null (parse (xml));
    assert_true (contains (doc_texts, "unattend/settings/component/SetupUILanguage/UILanguage/=de-DE"));
    assert_true (contains (doc_texts, "unattend/settings/component/UserLocale/=de-DE"));
}

// ---- vm.conf EXTRA_MEDIA list ----

void test_media_list () {
    assert_cmpstr (WindowsUnattend.merge_media ("", { "/a/v.iso", "/a/u.iso" }), CompareOperator.EQ, "/a/v.iso /a/u.iso");
    // existing entries are kept, in order; nothing listed twice
    assert_cmpstr (WindowsUnattend.merge_media ("/x/other.iso  /a/u.iso", { "/a/v.iso", "/a/u.iso" }), CompareOperator.EQ, "/x/other.iso /a/u.iso /a/v.iso");
    // an attached virtio-win disc (any path or version) is not added twice
    assert_cmpstr (WindowsUnattend.merge_media ("/vms/downloads/virtio-win/virtio-win.iso", { "/cache/virtio-win-0.1.302.iso", "/a/u.iso" }),
        CompareOperator.EQ, "/vms/downloads/virtio-win/virtio-win.iso /a/u.iso");
    assert_true (WindowsUnattend.has_virtio_win ("/x/y.iso /v/virtio-win-0.1.266.iso"));
    assert_false (WindowsUnattend.has_virtio_win ("/x/y.iso"));
    assert_false (WindowsUnattend.has_virtio_win (""));
    assert_cmpstr (WindowsUnattend.remove_media ("/v/virtio-win.iso /a/u.iso", "/a/u.iso"), CompareOperator.EQ, "/v/virtio-win.iso");
    assert_cmpstr (WindowsUnattend.remove_media ("/a/u.iso", "/a/u.iso"), CompareOperator.EQ, "");
    assert_cmpstr (WindowsUnattend.remove_media ("/v/x.iso", "/not/there.iso"), CompareOperator.EQ, "/v/x.iso");
    assert_true (WindowsUnattend.path_is_listable ("/home/me/x.iso"));
    assert_false (WindowsUnattend.path_is_listable ("/home/my name/x.iso"));
    assert_false (WindowsUnattend.path_is_listable (""));
}

// ---- virtio-win policy ----

void write_file (string path, string text) {
    DirUtils.create_with_parents (Path.get_dirname (path), 0755);
    try {
        FileUtils.set_contents (path, text);
    } catch (Error e) {
        error ("write %s: %s", path, e.message);
    }
}

void test_pinned_release () {
    assert_cmpint (VirtioWin.SHA256.length, CompareOperator.EQ, 64);
    assert_true (VirtioWin.DEFAULT_URL.has_prefix ("https://"));
    assert_true (VirtioWin.DEFAULT_URL.contains (VirtioWin.VERSION));       // pinned archive, not "latest"
    assert_false (VirtioWin.DEFAULT_URL.contains ("latest"));
    assert_false (VirtioWin.DEFAULT_URL.contains ("stable"));
    assert_true (VirtioWin.cache_path ().has_suffix ("virtio-win-%s.iso".printf (VirtioWin.VERSION)));
}

void test_verify_file () {
    string f = Path.build_filename (tmp_dir, "fake-virtio.iso");
    write_file (f, "hello virtio\n");
    // sha256 of "hello virtio\n"
    string sha = Checksum.compute_for_string (ChecksumType.SHA256, "hello virtio\n");
    assert_cmpstr (VirtioWin.sha256_file (f), CompareOperator.EQ, sha);
    string msg;
    assert_true (VirtioWin.verify_file (f, sha, 13, out msg));
    assert_true (msg.contains ("verified"));
    // wrong checksum: a clear failure that names both values
    assert_false (VirtioWin.verify_file (f, string.nfill (64, '0'), 13, out msg));
    assert_true (msg.contains ("Checksum mismatch"));
    assert_true (msg.contains (sha));
    // wrong size: reported as incomplete before hashing
    assert_false (VirtioWin.verify_file (f, sha, 14, out msg));
    assert_true (msg.contains ("incomplete"));
    // missing file
    assert_false (VirtioWin.verify_file (Path.build_filename (tmp_dir, "nope.iso"), sha, 13, out msg));
    assert_true (msg.contains ("cannot be read"));
}

async bool download_flow (out string msg) {
    return yield VirtioWin.download (null, out msg);
}

void run_download (string url, out bool ok, out string msg) {
    Environment.set_variable ("MACHINE_LAB_VIRTIO_URL", url, true);
    var loop = new MainLoop ();
    bool o = true;
    string m = "";
    download_flow.begin ((obj, res) => {
        o = download_flow.end (res, out m);
        loop.quit ();
    });
    loop.run ();
    Environment.unset_variable ("MACHINE_LAB_VIRTIO_URL");
    ok = o;
    msg = m;
}

void test_download_failure_states () {
    if (Environment.find_program_in_path ("curl") == null) {
        Test.skip ("curl not installed");
        return;
    }
    bool ok;
    string msg;
    // Unreachable server: a clear failure, and no usable file.
    run_download ("https://127.0.0.1:9/virtio-win.iso", out ok, out msg);
    assert_false (ok);
    assert_true (msg.has_prefix ("Download failed"));
    assert_false (FileUtils.test (VirtioWin.cache_path (), FileTest.EXISTS));
    assert_null (VirtioWin.find_present ());

    // Anything but https is refused (file:// would otherwise copy a local file in as "the ISO").
    string local = Path.build_filename (tmp_dir, "local.iso");
    write_file (local, "not an iso");
    run_download ("file://" + local, out ok, out msg);
    assert_false (ok);
    assert_true (msg.has_prefix ("Download failed"));
    assert_false (FileUtils.test (VirtioWin.cache_path (), FileTest.EXISTS));
    run_download ("http://127.0.0.1:9/virtio-win.iso", out ok, out msg);
    assert_false (ok);
    assert_false (FileUtils.test (VirtioWin.cache_path (), FileTest.EXISTS));
}

// ---- the answer-file disc ----

async bool build_flow (string dir, string xml, out string msg) {
    return yield UnattendMedia.build (dir, xml, out msg);
}

void test_build_media () {
    if (Environment.find_program_in_path ("genisoimage") == null && Environment.find_program_in_path ("mkisofs") == null) {
        Test.skip ("genisoimage not installed");
        return;
    }
    string dir = Path.build_filename (tmp_dir, "unattend-test");
    string xml = gen (opts ("aarch64", "lab", "pw", true));
    var loop = new MainLoop ();
    bool ok = false;
    string msg = "";
    build_flow.begin (dir, xml, (obj, res) => {
        ok = build_flow.end (res, out msg);
        loop.quit ();
    });
    loop.run ();
    assert_true (ok);
    assert_cmpstr (msg, CompareOperator.EQ, Path.build_filename (dir, "autounattend.iso"));
    assert_true (FileUtils.test (msg, FileTest.EXISTS));
    // owner-only, and the staging copy of the xml (with the password) is gone
    Posix.Stat st;
    assert_cmpint (Posix.stat (msg, out st), CompareOperator.EQ, 0);
    assert_cmpint ((int) (st.st_mode & 0777), CompareOperator.EQ, 0600);
    assert_false (FileUtils.test (Path.build_filename (dir, "stage"), FileTest.EXISTS));
    assert_false (FileUtils.test (msg + ".part", FileTest.EXISTS));
    // the disc carries autounattend.xml at its root
    if (Environment.find_program_in_path ("isoinfo") != null) {
        string listing = "";
        try {
            Process.spawn_command_line_sync ("isoinfo -J -l -i '%s'".printf (msg), out listing);
        } catch (Error e) {
            Test.fail ();
        }
        assert_true (listing.contains ("autounattend.xml"));
        string content = "";
        try {
            Process.spawn_command_line_sync ("isoinfo -J -x '/autounattend.xml' -i '%s'".printf (msg), out content);
        } catch (Error e) {
            Test.fail ();
        }
        assert_cmpstr (content, CompareOperator.EQ, xml);
    }
    UnattendMedia.remove ("x");   // harmless for an unknown name
    FileUtils.unlink (msg);
    DirUtils.remove (dir);
}

// ---- Windows guests are recognised ----

void test_windows_guest_discovery () {
    string vms = Path.build_filename (tmp_dir, "vms");
    write_file (Path.build_filename (vms, "windows", "vm.conf"), "GUEST=windows\nEXTRA_MEDIA=/v/virtio-win.iso\nEXTRA_BUS=usb\n");
    write_file (Path.build_filename (vms, "omarchy", "vm.conf"), "GUEST=omarchy\n");
    Environment.set_variable ("MSERIES_VM_DIR", vms, true);
    var list = new GenericArray<Machine> ();
    MachineStore.discover (list);
    Machine? win = null, omarchy = null;
    foreach (var m in list.data) {
        if (m.vm_name == "windows") win = m;
        if (m.vm_name == "omarchy") omarchy = m;
    }
    assert_nonnull (win);
    assert_nonnull (omarchy);
    assert_true (win.is_windows);
    assert_false (omarchy.is_windows);
    assert_cmpstr (win.conf_value ("EXTRA_MEDIA"), CompareOperator.EQ, "/v/virtio-win.iso");
    assert_cmpstr (win.conf_value ("EXTRA_BUS"), CompareOperator.EQ, "usb");
    assert_null (win.conf_value ("GPU"));
    // reading never modifies the guest
    string conf;
    try {
        FileUtils.get_contents (Path.build_filename (vms, "windows", "vm.conf"), out conf);
    } catch (Error e) {
        Test.fail ();
        return;
    }
    assert_cmpstr (conf, CompareOperator.EQ, "GUEST=windows\nEXTRA_MEDIA=/v/virtio-win.iso\nEXTRA_BUS=usb\n");
}

int main (string[] args) {
    Test.init (ref args);
    try {
        tmp_dir = DirUtils.make_tmp ("machine-lab-unattend-XXXXXX");
    } catch (Error e) {
        error ("tmp: %s", e.message);
    }
    Environment.set_variable ("XDG_CONFIG_HOME", Path.build_filename (tmp_dir, "config"), true);
    Environment.set_variable ("XDG_DATA_HOME", Path.build_filename (tmp_dir, "data"), true);
    Environment.set_variable ("MSERIES_VM_DIR", Path.build_filename (tmp_dir, "vms"), true);
    Test.add_func ("/unattend/driver-paths-per-arch", test_driver_paths_per_arch);
    Test.add_func ("/unattend/driver-folders-match-virtio-layout", test_driver_folders_exist_in_virtio_layout);
    Test.add_func ("/unattend/xml-valid-all-combinations", test_xml_is_valid_for_every_option_combination);
    Test.add_func ("/unattend/driver-paths-in-passes", test_driver_paths_in_passes);
    Test.add_func ("/unattend/pnputil-fallback", test_pnputil_fallback_per_driver);
    Test.add_func ("/unattend/default-non-destructive", test_default_is_non_destructive);
    Test.add_func ("/unattend/wipe-explicit", test_wipe_is_explicit);
    Test.add_func ("/unattend/account-and-escaping", test_account_and_escaping);
    Test.add_func ("/unattend/invalid-options", test_invalid_options);
    Test.add_func ("/unattend/locale", test_locale_flows_through);
    Test.add_func ("/unattend/media-list", test_media_list);
    Test.add_func ("/virtio/pinned-release", test_pinned_release);
    Test.add_func ("/virtio/verify-file", test_verify_file);
    Test.add_func ("/virtio/download-failure", test_download_failure_states);
    Test.add_func ("/unattend/build-media", test_build_media);
    Test.add_func ("/machine/windows-discovery", test_windows_guest_discovery);
    return Test.run ();
}
