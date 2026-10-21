/* SPDX-License-Identifier: GPL-3.0-or-later */
/* fprintd client: D-Bus interfaces plus the few facts the page needs.
 *
 * Everything here is asynchronous so the Settings main loop never blocks on the
 * Secure Enclave. The environment hooks at the bottom exist only so the page can
 * be exercised against a fake fprintd; they are not user-facing options.
 */
namespace MSeriesTouchId {
    public const string FPRINT_BUS_NAME = "net.reactivated.Fprint";
    public const string FPRINT_MANAGER_PATH = "/net/reactivated/Fprint/Manager";

    /* Most fingerprints one person can enrol, as on macOS. The enclave template
     * store is small and enrol/delete cycles are not free (see the xART notes in
     * mseries/aurora-sep/README.md), so the page does not offer more. */
    public const int MAX_FINGERS = 3;

    [DBus (name = "net.reactivated.Fprint.Manager")]
    public interface FprintManager : GLib.Object {
        public abstract async GLib.ObjectPath get_default_device () throws GLib.Error;
    }

    [DBus (name = "net.reactivated.Fprint.Device")]
    public interface FprintDevice : GLib.Object {
        public abstract async void claim (string username) throws GLib.Error;
        public abstract async void release () throws GLib.Error;
        public abstract async void enroll_start (string finger_name) throws GLib.Error;
        public abstract async void enroll_stop () throws GLib.Error;
        public abstract async string[] list_enrolled_fingers (string username) throws GLib.Error;
        public abstract async void delete_enrolled_finger (string finger_name) throws GLib.Error;

        [DBus (name = "name")]
        public abstract string name { owned get; }
        [DBus (name = "num-enroll-stages")]
        public abstract int num_enroll_stages { owned get; }

        public signal void enroll_status (string result, bool done);
    }

    /* Fingers offered in this order; the first one not yet enrolled is used. */
    public const string[] FINGER_ORDER = {
        "right-index-finger", "left-index-finger", "right-thumb", "left-thumb",
        "right-middle-finger", "left-middle-finger", "right-ring-finger",
        "left-ring-finger", "right-little-finger", "left-little-finger"
    };

    /* A small stable number per finger so each print is drawn with its own ridge pattern. */
    public int finger_seed (string name) {
        return (int) (GLib.str_hash (name) % 97);
    }

    public string finger_label (string name) {
        var text = name.replace ("-", " ");
        return text.substring (0, 1).up () + text.substring (1);
    }

    public string? next_free_finger (string[] enrolled) {
        foreach (var candidate in FINGER_ORDER) {
            if (!(candidate in enrolled)) {
                return candidate;
            }
        }
        return null;
    }

    /* Why Touch ID is unavailable, in words the page can show. */
    public errordomain TouchIdError {
        NO_ENCLAVE,
        NO_DEVICE
    }

    public class Hooks {
        private static string? hook (string name) {
            return GLib.Environment.get_variable (name);
        }

        /* MSERIES_TOUCHID_TEST=1 points the page at the session bus, a temp PAM
         * directory and an unprivileged helper invocation. */
        public static bool test_mode () {
            return hook ("MSERIES_TOUCHID_TEST") == "1";
        }

        public static GLib.BusType bus () {
            return test_mode () ? GLib.BusType.SESSION : GLib.BusType.SYSTEM;
        }

        public static string pam_dir () {
            return (test_mode () ? hook ("MSERIES_TOUCHID_PAM_DIR") : null) ?? "/etc/pam.d";
        }

        public static string sep_node () {
            return (test_mode () ? hook ("MSERIES_TOUCHID_SEP_NODE") : null) ?? "/dev/sep-bio";
        }

        public static string helper () {
            return (test_mode () ? hook ("MSERIES_TOUCHID_HELPER") : null)
                ?? "/usr/local/sbin/mseries-aurora-touchid-apply-pam";
        }

