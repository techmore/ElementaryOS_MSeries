#!/usr/bin/python3
"""Small system-Python IBus bridge client; transcript travels on stdin, not argv."""
import sys
from gi.repository import Gio, GLib


def main():
    if sys.argv[1] == 'select':
        import gi
        gi.require_version('IBus', '1.0')
        from gi.repository import IBus
        IBus.init(); bus = IBus.Bus.new()
        name = sys.argv[2] if len(sys.argv) > 2 else 'mseries-dictation'
        if not bus.is_connected() or not bus.set_global_engine(name):
            raise SystemExit('Could not select the dictation input method')
        current = bus.get_global_engine()
        if current is None or current.get_name() != name:
            raise SystemExit('Input method selection did not remain active')
        return
    method = {'begin': 'Begin', 'commit': 'Commit', 'cancel': 'Cancel', 'finish': 'Finish', 'ready': 'Ready'}[sys.argv[1]]
    args = None
    if method == 'Commit':
        text = sys.stdin.read(4001)
        if len(text) > 4000:
            raise SystemExit('Dictation chunk too long')
        args = GLib.Variant('(ss)', (sys.argv[2], text))
    if method == 'Finish': args = GLib.Variant('(s)', (sys.argv[2],))
    connection = Gio.bus_get_sync(Gio.BusType.SESSION, None)
    try:
        result = connection.call_sync('org.techmore.DictationInput', '/org/techmore/DictationInput',
            'org.techmore.DictationInput', method, args, None, Gio.DBusCallFlags.NO_AUTO_START, 4000, None)
    except GLib.Error:
        raise SystemExit('Dictation input unavailable, sensitive, cancelled or focus changed')
    if method == 'Ready' and not result.unpack()[0]: raise SystemExit('Dictation input is not ready')
    if method == 'Begin':
        print(result.unpack()[0])


if __name__ == '__main__':
    main()
