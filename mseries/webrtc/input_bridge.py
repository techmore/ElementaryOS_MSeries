#!/usr/bin/python3
"""Mutter 50 input adapter. Only its parent reads network input; no listener here."""
import json
import math
import os
import select
import signal
import sys

KEYS = {'Enter': 0xff0d, 'Backspace': 0xff08, 'Tab': 0xff09, 'Escape': 0xff1b,
        'Delete': 0xffff, 'ArrowLeft': 0xff51, 'ArrowUp': 0xff52,
        'ArrowRight': 0xff53, 'ArrowDown': 0xff54, 'Home': 0xff50, 'End': 0xff57,
        'PageUp': 0xff55, 'PageDown': 0xff56}
MODIFIERS = {'ctrl': 0xffe3, 'alt': 0xffe9, 'shift': 0xffe1, 'meta': 0xffeb}


def keysym(key):
    if key in KEYS:
        return KEYS[key]
    if isinstance(key, str) and len(key) == 1 and ord(key) >= 32:
        point = ord(key)
        return point if point <= 0xff else 0x01000000 | point
    raise ValueError('Unsupported key')


def dispatch(event, backend):
    """Strict bounded events; key/chord and click are always released atomically."""
    if not isinstance(event, dict):
        raise ValueError('Invalid input')
    kind = event.get('kind')
    if kind in ('move', 'scroll'):
        values = [event.get('dx'), event.get('dy')]
        if any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) or abs(v) > 1000 for v in values):
            raise ValueError('Invalid motion')
        backend.motion(kind, *values)
    elif kind == 'click':
        button = event.get('button', 'left')
        if button not in ('left', 'right'):
            raise ValueError('Invalid button')
        backend.click(272 if button == 'left' else 273)
    elif kind in ('key', 'text'):
        text = event.get('key') if kind == 'key' else event.get('text')
        if not isinstance(text, str) or not text or len(text) > (32 if kind == 'key' else 512):
            raise ValueError('Invalid text')
        mods = event.get('modifiers', []) if kind == 'key' else []
        if not isinstance(mods, list) or len(mods) > 4 or len(set(mods)) != len(mods) or any(m not in MODIFIERS for m in mods):
            raise ValueError('Invalid modifiers')
        codes = [keysym(text)] if kind == 'key' else [KEYS['Enter'] if k == '\n' else KEYS['Tab'] if k == '\t' else keysym(k) for k in text]
        backend.keys(codes, [MODIFIERS[m] for m in mods])
    else:
        raise ValueError('Invalid input kind')


class Mutter:
    def __init__(self):
        from gi.repository import Gio, GLib
        self.Gio, self.GLib = Gio, GLib
        self.session = Gio.bus_get_sync(Gio.BusType.SESSION, None)
        self.system = Gio.bus_get_sync(Gio.BusType.SYSTEM, None)
        self.path = None
        sessions = self.call(self.system, 'org.freedesktop.login1', '/org/freedesktop/login1',
                             'org.freedesktop.login1.Manager', 'ListSessions', None)[0]
        matches = []
        for _id, uid, _name, _seat, path in sessions:
            if uid != os.getuid():
                continue
            props = self.call(self.system, 'org.freedesktop.login1', path,
                              'org.freedesktop.DBus.Properties', 'GetAll', GLib.Variant('(s)', ('org.freedesktop.login1.Session',)))[0]
            if props.get('Active') and props.get('Type') == 'wayland':
                matches.append(path)
        if len(matches) != 1:
            raise RuntimeError('Control needs exactly one active Wayland session for this user')
        self.login_path = matches[0]
        self.check_unlocked()
        self.path = self.call(self.session, 'org.gnome.Mutter.RemoteDesktop', '/org/gnome/Mutter/RemoteDesktop',
                              'org.gnome.Mutter.RemoteDesktop', 'CreateSession', None)[0]
        self.remote('Start')

    def call(self, bus, name, path, interface, method, args):
        return bus.call_sync(name, path, interface, method, args, None,
                             self.Gio.DBusCallFlags.NONE, 1000, None).unpack()

    def check_unlocked(self):
        props = self.call(self.system, 'org.freedesktop.login1', self.login_path,
                          'org.freedesktop.DBus.Properties', 'GetAll',
                          self.GLib.Variant('(s)', ('org.freedesktop.login1.Session',)))[0]
        if props.get('LockedHint', True) or not props.get('Active'):
            raise RuntimeError('Desktop locked or inactive; enable control again after unlocking')

    def remote(self, method, signature=None, values=()):
        return self.call(self.session, 'org.gnome.Mutter.RemoteDesktop', self.path,
                         'org.gnome.Mutter.RemoteDesktop.Session', method,
                         self.GLib.Variant(signature, values) if signature else None)

    def motion(self, kind, dx, dy):
        if kind == 'move':
            self.remote('NotifyPointerMotionRelative', '(dd)', (float(dx), float(dy)))
        else:
            self.remote('NotifyPointerAxis', '(ddu)', (float(dx), float(dy), 2))

    def click(self, button):
        try:
            self.remote('NotifyPointerButton', '(ib)', (button, True))
        finally:
            self.remote('NotifyPointerButton', '(ib)', (button, False))

    def keys(self, codes, modifiers):
        pressed = []
        try:
            for code in modifiers:
                self.remote('NotifyKeyboardKeysym', '(ub)', (code, True)); pressed.append(code)
            for code in codes:
                self.check_unlocked()
                try:
                    self.remote('NotifyKeyboardKeysym', '(ub)', (code, True))
                finally:
                    self.remote('NotifyKeyboardKeysym', '(ub)', (code, False))
        finally:
            for code in reversed(pressed):
                self.remote('NotifyKeyboardKeysym', '(ub)', (code, False))

    def stop(self):
        if self.path:
            try:
                self.remote('Stop')
            except Exception:
                pass


def main():
    backend = None
    def interrupted(*_args):
        raise SystemExit(0)
    signal.signal(signal.SIGTERM, interrupted)
    try:
        backend = Mutter()
        print(json.dumps({'ready': True}), flush=True)
        pending = b''
        while True:
            backend.check_unlocked()
            readable, _, _ = select.select([sys.stdin], [], [], 1)
            if not readable:
                continue
            chunk = os.read(sys.stdin.fileno(), 8192)
            if not chunk:
                break
            pending += chunk
            while b'\n' in pending:
                line, pending = pending.split(b'\n', 1)
                if len(line) > 8192:
                    raise ValueError('Input too large')
                backend.check_unlocked()
                dispatch(json.loads(line), backend)
            if len(pending) > 8192:
                raise ValueError('Input too large')
    except Exception as error:
        print(json.dumps({'error': str(error)[:256]}), flush=True)
        return 1
    finally:
        if backend:
            backend.stop()
    return 0


if __name__ == '__main__':
    sys.exit(main())
