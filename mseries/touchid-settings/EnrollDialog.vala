/* SPDX-License-Identifier: GPL-3.0-or-later */
/* The "Add Fingerprint" sheet, an Adw.Dialog.
 *
 * One enrolment per sheet and no retry button on failure: the Secure Enclave
 * keeps a device-wide anti-replay counter that enrol/delete loops advance, so a
 * failed attempt closes and the person starts again deliberately.
 *
 * What the person sees: the hand with the finger to use pulsing, the print that
 * "breathes" while it waits, a Place / Lift cue that cycles at the tempo that has
 * worked on real hardware, a ripple and a smoother fill on every accepted touch,
 * and a green seal when the enclave says it is done. Cancel, Escape and closing
 * the sheet all end the enrolment and release the sensor. */
namespace MSeriesTouchId {
    public class EnrollDialog : Adw.Dialog {
        public signal void finished (bool added);

        private Sensor sensor;
        private string finger;
        private Gtk.Label finger_chip;
        private FingerprintArt art;
        private Gtk.Label title_label;
        private Gtk.Label hint_label;
        private Gtk.Label count_label;
        private Gtk.Box steps;
        private Gtk.Label step_place;
        private Gtk.Label step_lift;
        private Gtk.Button cancel_button;
        private Gtk.Button done_button;

        private ulong status_handler = 0;
        private ulong props_handler = 0;
        private uint invite_timer = 0;
        private uint idle_timer = 0;
        private bool live_events = false;
        private bool finger_down = false;
        private bool nudged = false;
        private uint cue_timer = 0;
        private bool cue_place = true;
        private bool claimed = false;
        private bool enrolling = false;
        private bool added = false;
        private bool ending = false;
        private int stages_passed = 0;

        public EnrollDialog (Sensor sensor, string finger, string[] enrolled) {
            Object (
                title: "Add Fingerprint",
                content_width: 420,
                follows_content_size: true,
                can_close: false
            );
            this.sensor = sensor;
            this.finger = finger;

            /* Header: Cancel on the left, Done appears on the right at the end. */
            var header = new Adw.HeaderBar () {
                show_start_title_buttons = false,
                show_end_title_buttons = false,
                title_widget = new Adw.WindowTitle ("Add Fingerprint", "")
            };
            cancel_button = new Gtk.Button.with_label ("Cancel");
            cancel_button.clicked.connect (() => request_end.begin ());
            header.pack_start (cancel_button);
            done_button = new Gtk.Button.with_label ("Done") { visible = false };
            done_button.add_css_class ("suggested-action");
            done_button.clicked.connect (() => force_close ());
            header.pack_end (done_button);

            finger_chip = new Gtk.Label (finger_label (finger)) { halign = Gtk.Align.CENTER };
            finger_chip.add_css_class ("mst-step");
            finger_chip.add_css_class ("mst-active");
            art = new FingerprintArt (172, 12, 3.8) { seed = finger_seed (finger) };

            title_label = new Gtk.Label ("Getting the sensor ready…") {
                wrap = true,
                justify = Gtk.Justification.CENTER
            };
            title_label.add_css_class ("mst-sheet-title");

            hint_label = new Gtk.Label (null) {
                wrap = true,
                justify = Gtk.Justification.CENTER,
                max_width_chars = 38
            };
            hint_label.add_css_class ("dim-label");
            hint_label.set_text ("Keep your finger off the sensor for a moment.");

            step_place = make_step ("Place");
            step_lift = make_step ("Lift");
            var step_repeat = make_step ("Repeat");
            steps = new Gtk.Box (Gtk.Orientation.HORIZONTAL, 8) { halign = Gtk.Align.CENTER, visible = false };
            steps.append (step_place);
            steps.append (step_lift);
            steps.append (step_repeat);
            /* The cue is decoration for sighted users; the hint label carries the words. */
            steps.update_property (Gtk.AccessibleProperty.LABEL, "Place your finger, lift it, repeat", -1);

            count_label = new Gtk.Label (null);
            count_label.add_css_class ("dim-label");
            count_label.add_css_class ("caption");

            var body = new Gtk.Box (Gtk.Orientation.VERTICAL, 14) {
                margin_top = 14,
                margin_bottom = 28,
                margin_start = 32,
                margin_end = 32,
                halign = Gtk.Align.CENTER
            };
            body.append (finger_chip);
            body.append (art);
            body.append (title_label);
            body.append (hint_label);
            body.append (steps);
            body.append (count_label);

            var view = new Adw.ToolbarView ();
            view.add_top_bar (header);
            view.content = body;
            child = view;

            closed.connect (() => {
                stop_timers ();
                finished (added);
            });
            close_attempt.connect (() => request_end.begin ());
        }

