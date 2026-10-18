#!/usr/bin/env python3
"""Reproducible GTK audit with synthetic inventories, no daemon or guest access.

Run in Xvfb with cairo. Reports UI-thread update time (not end-to-end frame
latency); optionally saves narrow/wide screenshots of every instance tab.
"""
import argparse
import copy
import json
import os
from pathlib import Path
import statistics
import sys
import tempfile
import time
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from orchard_incus.window import Window
from gi.repository import Gtk, GLib, Gdk, Graphene


def fixture(n):
    return {'name': f'dev-{n:04}', 'status': 'Running', 'type': 'container', 'architecture': 'aarch64',
            'config': {'image.description': 'Debian development', 'image.os': 'Debian', 'image.release': '13'},
            'state': {'memory': {'usage': 104857600}, 'cpu': {'usage': 1000000}, 'processes': 12,
                      'network': {'eth0': {'addresses': [{'family': 'inet', 'scope': 'global', 'address': f'10.0.0.{n % 250 + 1}'}]}}}}


def settle(duration=0.08):
    end = time.monotonic() + duration
    context = GLib.MainContext.default()
    while time.monotonic() < end:
        while context.pending():
            context.iteration(False)
        time.sleep(.002)


def capture(win, path):
    paint = Gtk.WidgetPaintable.new(win)
    snap = Gtk.Snapshot()
    paint.snapshot(snap, win.get_width(), win.get_height())
    node = snap.to_node()
    tex = win.get_renderer().render_texture(node, Graphene.Rect().init(0, 0, win.get_width(), win.get_height()))
    tex.save_to_png(str(path))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--screenshots', action='store_true')
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    app = Gtk.Application(application_id='io.github.techmore.OrchardAudit')
    app.register(None)
    Gtk.Settings.get_default().props.gtk_enable_animations = False
    receipts = {'method': 'GTK UI-thread show() milliseconds; nine sampled updates with full 90-point histories; Instances/Overview and Dashboard visible in separate passes; synthetic fixtures; cairo/X11; no Incus calls; deferred dashboard creation excluded', 'inventories': []}
    with tempfile.TemporaryDirectory() as directory, patch('orchard_incus.window.STATE_FILE', directory + '/state.json'), \
         patch.object(Window, 'check_incus'), patch.object(Window, 'bg'), patch.object(Window, 'read', create=True):
        for count in (10, 100, 500):
            win = Window(app)
            win.present()
            settle()
            data = [fixture(i) for i in range(count)]
            start = time.perf_counter()
            win.show(copy.deepcopy(data))
            first = (time.perf_counter() - start) * 1000
            win.open_instance('dev-0000')
            win.pages.set_visible_child_name('inst')
            settle()
            for history in win.hist.values():
                history['cpu'].extend([1.] * 90)
                history['mem'].extend([104857600] * 90)
            timings = []
            for _ in range(9):
                win.last_sample = 0  # exercise the chart cadence without waiting 3s
                for item in data:
                    item['state']['cpu']['usage'] += 1000000
                    item['state']['memory']['usage'] += 1024
                sample = copy.deepcopy(data)
                start = time.perf_counter()
                win.show(sample)
                timings.append((time.perf_counter() - start) * 1000)
                settle(.015)
            win.pages.set_visible_child_name('dash')
            settle(.1)
            deadline = time.monotonic() + 10
            while getattr(win, '_dashboard_rendering', False) and time.monotonic() < deadline:
                settle(.02)
            dashboard = []
            for _ in range(9):
                win.last_sample = 0
                for item in data:
                    item['state']['memory']['usage'] += 1024
                sample = copy.deepcopy(data)
                start = time.perf_counter()
                win.show(sample)
                dashboard.append((time.perf_counter() - start) * 1000)
                settle(.015)
            receipts['inventories'].append({'count': count, 'initial_ms': round(first, 2),
                'update_median_ms': round(statistics.median(timings), 2), 'update_max_ms': round(max(timings), 2),
                'dashboard_median_ms': round(statistics.median(dashboard), 2), 'dashboard_max_ms': round(max(dashboard), 2)})
            win.close()
            settle(.02)
        (args.output / 'measurements.json').write_text(json.dumps(receipts, indent=2) + '\n')
        if args.screenshots:
            for width, height, dark in ((1180, 740, False), (780, 480, False), (780, 480, True)):
                win = Window(app)
                win.set_default_size(width, height)
                Gtk.Settings.get_default().props.gtk_application_prefer_dark_theme = dark
                win.show([fixture(i) for i in range(4)])
                win.open_instance('dev-0000')
                win.present()
                for tab in ('ov', 'sn', 'ex', 'fi', 'de', 'se'):
                    win.tabs.set_visible_child_name(tab)
                    settle(.18)
                    capture(win, args.output / f'{width}-{height}-{"dark" if dark else "light"}-{tab}.png')
                win.pages.set_visible_child_name('dash')
                settle(.18)
                capture(win, args.output / f'{width}-{height}-{"dark" if dark else "light"}-dashboard.png')
                win.close()
                settle(.02)
    print(json.dumps(receipts, indent=2))
    (args.output / 'measurements.json').write_text(json.dumps(receipts, indent=2) + '\n')


if __name__ == '__main__':
    main()
