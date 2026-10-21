/* SPDX-License-Identifier: GPL-3.0-or-later */
namespace MSeries.Remote {
    public enum Answer {
        DENY,
        VIEW_ONLY,
        CONTROL
    }

    /* The owner's yes. Deny is the default, so a stray Enter never shares the screen. */
    public class ConsentPrompt : Granite.MessageDialog {
        public PendingRequest request { get; construct; }
        public signal void answered (Answer answer);
        private Gtk.Label countdown_label;
        private uint tick = 0;

        public ConsentPrompt (PendingRequest request, Gtk.Window? parent) {
            Object (
                request: request,
                primary_text: _("Allow “%s” to see your screen?").printf (request.device),
                secondary_text: _("This phone used a link you created. It will see everything on your screen. Nothing is recorded."),
                image_icon: new ThemedIcon ("preferences-system-sharing"),
                buttons: Gtk.ButtonsType.NONE,
                transient_for: parent,
                modal: false
            );
        }

        construct {
            title = _("Remote Desktop");
            add_button (_("Deny"), Answer.DENY);
            add_button (_("View Only"), Answer.VIEW_ONLY);
            if (request.control_offered) {
                var control = add_button (_("Allow Control"), Answer.CONTROL);
                control.add_css_class (Granite.CssClass.DESTRUCTIVE);
            } else {
                custom_bin.append (new Gtk.Label (_("This link offers viewing only.")) {
                    halign = Gtk.Align.START,
                    css_classes = { Granite.CssClass.DIM }
                });
            }
            set_default_response (Answer.DENY);
            countdown_label = new Gtk.Label ("") { halign = Gtk.Align.START, css_classes = { Granite.CssClass.DIM } };
            custom_bin.append (countdown_label);
            update_countdown ();
            tick = Timeout.add_seconds (1, () => {
                update_countdown ();
                return Source.CONTINUE;
            });
            response.connect ((id) => {
                clear_tick ();
                answered ((Answer) id);
                destroy ();
            });
            close_request.connect (() => {
                // Closing the window is a refusal, never an approval.
                clear_tick ();
                answered (Answer.DENY);
                return false;
            });
        }

        private void update_countdown () {
            int64 left = request.expires_ms - get_real_time () / 1000;
            countdown_label.label = _("Declines automatically in %s").printf (Presentation.countdown (left));
        }

        private void clear_tick () {
            if (tick != 0) {
                Source.remove (tick);
                tick = 0;
            }
        }

        /* The service withdrew the request (timeout, cancelled): close without answering. */
        public void withdraw () {
            clear_tick ();
            destroy ();
        }
    }
}
