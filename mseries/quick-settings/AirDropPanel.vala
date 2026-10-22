/* AirDrop section for the Quick Settings popover (top-right menu).
 *
 * Collapsed to one row (icon, "AirDrop", a one-line status and a direct receive switch). Who may send
 * and incoming files stay out of sight until the details button is clicked. All state lives in the
 * vendored `omdrop` command (mseries/omdrop); this widget only runs `omdrop status --json` and
 * `omdrop on|off|visibility|dir`, and only while the popover is open. OMDROP_CLI overrides the
 * command path (tests point it at a stub backend). */
using Gtk;

namespace MSeries {
    public class AirDropPanel : Gtk.Box {
        private const string[] WINDOW_ARGS = { "once", "10m", "1h", "forever" };

        private string cli;
        private Gtk.Revealer revealer;
        private Gtk.Image chevron;
        private Gtk.Label caption;
        public Gtk.Switch receive_switch { get; private set; }
        private Gtk.DropDown window_pick;
        private Gtk.DropDown audience_pick;
        private Gtk.Label problem;
        private Gtk.Button open_folder;
        private Gtk.Label name_label;
        private bool updating = false;
        private bool busy = false;
        private bool polling = false;
        private uint poll_source = 0;
        private string folder = "";
        private bool receiving = false;
        private bool ready = true;

        construct {
            var override_cli = GLib.Environment.get_variable ("OMDROP_CLI");
            cli = (override_cli != null && override_cli != "") ? override_cli : GLib.Path.build_filename (GLib.Environment.get_home_dir (), ".local", "bin", "omdrop");
            orientation = Gtk.Orientation.VERTICAL;
            add_css_class ("mseries-airdrop");

            var row = new Gtk.Box (Gtk.Orientation.HORIZONTAL, 6);
            row.append (new Gtk.Image.from_icon_name ("mseries-airdrop-symbolic") { pixel_size = 16 });
            var text = new Gtk.Box (Gtk.Orientation.VERTICAL, 0) { hexpand = true };
            text.append (new Gtk.Label ("AirDrop") { halign = Gtk.Align.START, xalign = 0 });
            caption = new Gtk.Label ("Off") { halign = Gtk.Align.START, xalign = 0, ellipsize = Pango.EllipsizeMode.END };
            caption.add_css_class (Granite.CssClass.DIM);
            caption.add_css_class ("caption");
            text.append (caption);
            row.append (text);
            chevron = new Gtk.Image.from_icon_name ("pan-end-symbolic") { pixel_size = 16 };
            row.append (chevron);
            var details_button = new Gtk.Button () { child = row, margin_start = 6, margin_end = 0, hexpand = true, tooltip_text = "Show AirDrop controls" };
            details_button.add_css_class ("flat");
            details_button.update_property (Gtk.AccessibleProperty.LABEL, "AirDrop details", -1);

            receive_switch = new Gtk.Switch () { valign = Gtk.Align.CENTER, margin_start = 6, margin_end = 6, sensitive = false, tooltip_text = "Receive files with AirDrop" };
            receive_switch.update_property (Gtk.AccessibleProperty.LABEL, "Receive Files", -1);
            receive_switch.notify["active"].connect (on_receive_toggled);

            var header = new Gtk.Box (Gtk.Orientation.HORIZONTAL, 0);
            header.append (details_button);
            header.append (receive_switch);
            append (header);

            var box = new Gtk.Box (Gtk.Orientation.VERTICAL, 0);
            problem = new Gtk.Label ("") { wrap = true, xalign = 0, margin_start = 12, margin_end = 12, margin_bottom = 6, visible = false };
            problem.add_css_class (Granite.CssClass.DIM);
            problem.add_css_class ("caption");
            box.append (problem);

            window_pick = new Gtk.DropDown.from_strings ({ "One File", "10 Minutes", "1 Hour", "Until Turned Off" }) { valign = Gtk.Align.CENTER };
            window_pick.selected = 1;
            box.append (labelled ("Stay Visible For", window_pick));

            audience_pick = new Gtk.DropDown.from_strings ({ "Everyone", "Contacts Only" }) { valign = Gtk.Align.CENTER };
            audience_pick.notify["selected"].connect (on_audience_changed);
            box.append (labelled ("Receive From", audience_pick));

            name_label = new Gtk.Label ("") { halign = Gtk.Align.START, xalign = 0, ellipsize = Pango.EllipsizeMode.END, margin_start = 12, margin_end = 12, margin_top = 3 };
            name_label.add_css_class (Granite.CssClass.DIM);
            name_label.add_css_class ("caption");
            box.append (name_label);

            open_folder = new Gtk.Button () { margin_start = 6, margin_end = 6 };
            var open_row = new Gtk.Box (Gtk.Orientation.HORIZONTAL, 6);
            open_row.append (new Gtk.Image.from_icon_name ("folder-symbolic") { pixel_size = 16 });
            open_row.append (new Gtk.Label ("Open Received Files") { halign = Gtk.Align.START, xalign = 0 });
            open_folder.child = open_row;
            open_folder.add_css_class ("flat");
            open_folder.clicked.connect (() => {
                if (folder != "") {
                    try { GLib.AppInfo.launch_default_for_uri (GLib.File.new_for_path (folder).get_uri (), null); } catch (GLib.Error e) { warning ("%s", e.message); }
                }
            });
            box.append (open_folder);

            revealer = new Gtk.Revealer () { child = box, reveal_child = false, transition_type = Gtk.RevealerTransitionType.SLIDE_DOWN };
            append (revealer);

            details_button.clicked.connect (() => {
                revealer.reveal_child = !revealer.reveal_child;
                chevron.icon_name = revealer.reveal_child ? "pan-down-symbolic" : "pan-end-symbolic";
                details_button.tooltip_text = revealer.reveal_child ? "Hide AirDrop controls" : "Show AirDrop controls";
            });

            // Nothing runs while the popover is closed; the section re-collapses so received files stay out of sight.
            map.connect (() => {
                revealer.reveal_child = false;
                chevron.icon_name = "pan-end-symbolic";
                refresh.begin ();
                poll_source = GLib.Timeout.add_seconds (3, () => { refresh.begin (); return GLib.Source.CONTINUE; });
            });
            unmap.connect (() => {
                if (poll_source != 0) { GLib.Source.remove (poll_source); poll_source = 0; }
            });
        }

