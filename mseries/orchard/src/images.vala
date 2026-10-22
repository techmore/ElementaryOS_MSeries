/* Ready-made disk images: load a bootable disk instead of running an installer, and save a
 * machine's disk as an image to reuse or share. Everything goes through qemu-img, and an image
 * is checked before it is trusted: its format must be known and it must not point at another
 * file on this Mac (a qcow2 "backing file" could otherwise expose host files to the guest). */

public class DiskImages : Object {
    public const string[] DISK_EXTS = { ".qcow2", ".img", ".raw", ".vmdk", ".vdi" };
    /* Free space to keep beyond the image itself (tests lower it). */
    public static int64 margin_bytes = 2147483648LL;
    public const string[] ALLOWED_FORMATS = { "qcow2", "raw", "vmdk", "vdi" };

    public struct Info {
        public string format;
        public int64 virtual_size;
        public bool has_backing;
    }

    /* How the file is packed: zip (e.g. a UTM bundle), a compressed stream, or a plain disk. */
    public static string kind_of (string path) {
        string p = path.down ();
        if (p.has_suffix (".zip")) return "zip";
        if (p.has_suffix (".xz")) return "xz";
        if (p.has_suffix (".zst")) return "zst";
        if (p.has_suffix (".gz")) return "gz";
        return "disk";
    }

    public static bool is_disk_name (string name) {
        string n = name.down ();
        foreach (var e in DISK_EXTS) {
            if (n.has_suffix (e)) return true;
        }
        return false;
    }

    /* Picks the disk inside a zip listing (`unzip -Zl` lines): the biggest disk file that is not
     * firmware variables. UTM bundles keep it under Data/. */
    public static string? pick_zip_entry (string listing) {
        string? best = null;
        int64 best_size = -1;
        foreach (var line in listing.split ("\n")) {
            string[] f = {};
            foreach (var w in line.strip ().split (" ")) {
                if (w != "") f += w;
            }
            if (f.length < 9 || f[0].length < 10 || f[0][0] == 'd') continue;
            int64 size = int64.parse (f[3]);
            // The name follows the HH:MM time column (the columns before it vary between unzip versions).
            int t = -1;
            for (int k = 4; k < f.length - 1; k++) {
                if (f[k].length == 5 && f[k][2] == ':') {
                    t = k;
                    break;
                }
            }
            if (t < 0) continue;
            string name = string.joinv (" ", f[t + 1:f.length]);
            if (!is_disk_name (name) || name.down ().contains ("efi") || name.down ().contains ("nvram")) continue;
            if (size > best_size) {
                best_size = size;
                best = name;
            }
        }
        return best;
    }

    public static bool allowed_format (string f) {
        foreach (var a in ALLOWED_FORMATS) {
            if (a == f) return true;
        }
        return false;
    }

    public static Info? parse_info (string json) {
        try {
            var parser = new Json.Parser ();
            parser.load_from_data (json);
            var o = parser.get_root ().get_object ();
            Info i = Info ();
            i.format = o.get_string_member ("format");
            i.virtual_size = o.get_int_member ("virtual-size");
            i.has_backing = o.has_member ("backing-filename") || o.has_member ("full-backing-filename");
            return i;
        } catch (Error e) {
            return null;
        }
    }

    private static async bool run (string[] argv, string? out_file, out string output) {
        try {
            string[] full = argv;
            SubprocessLauncher l;
            if (out_file == null) {
                l = new SubprocessLauncher (SubprocessFlags.STDOUT_PIPE | SubprocessFlags.STDERR_MERGE);
            } else {
                // Stream a command's stdout into a file (decompressing, unzipping).
                l = new SubprocessLauncher (SubprocessFlags.STDERR_SILENCE);
                l.setenv ("ML_OUT", out_file, true);
                full = { "sh", "-c", "exec \"$@\" > \"$ML_OUT\"", "sh" };
                foreach (var a in argv) full += a;
            }
            var p = l.spawnv (full);
            string o = "";
            if (out_file == null) {
                yield p.communicate_utf8_async (null, null, out o, null);
            } else {
                yield p.wait_async ();
            }
            output = o ?? "";
            return p.get_exit_status () == 0;
        } catch (Error e) {
            output = e.message;
            return false;
        }
    }

    private static int64 free_bytes (string dir) {
        try {
            var f = File.new_for_path (dir);
            while (!f.query_exists () && f.get_parent () != null) f = f.get_parent ();
            return (int64) f.query_filesystem_info ("filesystem::free").get_attribute_uint64 ("filesystem::free");
        } catch (Error e) {
            return -1;
        }
    }

    private static void rm_tree (string path) {
        try {
            var d = Dir.open (path);
            string? n;
            while ((n = d.read_name ()) != null) {
                FileUtils.unlink (Path.build_filename (path, n));
            }
        } catch (Error e) {}
        DirUtils.remove (path);
    }

