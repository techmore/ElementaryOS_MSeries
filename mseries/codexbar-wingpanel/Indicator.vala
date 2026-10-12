/* CodexBar quota indicator for Pantheon's Wingpanel. */
using GLib;
using Gtk;
using Json;
using Wingpanel;

namespace MSeries {
    public class CodexBarIndicator : Wingpanel.Indicator {
        private Gtk.Label panel_label;
        private Gtk.Box menu;
        private Gtk.Label status_label;
        private Gtk.Box providers_box;
        private string executable;
        private bool request_in_flight = false;

        public CodexBarIndicator () {
            GLib.Object (code_name: "codexbar");
        }

        construct {
            executable = GLib.Path.build_filename (Environment.get_home_dir (), ".local", "bin", "codexbar-linux");

            panel_label = new Gtk.Label ("CodexBar") {
                ellipsize = Pango.EllipsizeMode.END,
                max_width_chars = 15
            };
            panel_label.add_css_class ("caption");
            this.visible = true;

            menu = new Gtk.Box (Gtk.Orientation.VERTICAL, 8) {
                margin_top = 12,
                margin_bottom = 12,
                margin_start = 12,
                margin_end = 12,
                width_request = 280
            };

            var title = new Gtk.Label ("AI quota remaining") {
                xalign = 0,
                halign = Gtk.Align.START
            };
            title.add_css_class ("heading");
            menu.append (title);

            status_label = new Gtk.Label ("Loading CodexBar usage…") {
                xalign = 0,
                wrap = true,
                halign = Gtk.Align.FILL
            };
            menu.append (status_label);

            providers_box = new Gtk.Box (Gtk.Orientation.VERTICAL, 6);
            menu.append (providers_box);

            var refresh_button = make_button ("Refresh usage");
            refresh_button.clicked.connect (() => {
                run_action ("--refresh");
                Timeout.add_seconds (3, () => { read_snapshot (); return Source.REMOVE; });
            });
            menu.append (refresh_button);

            var quick_view_button = make_button ("Open CodexBar");
            quick_view_button.clicked.connect (() => run_action ("--quick-view"));
            menu.append (quick_view_button);

            var settings_button = make_button ("Settings and sign in");
            settings_button.clicked.connect (() => run_action ("--settings"));
            menu.append (settings_button);

            // CodexBar owns provider authentication, polling and cached usage.
            // This indicator only reads its documented, same-user local snapshot.
            try {
                Pid child_pid;
                Process.spawn_async (null, { executable, "--background" }, null,
                    SpawnFlags.SEARCH_PATH | SpawnFlags.STDOUT_TO_DEV_NULL | SpawnFlags.STDERR_TO_DEV_NULL,
                    null, out child_pid);
            } catch (Error e) {
                status_label.set_text ("Could not start CodexBar: " + e.message);
            }

            Timeout.add_seconds (5, () => { read_snapshot (); return Source.REMOVE; });
            Timeout.add_seconds (60, () => { read_snapshot (); return Source.CONTINUE; });
        }

        private Gtk.Button make_button (string label) {
            var button = new Gtk.Button.with_label (label);
            button.add_css_class ("flat");
            return button;
        }

        private void run_action (string action) {
            try {
                Pid child_pid;
                Process.spawn_async (null, { executable, action }, null,
                    SpawnFlags.SEARCH_PATH | SpawnFlags.STDOUT_TO_DEV_NULL | SpawnFlags.STDERR_TO_DEV_NULL,
                    null, out child_pid);
            } catch (Error e) {
                status_label.set_text ("Could not open CodexBar: " + e.message);
            }
        }

        private void clear_provider_rows () {
            while (providers_box.get_first_child () != null) {
                providers_box.remove (providers_box.get_first_child ());
            }
        }

        private void read_snapshot () {
            if (request_in_flight) {
                return;
            }
            request_in_flight = true;

            string stdout_text;
            string stderr_text;
            int exit_status;
            try {
                Process.spawn_sync (null, { executable, "--snapshot" }, null,
                    SpawnFlags.SEARCH_PATH | SpawnFlags.STDERR_TO_DEV_NULL,
                    null, out stdout_text, out stderr_text, out exit_status);
            } catch (Error e) {
                request_in_flight = false;
                show_unavailable ("Start CodexBar and sign in to see quota.");
                return;
            }
            request_in_flight = false;

            if (exit_status != 0 || stdout_text.strip ().length == 0) {
                show_unavailable ("Start CodexBar and sign in to see quota.");
                return;
            }

            try {
                var parser = new Json.Parser ();
                parser.load_from_data (stdout_text, -1);
                var root = parser.get_root ();
                if (root == null || root.get_node_type () != Json.NodeType.OBJECT) {
                    show_unavailable ("CodexBar returned an unsupported snapshot.");
                    return;
                }
                var snapshot = root.get_object ();
                var entries = snapshot.get_array_member ("barEntries");
                if (entries == null || entries.get_length () == 0) {
                    show_unavailable ("No quota data yet. Open Settings to sign in.");
                    return;
                }

                clear_provider_rows ();
                string first_text = "";
                for (uint i = 0; i < entries.get_length (); i++) {
                    var entry = entries.get_object_element (i);
                    var provider = entry.get_string_member ("provider") ?? "Provider";
                    var text = entry.get_string_member ("text") ?? "Quota unavailable";
                    if (i == 0) {
                        first_text = text;
                    }
                    var row = new Gtk.Box (Gtk.Orientation.HORIZONTAL, 8);
                    var provider_label = new Gtk.Label (provider) {
                        xalign = 0,
                        hexpand = true,
                        halign = Gtk.Align.START
                    };
                    provider_label.add_css_class ("heading");
                    var quota_label = new Gtk.Label (text) {
                        xalign = 1,
                        halign = Gtk.Align.END
                    };
                    quota_label.add_css_class ("numeric");
                    row.append (provider_label);
                    row.append (quota_label);
                    providers_box.append (row);
                }
                panel_label.set_text (compact_panel_text (first_text));
                status_label.set_text ("Remaining quota · updated " +
                    (snapshot.get_string_member ("updatedAt") ?? "recently"));
            } catch (Error e) {
                show_unavailable ("Could not read CodexBar usage: " + e.message);
            }
        }

        private string compact_panel_text (string text) {
            // barEntries.text follows CodexBar's remaining-quota preference.
            // Keep a short provider-neutral meter in Wingpanel.
            var trimmed = text.strip ();
            if (trimmed.length > 12) {
                return "AI " + trimmed.substring (0, 12);
            }
            return "AI " + trimmed;
        }

        private void show_unavailable (string message) {
            panel_label.set_text ("AI —");
            status_label.set_text (message);
            clear_provider_rows ();
        }

        public override Gtk.Widget get_display_widget () {
            return panel_label;
        }

        public override Gtk.Widget? get_widget () {
            read_snapshot ();
            return menu;
        }

        public override void opened () {
            read_snapshot ();
        }

        public override void closed () {
        }
    }
}

public Wingpanel.Indicator? get_indicator (Module module, Wingpanel.ServerType server_type) {
    if (server_type != Wingpanel.ServerType.SESSION) {
        return null;
    }
    return new MSeries.CodexBarIndicator ();
}
