public class InstanceDetails : Gtk.Window {
    private IncusClient client;
    private string instance;
    private Gtk.Label message;
    private Gtk.TextView details;
    private Gtk.TextView configuration;
    private Gtk.TextView logs;
    private Gtk.DropDown log_file;
    private string etag = "";
    private Json.Object? original_config;
    private Gtk.Stack stack;
    private bool state_busy = false;
    private Dashboard metrics;
    private Gtk.Label metrics_status;
    private uint metrics_timer = 0;
    private bool metrics_busy = false;
    private bool config_busy = false;

    public InstanceDetails (Gtk.Window parent, IncusClient api, string name, string initial_page = "inspect") {
        Object (transient_for: parent, title: name, default_width: 760, default_height: 600);
        client = api;
        instance = name;
        var header = new Gtk.HeaderBar ();
        var reload = new Gtk.Button.from_icon_name ("view-refresh-symbolic");
        reload.tooltip_text = "Refresh details";
        reload.clicked.connect (() => load.begin ());
        header.pack_end (reload);
        var restart = new Gtk.Button.from_icon_name ("view-refresh-symbolic") { tooltip_text = "Restart instance" };
        restart.clicked.connect (() => state_action.begin ("restart", false)); header.pack_start (restart);
        var freeze = new Gtk.Button.with_label ("Pause");
        freeze.clicked.connect (() => state_action.begin ("freeze", false)); header.pack_start (freeze);
        var resume = new Gtk.Button.with_label ("Resume");
        resume.clicked.connect (() => state_action.begin ("unfreeze", false)); header.pack_start (resume);
        var kill = new Gtk.Button.with_label ("Force stop");
        kill.clicked.connect (() => {
            var question = new Gtk.AlertDialog ("Force stop %s?".printf (instance)) { detail = "Unsaved work in this instance may be lost.", buttons = { "Cancel", "Force stop" }, cancel_button = 0, default_button = 0 };
            question.choose.begin (this, null, (obj, result) => { try { if (question.choose.end (result) == 1) state_action.begin ("stop", true); } catch (Error e) { } });
        }); header.pack_start (kill);
        set_titlebar (header);
        stack = new Gtk.Stack () { vexpand = true };
        var switcher = new Gtk.StackSwitcher () { stack = stack, halign = Gtk.Align.CENTER, margin_top = 12 };
        details = new Gtk.TextView () { editable = false, monospace = true, left_margin = 12, right_margin = 12 };
        stack.add_titled (new Gtk.ScrolledWindow () { child = details }, "inspect", "Inspect");
        metrics = new Dashboard ("instance-" + instance);
        metrics.set_storage ("Root disk measurements belong to this instance. Global image/pool accounting is on the main dashboard.");
        metrics_status = new Gtk.Label ("") { xalign = 0, wrap = true };
        var metric_box = new Gtk.Box (Gtk.Orientation.VERTICAL, 8); metric_box.append (metrics); metric_box.append (metrics_status);
        stack.add_titled (new Gtk.ScrolledWindow () { child = metric_box }, "stats", "Statistics");
        stack.notify["visible-child-name"].connect (() => { if (stack.visible_child_name == "stats") refresh_metrics.begin (); });
        weak InstanceDetails window = this;
        metrics_timer = Timeout.add_seconds (3, () => { if (window == null) return Source.REMOVE; if (window.stack.visible_child_name == "stats") window.refresh_metrics.begin (); return Source.CONTINUE; });
        close_request.connect (() => { if (metrics_timer != 0) { Source.remove (metrics_timer); metrics_timer = 0; } return false; });
        var config_box = new Gtk.Box (Gtk.Orientation.VERTICAL, 8) { margin_top = 12, margin_bottom = 12, margin_start = 12, margin_end = 12 };
        config_box.append (new Gtk.Label ("Instance settings, one key=value per line. Empty values remove a local override. Inherited profile settings are preserved. Quoted values use JSON escapes for newlines and quotes.") { wrap = true, xalign = 0 });
        configuration = new Gtk.TextView () { monospace = true, vexpand = true };
        config_box.append (new Gtk.ScrolledWindow () { child = configuration, vexpand = true });
        var save = new Gtk.Button.with_label ("Apply configuration") { halign = Gtk.Align.END };
        save.clicked.connect (() => {
            save.sensitive = false;
            apply.begin (false, (obj, result) => { apply.end (result); save.sensitive = true; });
        });
        config_box.append (save);
        var apply_restart = new Gtk.Button.with_label ("Stop, apply & start") { halign = Gtk.Align.END };
        apply_restart.clicked.connect (() => {
            var question = new Gtk.AlertDialog ("Apply settings with a restart?") { detail = "The instance will stop before changes are applied and start afterward. If applying fails, it stays stopped so you can review the error.", buttons = { "Cancel", "Apply and start" }, cancel_button = 0, default_button = 0 };
            question.choose.begin (this, null, (obj, result) => { try { if (question.choose.end (result) == 1) apply.begin (true); } catch (Error e) { } });
        }); config_box.append (apply_restart);
        var devices = new Gtk.Box (Gtk.Orientation.HORIZONTAL, 8);
        var mount = new Gtk.Button.with_label ("Mount folder…"); mount.clicked.connect (() => new DeviceEditor (this, client, instance, "disk").present ()); devices.append (mount);
        var port = new Gtk.Button.with_label ("Publish port…"); port.clicked.connect (() => new DeviceEditor (this, client, instance, "proxy").present ()); devices.append (port);
        var nic = new Gtk.Button.with_label ("Attach network…"); nic.clicked.connect (() => new DeviceEditor (this, client, instance, "nic").present ()); devices.append (nic);
        config_box.append (devices);
        var model = new Gtk.Button.with_label ("Connect configured local model…") { halign = Gtk.Align.END };
        model.clicked.connect (() => {
            var question = new Gtk.AlertDialog ("Connect this instance to your model endpoint?") { detail = "Orchard replaces localhost with the actual Incus bridge gateway. The model server must listen on that bridge address. Only the endpoint is injected; desktop API keys stay in the keyring.", buttons = { "Cancel", "Connect" }, cancel_button = 0, default_button = 0 };
            question.choose.begin (this, null, (obj, result) => { try { if (question.choose.end (result) == 1) connect_model.begin (); } catch (Error e) { } });
        }); config_box.append (model);
        var more = new Gtk.Box (Gtk.Orientation.HORIZONTAL, 8);
        var clone = new Gtk.Button.with_label ("Clone instance…"); clone.clicked.connect (() => clone_dialog ()); more.append (clone);
        var export_button = new Gtk.Button.with_label ("Export backup…");
        export_button.clicked.connect (() => {
            var chooser = new Gtk.FileDialog () { title = "Export Incus backup", initial_name = instance + ".tar.gz" };
            chooser.save.begin (this, null, (obj, result) => {
                try { var file = chooser.save.end (result); export_backup.begin (file); } catch (Error e) { }
            });
        }); more.append (export_button); config_box.append (more);
        stack.add_titled (config_box, "config", "Configuration");
        var log_box = new Gtk.Box (Gtk.Orientation.VERTICAL, 8) { margin_top = 12, margin_bottom = 12, margin_start = 12, margin_end = 12 };
        log_file = new Gtk.DropDown.from_strings ({ "lxc.log", "console.log", "qemu.log", "System journal" });
        var read = new Gtk.Button.with_label ("Read log");
        read.clicked.connect (() => read_log.begin ());
        var bar = new Gtk.Box (Gtk.Orientation.HORIZONTAL, 8);
        bar.append (log_file); bar.append (read);
        log_box.append (bar);
        logs = new Gtk.TextView () { editable = false, monospace = true };
        log_box.append (new Gtk.ScrolledWindow () { child = logs, vexpand = true });
        stack.add_titled (log_box, "logs", "Logs");
        message = new Gtk.Label ("") { xalign = 0, wrap = true, margin_start = 12, margin_end = 12, margin_bottom = 12 };
        var outer = new Gtk.Box (Gtk.Orientation.VERTICAL, 8);
        outer.append (switcher); outer.append (stack); outer.append (message);
        child = outer;
        load.begin ();
        stack.visible_child_name = initial_page;
        if (initial_page == "logs") read_log.begin ();
    }

