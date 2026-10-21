/* The "Add a Fingerprint" sheet.
 *
 * One enrolment per sheet and no retry button on failure: the Secure Enclave
 * keeps a device-wide anti-replay counter that enrol/delete loops advance, so a
 * failed attempt closes and the person starts again deliberately.
 */
namespace MSeriesTouchId {
    public class EnrollDialog : Gtk.Window {
        public signal void finished (bool added);

        private Sensor sensor;
        private string finger;
        private FingerprintArt art;
        private Gtk.Label title_label;
        private Gtk.Label hint_label;
        private Gtk.Button action_button;

        private ulong status_handler = 0;
        private bool claimed = false;
        private bool enrolling = false;
        private bool closing = false;
        private bool added = false;
        private int stages_passed = 0;

        public EnrollDialog (Gtk.Window parent, Sensor sensor, string finger) {
            Object (
                transient_for: parent,
                modal: true,
                resizable: false,
                destroy_with_parent: true,
                title: "Add a Fingerprint"
            );
            this.sensor = sensor;
            this.finger = finger;

            /* A bare sheet: the content carries its own title. */
            titlebar = new Gtk.Box (Gtk.Orientation.HORIZONTAL, 0) { visible = false };
            default_width = 380;

            art = new FingerprintArt ();

            title_label = new Gtk.Label ("Add a Fingerprint") { wrap = true, justify = Gtk.Justification.CENTER };
            title_label.add_css_class ("title-2");

            hint_label = new Gtk.Label (null) {
                wrap = true,
                justify = Gtk.Justification.CENTER,
                max_width_chars = 36,
                use_markup = false
            };
            hint_label.add_css_class ("dim-label");
            hint_label.set_text (
                "Place your %s on the sensor, then lift it and place it again. Keep tapping like this, shifting your finger a little each time so its edges are covered."
                    .printf (finger_label (finger).down ()));

            action_button = new Gtk.Button.with_label ("Cancel") { halign = Gtk.Align.CENTER };
            action_button.add_css_class ("pill");
            action_button.clicked.connect (() => {
                if (enrolling) {
                    cancel.begin ();
                } else {
                    close ();
                }
            });

            var box = new Gtk.Box (Gtk.Orientation.VERTICAL, 16) {
                margin_top = 32,
                margin_bottom = 28,
                margin_start = 32,
                margin_end = 32
            };
            box.append (art);
            box.append (title_label);
            box.append (hint_label);
            box.append (action_button);
            child = box;
            default_widget = action_button;

            update_art_description ();
            close_request.connect (on_close_request);
        }

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
            try {
                yield sensor.device.enroll_start (finger);
                enrolling = true;
            } catch (GLib.Error e) {
                fail ("Touch ID could not start", e.message);
                yield cleanup ();
            }
        }

        private void on_status (string result, bool done) {
            if (!enrolling) {
                return;
            }
            switch (result) {
                case "enroll-stage-passed":
                    stages_passed++;
                    art.progress = (double) stages_passed / sensor.stages;
                    hint_label.set_text ("Got it. Lift, then place your finger again.");
                    break;
                case "enroll-retry-scan":
                    hint_label.set_text ("That one didn't read. Lift and tap again, a little firmer.");
                    break;
                case "enroll-finger-not-centered":
                    hint_label.set_text ("Center your finger on the sensor.");
                    break;
                case "enroll-remove-and-retry":
                    hint_label.set_text ("Lift your finger, then place it again.");
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
            art.progress = 1.0;
            art.complete = true;
            title_label.set_text ("Fingerprint Added");
            hint_label.set_text ("You can use it to approve commands and system prompts. Your password still works.");
            action_button.set_label ("Done");
            action_button.add_css_class ("suggested-action");
            cleanup.begin ();
            update_art_description ();
        }

        private void fail (string title, string detail) {
            enrolling = false;
            title_label.set_text (title);
            hint_label.set_text (detail);
            action_button.set_label ("Close");
            cleanup.begin ();
        }

        private async void cancel () {
            action_button.sensitive = false;
            yield cleanup ();
            close ();
        }

        /* Always leave the sensor released, whichever way the sheet ends. */
        private async void cleanup () {
            if (status_handler != 0) {
                sensor.device.disconnect (status_handler);
                status_handler = 0;
            }
            if (enrolling) {
                enrolling = false;
                try {
                    yield sensor.device.enroll_stop ();
                } catch (GLib.Error e) {
                    GLib.warning ("EnrollStop failed: %s", e.message);
                }
            } else if (claimed && !added) {
                /* enrolment never started or already ended; nothing to stop */
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

        private bool on_close_request () {
            if (closing) {
                return false;
            }
            if (enrolling || claimed) {
                closing = true;
                cleanup.begin ((obj, res) => {
                    cleanup.end (res);
                    finished (added);
                    close ();
                });
                return true;
            }
            finished (added);
            return false;
        }

        private void update_art_description () {
            var percent = (int) GLib.Math.round (art.progress * 100);
            art.update_property (Gtk.AccessibleProperty.LABEL,
                                 "Fingerprint enrolment, %d percent complete".printf (percent), -1);
        }
    }
}
