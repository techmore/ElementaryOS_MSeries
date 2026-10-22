public class MountsWindow : Gtk.Window {
    private IncusClient client;
    private Gtk.ListBox list;
    private Gtk.Label status;
    public signal void open_instance (string name);
    public MountsWindow (Gtk.Window parent, IncusClient api) {
        Object (transient_for: parent, title: "Instance mounts", default_width: 760, default_height: 520);
        client = api;
        var box = new Gtk.Box (Gtk.Orientation.VERTICAL, 12) { margin_top = 12, margin_bottom = 12, margin_start = 12, margin_end = 12 };
        var refresh = new Gtk.Button.with_label ("Refresh mounts"); refresh.clicked.connect (() => reload.begin ()); box.append (refresh);
        list = new Gtk.ListBox () { selection_mode = Gtk.SelectionMode.NONE }; box.append (new Gtk.ScrolledWindow () { child = list, vexpand = true });
        status = new Gtk.Label ("") { xalign = 0, wrap = true }; box.append (status); child = box; reload.begin ();
    }
    private async void reload () {
        while (list.get_first_child () != null) list.remove (list.get_first_child ());
        try {
            var response = yield client.call ("GET", "/1.0/instances?recursion=2");
            foreach (var node in response.get_array_member ("metadata").get_elements ()) {
                var instance = node.get_object ();
                var name = instance.get_string_member ("name");
                var devices = instance.get_object_member (instance.has_member ("expanded_devices") ? "expanded_devices" : "devices");
                foreach (var key in devices.get_members ()) {
                    var device = devices.get_object_member (key);
                    if (device.get_string_member_with_default ("type", "") != "disk") continue;
                    var path = device.get_string_member_with_default ("path", "");
                    var source = device.get_string_member_with_default ("source", "");
                    var pool = device.get_string_member_with_default ("pool", "");
                    var row = new Gtk.Box (Gtk.Orientation.HORIZONTAL, 12) { margin_top = 8, margin_bottom = 8, margin_start = 8, margin_end = 8 };
                    var text = new Gtk.Label ("%s · %s\n%s → %s%s%s".printf (name, key, source == "" ? "root disk" : source, path, pool == "" ? "" : " · pool " + pool, device.get_string_member_with_default ("readonly", "false") == "true" ? " · read-only" : "")) { xalign = 0, wrap = true, hexpand = true };
                    row.append (text);
                    var inspect = new Gtk.Button.with_label ("Instance"); var selected_name = name;
                    inspect.clicked.connect (() => open_instance (selected_name)); row.append (inspect);
                    bool local = instance.get_object_member ("devices").has_member (key);
                    if (path != "/" && local) {
                        var remove = new Gtk.Button.with_label ("Remove mount"); var selected_key = key;
                        remove.clicked.connect (() => {
                            var question = new Gtk.AlertDialog ("Remove %s from %s?".printf (selected_key, selected_name)) {
                                detail = "The host folder or volume is preserved. Incus applies the device change; some VM devices require a restart.", buttons = { "Cancel", "Remove" }, cancel_button = 0, default_button = 0
                            };
                            question.choose.begin (this, null, (obj, result) => { try { if (question.choose.end (result) == 1) remove_mount.begin (selected_name, selected_key); } catch (Error e) { } });
                        }); row.append (remove);
                    }
                    list.append (row);
                }
            }
            status.label = "Includes inherited profile disks. Root and inherited devices cannot be removed from this view.";
        } catch (Error e) { status.label = e.message; }
    }
    private async void remove_mount (string name, string key) {
        try {
            var response = yield client.inspect_instance (name);
            var devices = response.get_object_member ("metadata").get_object_member ("devices");
            if (!devices.has_member (key)) throw new IOError.NOT_FOUND ("This local mount no longer exists.");
            if (devices.get_object_member (key).get_string_member_with_default ("path", "") == "/") throw new IOError.PERMISSION_DENIED ("Root disk removal is not allowed here.");
            devices.remove_member (key);
            yield DeviceEditor.save_devices (client, name, response, devices);
            yield reload ();
        } catch (Error e) { status.label = e.message; }
    }
}
