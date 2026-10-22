/* SPDX-License-Identifier: GPL-3.0-or-later */
/* Stand-alone host for the Dock & Taskbar page, for development and screenshots.
 * Not installed. It uses the real dock settings unless MSERIES_DOCK_SCHEMA_DIR
 * points at a fixture schema directory (with GSETTINGS_BACKEND=memory). */
namespace MSeriesDockSwitcher {
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

    public class Preview : Adw.Application {
        private string? shot = null;
        private int win_w = 760;
        private int win_h = 700;
        private double text_scale = 1.0;
        private bool force_dark = false;
        private bool force_light = false;
        private string? pick = null;
        private int shot_delay = 2200;

        public Preview () {
            Object (application_id: "io.elementary.mseries.dock-switcher-preview",
                    flags: GLib.ApplicationFlags.NON_UNIQUE | GLib.ApplicationFlags.HANDLES_COMMAND_LINE);
            add_main_option ("screenshot", 0, 0, GLib.OptionArg.FILENAME, "Save the window to FILE", "FILE");
            add_main_option ("size", 0, 0, GLib.OptionArg.STRING, "Window size, WIDTHxHEIGHT", "WxH");
            add_main_option ("text-scale", 0, 0, GLib.OptionArg.DOUBLE, "Scale text like the system text size setting", "N");
            add_main_option ("pick", 0, 0, GLib.OptionArg.STRING, "Choose a style after loading: taskbar or dock", "STYLE");
            add_main_option ("delay", 0, 0, GLib.OptionArg.INT, "Milliseconds before the screenshot is taken", "MS");
            add_main_option ("dark", 0, 0, GLib.OptionArg.NONE, "Force the dark style", null);
            add_main_option ("light", 0, 0, GLib.OptionArg.NONE, "Force the light style", null);
        }

        protected override int handle_local_options (GLib.VariantDict options) {
            string? s;
            if (options.lookup ("screenshot", "^ay", out s)) {
                shot = s;
            }
            if (options.lookup ("size", "s", out s)) {
                var parts = s.split ("x");
                if (parts.length == 2) {
                    win_w = int.parse (parts[0]);
                    win_h = int.parse (parts[1]);
                }
            }
            double d;
            if (options.lookup ("text-scale", "d", out d)) {
                text_scale = d;
            }
            if (options.lookup ("pick", "s", out s)) {
                pick = s;
            }
            int ms;
            if (options.lookup ("delay", "i", out ms)) {
                shot_delay = ms;
            }
            force_dark = options.contains ("dark");
            force_light = options.contains ("light");
            return -1;
        }

        protected override int command_line (GLib.ApplicationCommandLine command_line) {
            activate ();
            return 0;
        }

        protected override void activate () {
            if (force_dark) {
                Adw.StyleManager.get_default ().color_scheme = Adw.ColorScheme.FORCE_DARK;
            } else if (force_light) {
                Adw.StyleManager.get_default ().color_scheme = Adw.ColorScheme.FORCE_LIGHT;
            }
            if (text_scale != 1.0) {
                Gtk.Settings.get_default ().gtk_xft_dpi = (int) (96 * 1024 * text_scale);
            }
            var page = new DockPage ();
            var window = new Adw.Window () { default_width = win_w, default_height = win_h, title = "Dock & Taskbar" };
            var view = new Adw.ToolbarView ();
            view.add_top_bar (new Adw.HeaderBar ());
            view.content = page;
            window.content = view;
            window.application = this;
            window.present ();
            page.refresh ();

            if (pick != null) {
                GLib.Timeout.add (250, () => {
                    page.choose (pick == "taskbar" ? Style.TASKBAR : Style.DOCK);
                    return false;
                });
            }
            if (shot != null) {
                GLib.Timeout.add (shot_delay, () => {
                    if (!save_png (window, shot)) {
                        stderr.printf ("could not save %s\n", shot);
                    }
                    window.close ();
                    return false;
                });
            }
        }
    }
}

int main (string[] args) {
    return new MSeriesDockSwitcher.Preview ().run (args);
}
