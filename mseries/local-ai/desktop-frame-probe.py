#!/usr/bin/env python3
"""Record GTK frame-clock callbacks for a visible, continuously animated window."""
import json
import signal
import sys
import time
import gi

gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, GLib

frames = []
window = Gtk.Window(title='M-Series responsiveness measurement')
window.set_default_size(320, 120)
area = Gtk.DrawingArea()
window.add(area)

def draw(widget, cr):
    w, h = widget.get_allocated_width(), widget.get_allocated_height()
    cr.set_source_rgb(0.10, 0.14, 0.20)
    cr.paint()
    cr.set_source_rgb(0.2, 0.75, 0.9)
    cr.rectangle((time.monotonic() * 120) % max(1, w - 32), h / 2 - 16, 32, 32)
    cr.fill()
    return False

def tick(widget, clock):
    frames.append(time.monotonic())
    widget.queue_draw()
    return True

def finish(*_):
    with open(sys.argv[1], 'w') as out:
        json.dump({'frames_monotonic': frames}, out)
    Gtk.main_quit()
    return False

area.connect('draw', draw)
area.add_tick_callback(tick)
window.connect('destroy', finish)
GLib.unix_signal_add(GLib.PRIORITY_DEFAULT, signal.SIGTERM, finish)
window.show_all()
Gtk.main()
