/* SPDX-License-Identifier: GPL-3.0-or-later */
/* A fingerprint drawn as concentric ridges that fill with the accent colour as
 * enrolment progresses, the way the macOS Touch ID sheet does. */
namespace MSeriesTouchId {
    public class FingerprintArt : Gtk.DrawingArea {
        private const int RIDGES = 11;

        private double _progress = 0.0;
        public double progress {
            get { return _progress; }
            set {
                _progress = value.clamp (0.0, 1.0);
                queue_draw ();
            }
        }

        /* Draw every ridge in the success colour once enrolment is complete. */
        private bool _complete = false;
        public bool complete {
            get { return _complete; }
            set {
                _complete = value;
                queue_draw ();
            }
        }

        public FingerprintArt () {
            Object (
                content_width: 132,
                content_height: 132,
                halign: Gtk.Align.CENTER,
                valign: Gtk.Align.CENTER
            );
            accessible_role = Gtk.AccessibleRole.IMG;
            set_draw_func (draw);
            Adw.StyleManager.get_default ().notify["accent-color"].connect (() => queue_draw ());
            Adw.StyleManager.get_default ().notify["dark"].connect (() => queue_draw ());
        }

        private void draw (Gtk.DrawingArea area, Cairo.Context cr, int width, int height) {
            var fg = get_color ();
            /* elementary defines @accent_color from the user's chosen accent. */
            Gdk.RGBA accent;
            if (!get_style_context ().lookup_color ("accent_color", out accent)) {
                accent = Adw.StyleManager.get_default ().accent_color.to_rgba ();
            }
            var done = Gdk.RGBA ();
            done.parse ("#3a9104");
            if (Adw.StyleManager.get_default ().dark) {
                done.parse ("#68b723");
            }

            double cx = width / 2.0;
            double cy = height / 2.0 + 2;
            double max_r = double.min (width, height) / 2.0 - 6;
            double step = max_r / (RIDGES + 0.6);
            int lit = (int) GLib.Math.round (_progress * RIDGES);

            cr.set_line_cap (Cairo.LineCap.ROUND);
            cr.set_line_width (3.4);

            /* The ridges fill from the outside in. */
            for (int i = 0; i < RIDGES; i++) {
                double r = max_r - i * step;
                bool on = _complete || i < lit;
                var colour = _complete ? done : (on ? accent : fg);
                cr.set_source_rgba (colour.red, colour.green, colour.blue, on ? 1.0 : 0.22);

                /* Each ridge is an arc with a gap whose position wanders, which is
                 * what makes it read as a print rather than a target. */
                double gap = 0.55 + 0.05 * (i % 4);
                double start = GLib.Math.PI * (0.62 + 0.11 * i) + (i % 2 == 0 ? 0.0 : 0.9);
                cr.new_path ();
                cr.arc (cx, cy, r, start, start + 2 * GLib.Math.PI - gap);
                cr.stroke ();
            }

            /* Core of the print. */
            bool core_on = _complete || _progress > 0.97;
            var core_colour = _complete ? done : (core_on ? accent : fg);
            cr.set_source_rgba (core_colour.red, core_colour.green, core_colour.blue, core_on ? 1.0 : 0.22);
            cr.arc (cx, cy - step * 0.1, step * 0.45, 0, 2 * GLib.Math.PI);
            cr.fill ();
        }
    }
}