    /* Imports `src` as the machine's disk (dir/disk.qcow2). Never called on an installed machine. */
    public static async bool import_image (string src, string dir, out string message) {
        DirUtils.create_with_parents (dir, 0755);
        string tmp = Path.build_filename (dir, ".import");
        rm_tree (tmp);
        DirUtils.create_with_parents (tmp, 0700);
        string o;
        string source = src;
        string kind = kind_of (src);
        string raw = Path.build_filename (tmp, "unpacked");
        if (kind == "zip") {
            if (Environment.find_program_in_path ("unzip") == null) {
                message = "Install unzip to open .zip images.";
                rm_tree (tmp);
                return false;
            }
            yield run ({ "unzip", "-Zl", src }, null, out o);
            string? entry = pick_zip_entry (o);
            if (entry == null) {
                message = "No disk image (.qcow2, .img, .raw, .vmdk, .vdi) found inside that zip.";
                rm_tree (tmp);
                return false;
            }
            if (!(yield run ({ "unzip", "-p", src, entry }, raw, out o))) {
                message = "Could not unpack the zip: " + o.strip ();
                rm_tree (tmp);
                return false;
            }
            source = raw;
        } else if (kind != "disk") {
            string tool = kind == "xz" ? "xz" : (kind == "zst" ? "zstd" : "gzip");
            if (Environment.find_program_in_path (tool) == null) {
                message = "Install %s to open this image.".printf (tool);
                rm_tree (tmp);
                return false;
            }
            if (!(yield run ({ tool, "-dc", src }, raw, out o))) {
                message = "Could not decompress the image: " + o.strip ();
                rm_tree (tmp);
                return false;
            }
            source = raw;
        }

        // Look before trusting: only known formats, and nothing that reaches outside the file.
        if (!(yield run ({ "qemu-img", "info", "--output=json", "-U", source }, null, out o))) {
            message = "That file is not a disk image qemu-img can read.";
            rm_tree (tmp);
            return false;
        }
        var info = parse_info (o);
        if (info == null || !allowed_format (info.format)) {
            message = "Unsupported disk format. Use qcow2, raw, vmdk or vdi.";
            rm_tree (tmp);
            return false;
        }
        if (info.format == "raw" && (info.virtual_size < 1048576 || info.virtual_size % 512 != 0)) {
            message = "That file does not look like a disk image (a raw disk is at least 1 MiB and a whole number of sectors).";
            rm_tree (tmp);
            return false;
        }
        if (info.has_backing) {
            message = "That image depends on another file on its original computer. Flatten it first (qemu-img convert) and try again.";
            rm_tree (tmp);
            return false;
        }
        int64 need = 0;
        try {
            need = (int64) File.new_for_path (source).query_info ("standard::size", FileQueryInfoFlags.NONE).get_size ();
        } catch (Error e) {}
        int64 free = free_bytes (dir);
        if (free >= 0 && free < need + margin_bytes) {
            message = "Not enough free space: about %d GiB needed, %d GiB free.".printf (
                (int) ((need + margin_bytes) / 1073741824), (int) (free / 1073741824));
            rm_tree (tmp);
            return false;
        }

        string out_disk = Path.build_filename (tmp, "disk.qcow2");
        if (!(yield run ({ "qemu-img", "convert", "-f", info.format, "-O", "qcow2", source, out_disk }, null, out o))) {
            message = "Converting the image failed: " + o.strip ();
            rm_tree (tmp);
            return false;
        }
        string final_disk = Path.build_filename (dir, "disk.qcow2");
        if (FileUtils.rename (out_disk, final_disk) != 0) {
            message = "Could not place the disk in the machine folder.";
            rm_tree (tmp);
            return false;
        }
        FileUtils.unlink (Path.build_filename (dir, "efi-vars.fd"));   // fresh firmware settings for the new disk
        try {
            FileUtils.set_contents (Path.build_filename (dir, "imported"),
                "%s\n%s\n".printf (Path.get_basename (src), new DateTime.now_local ().format ("%F %T")));
        } catch (Error e) {}
        rm_tree (tmp);
        message = "Loaded %s (%d GiB virtual disk).".printf (Path.get_basename (src), (int) (info.virtual_size / 1073741824));
        return true;
    }

    /* Saves the machine's disk as a compressed qcow2 for reuse or sharing. */
    public static async bool export_image (string dir, string dest, out string message) {
        string disk = Path.build_filename (dir, "disk.qcow2");
        string partial = dest + ".partial";
        string o;
        if (!(yield run ({ "qemu-img", "convert", "-c", "-O", "qcow2", disk, partial }, null, out o))) {
            FileUtils.unlink (partial);
            message = "Saving the image failed: " + o.strip ();
            return false;
        }
        if (FileUtils.rename (partial, dest) != 0) {
            FileUtils.unlink (partial);
            message = "Could not write " + dest;
            return false;
        }
        message = "Saved " + Path.get_basename (dest);
        return true;
    }
}
