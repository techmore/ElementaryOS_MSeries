/* SPDX-License-Identifier: GPL-3.0-or-later
 * SPDX-FileCopyrightText: 2026 ElementaryOS_MSeries
 * Tailscale menu shared by the top panel indicator and the Work Mode taskbar.
 * Reads `tailscale status --json` (no root). On/off runs `tailscale up` / `tailscale down`,
 * which needs the operator setting; without it the menu shows the one-time command.
 */
namespace MSeries.Tailscale {
    public class Device : Object {
        public string name { get; set; default = ""; }
        public string dns_name { get; set; default = ""; }
        public string ip { get; set; default = ""; }
        public string os { get; set; default = ""; }
        public bool online { get; set; }

        /* First MagicDNS label, e.g. "sdolbec-ser8". */
        public string ssh_host {
            owned get {
                var host = dns_name.split (".")[0];
                return host != null && host != "" ? host : ip;
            }
        }

        public static Device? from_json (Json.Object node) {
            var device = new Device ();
            device.name = node.has_member ("HostName") ? node.get_string_member ("HostName") : "";
            device.dns_name = node.has_member ("DNSName") ? node.get_string_member ("DNSName") : "";
            device.os = node.has_member ("OS") ? node.get_string_member ("OS") : "";
            device.online = node.has_member ("Online") && node.get_boolean_member ("Online");
            if (node.has_member ("TailscaleIPs")) {
                var ips = node.get_array_member ("TailscaleIPs");
                for (uint i = 0; i < ips.get_length (); i++) {
                    var ip = ips.get_string_element (i);
                    // Prefer IPv4: it is what people type after `ssh`.
                    if (device.ip == "" || !ip.contains (":")) {
                        device.ip = ip;
                        if (!ip.contains (":")) break;
                    }
                }
            }
            // Phones often report "localhost"; the MagicDNS name is more useful.
            if (device.name == "" || device.name == "localhost") device.name = device.ssh_host;
            return device.ip != "" ? device : null;
        }
    }

    public enum State { UNKNOWN, NOT_RUNNING, STOPPED, NEEDS_LOGIN, CONNECTED }

    public class Panel : Gtk.Box {
        public State state { get; private set; default = State.UNKNOWN; }
        public signal void close_request ();

        private Granite.SwitchModelButton toggle;
        private Gtk.Label self_label;
        private Gtk.Box self_row;
        private Gtk.Box device_list;
        private Gtk.ScrolledWindow scroller;
        private Gtk.Label message;
        private Gtk.Box setup_box;
        private Gtk.Button login_button;
        private Device? self_device = null;
        private string auth_url = "";
        private bool updating = false;
        private bool busy = false;
        private bool refreshing = false;
        private uint timer = 0;
        private Cancellable cancellable = new Cancellable ();

