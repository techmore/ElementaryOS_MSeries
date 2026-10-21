class HandlerIds : Object { public ulong a; public ulong b; public ulong c; public ulong d; public ulong e; public ulong f; }

public class MainWindow : Gtk.ApplicationWindow {
    private IncusClient client = new IncusClient ();
    private ListStore store = new ListStore (typeof (Instance));
    private Gtk.Label status_label;
    private Granite.Toast toast;
    private uint poll_id = 0;
    private bool loading = false;
    private Dashboard? dashboard;
    private Gtk.Stack content_stack;
    private int64 last_storage_refresh = 0;
    private bool storage_busy = false;
    private Gtk.SearchEntry search;
    private Gtk.DropDown kind_filter;
    private Gtk.DropDown sort_order;
    private Gtk.Entry group_label;
    private GenericSet<string> selected_names = new GenericSet<string> (str_hash, str_equal);
    private Gtk.Label selection_status;
    private Gtk.FlowBox bulk_bar;
    private Preferences preferences = new Preferences ();
    private GenericSet<string> pending = new GenericSet<string> (str_hash, str_equal);

    public MainWindow (Gtk.Application app) {
        Object (application: app, default_width: 1040, default_height: 560, title: "Orchard for Incus");

        add_css_class ("orchard-window");
        var style = new Gtk.CssProvider ();
        style.load_from_string (
            ".orchard-window .orchard-metric-card { padding: 14px; border-radius: 12px; background: alpha(currentColor, 0.045); box-shadow: inset 0 0 0 1px alpha(currentColor, 0.07); } " +
            ".orchard-window .orchard-metric-card .heading { font-size: 1.05em; } " +
            ".orchard-window .orchard-list row { padding: 6px 0; border-bottom: 1px solid alpha(currentColor, 0.07); } " +
            ".orchard-window .orchard-sidebar { border-right: 1px solid alpha(currentColor, 0.08); }");
        Gtk.StyleContext.add_provider_for_display (get_display (), style, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION);
        var header = new Gtk.HeaderBar ();
        var refresh = new Gtk.Button.from_icon_name ("view-refresh-symbolic") { tooltip_text = "Refresh" };
        refresh.clicked.connect (() => { reload.begin (); });
        header.pack_end (refresh);
        var add = new Gtk.Button.with_label ("New Instance…") { tooltip_text = "New instance" };
        add.clicked.connect (() => { open_new_instance (); });
        add.add_css_class ("suggested-action");
        header.pack_start (add);
        refresh.update_property (Gtk.AccessibleProperty.LABEL, "Refresh", -1);
        add.update_property (Gtk.AccessibleProperty.LABEL, "New instance", -1);

        // Keep primary actions visible; secondary destinations remain named and keyboard-accessible.
        var destinations = new Menu ();
        string[] action_ids = { "resources", "dashboard", "models", "sandboxes", "system", "mounts", "logs", "preferences" };
        string[] action_labels = { "Resources…", "Resource Dashboard", "Local AI Models…", "Model Sandboxes…", "Incus System…", "Instance Mounts…", "Instance Logs…", "Preferences…" };
        for (int i = 0; i < action_ids.length; i++) {
            var id = action_ids[i];
            var action = new SimpleAction (id, null);
            action.activate.connect (() => {
                if (id == "resources") new ResourceBrowser (this, client).present ();
                else dispatch_command (id, "");
            });
            add_action (action);
            destinations.append (action_labels[i], "win." + id);
        }
        var more = new Gtk.MenuButton () {
            icon_name = "open-menu-symbolic", menu_model = destinations,
            tooltip_text = "More actions"
        };
        more.update_property (Gtk.AccessibleProperty.LABEL, "More actions", -1);
        header.pack_end (more);
        set_titlebar (header);

        var list = new Gtk.ListView (new Gtk.NoSelection (store), make_factory ());
        list.add_css_class ("rich-list");
        list.add_css_class ("orchard-list");
        var scroller = new Gtk.ScrolledWindow () { child = list, vexpand = true };

        status_label = new Gtk.Label ("") { margin_top = 6, margin_bottom = 6, xalign = 0, margin_start = 12 };
        status_label.add_css_class ("h4");

        var box = new Gtk.Box (Gtk.Orientation.VERTICAL, 0);
        var filters = new Gtk.Box (Gtk.Orientation.VERTICAL, 8) { margin_start = 12, margin_end = 12, margin_top = 8, margin_bottom = 8 };
        search = new Gtk.SearchEntry () { hexpand = true, placeholder_text = "Search names, images or status…" };
        kind_filter = new Gtk.DropDown.from_strings ({ "All instances", "Containers", "Virtual machines" });
        sort_order = new Gtk.DropDown.from_strings ({ "Name A–Z", "Name Z–A", "Memory usage", "Status" });
        uint saved_order = 0; uint.try_parse (preferences.read ("sort", "0"), out saved_order);
        if (saved_order < 4) sort_order.selected = saved_order;
        group_label = new Gtk.Entry () { placeholder_text = "Group by label, e.g. user.team", text = preferences.read ("group", "") };
        group_label.activate.connect (() => { try { preferences.write ("group", group_label.text); } catch (Error e) { } reload.begin (); });
        sort_order.notify["selected"].connect (() => { try { preferences.write ("sort", sort_order.selected.to_string ()); } catch (Error e) { } reload.begin (); });
        search.update_property (Gtk.AccessibleProperty.LABEL, "Search instances", -1);
        kind_filter.update_property (Gtk.AccessibleProperty.LABEL, "Instance type", -1);
        sort_order.update_property (Gtk.AccessibleProperty.LABEL, "Sort order", -1);
        group_label.update_property (Gtk.AccessibleProperty.LABEL, "Group by label", -1);
        var filter_controls = new Gtk.FlowBox () {
            selection_mode = Gtk.SelectionMode.NONE, homogeneous = false,
            min_children_per_line = 1, max_children_per_line = 3,
            column_spacing = 8, row_spacing = 8
        };
        filter_controls.insert (kind_filter, -1);
        filter_controls.insert (sort_order, -1);
        filter_controls.insert (group_label, -1);
        filters.append (search);
        filters.append (filter_controls);
        search.search_changed.connect (() => { reload.begin (); });
        kind_filter.notify["selected"].connect (() => { reload.begin (); });
        var keys = new Gtk.EventControllerKey ();
        keys.key_pressed.connect ((key, code, modifiers) => {
            if ((key == Gdk.Key.k || key == Gdk.Key.K) && (modifiers & Gdk.ModifierType.CONTROL_MASK) != 0) {
                var palette = new CommandPalette (this, client);
                palette.selected.connect (dispatch_command);
                palette.present ();
                return true;
            }
            return false;
        });
        ((Gtk.Widget) this).add_controller (keys);
        box.append (filters);
        bulk_bar = new Gtk.FlowBox () {
            selection_mode = Gtk.SelectionMode.NONE, homogeneous = false,
            min_children_per_line = 1, max_children_per_line = 6,
            column_spacing = 8, row_spacing = 8,
            margin_start = 12, margin_end = 12, margin_bottom = 8
        };
        selection_status = new Gtk.Label ("0 selected") { xalign = 0, hexpand = true }; bulk_bar.insert (selection_status, -1);
        var select_all = new Gtk.Button.with_label ("Select visible"); select_all.clicked.connect (() => {
            for (uint i = 0; i < store.get_n_items (); i++) selected_names.add (((Instance) store.get_item (i)).name);
            update_selection_ui (); reload.begin ();
        }); bulk_bar.insert (select_all, -1);
        string[] verbs = { "start", "stop", "delete" };
        foreach (var verb in verbs) {
            var button = new Gtk.Button.with_label (verb.substring (0, 1).up () + verb.substring (1) + " selected");
            var action = verb;
            button.clicked.connect (() => confirm_bulk (action)); bulk_bar.insert (button, -1);
        }
        var clear = new Gtk.Button.with_label ("Clear selection"); clear.clicked.connect (() => { selected_names.remove_all (); update_selection_ui (); reload.begin (); }); bulk_bar.insert (clear, -1);
        bulk_bar.visible = false;
        box.append (bulk_bar);
        box.append (scroller);
        box.append (status_label);

        toast = new Granite.Toast ("");
        content_stack = new Gtk.Stack () { hexpand = true, vexpand = true };
        dashboard = new Dashboard ();
        content_stack.add_titled (new Gtk.ScrolledWindow () { child = dashboard }, "dashboard", "Dashboard");
        content_stack.add_titled (box, "instances", "Instances");
        var podman_page = new PodmanPage ();
        podman_page.notice.connect ((text) => { toast.title = text; toast.send_notification (); });
        content_stack.add_titled (podman_page, "podman", "Podman");
        var sidebar = new Gtk.StackSidebar () { stack = content_stack, width_request = 150 };
        sidebar.add_css_class ("navigation-sidebar");
        sidebar.add_css_class ("orchard-sidebar");
        var layout = new Gtk.Box (Gtk.Orientation.HORIZONTAL, 0); layout.append (sidebar); layout.append (content_stack);
        var overlay = new Gtk.Overlay () { child = layout };
        overlay.add_overlay (toast);
        child = overlay;

        reload.begin ();
        poll_id = Timeout.add_seconds (3, () => { reload.begin (); return Source.CONTINUE; });
        close_request.connect (() => { Source.remove (poll_id); return false; });
    }

