"""GTK 3 X11 clients for the focus probe (run on the nested compositor's XWayland).

  card   <status>     an override-redirect, no-input notification card, built like
                      mseries/desktop-notifications/popup.py; writes "clicked" when its button is pressed
  burst  <count>      maps and destroys <count> such cards back to back
  urgent <delay-ms>   a normal window titled probe-X that sets the WM_HINTS urgency hint after <delay-ms>
"""
import sys

import gi
gi.require_version('Gtk', '3.0')
gi.require_version('Gdk', '3.0')
from gi.repository import Gdk, GLib, Gtk


def card(x=40, y=40):
    window = Gtk.Window(type=Gtk.WindowType.POPUP)
    window.set_type_hint(Gdk.WindowTypeHint.NOTIFICATION)
    window.set_accept_focus(False)
    window.set_focus_on_map(False)
    window.set_default_size(300, 100)
    window.move(x, y)
    window.connect('realize', lambda w: w.get_window().set_override_redirect(True))
    return window


mode, arg = sys.argv[1], sys.argv[2]
if mode == 'card':
    window = card()
    button = Gtk.Button(label='card')

    def clicked(*_):
        with open(arg, 'w') as out:
            out.write('clicked')
    button.connect('clicked', clicked)
    window.add(button)
    window.connect('map-event', lambda *_: open(arg + '.mapped', 'w').close())
    window.show_all()
elif mode == 'burst':
    remaining = [int(arg)]

    def step():
        # Lifetimes from 0 to 45 ms, so some cards die while the compositor
        # is still handling their MapNotify.
        window = card(60 + remaining[0] % 7 * 10, 60)
        window.add(Gtk.Label(label='burst'))
        window.show_all()
        lifetime = remaining[0] % 4 * 15
        if lifetime:
            GLib.timeout_add(lifetime, lambda: window.destroy() or False)
        else:
            window.destroy()
        remaining[0] -= 1
        if remaining[0] <= 0:
            GLib.timeout_add(500, Gtk.main_quit)
            return False
        return True
    GLib.timeout_add(25, step)
elif mode == 'urgent':
    window = Gtk.Window(title='probe-X')
    window.set_default_size(300, 150)
    window.add(Gtk.Label(label='X'))
    window.show_all()
    GLib.timeout_add(int(arg), lambda: window.set_urgency_hint(True) or False)
else:
    raise SystemExit('unknown mode ' + mode)
Gtk.main()
