#!/usr/bin/env python3
"""One plain GTK 4 window for nested snap checks. argv[1] = minimum width (optional)."""
import sys
import gi
gi.require_version('Gtk', '4.0')
from gi.repository import Gtk

min_width = int(sys.argv[1]) if len(sys.argv) > 1 else 0
app = Gtk.Application(application_id='org.techmore.SnapFixture')


def activate(app):
    win = Gtk.ApplicationWindow(application=app, title='Snap fixture')
    win.set_default_size(700, 450)
    label = Gtk.Label(label='snap fixture')
    if min_width:
        label.set_size_request(min_width, 200)
    win.set_child(label)
    win.present()


app.connect('activate', activate)
app.run([])