    private void update_selection_ui () {
        selection_status.label = "%u selected".printf (selected_names.length);
        bulk_bar.visible = selected_names.length > 0;
    }

    private Gtk.ListItemFactory make_factory () {
        var f = new Gtk.SignalListItemFactory ();
        f.setup.connect ((obj) => {
            var item = (Gtk.ListItem) obj;
            var row = new Gtk.Box (Gtk.Orientation.HORIZONTAL, 12) { margin_top = 6, margin_bottom = 6, margin_start = 12, margin_end = 12 };
            var dot = new Gtk.Image.from_icon_name ("media-record-symbolic");
            var name = new Gtk.Label ("") { xalign = 0, hexpand = true, name = "name", ellipsize = Pango.EllipsizeMode.END, width_chars = 8, max_width_chars = 24 };
            name.add_css_class ("h3");
            var meta = new Gtk.Label ("") { xalign = 1, name = "meta", wrap = true, max_width_chars = 24 };
            meta.add_css_class ("dim-label");
            var toggle = new Gtk.Button () { valign = Gtk.Align.CENTER, name = "toggle" };
            var shell = new Gtk.Button.with_label ("Shell") { valign = Gtk.Align.CENTER, name = "shell" };
            var snap = new Gtk.Button.from_icon_name ("camera-photo-symbolic") { valign = Gtk.Align.CENTER, tooltip_text = "Snapshots…", name = "snap" };
            var del = new Gtk.Button.from_icon_name ("edit-delete-symbolic") { valign = Gtk.Align.CENTER, tooltip_text = "Delete", name = "del" };
            del.add_css_class ("destructive-action");
            snap.update_property (Gtk.AccessibleProperty.LABEL, "Snapshots", -1);
            del.update_property (Gtk.AccessibleProperty.LABEL, "Delete instance", -1);
            row.append (dot); row.append (name); row.append (meta);
            row.append (toggle); row.append (shell); row.append (snap); row.append (del);
            var inspect = new Gtk.Button.from_icon_name ("document-properties-symbolic") { tooltip_text = "Inspect, configure and read logs" };
            inspect.update_property (Gtk.AccessibleProperty.LABEL, "Instance details", -1);
            row.append (inspect);
            row.append (new Gtk.CheckButton () { tooltip_text = "Select for bulk actions" });
            item.child = row;
        });
        f.bind.connect ((obj) => {
            var item = (Gtk.ListItem) obj;
            var inst = (Instance) item.item;
            var row = (Gtk.Box) item.child;
            var dot = (Gtk.Image) row.get_first_child ();
            dot.remove_css_class ("success"); dot.remove_css_class ("dim-label");
            dot.add_css_class (inst.running ? "success" : "dim-label");
            Gtk.Widget w = dot.get_next_sibling ();
            var group = group_label.text.strip ();
            ((Gtk.Label) w).label = group == "" ? inst.name : (inst.labels.lookup (group) ?? "Unlabelled") + " · " + inst.name;
            w.tooltip_text = ((Gtk.Label) w).label;
            w = w.get_next_sibling ();
            var mem = inst.running ? " · %s".printf (format_size ((uint64) inst.memory_bytes)) : "";
            ((Gtk.Label) w).label = "%s · %s%s%s".printf (
                inst.kind == "virtual-machine" ? "VM" : "Container", inst.status,
                inst.ipv4 != "" ? " · " + inst.ipv4 : "", mem);
            var toggle = (Gtk.Button) w.get_next_sibling ();
            var shell = (Gtk.Button) toggle.get_next_sibling ();
            var snap = (Gtk.Button) shell.get_next_sibling ();
            var del = (Gtk.Button) snap.get_next_sibling ();
            var info = (Gtk.Button) del.get_next_sibling ();
            toggle.label = inst.running ? "Stop" : "Start";
            shell.sensitive = inst.running;
            // Replace handlers on rebind by cloning-free approach: handler ids stored on the item.
            disconnect_stored (item);
            var ids = new HandlerIds ();
            var n = inst.name;
            var running = inst.running;
            ids.a = toggle.clicked.connect (() => { act.begin (n, running ? "stop" : "start"); });
            ids.b = shell.clicked.connect (() => { open_shell (n); });
            ids.c = snap.clicked.connect (() => { open_snapshots (n); });
            ids.d = del.clicked.connect (() => { confirm_delete (n); });
            ids.e = info.clicked.connect (() => { new InstanceDetails (this, client, n).present (); });
            var selected = (Gtk.CheckButton) info.get_next_sibling ();
            selected.active = selected_names.contains (n); selected.tooltip_text = "Select " + n;
            selected.update_property (Gtk.AccessibleProperty.LABEL, "Select " + n, -1);
            ids.f = selected.toggled.connect (() => {
                if (selected.active) selected_names.add (n); else selected_names.remove (n);
                update_selection_ui ();
            });
            toggle.sensitive = !pending.contains (n);
            item.set_data<HandlerIds> ("ids", ids);
        });
        f.unbind.connect ((obj) => { disconnect_stored ((Gtk.ListItem) obj); });
        return f;
    }