        construct {
            orientation = Gtk.Orientation.VERTICAL;
            spacing = 0;
            width_request = 320;
            margin_top = 3;
            margin_bottom = 3;

            toggle = new Granite.SwitchModelButton ("Tailscale") {
                description = "Checking…"
            };
            toggle.notify["active"].connect (() => {
                if (!updating && !busy) set_running.begin (toggle.active);
            });
            append (toggle);

            // This machine: name and IP, click to copy.
            self_label = new Gtk.Label (null) { xalign = 0, hexpand = true, ellipsize = Pango.EllipsizeMode.END };
            self_label.add_css_class (Granite.CssClass.DIM);
            var self_copy = icon_button ("edit-copy-symbolic", "Copy this device's IP");
            self_copy.clicked.connect (() => {
                if (self_device != null) copy_text (self_device.ip, self_label, "Copied " + self_device.ip);
            });
            self_row = new Gtk.Box (Gtk.Orientation.HORIZONTAL, 6) { margin_start = 12, margin_end = 6, visible = false };
            self_row.append (self_label);
            self_row.append (self_copy);
            append (self_row);

            message = new Gtk.Label (null) {
                wrap = true, xalign = 0, visible = false, selectable = true,
                margin_start = 12, margin_end = 12, margin_top = 3, margin_bottom = 3, max_width_chars = 36
            };
            message.add_css_class (Granite.CssClass.DIM);
            append (message);

            // One-time setup so on/off works without sudo.
            setup_box = new Gtk.Box (Gtk.Orientation.HORIZONTAL, 6) { margin_start = 12, margin_end = 6, visible = false };
            var setup_command = new Gtk.Label (operator_command ()) {
                xalign = 0, hexpand = true, selectable = true, wrap = true, wrap_mode = Pango.WrapMode.CHAR
            };
            setup_command.add_css_class (Granite.CssClass.MONOSPACE);
            var setup_copy = icon_button ("edit-copy-symbolic", "Copy command");
            setup_copy.clicked.connect (() => copy_text (operator_command (), message, "Copied. Paste it in Terminal, then try again."));
            setup_box.append (setup_command);
            setup_box.append (setup_copy);
            append (setup_box);

            login_button = new Gtk.Button () { child = new Gtk.Label ("Log In…") { xalign = 0 }, visible = false };
            login_button.add_css_class ("menuitem");
            login_button.add_css_class ("flat");
            login_button.clicked.connect (() => {
                if (auth_url != "") open_uri (auth_url);
                else run_detached ({ "tailscale", "login" });
            });
            append (login_button);

            append (new Gtk.Separator (Gtk.Orientation.HORIZONTAL) { margin_top = 3, margin_bottom = 3 });

            device_list = new Gtk.Box (Gtk.Orientation.VERTICAL, 0);
            scroller = new Gtk.ScrolledWindow () {
                child = device_list,
                hscrollbar_policy = Gtk.PolicyType.NEVER,
                propagate_natural_height = true,
                max_content_height = 420
            };
            append (scroller);

            append (new Gtk.Separator (Gtk.Orientation.HORIZONTAL) { margin_top = 3, margin_bottom = 3 });
            var admin = new Gtk.Button () { child = new Gtk.Label ("Admin Console…") { xalign = 0 } };
            admin.add_css_class ("menuitem");
            admin.add_css_class ("flat");
            admin.clicked.connect (() => open_uri ("https://login.tailscale.com/admin/machines"));
            append (admin);

            // Refresh on open; poll lightly so the panel icon follows the connection.
            map.connect (() => { refresh.begin (); schedule (5); });
            unmap.connect (() => schedule (60));
            schedule (60);
            refresh.begin ();
        }

        public override void dispose () {
            cancellable.cancel ();
            if (timer != 0) { Source.remove (timer); timer = 0; }
            base.dispose ();
        }

        private void schedule (uint seconds) {
            if (timer != 0) Source.remove (timer);
            timer = Timeout.add_seconds (seconds, () => { refresh.begin (); return Source.CONTINUE; });
        }

        private static string operator_command () {
            return "sudo tailscale set --operator=" + Environment.get_user_name ();
        }

        private static Gtk.Button icon_button (string icon, string tip) {
            var button = new Gtk.Button.from_icon_name (icon) { tooltip_text = tip, valign = Gtk.Align.CENTER };
            button.add_css_class ("flat");
            button.update_property (Gtk.AccessibleProperty.LABEL, tip, -1);
            return button;
        }

        public async void refresh () {
            if (refreshing || busy) return;
            refreshing = true;
            string stdout_text = "";
            string stderr_text = "";
            int status = -1;
            try {
                var proc = new Subprocess.newv ({ "tailscale", "status", "--json" },
                    SubprocessFlags.STDOUT_PIPE | SubprocessFlags.STDERR_PIPE);
                yield proc.communicate_utf8_async (null, cancellable, out stdout_text, out stderr_text);
                status = proc.get_exit_status ();
            } catch (Error e) {
                if (cancellable.is_cancelled ()) { refreshing = false; return; }
                stderr_text = e.message;
            }
            refreshing = false;
            // `status --json` still prints JSON when stopped; only a missing daemon gives none.
            if (stdout_text == null || stdout_text.strip () == "") {
                apply_unavailable (status == -1 ? "Tailscale isn't installed." : "Tailscale isn't running.");
                return;
            }
            try {
                var parser = new Json.Parser ();
                parser.load_from_data (stdout_text);
                apply_status (parser.get_root ().get_object ());
            } catch (Error e) {
                apply_unavailable ("Couldn't read Tailscale status.");
            }
        }

        private void apply_unavailable (string text) {
            state = State.NOT_RUNNING;
            set_toggle (false, text);
            toggle.sensitive = false;
            self_row.visible = false;
            login_button.visible = false;
            clear_devices ();
        }

