/* SPDX-License-Identifier: GPL-3.0-or-later */
/* Two hands, palms toward you, with the fingers that have a fingerprint lit.
 *
 * It is a picture of state, not a control: the finger cards and the Add
 * Fingerprint button are the accessible way to change anything. In the sheet the
 * finger about to be enrolled pulses so the person knows which one to use. */
namespace MSeriesTouchId {
    public class HandDiagram : Gtk.DrawingArea {
        /* The drawing's own coordinate box; the widget scales it to fit. */
        private const double HAND_W = 100.0;
        private const double HAND_H = 130.0;
        private const double GAP = 18.0;
        private const double PAD_LEN = 27.0;

        private string[] _enrolled = {};
        public string[] enrolled {
            get { return _enrolled; }
            set {
                _enrolled = value;
                update_label ();
                queue_draw ();
            }
        }

        private string? _target = null;
        public string? target {
            get { return _target; }
            set {
                _target = value;
                update_label ();
                queue_draw ();
            }
        }

        private double pulse_t = 0.0;
        private Adw.Animation? pulse_anim = null;

        public HandDiagram () {
            Object (
                content_width: 232,
                content_height: 140,
                halign: Gtk.Align.CENTER,
                valign: Gtk.Align.CENTER
            );
            accessible_role = Gtk.AccessibleRole.IMG;
            set_draw_func (draw);
            var style = Adw.StyleManager.get_default ();
            style.notify["accent-color"].connect (() => queue_draw ());
            style.notify["dark"].connect (() => queue_draw ());
            map.connect (start_pulse);
            unmap.connect (() => {
                if (pulse_anim != null) {
                    pulse_anim.skip ();
                }
            });
            update_label ();
        }

        private void start_pulse () {
            if (pulse_anim != null) {
                pulse_anim.skip ();
            }
            var target_cb = new Adw.CallbackAnimationTarget ((v) => {
                pulse_t = v;
                if (_target != null) {
                    queue_draw ();
                }
            });
            pulse_anim = new Adw.TimedAnimation (this, 0.0, 1.0, 900, target_cb) {
                easing = Adw.Easing.EASE_IN_OUT_SINE,
                repeat_count = 0,
                alternate = true
            };
            pulse_anim.play ();
        }

        private void update_label () {
            string text;
            if (_enrolled.length == 0) {
                text = "No fingerprints added";
            } else {
                string[] names = {};
                foreach (var finger in _enrolled) {
                    names += finger_label (finger).down ();
                }
                text = "Fingerprints added: %s".printf (string.joinv (", ", names));
            }
            if (_target != null) {
                text += ". Next: %s".printf (finger_label (_target).down ());
            }
            update_property (Gtk.AccessibleProperty.LABEL, text, -1);
        }

        /* A capsule: a rectangle with fully rounded ends. */
        private static void capsule (Cairo.Context cr, double x, double y, double w, double h) {
            double r = w / 2.0;
            cr.new_sub_path ();
            cr.arc (x + r, y + r, r, GLib.Math.PI, 0);
            cr.arc (x + r, y + h - r, r, 0, GLib.Math.PI);
            cr.close_path ();
        }

        private static void rounded (Cairo.Context cr, double x, double y, double w, double h, double r) {
            cr.new_sub_path ();
            cr.arc (x + w - r, y + r, r, -GLib.Math.PI / 2, 0);
            cr.arc (x + w - r, y + h - r, r, 0, GLib.Math.PI / 2);
            cr.arc (x + r, y + h - r, r, GLib.Math.PI / 2, GLib.Math.PI);
            cr.arc (x + r, y + r, r, GLib.Math.PI, 3 * GLib.Math.PI / 2);
            cr.close_path ();
        }

        /* One finger's geometry for a right hand with the thumb on the right. */
        private struct Digit {
            string name;
            double cx;
            double top;
        }

        private void draw (Gtk.DrawingArea area, Cairo.Context cr, int width, int height) {
            var fg = get_color ();
            Gdk.RGBA accent;
            if (!get_style_context ().lookup_color ("accent_color", out accent)) {
                accent = Adw.StyleManager.get_default ().accent_color.to_rgba ();
            }

            double total_w = HAND_W * 2 + GAP;
            double scale = double.min (width / total_w, height / HAND_H);
            cr.translate ((width - total_w * scale) / 2.0, (height - HAND_H * scale) / 2.0);
            cr.scale (scale, scale);

            draw_hand (cr, "left", 0.0, fg, accent, true);
            draw_hand (cr, "right", HAND_W + GAP, fg, accent, false);
        }

        private void draw_hand (Cairo.Context cr, string side, double ox, Gdk.RGBA fg, Gdk.RGBA accent, bool mirror) {
            cr.save ();
            cr.translate (ox, 0);
            if (mirror) {
                cr.translate (HAND_W, 0);
                cr.scale (-1, 1);
            }

            Digit[] digits = {
                { "little-finger", 25.0, 46.0 },
                { "ring-finger", 40.5, 30.0 },
                { "middle-finger", 56.0, 22.0 },
                { "index-finger", 71.5, 32.0 }
            };
            double finger_w = 13.5;

            /* The silhouette: one fill for palm, fingers and thumb, so the overlaps
             * do not double their opacity. */
            cr.set_fill_rule (Cairo.FillRule.WINDING);
            cr.new_path ();
            rounded (cr, 14, 64, 72, 62, 26);
            foreach (var d in digits) {
                capsule (cr, d.cx - finger_w / 2.0, d.top, finger_w, 80.0 - d.top);
            }
            /* The thumb comes off the palm's outer edge, angled outward. It joins the
             * same path: a separate fill would double the opacity where they overlap. */
            cr.save ();
            cr.translate (82, 100);
            cr.rotate (0.62);
            capsule (cr, -8.0, -44.0, 16.0, 56.0);
            cr.restore ();
            cr.set_source_rgba (fg.red, fg.green, fg.blue, 0.11);
            cr.fill ();

            /* Fingertip pads: lit where a fingerprint exists, pulsing for the target. */
            foreach (var d in digits) {
                var key = side + "-" + d.name;
                paint_pad (cr, key, d.cx - finger_w / 2.0, d.top, finger_w, PAD_LEN, accent);
            }
            cr.save ();
            cr.translate (82, 100);
            cr.rotate (0.62);
            paint_pad (cr, side + "-thumb", -8.0, -44.0, 16.0, PAD_LEN, accent);
            cr.restore ();

            cr.restore ();
        }

        private void paint_pad (Cairo.Context cr, string key, double x, double y, double w, double h,
                                Gdk.RGBA accent) {
            bool lit = key in _enrolled;
            bool next = _target != null && key == _target;
            if (!lit && !next) {
                return;
            }
            capsule (cr, x, y, w, h);
            double alpha = lit ? 0.95 : 0.28 + 0.55 * pulse_t;
            cr.set_source_rgba (accent.red, accent.green, accent.blue, alpha);
            cr.fill_preserve ();
            if (next) {
                cr.set_line_width (1.6);
                cr.set_source_rgba (accent.red, accent.green, accent.blue, 0.5 + 0.5 * pulse_t);
                cr.stroke ();
            } else {
                cr.new_path ();
            }
        }
    }
}
