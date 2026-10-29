"""GTK 3 X11 windows for the server-side frame probe.

  ssd <title> <w> <h>   a plain window that asks the window manager for a frame, with
                        WiFiman Desktop's hints: _MOTIF_WM_HINTS 0x2, 0x0, 0x1, 0x0, 0x0,
                        min size 420x460, max size 2147483647
  csd <title> <w> <h>   a window with a GtkHeaderBar: client-side decorated, moved
                        through _NET_WM_MOVERESIZE when its header bar is dragged
"""
import sys

import gi
gi.require_version('Gtk', '3.0')
gi.require_version('Gdk', '3.0')
from gi.repository import Gdk, Gtk

mode, title, width, height = sys.argv[1], sys.argv[2], int(sys.argv[3]), int(sys.argv[4])
window = Gtk.Window(title=title)
window.set_default_size(width, height)
window.connect('destroy', Gtk.main_quit)
if mode == 'ssd':
    hints = Gdk.Geometry()
    hints.min_width, hints.min_height = 420, 460
    hints.max_width = hints.max_height = 2147483647
    window.set_geometry_hints(None, hints, Gdk.WindowHints.MIN_SIZE | Gdk.WindowHints.MAX_SIZE)
    # flags=MWM_HINTS_DECORATIONS, decorations=MWM_DECOR_ALL, as Electron sets for frame: true.
    window.connect('realize', lambda w: w.get_window().set_decorations(Gdk.WMDecoration.ALL))
    window.add(Gtk.Label(label='server-side frame'))
elif mode == 'csd':
    bar = Gtk.HeaderBar(title=title, show_close_button=True)
    window.set_titlebar(bar)
    window.add(Gtk.Label(label='client-side frame'))
else:
    raise SystemExit('unknown mode ' + mode)
window.show_all()
Gtk.main()