        /* Test hooks: what the collapsed row says, whether the controls are open, and the problem line. */
        public string status_text { get { return caption.label; } }
        public string problem_text { get { return problem.visible ? problem.label : ""; } }
        public bool expanded { get { return revealer.reveal_child; } }
        public void set_expanded (bool open) {
            revealer.reveal_child = open;
            chevron.icon_name = open ? "pan-down-symbolic" : "pan-end-symbolic";
        }

        private Gtk.Widget labelled (string text, Gtk.Widget control) {
            var r = new Gtk.Box (Gtk.Orientation.HORIZONTAL, 6) { margin_start = 12, margin_end = 12, margin_top = 3, margin_bottom = 3 };
            r.append (new Gtk.Label (text) { halign = Gtk.Align.START, hexpand = true, xalign = 0 });
            r.append (control);
            return r;
        }

        /* Runs the command; returns (exit status, stdout, stderr). */
        private async bool run (string[] args, out string out_text, out string err_text) {
            out_text = ""; err_text = "";
            try {
                string[] argv = { cli };
                foreach (var a in args) argv += a;
                var p = new GLib.Subprocess.newv (argv, GLib.SubprocessFlags.STDOUT_PIPE | GLib.SubprocessFlags.STDERR_PIPE);
                string o, e;
                yield p.communicate_utf8_async (null, null, out o, out e);
                out_text = o ?? ""; err_text = e ?? "";
                return p.get_successful ();
            } catch (GLib.Error e) {
                err_text = e.message;
                return false;
            }
        }

