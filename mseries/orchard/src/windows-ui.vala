/* Settings card for Windows guests (mseries-vm "windows" machines): get the virtio-win drivers and
 * attach them together with an unattended-install answer file. Everything here is user-triggered and
 * only changes a guest that has not been installed yet and is not running. */

public class WindowsDriversCard : Gtk.Box {
    private Machine machine;
    private Gtk.Label status = new Gtk.Label ("");
    private Gtk.Label result = new Gtk.Label ("");
    private Gtk.ProgressBar bar = new Gtk.ProgressBar ();
    private Gtk.Button download_button = new Gtk.Button.with_label ("");
    private Gtk.Entry account_entry = new Gtk.Entry ();
    private Gtk.PasswordEntry password_entry = new Gtk.PasswordEntry ();
    private Gtk.CheckButton skip_check = new Gtk.CheckButton.with_label ("Let setup finish without a network or Microsoft account (best effort)");
    private Gtk.CheckButton wipe_check = new Gtk.CheckButton.with_label ("Erase and partition the machine's disk without asking");
    private Gtk.Button attach_button = new Gtk.Button.with_label ("Attach Drivers and Answer File");
    private Gtk.Button remove_button = new Gtk.Button.with_label ("Remove Answer File");
    private bool busy = false;

    public signal void toast (string text);

    public WindowsDriversCard (Machine machine) {
        Object (orientation: Gtk.Orientation.VERTICAL, spacing: 8);
        this.machine = machine;
        add_css_class ("ml-card");
        var inner = new Gtk.Box (Gtk.Orientation.VERTICAL, 8);
        inner.add_css_class ("ml-form-row");
        append (inner);

        var title = new Gtk.Label ("Windows drivers (virtio-win)");
        title.xalign = 0;
        title.add_css_class ("heading");
        inner.append (title);
        var note = new Gtk.Label ("Windows Setup cannot see this machine's disks, network or display until virtio drivers are loaded. Download the driver disc once, then attach it with an answer file (autounattend.xml) that loads the drivers by itself. Only machines that are not installed yet are changed.");
        note.wrap = true;
        note.xalign = 0;
        note.add_css_class ("dim-label");
        inner.append (note);

        status.xalign = 0;
        status.wrap = true;
        inner.append (status);
        bar.visible = false;
        inner.append (bar);
        download_button.halign = Gtk.Align.START;
        download_button.clicked.connect (() => do_download.begin ());
        inner.append (download_button);

        var sub = new Gtk.Label ("Unattended install (optional)");
        sub.xalign = 0;
        sub.margin_top = 8;
        sub.add_css_class ("heading");
        inner.append (sub);
        account_entry.placeholder_text = "Local account name (leave empty to choose in setup)";
        account_entry.max_length = 20;
        inner.append (account_entry);
        password_entry.placeholder_text = "Password for that account";
        password_entry.show_peek_icon = true;
        inner.append (password_entry);
        skip_check.active = true;
        inner.append (skip_check);
        inner.append (wipe_check);
        var warn = new Gtk.Label ("The password is stored in plain text on the answer-file disc (readable only by you) until you remove it. With erase on, Setup wipes the machine's own virtual disk and installs without asking which disk to use.");
        warn.wrap = true;
        warn.xalign = 0;
        warn.add_css_class ("dim-label");
        inner.append (warn);

        var buttons = new Gtk.Box (Gtk.Orientation.HORIZONTAL, 8);
        attach_button.add_css_class ("suggested-action");
        attach_button.clicked.connect (() => do_attach.begin ());
        remove_button.clicked.connect (() => do_remove.begin ());
        buttons.append (attach_button);
        buttons.append (remove_button);
        inner.append (buttons);
        result.xalign = 0;
        result.wrap = true;
        result.selectable = true;
        inner.append (result);
        update ();
    }

    private bool can_change () {
        return machine.is_windows && machine.is_fresh ();
    }

    /* Called whenever the machine changes state. */
    public void update () {
        visible = machine.is_windows;
        if (!machine.is_windows) {
            return;
        }
        string? present = VirtioWin.find_present ();
        status.label = present != null
            ? "virtio-win %s is on this computer (%s). It is checked against its SHA-256 again before it is attached.".printf (VirtioWin.VERSION, present)
            : "virtio-win %s is not downloaded yet.".printf (VirtioWin.VERSION);
        download_button.label = present != null ? "Download Again" : "Download virtio-win (%d MiB)".printf ((int) (VirtioWin.SIZE / 1048576));
        download_button.tooltip_text = "Fetches virtio-win %s over HTTPS from fedorapeople.org and keeps it only if its SHA-256 is %s…".printf (
            VirtioWin.VERSION, VirtioWin.SHA256.substring (0, 12));
        bool free_to_change = can_change () && !busy;
        download_button.sensitive = !busy;
        attach_button.sensitive = free_to_change;
        attach_button.tooltip_text = free_to_change ? null
            : (machine.running ? "Shut the machine down first." : (machine.is_fresh () ? null : "This machine is already installed; its settings are not changed."));
        remove_button.sensitive = !busy && !machine.running && FileUtils.test (UnattendMedia.iso_path (machine.vm_name), FileTest.EXISTS);
        account_entry.sensitive = free_to_change;
        password_entry.sensitive = free_to_change;
        skip_check.sensitive = free_to_change;
        wipe_check.sensitive = free_to_change;
    }

    private void set_result (string text, bool failed) {
        result.label = text;
        if (failed) {
            result.add_css_class ("error");
        } else {
            result.remove_css_class ("error");
        }
    }

