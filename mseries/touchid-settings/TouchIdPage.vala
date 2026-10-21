/* SPDX-License-Identifier: GPL-3.0-or-later */
/* The Touch ID settings page.
 *
 * Modelled on macOS "Touch ID & Password": a hero that says in one glance whether
 * Touch ID is ready, your fingerprints as tiles, then what they unlock. Built from
 * libadwaita widgets inside a Switchboard plug, like Work Mode. All sensor and PAM
 * work is asynchronous; the page never blocks the Settings main loop, and nothing
 * is written to PAM until the person flips a switch.
 *
 * It also reads the driver's own status (see Diagnostics.vala) so that a Mac where
 * Touch ID cannot work yet says why, instead of offering switches that do nothing. */
namespace MSeriesTouchId {
    public class TouchIdPage : Adw.Bin {
        private Adw.ToastOverlay toasts;
        private Gtk.Stack stack;
        private Adw.StatusPage unavailable_page;

        private Adw.Banner banner;
        private FingerprintArt hero_art;
        private Gtk.Label hero_status;
        private Gtk.Label hero_hint;
        private Gtk.Button hero_add;
        private HandDiagram hands;
        private Gtk.Label hands_caption;

        private Adw.PreferencesGroup fingers_group;
        private Gtk.FlowBox grid;
        private AddTile add_tile;
        private Adw.SwitchRow sudo_row;
        private Adw.SwitchRow polkit_row;
        private Adw.SwitchRow login_row;
        private Adw.PreferencesGroup details_group;
        private Adw.ExpanderRow details_row;
        private Gee.ArrayList<Adw.ActionRow> detail_rows = new Gee.ArrayList<Adw.ActionRow> ();

        private Sensor? sensor = null;
        private string[] enrolled = {};
        private DriverDiag diag = new DriverDiag ();
        private bool busy = false;
        private bool syncing = false;
        private bool loaded = false;
        /* Why turning a switch on is not allowed right now, or null. Checked again in toggled(). */
        private string? switch_blocker = null;

        /* The open Add Fingerprint sheet, if any. */
        public EnrollDialog? active_dialog { get; private set; default = null; }

        public TouchIdPage () {
            Style.ensure ();
            toasts = new Adw.ToastOverlay ();
            stack = new Gtk.Stack () {
                transition_type = Gtk.StackTransitionType.CROSSFADE,
                hexpand = true,
                vexpand = true
            };
            toasts.child = stack;
            child = toasts;

            stack.add_named (build_loading (), "loading");
            stack.add_named (build_unavailable (), "unavailable");
            stack.add_named (build_ready (), "ready");
            stack.visible_child_name = "loading";
        }

        /* ---- construction ------------------------------------------------ */

        private Gtk.Widget build_loading () {
            var spinner = new Adw.Spinner () { width_request = 32, height_request = 32 };
            var label = new Gtk.Label ("Checking Touch ID…");
            label.add_css_class ("dim-label");
            var box = new Gtk.Box (Gtk.Orientation.VERTICAL, 12) {
                halign = Gtk.Align.CENTER,
                valign = Gtk.Align.CENTER
            };
            box.append (spinner);
            box.append (label);
            return box;
        }

        private Gtk.Widget build_unavailable () {
            unavailable_page = new Adw.StatusPage () {
                icon_name = "fingerprint-symbolic",
                title = "Touch ID Isn't Available",
                vexpand = true
            };
            var retry = new Gtk.Button.with_label ("Check Again") { halign = Gtk.Align.CENTER };
            retry.add_css_class ("pill");
            retry.clicked.connect (() => refresh.begin ());
            unavailable_page.child = retry;
            return unavailable_page;
        }

