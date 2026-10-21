/* SPDX-License-Identifier: GPL-3.0-or-later */
/* A small drawn desktop for each style: a wallpaper, a window, and either a
 * full-width taskbar (Start, centred apps, tray, clock) or a floating dock.
 * Drawn with Cairo so it follows light/dark and the accent colour, and needs no
 * image assets. */
namespace MSeriesDockSwitcher {
    public class Illustration : Gtk.DrawingArea {
        public Style style { get; construct; }

        public Illustration (Style style) {
            Object (style: style);
        }

        construct {
            add_css_class ("msd-preview");
            set_content_width (236);
            set_content_height (132);
            set_draw_func (draw);
            var manager = Adw.StyleManager.get_default ();
            manager.notify["dark"].connect (queue_draw);
            manager.notify["accent-color"].connect (queue_draw);
            update_property (Gtk.AccessibleProperty.LABEL,
                style == Style.TASKBAR
                    ? "Illustration of a full-width taskbar along the bottom of the screen"
                    : "Illustration of a floating dock centred above the bottom of the screen",
                -1);
        }

        private static void rounded (Cairo.Context cr, double x, double y, double w, double h, double r) {
            r = double.min (r, double.min (w, h) / 2);
            cr.new_sub_path ();
            cr.arc (x + w - r, y + r, r, -Math.PI / 2, 0);
            cr.arc (x + w - r, y + h - r, r, 0, Math.PI / 2);
            cr.arc (x + r, y + h - r, r, Math.PI / 2, Math.PI);
            cr.arc (x + r, y + r, r, Math.PI, 3 * Math.PI / 2);
            cr.close_path ();
        }

        private void draw (Gtk.DrawingArea area, Cairo.Context cr, int width, int height) {
            var dark = Adw.StyleManager.get_default ().dark;
            var accent = Adw.StyleManager.get_default ().accent_color.to_rgba ();
            double w = width, h = height;

            /* Wallpaper, clipped to the rounded frame. */
            rounded (cr, 0, 0, w, h, 12);
            cr.clip ();
            var wall = new Cairo.Pattern.linear (0, 0, w, h);
            if (dark) {
                wall.add_color_stop_rgb (0, 0.10, 0.14, 0.27);
                wall.add_color_stop_rgb (1, 0.20, 0.17, 0.38);
            } else {
                wall.add_color_stop_rgb (0, 0.58, 0.74, 0.95);
                wall.add_color_stop_rgb (1, 0.86, 0.80, 0.96);
            }
            cr.set_source (wall);
            cr.paint ();

            /* A window, so it's clear what sits above the bar. */
            var bar_h = style == Style.TASKBAR ? 22.0 : 0.0;
            var win_x = w * 0.18;
            var win_w = w * 0.64;
            var win_y = 14.0;
            var win_h = h - win_y - (style == Style.TASKBAR ? bar_h + 8 : 46);
            rounded (cr, win_x, win_y, win_w, win_h, 7);
            cr.set_source_rgba (dark ? 0.16 : 1.0, dark ? 0.16 : 1.0, dark ? 0.19 : 1.0, 0.94);
            cr.fill ();
            cr.set_source_rgba (0, 0, 0, dark ? 0.35 : 0.10);
            cr.rectangle (win_x, win_y + 10, win_w, 1);
            cr.fill ();
            for (var i = 0; i < 3; i++) {
                cr.arc (win_x + 8 + i * 8, win_y + 5, 2.1, 0, 2 * Math.PI);
                cr.set_source_rgba (0.5, 0.5, 0.55, 0.7);
                cr.fill ();
            }
            for (var line = 0; line < 3; line++) {
                rounded (cr, win_x + 10, win_y + 20 + line * 10, win_w * (0.7 - line * 0.14), 4, 2);
                cr.set_source_rgba (0.5, 0.5, 0.58, dark ? 0.45 : 0.35);
                cr.fill ();
            }

            double[,] hues = { { 0.25, 0.52, 0.96 }, { 0.98, 0.60, 0.20 }, { 0.30, 0.74, 0.42 },
                               { 0.62, 0.40, 0.86 }, { 0.92, 0.36, 0.36 } };

            if (style == Style.TASKBAR) {
                /* Full-width bar flush to the bottom edge. */
                cr.rectangle (0, h - bar_h, w, bar_h);
                cr.set_source_rgba (dark ? 0.10 : 0.97, dark ? 0.10 : 0.97, dark ? 0.13 : 0.99, 0.94);
                cr.fill ();
                cr.rectangle (0, h - bar_h, w, 1);
                cr.set_source_rgba (0, 0, 0, dark ? 0.5 : 0.12);
                cr.fill ();
                /* Start button, four small squares. */
                var sx = w / 2 - 5 * 7.5 - 12;
                for (var q = 0; q < 4; q++) {
                    cr.rectangle (sx + (q % 2) * 6, h - bar_h + 6 + (q / 2) * 6, 5, 5);
                    cr.set_source_rgba (accent.red, accent.green, accent.blue, 1.0);
                    cr.fill ();
                }
                /* Centred apps. */
                for (var a = 0; a < 5; a++) {
                    rounded (cr, w / 2 - 5 * 7.5 + a * 15, h - bar_h + 5, 12, 12, 3);
                    cr.set_source_rgb (hues[a, 0], hues[a, 1], hues[a, 2]);
                    cr.fill ();
                }
                /* Running marker under the first app. */
                rounded (cr, w / 2 - 5 * 7.5 + 3, h - 3.5, 6, 2, 1);
                cr.set_source_rgba (accent.red, accent.green, accent.blue, 1.0);
                cr.fill ();
                /* Tray and clock on the right. */
                for (var t = 0; t < 3; t++) {
                    cr.arc (w - 62 + t * 9, h - bar_h / 2, 2.4, 0, 2 * Math.PI);
                    cr.set_source_rgba (0.5, 0.5, 0.55, 0.85);
                    cr.fill ();
                }
                rounded (cr, w - 32, h - bar_h / 2 - 3, 24, 6, 3);
                cr.set_source_rgba (0.5, 0.5, 0.55, 0.85);
                cr.fill ();
            } else {
                /* Floating, rounded dock centred above the bottom edge. */
                var dw = 5 * 22.0 + 14;
                var dh = 32.0;
                var dx = (w - dw) / 2;
                var dy = h - dh - 8;
                rounded (cr, dx, dy, dw, dh, 12);
                cr.set_source_rgba (dark ? 0.10 : 1.0, dark ? 0.10 : 1.0, dark ? 0.13 : 1.0, dark ? 0.78 : 0.62);
                cr.fill_preserve ();
                cr.set_source_rgba (1, 1, 1, dark ? 0.12 : 0.55);
                cr.set_line_width (1);
                cr.stroke ();
                for (var a = 0; a < 5; a++) {
                    rounded (cr, dx + 7 + a * 22, dy + 6, 18, 18, 5);
                    cr.set_source_rgb (hues[a, 0], hues[a, 1], hues[a, 2]);
                    cr.fill ();
                }
                cr.arc (dx + 16, dy + dh - 3, 1.6, 0, 2 * Math.PI);
                cr.set_source_rgba (0.5, 0.5, 0.55, 0.9);
                cr.fill ();
            }
        }
    }
}
