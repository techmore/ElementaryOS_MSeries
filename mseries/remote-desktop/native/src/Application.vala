/* SPDX-License-Identifier: GPL-3.0-or-later */
namespace MSeries.Remote {
    public class Application : Gtk.Application {
        private Service service;
        private MainWindow? window = null;
        private ConsentPrompt? prompt = null;
        private bool background = false;
        private string? prompt_id = null;

        public Application () {
            Object (application_id: "io.github.techmore.RemoteDesktop", flags: ApplicationFlags.HANDLES_COMMAND_LINE);
            add_main_option ("background", 0, OptionFlags.NONE, OptionArg.NONE, "Run without a window; answer connection requests", null);
        }

        protected override void startup () {
            base.startup ();
            Granite.init ();
        }

        protected override int command_line (ApplicationCommandLine cl) {
            var options = cl.get_options_dict ();
            background = options.contains ("background");
            activate_or_hold ();
            return 0;
        }

        private void activate_or_hold () {
            ensure_service ();
            if (!background) {
                present_window ();
            }
        }

        private void ensure_service () {
            if (service != null) return;
            service = new Service ();
            service.consent_requested.connect (on_request);
            service.changed.connect (on_changed);
            service.start ();
            // Keep running for consent prompts even with no window open.
            hold ();
        }

        private void present_window () {
            if (window == null) window = new MainWindow (this, service);
            window.present ();
        }

        private void on_request (PendingRequest request) {
            if (prompt != null) prompt.withdraw ();
            prompt_id = request.id;
            prompt = new ConsentPrompt (request, (window != null && window.visible) ? window : null);
            prompt.answered.connect ((answer) => {
                withdraw_notification ("consent");
                var id = request.id;
                prompt = null;
                prompt_id = null;
                service.decide.begin (id, answer != Answer.DENY, answer == Answer.CONTROL);
            });
            prompt.present ();

            // The notification reaches the person even when the dialog is behind other windows.
            var n = new Notification (_("Allow “%s” to see your screen?").printf (request.device));
            n.set_body (_("Open Remote Desktop to answer. It declines automatically if you don't."));
            n.set_priority (NotificationPriority.URGENT);
            n.set_icon (new ThemedIcon ("preferences-system-sharing"));
            send_notification ("consent", n);
        }

        private void on_changed () {
            // A request that is no longer pending (timed out, cancelled) closes its prompt.
            var p = service.status.pending;
            if (prompt != null && (p == null || p.id != prompt_id)) {
                prompt.withdraw ();
                prompt = null;
                prompt_id = null;
                withdraw_notification ("consent");
            }
        }
    }

    public int main (string[] args) {
        Intl.setlocale ();
        Intl.textdomain ("mseries-remote");
        return new Application ().run (args);
    }
}