        private Gtk.Widget build_hero () {
            var hero = new Gtk.Box (Gtk.Orientation.VERTICAL, 14);
            hero.add_css_class ("mst-hero");

            hero_art = new FingerprintArt (104, 10, 3.0);
            hero_art.update_property (Gtk.AccessibleProperty.LABEL, "Touch ID", -1);

            var title = new Gtk.Label ("Touch ID") { xalign = 0 };
            title.add_css_class ("mst-hero-title");
            hero_status = new Gtk.Label (null) { xalign = 0, wrap = true, max_width_chars = 34 };
            hero_status.add_css_class ("mst-status");
            hero_hint = new Gtk.Label (null) { xalign = 0, wrap = true, max_width_chars = 34 };
            hero_hint.add_css_class ("dim-label");

            var texts = new Gtk.Box (Gtk.Orientation.VERTICAL, 4) { valign = Gtk.Align.CENTER };
            texts.append (title);
            texts.append (hero_status);
            texts.append (hero_hint);

            var top = new Gtk.Box (Gtk.Orientation.HORIZONTAL, 22) { halign = Gtk.Align.CENTER };
            top.append (hero_art);
            top.append (texts);
            hero.append (top);

            hands = new HandDiagram ();
            hero.append (hands);
            hands_caption = new Gtk.Label (null) { wrap = true, justify = Gtk.Justification.CENTER };
            hands_caption.add_css_class ("dim-label");
            hands_caption.add_css_class ("caption");
            hero.append (hands_caption);

            hero_add = new Gtk.Button.with_label ("Add Fingerprint") { halign = Gtk.Align.CENTER };
            hero_add.add_css_class ("pill");
            hero_add.add_css_class ("suggested-action");
            hero_add.clicked.connect (() => add_fingerprint.begin ());
            hero.append (hero_add);
            return hero;
        }

        private Gtk.Widget build_ready () {
            var content = new Gtk.Box (Gtk.Orientation.VERTICAL, 22) {
                margin_top = 18,
                margin_bottom = 28,
                margin_start = 18,
                margin_end = 18
            };

            banner = new Adw.Banner ("") { revealed = false, button_label = "Details" };
            banner.button_clicked.connect (() => {
                details_row.expanded = true;
                details_row.grab_focus ();
            });
            content.append (banner);
            content.append (build_hero ());

            /* Fingerprints as tiles, then a dashed tile to add one. */
            fingers_group = new Adw.PreferencesGroup () {
                title = "Your Fingerprints",
                description = "Add up to %d fingerprints. Touch ID on Linux is experimental; your password always works as a fallback."
                    .printf (MAX_FINGERS)
            };
            grid = new Gtk.FlowBox () {
                selection_mode = Gtk.SelectionMode.NONE,
                min_children_per_line = 1,
                max_children_per_line = 3,
                column_spacing = 12,
                row_spacing = 12,
                homogeneous = true,
                activate_on_single_click = false
            };
            add_tile = new AddTile ();
            add_tile.clicked.connect (() => add_fingerprint.begin ());
            fingers_group.add (grid);
            content.append (fingers_group);

            var use_group = new Adw.PreferencesGroup () {
                title = "Use Touch ID For",
                description = "Your password is still required after a restart and to unlock the disk at startup."
            };
            sudo_row = new Adw.SwitchRow () {
                title = "Terminal Commands",
                subtitle = "Approve sudo with your fingerprint."
            };
            sudo_row.add_prefix (new Gtk.Image.from_icon_name ("utilities-terminal-symbolic"));
            polkit_row = new Adw.SwitchRow () {
                title = "System Authorization",
                subtitle = "Approve administrator prompts from apps and Settings."
            };
            polkit_row.add_prefix (new Gtk.Image.from_icon_name ("dialog-password-symbolic"));
            login_row = new Adw.SwitchRow () {
                title = "Login and Lock Screen",
                subtitle = "Not available yet.",
                sensitive = false
            };
            login_row.add_prefix (new Gtk.Image.from_icon_name ("system-lock-screen-symbolic"));
            use_group.add (sudo_row);
            use_group.add (polkit_row);
            use_group.add (login_row);
            content.append (use_group);

            sudo_row.notify["active"].connect (() => toggled.begin (sudo_row, "sudo", "terminal commands"));
            polkit_row.notify["active"].connect (() => toggled.begin (polkit_row, "polkit-1", "system authorization"));

            details_group = new Adw.PreferencesGroup ();
            details_row = new Adw.ExpanderRow () {
                title = "Details",
                subtitle = "What the Secure Enclave driver reports"
            };
            details_row.add_prefix (new Gtk.Image.from_icon_name ("utilities-system-monitor-symbolic"));
            details_group.add (details_row);
            details_group.visible = false;
            content.append (details_group);

            var clamp = new Adw.Clamp () {
                maximum_size = 680,
                tightening_threshold = 540,
                child = content
            };
            return new Gtk.ScrolledWindow () {
                child = clamp,
                hscrollbar_policy = Gtk.PolicyType.NEVER,
                vexpand = true
            };
        }

        /* ---- state ------------------------------------------------------- */