    private async void load () {
        message.label = "Loading…";
        try {
            var response = yield client.inspect_instance (instance);
            var data = response.get_object_member ("metadata");
            etag = response.get_string_member_with_default ("_orchard_etag", "");
            original_config = data.get_object_member ("config");
            details.buffer.text = IncusClient.json_string (data);
            configuration.buffer.text = ConfigText.render (original_config, true);
            message.label = "Changes use Incus version checks to avoid overwriting concurrent edits.";
        } catch (Error e) { message.label = e.message; }
    }

    private async void apply (bool restart) {
        if (config_busy) return;
        config_busy = true;
        try {
            if (original_config == null || etag == "") throw new IOError.FAILED ("Refresh the instance before applying changes.");
            var config = ConfigText.parse (configuration.buffer.text, true);
            if (restart) yield client.update_with_restart (instance, config, etag);
            else yield client.update_instance (instance, config, etag);
            yield load ();
            message.label = restart ? "Configuration applied and instance started." : "Configuration applied. Incus reports if a setting requires a restart.";
        } catch (Error e) { message.label = e.message; }
        config_busy = false;
    }

    private async void read_log () {
        try {
            var item = (Gtk.StringObject) log_file.selected_item;
            logs.buffer.text = item.string == "System journal" ? yield client.journal (instance) : yield client.read_log (instance, item.string);
            message.label = "Log snapshot loaded.";
        } catch (Error e) { message.label = e.message; }
    }
    private async void state_action (string action, bool force) {
        if (state_busy) return;
        state_busy = true;
        try {
            message.label = "Applying " + action + "…";
            yield client.change_state (instance, action, force);
            yield load ();
            message.label = action + " complete.";
        } catch (Error e) { message.label = e.message; }
        state_busy = false;
    }

