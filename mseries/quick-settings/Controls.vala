/* SPDX-License-Identifier: GPL-3.0-or-later
 * Shared building blocks for the top-right Quick Settings menu: the stylesheet, the rounded Card
 * that groups related rows, the common SliderRow (icon, slider, percentage) that Volume, Screen
 * Brightness and Keyboard Brightness are built on, and the Volume slider itself. Colours come
 * from the theme's own tokens, so light, dark and accent changes follow the system. */
namespace QuickSettings {
    public class Style : Object {
        private static bool loaded = false;

        public static void ensure () {
            if (loaded || Gdk.Display.get_default () == null) {
                return;
            }
            loaded = true;
            var css = new Gtk.CssProvider ();
            css.load_from_string (
                "quicksettings .mseries-card {" +
                " background: alpha(@text_color, 0.06);" +
                " border-radius: 9px;" +
                " box-shadow: inset 0 0 0 1px alpha(@text_color, 0.08);" +
                " margin: 0 0.666rem 0.666rem;" +
                " padding: 0.333rem 0; }" +
                "quicksettings .mseries-card scalebox { padding: 0.333rem 0.75rem; }" +
                "quicksettings .mseries-card scalebox scale { margin: 0; }" +
                "quicksettings .mseries-card scale trough { min-height: 6px; border-radius: 3px; }" +
                "quicksettings .mseries-card scale highlight { border-radius: 3px; }" +
                "quicksettings .mseries-card scale slider { min-width: 16px; min-height: 16px; }" +
                "quicksettings .mseries-slider-icon {" +
                " min-width: 28px; min-height: 28px; padding: 0; border-radius: 999px;" +
                " background: alpha(@text_color, 0.10); box-shadow: none; }" +
                "quicksettings button.mseries-slider-icon:hover { background: alpha(@text_color, 0.18); }" +
                "quicksettings .mseries-slider-icon.muted { background: alpha(@text_color, 0.04); color: alpha(@text_color, 0.5); }" +
                "quicksettings .mseries-slider-value { font-feature-settings: \"tnum\"; min-width: 3.2em; }" +
                "quicksettings .mseries-card button.flat { border-radius: 6px; margin: 0 0.333rem; }"
            );
            Gtk.StyleContext.add_provider_for_display (
                Gdk.Display.get_default (), css, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
            );
        }
    }

    /* A rounded group of rows. It hides itself when every row in it is hidden, so devices a
     * machine does not have (no keyboard backlight, no charge limit) never leave an empty box. */
    public class Card : Gtk.Box {
        construct {
            orientation = VERTICAL;
            spacing = 0;
            visible = false;
            Style.ensure ();
            add_css_class ("mseries-card");
        }

        public void add_row (Gtk.Widget row) {
            append (row);
            row.notify["visible"].connect (update_visibility);
            update_visibility ();
        }

        private void update_visibility () {
            for (var child = get_first_child (); child != null; child = child.get_next_sibling ()) {
                if (child.visible) {
                    visible = true;
                    return;
                }
            }
            visible = false;
        }
    }

    /* Icon, slider and percentage on one line. Subclasses supply write () and keep the slider in
     * step with the system through show_value (). Drags are coalesced: the newest value is written
     * after 100 ms of quiet, and only one write is in flight at a time. */
    public abstract class SliderRow : Gtk.Box {
        public string title { get; construct; }
        public bool clickable { get; construct; default = false; }

        protected Gtk.Scale slider;
        private Gtk.Image icon_image;
        private Gtk.Widget icon_widget;
        private Gtk.Label percentage;
        private bool updating = false;
        private bool writing = false;
        private uint timeout_id = 0;
        private double requested = 0;

        // True while the user is moving the slider or a write is in flight; refreshes must wait.
        protected bool busy {
            get { return writing || timeout_id != 0; }
        }

        class construct {
            set_css_name ("scalebox");
        }

        construct {
            orientation = HORIZONTAL;
            spacing = 9;

            icon_image = new Gtk.Image.from_icon_name (icon_for (0, false));
            if (clickable) {
                var button = new Gtk.Button () { child = icon_image, valign = CENTER, tooltip_text = title };
                button.clicked.connect (() => { icon_activated (); });
                button.update_property_value ({ Gtk.AccessibleProperty.LABEL }, { title });
                icon_widget = button;
            } else {
                icon_widget = new Gtk.CenterBox () { center_widget = icon_image, valign = CENTER };
            }
            icon_widget.add_css_class ("mseries-slider-icon");

            slider = new Gtk.Scale.with_range (HORIZONTAL, 0, 100, 1) {
                hexpand = true,
                draw_value = false,
                valign = CENTER,
                tooltip_text = title
            };
            slider.adjustment.page_increment = 10;
            slider.update_property_value ({ Gtk.AccessibleProperty.LABEL }, { title });

            percentage = new Gtk.Label ("") { xalign = 1, valign = CENTER };
            percentage.add_css_class (Granite.CssClass.DIM);
            percentage.add_css_class ("mseries-slider-value");

            append (icon_widget);
            append (slider);
            append (percentage);

            slider.value_changed.connect (on_value_changed);
        }

