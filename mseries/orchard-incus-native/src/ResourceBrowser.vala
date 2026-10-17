public class ResourceBrowser : Gtk.Window {
    private IncusClient client;
    private Gtk.DropDown category;
    private Gtk.ListBox list;
    private Gtk.Label status;
    private Gtk.Button add;
    private string[] endpoints = { "/1.0/images", "/1.0/networks", "/1.0/network-zones", "/1.0/storage-pools", "/1.0/profiles", "/1.0/projects", "/1.0/operations" };
    private string[] titles = { "Images", "Networks", "DNS zones", "Storage pools", "Profiles", "Projects", "Operations" };
    private bool loading = false;
    private string target_filter = "";
    private Gtk.SearchEntry search;
    private Gtk.DropDown sort_order;
    private Preferences preferences = new Preferences ();
    private GenericSet<string> selected_names = new GenericSet<string> (str_hash, str_equal);

    public ResourceBrowser (Gtk.Window parent, IncusClient api, string kind = "", string target = "") {
        Object (transient_for: parent, title: "Incus resources", default_width: 740, default_height: 520);
        client = api;
        var header = new Gtk.HeaderBar ();
        category = new Gtk.DropDown.from_strings (titles);
        target_filter = target;
        for (uint i = 0; i < endpoints.length; i++) if (endpoints[i] == "/1.0/" + kind) category.selected = i;
        header.title_widget = category;
        var refresh = new Gtk.Button.from_icon_name ("view-refresh-symbolic") { tooltip_text = "Refresh resources" };
        refresh.clicked.connect (() => reload.begin ());
        add = new Gtk.Button.from_icon_name ("list-add-symbolic") { tooltip_text = "Create resource" };
        add.clicked.connect (() => {
            if (category.selected == 0) {
                var window = new ImagePullWindow (this, client); window.completed.connect (() => reload.begin ()); window.present ();
            } else create_dialog ();
        });
        header.pack_start (add); header.pack_end (refresh);
        set_titlebar (header);
        list = new Gtk.ListBox () { selection_mode = Gtk.SelectionMode.NONE };
        list.add_css_class ("boxed-list");
        status = new Gtk.Label ("") { xalign = 0, wrap = true };
        var box = new Gtk.Box (Gtk.Orientation.VERTICAL, 12) { margin_top = 12, margin_bottom = 12, margin_start = 12, margin_end = 12 };
        var filters = new Gtk.Box (Gtk.Orientation.HORIZONTAL, 8);
        search = new Gtk.SearchEntry () { placeholder_text = "Search resources…", hexpand = true };
        sort_order = new Gtk.DropDown.from_strings ({ "Name A–Z", "Name Z–A", "Largest images first" });
        uint order = 0; uint.try_parse (preferences.read ("resource-sort", "0"), out order); if (order < 3) sort_order.selected = order;
        search.search_changed.connect (() => reload.begin ());
        sort_order.notify["selected"].connect (() => { try { preferences.write ("resource-sort", sort_order.selected.to_string ()); } catch (Error e) { } reload.begin (); });
        var bulk = new Gtk.Button.with_label ("Delete selected…"); bulk.clicked.connect (confirm_bulk_delete);
        filters.append (search); filters.append (sort_order); filters.append (bulk); box.append (filters);
        box.append (new Gtk.ScrolledWindow () { child = list, vexpand = true });
        box.append (status); child = box;
        category.notify["selected"].connect (() => { target_filter = ""; selected_names.remove_all (); reload.begin (); });
        reload.begin ();
    }

    private async void reload () {
        if (loading) return;
        loading = true;
        uint selected = category.selected;
        category.sensitive = false;
        add.sensitive = selected != 3 && selected != 6;
        status.label = "Loading…";
        while (list.get_first_child () != null) list.remove (list.get_first_child ());
        try {
            var result = yield client.call ("GET", endpoints[selected] + "?recursion=1");
            var metadata = result.get_member ("metadata");
            if (metadata.get_node_type () == Json.NodeType.ARRAY) {
                var ordered = new List<Json.Object> ();
                foreach (var node in metadata.get_array ().get_elements ()) if (node.get_node_type () == Json.NodeType.OBJECT) ordered.append (node.get_object ());
                ordered.sort_with_data ((a, b) => {
                    var key = selected == 0 ? "fingerprint" : "name";
                    if (sort_order.selected == 2 && selected == 0) {
                        var size_a = a.get_int_member_with_default ("size", 0); var size_b = b.get_int_member_with_default ("size", 0);
                        if (size_a != size_b) return size_a > size_b ? -1 : 1;
                    }
                    var comparison = a.get_string_member_with_default (key, "").collate (b.get_string_member_with_default (key, ""));
                    return sort_order.selected == 1 ? -comparison : comparison;
                });
                foreach (var item in ordered) {
                    string name = selected == 0 ? item.get_string_member_with_default ("fingerprint", "") : item.get_string_member_with_default ("name", "");
                    if (name == "") continue;
                    var description = item.get_string_member_with_default ("description", "");
                    if (selected == 0 && item.has_member ("properties")) description = item.get_object_member ("properties").get_string_member_with_default ("description", "");
                    append_resource (selected, name, description, item);
                }
            } else if (selected == 6 && metadata.get_node_type () == Json.NodeType.OBJECT) {
                var groups = metadata.get_object ();
                foreach (var key in groups.get_members ()) {
                    foreach (var node in groups.get_array_member (key).get_elements ()) {
                        var item = node.get_object ();
                        append_resource (selected, item.get_string_member ("id"), item.get_string_member_with_default ("description", key), item);
                    }
                }
            }
            status.label = target_filter != "" && list.get_first_child () == null ? "Resource not found: " + target_filter : "Resources reported by the local Incus server.";
        } catch (Error e) { status.label = e.message; }
        category.sensitive = true;
        loading = false;
    }

    private void append_resource (uint selected, string name, string description, Json.Object data) {
        if (target_filter != "" && name != target_filter) return;
        if (PaletteMatch.score (search.text, name + " " + description) < 0) return;
        var row = new Gtk.Box (Gtk.Orientation.HORIZONTAL, 12) { margin_top = 8, margin_bottom = 8, margin_start = 12, margin_end = 12 };
        var labels = new Gtk.Box (Gtk.Orientation.VERTICAL, 3) { hexpand = true };
        labels.append (new Gtk.Label (name) { xalign = 0, ellipsize = Pango.EllipsizeMode.MIDDLE, max_width_chars = 42 });
        var note = new Gtk.Label (description) { xalign = 0, wrap = true };
        note.add_css_class ("dim-label"); labels.append (note); row.append (labels);
        var inspect = new Gtk.Button.with_label ("Inspect");
        inspect.clicked.connect (() => {
            var view = new Gtk.TextView () { editable = false, monospace = true, left_margin = 12, right_margin = 12, top_margin = 12 };
            view.buffer.text = IncusClient.json_string (data);
            new Gtk.Window () { transient_for = this, title = name, default_width = 680, default_height = 480, child = new Gtk.ScrolledWindow () { child = view } }.present ();
        });
        row.append (inspect);
        if (selected == 0) {
            var launch = new Gtk.Button.with_label ("Launch…");
            launch.clicked.connect (() => {
                Gtk.Window? parent = get_transient_for ();
                while (parent != null && !(parent is MainWindow)) parent = parent.get_transient_for ();
                if (parent == null) {
                    var app = GLib.Application.get_default () as Gtk.Application;
                    if (app != null) { app.activate (); foreach (var window in app.get_windows ()) if (window is MainWindow) parent = window; }
                }
                if (parent is MainWindow) ((MainWindow) parent).create_from_image (name, data.get_string_member_with_default ("type", "container") == "virtual-machine");
                else status.label = "Open the main manager to launch this image.";
            }); row.append (launch);
        }
        if (selected == 1 || selected == 2 || selected == 4 || selected == 5) {
            var edit = new Gtk.Button.with_label ("Settings…"); edit.clicked.connect (() => edit_resource.begin (selected, name)); row.append (edit);
        }
        if (selected != 3 && !(selected == 1 && !data.get_boolean_member_with_default ("managed", false))) {
            var remove = new Gtk.Button.from_icon_name ("edit-delete-symbolic") { tooltip_text = selected == 6 ? "Cancel operation" : "Delete resource" };
            remove.add_css_class ("destructive-action");
            remove.clicked.connect (() => {
                var question = new Gtk.AlertDialog ("%s %s?".printf (selected == 6 ? "Cancel" : "Delete", name)) {
                    detail = "Incus will refuse the operation if this resource is still in use. This action cannot be undone.",
                    buttons = { "Cancel", "Confirm" }, cancel_button = 0, default_button = 0
                };
                question.choose.begin (this, null, (obj, result) => {
                    try { if (question.choose.end (result) == 1) remove_resource.begin (selected, name); } catch (Error e) { }
                });
            });
            row.append (remove);
            var check = new Gtk.CheckButton () { tooltip_text = "Select " + name, active = selected_names.contains (name) };
            check.toggled.connect (() => { if (check.active) selected_names.add (name); else selected_names.remove (name); }); row.append (check);
        }
        list.append (row);
    }

    private async void remove_resource (uint selected, string name) {
        try {
            var result = yield client.call ("DELETE", endpoints[selected] + "/" + Uri.escape_string (name, null, false));
            yield client.wait_operation (result);
            yield reload ();
        } catch (Error e) { status.label = e.message; }
    }

    private void create_dialog () {
        uint selected = category.selected;
        var dialog = new Gtk.Window () { transient_for = this, modal = true, title = "New " + titles[selected], default_width = 420 };
        var box = new Gtk.Box (Gtk.Orientation.VERTICAL, 12) { margin_top = 18, margin_bottom = 18, margin_start = 18, margin_end = 18 };
        var name = new Gtk.Entry () { placeholder_text = selected == 2 ? "example.internal" : "Resource name" };
        var subnet = new Gtk.Entry () { placeholder_text = "IPv4 subnet, e.g. 10.40.0.1/24 (auto if empty)" };
        var domain = new Gtk.Entry () { placeholder_text = "DNS domain (optional)" };
        var host_only = new Gtk.CheckButton.with_label ("Host-only bridge (no routing, NAT, IPv6 or DNS forwarding)");
        var error_label = new Gtk.Label ("") { wrap = true, xalign = 0 };
        box.append (name);
        if (selected == 1) { box.append (subnet); box.append (domain); box.append (host_only); }
        var create = new Gtk.Button.with_label ("Create") { halign = Gtk.Align.END };
        create.clicked.connect (() => {
            if (name.text.strip () == "") { error_label.label = "Enter a name."; return; }
            create.sensitive = false;
            var body = new Json.Object ();
            body.set_string_member ("name", name.text.strip ());
            var config = new Json.Object ();
            if (selected == 1) {
                body.set_string_member ("type", "bridge");
                config.set_string_member ("ipv4.address", subnet.text.strip () == "" ? "auto" : subnet.text.strip ());
                config.set_string_member ("ipv4.nat", host_only.active ? "false" : "true");
                if (host_only.active) {
                    config.set_string_member ("ipv4.routing", "false"); config.set_string_member ("ipv6.address", "none");
                    config.set_string_member ("dns.mode", "none"); config.set_string_member ("raw.dnsmasq", "port=0");
                }
                if (domain.text.strip () != "") config.set_string_member ("dns.domain", domain.text.strip ());
            }
            body.set_object_member ("config", config);
            if (selected == 4) body.set_object_member ("devices", new Json.Object ());
            create_resource.begin (selected, body, dialog, create, error_label);
        });
        box.append (error_label); box.append (create); dialog.child = box; dialog.present ();
    }

    private async void create_resource (uint selected, Json.Object body, Gtk.Window dialog, Gtk.Button button, Gtk.Label error_label) {
        try {
            var result = yield client.call ("POST", endpoints[selected], IncusClient.json_string (body));
            yield client.wait_operation (result);
            dialog.destroy ();
            yield reload ();
        } catch (Error e) { error_label.label = e.message; button.sensitive = true; }
    }
    private void confirm_bulk_delete () {
        uint selected = category.selected;
        if (selected_names.length == 0) return;
        string[] names = {}; selected_names.foreach ((name) => { names += name; });
        var question = new Gtk.AlertDialog ("Delete %u selected resources?".printf (selected_names.length)) {
            detail = string.joinv ("\n", names) + "\nIn-use resources will be refused by Incus.", buttons = { "Cancel", "Delete" }, cancel_button = 0, default_button = 0
        };
        question.choose.begin (this, null, (obj, result) => { try { if (question.choose.end (result) == 1) bulk_delete.begin (selected, names); } catch (Error e) { } });
    }
    private async void bulk_delete (uint selected, string[] names) {
        int success = 0; var failures = new StringBuilder ();
        foreach (var name in names) {
            try {
                var response = yield client.call ("DELETE", endpoints[selected] + "/" + Uri.escape_string (name, null, false));
                yield client.wait_operation (response); success++; selected_names.remove (name);
            } catch (Error e) { failures.append (name + ": " + e.message + "\n"); }
        }
        yield reload ();
        status.label = "%d of %d resources deleted. %s".printf (success, names.length, failures.str);
    }
    private async void edit_resource (uint selected, string name) {
        try {
            var path = endpoints[selected] + "/" + Uri.escape_string (name, null, false);
            var response = yield client.call ("GET", path);
            var config = response.get_object_member ("metadata").get_object_member ("config");
            var dialog = new Gtk.Window () { transient_for = this, title = "Settings · " + name, default_width = 620, default_height = 420 };
            var box = new Gtk.Box (Gtk.Orientation.VERTICAL, 12) { margin_top = 12, margin_bottom = 12, margin_start = 12, margin_end = 12 };
            box.append (new Gtk.Label ("Native Incus settings, one key=value per line. Empty values clear an override. Use user.* for labels and dns.* for managed-network DNS settings. Quoted values use JSON escapes for newlines and quotes.") { xalign = 0, wrap = true });
            var editor = new Gtk.TextView () { monospace = true, vexpand = true };
            editor.buffer.text = ConfigText.render (config);
            box.append (new Gtk.ScrolledWindow () { child = editor, vexpand = true });
            var error_label = new Gtk.Label ("") { xalign = 0, wrap = true }; box.append (error_label);
            var save = new Gtk.Button.with_label ("Apply settings");
            save.clicked.connect (() => {
                try {
                    var patch = new Json.Object (); var values = ConfigText.parse (editor.buffer.text);
                    patch.set_object_member ("config", values); save.sensitive = false;
                    save_resource.begin (path, patch, response.get_string_member ("_orchard_etag"), dialog, save, error_label);
                } catch (Error e) { error_label.label = e.message; }
            });
            box.append (save); dialog.child = box; dialog.present ();
        } catch (Error e) { status.label = e.message; }
    }
    private async void save_resource (string path, Json.Object patch, string etag, Gtk.Window dialog, Gtk.Button button, Gtk.Label error_label) {
        try { yield client.patch_resource (path, patch, etag); dialog.destroy (); yield reload (); }
        catch (Error e) { error_label.label = e.message; button.sensitive = true; }
    }
}
