#!/usr/bin/python3
"""Small system-Python IBus bridge client; transcript travels on stdin, not argv."""
import sys
from gi.repository import Gio, GLib


def main():
    method = {'begin': 'Begin', 'commit': 'Commit', 'cancel': 'Cancel'}[sys.argv[1]]
    args = None
    if method == 'Commit':
        text = sys.stdin.read(4001)
        if len(text) > 4000:
            raise SystemExit('Dictation chunk too long')
        args = GLib.Variant('(ss)', (sys.argv[2], text))
    connection = Gio.bus_get_sync(Gio.BusType.SESSION, None)
    try:
        result = connection.call_sync('org.techmore.DictationInput', '/org/techmore/DictationInput',
            'org.techmore.DictationInput', method, args, None, Gio.DBusCallFlags.NO_AUTO_START, 2000, None)
    except GLib.Error:
        raise SystemExit('Dictation input unavailable, sensitive, cancelled or focus changed')
    if method == 'Begin':
        print(result.unpack()[0])


if __name__ == '__main__':
    main()