    private void disconnect_stored (Gtk.ListItem item) {
        var ids = item.steal_data<HandlerIds> ("ids");
        if (ids == null || item.child == null) return;
        var row = (Gtk.Box) item.child;
        var name = row.get_first_child ().get_next_sibling ().get_next_sibling ();
        var toggle = name.get_next_sibling ();
        var shell = toggle.get_next_sibling ();
        var snap = shell.get_next_sibling ();
        var del = snap.get_next_sibling ();
        SignalHandler.disconnect (toggle, ids.a);
        SignalHandler.disconnect (shell, ids.b);
        SignalHandler.disconnect (snap, ids.c);
        SignalHandler.disconnect (del, ids.d);
        SignalHandler.disconnect (del.get_next_sibling (), ids.e);
        SignalHandler.disconnect (del.get_next_sibling ().get_next_sibling (), ids.f);
    }

    // ----- New instance dialog -----
    private void open_new_instance (string initial_image = "ubuntu/24.04", bool initial_vm = false) {
        var dlg = new Gtk.Window () { transient_for = this, modal = true, title = "New instance", default_width = 380 };
        var box = new Gtk.Box (Gtk.Orientation.VERTICAL, 12) { margin_top = 18, margin_bottom = 18, margin_start = 18, margin_end = 18 };
        var name = new Gtk.Entry () { placeholder_text = "Name (e.g. web-1)", activates_default = true };
        var image = new Gtk.Entry () { text = initial_image, placeholder_text = "System image alias or local:fingerprint" };
        var cpus = new Gtk.SpinButton.with_range (1, 256, 1) { value = 2 };
        var memory = new Gtk.Entry () { text = "2GiB", placeholder_text = "Memory limit, e.g. 2GiB" };
        var ephemeral = new Gtk.CheckButton.with_label ("Delete automatically after stopping");
        var vm = new Gtk.CheckButton.with_label ("Virtual machine (default: container)") { active = initial_vm };
        var environment = new Gtk.TextView () { monospace = true, height_request = 70 };
        var labels = new Gtk.TextView () { monospace = true, height_request = 60 };
        var hint = new Gtk.Label ("Images come from images.linuxcontainers.org. The first launch downloads the image.") { wrap = true, xalign = 0 };
        hint.add_css_class ("dim-label");
        var create = new Gtk.Button.with_label ("Create") { halign = Gtk.Align.END };
        create.add_css_class ("suggested-action");
        create.clicked.connect (() => {
            var n = name.text.strip ();
            var img = image.text.strip ();
            if (n == "" || img == "") { toast.title = "Enter a name and an image"; toast.send_notification (); return; }
            var config = new Json.Object ();
            foreach (var line in environment.buffer.text.split ("\n")) {
                if (line.strip () == "") continue;
                int separator = line.index_of_char ('=');
                if (separator <= 0) { toast.title = "Use KEY=value for each environment variable."; toast.send_notification (); return; }
                config.set_string_member ("environment." + line.substring (0, separator).strip (), line.substring (separator + 1));
            }
            foreach (var line in labels.buffer.text.split ("\n")) {
                if (line.strip () == "") continue;
                int separator = line.index_of_char ('=');
                if (separator <= 0) { toast.title = "Use key=value for each label."; toast.send_notification (); return; }
                var key = line.substring (0, separator).strip ();
                config.set_string_member (key.has_prefix ("user.") ? key : "user." + key, line.substring (separator + 1));
            }
            dlg.destroy ();
            config.set_string_member ("limits.cpu", ((int) cpus.value).to_string ());
            config.set_string_member ("limits.memory", memory.text.strip ());
            launch.begin (n, img, vm.active, config, ephemeral.active);
        });
        box.append (name); box.append (image); box.append (vm);
        box.append (new Gtk.Label ("CPU cores") { xalign = 0 }); box.append (cpus);
        box.append (new Gtk.Label ("Memory limit") { xalign = 0 }); box.append (memory);
        box.append (ephemeral);
        box.append (new Gtk.Label ("Environment variables (KEY=value, one per line)") { xalign = 0 }); box.append (new Gtk.ScrolledWindow () { child = environment, min_content_height = 70 });
        box.append (new Gtk.Label ("Labels (key=value, one per line)") { xalign = 0 }); box.append (new Gtk.ScrolledWindow () { child = labels, min_content_height = 60 });
        box.append (hint); box.append (create);
        dlg.child = new Gtk.ScrolledWindow () { child = box, propagate_natural_height = true, min_content_height = 300, max_content_height = 600 };
        dlg.default_height = 650;
        dlg.present ();
    }