        private Gtk.Label make_step (string text) {
            var label = new Gtk.Label (text);
            label.add_css_class ("mst-step");
            return label;
        }

        /* ---- the Place / Lift cue ---------------------------------------- */

        private void start_cue () {
            if (!Gtk.Settings.get_default ().gtk_enable_animations) {
                step_place.add_css_class ("mst-active");
                return;
            }
            cue_place = true;
            cue_step ();
        }

        private void cue_step () {
            if (cue_place) {
                step_place.add_css_class ("mst-active");
                step_lift.remove_css_class ("mst-active");
            } else {
                step_lift.add_css_class ("mst-active");
                step_place.remove_css_class ("mst-active");
            }
            uint delay = cue_place ? 1200 : 800;
            cue_place = !cue_place;
            cue_timer = GLib.Timeout.add (delay, () => {
                cue_timer = 0;
                cue_step ();
                return GLib.Source.REMOVE;
            });
        }

        private void stop_cue () {
            if (cue_timer != 0) {
                GLib.Source.remove (cue_timer);
                cue_timer = 0;
            }
        }

        private void stop_timers () {
            stop_cue ();
            if (invite_timer != 0) {
                GLib.Source.remove (invite_timer);
                invite_timer = 0;
            }
            if (idle_timer != 0) {
                GLib.Source.remove (idle_timer);
                idle_timer = 0;
            }
        }

        /* ---- enrolment ---------------------------------------------------- */

        public async void begin_enrol () {
            var user = Hooks.user ();
            try {
                yield sensor.device.claim (user);
                claimed = true;
            } catch (GLib.Error e) {
                fail ("Touch ID could not be used", e.message);
                return;
            }

            status_handler = sensor.device.enroll_status.connect (on_status);
            /* If fprintd reports finger presence, follow it live; otherwise the timed cue stands in. */
            props_handler = ((GLib.DBusProxy) sensor.device).g_properties_changed.connect (on_properties);
            try {
                yield sensor.device.enroll_start (finger);
                enrolling = true;
                become_ready ();
            } catch (GLib.Error e) {
                fail ("Touch ID could not start", e.message);
                yield cleanup ();
            }
        }

        /* The sensor is up and listening: this is the moment to put a finger on it. People click Add
         * with a pointer, so the sheet must not assume the finger is already there. */
        private void become_ready () {
            art.state = ArtState.WAITING;
            steps.visible = true;
            prompt_place ();
            start_cue ();
            start_invite ();
            idle_timer = GLib.Timeout.add_seconds (15, () => {
                idle_timer = 0;
                if (enrolling && stages_passed == 0 && !finger_down && !nudged) {
                    nudged = true;
                    title_label.set_text ("Still waiting for your finger");
                    set_hint ("Place your fingertip flat on the sensor, covering the whole pad.");
                }
                return GLib.Source.REMOVE;
            });
        }

        private void prompt_place () {
            if (stages_passed == 0) {
                title_label.set_text ("Place your finger on the sensor now");
                set_hint ("Rest your %s flat on the sensor. The print fills in as each touch is read."
                    .printf (finger_label (finger).down ()));
            } else {
                title_label.set_text ("Place your finger again");
                set_hint ("Lift, then rest it on the sensor again, covering a slightly different part.");
            }
        }

        /* A ripple every couple of seconds invites the first touch, then stops. */
        private void start_invite () {
            if (!Gtk.Settings.get_default ().gtk_enable_animations) {
                return;
            }
            invite_timer = GLib.Timeout.add (1800, () => {
                if (!enrolling || stages_passed > 0 || finger_down) {
                    invite_timer = 0;
                    return GLib.Source.REMOVE;
                }
                art.ripple ();
                return GLib.Source.CONTINUE;
            });
        }

        /* fprintd's finger-needed / finger-present, when the sensor driver reports them. */
        private void on_properties (GLib.Variant changed, string[] invalidated) {
            if (!enrolling) {
                return;
            }
            var present = changed.lookup_value ("finger-present", GLib.VariantType.BOOLEAN);
            var needed = changed.lookup_value ("finger-needed", GLib.VariantType.BOOLEAN);
            if (present == null && needed == null) {
                return;
            }
            if (!live_events) {
                /* Real events arrived: stop the timed cue and let the sensor drive it. */
                live_events = true;
                stop_cue ();
            }
            if (present != null) {
                finger_down = present.get_boolean ();
                if (finger_down) {
                    step_place.add_css_class ("mst-active");
                    step_lift.remove_css_class ("mst-active");
                    art.ripple ();
                    title_label.set_text ("Hold still");
                    set_hint ("Reading your fingerprint.");
                } else {
                    step_lift.add_css_class ("mst-active");
                    step_place.remove_css_class ("mst-active");
                    if (stages_passed > 0) {
                        title_label.set_text ("Lift, then place it again");
                    }
                }
            }
            if (needed != null && needed.get_boolean () && !finger_down) {
                step_place.add_css_class ("mst-active");
                step_lift.remove_css_class ("mst-active");
                prompt_place ();
            }
        }

