/* SPDX-License-Identifier: GPL-3.0-or-later
 * SPDX-FileCopyrightText: 2026 ElementaryOS_MSeries
 * BlueZ controls for the right-hand Quick Settings menu. No discovery runs in the background;
 * pairing and authentication remain in the desktop's Bluetooth settings and pairing agent.
 */
public class QuickSettings.Bluetooth : Gtk.Box {
    private Granite.SwitchModelButton toggle;
    private Gtk.Box devices;
    private Gtk.Label status;
    private DBusObjectManagerClient? manager;
    private Cancellable cancellable = new Cancellable ();
    private bool updating = false;
    private bool radio_busy = false;
    private bool refreshing = false;
    private HashTable<string, bool> pending = new HashTable<string, bool> (str_hash, str_equal);

    construct {
        orientation = Gtk.Orientation.VERTICAL;
        toggle = new Granite.SwitchModelButton (_("Bluetooth")) {
            description = _("Connect to saved devices"),
            sensitive = false
        };
        append (toggle);
        devices = new Gtk.Box (Gtk.Orientation.VERTICAL, 3) {
            margin_start = 12, margin_end = 12
        };
        append (devices);
        status = new Gtk.Label (null) {
            wrap = true, xalign = 0, visible = false,
            margin_start = 12, margin_end = 12
        };
        status.add_css_class (Granite.CssClass.DIM);
        append (status);
        var settings = new Gtk.Button.with_label (_("Bluetooth Settings…")) {
            halign = Gtk.Align.START, margin_start = 6, margin_end = 6
        };
        settings.add_css_class ("flat");
        settings.clicked.connect (() => {
            try {
                AppInfo.launch_default_for_uri ("settings://bluetooth", null);
                var popover = get_ancestor (typeof (Gtk.Popover)) as Gtk.Popover;
                if (popover != null) popover.popdown ();
            } catch (Error e) {
                show_error (_("Could not open Bluetooth settings."));
            }
        });
        append (settings);
        toggle.notify["active"].connect (() => {
            if (!updating && !radio_busy) set_power.begin (toggle.active);
        });
        map.connect (refresh);
        initialize.begin ();
    }

    public override void dispose () {
        cancellable.cancel ();
        base.dispose ();
    }

    private async void initialize () {
        try {
            manager = yield new DBusObjectManagerClient.for_bus (
                BusType.SYSTEM, DBusObjectManagerClientFlags.DO_NOT_AUTO_START,
                "org.bluez", "/", null, cancellable
            );
            manager.object_added.connect (() => refresh_if_mapped ());
            manager.object_removed.connect (() => refresh_if_mapped ());
            manager.interface_added.connect (() => refresh_if_mapped ());
            manager.interface_removed.connect (() => refresh_if_mapped ());
            manager.interface_proxy_properties_changed.connect (() => refresh_if_mapped ());
            manager.notify["name-owner"].connect (() => refresh_if_mapped ());
            refresh ();
        } catch (Error e) {
            if (!cancellable.is_cancelled ()) {
                info ("Bluetooth service unavailable: %s", e.message);
                toggle.tooltip_text = _("Bluetooth service unavailable");
                show_error (_("Open Bluetooth settings to check the Bluetooth service."));
            }
        }
    }

    private static bool flag (DBusProxy proxy, string name) {
        var value = proxy.get_cached_property (name);
        return value != null && value.get_boolean ();
    }

    private static string device_name (DBusProxy proxy) {
        var value = proxy.get_cached_property ("Alias") ?? proxy.get_cached_property ("Name")
            ?? proxy.get_cached_property ("Address");
        return value != null ? value.get_string () : _("Bluetooth device");
    }

    private void show_error (string message) {
        status.label = message;
        status.visible = true;
    }

    private void refresh_if_mapped () {
        if (get_mapped ()) refresh ();
    }

    private void refresh () {
        if (refreshing) return;
        refreshing = true;
        rebuild ();
        refreshing = false;
    }