    private async void do_download () {
        if (busy) {
            return;
        }
        busy = true;
        update ();
        bar.visible = true;
        bar.fraction = 0;
        set_result ("Downloading virtio-win %s…".printf (VirtioWin.VERSION), false);
        string msg;
        bool ok = yield VirtioWin.download ((done, total) => {
            bar.fraction = total > 0 ? (double) done / (double) total : 0;
        }, out msg);
        bar.visible = false;
        busy = false;
        set_result (msg, !ok);
        toast (ok ? "virtio-win downloaded and verified" : "virtio-win download failed");
        update ();
    }

    private async bool set_conf (string tool, string key, string value) {
        try {
            var p = new Subprocess (SubprocessFlags.STDOUT_SILENCE | SubprocessFlags.STDERR_PIPE, tool, "set", machine.vm_name, key, value);
            string? err;
            yield p.communicate_utf8_async (null, null, null, out err);
            if (p.get_if_exited () && p.get_exit_status () == 0) {
                return true;
            }
            set_result ("Could not set %s: %s".printf (key, (err ?? "").strip ()), true);
        } catch (Error e) {
            set_result ("Could not set %s: %s".printf (key, e.message), true);
        }
        return false;
    }

    private async void do_attach () {
        if (busy) {
            return;
        }
        if (!can_change ()) {
            set_result ("This machine is running or already installed, so it was not changed.", true);
            return;
        }
        var o = new UnattendOptions ();
        o.arch = machine.arch;
        o.account = account_entry.text.strip ();
        o.password = password_entry.text;
        o.skip_network = skip_check.active;
        o.wipe_disk = wipe_check.active;
        string err;
        string? xml = WindowsUnattend.generate (o, out err);
        if (xml == null) {
            set_result (err, true);
            return;
        }
        if (o.wipe_disk) {
            var dlg = new Gtk.AlertDialog ("Let setup erase the disk of “%s”?".printf (machine.name));
            dlg.detail = "Windows Setup will wipe this machine's virtual disk and install onto it without asking. Only the machine's own disk is affected, nothing on this computer.";
            dlg.buttons = { "Cancel", "Erase and Install" };
            dlg.cancel_button = 0;
            dlg.default_button = 0;
            try {
                if ((yield dlg.choose ((Gtk.Window) get_root (), null)) != 1) {
                    return;
                }
            } catch (Error e) {
                return;
            }
        }
        string? tool = Machine.find_mseries_vm ();
        if (tool == null) {
            set_result ("The mseries-vm tool was not found, so the machine cannot be changed.", true);
            return;
        }
        busy = true;
        update ();
        yield attach (tool, xml);
        busy = false;
        update ();
    }

    private async void attach (string tool, string xml) {
        string existing = machine.conf_value ("EXTRA_MEDIA") ?? "";
        bool has_virtio = WindowsUnattend.has_virtio_win (existing);
        string[] adds = {};

        // 1. A verified driver disc, unless the machine already has one attached.
        if (!has_virtio) {
            string? iso = VirtioWin.find_present ();
            if (iso == null) {
                set_result ("virtio-win is not downloaded yet. Press Download first; nothing was changed.", true);
                return;
            }
            set_result ("Checking the checksum of %s…".printf (Path.get_basename (iso)), false);
            string vmsg;
            if (!(yield VirtioWin.verify_async (iso, VirtioWin.SHA256, VirtioWin.SIZE, out vmsg))) {
                set_result (vmsg + " Nothing was attached. Use Download Again to replace it.", true);
                return;
            }
            if (!WindowsUnattend.path_is_listable (iso)) {
                set_result ("The path %s contains a space, which vm.conf's EXTRA_MEDIA list cannot hold. Move the file or use a home folder without spaces.".printf (iso), true);
                return;
            }
            adds += iso;
        }

        // 2. The answer-file disc.
        set_result ("Building the answer file…", false);
        string unattend_msg;
        if (!(yield UnattendMedia.build (UnattendMedia.dir_for (machine.vm_name), xml, out unattend_msg))) {
            set_result (unattend_msg, true);
            return;
        }
        if (!WindowsUnattend.path_is_listable (unattend_msg)) {
            UnattendMedia.remove (machine.vm_name);
            set_result ("The path %s contains a space, which vm.conf's EXTRA_MEDIA list cannot hold.".printf (unattend_msg), true);
            return;
        }
        adds += unattend_msg;

        // 3. Only now touch the machine's settings: extra media, USB for it (Setup reads USB natively), and ramfb.
        string merged = WindowsUnattend.merge_media (existing, adds);
        if (!(yield set_conf (tool, "EXTRA_MEDIA", merged)) || !(yield set_conf (tool, "EXTRA_BUS", "usb")) || !(yield set_conf (tool, "GPU", "ramfb"))) {
            return;
        }
        set_result ("Attached. Start the installer: Setup loads the virtio drivers itself and finds the answer file on its own. After the install, press Remove Answer File.", false);
        toast ("Drivers and answer file attached");
    }

    private async void do_remove () {
        if (busy || machine.running) {
            return;
        }
        string? tool = Machine.find_mseries_vm ();
        if (tool == null) {
            set_result ("The mseries-vm tool was not found.", true);
            return;
        }
        busy = true;
        update ();
        string existing = machine.conf_value ("EXTRA_MEDIA") ?? "";
        string without = WindowsUnattend.remove_media (existing, UnattendMedia.iso_path (machine.vm_name));
        bool ok = without == existing || (yield set_conf (tool, "EXTRA_MEDIA", without));
        if (ok) {
            UnattendMedia.remove (machine.vm_name);
            set_result ("Answer file removed from the machine and deleted.", false);
            toast ("Answer file removed");
        }
        busy = false;
        update ();
    }
}
