public class DeviceEditor : Gtk.Window {
    private IncusClient client;
    private string instance;
    private string kind;
    private Gtk.Entry device_name;
    private Gtk.Entry source;
    private Gtk.Entry target;
    private Gtk.CheckButton read_only;
    private Gtk.Label error_label;
    private Gtk.Button save;

    public DeviceEditor (Gtk.Window parent, IncusClient api, string name, string device_kind) {
        Object (transient_for: parent, modal: true, title: device_kind == "disk" ? "Mount a folder" : device_kind == "proxy" ? "Publish a port" : "Attach a network", default_width: 480);
        client = api; instance = name; kind = device_kind;
        var box = new Gtk.Box (Gtk.Orientation.VERTICAL, 12) { margin_top = 18, margin_bottom = 18, margin_start = 18, margin_end = 18 };
        device_name = new Gtk.Entry () { placeholder_text = "Unique device name" };
        source = new Gtk.Entry ();
        target = new Gtk.Entry ();
        if (kind == "disk") {
            source.placeholder_text = "Host folder, e.g. /home/user/project";
            target.placeholder_text = "Instance folder, e.g. /workspace";
        } else if (kind == "proxy") {
            source.text = "tcp:127.0.0.1:8080";
            target.text = "tcp:127.0.0.1:80";
            box.append (new Gtk.Label ("Listen on the host; connect inside the instance. Use tcp: or udp: and keep 127.0.0.1 for local-only access.") { wrap = true, xalign = 0 });
        } else {
            source.placeholder_text = "Managed network, e.g. incusbr0";
            target.text = "eth1";
        }
        box.append (device_name); box.append (source); box.append (target);
        read_only = new Gtk.CheckButton.with_label ("Read-only mount") { active = true };
        if (kind == "disk") box.append (read_only);
        error_label = new Gtk.Label ("") { wrap = true, xalign = 0 }; box.append (error_label);
        save = new Gtk.Button.with_label ("Add device") { halign = Gtk.Align.END };
        save.clicked.connect (() => apply.begin ()); box.append (save);
        child = box;
    }

    private async void apply () {
        save.sensitive = false;
        try {
            var key = device_name.text.strip ();
            if (key == "" || source.text.strip () == "" || target.text.strip () == "") throw new IOError.INVALID_ARGUMENT ("Complete every field.");
            if (kind == "disk" && (!source.text.has_prefix ("/") || !target.text.has_prefix ("/") || target.text == "/")) throw new IOError.INVALID_ARGUMENT ("Use absolute folder paths; the root disk cannot be replaced here.");
            var response = yield client.inspect_instance (instance);
            var data = response.get_object_member ("metadata");
            var devices = data.get_object_member ("devices");
            if (devices.has_member (key) || (data.has_member ("expanded_devices") && data.get_object_member ("expanded_devices").has_member (key))) throw new IOError.EXISTS ("That device name already exists locally or in a profile.");
            var device = new Json.Object ();
            device.set_string_member ("type", kind);
            if (kind == "disk") {
                device.set_string_member ("source", source.text.strip ());
                device.set_string_member ("path", target.text.strip ());
                device.set_string_member ("readonly", read_only.active ? "true" : "false");
            } else if (kind == "proxy") {
                device.set_string_member ("listen", source.text.strip ());
                device.set_string_member ("connect", target.text.strip ());
            } else {
                device.set_string_member ("network", source.text.strip ());
                device.set_string_member ("name", target.text.strip ());
            }
            devices.set_object_member (key, device);
            yield save_devices (client, instance, response, devices);
            destroy ();
        } catch (Error e) { error_label.label = e.message; save.sensitive = true; }
    }

    public static async void save_devices (IncusClient client, string name, Json.Object response, Json.Object devices) throws Error {
        var data = response.get_object_member ("metadata");
        var body = new Json.Object ();
        string[] writable = { "architecture", "config", "description", "ephemeral", "profiles", "stateful" };
        foreach (var key in writable) if (data.has_member (key)) body.set_member (key, data.get_member (key).copy ());
        body.set_object_member ("devices", devices);
        var result = yield client.call ("PUT", "/1.0/instances/" + Uri.escape_string (name, null, false), IncusClient.json_string (body), response.get_string_member ("_orchard_etag"));
        yield client.wait_operation (result);
    }
}
