public class SandboxesWindow : Gtk.Window {
    private IncusClient client;
    private Gtk.ListBox list;
    private Gtk.Label status;
    public SandboxesWindow (Gtk.Window parent, IncusClient api) {
        Object (transient_for: parent, title: "Model sandboxes", default_width: 820, default_height: 520);
        client = api;
        var box = new Gtk.Box (Gtk.Orientation.VERTICAL, 12) { margin_top = 12, margin_bottom = 12, margin_start = 12, margin_end = 12 };
        var bar = new Gtk.Box (Gtk.Orientation.HORIZONTAL, 8);
        var create = new Gtk.Button.with_label ("Create native sandbox…"); create.clicked.connect (() => { var dialog = new SandboxCreateWindow (this, client); dialog.completed.connect (() => reload.begin ()); dialog.present (); }); bar.append (create);
        var refresh = new Gtk.Button.with_label ("Refresh"); refresh.clicked.connect (() => reload.begin ()); bar.append (refresh); box.append (bar);
        list = new Gtk.ListBox () { selection_mode = Gtk.SelectionMode.NONE }; box.append (new Gtk.ScrolledWindow () { child = list, vexpand = true });
        status = new Gtk.Label ("Network badges describe current Incus configuration, not a security attestation. Containers share the host kernel; VMs use a guest kernel.") { xalign = 0, wrap = true }; box.append (status); child = box; reload.begin ();
    }
    private async void reload () {
        while (list.get_first_child () != null) list.remove (list.get_first_child ());
        try {
            var response = yield client.call ("GET", "/1.0/instances?recursion=2");
            var networks = yield client.call ("GET", "/1.0/networks?recursion=1");
            foreach (var node in response.get_array_member ("metadata").get_elements ()) {
                var instance = node.get_object ();
                var config = instance.get_object_member ("config");
                var endpoint = config.get_string_member_with_default ("environment.OPENAI_BASE_URL", config.get_string_member_with_default ("environment.OLLAMA_HOST", ""));
                bool managed = config.get_string_member_with_default ("user.orchard.sandbox", "false") == "true";
                if (endpoint == "" && !managed) continue;
                var name = instance.get_string_member ("name");
                var devices = instance.get_object_member ("expanded_devices");
                bool host_only = true; int nic_count = 0; int host_mounts = 0;
                foreach (var key in devices.get_members ()) {
                    var device = devices.get_object_member (key);
                    if (device.get_string_member_with_default ("type", "") == "disk" && device.get_string_member_with_default ("source", "").has_prefix ("/")) host_mounts++;
                    if (device.get_string_member_with_default ("type", "") != "nic") continue;
                    nic_count++; bool known = false;
                    foreach (var network_node in networks.get_array_member ("metadata").get_elements ()) {
                        var network = network_node.get_object ();
                        if (network.get_string_member ("name") == device.get_string_member_with_default ("network", "")) { known = true; if (!ModelBridge.host_only (network)) host_only = false; }
                    }
                    if (!known) host_only = false;
                }
                var row = new Gtk.Box (Gtk.Orientation.HORIZONTAL, 12) { margin_top = 10, margin_bottom = 10, margin_start = 10, margin_end = 10 };
                string boundary = instance.get_string_member_with_default ("type", "container") == "virtual-machine" ? "VM · guest kernel" : "Container · shared host kernel";
                var label = new Gtk.Label (name + " · " + instance.get_string_member ("status") + "\n" + boundary + " · " + (nic_count > 0 && host_only ? "Configured host-only network" : "Network routing permitted or unverified") + "\n" + endpoint + (host_mounts > 0 ? "\nHost folder mounts: " + host_mounts.to_string () : "")) { xalign = 0, wrap = true, hexpand = true }; row.append (label);
                var details = new Gtk.Button.with_label ("Details"); details.clicked.connect (() => new InstanceDetails (this, client, name).present ()); row.append (details);
                bool ollama = !config.has_member ("environment.OPENAI_BASE_URL") && config.has_member ("environment.OLLAMA_HOST");
                var chat = new Gtk.Button.with_label ("Test model") { sensitive = endpoint != "", tooltip_text = "Tests from this desktop; guest access may differ" }; chat.clicked.connect (() => new ModelsWindow (this, ollama ? endpoint + "/v1" : endpoint).present ()); row.append (chat);
                var shell = new Gtk.Button.with_label ("Shell"); shell.clicked.connect (() => {
                    var parent = get_transient_for () as MainWindow; if (parent != null) parent.open_instance_shell (name);
                }); row.append (shell);
                var stop = new Gtk.Button.with_label ("Stop now"); stop.add_css_class ("destructive-action");
                stop.clicked.connect (() => {
                    var question = new Gtk.AlertDialog ("Force stop sandbox %s?".printf (name)) { detail = "Processes stop immediately. Unsaved work may be lost.", buttons = { "Cancel", "Stop now" }, cancel_button = 0, default_button = 0 };
                    question.choose.begin (this, null, (obj, result) => { try { if (question.choose.end (result) == 1) stop_sandbox.begin (name); } catch (Error e) { } });
                }); row.append (stop); list.append (row);
            }
        } catch (Error e) { status.label = e.message; }
    }
    private async void stop_sandbox (string name) {
        try { yield client.change_state (name, "stop", true); yield reload (); }
        catch (Error e) { status.label = e.message; }
    }
}

