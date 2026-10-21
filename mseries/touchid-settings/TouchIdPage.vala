/* The Touch ID settings page: fingerprints, then what they unlock.
 *
 * Modelled on macOS "Touch ID & Password" and built from the same pieces as
 * the Work Mode page (libadwaita preferences widgets inside a Switchboard plug).
 * All sensor and PAM work is asynchronous; the page never blocks the Settings
 * main loop. Nothing is written to PAM until the person flips a switch.
 */
namespace MSeriesTouchId {
    public class TouchIdPage : Adw.Bin {
        private Adw.ToastOverlay toasts;
        private Gtk.Stack stack;
        private Adw.StatusPage unavailable_page;
        private Adw.PreferencesGroup fingers_group;
        private Adw.PreferencesGroup use_group;
        private Adw.ButtonRow add_row;
        private Adw.SwitchRow sudo_row;
        private Adw.SwitchRow polkit_row;
        private Adw.SwitchRow login_row;
        private Gee.ArrayList<Adw.ActionRow> finger_rows = new Gee.ArrayList<Adw.ActionRow> ();

        private Sensor? sensor = null;
        private string[] enrolled = {};
        private bool busy = false;
        private bool syncing = false;
        private bool loaded = false;
        private bool add_row_attached = false;

        /* The open Add Fingerprint sheet, if any. */
        public EnrollDialog? active_dialog { get; private set; default = null; }

        public TouchIdPage () {
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

        private Gtk.Widget build_ready () {
            var page = new Adw.PreferencesPage ();

            fingers_group = new Adw.PreferencesGroup () {
                title = "Fingerprints",
                description = "Add up to %d fingerprints. Touch ID on Linux is experimental; your password always works as a fallback."
                    .printf (MAX_FINGERS)
            };
            add_row = new Adw.ButtonRow () {
                title = "Add Fingerprint",
                start_icon_name = "list-add-symbolic"
            };
            add_row.activated.connect (() => add_fingerprint.begin ());
            page.add (fingers_group);

            use_group = new Adw.PreferencesGroup () {
                title = "Use Touch ID For",
                description = "Your password is still required after a restart and to unlock the disk at startup."
            };
            sudo_row = new Adw.SwitchRow () {
                title = "Terminal Commands",
                subtitle = "Approve sudo with your fingerprint."
            };
            polkit_row = new Adw.SwitchRow () {
                title = "System Authorization",
                subtitle = "Approve administrator prompts from apps and Settings."
            };
            login_row = new Adw.SwitchRow () {
                title = "Login and Lock Screen",
                subtitle = "Not available yet.",
                sensitive = false
            };
            use_group.add (sudo_row);
            use_group.add (polkit_row);
            use_group.add (login_row);
            page.add (use_group);

            sudo_row.notify["active"].connect (() => toggled.begin (sudo_row, "sudo", "terminal commands"));
            polkit_row.notify["active"].connect (() => toggled.begin (polkit_row, "polkit-1", "system authorization"));
            return page;
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
                rebuild_fingers ();
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

        private void rebuild_fingers () {
            foreach (var row in finger_rows) {
                fingers_group.remove (row);
            }
            finger_rows.clear ();
            if (add_row_attached) {
                fingers_group.remove (add_row);
                add_row_attached = false;
            }

            foreach (var finger in enrolled) {
                var row = new Adw.ActionRow () {
                    title = finger_label (finger),
                    subtitle = "Touch ID"
                };
                row.add_prefix (new Gtk.Image.from_icon_name ("fingerprint-symbolic"));
                var remove = new Gtk.Button.from_icon_name ("edit-delete-symbolic") {
                    valign = Gtk.Align.CENTER,
                    tooltip_text = "Remove %s".printf (finger_label (finger).down ())
                };
                remove.add_css_class ("flat");
                remove.update_property (Gtk.AccessibleProperty.LABEL,
                                        "Remove %s".printf (finger_label (finger).down ()), -1);
                var captured = finger;
                remove.clicked.connect (() => confirm_remove.begin (captured));
                row.add_suffix (remove);
                fingers_group.add (row);
                finger_rows.add (row);
            }

            if (enrolled.length < MAX_FINGERS) {
                fingers_group.add (add_row);
                add_row_attached = true;
            }
        }

        private void sync_switches () {
            syncing = true;
            bool has_finger = enrolled.length > 0;
            bool helper_ok = GLib.FileUtils.test (Hooks.helper (), GLib.FileTest.EXISTS);
            string? blocker = !has_finger ? "Add a fingerprint first."
                : (!helper_ok ? "The Touch ID helper isn't installed. Run mseries/install-touchid-settings.sh." : null);

            sudo_row.active = pam_uses_fingerprint ("sudo");
            polkit_row.active = pam_uses_fingerprint ("polkit-1");
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
            row.sensitive = false;
            var error = yield set_pam (service, wanted);
            if (error == "") {
                toasts.add_toast (new Adw.Toast (
                    wanted ? "Touch ID is on for %s".printf (what) : "Touch ID is off for %s".printf (what)));
            } else {
                if (error != "Cancelled") {
                    toasts.add_toast (new Adw.Toast ("Couldn't change %s: %s".printf (what, error)));
                }
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
            var dialog = new EnrollDialog (window, sensor, finger);
            active_dialog = dialog;
            dialog.finished.connect ((added) => {
                busy = false;
                active_dialog = null;
                if (added) {
                    toasts.add_toast (new Adw.Toast ("Fingerprint added"));
                }
                refresh.begin ();
            });
            dialog.present ();
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
                "Touch ID will stop recognising it. You can add it again later."
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
