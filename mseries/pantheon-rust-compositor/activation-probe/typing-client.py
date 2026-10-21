"""A separate client that owns the focused window and receives the user's typing."""
import sys
import gi
gi.require_version('Gtk', '4.0')
from gi.repository import Gtk, GLib

class App(Gtk.Application):
    def do_activate(self):
        win = Gtk.ApplicationWindow(application=self, title='probe-B', default_width=320, default_height=160)
        self.entry = Gtk.Entry()
        win.set_child(self.entry)
        win.present()
        self.entry.grab_focus()
        GLib.timeout_add(200, self.save)
    def save(self):
        open(sys.argv[1], 'w').write(self.entry.get_text())
        return True

App(application_id='ms.nested.probe.b').run([])
