#!/usr/bin/python3
"""Explicit window recovery through Pantheon's existing desktop interface."""
import argparse
import json
import subprocess
import sys

from gi.repository import Gio, GLib

BUS = 'org.pantheon.gala'
PATH = '/org/pantheon/gala/DesktopInterface'
INTERFACE = 'org.pantheon.gala.DesktopIntegration'


def call(method, parameters=None, result_type=None):
    return Gio.bus_get_sync(Gio.BusType.SESSION, None).call_sync(
        BUS, PATH, INTERFACE, method, parameters,
        GLib.VariantType.new(result_type) if result_type else None,
        Gio.DBusCallFlags.NONE, 3000, None)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--list', action='store_true', help='list recoverable windows as JSON')
    parser.add_argument('--focus', type=int, metavar='UID', help='restore and focus a chosen window')
    args = parser.parse_args()
    windows = call('GetWindows', result_type='(a(ta{sv}))').unpack()[0]
    if args.list:
        print(json.dumps([{'uid': uid, **properties} for uid, properties in windows]))
        return 0
    # Never exercise the known mixed-client focus bug in an older live session.
    try:
        Gio.bus_get_sync(Gio.BusType.SESSION, None).call_sync(
            BUS, PATH, 'org.freedesktop.DBus.Properties', 'Get',
            GLib.Variant('(ss)', (INTERFACE, 'FocusRoutingVersion')), None,
            Gio.DBusCallFlags.NONE, 3000, None)
    except GLib.Error:
        print('A fresh login is required to load the window focus fix before recovery.', file=sys.stderr)
        return 1
    if args.focus is not None:
        if args.focus not in {uid for uid, _ in windows}:
            parser.error('window is no longer available')
        call('FocusWindow', GLib.Variant('(t)', (args.focus,)))
        return 0
    if not windows:
        print('No application windows are available.', file=sys.stderr)
        return 0
    rows = []
    for uid, properties in windows:
        rows.extend([str(uid), properties.get('title') or properties.get('app-id', 'Application'),
                     properties.get('app-id', 'Application'), str(properties.get('workspace-index', 0) + 1)])
    result = subprocess.run([
        'zenity', '--list', '--title=Restore Application Windows',
        '--text=Choose a window to restore and focus.', '--width=560', '--height=360',
        '--column=ID', '--column=Window', '--column=Application', '--column=Workspace',
        '--hide-column=1', '--print-column=1', *rows,
    ], text=True, capture_output=True)
    if result.returncode == 0 and result.stdout.strip():
        uid = int(result.stdout.strip())
        if uid in {item[0] for item in windows}:
            call('FocusWindow', GLib.Variant('(t)', (uid,)))
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except GLib.Error as error:
        print(f'Window recovery failed: {error.message}', file=sys.stderr)
        raise SystemExit(1)
