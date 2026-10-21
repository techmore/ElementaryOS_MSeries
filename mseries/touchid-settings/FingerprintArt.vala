/* SPDX-License-Identifier: GPL-3.0-or-later */
/* The fingerprint: concentric ridges drawn with Cairo.
 *
 * It does three jobs. On the page it is a calm accent-coloured badge; on a finger
 * card it is a small static print; in the Add Fingerprint sheet it is the
 * feedback surface: ridges fill from the outside in as touches are accepted, the
 * print "breathes" while it waits for a finger, a ripple leaves it on every
 * accepted touch, and on success the centre becomes a green seal with a check
 * that draws itself. All motion goes through Adw animations, which honour the
 * system's reduced-motion setting by jumping straight to the end value. */
namespace MSeriesTouchId {
    public enum ArtState {
        IDLE,
        WAITING,
        SUCCESS,
        FAILED
    }

    public class FingerprintArt : Gtk.DrawingArea {
        public const int RIDGES = 11;

        private double _progress = 0.0;
        private double pulse_t = 0.0;
        private double ripple_t = 1.0;
        private double check_t = 0.0;
        private double pop_t = 1.0;

        private Adw.Animation? progress_anim = null;
        private Adw.Animation? pulse_anim = null;
        private Adw.Animation? ripple_anim = null;
        private Adw.Animation? check_anim = null;
        private Adw.Animation? pop_anim = null;
        private uint check_delay = 0;

        /* Fraction of the print that is filled, 0..1. */
        public double progress {
            get { return _progress; }
            set {
                _progress = value.clamp (0.0, 1.0);
                queue_draw ();
            }
        }

        /* Draw every ridge in the accent colour (finger cards, "ready" badge). */
        private bool _lit = false;
        public bool lit {
            get { return _lit; }
            set {
                _lit = value;
                queue_draw ();
            }
        }

        private ArtState _state = ArtState.IDLE;
        public ArtState state {
            get { return _state; }
            set {
                if (_state == value) {
                    return;
                }
                _state = value;
                apply_state ();
                queue_draw ();
            }
        }

        public int ridge_count { get; construct; default = RIDGES; }
        public double line_width { get; construct; default = 3.4; }

        public FingerprintArt (int size = 132, int ridges = RIDGES, double line_width = 3.4) {
            Object (
                content_width: size,
                content_height: size,
                halign: Gtk.Align.CENTER,
                valign: Gtk.Align.CENTER,
                ridge_count: ridges,
                line_width: line_width
            );
            accessible_role = Gtk.AccessibleRole.IMG;
            set_draw_func (draw);
            var style = Adw.StyleManager.get_default ();
            style.notify["accent-color"].connect (() => queue_draw ());
            style.notify["dark"].connect (() => queue_draw ());
            unmap.connect (stop_all);
        }

        /* Move the fill to `to` with a short ease; the sheet calls this per touch. */
        public void animate_progress (double to) {
            to = to.clamp (0.0, 1.0);
            if (progress_anim != null) {
                progress_anim.skip ();
            }
            var target = new Adw.CallbackAnimationTarget ((v) => {
                _progress = v;
                queue_draw ();
            });
            progress_anim = new Adw.TimedAnimation (this, _progress, to, 380, target) {
                easing = Adw.Easing.EASE_OUT_CUBIC
            };
            progress_anim.play ();
        }

        /* A ring leaves the print: one accepted touch. */
        public void ripple () {
            if (ripple_anim != null) {
                ripple_anim.skip ();
            }
            var target = new Adw.CallbackAnimationTarget ((v) => {
                ripple_t = v;
                queue_draw ();
            });
            ripple_anim = new Adw.TimedAnimation (this, 0.0, 1.0, 700, target) {
                easing = Adw.Easing.EASE_OUT_CUBIC
            };
            ripple_anim.play ();
        }

