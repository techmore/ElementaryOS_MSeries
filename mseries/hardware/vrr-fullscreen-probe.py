#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Short, explicitly invoked fullscreen content probe; never changes display modes.

The requested 24/60/90-fps draw cadence is not measured panel refresh.
Record DRM properties separately. Escape closes the owned window.
"""
import argparse
import json
import math
from pathlib import Path
import time


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--connector', required=True, help='built-in eDP connector')
    parser.add_argument('--output', required=True, type=Path, help='new local JSON receipt')
    args = parser.parse_args()
    if not args.connector.startswith('eDP-'):
        parser.error('choose a built-in eDP connector; external fullscreen tests are out of scope')
    if args.output.exists():
        parser.error('output already exists; preserve previous observations')
    if not args.output.parent.is_dir():
        parser.error('output parent directory must exist')

    import gi
    gi.require_version('Gtk', '4.0')
    from gi.repository import Gdk, GLib, Gtk

    display = Gdk.Display.get_default()
    if display is None:
        parser.error('requires the active graphical session')
    monitors = display.get_monitors()
    internal = next((monitors.get_item(i) for i in range(monitors.get_n_items())
                     if monitors.get_item(i).get_connector() == args.connector), None)
    if internal is None:
        parser.error('requested built-in connector is not present')

    app = Gtk.Application(application_id='local.mseries.VrrProbe')
    draws = []
    observations = []
    start = None

    def activate(application):
        nonlocal start
        start = time.monotonic()
        window = Gtk.ApplicationWindow(application=application, title='Built-in VRR probe — Escape to close')
        area = Gtk.DrawingArea()
        window.set_child(area)

        def draw(_area, cr, width, height):
            elapsed = time.monotonic() - start
            cr.set_source_rgb(.035, .045, .06)
            cr.paint()
            cr.set_source_rgb(.55, .8, .95)
            cr.arc(width * (.5 + .35 * math.sin(elapsed * 2)), height * .55, 24, 0, math.tau)
            cr.fill()
            cr.set_source_rgb(.85, .88, .9)
            cr.select_font_face('Sans')
            cr.set_font_size(22)
            cr.move_to(width * .08, height * .25)
            cr.show_text('Built-in VRR probe — closes after 12 seconds — Escape to exit')
            draws.append(elapsed)

        area.set_draw_func(draw)
        last = [0.0, -1]

        def tick():
            elapsed = time.monotonic() - start
            if elapsed >= 12:
                application.quit()
                return False
            fps = 24 if elapsed < 4 else 60 if elapsed < 8 else 90
            if elapsed - last[0] >= 1 / fps:
                area.queue_draw()
                last[0] = elapsed
            bucket = int(elapsed * 2)
            if bucket != last[1]:
                observations.append({'elapsed_seconds': round(elapsed, 3),
                                     'requested_content_fps': fps,
                                     'active': window.is_active(),
                                     'fullscreen': window.is_fullscreen()})
                last[1] = bucket
            return True

        keys = Gtk.EventControllerKey()

        def pressed(_controller, key, _code, _state):
            if key == Gdk.KEY_Escape:
                application.quit()
                return True
            return False

        keys.connect('key-pressed', pressed)
        window.add_controller(keys)
        window.fullscreen_on_monitor(internal)
        window.present()
        GLib.timeout_add(2, tick)

    app.connect('activate', activate)
    status = app.run([])
    result = {'kind': 'fullscreen-content-observation', 'connector': args.connector,
              'requested_content_fps': [24, 60, 90], 'draw_calls': len(draws),
              'duration_seconds': None if start is None else time.monotonic() - start,
              'application_exit_status': status, 'window_observations': observations,
              'limits': ['No display configuration was changed by this probe.',
                         'Draw cadence is not physical refresh or VRR proof.',
                         'Capture DRM properties and user observations separately.']}
    with args.output.open('x') as stream:
        json.dump(result, stream, indent=2)
        stream.write('\n')
    return status


if __name__ == '__main__':
    raise SystemExit(main())
