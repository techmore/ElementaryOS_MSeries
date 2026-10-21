/* Stand-alone host for the Touch ID page, for development and screenshots.
 * Not installed. With MSERIES_TOUCHID_TEST=1 it talks to a fake fprintd on the
 * session bus; otherwise it shows the real page against the real sensor. */
namespace MSeriesTouchId {
    private bool save_png (Gtk.Widget widget, string path) {
        var paintable = new Gtk.WidgetPaintable (widget);
        var snapshot = new Gtk.Snapshot ();
        paintable.snapshot (snapshot, widget.get_width (), widget.get_height ());
        var node = snapshot.to_node ();
        var native = widget.get_native ();
        if (node == null || native == null) {
            return false;
        }
        var texture = native.get_renderer ().render_texture (node, null);
        return texture.save_to_png (path);
    }

    private Adw.SwitchRow? find_switch (Gtk.Widget widget, string title) {
        var row = widget as Adw.SwitchRow;
        if (row != null && row.title == title) {
            return row;
        }
        for (var kid = widget.get_first_child (); kid != null; kid = kid.get_next_sibling ()) {
            var found = find_switch (kid, title);
            if (found != null) {
                return found;
            }
        }
        return null;
    }

    public class Preview : Adw.Application {
        private string? flip = null;
        private string? shot = null;
        private string? dialog_shot = null;
        private bool dark = false;
        private bool force_scheme = false;

        public Preview () {
            Object (application_id: "io.elementary.mseries.touchid-preview",
                    flags: GLib.ApplicationFlags.NON_UNIQUE | GLib.ApplicationFlags.HANDLES_COMMAND_LINE);
            add_main_option ("screenshot", 0, 0, GLib.OptionArg.FILENAME, "Save the window to FILE", "FILE");
            add_main_option ("dialog-screenshot", 0, 0, GLib.OptionArg.FILENAME, "Open Add Fingerprint and save it to FILE", "FILE");
            add_main_option ("flip", 0, 0, GLib.OptionArg.STRING, "Turn on the switch with this title after loading", "TITLE");
            add_main_option ("dark", 0, 0, GLib.OptionArg.NONE, "Force the dark style", null);
            add_main_option ("light", 0, 0, GLib.OptionArg.NONE, "Force the light style", null);
        }

        protected override int handle_local_options (GLib.VariantDict options) {
            string? s;
            if (options.lookup ("screenshot", "^ay", out s)) {
                shot = s;
            }
            if (options.lookup ("dialog-screenshot", "^ay", out s)) {
                dialog_shot = s;
            }
            if (options.lookup ("flip", "s", out s)) {
                flip = s;
            }
            if (options.contains ("dark")) {
                dark = true;
                force_scheme = true;
            }
            if (options.contains ("light")) {
                force_scheme = true;
            }
            return -1;
        }

        protected override int command_line (GLib.ApplicationCommandLine cl) {
            activate ();
            return 0;
        }

        protected override void activate () {
            if (force_scheme) {
                Adw.StyleManager.get_default ().color_scheme =
                    dark ? Adw.ColorScheme.FORCE_DARK : Adw.ColorScheme.FORCE_LIGHT;
            }
            var page = new TouchIdPage ();
            var window = new Gtk.ApplicationWindow (this) {
                title = "Touch ID",
                default_width = 760,
                default_height = 640,
                child = page
            };
            window.present ();
            page.refresh.begin ();

            if (flip != null) {
                GLib.Timeout.add (1200, () => {
                    var row = find_switch (window, flip);
                    if (row != null) {
                        row.active = true;
                    } else {
                        GLib.stderr.printf ("no switch titled %s\n", flip);
                    }
                    return false;
                });
            }

            if (dialog_shot != null) {
                GLib.Timeout.add (1500, () => {
                    page.open_add_for_preview ();
                    return false;
                });
                GLib.Timeout.add (4500, () => {
                    var dialog = page.active_dialog;
                    if (dialog != null) {
                        save_png (dialog, dialog_shot);
                        dialog.close ();   /* exercises Cancel: EnrollStop then Release */
                    }
                    GLib.Timeout.add (900, () => {
                        quit ();
                        return false;
                    });
                    return false;
                });
            } else if (shot != null) {
                GLib.Timeout.add (2500, () => {
                    save_png (window, shot);
                    quit ();
                    return false;
                });
            }
        }
    }
}

int main (string[] args) {
    return new MSeriesTouchId.Preview ().run (args);
}