        public override void dispose () {
            if (timeout_id != 0) {
                Source.remove (timeout_id);
                timeout_id = 0;
            }
            base.dispose ();
        }

        protected abstract string icon_for (double value, bool dimmed);

        protected abstract async void write (double value) throws Error;

        protected virtual void icon_activated () {}

        protected virtual void wrote () {}

        // Moves the slider to a value read from the system without sending it back.
        protected void show_value (double value, bool dimmed = false) {
            updating = true;
            slider.set_value (value);
            updating = false;
            update_display (dimmed);
        }

        protected void update_display (bool dimmed = false) {
            var value = slider.get_value ();
            percentage.label = "%.0f%%".printf (value);
            icon_image.icon_name = icon_for (value, dimmed);
            if (dimmed) {
                icon_widget.add_css_class ("muted");
            } else {
                icon_widget.remove_css_class ("muted");
            }
        }

        private void on_value_changed () {
            update_display (false);
            if (updating) {
                return;
            }
            requested = slider.get_value ();
            if (timeout_id != 0) {
                Source.remove (timeout_id);
            }
            timeout_id = Timeout.add (100, () => {
                timeout_id = 0;
                if (!writing) {
                    flush.begin ();
                }
                return Source.REMOVE;
            });
        }

        private async void flush () {
            writing = true;
            double target = requested;
            do {
                target = requested;
                try {
                    yield write (target);
                } catch (Error e) {
                    warning ("Could not set %s: %s", title, e.message);
                    break;
                }
            } while (target != requested);
            writing = false;
            wrote ();
        }
    }

    /* Volume of the default output, through WirePlumber. Clicking the icon mutes; moving the
     * slider while muted unmutes. Follows changes made elsewhere (keys, apps) while the menu is
     * open, and the output chosen in Sound Output below. */
    public class Volume : SliderRow {
        private const string SINK = "@DEFAULT_AUDIO_SINK@";
        private bool muted = false;
        private bool refreshing = false;
        private uint poll_id = 0;

        public Volume () {
            Object (title: _("Volume"), clickable: true);
        }

        construct {
            map.connect (() => {
                refresh.begin ();
                poll_id = Timeout.add (1500, () => {
                    refresh.begin ();
                    return Source.CONTINUE;
                });
            });
            unmap.connect (stop_polling);
        }

        public override void dispose () {
            stop_polling ();
            base.dispose ();
        }

        private void stop_polling () {
            if (poll_id != 0) {
                Source.remove (poll_id);
                poll_id = 0;
            }
        }

        protected override string icon_for (double value, bool dimmed) {
            if (dimmed || value <= 0) {
                return "audio-volume-muted-symbolic";
            }
            if (value < 34) {
                return "audio-volume-low-symbolic";
            }
            return value < 67 ? "audio-volume-medium-symbolic" : "audio-volume-high-symbolic";
        }

        private static async string run (string[] args) throws Error {
            string[] argv = { "wpctl" };
            foreach (var arg in args) {
                argv += arg;
            }
            var process = new Subprocess.newv (argv, SubprocessFlags.STDOUT_PIPE | SubprocessFlags.STDERR_SILENCE);
            string? text;
            yield process.communicate_utf8_async (null, null, out text, null);
            if (!process.get_successful ()) {
                throw new IOError.FAILED ("wpctl %s failed", args[0]);
            }
            return text ?? "";
        }

        private async void refresh () {
            if (refreshing || busy) {
                return;
            }
            refreshing = true;
            try {
                // "Volume: 0.45" or "Volume: 0.45 [MUTED]"
                var text = yield run ({ "get-volume", SINK });
                var parts = text.strip ().split (" ");
                if (parts.length < 2 || parts[0] != "Volume:") {
                    throw new IOError.FAILED ("unexpected wpctl output");
                }
                muted = text.contains ("[MUTED]");
                if (!busy) {
                    show_value (Math.round (double.parse (parts[1]) * 100).clamp (0, 100), muted);
                }
                visible = true;
            } catch (Error e) {
                info ("Volume unavailable: %s", e.message);
                visible = false;
            }
            refreshing = false;
        }

        protected override void icon_activated () {
            toggle_mute.begin ();
        }

        private async void toggle_mute () {
            try {
                yield run ({ "set-mute", SINK, "toggle" });
            } catch (Error e) {
                warning ("Could not change mute: %s", e.message);
            }
            refresh.begin ();
        }

        protected override async void write (double value) throws Error {
            if (muted) {
                yield run ({ "set-mute", SINK, "0" });
                muted = false;
            }
            // A percentage string avoids locale-dependent decimal separators.
            yield run ({ "set-volume", "-l", "1.0", SINK, "%d%%".printf ((int) Math.round (value)) });
        }

        protected override void wrote () {
            update_display (muted);
            refresh.begin ();
        }
    }
}