    private void clone_dialog () {
        var dialog = new Gtk.Window () { transient_for = this, modal = true, title = "Clone " + instance, default_width = 380 };
        var box = new Gtk.Box (Gtk.Orientation.VERTICAL, 12) { margin_top = 18, margin_bottom = 18, margin_start = 18, margin_end = 18 };
        var name = new Gtk.Entry () { placeholder_text = "New instance name" };
        var create = new Gtk.Button.with_label ("Clone");
        var error_label = new Gtk.Label ("") { wrap = true, xalign = 0 };
        create.clicked.connect (() => {
            if (name.text.strip () == "") { error_label.label = "Enter a name."; return; }
            create.sensitive = false;
            clone_instance.begin (name.text.strip (), dialog, create, error_label);
        });
        box.append (name); box.append (error_label); box.append (create); dialog.child = box; dialog.present ();
    }

    private async void clone_instance (string name, Gtk.Window dialog, Gtk.Button button, Gtk.Label error_label) {
        try { yield client.clone_instance (instance, name); dialog.destroy (); message.label = "Clone created: " + name; }
        catch (Error e) { error_label.label = e.message; button.sensitive = true; }
    }

    private async void export_backup (File destination) {
        message.label = "Exporting backup…";
        try { yield client.export_instance (instance, destination); message.label = "Saved backup to " + destination.get_parse_name (); }
        catch (Error e) { message.label = e.message; }
    }
    private async void refresh_metrics () {
        if (metrics_busy) return;
        metrics_busy = true;
        try {
            var response = yield client.call ("GET", "/1.0/instances/" + Uri.escape_string (instance, null, false) + "/state");
            var state = response.get_object_member ("metadata");
            var data = new Json.Object (); data.set_string_member ("name", instance); data.set_string_member ("status", state.get_string_member ("status")); data.set_object_member ("state", state);
            metrics.update ({ Instance.from_json (data) }); metrics_status.label = "Live statistics.";
        } catch (Error e) { metrics_status.label = "Statistics are stale: " + e.message; }
        metrics_busy = false;
    }
    private async void connect_model () {
        try {
            var preferences = new Preferences ();
            if (preferences.read ("model-enabled", "true") != "true") throw new IOError.FAILED ("Enable and save a model endpoint first.");
            var url = yield ModelBridge.attach (client, instance, preferences.read ("model-endpoint", "http://127.0.0.1:11434/v1"));
            yield load ();
            message.label = "Model endpoint configured: " + url + ". Server binding and guest access must be verified; no API key was injected.";
        } catch (Error e) { message.label = e.message; }
    }
}