    private async void launch (string name, string image, bool vm, Json.Object config, bool ephemeral) {
        toast.title = "Creating %s…".printf (name); toast.send_notification ();
        try {
            yield client.create_instance (name, image, vm, config, ephemeral);
            toast.title = "%s is running".printf (name);
        } catch (Error e) {
            toast.title = e.message;
        }
        toast.send_notification ();
        yield reload ();
    }

    // ----- Snapshots dialog -----
    private void open_snapshots (string instance) {
        var dlg = new Gtk.Window () { transient_for = this, modal = true, title = "Snapshots of %s".printf (instance),
            default_width = 420, default_height = 360 };
        var list = new Gtk.Box (Gtk.Orientation.VERTICAL, 6) { margin_top = 12, margin_bottom = 12, margin_start = 12, margin_end = 12 };
        var scroller = new Gtk.ScrolledWindow () { child = list, vexpand = true };
        var take = new Gtk.Button.with_label ("Take snapshot") { margin_top = 6, margin_bottom = 12, margin_start = 12, margin_end = 12, halign = Gtk.Align.END };
        take.add_css_class ("suggested-action");
        var outer = new Gtk.Box (Gtk.Orientation.VERTICAL, 0);
        outer.append (scroller); outer.append (take);
        dlg.child = outer;

        take.clicked.connect (() => { snapshot_then.begin (instance, () => { fill_snapshots.begin (instance, list, dlg); }); });
        fill_snapshots.begin (instance, list, dlg);
        dlg.present ();
    }