        private void apply_state () {
            if (pulse_anim != null) {
                pulse_anim.skip ();
                pulse_anim = null;
            }
            pulse_t = 0.0;

            switch (_state) {
                case ArtState.WAITING:
                    var pulse_target = new Adw.CallbackAnimationTarget ((v) => {
                        pulse_t = v;
                        queue_draw ();
                    });
                    pulse_anim = new Adw.TimedAnimation (this, 0.0, 1.0, 1100, pulse_target) {
                        easing = Adw.Easing.EASE_IN_OUT_SINE,
                        repeat_count = 0,
                        alternate = true
                    };
                    pulse_anim.play ();
                    break;
                case ArtState.SUCCESS:
                    animate_progress (1.0);
                    check_t = 0.0;
                    pop_t = 0.0;
                    var pop_target = new Adw.CallbackAnimationTarget ((v) => {
                        pop_t = v;
                        queue_draw ();
                    });
                    pop_anim = new Adw.TimedAnimation (this, 0.0, 1.0, 520, pop_target) {
                        easing = Adw.Easing.EASE_OUT_CUBIC
                    };
                    pop_anim.play ();
                    if (check_delay != 0) {
                        GLib.Source.remove (check_delay);
                    }
                    check_delay = GLib.Timeout.add (260, () => {
                        check_delay = 0;
                        var check_target = new Adw.CallbackAnimationTarget ((v) => {
                            check_t = v;
                            queue_draw ();
                        });
                        check_anim = new Adw.TimedAnimation (this, 0.0, 1.0, 420, check_target) {
                            easing = Adw.Easing.EASE_OUT_CUBIC
                        };
                        check_anim.play ();
                        return GLib.Source.REMOVE;
                    });
                    break;
                default:
                    break;
            }
        }

        private void stop_all () {
            foreach (var anim in new Adw.Animation?[] { progress_anim, pulse_anim, ripple_anim, check_anim, pop_anim }) {
                if (anim != null) {
                    anim.skip ();
                }
            }
            if (check_delay != 0) {
                GLib.Source.remove (check_delay);
                check_delay = 0;
            }
        }

        /* Theme colours, with fallbacks for hosts that do not define the name. */
        private Gdk.RGBA named (string name, string fallback) {
            Gdk.RGBA colour;
            if (!get_style_context ().lookup_color (name, out colour)) {
                colour = Gdk.RGBA ();
                colour.parse (fallback);
            }
            return colour;
        }

