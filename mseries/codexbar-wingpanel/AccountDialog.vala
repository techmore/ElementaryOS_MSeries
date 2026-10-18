/* Native account sheet shared by provider onboarding. Authentication stays in the helpers. */
namespace MSeries {
    internal class AccountDialog : Granite.Dialog {
        public signal void completed ();
        public signal void confirmed ();
        private GLib.Subprocess? process = null;
        private Gtk.Button sign_in;
        private Gtk.Button cancel;
        private Gtk.Box progress;
        private Gtk.Box steps;
        private Gtk.Label heading_label;
        private Gtk.Label detail_label;
        private Gtk.Label note;
        private Gtk.Image mark;
        private Gtk.Box emblem;
        private string[] command;
        private bool closed = false;
        private bool confirmation_only = false;

        public AccountDialog (string heading, string detail, string icon, string[] command,
                              string provider = "codex", string action_label = "Sign in with browser") {
            GLib.Object (resizable: false, title: heading, default_width: 440);
            this.command = command;
            add_css_class ("cb-account-dialog");
            var css = new Gtk.CssProvider ();
            css.load_from_string (
                ".cb-account-dialog .account-emblem { background: linear-gradient(to bottom, @theme_base_color, @theme_bg_color); border: 1px solid alpha(currentColor, 0.12); border-radius: 22px; box-shadow: 0 3px 6px alpha(black, 0.08), inset 0 1px alpha(white, 0.5); padding: 20px; margin: 4px 0 8px; } " +
                ".cb-account-dialog .account-emblem.claude { color: #c16b49; } " +
                ".cb-account-dialog .account-heading { font-size: 1.65em; font-weight: 700; letter-spacing: -0.4px; } " +
                ".cb-account-dialog .account-steps { background: @theme_base_color; border: 1px solid alpha(currentColor, 0.14); border-radius: 9px; box-shadow: 0 1px 2px alpha(black, 0.04); } " +
                ".cb-account-dialog .account-step { padding: 14px 16px; } " +
                ".cb-account-dialog .account-step-icon { color: @accent_color; background: alpha(@accent_color, 0.09); border-radius: 50%; padding: 9px; } " +
                ".cb-account-dialog .account-step-title { font-weight: 600; } " +
                ".cb-account-dialog .account-caption { font-size: 0.92em; } " +
                ".cb-account-dialog .account-note { font-size: 0.85em; } " +
                ".cb-account-dialog .account-success { color: @success_color; } " +
                ".cb-account-dialog .account-error { color: @error_color; }");
            Gtk.StyleContext.add_provider_for_display (get_display (), css, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION);
            var body = new Gtk.Box (Gtk.Orientation.VERTICAL, 12) {
                margin_top = 24, margin_bottom = 18, margin_start = 30, margin_end = 30
            };
            get_content_area ().append (body);
            emblem = new Gtk.Box (Gtk.Orientation.VERTICAL, 0) { halign = Gtk.Align.CENTER };
            emblem.add_css_class ("account-emblem");
            emblem.add_css_class (provider);
            mark = new Gtk.Image.from_icon_name (icon) { pixel_size = 40 };
            emblem.append (mark);
            body.append (emblem);
            heading_label = new Gtk.Label (heading) { justify = Gtk.Justification.CENTER, wrap = true };
            heading_label.add_css_class ("account-heading");
            body.append (heading_label);
            detail_label = new Gtk.Label (detail) {
                wrap = true, justify = Gtk.Justification.CENTER, max_width_chars = 40
            };
            detail_label.add_css_class ("dim-label");
            body.append (detail_label);
            steps = new Gtk.Box (Gtk.Orientation.VERTICAL, 0) { margin_top = 12, margin_bottom = 4 };
            steps.add_css_class ("account-steps");
            if (provider == "opencode") {
                steps.append (step ("web-browser-symbolic", "Sign in to OpenCode", "Use your browser, including passkeys."));
                steps.append (new Gtk.Separator (Gtk.Orientation.HORIZONTAL));
                steps.append (step ("dialog-password-symbolic", "Connect with an API key", "Copy a key from the console. We'll check it before saving."));
            } else {
                steps.append (step ("web-browser-symbolic", "Choose your account", "Sign in securely in your browser."));
                steps.append (new Gtk.Separator (Gtk.Orientation.HORIZONTAL));
                steps.append (step ("system-switch-user-symbolic", "Keep your accounts together", "See remaining usage and switch from the panel."));
            }
            body.append (steps);
            note = new Gtk.Label (provider == "codex" ? "Your current Codex sign-in stays active."
                : provider == "claude" ? "Your current Claude Code account is saved first."
                : "Your API key is saved on this computer.") {
                wrap = true, justify = Gtk.Justification.CENTER, max_width_chars = 44, margin_top = 4
            };
            note.add_css_class ("dim-label");
            note.add_css_class ("account-note");
            body.append (note);
            cancel = (Gtk.Button) add_button ("Cancel", Gtk.ResponseType.CANCEL);
            sign_in = (Gtk.Button) add_button (action_label, Gtk.ResponseType.ACCEPT);
            sign_in.add_css_class ("suggested-action");
            set_default_response (Gtk.ResponseType.ACCEPT);
            progress = new Gtk.Box (Gtk.Orientation.HORIZONTAL, 8) {
                visible = false, halign = Gtk.Align.CENTER, margin_top = 16, margin_bottom = 16
            };
            progress.append (new Gtk.Spinner () { spinning = true });
            progress.append (new Gtk.Label ("Waiting for browser sign-in…"));
            body.append (progress);
            response.connect ((response) => {
                if (response == Gtk.ResponseType.ACCEPT && process == null) {
                    if (confirmation_only) {
                        close ();
                        confirmed ();
                    } else start.begin ();
                } else if (response != Gtk.ResponseType.ACCEPT) close ();
            });
            close_request.connect (() => {
                closed = true;
                if (process != null) process.send_signal (15);
                return false;
            });
        }