    private delegate void Done ();

    private async void snapshot_then (string instance, owned Done done) {
        yield take_snapshot (instance);
        done ();
    }

    private async void fill_snapshots (string instance, Gtk.Box list, Gtk.Window dlg) {
        Gtk.Widget? w;
        while ((w = list.get_first_child ()) != null) list.remove (w);
        try {
            var snaps = yield client.list_snapshots (instance);
            if (snaps.length == 0) {
                var empty = new Gtk.Label ("No snapshots yet.") { xalign = 0 };
                empty.add_css_class ("dim-label");
                list.append (empty);
            }
            foreach (var snap in snaps) {
                var row = new Gtk.Box (Gtk.Orientation.HORIZONTAL, 8);
                row.append (new Gtk.Label (snap) { xalign = 0, hexpand = true });
                var restore = new Gtk.Button.with_label ("Restore");
                var remove = new Gtk.Button.from_icon_name ("edit-delete-symbolic") { tooltip_text = "Delete snapshot" };
                var s = snap;
                restore.clicked.connect (() => { confirm_restore (instance, s, dlg); });
                remove.clicked.connect (() => {
                    var confirmation = new Gtk.AlertDialog ("Delete snapshot %s?".printf (s)) {
                        detail = "This snapshot will be permanently removed.", buttons = { "Cancel", "Delete" }, cancel_button = 0, default_button = 0
                    };
                    confirmation.choose.begin (dlg, null, (obj, result) => {
                        try {
                            if (confirmation.choose.end (result) == 1) delete_snapshot.begin (instance, s, () => { fill_snapshots.begin (instance, list, dlg); });
                        } catch (Error e) { }
                    });
                });
                row.append (restore); row.append (remove);
                list.append (row);
            }
        } catch (Error e) {
            list.append (new Gtk.Label (e.message) { wrap = true, xalign = 0 });
        }
    }

    private async void delete_snapshot (string instance, string snap, owned Done done) {
        try {
            yield client.delete_snapshot (instance, snap);
        } catch (Error e) {
            toast.title = e.message; toast.send_notification ();
        }
        done ();
    }