        /* The sensor reports 37 stages but a real enrolment finished in about eight
         * touches, so the fill is an estimate that never reaches 100% on its own;
         * "Fingerprint Added" is what finishes it. */
        private double estimated_progress () {
            double expected = sensor.stages <= 15 ? sensor.stages : 8;
            return double.min ((double) stages_passed / expected, 0.92);
        }

        private void set_hint (string text) {
            hint_label.set_text (text);
            announce (text, Gtk.AccessibleAnnouncementPriority.MEDIUM);
        }

        private void on_status (string result, bool done) {
            if (!enrolling) {
                return;
            }
            switch (result) {
                case "enroll-stage-passed":
                    stages_passed++;
                    art.ripple ();
                    art.animate_progress (estimated_progress ());
                    title_label.set_text ("Keep going");
                    set_hint ("Got it. Lift, then place your finger again, covering a slightly different part.");
                    count_label.set_text (stages_passed == 1 ? "1 touch registered" : "%d touches registered".printf (stages_passed));
                    break;
                case "enroll-retry-scan":
                    set_hint ("That one didn't read. Lift and place it again, a little firmer.");
                    break;
                case "enroll-finger-not-centered":
                    set_hint ("Center your fingertip on the sensor.");
                    break;
                case "enroll-too-fast":
                    set_hint ("That was too quick. Rest your finger a moment before lifting.");
                    break;
                case "enroll-swipe-too-short":
                    set_hint ("Place your finger and keep it there a little longer.");
                    break;
                case "enroll-remove-and-retry":
                    set_hint ("Lift your finger, then place it again.");
                    break;
                case "enroll-duplicate":
                    fail ("This fingerprint is already added", "Choose a different finger, or remove the existing one first.");
                    break;
                case "enroll-completed":
                    succeed ();
                    break;
                case "enroll-data-full":
                    fail ("No room for another fingerprint", "Remove a fingerprint and try again.");
                    break;
                case "enroll-disconnected":
                    fail ("The sensor went away", "Touch ID stopped responding. Close this and check Touch ID again.");
                    break;
                case "enroll-failed":
                default:
                    if (done) {
                        fail ("The fingerprint could not be saved",
                              "Close this and check Touch ID before trying again. Details are in the kernel log (journalctl -k).");
                    }
                    break;
            }
            update_art_description ();
        }

        private void succeed () {
            added = true;
            enrolling = false;
            stop_timers ();
            steps.visible = false;
            art.state = ArtState.SUCCESS;
            title_label.set_text ("Fingerprint Added");
            set_hint ("You can use it to approve commands and system prompts. Your password still works.");
            cancel_button.visible = false;
            done_button.visible = true;
            done_button.grab_focus ();
            can_close = true;
            cleanup.begin ();
            update_art_description ();
        }

        private void fail (string title, string detail) {
            enrolling = false;
            stop_timers ();
            steps.visible = false;
            art.state = ArtState.FAILED;
            title_label.set_text (title);
            set_hint (detail);
            cancel_button.set_label ("Close");
            can_close = true;
            cleanup.begin ();
        }

        /* Cancel, Escape or closing mid-enrolment: stop the enclave, release the sensor, then close. */
        private async void request_end () {
            if (ending) {
                return;
            }
            ending = true;
            cancel_button.sensitive = false;
            yield cleanup ();
            can_close = true;
            force_close ();
        }

        /* Always leave the sensor released, whichever way the sheet ends. */
        private async void cleanup () {
            if (status_handler != 0) {
                sensor.device.disconnect (status_handler);
                status_handler = 0;
            }
            if (props_handler != 0) {
                ((GLib.DBusProxy) sensor.device).disconnect (props_handler);
                props_handler = 0;
            }
            if (enrolling) {
                enrolling = false;
                try {
                    yield sensor.device.enroll_stop ();
                } catch (GLib.Error e) {
                    GLib.warning ("EnrollStop failed: %s", e.message);
                }
            }
            if (claimed) {
                claimed = false;
                try {
                    yield sensor.device.release ();
                } catch (GLib.Error e) {
                    GLib.warning ("Release failed: %s", e.message);
                }
            }
        }

        private void update_art_description () {
            string text;
            if (added) {
                text = "Fingerprint added";
            } else {
                text = "Fingerprint enrolment, %d touches registered".printf (stages_passed);
            }
            art.update_property (Gtk.AccessibleProperty.LABEL, text, -1);
        }
    }
}
