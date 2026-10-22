/* Disk snapshots for Machine Lab's own machines: qcow2 internal snapshots through qemu-img.
 * A snapshot is a restore point for the whole disk (not the running memory), so the machine
 * must be shut down first. Take one before an upgrade or an experiment; restore if it goes wrong. */

public class DiskSnapshot : Object {
    public string id { get; set; default = ""; }
    public string tag { get; set; default = ""; }
    public string size { get; set; default = ""; }
    public string taken { get; set; default = ""; }
}

public class Snapshots : Object {
    /* Tags are kept to a safe alphabet so they survive shells, qemu-img and the list parser. */
    public static bool valid_tag (string tag) {
        if (tag.length == 0 || tag.length > 48) {
            return false;
        }
        for (int i = 0; i < tag.length; i++) {
            unichar c = tag.get_char (tag.index_of_nth_char (i));
            if (!(c.isalnum () || c == '-' || c == '_' || c == '.')) {
                return false;
            }
        }
        return true;
    }

    /* Parses `qemu-img snapshot -l`:
     *   ID  TAG  VM SIZE  DATE  VM CLOCK  ICOUNT
     *   1   before-upgrade  0 B  2026-10-19 21:40:11  00:00:00.000 */
    public static DiskSnapshot[] parse (string output) {
        DiskSnapshot[] list = {};
        foreach (var line in output.split ("\n")) {
            string[] t = line.strip ().split (" ");
            string[] f = {};
            foreach (var w in t) {
                if (w != "") {
                    f += w;
                }
            }
            if (f.length < 6 || !(f[0][0].isdigit ())) {
                continue;   // headers, blank lines
            }
            var s = new DiskSnapshot ();
            s.id = f[0];
            s.tag = f[1];
            s.size = "%s %s".printf (f[2], f[3]);
            s.taken = "%s %s".printf (f[4], f[5]);
            list += s;
        }
        return list;
    }

    public static async bool run (string disk, string[] verb, out string output) {
        string[] argv = { "qemu-img", "snapshot" };
        foreach (var v in verb) {
            argv += v;
        }
        argv += disk;
        try {
            var p = new Subprocess.newv (argv, SubprocessFlags.STDOUT_PIPE | SubprocessFlags.STDERR_MERGE);
            string o;
            yield p.communicate_utf8_async (null, null, out o, null);
            output = o ?? "";
            return p.get_exit_status () == 0;
        } catch (Error e) {
            output = e.message;
            return false;
        }
    }
}

public class SnapshotsCard : Gtk.Box {
    private Machine machine;
    private Gtk.Box rows = new Gtk.Box (Gtk.Orientation.VERTICAL, 0);
    private Gtk.Entry name_entry = new Gtk.Entry ();
    private Gtk.Button take = new Gtk.Button.with_label ("Take Snapshot");
    private Gtk.Label note = new Gtk.Label ("");
    private bool busy = false;

    public signal void toast (string text);

    public SnapshotsCard (Machine machine) {
        Object (orientation: Gtk.Orientation.VERTICAL, spacing: 8);
        this.machine = machine;
        add_css_class ("ml-form-row");
        var title = new Gtk.Label ("Snapshots");
        title.xalign = 0;
        title.add_css_class ("heading");
        append (title);
        note.xalign = 0;
        note.wrap = true;
        note.add_css_class ("dim-label");
        append (note);

        var add = new Gtk.Box (Gtk.Orientation.HORIZONTAL, 8);
        name_entry.placeholder_text = "Name, e.g. before-upgrade";
        name_entry.hexpand = true;
        name_entry.max_length = 48;
        add.append (name_entry);
        take.add_css_class ("suggested-action");
        take.clicked.connect (() => do_take.begin ());
        name_entry.activate.connect (() => do_take.begin ());
        add.append (take);
        append (add);
        append (rows);
        update ();
    }

    private string disk () {
        return Path.build_filename (machine.dir, "disk.qcow2");
    }

    /* Called whenever the machine changes state. */
    public void update () {
        bool can = !machine.running && machine.has_disk ();
        name_entry.sensitive = can && !busy;
        take.sensitive = can && !busy;
        if (machine.running) {
            note.label = "Shut the machine down to take or restore a snapshot. A snapshot saves the disk, not the running memory.";
        } else if (!machine.has_disk ()) {
            note.label = "Snapshots become available once the machine has a disk.";
        } else {
            note.label = "Restore points for this machine's disk. Restoring rolls the disk back and discards later changes.";
        }
        reload.begin ();
    }

    private async void reload () {
        if (!machine.has_disk ()) {
            clear_rows ();
            return;
        }
        string o;
        yield Snapshots.run (disk (), { "-l" }, out o);
        clear_rows ();
        bool can = !machine.running && !busy;
        foreach (var s in Snapshots.parse (o)) {
            var row = new Gtk.Box (Gtk.Orientation.HORIZONTAL, 8);
            row.margin_top = 4;
            var info = new Gtk.Box (Gtk.Orientation.VERTICAL, 0);
            info.hexpand = true;
            var l = new Gtk.Label (s.tag);
            l.xalign = 0;
            info.append (l);
            var d = new Gtk.Label ("%s · %s".printf (s.taken, s.size));
            d.xalign = 0;
            d.add_css_class ("dim-label");
            info.append (d);
            row.append (info);
            var restore = new Gtk.Button.with_label ("Restore…");
            restore.sensitive = can;
            var tag = s.tag;
            restore.clicked.connect (() => confirm_restore.begin (tag));
            row.append (restore);
            var del = new Gtk.Button.from_icon_name ("user-trash-symbolic");
            del.add_css_class ("flat");
            del.tooltip_text = "Delete this snapshot";
            del.sensitive = can;
            del.clicked.connect (() => do_delete.begin (tag));
            row.append (del);
            rows.append (row);
        }
    }

    private void clear_rows () {
        Gtk.Widget? c;
        while ((c = rows.get_first_child ()) != null) {
            rows.remove (c);
        }
    }

    private async void do_take () {
        string tag = name_entry.text.strip ();
        if (!Snapshots.valid_tag (tag)) {
            toast ("Use letters, numbers, dots, dashes and underscores (up to 48).");
            return;
        }
        busy = true;
        string o;
        bool ok = yield Snapshots.run (disk (), { "-c", tag }, out o);
        busy = false;
        toast (ok ? "Snapshot “%s” saved".printf (tag) : "Snapshot failed: " + o.strip ());
        if (ok) {
            name_entry.text = "";
        }
        update ();
    }

    private async void confirm_restore (string tag) {
        var dlg = new Gtk.AlertDialog ("Restore “%s”?".printf (tag));
        dlg.detail = "The disk goes back to how it was then. Everything done in the machine since is lost. Take a new snapshot first if you may want it.";
        dlg.buttons = { "Cancel", "Restore" };
        dlg.cancel_button = 0;
        dlg.default_button = 0;
        try {
            int r = yield dlg.choose ((Gtk.Window) get_root (), null);
            if (r != 1) {
                return;
            }
        } catch (Error e) {
            return;
        }
        busy = true;
        string o;
        bool ok = yield Snapshots.run (disk (), { "-a", tag }, out o);
        busy = false;
        toast (ok ? "Restored “%s”".printf (tag) : "Restore failed: " + o.strip ());
        update ();
    }

    private async void do_delete (string tag) {
        busy = true;
        string o;
        bool ok = yield Snapshots.run (disk (), { "-d", tag }, out o);
        busy = false;
        toast (ok ? "Deleted “%s”".printf (tag) : "Delete failed: " + o.strip ());
        update ();
    }
}
