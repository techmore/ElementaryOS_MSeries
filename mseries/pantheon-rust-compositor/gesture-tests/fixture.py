#!/usr/bin/env python3
"""Two plain GTK windows with distinct colors for nested render measurements."""
import gi
gi.require_version('Gtk', '4.0')
from gi.repository import Gtk, Gdk
app = Gtk.Application(application_id='org.techmore.GestureFixture')
def activate(app):
    css = Gtk.CssProvider()
    css.load_from_data(b'.red { background: #dd3333; color: white; } .blue { background: #3355dd; color: white; }')
    Gtk.StyleContext.add_provider_for_display(Gdk.Display.get_default(), css, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
    for color in ['red', 'blue']:
        win = Gtk.ApplicationWindow(application=app, title=f'Gesture {color}')
        win.set_default_size(780, 520)
        win.add_css_class(color)
        win.set_child(Gtk.Label(label=f'{color.upper()} workspace window'))
        win.present()
app.connect('activate', activate)
app.run([])