        private async void refresh () {
            if (polling || busy) return;
            polling = true;
            string o, e;
            bool ok = yield run ({ "status", "--json" }, out o, out e);
            if (!ok) {
                polling = false;
                set_unavailable ("AirDrop isn't installed");
                return;
            }
            try {
                var parser = new Json.Parser ();
                parser.load_from_data (o);
                var s = parser.get_root ().get_object ();
                apply_status (s);
            } catch (GLib.Error err) {
                set_unavailable ("AirDrop isn't responding");
            }
            polling = false;
            if (!receiving) yield check_ready ();
        }

        private void set_unavailable (string why) {
            ready = false;
            caption.label = why;
            updating = true;
            receive_switch.active = false;
            updating = false;
            receive_switch.sensitive = false;
            problem.label = why + ". Run mseries/install-omdrop.sh to set it up.";
            problem.visible = true;
        }

        private void apply_status (Json.Object s) {
            receiving = s.get_boolean_member_with_default ("receiving", false);
            var visible_now = s.has_member ("visible") && !s.get_null_member ("visible") && s.get_boolean_member ("visible");
            string name = s.has_member ("name") && !s.get_null_member ("name") ? s.get_string_member ("name") : "";
            folder = s.has_member ("dir") ? s.get_string_member ("dir") : "";
            bool contacts = s.has_member ("visibility") && s.get_string_member ("visibility") == "contacts";
            string mode = s.has_member ("mode") ? s.get_string_member ("mode") : "off";
            int64 left = s.has_member ("remaining") && !s.get_null_member ("remaining") ? s.get_int_member ("remaining") : -1;

            updating = true;
            receive_switch.active = receiving;
            audience_pick.selected = contacts ? 1 : 0;
            updating = false;
            receive_switch.sensitive = true;
            name_label.label = name != "" ? "Visible as \"%s\"".printf (name) : "";
            open_folder.sensitive = folder != "";

            if (!receiving) {
                caption.label = "Off";
            } else {
                string who = contacts ? "contacts" : "everyone";
                string until = mode == "once" ? "until one file arrives" : (left >= 0 ? "%d:%02d left".printf ((int) (left / 60), (int) (left % 60)) : "until turned off");
                caption.label = visible_now ? "Visible to %s, %s".printf (who, until) : "Starting…";
            }
        }

        /* When off, ask `doctor` whether receiving can work at all and say why not in plain words. */
        private async void check_ready () {
            string o, e;
            if (!(yield run ({ "doctor", "--json" }, out o, out e))) return;
            try {
                var parser = new Json.Parser ();
                parser.load_from_data (o);
                var d = parser.get_root ().get_object ();
                ready = d.get_boolean_member_with_default ("ready", false);
                if (ready) {
                    problem.visible = false;
                } else {
                    var missing = d.get_array_member ("missing");
                    string first = missing.get_length () > 0 ? missing.get_object_element (0).get_string_member ("say") : "";
                    problem.label = "Not ready: " + first;
                    problem.visible = true;
                    caption.label = "Needs the Wi-Fi driver";
                }
            } catch (GLib.Error err) {
                // Leave whatever status already shows.
            }
        }

        private void on_receive_toggled () {
            if (updating || busy) return;
            bool want = receive_switch.active;
            busy = true;
            receive_switch.sensitive = false;
            caption.label = want ? "Turning on…" : "Turning off…";
            string[] args = want ? new string[] { "on", WINDOW_ARGS[window_pick.selected] } : new string[] { "off" };
            run.begin (args, (o, r) => {
                string so, se;
                bool ok = run.end (r, out so, out se);
                busy = false;
                if (!ok) {
                    var msg = se.strip ();
                    problem.label = msg != "" ? msg.split ("\n")[0] : "AirDrop could not be turned %s".printf (want ? "on" : "off");
                    problem.visible = true;
                } else {
                    problem.visible = false;
                }
                refresh.begin ();
            });
        }

        private void on_audience_changed () {
            if (updating || busy) return;
            string mode = audience_pick.selected == 1 ? "contacts" : "everyone";
            run.begin ({ "visibility", mode }, (o, r) => {
                string so, se;
                run.end (r, out so, out se);
                refresh.begin ();
            });
        }
    }
}