        /* Called each time the page is shown. Cheap after the first load. */
        public async void refresh () {
            if (busy) {
                return;
            }
            busy = true;
            if (!loaded) {
                stack.visible_child_name = "loading";
            }
            try {
                if (sensor == null) {
                    sensor = yield Sensor.open ();
                }
                enrolled = yield sensor.enrolled ();
                diag = DriverDiag.read ();
                rebuild_fingers ();
                apply_state ();
                update_details ();
                sync_switches ();
                loaded = true;
                stack.visible_child_name = "ready";
            } catch (TouchIdError.NO_ENCLAVE e) {
                show_unavailable ("Touch ID Isn't Available",
                    "This kernel doesn't expose the Secure Enclave fingerprint device. Touch ID needs the Aurora SEP kernel on an M-series Mac.");
            } catch (TouchIdError.NO_DEVICE e) {
                show_unavailable ("No Fingerprint Sensor Found",
                    "The Secure Enclave is running, but fprintd doesn't report a sensor. %s".printf (e.message));
            } catch (GLib.Error e) {
                if (loaded) {
                    toasts.add_toast (new Adw.Toast ("Couldn't read Touch ID: %s".printf (e.message)));
                } else {
                    show_unavailable ("Touch ID Didn't Respond", e.message);
                }
            }
            busy = false;
        }

        private void show_unavailable (string title, string detail) {
            sensor = null;
            loaded = false;
            unavailable_page.title = title;
            unavailable_page.description = detail;
            stack.visible_child_name = "unavailable";
        }

        private bool matching_blocked () {
            return diag.get ("matching") == "blocked";
        }

        private bool sensor_not_ready () {
            return diag.get ("touchid") == "not-ready";
        }

        /* The hero, hands and banner: one honest summary of where Touch ID stands. */
        private void apply_state () {
            int count = enrolled.length;
            hands.enrolled = enrolled;
            hands.target = null;
            hands_caption.set_text (count == 0
                ? "No fingerprints yet. Touch ID on Linux is experimental; your password always works as a fallback."
                : string.joinv (" · ", labelled (enrolled)));

            foreach (var css in new string[] { "success", "warning", "error", "dim-label" }) {
                hero_status.remove_css_class (css);
            }

            string? banner_text = null;
            if (sensor_not_ready ()) {
                hero_art.lit = false;
                hero_status.set_text ("Needs attention");
                hero_status.add_css_class ("warning");
                hero_hint.set_text ("The sensor didn't finish starting. Restart your Mac to recover it.");
                banner_text = "The Touch ID sensor isn't ready";
            } else if (matching_blocked ()) {
                hero_art.lit = false;
                hero_status.set_text (count > 0 ? "Added, but can't unlock yet" : "Can't unlock yet");
                hero_status.add_css_class ("warning");
                hero_hint.set_text ("Matching is switched off on this Mac, so a fingerprint can't approve anything yet.");
                banner_text = "Matching is blocked by the xART guard on this Mac";
            } else if (count == 0) {
                hero_art.lit = false;
                hero_status.set_text ("Not set up");
                hero_status.add_css_class ("dim-label");
                hero_hint.set_text ("Unlock commands and prompts with a touch.");
            } else {
                hero_art.lit = true;
                hero_status.set_text ("Ready");
                hero_status.add_css_class ("success");
                hero_hint.set_text (count == 1 ? "1 fingerprint added." : "%d fingerprints added.".printf (count));
            }

            hero_add.visible = count == 0;
            banner.title = banner_text ?? "";
            banner.revealed = banner_text != null && diag.available;
        }

        private static string[] labelled (string[] fingers) {
            string[] names = {};
            foreach (var finger in fingers) {
                names += finger_label (finger);
            }
            return names;
        }

        private void rebuild_fingers () {
            /* With no fingerprints the hero's button is the one call to action. */
            fingers_group.visible = enrolled.length > 0;
            grid.remove_all ();
            foreach (var finger in enrolled) {
                var card = new FingerCard (finger);
                card.remove_requested.connect ((f) => confirm_remove.begin (f));
                grid.append (card);
            }
            if (enrolled.length < MAX_FINGERS) {
                grid.append (add_tile);
            }
            /* Only the buttons inside the tiles should take keyboard focus. */
            for (var child = grid.get_first_child (); child != null; child = child.get_next_sibling ()) {
                child.focusable = false;
            }
        }

        private void update_details () {
            foreach (var row in detail_rows) {
                details_row.remove (row);
            }
            detail_rows.clear ();
            details_group.visible = diag.available;
            if (!diag.available) {
                return;
            }
            foreach (var key in DriverDiag.ORDER) {
                var value = diag.get (key);
                if (value == null) {
                    continue;
                }
                var row = new Adw.ActionRow () { title = DriverDiag.label (key) };
                var explanation = DriverDiag.explanation (key, value);
                if (explanation != null) {
                    row.subtitle = explanation;
                }
                var shown = new Gtk.Label (value) { valign = Gtk.Align.CENTER, selectable = true };
                shown.add_css_class ("mst-mono");
                if (explanation != null) {
                    shown.add_css_class ("warning");
                }
                row.add_suffix (shown);
                details_row.add_row (row);
                detail_rows.add (row);
            }
        }

