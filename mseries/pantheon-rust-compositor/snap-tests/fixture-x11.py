#!/usr/bin/env python3
"""One GTK 3 window on XWayland. SIGUSR1 makes it resize itself (S7)."""
import signal
import gi
gi.require_version('Gtk', '3.0')
from gi.repository import GLib, Gtk

win = Gtk.Window(title='Snap X11 fixture')
win.set_default_size(640, 420)
win.add(Gtk.Label(label='snap X11 fixture'))
win.connect('destroy', Gtk.main_quit)


def resize_self():
    win.resize(420, 300)
    return GLib.SOURCE_CONTINUE


GLib.unix_signal_add(GLib.PRIORITY_DEFAULT, signal.SIGUSR1, resize_self)
GLib.unix_signal_add(GLib.PRIORITY_DEFAULT, signal.SIGTERM, lambda: Gtk.main_quit() or False)
win.show_all()
Gtk.main()
