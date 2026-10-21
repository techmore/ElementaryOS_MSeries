#!/usr/bin/env python3
"""Plain GTK 4 windows for nested snap checks.

argv[1] = minimum width (0 for none), argv[2] = number of windows (default 1).
"""
import sys
import gi
gi.require_version('Gtk', '4.0')
from gi.repository import Gtk

min_width = int(sys.argv[1]) if len(sys.argv) > 1 else 0
count = int(sys.argv[2]) if len(sys.argv) > 2 else 1
app = Gtk.Application(application_id='org.techmore.SnapFixture')


def activate(app):
    for index in range(count):
        win = Gtk.ApplicationWindow(application=app, title=f'Snap fixture {index}')
        win.set_default_size(700 - 60 * index, 450 - 30 * index)
        label = Gtk.Label(label=f'snap fixture {index}')
        if min_width:
            label.set_size_request(min_width, 200)
        win.set_child(label)
        win.present()


app.connect('activate', activate)
app.run([])