        private void sync_switches () {
            syncing = true;
            bool has_finger = enrolled.length > 0;
            bool helper_ok = GLib.FileUtils.test (Hooks.helper (), GLib.FileTest.EXISTS);
            string? blocker = null;
            if (!has_finger) {
                blocker = "Add a fingerprint first.";
            } else if (sensor_not_ready ()) {
                blocker = "The Touch ID sensor isn't ready.";
            } else if (matching_blocked ()) {
                blocker = "Matching is blocked on this Mac, so a fingerprint can't approve this yet.";
            } else if (!helper_ok) {
                blocker = "The Touch ID helper isn't installed. Run mseries/install-touchid-settings.sh.";
            }

            switch_blocker = blocker;
            sudo_row.active = pam_uses_fingerprint ("sudo");
            polkit_row.active = pam_uses_fingerprint ("polkit-1");
            /* A switch that is already on stays usable so it can always be turned off. */
            sudo_row.sensitive = blocker == null || sudo_row.active;
            polkit_row.sensitive = blocker == null || polkit_row.active;
            sudo_row.subtitle = blocker ?? "Approve sudo with your fingerprint.";
            polkit_row.subtitle = blocker ?? "Approve administrator prompts from apps and Settings.";
            syncing = false;
        }

        /* ---- actions ----------------------------------------------------- */

        private async void toggled (Adw.SwitchRow row, string service, string what) {
            if (syncing) {
                return;
            }
            bool wanted = row.active;
            /* The row is greyed out for people; enforce the same rule here so nothing else can flip it. */
            if (wanted && switch_blocker != null) {
                toasts.add_toast (new Adw.Toast (switch_blocker));
                sync_switches ();
                return;
            }
            row.sensitive = false;
            var error = yield set_pam (service, wanted);
            if (error == "") {
                toasts.add_toast (new Adw.Toast (
                    wanted ? "Touch ID is on for %s".printf (what) : "Touch ID is off for %s".printf (what)));
            } else if (error != "Cancelled") {
                toasts.add_toast (new Adw.Toast ("Couldn't change %s: %s".printf (what, error)));
            }
            /* Show what is really in /etc/pam.d, not what was asked for. */
            sync_switches ();
        }

        private async void add_fingerprint () {
            if (busy || sensor == null) {
                return;
            }
            var finger = next_free_finger (enrolled);
            if (finger == null || enrolled.length >= MAX_FINGERS) {
                return;
            }
            var window = get_root () as Gtk.Window;
            if (window == null) {
                return;
            }
            busy = true;
            var dialog = new EnrollDialog (sensor, finger, enrolled);
            active_dialog = dialog;
            dialog.finished.connect ((added) => {
                busy = false;
                active_dialog = null;
                if (added) {
                    toasts.add_toast (new Adw.Toast ("Fingerprint added"));
                }
                refresh.begin ();
            });
            dialog.present (window);
            yield dialog.begin_enrol ();
        }

        /* Preview/screenshot hook: same path as pressing Add Fingerprint. */
        public void open_add_for_preview () {
            add_fingerprint.begin ();
        }

        private async void confirm_remove (string finger) {
            var window = get_root () as Gtk.Window;
            if (window == null || sensor == null || busy) {
                return;
            }
            var alert = new Adw.AlertDialog (
                "Remove %s?".printf (finger_label (finger).down ()),
                "Touch ID will stop recognising it. You can add it again later, but avoid removing and re-adding fingerprints repeatedly."
            );
            alert.add_response ("cancel", "Cancel");
            alert.add_response ("remove", "Remove");
            alert.set_response_appearance ("remove", Adw.ResponseAppearance.DESTRUCTIVE);
            alert.default_response = "cancel";
            alert.close_response = "cancel";

            var response = yield alert.choose (window, null);
            if (response != "remove") {
                return;
            }
            busy = true;
            try {
                yield sensor.remove (finger);
                toasts.add_toast (new Adw.Toast ("Fingerprint removed"));
            } catch (GLib.Error e) {
                toasts.add_toast (new Adw.Toast ("Couldn't remove it: %s".printf (e.message)));
            }
            busy = false;
            yield refresh ();
        }
    }
}
