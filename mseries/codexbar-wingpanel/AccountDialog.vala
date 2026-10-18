/* Elementary account onboarding: one native window from browser sign-in to completion. */
namespace MSeries {
    internal class AccountDialog : Granite.MessageDialog {
        public signal void completed ();
        private GLib.Subprocess? process = null;
        private Gtk.Widget sign_in;
        private Gtk.Widget cancel;
        private Gtk.Box progress;
        private string[] command;
        private bool closed = false;

        public AccountDialog (string heading, string detail, string icon, string[] command) {
            GLib.Object (primary_text: heading, secondary_text: detail,
                image_icon: new ThemedIcon (icon), buttons: Gtk.ButtonsType.NONE,
                resizable: false, title: heading);
            this.command = command;
            cancel = add_button ("Cancel", Gtk.ResponseType.CANCEL);
            sign_in = add_button ("Sign in with browser", Gtk.ResponseType.ACCEPT);
            sign_in.add_css_class ("suggested-action");
            progress = new Gtk.Box (Gtk.Orientation.HORIZONTAL, 8) { visible = false };
            progress.append (new Gtk.Spinner () { spinning = true });
            progress.append (new Gtk.Label ("Waiting for browser sign-in…") { xalign = 0 });
            custom_bin.append (progress);
            response.connect ((response) => {
                if (response == Gtk.ResponseType.ACCEPT && process == null) {
                    start.begin ();
                } else if (response != Gtk.ResponseType.ACCEPT) {
                    close ();
                }
            });
            close_request.connect (() => {
                closed = true;
                if (process != null) process.send_signal (15);
                return false;
            });
        }

        private async void start () {
            sign_in.set_sensitive (false);
            progress.visible = true;
            secondary_text = "Choose the account you want to add in your browser. If it opens the current account, choose another account there.";
            var ok = false;
            string output = "";
            try {
                process = new GLib.Subprocess.newv (command, SubprocessFlags.STDOUT_PIPE | SubprocessFlags.STDERR_MERGE);
                yield process.communicate_utf8_async (null, null, out output, null);
                ok = process.get_successful ();
            } catch (Error e) {
                output = "Sign-in could not start. Please try again.";
            }
            process = null;
            if (closed) return;
            progress.visible = false;
            primary_text = ok ? "Account added" : "Couldn't add account";
            secondary_text = output.strip ().length > 0 ? output.strip () : "Sign-in did not finish. Please try again.";
            sign_in.visible = !ok;
            sign_in.sensitive = true;
            ((Gtk.Button) cancel).label = "Close";
            if (ok) completed ();
        }
    }
}