public class SandboxCreateWindow : Gtk.Window {
    private IncusClient client;
    private Gtk.Entry name;
    private Gtk.Entry image;
    private Gtk.Entry endpoint;
    private Gtk.Entry memory;
    private Gtk.SpinButton cpus;
    private Gtk.CheckButton vm;
    private Gtk.CheckButton require_host_only;
    private Gtk.DropDown network;
    private Gtk.DropDown pool;
    private Gtk.Label status;
    private Gtk.Button create;
    public signal void completed ();
    public SandboxCreateWindow (Gtk.Window parent, IncusClient api) {
        Object (transient_for: parent, modal: true, title: "Native model sandbox", default_width: 540);
        client = api;
        var preferences = new Preferences ();
        var box = new Gtk.Box (Gtk.Orientation.VERTICAL, 10) { margin_top = 18, margin_bottom = 18, margin_start = 18, margin_end = 18 };
        name = new Gtk.Entry () { placeholder_text = "Sandbox name" }; box.append (name);
        image = new Gtk.Entry () { text = "ubuntu/24.04/cloud", placeholder_text = "Native system-image alias or local:fingerprint" }; box.append (image);
        endpoint = new Gtk.Entry () { text = preferences.read ("model-endpoint", "http://127.0.0.1:11434/v1"), placeholder_text = "Model endpoint (no API key)" }; box.append (endpoint);
        vm = new Gtk.CheckButton.with_label ("Use a VM with a separate guest kernel") { active = true }; box.append (vm);
        cpus = new Gtk.SpinButton.with_range (1, 256, 1) { value = 2 }; memory = new Gtk.Entry () { text = "2GiB" };
        box.append (new Gtk.Label ("CPU cores / memory limit") { xalign = 0 }); box.append (cpus); box.append (memory);
        network = new Gtk.DropDown.from_strings ({ }); pool = new Gtk.DropDown.from_strings ({ });
        box.append (new Gtk.Label ("Network / storage pool") { xalign = 0 }); box.append (network); box.append (pool);
        require_host_only = new Gtk.CheckButton.with_label ("Require a configured host-only network") { active = true }; box.append (require_host_only);
        var refresh = new Gtk.Button.with_label ("Refresh networks and pools"); refresh.clicked.connect (() => load.begin ()); box.append (refresh);
        var manage = new Gtk.Button.with_label ("Manage / create networks…"); manage.clicked.connect (() => new ResourceBrowser (this, client, "networks").present ()); box.append (manage);
        status = new Gtk.Label ("The model server must listen on the chosen bridge address. Desktop API keys are never injected. Native system images replace OCI agent images; install your agent inside the guest. No existing profiles or host-folder mounts are inherited.") { wrap = true, xalign = 0 }; box.append (status);
        create = new Gtk.Button.with_label ("Create and start sandbox") { sensitive = false }; create.clicked.connect (() => provision.begin ()); box.append (create); child = new Gtk.ScrolledWindow () { child = box, propagate_natural_height = true, min_content_height = 300, max_content_height = 600 }; default_height = 650;
        load.begin ();
    }
    private async void load () {
        try {
            var networks = yield client.call ("GET", "/1.0/networks?recursion=1"); string[] choices = {};
            foreach (var node in networks.get_array_member ("metadata").get_elements ()) if (node.get_object ().get_boolean_member_with_default ("managed", false)) choices += node.get_object ().get_string_member ("name");
            network.model = new Gtk.StringList (choices);
            var pools = yield client.call ("GET", "/1.0/storage-pools?recursion=1"); string[] pools_list = {};
            foreach (var node in pools.get_array_member ("metadata").get_elements ()) pools_list += node.get_object ().get_string_member ("name");
            pool.model = new Gtk.StringList (pools_list); create.sensitive = choices.length > 0 && pools_list.length > 0;
        } catch (Error e) { status.label = e.message; }
    }
    private async void provision () {
        create.sensitive = false;
        try {
            if (name.text.strip () == "" || image.text.strip () == "") throw new IOError.INVALID_ARGUMENT ("Enter a name and native system image.");
            var chosen = network.selected_item as Gtk.StringObject; var storage = pool.selected_item as Gtk.StringObject;
            if (chosen == null || storage == null) throw new IOError.INVALID_ARGUMENT ("Choose a managed network and storage pool.");
            var fresh = yield client.call ("GET", "/1.0/networks/" + Uri.escape_string (chosen.string, null, false));
            if (require_host_only.active && !ModelBridge.host_only (fresh.get_object_member ("metadata"))) throw new IOError.FAILED ("Create a host-only bridge in Networks first, then refresh and select it; or explicitly allow a routed network.");
            var url = ModelBridge.container_url (endpoint.text, fresh.get_object_member ("metadata"));
            var config = new Json.Object (); config.set_string_member ("user.orchard.sandbox", "true"); config.set_string_member ("user.orchard.model-endpoint", url); config.set_string_member ("environment.OPENAI_BASE_URL", url);
            config.set_string_member ("limits.cpu", ((int) cpus.value).to_string ()); config.set_string_member ("limits.memory", memory.text.strip ());
            if (!vm.active) { config.set_string_member ("security.privileged", "false"); config.set_string_member ("security.nesting", "false"); }
            var devices = new Json.Object (); var root = new Json.Object (); root.set_string_member ("type", "disk"); root.set_string_member ("path", "/"); root.set_string_member ("pool", storage.string); devices.set_object_member ("root", root);
            var nic = new Json.Object (); nic.set_string_member ("type", "nic"); nic.set_string_member ("name", "eth0"); nic.set_string_member ("network", chosen.string); devices.set_object_member ("eth0", nic);
            status.label = "Creating sandbox… Native image download or VM startup may take a while.";
            yield client.create_instance (name.text.strip (), image.text.strip (), vm.active, config, false, devices, true);
            completed (); destroy ();
        } catch (Error e) { status.label = e.message; create.sensitive = true; }
    }
}
