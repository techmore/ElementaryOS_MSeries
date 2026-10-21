"""Client B: one big MenuButton whose popover (an xdg_popup with a grab) holds an entry.

Writes {"popover": visible, "entry": text} to argv[1] every 100 ms, so the probe can
tell whether the menu closed and whether keystrokes went into it.
"""
import json
import sys

import gi
gi.require_version('Gtk', '4.0')
from gi.repository import Gtk, GLib


class App(Gtk.Application):
    def do_activate(self):
        win = Gtk.ApplicationWindow(application=self, title='probe-B', default_width=1000, default_height=700)
        self.entry = Gtk.Entry()
        self.popover = Gtk.Popover(child=self.entry)
        self.popover.connect('map', lambda *_: self.entry.grab_focus())
        button = Gtk.MenuButton(label='menu', popover=self.popover, hexpand=True, vexpand=True)
        win.set_child(button)
        win.present()
        GLib.timeout_add(100, self.save)

    def save(self):
        with open(sys.argv[1], 'w') as out:
            json.dump({'popover': self.popover.get_visible(), 'entry': self.entry.get_text()}, out)
        return True


App(application_id='ms.nested.probe.menu').run([])