    private void confirm_restore (string instance, string snap, Gtk.Window parent) {
        var dlg = new Granite.MessageDialog.with_image_from_icon_name (
            "Restore %s to %s?".printf (instance, snap),
            "Changes made after this snapshot will be lost.",
            "dialog-warning", Gtk.ButtonsType.CANCEL) { transient_for = parent, modal = true };
        dlg.add_button ("Restore", Gtk.ResponseType.ACCEPT);
        dlg.response.connect ((r) => {
            dlg.destroy ();
            if (r == Gtk.ResponseType.ACCEPT) do_restore.begin (instance, snap);
        });
        dlg.present ();
    }

    private async void do_restore (string instance, string snap) {
        try {
            yield client.restore_snapshot (instance, snap);
            toast.title = "Restored %s to %s".printf (instance, snap);
        } catch (Error e) {
            toast.title = e.message;
        }
        toast.send_notification ();
        yield reload ();
    }

    private async void reload () {
        if (loading) return;
        loading = true;
        try {
            var items = yield client.list_instances ();
            var live_names = new GenericSet<string> (str_hash, str_equal);
            foreach (var item in items) live_names.add (item.name);
            string[] gone = {}; selected_names.foreach ((name) => { if (!live_names.contains (name)) gone += name; });
            foreach (var name in gone) selected_names.remove (name);
            update_selection_ui ();
            if (dashboard != null) dashboard.update (items);
            if (get_monotonic_time () - last_storage_refresh > 60000000) refresh_storage.begin ();
            store.remove_all ();
            int running = 0;
            var ordered = new List<Instance> ();
            foreach (var item in items) ordered.append (item);
            ordered.sort_with_data ((a, b) => {
                var group = group_label.text.strip ();
                if (group != "") {
                    int comparison = (a.labels.lookup (group) ?? "").collate (b.labels.lookup (group) ?? "");
                    if (comparison != 0) return comparison;
                }
                if (sort_order.selected == 1) return b.name.collate (a.name);
                if (sort_order.selected == 2 && a.memory_bytes != b.memory_bytes) return a.memory_bytes > b.memory_bytes ? -1 : 1;
                if (sort_order.selected == 3 && a.status != b.status) return a.status.collate (b.status);
                return a.name.collate (b.name);
            });
            foreach (var i in ordered) {
                if (i.running) running++;
                if (kind_filter.selected == 1 && i.kind != "container") continue;
                if (kind_filter.selected == 2 && i.kind != "virtual-machine") continue;
                if (PaletteMatch.score (search.text, i.name + " " + i.image + " " + i.status) < 0) continue;
                store.append (i);
            }
            status_label.label = "%d instances · %d running".printf (items.length, running);
        } catch (Error e) {
            status_label.label = "Cannot reach Incus: " + e.message;
            if (dashboard != null) dashboard.set_error (e.message);
        }
        loading = false;
    }

    private async void act (string name, string action) {
        if (pending.contains (name)) return;
        pending.add (name);
        try {
            toast.title = "%s %s…".printf (action, name); toast.send_notification ();
            yield client.change_state (name, action);
            toast.title = "%s: %s complete".printf (name, action); toast.send_notification ();
        } catch (Error e) {
            toast.title = e.message; toast.send_notification ();
        }
        pending.remove (name);
        yield reload ();
    }

    private async void take_snapshot (string name) {
        var snap = "snap-" + new DateTime.now_local ().format ("%Y%m%d-%H%M%S");
        try {
            yield client.create_snapshot (name, snap);
            toast.title = "Created %s on %s".printf (snap, name);
        } catch (Error e) {
            toast.title = e.message;
        }
        toast.send_notification ();
        yield reload ();
    }

    private void open_shell (string name) {
        try {
            var terminal = preferences.read ("terminal", "io.elementary.terminal");
            string[] arguments;
            if (terminal == "io.elementary.terminal") arguments = { terminal, "-e", "incus exec %s -- %s".printf (Shell.quote (name), Shell.quote (preferences.shell)) };
            else if (terminal == "xterm") arguments = { terminal, "-e", "incus", "exec", name, "--", preferences.shell };
            else arguments = { terminal, "--", "incus", "exec", name, "--", preferences.shell };
            var environment = Environ.set_variable (Environ.get (), "INCUS_SOCKET", Environment.get_variable ("INCUS_SOCKET") ?? preferences.read ("socket", "/var/lib/incus/unix.socket"), true);
            Process.spawn_async (null, arguments, environment, SpawnFlags.SEARCH_PATH, null, null);
        } catch (Error e) {
            toast.title = e.message; toast.send_notification ();
        }
    }