        /* A directory of fake driver attributes for the tests. */
        public static string? diag_dir () {
            return test_mode () ? hook ("MSERIES_TOUCHID_DIAG_DIR") : null;
        }

        public static string user () {
            return GLib.Environment.get_user_name ();
        }
    }

    /* A sensor that fprintd has found, with its proxy. */
    public class Sensor : GLib.Object {
        public FprintDevice device { get; private set; }
        public string title { get; private set; }
        public int stages { get; private set; }

        private Sensor (FprintDevice device) {
            this.device = device;
            title = device.name;
            stages = device.num_enroll_stages;
            if (stages <= 0) {
                stages = 1;
            }
        }

        public static async Sensor open () throws GLib.Error {
            if (!GLib.FileUtils.test (Hooks.sep_node (), GLib.FileTest.EXISTS)) {
                throw new TouchIdError.NO_ENCLAVE ("The Secure Enclave biometric device is missing.");
            }
            FprintManager manager = yield GLib.Bus.get_proxy<FprintManager> (
                Hooks.bus (), FPRINT_BUS_NAME, FPRINT_MANAGER_PATH);
            GLib.ObjectPath path;
            try {
                path = yield manager.get_default_device ();
            } catch (GLib.Error e) {
                throw new TouchIdError.NO_DEVICE ("%s", e.message);
            }
            FprintDevice device = yield GLib.Bus.get_proxy<FprintDevice> (
                Hooks.bus (), FPRINT_BUS_NAME, (string) path);
            return new Sensor (device);
        }

        public async string[] enrolled () throws GLib.Error {
            try {
                return yield device.list_enrolled_fingers (Hooks.user ());
            } catch (GLib.Error e) {
                /* fprintd reports "no prints" as an error, not an empty list. */
                if (e.message.contains ("NoEnrolledPrints")) {
                    return new string[0];
                }
                throw e;
            }
        }

        public async void remove (string finger) throws GLib.Error {
            yield device.claim (Hooks.user ());
            try {
                yield device.delete_enrolled_finger (finger);
            } finally {
                try {
                    yield device.release ();
                } catch (GLib.Error e) {
                    GLib.warning ("Releasing the sensor failed: %s", e.message);
                }
            }
        }
    }

    /* Which password prompts use the fingerprint, read straight from /etc/pam.d. */
    public bool pam_uses_fingerprint (string service) {
        var path = GLib.Path.build_filename (Hooks.pam_dir (), service);
        string contents;
        try {
            GLib.FileUtils.get_contents (path, out contents);
        } catch (GLib.FileError e) {
            return false;
        }
        try {
            var re = new GLib.Regex ("^\\s*auth\\s+\\S+\\s+pam_fprintd\\.so", GLib.RegexCompileFlags.MULTILINE);
            return re.match (contents);
        } catch (GLib.RegexError e) {
            return false;
        }
    }

    /* Run the PAM helper. Returns an empty string on success, else a reason. */
    public async string set_pam (string service, bool enable) {
        string[] argv = {};
        if (!Hooks.test_mode ()) {
            argv += "pkexec";
        }
        argv += Hooks.helper ();
        argv += "--only";
        argv += service;
        if (!enable) {
            argv += "--remove";
        }
        try {
            var proc = new GLib.Subprocess.newv (argv,
                GLib.SubprocessFlags.STDERR_PIPE | GLib.SubprocessFlags.STDOUT_SILENCE);
            string? err_text;
            yield proc.communicate_utf8_async (null, null, null, out err_text);
            if (proc.get_successful ()) {
                return "";
            }
            /* pkexec exits 126 when the user dismisses the password prompt. */
            if (proc.get_exit_status () == 126 || proc.get_exit_status () == 127) {
                return "Cancelled";
            }
            return (err_text != null && err_text.strip () != "") ? err_text.strip () : "The helper failed";
        } catch (GLib.Error e) {
            return e.message;
        }
    }
}
