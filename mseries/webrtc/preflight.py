#!/usr/bin/python3
"""Read-only deployment checks. Never opens a capture/input session or reads keys."""
import argparse
import json
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
import sys
import urllib.request
from urllib.parse import urlsplit


def http_health(url):
    parsed = urlsplit(url)
    if parsed.username or parsed.password or parsed.fragment or parsed.scheme not in ('http', 'https'):
        raise ValueError('Health URL must not contain credentials or fragments')
    if parsed.scheme == 'http' and parsed.hostname not in ('localhost', '127.0.0.1', '::1'):
        raise ValueError('Use verified HTTPS outside localhost')
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, *args):
            return None
    opener = urllib.request.build_opener(NoRedirect)
    with opener.open(url, timeout=4) as response:
        response.read(4097)
        if response.status != 200:
            raise ValueError('Health returned a non-200 status')
    return 'HTTP 200 with standard TLS verification'


def report(gateway=None):
    checks = []
    def check(name, callback):
        try:
            detail = callback()
            checks.append({'name': name, 'ok': True, 'detail': detail})
        except Exception as error:
            checks.append({'name': name, 'ok': False, 'detail': str(error)[:250]})
    def linux():
        if platform.system() != 'Linux':
            raise ValueError('Run the desktop checks after booting ElementaryOS Linux')
        return platform.machine()
    check('Linux desktop', linux)
    def node():
        executable = shutil.which('node')
        if not executable:
            raise ValueError('Install Node.js 22 or newer')
        result = subprocess.run([executable, '--version'], text=True, capture_output=True, timeout=3, check=True)
        version = result.stdout.strip()
        if not re.fullmatch(r'v\d+\.\d+\.\d+', version) or int(version.split('.')[0][1:]) < 22:
            raise ValueError('Node.js 22 or newer is required')
        return version
    check('Node runtime', node)
    def portal():
        paths = [Path('/usr/share/xdg-desktop-portal/portals/pantheon.portal'), Path('/usr/local/share/xdg-desktop-portal/portals/pantheon.portal')]
        for path in paths:
            if path.is_file() and 'org.freedesktop.impl.portal.ScreenCast' in path.read_text():
                return 'Pantheon ScreenCast portal declaration present'
        raise ValueError('Pantheon ScreenCast portal missing; check xdg-desktop-portal-pantheon')
    check('Pantheon screen capture', portal)
    def desktop_bus():
        from gi.repository import Gio, GLib
        session = Gio.bus_get_sync(Gio.BusType.SESSION, None)
        def call(bus, name, path, interface, method, args):
            return bus.call_sync(name, path, interface, method, args, None, Gio.DBusCallFlags.NONE, 1500, None).unpack()
        for name in ('org.gnome.Mutter.ScreenCast', 'org.gnome.Mutter.RemoteDesktop'):
            owned = call(session, 'org.freedesktop.DBus', '/org/freedesktop/DBus', 'org.freedesktop.DBus', 'NameHasOwner', GLib.Variant('(s)', (name,)))[0]
            if not owned:
                raise ValueError(name + ' is not running in this graphical session')
        system = Gio.bus_get_sync(Gio.BusType.SYSTEM, None)
        sessions = call(system, 'org.freedesktop.login1', '/org/freedesktop/login1', 'org.freedesktop.login1.Manager', 'ListSessions', None)[0]
        active = []
        for _id, uid, _name, _seat, path in sessions:
            if uid == os.getuid():
                props = call(system, 'org.freedesktop.login1', path, 'org.freedesktop.DBus.Properties', 'GetAll', GLib.Variant('(s)', ('org.freedesktop.login1.Session',)))[0]
                if props.get('Type') == 'wayland' and props.get('Active'):
                    active.append(props)
        if len(active) != 1 or active[0].get('LockedHint', True):
            raise ValueError('Needs exactly one active, unlocked Wayland session for this user')
        return 'ScreenCast/RemoteDesktop owned; active unlocked Wayland session. No input/capture session opened.'
    check('Compositor and lock state', desktop_bus)
    check('Local sharing service', lambda: http_health('http://127.0.0.1:8789/health'))
    if gateway:
        check('Public HTTPS gateway', lambda: http_health(gateway))
    return {'checks': checks, 'ready_for_manual_acceptance': all(c['ok'] for c in checks),
            'qualification': 'Read-only prerequisites only; approve real capture and test phone input/lock, recording, LAN and cellular next.'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--gateway', help='Optional exact HTTPS health URL (no tokens)')
    args = parser.parse_args()
    result = report(args.gateway)
    print(json.dumps(result, indent=2))
    return 0 if result['ready_for_manual_acceptance'] else 1


if __name__ == '__main__':
    sys.exit(main())