        private void apply_status (Json.Object root) {
            var backend = root.has_member ("BackendState") ? root.get_string_member ("BackendState") : "";
            auth_url = root.has_member ("AuthURL") ? root.get_string_member ("AuthURL") : "";
            string tailnet = "";
            if (root.has_member ("CurrentTailnet") && root.get_member ("CurrentTailnet").get_node_type () == Json.NodeType.OBJECT) {
                var t = root.get_object_member ("CurrentTailnet");
                if (t.has_member ("Name")) tailnet = t.get_string_member ("Name");
            }
            toggle.sensitive = true;
            switch (backend) {
                case "Running":
                    state = State.CONNECTED;
                    set_toggle (true, tailnet != "" ? "Connected · " + tailnet : "Connected");
                    break;
                case "NeedsLogin":
                case "NeedsMachineAuth":
                    state = State.NEEDS_LOGIN;
                    set_toggle (false, backend == "NeedsLogin" ? "Logged out" : "Waiting for approval");
                    break;
                case "Starting":
                    state = State.STOPPED;
                    set_toggle (true, "Connecting…");
                    break;
                default:
                    state = State.STOPPED;
                    set_toggle (false, "Disconnected");
                    break;
            }
            login_button.visible = state == State.NEEDS_LOGIN;

            self_device = null;
            if (root.has_member ("Self") && root.get_member ("Self").get_node_type () == Json.NodeType.OBJECT) {
                self_device = Device.from_json (root.get_object_member ("Self"));
            }
            self_row.visible = self_device != null && state == State.CONNECTED;
            if (self_device != null) self_label.label = "This device: %s · %s".printf (self_device.ssh_host, self_device.ip);

            var devices = new GenericArray<Device> ();
            if (root.has_member ("Peer") && root.get_member ("Peer").get_node_type () == Json.NodeType.OBJECT) {
                var peers = root.get_object_member ("Peer");
                peers.foreach_member ((obj, key, node) => {
                    if (node.get_node_type () != Json.NodeType.OBJECT) return;
                    var d = Device.from_json (node.get_object ());
                    if (d != null) devices.add (d);
                });
            }
            devices.sort ((a, b) => {
                if (a.online != b.online) return a.online ? -1 : 1;
                return a.name.collate (b.name);
            });
            show_devices (devices);
        }

        private void set_toggle (bool active, string description) {
            updating = true;
            toggle.active = active;
            toggle.description = description;
            updating = false;
        }

        private void clear_devices () {
            Gtk.Widget? child;
            while ((child = device_list.get_first_child ()) != null) device_list.remove (child);
        }

        private void show_devices (GenericArray<Device> devices) {
            // Keep scroll position across refreshes while the menu is open.
            var offset = scroller.vadjustment.value;
            clear_devices ();
            if (state != State.CONNECTED) {
                var note = new Gtk.Label ("Connect to see your devices.") { xalign = 0, margin_start = 12, margin_end = 12, margin_top = 3, margin_bottom = 3 };
                note.add_css_class (Granite.CssClass.DIM);
                device_list.append (note);
                return;
            }
            bool offline_header = false;
            device_list.append (new Granite.HeaderLabel ("Devices") { margin_start = 12, margin_end = 12 });
            foreach (var device in devices) {
                if (!device.online && !offline_header) {
                    offline_header = true;
                    device_list.append (new Granite.HeaderLabel ("Offline") { margin_start = 12, margin_end = 12 });
                }
                device_list.append (device_row (device));
            }
            if (devices.length == 0) {
                var none = new Gtk.Label ("No other devices yet.") { xalign = 0, margin_start = 12 };
                none.add_css_class (Granite.CssClass.DIM);
                device_list.append (none);
            }
            Idle.add (() => { scroller.vadjustment.value = offset; return Source.REMOVE; });
        }

