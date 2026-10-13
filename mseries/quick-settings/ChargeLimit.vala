/* SPDX-License-Identifier: GPL-3.0-or-later
 * Battery charge limit switch for Apple Silicon (macsmc-battery). Changing it asks for your
 * administrator password through polkit; the privileged work is done by mseries-power. */
public class QuickSettings.ChargeLimit : Gtk.Box {
    private const string SYSFS = "/sys/class/power_supply/macsmc-battery/charge_control_end_threshold";
    private const string HELPER = "/usr/local/sbin/mseries-power";

    private Granite.SwitchModelButton toggle;
    private bool updating = false;
    private bool busy = false;

    construct {
        orientation = VERTICAL;
        visible = FileUtils.test (SYSFS, FileTest.EXISTS) && FileUtils.test (HELPER, FileTest.IS_EXECUTABLE);

        toggle = new Granite.SwitchModelButton (_("Limit Charging to 80%")) {
            description = _("Keeps the battery healthier while plugged in")
        };
        append (toggle);

        refresh ();
        toggle.notify["active"].connect (on_toggled);
        // The limit can change from the terminal or at boot, so re-read it whenever the menu opens.
        map.connect (refresh);
    }

    private int read_limit () {
        try {
            string contents;
            FileUtils.get_contents (SYSFS, out contents);
            return int.parse (contents.strip ());
        } catch (Error e) {
            return -1;
        }
    }

    private void refresh () {
        if (busy) {
            return;
        }

        var limit = read_limit ();
        if (limit < 0) {
            visible = false;
            return;
        }

        updating = true;
        toggle.active = limit < 100;
        updating = false;
    }

    private void on_toggled () {
        if (updating || busy) {
            return;
        }

        busy = true;
        toggle.sensitive = false;
        apply.begin (toggle.active ? "80" : "100");
    }

    private async void apply (string target) {
        try {
            var process = new Subprocess (SubprocessFlags.STDOUT_SILENCE | SubprocessFlags.STDERR_SILENCE,
                "pkexec", HELPER, "limit", target);
            yield process.wait_check_async ();
        } catch (Error e) {
            // Password prompt dismissed or the helper failed: fall back to the real state below.
            info ("Charge limit not changed: %s", e.message);
        }

        busy = false;
        toggle.sensitive = true;
        refresh ();
    }
}
