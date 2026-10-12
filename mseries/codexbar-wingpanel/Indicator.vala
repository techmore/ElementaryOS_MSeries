/* CodexBar quota indicator for Pantheon's Wingpanel. */
using GLib;
using Gtk;
using Json;
using Wingpanel;

namespace MSeries {
    public class CodexBarIndicator : Wingpanel.Indicator {
        private Gtk.Label panel_label;
        private Gtk.Box panel_display;
        private Gtk.Box menu;
        private Gtk.Label status_label;
        private Gtk.Box providers_box;
        private Gtk.Button refresh_button;
        private Gtk.Image refresh_icon;
        private string executable;
        private bool request_in_flight = false;
        private bool snapshot_busy = false;
        private uint refresh_poll_count = 0;

        public CodexBarIndicator () {
            GLib.Object (code_name: "codexbar");
        }

        construct {
            executable = GLib.Path.build_filename (Environment.get_home_dir (), ".local", "bin", "codexbar-linux");

            var panel_icon = new Gtk.Image.from_icon_name ("mseries-codexbar-openai-symbolic") {
                pixel_size = 18
            };
            panel_icon.add_css_class ("symbolic");
            panel_label = new Gtk.Label ("5H — · 7D —") {
                ellipsize = Pango.EllipsizeMode.END,
                max_width_chars = 18
            };
            panel_label.add_css_class ("caption");
            panel_display = new Gtk.Box (Gtk.Orientation.HORIZONTAL, 5);
            panel_display.append (panel_icon);
            panel_display.append (panel_label);
            panel_display.set_tooltip_text ("OpenAI Codex usage remaining");
            this.visible = true;

            menu = new Gtk.Box (Gtk.Orientation.VERTICAL, 14) {
                margin_top = 14,
                margin_bottom = 14,
                margin_start = 14,
                margin_end = 14,
                width_request = 360
            };

            var title_row = new Gtk.Box (Gtk.Orientation.HORIZONTAL, 10);
            var menu_icon = new Gtk.Image.from_icon_name ("mseries-codexbar-openai-symbolic") {
                pixel_size = 22
            };
            menu_icon.add_css_class ("symbolic");
            title_row.append (menu_icon);

            var title_stack = new Gtk.Box (Gtk.Orientation.VERTICAL, 2) {
                hexpand = true,
                halign = Gtk.Align.FILL
            };
            var title = new Gtk.Label ("CodexBar") {
                xalign = 0,
                halign = Gtk.Align.START
            };
            title.add_css_class ("heading");
            title_stack.append (title);
            var subtitle = new Gtk.Label ("Usage overview") {
                xalign = 0,
                halign = Gtk.Align.START
            };
            subtitle.add_css_class ("dim-label");
            subtitle.add_css_class ("caption");
            title_stack.append (subtitle);
            title_row.append (title_stack);

            refresh_icon = new Gtk.Image.from_icon_name ("view-refresh-symbolic") {
                pixel_size = 16
            };
            refresh_icon.add_css_class ("symbolic");
            refresh_button = new Gtk.Button () {
                child = refresh_icon,
                tooltip_text = "Refresh usage"
            };
            refresh_button.add_css_class ("flat");
            refresh_button.clicked.connect (() => refresh_usage ());
            title_row.append (refresh_button);
            menu.append (title_row);

            status_label = new Gtk.Label ("Loading CodexBar usage…") {
                xalign = 0,
                wrap = true,
                halign = Gtk.Align.FILL
            };
            status_label.add_css_class ("dim-label");
            status_label.add_css_class ("caption");
            menu.append (status_label);

            providers_box = new Gtk.Box (Gtk.Orientation.VERTICAL, 12);
            menu.append (providers_box);

            var separator = new Gtk.Separator (Gtk.Orientation.HORIZONTAL);
            menu.append (separator);

            var action_grid = new Gtk.Grid () {
                column_spacing = 8,
                row_spacing = 8,
                column_homogeneous = true,
                row_homogeneous = true
            };
            action_grid.attach (make_action_button ("Quick View", "view-reveal-symbolic", "--quick-view"), 0, 0, 1, 1);
            action_grid.attach (make_action_button ("Usage", "utilities-system-monitor-symbolic", "--usage"), 1, 0, 1, 1);
            action_grid.attach (make_action_button ("Spending", "view-list-symbolic", "--spending"), 0, 1, 1, 1);
            action_grid.attach (make_action_button ("Settings & Sign In", "preferences-system-symbolic", "--settings"), 1, 1, 1, 1);
            menu.append (action_grid);

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

        private Gtk.Button make_action_button (string label, string icon_name, string action) {
            var button = new Gtk.Button () {
                tooltip_text = label,
                height_request = 58,
                hexpand = true
            };
            var content = new Gtk.Box (Gtk.Orientation.VERTICAL, 5) {
                halign = Gtk.Align.CENTER,
                valign = Gtk.Align.CENTER
            };
            var icon = new Gtk.Image.from_icon_name (icon_name) { pixel_size = 18 };
            icon.add_css_class ("symbolic");
            content.append (icon);
            var text = new Gtk.Label (label) {
                xalign = 0.5f,
                justify = Gtk.Justification.CENTER
            };
            text.add_css_class ("caption");
            content.append (text);
            button.set_child (content);
            button.clicked.connect (() => run_action (action));
            return button;
        }

        private void refresh_usage () {
            run_action ("--refresh");
            status_label.set_text ("Refreshing usage…");
            refresh_icon.set_from_icon_name ("process-working-symbolic");
            refresh_button.set_sensitive (false);
            refresh_poll_count = 0;
            Timeout.add_seconds (2, () => {
                read_snapshot ();
                refresh_poll_count++;
                if ((!snapshot_busy && refresh_poll_count >= 3) || refresh_poll_count >= 30) {
                    return Source.REMOVE;
                }
                return Source.CONTINUE;
            });
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

            string? stdout_text = null;
            string? stderr_text = null;
            int exit_status;
            try {
                Process.spawn_sync (null, { executable, "--snapshot" }, null,
                    SpawnFlags.SEARCH_PATH,
                    null, out stdout_text, out stderr_text, out exit_status);
            } catch (Error e) {
                request_in_flight = false;
                show_unavailable ("Start CodexBar and sign in to see quota.");
                return;
            }
            request_in_flight = false;

            if (exit_status != 0 || stdout_text == null || stdout_text.strip ().length == 0) {
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
                var entries = snapshot.get_array_member ("entries");
                if (entries == null || entries.get_length () == 0) {
                    show_unavailable ("No quota data yet. Open Settings to sign in.");
                    return;
                }

                clear_provider_rows ();
                snapshot_busy = snapshot.get_boolean_member ("busy");
                refresh_icon.set_from_icon_name (snapshot_busy ? "process-working-symbolic" : "view-refresh-symbolic");
                refresh_button.set_sensitive (!snapshot_busy);
                string codex_panel_summary = "";
                string claude_panel_summary = "";
                for (uint i = 0; i < entries.get_length (); i++) {
                    var entry = entries.get_object_element (i);
                    var provider = entry.get_string_member ("provider") ?? "Provider";
                    append_provider_entry (entry);
                    if (provider.down ().contains ("codex")) {
                        codex_panel_summary = compact_codex_summary (entry);
                    } else if (provider.down ().contains ("claude")) {
                        claude_panel_summary = compact_codex_summary (entry);
                    }
                }

                var parts = new string[0];
                if (codex_panel_summary.length > 0) {
                    parts += (claude_panel_summary.length > 0 ? "CX " : "") + codex_panel_summary;
                }
                if (claude_panel_summary.length > 0) {
                    parts += "CL " + claude_panel_summary;
                }
                var panel_text = string.joinv ("   ", parts);
                panel_label.set_text (panel_text.length > 0 ? panel_text : "OpenAI —");
                panel_display.set_tooltip_text (panel_text.length > 0
                    ? "Remaining · " + (claude_panel_summary.length > 0 ? "CX = OpenAI Codex, CL = Claude" : "OpenAI Codex")
                    : "Usage unavailable");

                var update_status = "Updated " + (snapshot.get_string_member ("updated") ?? "recently");
                if (snapshot_busy) {
                    update_status = "Refreshing usage… · " + update_status;
                }
                if (snapshot.get_boolean_member ("stale")) {
                    update_status += " · cached data";
                }
                var snapshot_error = snapshot.get_string_member ("error") ?? "";
                if (snapshot_error.length > 0) {
                    update_status += " · " + snapshot_error;
                }
                status_label.set_text (update_status);
            } catch (Error e) {
                show_unavailable ("Could not read CodexBar usage: " + e.message);
            }
        }

        private void append_provider_entry (Json.Object entry) {
            var provider = entry.get_string_member ("provider") ?? "Provider";
            var title_text = provider.down () == "codex" ? "OpenAI Codex" :
                provider.down () == "claude" ? "Claude" : provider;
            var title = new Gtk.Label (title_text) {
                xalign = 0,
                halign = Gtk.Align.START
            };
            title.add_css_class ("heading");

            var provider_section = new Gtk.Box (Gtk.Orientation.VERTICAL, 8);
            provider_section.append (title);
            providers_box.append (provider_section);

            var previous_provider_box = providers_box;
            providers_box = provider_section;

            var windows = entry.get_array_member ("windows");
            if (windows != null && windows.get_length () > 0) {
                for (uint i = 0; i < windows.get_length (); i++) {
                    append_window (windows.get_object_element (i));
                }
            } else {
                append_metric_row ("Usage", "Unavailable");
            }

            var provider_status = entry.get_string_member ("status") ?? "";
            if (provider_status.length > 0) {
                append_subtle_row ("Status · " + provider_status);
            }
            var provider_error = entry.get_string_member ("error") ?? "";
            if (provider_error.length > 0) {
                append_subtle_row (provider_error);
            }
            providers_box = previous_provider_box;
        }

        private string compact_codex_summary (Json.Object entry) {
            var windows = entry.get_array_member ("windows");
            if (windows == null) {
                return "";
            }

            string session = "";
            string weekly = "";
            for (uint i = 0; i < windows.get_length (); i++) {
                var window = windows.get_object_element (i);
                var label = window.get_string_member ("label") ?? "";
                int minutes = (int) window.get_int_member ("minutes");
                var remaining_node = window.get_member ("remaining");
                if (remaining_node == null || remaining_node.get_node_type () == Json.NodeType.NULL) {
                    continue;
                }
                var remaining = remaining_node.get_double ();
                var value = "%0.0f%%".printf (remaining);
                var short_label = short_window_label (label, minutes);
                if (minutes > 0 && minutes <= 360 || label.down ().contains ("hour")) {
                    session = short_label + " " + value;
                } else if (minutes >= 1440 || label.down ().contains ("week") || label.down ().contains ("day")) {
                    weekly = short_label + " " + value;
                }
            }
            if (session.length > 0 && weekly.length > 0) {
                return session + " · " + weekly;
            }
            return session.length > 0 ? session : weekly;
        }

        private string short_window_label (string label, int minutes) {
            var normalized = label.down ();
            if (normalized.contains ("hour") || minutes > 0 && minutes <= 360) {
                var hours = minutes > 0 ? (minutes + 30) / 60 : 5;
                return "%dH".printf (hours);
            }
            if (normalized.contains ("week")) {
                return "7D";
            }
            if (normalized.contains ("month")) {
                return "30D";
            }
            if (normalized.contains ("day") || minutes >= 1440) {
                var days = minutes > 0 ? (minutes + 720) / 1440 : 7;
                return "%dD".printf (days);
            }
            return label;
        }

        private void append_window (Json.Object window) {
            var label = window.get_string_member ("label") ?? "Quota";
            var reset = window.get_string_member ("resetText") ?? "";
            var pace = window.get_string_member ("pace") ?? "";
            var remaining_node = window.get_member ("remaining");

            var quota_card = new Gtk.Box (Gtk.Orientation.VERTICAL, 8) {
                margin_top = 2,
                margin_bottom = 2,
                margin_start = 10,
                margin_end = 10
            };
            quota_card.add_css_class ("card");

            var heading = new Gtk.Box (Gtk.Orientation.HORIZONTAL, 8);
            var name_label = new Gtk.Label (label) {
                xalign = 0,
                hexpand = true,
                halign = Gtk.Align.START
            };
            name_label.add_css_class ("dim-label");
            heading.append (name_label);

            if (remaining_node == null || remaining_node.get_node_type () == Json.NodeType.NULL) {
                var unknown = new Gtk.Label ("Unavailable") { halign = Gtk.Align.END };
                heading.append (unknown);
                quota_card.append (heading);
                providers_box.append (quota_card);
                return;
            }

            var remaining = remaining_node.get_double ();
            var percent_label = new Gtk.Label ("%0.0f%% remaining".printf (remaining)) {
                halign = Gtk.Align.END
            };
            percent_label.add_css_class ("numeric");
            percent_label.add_css_class ("heading");
            heading.append (percent_label);
            quota_card.append (heading);

            var progress = new Gtk.ProgressBar () {
                show_text = false,
                height_request = 7,
                tooltip_text = "%0.0f%% remaining".printf (remaining)
            };
            progress.set_fraction (GLib.Math.fmin (1.0, GLib.Math.fmax (0.0, remaining / 100.0)));
            if (window.get_boolean_member ("warning")) {
                progress.add_css_class ("warning");
            }
            quota_card.append (progress);

            if (reset.length > 0) {
                append_quota_detail (quota_card, "appointment-soon-symbolic", reset, true);
            }
            var estimate = pace_estimate (pace);
            if (estimate.length > 0) {
                append_quota_detail (quota_card, "document-properties-symbolic", estimate, false);
            } else if (pace.length > 0) {
                append_quota_detail (quota_card, "document-properties-symbolic", pace, true);
            }
            providers_box.append (quota_card);
        }

        private void append_quota_detail (Gtk.Box card, string icon_name, string text, bool subdued) {
            var row = new Gtk.Box (Gtk.Orientation.HORIZONTAL, 8);
            var icon = new Gtk.Image.from_icon_name (icon_name) { pixel_size = 14 };
            icon.add_css_class ("dim-label");
            icon.add_css_class ("symbolic");
            row.append (icon);
            var label = new Gtk.Label (text) {
                xalign = 0,
                hexpand = true,
                wrap = true,
                halign = Gtk.Align.START
            };
            if (subdued) {
                label.add_css_class ("dim-label");
                label.add_css_class ("caption");
            } else {
                label.add_css_class ("heading");
            }
            row.append (label);
            card.append (row);
        }

        private string pace_estimate (string pace) {
            foreach (string part in pace.split ("|")) {
                var detail = part.strip ();
                var runout = "Runs out in ";
                var runout_index = detail.index_of (runout);
                if (runout_index >= 0) {
                    var remaining_time = detail.substring (runout_index + runout.length).strip ();
                    if (remaining_time.length > 0) {
                        return "About " + remaining_time + " left at this pace";
                    }
                }
                if (detail.down ().contains ("lasts until reset")) {
                    return "At this pace, lasts until reset";
                }
            }
            return "";
        }

        private void append_metric_row (string name, string value) {
            var row = new Gtk.Box (Gtk.Orientation.HORIZONTAL, 8);
            var name_label = new Gtk.Label (name) {
                xalign = 0,
                hexpand = true,
                halign = Gtk.Align.START
            };
            var value_label = new Gtk.Label (value) {
                xalign = 1,
                halign = Gtk.Align.END
            };
            value_label.add_css_class ("numeric");
            row.append (name_label);
            row.append (value_label);
            providers_box.append (row);
        }

        private void append_subtle_row (string text) {
            var label = new Gtk.Label (text) {
                xalign = 0,
                wrap = true,
                halign = Gtk.Align.FILL
            };
            label.add_css_class ("dim-label");
            providers_box.append (label);
        }

        private void show_unavailable (string message) {
            snapshot_busy = false;
            panel_label.set_text ("5H — · 7D —");
            panel_display.set_tooltip_text (message);
            status_label.set_text (message);
            refresh_icon.set_from_icon_name ("view-refresh-symbolic");
            refresh_button.set_sensitive (true);
            clear_provider_rows ();
        }

        public override Gtk.Widget get_display_widget () {
            return panel_display;
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
