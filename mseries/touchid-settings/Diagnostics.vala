/* SPDX-License-Identifier: GPL-3.0-or-later */
/* What the Secure Enclave driver says about itself, read from sysfs.
 *
 * apple_sep publishes small read-only attributes under
 * /sys/bus/platform/drivers/apple_sep/<device>/diag/. The page shows them in a
 * Details section and uses two of them (`touchid`, `matching`) to explain, in
 * words, why Touch ID cannot be used yet. Reading is cheap and never touches the
 * sensor. */
namespace MSeriesTouchId {
    public class DriverDiag : GLib.Object {
        private GLib.HashTable<string, string> values =
            new GLib.HashTable<string, string> (GLib.str_hash, GLib.str_equal);

        public bool available { get; private set; default = false; }

        /* Attribute names in the order the Details section lists them. */
        public const string[] ORDER = {
            "touchid", "sensor", "matching", "restore", "keybag", "xart", "xart_guard",
            "xart_guard_list", "xart_guard_refusals", "profile", "boot", "endpoints"
        };

        public string? get (string key) {
            return values.lookup (key);
        }

        private static string? find_dir () {
            /* In test mode only the fake directory counts; never read the real driver. */
            if (Hooks.test_mode ()) {
                return Hooks.diag_dir ();
            }
            const string root = "/sys/bus/platform/drivers/apple_sep";
            try {
                var dir = GLib.Dir.open (root);
                string? name;
                while ((name = dir.read_name ()) != null) {
                    var candidate = GLib.Path.build_filename (root, name, "diag");
                    if (GLib.FileUtils.test (candidate, GLib.FileTest.IS_DIR)) {
                        return candidate;
                    }
                }
            } catch (GLib.FileError e) {
                /* no driver bound */
            }
            return null;
        }

        public static DriverDiag read () {
            var diag = new DriverDiag ();
            var dir = find_dir ();
            if (dir == null) {
                return diag;
            }
            foreach (var key in ORDER) {
                string contents;
                try {
                    GLib.FileUtils.get_contents (GLib.Path.build_filename (dir, key), out contents);
                    diag.values.insert (key, contents.strip ());
                    diag.available = true;
                } catch (GLib.FileError e) {
                    /* attribute not present on this driver version */
                }
            }
            return diag;
        }

        public static string label (string key) {
            switch (key) {
                case "touchid": return "Touch ID";
                case "sensor": return "Sensor";
                case "matching": return "Matching";
                case "restore": return "Saved fingerprints";
                case "keybag": return "Key bag";
                case "xart": return "xART storage";
                case "xart_guard": return "xART guard level";
                case "xart_guard_list": return "xART ownership list";
                case "xart_guard_refusals": return "Refused xART writes";
                case "profile": return "Platform profile";
                case "boot": return "Enclave boot";
                case "endpoints": return "Enclave endpoints";
                default: return key;
            }
        }

        /* One sentence for each value a person might have to act on. */
        public static string? explanation (string key, string value) {
            if (key == "matching" && value == "blocked") {
                return "Matching is switched off by the xART guard on this Mac, so a fingerprint cannot unlock anything yet.";
            }
            if (key == "touchid" && value == "not-ready") {
                return "The sensor did not finish starting. Restarting the Mac recovers it.";
            }
            if (key == "sensor" && value != "online") {
                return "The fingerprint sensor is not responding.";
            }
            return null;
        }
    }
}
