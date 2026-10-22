public class SystemWindow : Gtk.Window {
    private IncusClient client;
    private Gtk.TextView properties;
    private Gtk.TextView journal;
    private Gtk.Label status;
    private bool busy = false;
    public SystemWindow (Gtk.Window parent, IncusClient api) {
        Object (transient_for: parent, title: "Incus system", default_width: 740, default_height: 560);
        client = api;
        var box = new Gtk.Box (Gtk.Orientation.VERTICAL, 12) { margin_top = 12, margin_bottom = 12, margin_start = 12, margin_end = 12 };
        var actions = new Gtk.Box (Gtk.Orientation.HORIZONTAL, 8);
        var refresh = new Gtk.Button.with_label ("Refresh system properties"); refresh.clicked.connect (() => load.begin ()); actions.append (refresh);
        foreach (var verb in new string[] { "start", "stop", "restart" }) {
            var button = new Gtk.Button.with_label (verb + " Incus");
            var action = verb;
            button.clicked.connect (() => {
                var question = new Gtk.AlertDialog ("%s the Incus daemon?".printf (action)) {
                    detail = "This changes the host Incus service and socket for every local instance, including Rupert. Administrator authentication is required.",
                    buttons = { "Cancel", "Confirm" }, cancel_button = 0, default_button = 0
                };
                question.choose.begin (this, null, (obj, result) => { try { if (question.choose.end (result) == 1) control.begin (action); } catch (Error e) { } });
            }); actions.append (button);
        }
        box.append (actions);
        var tabs = new Gtk.Stack () { vexpand = true };
        var switcher = new Gtk.StackSwitcher () { stack = tabs, halign = Gtk.Align.CENTER }; box.append (switcher);
        properties = new Gtk.TextView () { editable = false, monospace = true, left_margin = 12, right_margin = 12 };
        tabs.add_titled (new Gtk.ScrolledWindow () { child = properties }, "properties", "Properties and resources");
        var logs_box = new Gtk.Box (Gtk.Orientation.VERTICAL, 8);
        var read = new Gtk.Button.with_label ("Read latest daemon journal"); read.clicked.connect (() => read_journal.begin ()); logs_box.append (read);
        journal = new Gtk.TextView () { editable = false, monospace = true };
        logs_box.append (new Gtk.ScrolledWindow () { child = journal, vexpand = true }); tabs.add_titled (logs_box, "journal", "Daemon logs");
        box.append (tabs); status = new Gtk.Label ("") { xalign = 0, wrap = true }; box.append (status); child = box;
        load.begin ();
    }
    private async void load () {
        try {
            var response = yield client.call ("GET", "/1.0");
            var metadata = response.get_object_member ("metadata");
            var env = metadata.get_object_member ("environment");
            var safe = new Json.Object ();
            foreach (var key in new string[] { "server_version", "server_name", "server_clustered", "kernel", "kernel_version", "kernel_architecture", "os_name", "os_version", "driver", "driver_version", "storage", "storage_version", "architectures", "project" }) if (env.has_member (key)) safe.set_member (key, env.get_member (key).copy ());
            properties.buffer.text = IncusClient.json_string (safe);
            var resources = yield client.call ("GET", "/1.0/resources");
            properties.buffer.text += "\n\nHost resources\n" + IncusClient.json_string (resources.get_object_member ("metadata"));
            status.label = "Native Incus API version " + metadata.get_string_member_with_default ("api_version", "unknown");
        } catch (Error e) { status.label = "Incus unavailable: " + e.message; }
    }
    private async void control (string verb) {
        if (busy) return;
        busy = true;
        try {
            var process = new Subprocess.newv ({ "pkexec", "/usr/bin/systemctl", verb, "incus.service", "incus.socket" }, SubprocessFlags.STDOUT_PIPE | SubprocessFlags.STDERR_MERGE);
            string? output;
            yield process.communicate_utf8_async (null, null, out output, null);
            if (!process.get_successful ()) throw new IOError.FAILED (output ?? "Incus service action failed or was cancelled.");
            yield load ();
        } catch (Error e) { status.label = e.message; }
        busy = false;
    }
    private async void read_journal () {
        try {
            var process = new Subprocess.newv ({ "journalctl", "-u", "incus.service", "--no-pager", "-n", "500" }, SubprocessFlags.STDOUT_PIPE | SubprocessFlags.STDERR_MERGE);
            string? output;
            yield process.communicate_utf8_async (null, null, out output, null);
            journal.buffer.text = output ?? "";
            status.label = process.get_successful () ? "Latest host Incus journal loaded." : "The current desktop user cannot read the Incus journal.";
        } catch (Error e) { status.label = e.message; }
    }
}