    private void confirm_delete (string name) {
        var dlg = new Granite.MessageDialog.with_image_from_icon_name (
            "Delete %s?".printf (name),
            "The instance and all of its snapshots will be permanently removed.",
            "dialog-warning", Gtk.ButtonsType.CANCEL) { transient_for = this, modal = true };
        var del = dlg.add_button ("Delete", Gtk.ResponseType.ACCEPT);
        del.add_css_class ("destructive-action");
        dlg.response.connect ((r) => {
            dlg.destroy ();
            if (r == Gtk.ResponseType.ACCEPT) del_instance.begin (name);
        });
        dlg.present ();
    }

    private async void del_instance (string name) {
        try {
            var current = yield client.inspect_instance (name);
            if (current.get_object_member ("metadata").get_string_member ("status") != "Stopped") {
                yield client.change_state (name, "stop", true);
            }
            if (!current.get_object_member ("metadata").get_boolean_member_with_default ("ephemeral", false) || current.get_object_member ("metadata").get_string_member ("status") == "Stopped") yield client.delete_instance (name);
        } catch (Error e) {
            toast.title = e.message; toast.send_notification ();
        }
        yield reload ();
    }
    private void open_preferences () {
        var dialog = new Gtk.Window () { transient_for = this, modal = true, title = "Preferences", default_width = 420 };
        var box = new Gtk.Box (Gtk.Orientation.VERTICAL, 12) { margin_top = 18, margin_bottom = 18, margin_start = 18, margin_end = 18 };
        box.append (new Gtk.Label ("Container shell") { xalign = 0 });
        var shell = new Gtk.Entry () { text = preferences.shell };
        box.append (shell);
        box.append (new Gtk.Label ("Terminal application") { xalign = 0 });
        string[] terminals = { "io.elementary.terminal", "gnome-terminal", "kgx", "xterm" };
        var terminal = new Gtk.DropDown.from_strings (terminals);
        for (uint i = 0; i < terminals.length; i++) if (terminals[i] == preferences.read ("terminal", "io.elementary.terminal")) terminal.selected = i;
        box.append (terminal);
        box.append (new Gtk.Label ("Incus Unix socket (restart Orchard and its panel to apply)") { xalign = 0, wrap = true });
        var socket = new Gtk.Entry () { text = preferences.read ("socket", "/var/lib/incus/unix.socket") };
        box.append (socket);
        var save = new Gtk.Button.with_label ("Save") { halign = Gtk.Align.END };
        save.clicked.connect (() => {
            try {
                if (!shell.text.has_prefix ("/") || shell.text.contains ("\n")) throw new IOError.INVALID_ARGUMENT ("Enter an absolute shell path, such as /bin/sh.");
                if (!socket.text.has_prefix ("/")) throw new IOError.INVALID_ARGUMENT ("Enter an absolute socket path.");
                preferences.write ("shell", shell.text.strip ());
                preferences.write ("terminal", terminals[terminal.selected]);
                preferences.write ("socket", socket.text.strip ());
                dialog.destroy ();
            } catch (Error e) { toast.title = e.message; toast.send_notification (); }
        });
        box.append (save); dialog.child = box; dialog.present ();
    }
    public void navigate_uri (string uri_text) {
        try {
            var uri = Uri.parse (uri_text, UriFlags.NONE);
            if ((uri.get_scheme () ?? "").down () != "orchard") throw new IOError.INVALID_ARGUMENT ("Not an Orchard link.");
            var section = (uri.get_host () ?? "").down ();
            var target = Uri.unescape_string (uri.get_path ()) ?? "";
            while (target.has_prefix ("/")) target = target.substring (1);
            if (section == "container" || section == "machine") {
                content_stack.visible_child_name = "instances";
                kind_filter.selected = section == "machine" ? 2 : 1;
                search.text = target;
                if (target != "") new InstanceDetails (this, client, target).present ();
            } else if (section == "containers" || section == "machines") {
                content_stack.visible_child_name = "instances";
                kind_filter.selected = section == "machines" ? 2 : 1;
            } else if (section == "podman") {
                content_stack.visible_child_name = "podman";
            } else if (section == "dashboard" || section == "models" || section == "sandboxes" || section == "systemlogs" || section == "mount" || section == "mounts") {
                dispatch_command (section == "systemlogs" ? "system" : section == "mount" ? "mounts" : section, target);
            } else if (section == "image" || section == "images" || section == "network" || section == "networks" || section == "dns" || section == "profiles" || section == "projects") {
                var kind = section == "image" ? "images" : section == "network" ? "networks" : section == "dns" ? "network-zones" : section;
                new ResourceBrowser (this, client, kind, target).present ();
            } else {
                throw new IOError.NOT_SUPPORTED ("This Orchard destination is not available in the Incus-only runtime: " + section);
            }
        } catch (Error e) { toast.title = e.message; toast.send_notification (); }
    }
    private void open_dashboard () {
        content_stack.visible_child_name = "dashboard";
        reload.begin ();
    }

