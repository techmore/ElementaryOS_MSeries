#!/usr/bin/python3
"""Floating microphone indicator for F5 dictation, like macOS dictation's mic.

Started by stream-dictate.py when the microphone opens and stopped when it closes.
Reads one line per update on stdin: a level from 0 to 1, or "quit".

The window never takes keyboard focus: the compositor recognises its application ID
(org.techmore.mseries.DictationIndicator) and places it bottom-centre above the dock.
On a compositor that does not advertise that (DictationIndicatorPlacementVersion),
a normal window would steal focus from the field being dictated into, so this exits
with status 3 and the controller falls back to a notification.
"""
import math
import sys
import threading

import gi

gi.require_version('Gtk', '4.0')
from gi.repository import Gio, GLib, Gtk  # noqa: E402

APP_ID = 'org.techmore.mseries.DictationIndicator'
UNSUPPORTED = 3
BARS = 5

CSS = b"""
window.dictation-indicator { background: transparent; }
.pill {
  background-color: alpha(#1c1c1e, 0.88);
  border-radius: 28px;
  padding: 10px 18px;
  box-shadow: 0 6px 18px alpha(black, 0.35);
}
.pill image { color: white; }
.pill .bar { background-color: white; border-radius: 2px; min-width: 4px; }
"""


def compositor_supports_indicator():
    try:
        bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
        reply = bus.call_sync('org.pantheon.gala', '/org/pantheon/gala/DesktopInterface',
                              'org.freedesktop.DBus.Properties', 'Get',
                              GLib.Variant('(ss)', ('org.pantheon.gala.DesktopIntegration',
                                                    'DictationIndicatorPlacementVersion')),
                              GLib.VariantType('(v)'), Gio.DBusCallFlags.NONE, 500, None)
        return reply.unpack()[0] >= 1
    except GLib.Error:
        return False


class Indicator(Gtk.Application):
    def __init__(self):
        super().__init__(application_id=APP_ID, flags=Gio.ApplicationFlags.NON_UNIQUE)
        self.level = 0.0
        self.shown = 0.0
        self.phase = 0.0
        self.bars = []

    def do_activate(self):
        provider = Gtk.CssProvider()
        provider.load_from_data(CSS)
        Gtk.StyleContext.add_provider_for_display(
            Gtk.Widget.get_display(Gtk.Label()), provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        win = Gtk.ApplicationWindow(application=self, title='Dictation', decorated=False,
                                    resizable=False, focusable=False, can_focus=False)
        win.add_css_class('dictation-indicator')
        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10, valign=Gtk.Align.CENTER)
        box.add_css_class('pill')
        icon = Gtk.Image.new_from_icon_name('audio-input-microphone-symbolic')
        icon.set_pixel_size(22)
        box.append(icon)
        meter = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=3, valign=Gtk.Align.CENTER)
        for _ in range(BARS):
            bar = Gtk.Box(valign=Gtk.Align.CENTER)
            bar.add_css_class('bar')
            bar.set_size_request(4, 4)
            meter.append(bar)
            self.bars.append(bar)
        box.append(meter)
        win.set_child(box)
        win.present()
        GLib.timeout_add(33, self.tick)
        threading.Thread(target=self.read_stdin, daemon=True).start()

    def read_stdin(self):
        for line in sys.stdin:
            line = line.strip()
            if line == 'quit':
                break
            try:
                # Speech RMS is roughly 0.01-0.2; map it onto 0-1 on a log scale.
                rms = max(float(line), 1e-4)
                self.level = min(1.0, max(0.0, (math.log10(rms) + 2.3) / 1.6))
            except ValueError:
                pass
        GLib.idle_add(self.quit)

    def tick(self):
        # Fast attack, slow release, and a gentle idle wave so it reads as "listening".
        self.shown = self.level if self.level > self.shown else self.shown * 0.85 + self.level * 0.15
        self.phase += 0.25
        for i, bar in enumerate(self.bars):
            centre = 1.0 - abs(i - (BARS - 1) / 2) / BARS
            idle = 0.12 + 0.06 * math.sin(self.phase + i)
            height = 4 + 22 * max(idle, self.shown * centre)
            bar.set_size_request(4, int(height))
        return True


def main():
    if '--check' not in sys.argv and not compositor_supports_indicator():
        return UNSUPPORTED
    if '--check' in sys.argv:
        return 0 if compositor_supports_indicator() else UNSUPPORTED
    return Indicator().run([sys.argv[0]])


if __name__ == '__main__':
    sys.exit(main())
