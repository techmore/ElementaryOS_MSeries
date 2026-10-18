/* Elementary account onboarding: one native window from browser sign-in to completion. */
namespace MSeries {
    internal class AccountDialog : Granite.Dialog {
        public signal void completed ();
        private GLib.Subprocess? process = null;
        private Gtk.Widget sign_in;
        private Gtk.Widget cancel;
        private Gtk.Box progress;
        private Gtk.Box steps;
        private Gtk.Label heading_label;
        private Gtk.Label detail_label;
        private Gtk.Image mark;
        private string[] command;
        private bool closed = false;

        public AccountDialog (string heading, string detail, string icon, string[] command) {
            GLib.Object (resizable: false, title: heading, default_width: 420);
            this.command = command;
            add_css_class ("cb-account-dialog");
            var css = new Gtk.CssProvider ();
            css.load_from_string (
                ".cb-account-dialog .account-mark { background: alpha(currentColor, 0.05); border-radius: 20px; padding: 18px; } " +
                ".cb-account-dialog .account-heading { font-size: 1.45em; font-weight: 700; } " +
                ".cb-account-dialog .account-steps { background: alpha(currentColor, 0.04); border-radius: 10px; padding: 14px; } " +
                ".cb-account-dialog .account-caption { font-size: 0.85em; opacity: 0.7; } " +
                ".cb-account-dialog .account-success { color: @success_color; }");
            Gtk.StyleContext.add_provider_for_display (get_display (), css, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION);
            var body = new Gtk.Box (Gtk.Orientation.VERTICAL, 14) {
                margin_top = 20, margin_bottom = 20, margin_start = 24, margin_end = 24
            };
            get_content_area ().append (body);
            mark = new Gtk.Image.from_icon_name (icon) { pixel_size = 38, halign = Gtk.Align.CENTER };
            mark.add_css_class ("account-mark");
            body.append (mark);
            heading_label = new Gtk.Label (heading) { justify = Gtk.Justification.CENTER, wrap = true };
            heading_label.add_css_class ("account-heading");
            body.append (heading_label);
            detail_label = new Gtk.Label (detail) { wrap = true, justify = Gtk.Justification.CENTER, max_width_chars = 42 };
            detail_label.add_css_class ("dim-label");
            body.append (detail_label);
            steps = new Gtk.Box (Gtk.Orientation.VERTICAL, 14);
            steps.add_css_class ("account-steps");
            steps.append (step ("web-browser-symbolic", "Use your browser", "Choose the account you want to add."));
            steps.append (step ("avatar-default-symbolic", "Keep your current account", "Switch accounts whenever you're ready."));
            body.append (steps);
            cancel = add_button ("Cancel", Gtk.ResponseType.CANCEL);
            sign_in = add_button ("Sign in with browser", Gtk.ResponseType.ACCEPT);
            sign_in.add_css_class ("suggested-action");
            progress = new Gtk.Box (Gtk.Orientation.HORIZONTAL, 8) { visible = false, halign = Gtk.Align.CENTER };
            progress.append (new Gtk.Spinner () { spinning = true });
            progress.append (new Gtk.Label ("Waiting for browser sign-in…"));
            body.append (progress);
            response.connect ((response) => {
                if (response == Gtk.ResponseType.ACCEPT && process == null) start.begin ();
                else if (response != Gtk.ResponseType.ACCEPT) close ();
            });
            close_request.connect (() => {
                closed = true;
                if (process != null) process.send_signal (15);
                return false;
            });
        }

        private static Gtk.Widget step (string icon, string heading, string detail) {
            var row = new Gtk.Box (Gtk.Orientation.HORIZONTAL, 12);
            row.append (new Gtk.Image.from_icon_name (icon) { pixel_size = 20 });
            var copy = new Gtk.Box (Gtk.Orientation.VERTICAL, 2);
            copy.append (new Gtk.Label (heading) { xalign = 0 });
            var caption = new Gtk.Label (detail) { xalign = 0, wrap = true, max_width_chars = 38 };
            caption.add_css_class ("account-caption");
            copy.append (caption);
            row.append (copy);
            return row;
        }

        private async void start () {
            sign_in.set_sensitive (false);
            steps.visible = false;
            progress.visible = true;
            heading_label.label = "Finish signing in";
            detail_label.label = "Choose the other account in your browser. You can leave this window open while you sign in.";
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
            heading_label.label = ok ? "Account added" : "Couldn't add account";
            detail_label.label = output.strip ().length > 0 ? output.strip () : "Sign-in did not finish. Please try again.";
            if (ok) {
                mark.icon_name = "emblem-default-symbolic";
                mark.add_css_class ("account-success");
            }
            sign_in.visible = !ok;
            sign_in.sensitive = true;
            ((Gtk.Button) cancel).label = "Close";
            if (ok) completed ();
        }
    }
}