        private void draw (Gtk.DrawingArea area, Cairo.Context cr, int width, int height) {
            var fg = get_color ();
            Gdk.RGBA accent;
            if (!get_style_context ().lookup_color ("accent_color", out accent)) {
                accent = Adw.StyleManager.get_default ().accent_color.to_rgba ();
            }
            bool dark = Adw.StyleManager.get_default ().dark;
            var success = named ("success_color", dark ? "#68b723" : "#3a9104");
            var danger = named ("error_color", dark ? "#ff8c82" : "#c6262e");

            double cx = width / 2.0;
            double cy = height / 2.0;
            double max_r = double.min (width, height) / 2.0 - line_width * 1.6;
            double step = max_r / (ridge_count + 0.6);

            /* "Breathing" while waiting, a small pop when the check lands. */
            double scale = 1.0 - 0.035 * pulse_t;
            scale += 0.07 * GLib.Math.sin (GLib.Math.PI * pop_t) * (_state == ArtState.SUCCESS ? 1.0 : 0.0);
            cr.save ();
            cr.translate (cx, cy);
            cr.scale (scale, scale);
            cr.translate (-cx, -cy);

            cr.set_line_cap (Cairo.LineCap.ROUND);
            cr.set_line_width (line_width);

            double filled = _progress * ridge_count;
            for (int i = 0; i < ridge_count; i++) {
                double r = max_r - i * step;
                double f = _lit ? 1.0 : (filled - i).clamp (0.0, 1.0);

                Gdk.RGBA on = accent;
                if (_state == ArtState.SUCCESS) {
                    on = success;
                } else if (_state == ArtState.FAILED) {
                    on = danger;
                }

                /* Blend the dim ridge toward the lit one so the fill is smooth. */
                double dim = _state == ArtState.FAILED ? 0.55 : 0.2;
                double alpha = dim + (1.0 - dim) * f;
                double red = fg.red + (on.red - fg.red) * f;
                double green = fg.green + (on.green - fg.green) * f;
                double blue = fg.blue + (on.blue - fg.blue) * f;
                if (_state == ArtState.SUCCESS && check_t > 0.0) {
                    alpha = double.min (alpha, 1.0 - 0.45 * check_t);
                }
                cr.set_source_rgba (red, green, blue, alpha);

                /* Each ridge is an arc whose gap wanders: a print, not a target. */
                double gap = 0.55 + 0.05 * (i % 4);
                double start = GLib.Math.PI * (0.62 + 0.11 * i) + (i % 2 == 0 ? 0.0 : 0.9);
                cr.new_path ();
                cr.arc (cx, cy, r, start, start + 2 * GLib.Math.PI - gap);
                cr.stroke ();
            }

            /* The core: a dot, or the success seal with its check. */
            if (_state == ArtState.SUCCESS) {
                double seal = step * 3.4;
                cr.set_source_rgba (success.red, success.green, success.blue, 0.15 + 0.85 * check_t);
                cr.arc (cx, cy, seal * (0.55 + 0.45 * check_t), 0, 2 * GLib.Math.PI);
                cr.fill ();
                if (check_t > 0.0) {
                    draw_check (cr, cx, cy, seal * 0.62, check_t);
                }
            } else {
                bool core_on = _lit || _progress > 0.97;
                var core = _state == ArtState.FAILED ? danger : (core_on ? accent : fg);
                cr.set_source_rgba (core.red, core.green, core.blue, core_on ? 1.0 : 0.22);
                cr.arc (cx, cy - step * 0.1, step * 0.45, 0, 2 * GLib.Math.PI);
                cr.fill ();
            }
            cr.restore ();

            /* The ripple is drawn unscaled so it can leave the print's edge. */
            if (ripple_t < 1.0) {
                cr.set_line_width (line_width * 0.9);
                cr.set_source_rgba (accent.red, accent.green, accent.blue, (1.0 - ripple_t) * 0.6);
                cr.arc (cx, cy, max_r * (0.7 + 0.45 * ripple_t), 0, 2 * GLib.Math.PI);
                cr.stroke ();
            }
        }

        /* A two-segment check that draws itself: `t` is how much of it exists. */
        private void draw_check (Cairo.Context cr, double cx, double cy, double r, double t) {
            double x1 = cx - r * 0.62, y1 = cy + r * 0.02;
            double x2 = cx - r * 0.14, y2 = cy + r * 0.50;
            double x3 = cx + r * 0.68, y3 = cy - r * 0.46;
            double l1 = GLib.Math.hypot (x2 - x1, y2 - y1);
            double l2 = GLib.Math.hypot (x3 - x2, y3 - y2);
            double reach = t * (l1 + l2);

            cr.set_source_rgba (1, 1, 1, 1);
            cr.set_line_width (line_width * 1.7);
            cr.set_line_cap (Cairo.LineCap.ROUND);
            cr.set_line_join (Cairo.LineJoin.ROUND);
            cr.new_path ();
            cr.move_to (x1, y1);
            if (reach <= l1) {
                cr.line_to (x1 + (x2 - x1) * reach / l1, y1 + (y2 - y1) * reach / l1);
            } else {
                cr.line_to (x2, y2);
                double rest = (reach - l1) / l2;
                cr.line_to (x2 + (x3 - x2) * rest, y2 + (y3 - y2) * rest);
            }
            cr.stroke ();
        }
    }
}
