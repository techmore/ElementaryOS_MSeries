/* The virtio-win driver ISO and the answer-file media for Windows guests.
 *
 * Policy (issue #265): the ISO is a pinned release, never "latest". Its SHA-256 and size are compiled in;
 * a file that does not match is never attached. Nothing is downloaded unless the user presses the
 * Download button, the download goes to a .partial file over HTTPS only, and the file is moved into place
 * only after its checksum matches. A failed or corrupt download leaves no usable file behind. */

public class VirtioWin : Object {
    /* Fedora's archived stable virtio-win release (Red Hat signed drivers), the same ISO documented in
     * mseries/OS9-HANDOFF.md. */
    public const string VERSION = "0.1.302";
    public const string DEFAULT_URL = "https://fedorapeople.org/groups/virt/virtio-win/direct-downloads/archive-virtio/virtio-win-0.1.302-1/virtio-win-0.1.302.iso";
    public const string SHA256 = "303f7ae40dad495d6ae474fdc571df58958a4dbc5c37a522d80f9a203867949d";
    public const int64 SIZE = 877373440;

    /* Tests can point the download somewhere unreachable; the checksum still decides what is accepted. */
    public static string url () {
        return Environment.get_variable ("MACHINE_LAB_VIRTIO_URL") ?? DEFAULT_URL;
    }

    public static string cache_dir () {
        return Path.build_filename (Environment.get_user_data_dir (), "machine-lab", "cache", "virtio-win");
    }

    public static string cache_path () {
        return Path.build_filename (cache_dir (), "virtio-win-%s.iso".printf (VERSION));
    }

    /* Where an ISO may already be: our cache, then the folder mseries-vm's docs use. */
    public static string[] candidates () {
        return {
            cache_path (),
            Path.build_filename (Machine.vms_dir (), "downloads", "virtio-win", "virtio-win.iso")
        };
    }

    public static int64 file_size (string path) {
        try {
            return File.new_for_path (path).query_info ("standard::size", FileQueryInfoFlags.NONE).get_size ();
        } catch (Error e) {
            return -1;
        }
    }

    /* A candidate that exists and has the pinned size (cheap: the checksum comes later). */
    public static string? find_present () {
        foreach (var c in candidates ()) {
            if (file_size (c) == SIZE) {
                return c;
            }
        }
        return null;
    }

    /* SHA-256 of a file as lower-case hex, or null when it cannot be read. Blocking. */
    public static string? sha256_file (string path) {
        try {
            var stream = File.new_for_path (path).read ();
            var sum = new Checksum (ChecksumType.SHA256);
            var buf = new uint8[1048576];
            ssize_t n;
            while ((n = stream.read (buf)) > 0) {
                sum.update (buf, n);
            }
            stream.close ();
            return sum.get_string ();
        } catch (Error e) {
            return null;
        }
    }

    /* Blocking check against expected values: a sentence for the user in `message` on failure. */
    public static bool verify_file (string path, string expected_sha256, int64 expected_size, out string message) {
        int64 size = file_size (path);
        if (size < 0) {
            message = "%s cannot be read.".printf (path);
            return false;
        }
        if (size != expected_size) {
            message = "%s is %s bytes, expected %s: the download is incomplete or the wrong file.".printf (
                Path.get_basename (path), size.to_string (), expected_size.to_string ());
            return false;
        }
        string? got = sha256_file (path);
        if (got == null) {
            message = "%s cannot be read.".printf (path);
            return false;
        }
        if (got != expected_sha256) {
            message = "Checksum mismatch for %s: expected %s, got %s. The file is corrupt or not the pinned virtio-win %s.".printf (
                Path.get_basename (path), expected_sha256, got, VERSION);
            return false;
        }
        message = "Checksum verified (SHA-256 %s…).".printf (expected_sha256.substring (0, 12));
        return true;
    }

    /* Same as verify_file, off the main thread. */
    public static async bool verify_async (string path, string expected_sha256, int64 expected_size, out string message) {
        string msg = "";
        bool ok = false;
        SourceFunc resume = verify_async.callback;
        new Thread<void> ("ml-virtio-sha", () => {
            ok = verify_file (path, expected_sha256, expected_size, out msg);
            Idle.add ((owned) resume);
        });
        yield;
        message = msg;
        return ok;
    }

    public delegate void ProgressFunc (int64 done, int64 total);

