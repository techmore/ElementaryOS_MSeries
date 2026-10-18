/* SPDX-License-Identifier: GPL-3.0-or-later
 * Native Wayland quarter snapping for Gala 8.6.2 / Mutter 50.
 */
namespace Mseries.Snapping {
    public class Main : Gala.Plugin {
        private Gala.WindowManager wm;
        private GLib.Settings settings;
        private ulong begin_handler;
        private ulong end_handler;
        private ulong key_handler;
        private uint poll;
        private Meta.Window? dragged;
        private Clutter.Actor? preview;
        private bool cancelled;
        private const string[] NAMES = {"top-left", "top-right", "bottom-left", "bottom-right"};

        public override void initialize (Gala.WindowManager wm) {
            this.wm = wm;
            settings = new GLib.Settings ("org.techmore.mseries.snapping");
            var display = wm.get_display ();
            display.add_keybinding ("top-left", settings, Meta.KeyBindingFlags.IGNORE_AUTOREPEAT,
                (d, w, e, b) => snap_focused (0));
            display.add_keybinding ("top-right", settings, Meta.KeyBindingFlags.IGNORE_AUTOREPEAT,
                (d, w, e, b) => snap_focused (1));
            display.add_keybinding ("bottom-left", settings, Meta.KeyBindingFlags.IGNORE_AUTOREPEAT,
                (d, w, e, b) => snap_focused (2));
            display.add_keybinding ("bottom-right", settings, Meta.KeyBindingFlags.IGNORE_AUTOREPEAT,
                (d, w, e, b) => snap_focused (3));
            begin_handler = display.grab_op_begin.connect ((win, op) => {
                if (op != Meta.GrabOp.MOVING && op != Meta.GrabOp.MOVING_UNCONSTRAINED) return;
                if (!eligible (win)) return;
                clear_drag ();
                dragged = win;
                cancelled = false;
                poll = Timeout.add (32, () => { update_preview (); return Source.CONTINUE; });
            });
            // Remember Escape so cancelling a move never accidentally tiles it.
            key_handler = display.get_compositor ().get_stage ().captured_event.connect ((event) => {
                if (dragged != null && event.get_type () == Clutter.EventType.KEY_PRESS &&
                    event.get_key_symbol () == 0xff1b) cancelled = true;
                return Clutter.EVENT_PROPAGATE;
            });
            end_handler = display.grab_op_end.connect ((win, op) => {
                if (dragged != win) return;
                int monitor;
                int corner = pointer_corner (out monitor);
                Graphene.Point point;
                Clutter.ModifierType mods;
                display.get_compositor ().get_backend ().get_cursor_tracker ().get_pointer (out point, out mods);
                // Escape can be consumed by Mutter before stage event delivery.
                // A grab ending while the drag button remains down is cancelled.
                bool apply = !cancelled && corner >= 0 && (mods & Clutter.ModifierType.BUTTON1_MASK) == 0;
                clear_drag ();
                if (apply) {
                    // Mutter finishes its own edge-tile operation after this signal.
                    Idle.add (() => {
                        if (win.get_compositor_private () != null && eligible (win)) snap (win, monitor, corner);
                        return Source.REMOVE;
                    });
                }
            });
            message ("M-series quarter snapping initialized");
        }

        private bool eligible (Meta.Window win) {
            return win.get_window_type () == Meta.WindowType.NORMAL && win.allows_resize () && !win.is_fullscreen ();
        }

        private void snap_focused (int corner) {
            var win = wm.get_display ().get_focus_window ();
            if (win != null && eligible (win)) snap (win, win.get_monitor (), corner);
        }

        private Mtk.Rectangle quarter (Meta.Window win, int monitor, int corner) {
            var area = win.get_work_area_for_monitor (monitor);
            int left = area.width / 2;
            int top = area.height / 2;
            bool right = (corner % 2) == 1;
            bool bottom = corner >= 2;
            return {area.x + (right ? left : 0), area.y + (bottom ? top : 0),
                right ? area.width - left : left, bottom ? area.height - top : top};
        }

        private void snap (Meta.Window win, int monitor, int corner) {
            var rect = quarter (win, monitor, corner);
            win.unmaximize ();
            win.move_to_monitor (monitor);
            win.move_resize_frame (true, rect.x, rect.y, rect.width, rect.height);
        }

        private int pointer_corner (out int monitor) {
            monitor = -1;
            Graphene.Point point;
            Clutter.ModifierType mods;
            var display = wm.get_display ();
            display.get_compositor ().get_backend ().get_cursor_tracker ().get_pointer (out point, out mods);
            for (int m = 0; m < display.get_n_monitors (); m++) {
                var geo = display.get_monitor_geometry (m);
                if (point.x < geo.x || point.y < geo.y || point.x >= geo.x + geo.width || point.y >= geo.y + geo.height) continue;
                monitor = m;
                // Corners are 40 logical pixels, independently of display scale.
                bool left = point.x < geo.x + 40;
                bool right = point.x >= geo.x + geo.width - 40;
                bool top = point.y < geo.y + 40;
                bool bottom = point.y >= geo.y + geo.height - 40;
                if ((left || right) && (top || bottom)) return (bottom ? 2 : 0) + (right ? 1 : 0);
                return -1;
            }
            return -1;
        }

        private void update_preview () {
            int monitor;
            int corner = pointer_corner (out monitor);
            if (dragged == null || cancelled || corner < 0) {
                if (preview != null) preview.hide ();
                return;
            }
            var rect = quarter (dragged, monitor, corner);
            wm.hide_tile_preview ();
            if (preview == null) {
                preview = new Clutter.Actor () {
                    background_color = {0x60, 0xa5, 0xfa, 0x70},
                    reactive = false
                };
                wm.get_display ().get_compositor ().get_feedback_group ().add_child (preview);
            }
            preview.set_position (rect.x, rect.y);
            preview.set_size (rect.width, rect.height);
            preview.show ();
        }

        private void clear_drag () {
            if (poll != 0) { Source.remove (poll); poll = 0; }
            if (preview != null) { preview.destroy (); preview = null; }
            dragged = null;
        }

        public override void destroy () {
            clear_drag ();
            var display = wm.get_display ();
            SignalHandler.disconnect (display, begin_handler);
            SignalHandler.disconnect (display, end_handler);
            SignalHandler.disconnect (display.get_compositor ().get_stage (), key_handler);
            foreach (var name in NAMES) display.remove_keybinding (name);
        }
    }
}

public Gala.PluginInfo register_plugin () {
    return {"mseries-snapping", "M-series", typeof (Mseries.Snapping.Main),
        Gala.PluginFunction.ADDITION, Gala.LoadPriority.IMMEDIATE};
}