        public AccountDialog.prompt (string heading, string detail, string icon,
                                     string provider, string action_label) {
            this (heading, detail, icon, {}, provider, action_label);
            confirmation_only = true;
        }

        private static Gtk.Widget step (string icon, string heading, string detail) {
            var row = new Gtk.Box (Gtk.Orientation.HORIZONTAL, 12);
            row.add_css_class ("account-step");
            var image = new Gtk.Image.from_icon_name (icon) { pixel_size = 18, valign = Gtk.Align.CENTER };
            image.add_css_class ("account-step-icon");
            row.append (image);
            var copy = new Gtk.Box (Gtk.Orientation.VERTICAL, 3) { hexpand = true };
            var title = new Gtk.Label (heading) { xalign = 0 };
            title.add_css_class ("account-step-title");
            copy.append (title);
            var caption = new Gtk.Label (detail) { xalign = 0, wrap = true, max_width_chars = 32 };
            caption.add_css_class ("dim-label");
            caption.add_css_class ("account-caption");
            copy.append (caption);
            row.append (copy);
            return row;
        }

        private async void start () {
            sign_in.sensitive = false;
            steps.visible = false;
            note.visible = true;
            note.label = "You can leave this window open while you sign in.";
            progress.visible = true;
            emblem.remove_css_class ("account-error");
            mark.icon_name = "web-browser-symbolic";
            heading_label.label = "Finish in your browser";
            detail_label.label = "Choose the account you'd like to add to CodexBar.";
            cancel.label = "Cancel";
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
            heading_label.label = ok ? "You're all set" : "Let's try that again";
            detail_label.label = ok ? "Your account is ready in CodexBar."
                : "We couldn't finish adding your account.";
            mark.icon_name = ok ? "emblem-default-symbolic" : "dialog-warning-symbolic";
            emblem.add_css_class (ok ? "account-success" : "account-error");
            // Keep helper detail selectable and bounded so a long error never stretches the sheet.
            note.label = output.strip ().length > 0 ? output.strip ()
                : ok ? "Choose it from Accounts whenever you're ready." : "Please try signing in again.";
            note.selectable = true;
            note.lines = 4;
            note.ellipsize = Pango.EllipsizeMode.END;
            note.tooltip_text = note.label;
            sign_in.visible = !ok;
            sign_in.label = "Try Again";
            sign_in.sensitive = true;
            cancel.label = "Close";
            set_default_response (ok ? Gtk.ResponseType.CANCEL : Gtk.ResponseType.ACCEPT);
            if (ok) {
                cancel.add_css_class ("suggested-action");
                cancel.grab_focus ();
                completed ();
            } else sign_in.grab_focus ();
        }
    }
}