        private Gtk.Widget device_row (Device device) {
            var dot = new Gtk.Label ("●") { tooltip_text = device.online ? "Online" : "Offline" };
            dot.add_css_class (device.online ? Granite.CssClass.SUCCESS : Granite.CssClass.DIM);
            var name = new Gtk.Label (device.name) { xalign = 0, ellipsize = Pango.EllipsizeMode.END };
            var detail = new Gtk.Label ("%s · %s".printf (device.ip, pretty_os (device.os))) { xalign = 0, ellipsize = Pango.EllipsizeMode.END };
            detail.add_css_class (Granite.CssClass.SMALL);
            detail.add_css_class (Granite.CssClass.DIM);
            var text = new Gtk.Box (Gtk.Orientation.VERTICAL, 0) { hexpand = true };
            text.append (name);
            text.append (detail);
            var row_content = new Gtk.Box (Gtk.Orientation.HORIZONTAL, 8);
            row_content.append (dot);
            row_content.append (text);

            // Clicking the row copies the IP.
            var row = new Gtk.Button () { child = row_content, hexpand = true, tooltip_text = "Copy IP " + device.ip };
            row.add_css_class ("menuitem");
            row.add_css_class ("flat");
            row.clicked.connect (() => copy_text (device.ip, detail, "Copied IP " + device.ip));

            var ip_button = icon_button ("edit-copy-symbolic", "Copy IP");
            ip_button.clicked.connect (() => copy_text (device.ip, detail, "Copied IP " + device.ip));
            var ssh_command = "ssh " + device.ssh_host;
            var ssh_button = icon_button ("utilities-terminal-symbolic", "Copy “%s”".printf (ssh_command));
            ssh_button.clicked.connect (() => copy_text (ssh_command, detail, "Copied “" + ssh_command + "”"));

            var box = new Gtk.Box (Gtk.Orientation.HORIZONTAL, 0) { margin_end = 6 };
            box.append (row);
            box.append (ip_button);
            box.append (ssh_button);
            if (!device.online) {
                name.add_css_class (Granite.CssClass.DIM);
            }
            return box;
        }

        private static string pretty_os (string os) {
            switch (os) {
                case "linux": return "Linux";
                case "macOS": return "macOS";
                case "iOS": return "iOS";
                case "windows": return "Windows";
                case "android": return "Android";
                case "": return "Unknown";
                default: return os;
            }
        }

        /* Copy, then show a short confirmation in place of `label` for 1.5 s. */
        private void copy_text (string text, Gtk.Label label, string confirmation) {
            get_clipboard ().set_text (text);
            var previous = label.label;
            if (previous == confirmation) return;
            label.label = confirmation;
            label.add_css_class (Granite.CssClass.SUCCESS);
            var was_visible = label.visible;
            label.visible = true;
            Timeout.add (1500, () => {
                if (label.label == confirmation) {
                    label.label = previous;
                    label.visible = was_visible;
                }
                label.remove_css_class (Granite.CssClass.SUCCESS);
                return Source.REMOVE;
            });
        }

        private async void set_running (bool on) {
            busy = true;
            toggle.sensitive = false;
            toggle.description = on ? "Connecting…" : "Disconnecting…";
            message.visible = false;
            setup_box.visible = false;
            string err = "";
            int status = -1;
            try {
                var proc = new Subprocess.newv ({ "tailscale", on ? "up" : "down" },
                    SubprocessFlags.STDOUT_SILENCE | SubprocessFlags.STDERR_PIPE);
                string? out_text;
                yield proc.communicate_utf8_async (null, cancellable, out out_text, out err);
                status = proc.get_exit_status ();
            } catch (Error e) {
                err = e.message;
            }
            busy = false;
            toggle.sensitive = true;
            if (status != 0) {
                var lower = (err ?? "").down ();
                if (lower.contains ("access denied") || lower.contains ("permission") || lower.contains ("operator")) {
                    message.label = "Turning Tailscale on or off needs a one-time setup. Run this in Terminal:";
                    setup_box.visible = true;
                } else {
                    message.label = (err ?? "").strip () != "" ? err.strip () : "Tailscale didn't respond.";
                }
                message.visible = true;
            }
            yield refresh ();
        }

        private void open_uri (string uri) {
            var launcher = new Gtk.UriLauncher (uri);
            launcher.launch.begin (get_root () as Gtk.Window, null);
            close_request ();
        }

        private static void run_detached (string[] argv) {
            try {
                new Subprocess.newv (argv, SubprocessFlags.STDOUT_SILENCE | SubprocessFlags.STDERR_SILENCE);
            } catch (Error e) {
                warning ("Could not run %s: %s", argv[0], e.message);
            }
        }
    }
}