    private void rebuild () {
        bool powered = false;
        int adapters = 0;
        var saved = new GenericArray<DBusProxy> ();
        if (manager != null && manager.name_owner != null) {
            foreach (var obj in manager.get_objects ()) {
                var adapter = obj.get_interface ("org.bluez.Adapter1") as DBusProxy;
                if (adapter != null) {
                    adapters++;
                    powered = powered || flag (adapter, "Powered");
                }
                var device = obj.get_interface ("org.bluez.Device1") as DBusProxy;
                if (device != null && (flag (device, "Paired") || flag (device, "Bonded") || flag (device, "Connected"))) {
                    saved.add (device);
                }
            }
        }
        updating = true;
        toggle.active = powered;
        toggle.sensitive = adapters > 0 && !radio_busy;
        toggle.tooltip_text = adapters == 0 ? _("No Bluetooth adapter available")
            : (powered ? _("On") : _("Off"));
        updating = false;
        while (devices.get_first_child () != null) devices.remove (devices.get_first_child ());
        devices.visible = powered;
        if (!powered) return;
        saved.sort ((a, b) => {
            bool ac = flag (a, "Connected"), bc = flag (b, "Connected");
            if (ac != bc) return ac ? -1 : 1;
            return device_name (a).collate (device_name (b));
        });
        if (saved.length == 0) {
            var empty = new Gtk.Label (_("No saved devices. Pair a device in Bluetooth Settings.")) {
                wrap = true, xalign = 0
            };
            empty.add_css_class (Granite.CssClass.DIM);
            devices.append (empty);
        }
        for (uint i = 0; i < saved.length; i++) {
            var device = saved[i];
            bool connected = flag (device, "Connected");
            var path = device.get_object_path ();
            var icon_value = device.get_cached_property ("Icon");
            var icon = new Gtk.Image.from_icon_name (icon_value != null ? icon_value.get_string () : "bluetooth-symbolic");
            var name = new Gtk.Label (device_name (device)) {
                xalign = 0, hexpand = true, ellipsize = Pango.EllipsizeMode.END,
                max_width_chars = 22, tooltip_text = device_name (device)
            };
            var button = new Gtk.Button.with_label (
                pending.contains (path) ? _("Working…") : (connected ? _("Disconnect") : _("Connect"))
            ) { sensitive = !pending.contains (path) && !radio_busy };
            button.clicked.connect (() => change_device.begin (device, !connected));
            var row = new Gtk.Box (Gtk.Orientation.HORIZONTAL, 8);
            row.append (icon);
            row.append (name);
            row.append (button);
            devices.append (row);
        }
    }

    private async void set_power (bool enabled) {
        if (manager == null) return;
        radio_busy = true;
        status.visible = false;
        refresh ();
        try {
            foreach (var obj in manager.get_objects ()) {
                var adapter = obj.get_interface ("org.bluez.Adapter1") as DBusProxy;
                if (adapter == null) continue;
                yield adapter.get_connection ().call (
                    "org.bluez", adapter.get_object_path (), "org.freedesktop.DBus.Properties", "Set",
                    new Variant ("(ssv)", "org.bluez.Adapter1", "Powered", new Variant.boolean (enabled)),
                    null, DBusCallFlags.NONE, 5000, cancellable
                );
            }
        } catch (Error e) {
            if (!cancellable.is_cancelled ()) show_error (_("Could not change Bluetooth power. Check airplane mode or Bluetooth settings."));
        }
        radio_busy = false;
        refresh ();
    }

    private async void change_device (DBusProxy device, bool connect_device) {
        var path = device.get_object_path ();
        if (pending.contains (path)) return;
        pending.insert (path, true);
        status.visible = false;
        refresh ();
        try {
            yield device.call (connect_device ? "Connect" : "Disconnect", null,
                DBusCallFlags.NONE, 20000, cancellable);
        } catch (Error e) {
            if (!cancellable.is_cancelled ()) {
                show_error (connect_device
                    ? _("Could not connect to %s. Make sure it is nearby and ready to connect.").printf (device_name (device))
                    : _("Could not disconnect %s.").printf (device_name (device)));
            }
        }
        pending.remove (path);
        refresh ();
    }
}