    /* Downloads the pinned ISO into the cache. Only ever called from an explicit user action.
     * On success the verified file is at cache_path(); on any failure nothing usable is left behind. */
    public static async bool download (ProgressFunc? progress, out string message) {
        if (Environment.find_program_in_path ("curl") == null) {
            message = "curl is not installed. Install it (sudo apt install curl) and try again.";
            return false;
        }
        string dir = cache_dir ();
        if (DirUtils.create_with_parents (dir, 0755) != 0) {
            message = "Cannot create %s.".printf (dir);
            return false;
        }
        int64 free = free_bytes (dir);
        string part = cache_path () + ".partial";
        int64 have = int64.max (0, file_size (part));
        if (free >= 0 && free < SIZE - have + 1073741824) {
            message = "Not enough free space: virtio-win needs %d MiB plus 1 GiB spare, %d MiB is free.".printf (
                (int) (SIZE / 1048576), (int) (free / 1048576));
            return false;
        }

        string code = "";
        bool launched = true;
        Subprocess? p = null;
        try {
            // https only (also for redirects); resume a previous partial file; fail on HTTP errors.
            p = new Subprocess (SubprocessFlags.STDERR_PIPE | SubprocessFlags.STDOUT_SILENCE,
                "curl", "--fail", "--location", "--silent", "--show-error",
                "--proto", "=https", "--proto-redir", "=https",
                "--connect-timeout", "20", "--retry", "3", "--continue-at", "-",
                "--output", part, url ());
        } catch (Error e) {
            launched = false;
            code = e.message;
        }
        if (!launched || p == null) {
            message = "Could not start the download: " + code;
            return false;
        }
        uint poll = 0;
        if (progress != null) {
            poll = Timeout.add (500, () => {
                progress (int64.max (0, file_size (part)), SIZE);
                return Source.CONTINUE;
            });
        }
        string? err = null;
        try {
            yield p.communicate_utf8_async (null, null, null, out err);
        } catch (Error e) {
            err = e.message;
        }
        if (poll != 0) {
            Source.remove (poll);
        }
        if (!p.get_if_exited () || p.get_exit_status () != 0) {
            // Keep the partial file only when the transfer was merely interrupted and can resume.
            message = "Download failed: %s Nothing was installed. Check the connection and try again (the transfer resumes).".printf (
                (err ?? "").strip () == "" ? "the server did not deliver the file." : (err ?? "").strip () + ".");
            return false;
        }
        string vmsg;
        if (!(yield verify_async (part, SHA256, SIZE, out vmsg))) {
            FileUtils.unlink (part);   // a corrupt file must not be resumed or reused
            message = vmsg + " The downloaded file was deleted; use Download to start over.";
            return false;
        }
        if (FileUtils.rename (part, cache_path ()) != 0) {
            message = "Verified, but could not move the file into place at %s.".printf (cache_path ());
            return false;
        }
        message = vmsg;
        return true;
    }

    private static int64 free_bytes (string dir) {
        try {
            var f = File.new_for_path (dir);
            while (!f.query_exists () && f.get_parent () != null) {
                f = f.get_parent ();
            }
            return (int64) f.query_filesystem_info ("filesystem::free").get_attribute_uint64 ("filesystem::free");
        } catch (Error e) {
            return -1;
        }
    }
}

/* The small CD that carries autounattend.xml. Windows Setup looks for it at the root of every drive. */
public class UnattendMedia : Object {
    public static string dir_for (string vm_name) {
        return Path.build_filename (Environment.get_user_data_dir (), "machine-lab", "unattend", vm_name);
    }

    public static string iso_path (string vm_name) {
        return Path.build_filename (dir_for (vm_name), "autounattend.iso");
    }

    /* Writes `xml` as autounattend.xml and packs it into a Joliet ISO with genisoimage. The result is
     * owner-only (it may contain the account password). Never touches anything outside `dir`. */
    public static async bool build (string dir, string xml, out string message) {
        string? tool = Environment.find_program_in_path ("genisoimage") ?? Environment.find_program_in_path ("mkisofs");
        if (tool == null) {
            message = "genisoimage is not installed. Install it (sudo apt install genisoimage) and try again.";
            return false;
        }
        if (DirUtils.create_with_parents (dir, 0700) != 0) {
            message = "Cannot create %s.".printf (dir);
            return false;
        }
        string stage = Path.build_filename (dir, "stage");
        DirUtils.create_with_parents (stage, 0700);
        string xml_path = Path.build_filename (stage, "autounattend.xml");
        string iso = Path.build_filename (dir, "autounattend.iso");
        string part = iso + ".part";
        try {
            FileUtils.set_contents (xml_path, xml);
            FileUtils.chmod (xml_path, 0600);
        } catch (Error e) {
            message = "Could not write the answer file: " + e.message;
            return false;
        }
        string out_text = "";
        bool ok = false;
        try {
            var p = new Subprocess (SubprocessFlags.STDOUT_PIPE | SubprocessFlags.STDERR_MERGE,
                tool, "-quiet", "-volid", "UNATTEND", "-joliet", "-joliet-long", "-rock", "-output", part, stage);
            string? o;
            yield p.communicate_utf8_async (null, null, out o, null);
            out_text = o ?? "";
            ok = p.get_if_exited () && p.get_exit_status () == 0;
        } catch (Error e) {
            out_text = e.message;
        }
        FileUtils.unlink (xml_path);
        DirUtils.remove (stage);
        if (!ok) {
            FileUtils.unlink (part);
            message = "Could not build the answer-file disc: " + out_text.strip ();
            return false;
        }
        FileUtils.chmod (part, 0600);
        if (FileUtils.rename (part, iso) != 0) {
            FileUtils.unlink (part);
            message = "Could not place the answer-file disc at %s.".printf (iso);
            return false;
        }
        message = iso;
        return true;
    }

    /* Removes the disc and its folder (it may hold a password). */
    public static void remove (string vm_name) {
        string d = dir_for (vm_name);
        FileUtils.unlink (iso_path (vm_name));
        FileUtils.unlink (iso_path (vm_name) + ".part");
        DirUtils.remove (d);
    }
}
