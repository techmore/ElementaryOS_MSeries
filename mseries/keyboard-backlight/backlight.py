#!/usr/bin/python3
"""Ambient keyboard lighting for Pantheon via UPower; never touches display brightness."""
import argparse
import math
import os
from pathlib import Path
import time
from gi.repository import Gio, GLib


def percent(lux):
    return max(0, min(100, round(100 * (180 - lux) / 172)))


def illuminance(root=Path('/sys/bus/iio/devices')):
    for device in sorted(root.glob('iio:device*')):
        try:
            # Do not mistake Apple's adjacent lid-angle sensor for ALS.
            if not (device / 'name').read_text().strip().endswith('-als'):
                continue
            value = float((device / 'in_illuminance_input').read_text())
            if math.isfinite(value) and value >= 0:
                return value
        except (OSError, ValueError):
            continue
    raise OSError('No readable ambient illuminance sensor')


class Keyboard:
    def __init__(self):
        self.bus = Gio.bus_get_sync(Gio.BusType.SYSTEM, None)
        self.proxy = Gio.DBusProxy.new_sync(self.bus, Gio.DBusProxyFlags.NONE, None,
            'org.freedesktop.UPower', '/org/freedesktop/UPower/KbdBacklight',
            'org.freedesktop.UPower.KbdBacklight', None)
        self.maximum = self.call('GetMaxBrightness')
        if self.maximum <= 0:
            raise OSError('Keyboard backlight unavailable')

    def call(self, method, value=None):
        args = GLib.Variant('(i)', (value,)) if value is not None else None
        result = self.proxy.call_sync(method, args, Gio.DBusCallFlags.NONE, 2000, None).unpack()
        return result[0] if result else None

    def session_active(self):
        # Background/autostart processes may belong to a user manager, not a
        # login session. Check this user's graphical session through logind.
        result = self.bus.call_sync('org.freedesktop.login1', '/org/freedesktop/login1',
            'org.freedesktop.login1.Manager', 'ListSessions', None, None,
            Gio.DBusCallFlags.NONE, 2000, None)
        for _sid, uid, _user, _seat, path in result.unpack()[0]:
            if uid != os.getuid():
                continue
            props = self.bus.call_sync('org.freedesktop.login1', path,
                'org.freedesktop.DBus.Properties', 'GetAll',
                GLib.Variant('(s)', ('org.freedesktop.login1.Session',)), None,
                Gio.DBusCallFlags.NONE, 2000, None).unpack()[0]
            if props.get('Type') in ('wayland', 'x11') and props.get('Active', False):
                return not props.get('LockedHint', True)
        return False



def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--step', choices=('up', 'down'))
    parser.add_argument('--once', action='store_true')
    args = parser.parse_args()
    keyboard = Keyboard()
    if args.step:
        current = keyboard.call('GetBrightness')
        step = max(1, round(keyboard.maximum * .1))
        keyboard.call('SetBrightness', max(0, min(keyboard.maximum,
            current + (step if args.step == 'up' else -step))))
        return
    last = None
    paused_lux = None
    while True:
        try:
            lux = illuminance()
            current = keyboard.call('GetBrightness')
            if last is not None and current != last:
                paused_lux = lux
            last = current
            if paused_lux is not None and abs(lux - paused_lux) >= max(20, paused_lux * .4):
                paused_lux = None
            lid_closed = any('closed' in p.read_text() for p in Path('/proc/acpi/button/lid').glob('*/state'))
            if paused_lux is None and not lid_closed and keyboard.session_active():
                target = round(keyboard.maximum * percent(lux) / 100)
                if abs(current - target) >= max(1, keyboard.maximum * .04):
                    keyboard.call('SetBrightness', target)
                    last = keyboard.call('GetBrightness')
            if args.once:
                print(f'Ambient {lux:g} lx; keyboard {last}/{keyboard.maximum}')
        except (OSError, ValueError, GLib.Error) as error:
            if args.once:
                raise SystemExit(str(error))
            print(f'Keyboard lighting: {error}', flush=True)
        if args.once:
            return
        time.sleep(5)


if __name__ == '__main__':
    main()