    private void dispatch_command (string action, string target) {
        switch (action) {
        case "dashboard": open_dashboard (); break;
        case "models": new ModelsWindow (this).present (); break;
        case "sandboxes": new SandboxesWindow (this, client).present (); break;
        case "system": new SystemWindow (this, client).present (); break;
        case "mounts": new MountsWindow (this, client).present (); break;
        case "create": open_new_instance (); break;
        case "preferences": open_preferences (); break;
        case "refresh": reload.begin (); break;
        case "shell": open_shell (target); break;
        case "stop": case "start": case "restart": act.begin (target, action); break;
        case "inspect": new InstanceDetails (this, client, target).present (); break;
        case "logs": new LogViewer (this, client, target).present (); break;
        default: new ResourceBrowser (this, client, action, target).present (); break;
        }
    }
    private void confirm_bulk (string action) {
        if (selected_names.length == 0) return;
        string[] names = {};
        selected_names.foreach ((name) => { names += name; });
        var question = new Gtk.AlertDialog ("%s %u selected instances?".printf (action, selected_names.length)) {
            detail = string.joinv ("\n", names) + (action == "delete" ? "\nInstances and snapshots will be permanently removed." : ""),
            buttons = { "Cancel", "Confirm" }, cancel_button = 0, default_button = 0
        };
        question.choose.begin (this, null, (obj, result) => { try { if (question.choose.end (result) == 1) apply_bulk.begin (action, names); } catch (Error e) { } });
    }
    private async void apply_bulk (string action, string[] names) {
        int success = 0;
        var failures = new StringBuilder ();
        foreach (var name in names) {
            if (pending.contains (name)) { failures.append (name + ": already busy\n"); continue; }
            pending.add (name);
            try {
                if (action == "delete") {
                    var current = yield client.inspect_instance (name);
                    if (current.get_object_member ("metadata").get_string_member ("status") != "Stopped") yield client.change_state (name, "stop", true);
                    if (!current.get_object_member ("metadata").get_boolean_member_with_default ("ephemeral", false) || current.get_object_member ("metadata").get_string_member ("status") == "Stopped") yield client.delete_instance (name);
                    selected_names.remove (name);
                } else yield client.change_state (name, action);
                success++;
            } catch (Error e) { failures.append (name + ": " + e.message + "\n"); }
            pending.remove (name);
        }
        yield reload ();
        update_selection_ui ();
        var outcome = new Gtk.AlertDialog ("%d of %d actions completed".printf (success, names.length)) { detail = failures.str == "" ? "All selected operations succeeded." : failures.str };
        outcome.show (this);
    }
    public void create_from_image (string fingerprint, bool vm) { open_new_instance ("local:" + fingerprint, vm); }
    public void open_instance_shell (string name) { open_shell (name); }
    private async void refresh_storage () {
        if (storage_busy) return;
        storage_busy = true;
        try {
            var text = new StringBuilder ();
            var images = yield client.call ("GET", "/1.0/images?recursion=1");
            int64 sizes = 0;
            foreach (var node in images.get_array_member ("metadata").get_elements ()) sizes += node.get_object ().get_int_member_with_default ("size", 0);
            text.append ("Cached images · " + format_size ((uint64) sizes) + " (reported image sizes)\n");
            var pools = yield client.call ("GET", "/1.0/storage-pools?recursion=1");
            foreach (var node in pools.get_array_member ("metadata").get_elements ()) {
                var name = node.get_object ().get_string_member ("name");
                var resources = yield client.call ("GET", "/1.0/storage-pools/" + Uri.escape_string (name, null, false) + "/resources");
                var space = resources.get_object_member ("metadata").get_object_member ("space");
                text.append ("Pool " + name + " · " + format_size ((uint64) space.get_int_member_with_default ("used", 0)) + " used of " + format_size ((uint64) space.get_int_member_with_default ("total", 0)) + "\n");
            }
            if (dashboard != null) dashboard.set_storage (text.str);
        } catch (Error e) { if (dashboard != null) dashboard.set_storage ("Storage accounting unavailable: " + e.message); }
        last_storage_refresh = get_monotonic_time (); storage_busy = false;
    }
}
