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
        private Gtk.Stack refresh_display;
        private Gtk.Spinner refresh_spinner;
        private uint refresh_poll_source = 0;
        private string executable;
        private bool request_in_flight = false;
        private bool snapshot_busy = false;
        private bool snapshot_stale = false;
        private uint refresh_poll_count = 0;
        private bool refresh_after_snapshot = false;
        private RefreshPolicy refresh_policy = new RefreshPolicy ();

        public CodexBarIndicator () {
            GLib.Object (code_name: "codexbar");
        }

        construct {
            executable = GLib.Path.build_filename (Environment.get_home_dir (), ".local", "bin", "codexbar-linux");

            var panel_icon = new Gtk.Image.from_icon_name ("mseries-codexbar-openai-symbolic") {
                pixel_size = 12
            };
            panel_icon.add_css_class ("symbolic");
            panel_label = new Gtk.Label ("5H — · 7D —") {
                ellipsize = Pango.EllipsizeMode.END,
                max_width_chars = 52
            };
            panel_label.add_css_class ("caption");
            panel_display = new Gtk.Box (Gtk.Orientation.HORIZONTAL, 5);
            panel_display.append (panel_icon);
            panel_display.append (panel_label);
            panel_display.set_tooltip_text ("OpenAI Codex usage remaining · Middle-click to refresh");
            var refresh_gesture = new Gtk.GestureClick () { button = 2 };
            refresh_gesture.released.connect (() => refresh_usage ());
            panel_display.add_controller (refresh_gesture);
            this.visible = true;

            menu = new Gtk.Box (Gtk.Orientation.VERTICAL, 6) {
                margin_top = 6,
                margin_bottom = 6,
                margin_start = 6,
                margin_end = 6,
                width_request = 320
            };

            menu.add_css_class ("mseries-codexbar-compact");
            var compact_style = new Gtk.CssProvider ();
            compact_style.load_from_string (
                ".mseries-codexbar-compact label { font-size: 7.5pt; } " +
                ".mseries-codexbar-compact .h3 { font-size: 8.5pt; } " +
                ".mseries-codexbar-compact button { padding: 3px 5px; } " +
                ".mseries-codexbar-compact progressbar trough, " +
                ".mseries-codexbar-compact progressbar progress { min-height: 3px; }");
            Gtk.StyleContext.add_provider_for_display (menu.get_display (), compact_style,
                Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION);

            var title_row = new Gtk.Box (Gtk.Orientation.HORIZONTAL, 6);
            var menu_icon = new Gtk.Image.from_icon_name ("mseries-codexbar-openai-symbolic") {
                pixel_size = 14
            };
            menu_icon.add_css_class ("symbolic");
            title_row.append (menu_icon);

            var title_stack = new Gtk.Box (Gtk.Orientation.VERTICAL, 3) {
                hexpand = true
            };
            var title = new Granite.HeaderLabel ("CodexBar") {
                size = Granite.HeaderLabel.Size.H3
            };
            title_stack.append (title);
            status_label = new Gtk.Label ("Loading usage…") {
                xalign = 0,
                wrap = true,
                max_width_chars = 34
            };
            status_label.add_css_class ("dim-label");
            status_label.add_css_class ("caption");
            title_stack.append (status_label);
            title_row.append (title_stack);

            refresh_display = new Gtk.Stack ();
            refresh_display.add_named (new Gtk.Image.from_icon_name ("view-refresh-symbolic"), "idle");
            refresh_spinner = new Gtk.Spinner ();
            refresh_display.add_named (refresh_spinner, "busy");
            refresh_button = new Gtk.Button () {
                child = refresh_display,
                tooltip_text = "Refresh usage",
                valign = Gtk.Align.CENTER
            };
            refresh_button.add_css_class ("flat");
            refresh_button.clicked.connect (() => refresh_usage ());
            title_row.append (refresh_button);
            menu.append (title_row);

            providers_box = new Gtk.Box (Gtk.Orientation.VERTICAL, 8);
            var scroll = new Gtk.ScrolledWindow () {
                child = providers_box,
                hscrollbar_policy = Gtk.PolicyType.NEVER,
                vscrollbar_policy = Gtk.PolicyType.AUTOMATIC,
                propagate_natural_height = true,
                min_content_height = 180,
                max_content_height = 252
            };
            menu.append (scroll);
            menu.append (new Gtk.Separator (Gtk.Orientation.HORIZONTAL));

            // Labeled, borderless action rows live inside Wingpanel's popover.
            var actions = new Gtk.Box (Gtk.Orientation.VERTICAL, 0);
            actions.append (make_action_button ("Quick View…", "view-reveal-symbolic", "--quick-view"));
            actions.append (make_action_button ("Usage Details…", "view-list-symbolic", "--usage"));
            actions.append (make_action_button ("Spending…", "accessories-calculator-symbolic", "--spending"));
            
            actions.append (make_action_button ("Settings & Sign In…", "preferences-system-symbolic", "--settings"));
            menu.append (actions);

            // CodexBar owns provider authentication, polling and cached usage.
            // The indicator reads snapshots and requests refreshes through documented local IPC.
            try {
                Pid child_pid;
                Process.spawn_async (null, { executable, "--background" }, null,
                    SpawnFlags.SEARCH_PATH | SpawnFlags.STDOUT_TO_DEV_NULL | SpawnFlags.STDERR_TO_DEV_NULL,
                    null, out child_pid);
            } catch (Error e) {
                status_label.set_text ("Could not start CodexBar: " + e.message);
            }

            Timeout.add_seconds (5, () => { read_snapshot.begin (); return Source.CONTINUE; });
        }

        private Gtk.Button make_action_button (string label, string icon_name, string action) {
            var content = new Gtk.Box (Gtk.Orientation.HORIZONTAL, 7);
            content.append (new Gtk.Image.from_icon_name (icon_name) { pixel_size = 10 });
            content.append (new Gtk.Label (label) { xalign = 0, hexpand = true });
            var button = new Gtk.Button () { child = content };
            button.add_css_class ("flat");
            button.clicked.connect (() => {
                var popover = button.get_ancestor (typeof (Gtk.Popover)) as Gtk.Popover;
                if (popover != null) {
                    popover.popdown ();
                }
                run_action (action);
            });
            return button;
        }

        private void set_refreshing (bool busy) {
            refresh_display.set_visible_child_name (busy ? "busy" : "idle");
            refresh_spinner.set_spinning (busy);
            refresh_button.set_sensitive (!busy);
        }

        private void refresh_usage () {
            if (snapshot_busy || !run_action ("--refresh")) {
                return;
            }
            refresh_policy.requested (GLib.get_monotonic_time ());
            status_label.set_text ("Refreshing usage…");
            set_refreshing (true);
            if (refresh_poll_source != 0) {
                Source.remove (refresh_poll_source);
            }
            refresh_poll_count = 0;
            refresh_poll_source = Timeout.add_seconds (2, () => {
                read_snapshot.begin ();
                refresh_poll_count++;
                if ((!snapshot_busy && refresh_poll_count >= 3) || refresh_poll_count >= 30) {
                    refresh_poll_source = 0;
                    set_refreshing (false);
                    return Source.REMOVE;
                }
                return Source.CONTINUE;
            });
        }

        private bool run_action (string action) {
            try {
                Pid child_pid;
                Process.spawn_async (null, { executable, action }, null,
                    SpawnFlags.SEARCH_PATH | SpawnFlags.STDOUT_TO_DEV_NULL | SpawnFlags.STDERR_TO_DEV_NULL,
                    null, out child_pid);
                return true;
            } catch (Error e) {
                status_label.set_text ("Could not open CodexBar: " + e.message);
                return false;
            }
        }

        private void clear_provider_rows () {
            while (providers_box.get_first_child () != null) {
                providers_box.remove (providers_box.get_first_child ());
            }
        }

        private async void read_snapshot (bool refresh_if_old = false) {
            refresh_after_snapshot = refresh_after_snapshot || refresh_if_old;
            if (request_in_flight) {
                return;
            }
            request_in_flight = true;

            try {
                var process = new GLib.Subprocess (SubprocessFlags.STDOUT_PIPE | SubprocessFlags.STDERR_PIPE,
                    executable, "--snapshot");
                string stdout_text;
                string stderr_text;
                yield process.communicate_utf8_async (null, null, out stdout_text, out stderr_text);
                if (!process.get_successful () || stdout_text.strip ().length == 0) {
                    show_unavailable ("Start CodexBar and sign in to see quota.");
                    return;
                }

                var parser = new Json.Parser ();
                parser.load_from_data (stdout_text, -1);
                var root = parser.get_root ();
                if (root == null || root.get_node_type () != Json.NodeType.OBJECT) {
                    show_unavailable ("CodexBar returned an unsupported snapshot.");
                    return;
                }
                var snapshot = root.get_object ();
                update_snapshot (snapshot);
                if (refresh_after_snapshot && should_refresh_on_open (snapshot)) {
                    refresh_usage ();
                }
            } catch (Error e) {
                show_unavailable ("Could not read CodexBar usage: " + e.message);
            } finally {
                request_in_flight = false;
                refresh_after_snapshot = false;
            }
        }

        private bool should_refresh_on_open (Json.Object snapshot) {
            int64 oldest_update_unix = 0;
            var entries = snapshot.get_array_member ("entries");
            if (entries != null) {
                for (uint i = 0; i < entries.get_length (); i++) {
                    var entry = entries.get_object_element (i);
                    var updated = entry.get_string_member ("updatedAt") ?? "";
                    var timestamp = new DateTime.from_iso8601 (updated, null);
                    if (timestamp == null) {
                        oldest_update_unix = 0;
                        break;
                    }
                    if (oldest_update_unix == 0 || timestamp.to_unix () < oldest_update_unix) {
                        oldest_update_unix = timestamp.to_unix ();
                    }
                }
            }
            return refresh_policy.should_refresh_on_open (snapshot.get_boolean_member ("busy"),
                oldest_update_unix, new DateTime.now_utc ().to_unix (), GLib.get_monotonic_time ());
        }

        private void update_snapshot (Json.Object snapshot) {
            snapshot_stale = snapshot.get_boolean_member ("stale");
            var entries = snapshot.get_array_member ("entries");
            if (entries == null || entries.get_length () == 0) {
                if (snapshot.get_boolean_member ("busy")) {
                    snapshot_busy = true;
                    set_refreshing (true);
                    status_label.set_text ("Fetching usage…");
                    clear_provider_rows ();
                    append_subtle_row ("Your limits will appear when the update completes.");
                } else {
                    show_unavailable ("No quota data yet. Open Settings to sign in.");
                }
                return;
            }

            clear_provider_rows ();
            snapshot_busy = snapshot.get_boolean_member ("busy");
            set_refreshing (snapshot_busy);
            string codex_panel_summary = "";
            string claude_panel_summary = "";
            var eta_tooltips = new string[0];
            for (uint i = 0; i < entries.get_length (); i++) {
                var entry = entries.get_object_element (i);
                var provider = entry.get_string_member ("provider") ?? "Provider";
                append_provider_entry (entry);
                var now_unix = new DateTime.now_utc ().to_unix ();
                var eta = QuotaEta.for_entry (entry, QuotaEta.entry_stale (entry, snapshot_stale, now_unix), now_unix);
                eta_tooltips += provider + " · " + eta.detail +
                    (eta.window_label.length > 0 ? " (" + eta.window_label + ")" : "");
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
                ? "Quota remaining · ETA at the current pace\n" + string.joinv ("\n", eta_tooltips) + "\nMiddle-click to refresh"
                : "Usage unavailable");

            var update_status = "Remaining · Updated " + (snapshot.get_string_member ("updated") ?? "recently");
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
        }

        private void append_provider_entry (Json.Object entry) {
            var provider = entry.get_string_member ("provider") ?? "Provider";
            var title_text = provider.down () == "codex" ? "OpenAI Codex" :
                provider.down () == "claude" ? "Claude" : provider;
            var title = new Gtk.Label (title_text) { xalign = 0 };
            title.add_css_class ("heading");

            var provider_section = new Gtk.Box (Gtk.Orientation.VERTICAL, 4);
            provider_section.append (title);
            providers_box.append (provider_section);

            var previous_provider_box = providers_box;
            var limits = new Gtk.Box (Gtk.Orientation.VERTICAL, 3);
            provider_section.append (limits);
            providers_box = limits;

            var windows = entry.get_array_member ("windows");
            var now_unix = new DateTime.now_utc ().to_unix ();
            var eta_stale = QuotaEta.entry_stale (entry, snapshot_stale, now_unix);
            if (windows != null && windows.get_length () > 0) {
                for (uint i = 0; i < windows.get_length (); i++) {
                    append_window (windows.get_object_element (i), eta_stale);
                }
            } else {
                append_metric_row ("Usage", "Unavailable");
            }

            providers_box = provider_section;
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
            if (windows == null || windows.get_length () == 0) return "";
            string remaining = "—";
            for (uint i = 0; i < windows.get_length (); i++) {
                var window = windows.get_object_element (i);
                var node = window.get_member ("remaining");
                if (node == null || node.get_node_type () == Json.NodeType.NULL) continue;
                remaining = "%0.0f%%".printf (node.get_double ());
                // The first measured window is the provider's session/general quota.
                break;
            }
            var now_unix = new DateTime.now_utc ().to_unix ();
            var eta = QuotaEta.for_entry (entry, QuotaEta.entry_stale (entry, snapshot_stale, now_unix), now_unix);
            var limit = eta.state == EtaState.DEPLETING || eta.state == EtaState.EXHAUSTED
                ? short_window_label (eta.window_label, eta.window_minutes) + " " : "";
            return remaining + " · " + limit + eta.compact;
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

        private void append_window (Json.Object window, bool eta_stale) {
            var label = window.get_string_member ("label") ?? "Quota";
            var reset = window.get_string_member ("resetText") ?? "";
            var pace = window.get_string_member ("pace") ?? "";
            var remaining_node = window.get_member ("remaining");

            var remaining = remaining_node == null || remaining_node.get_node_type () == Json.NodeType.NULL
                ? -1.0 : GLib.Math.fmin (100.0, GLib.Math.fmax (0.0, remaining_node.get_double ()));
            var warning = window.get_boolean_member ("warning");
            var detail = remaining < 0 ? "Usage not reported yet" : "%0.0f%% remaining".printf (remaining);
            if (warning) {
                detail += remaining <= 0 ? " · Quota exhausted" : " · Low remaining quota";
            }
            if (reset.length > 0) detail += " · " + reset;
            if (pace.length > 0) detail += " · " + pace;

            var row = new Gtk.Box (Gtk.Orientation.HORIZONTAL, 8) { tooltip_text = label + " · " + detail };
            var short_label = short_window_label (label, (int) window.get_int_member ("minutes"));
            var name = new Gtk.Label (short_label) {
                xalign = 0, width_request = 52, ellipsize = Pango.EllipsizeMode.END,
                tooltip_text = label
            };
            row.append (name);
            var progress = new Gtk.ProgressBar () {
                show_text = false, hexpand = true, valign = Gtk.Align.CENTER,
                width_request = 64, sensitive = remaining >= 0
            };
            progress.set_fraction (remaining < 0 ? 0 : remaining / 100.0);
            if (warning) progress.add_css_class ("warning");
            row.append (progress);
            var percent = new Gtk.Label (remaining < 0 ? "—" : "%0.0f%%".printf (remaining)) {
                xalign = 1, width_request = 38, tooltip_text = detail
            };
            percent.add_css_class ("numeric");
            row.append (percent);
            var reset_label = new Gtk.Label (reset.length > 0 ? reset : "Reset unknown") {
                xalign = 0, width_request = 108, max_width_chars = 18,
                ellipsize = Pango.EllipsizeMode.END, tooltip_text = detail
            };
            reset_label.add_css_class ("dim-label");
            row.append (reset_label);
            providers_box.append (row);
            var eta = QuotaEta.from_window (window, eta_stale, new DateTime.now_utc ().to_unix ());
            var eta_label = new Gtk.Label (eta.detail) {
                xalign = 0, wrap = true, margin_start = 60,
                tooltip_text = "Quota estimate from CodexBar's current usage pace. The menu bar shows the earliest available limit; reset times are separate."
            };
            eta_label.add_css_class ("caption");
            eta_label.add_css_class (eta.state == EtaState.EXHAUSTED || eta.state == EtaState.DEPLETING ? "warning" : "dim-label");
            providers_box.append (eta_label);
        }

        private void append_metric_row (string name, string value) {
            var row = new Gtk.Box (Gtk.Orientation.HORIZONTAL, 7) {
                margin_top = 6, margin_bottom = 6,
                margin_start = 6, margin_end = 6
            };
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
            status_label.set_text ("Usage unavailable");
            set_refreshing (false);
            clear_provider_rows ();
            var empty = new Gtk.Box (Gtk.Orientation.VERTICAL, 6) {
                margin_top = 6,
                margin_bottom = 6
            };
            var explanation = new Gtk.Label (message) { xalign = 0, wrap = true };
            explanation.add_css_class ("dim-label");
            empty.append (explanation);
            var sign_in = new Gtk.Button.with_label ("Settings & Sign In…") {
                halign = Gtk.Align.START
            };
            sign_in.clicked.connect (() => {
                var popover = sign_in.get_ancestor (typeof (Gtk.Popover)) as Gtk.Popover;
                if (popover != null) {
                    popover.popdown ();
                }
                run_action ("--settings");
            });
            empty.append (sign_in);
            providers_box.append (empty);
        }

        public override Gtk.Widget get_display_widget () {
            return panel_display;
        }

        public override Gtk.Widget? get_widget () {
            read_snapshot.begin ();
            return menu;
        }

        public override void opened () {
            read_snapshot.begin (true);
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
