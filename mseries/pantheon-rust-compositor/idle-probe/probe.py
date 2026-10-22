#!/usr/bin/python3
"""Idle and power-save checks against a nested pantheon-compositor (run by run.sh).

Uses GnomeDesktop.IdleMonitor, the libgnome-desktop-4 client gsd-power uses,
so discovery through the ObjectManager is exercised exactly as in a session.
Input is injected into the nested window with xdotool on $HOST_DISPLAY.

  1. an idle watch fires after ~1.5 s without input;
  2. a user-active watch fires on input, and idle time drops back near zero;
  3. a GTK 4 window inhibiting idle (zwp_idle_inhibit_v1) holds idle time at
     zero; after it uninhibits, the idle watch fires again;
  4. DisplayConfig PowerSaveMode=3 reads back 3; input wakes it back to 0.
Prints one RESULT line per check.
"""
import os
import subprocess
import sys
import time

import gi

gi.require_version('GnomeDesktop', '4.0')
gi.require_version('Gtk', '4.0')
from gi.repository import Gio, GLib, GnomeDesktop, Gtk  # noqa: E402

HOST_DISPLAY = os.environ['HOST_DISPLAY']
results = []
loop = GLib.MainLoop()


def poke():
    env = dict(os.environ, DISPLAY=HOST_DISPLAY)
    for x, y in ((300, 300), (320, 330), (350, 340)):
        subprocess.run(['xdotool', 'mousemove', str(x), str(y)], env=env, check=False)


def result(name, ok, detail):
    results.append(ok)
    print(f'RESULT {name} {"ok" if ok else "FAIL"} {detail}', flush=True)


def wait_until(predicate, seconds):
    deadline = time.monotonic() + seconds
    context = loop.get_context()
    while time.monotonic() < deadline:
        if predicate():
            return True
        context.iteration(False)
        time.sleep(0.01)
    return predicate()


def main():
    Gtk.init()
    monitor = GnomeDesktop.IdleMonitor.new()
    bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)

    # 1. idle watch, counted from fresh input (a watch whose interval has
    #    already passed fires at once, as in Mutter)
    fired = []
    wait_until(lambda: False, 0.5)  # let the monitor connect through the ObjectManager
    poke()
    started = time.monotonic()
    watch = monitor.add_idle_watch(1500, lambda m, wid: fired.append(time.monotonic() - started))
    ok = wait_until(lambda: fired, 6)
    result('idle-watch', ok and 1.3 <= fired[0] <= 4.0,
           f'fired after {fired[0]:.2f}s' if fired else 'never fired')

    # 2. user-active watch
    active = []
    monitor.add_user_active_watch(lambda m, wid: active.append(True))
    poke()
    ok = wait_until(lambda: active, 5)
    idletime = monitor.get_idletime()
    result('user-active', ok and idletime < 1500, f'fired={ok} idletime={idletime}ms')

    # 3. inhibitor: GtkApplication.inhibit(IDLE) on Wayland uses zwp_idle_inhibit_v1
    app = Gtk.Application(application_id='org.techmore.IdleProbe', flags=Gio.ApplicationFlags.NON_UNIQUE)
    app.register(None)
    window = Gtk.Window(title='idle-inhibitor', application=app)
    window.set_default_size(200, 120)
    window.present()
    wait_until(lambda: window.get_mapped(), 5)
    poke()
    wait_until(lambda: False, 0.3)
    fired.clear()
    cookie = app.inhibit(window, Gtk.ApplicationInhibitFlags.IDLE, 'idle probe')
    wait_until(lambda: False, 2.5)
    idle_while_inhibited = monitor.get_idletime()
    held = not fired and idle_while_inhibited < 500
    if cookie:
        app.uninhibit(cookie)
    fired_after = wait_until(lambda: fired, 4)
    result('inhibitor', held and fired_after,
           f'cookie={cookie} idletime_while_inhibited={idle_while_inhibited}ms '
           f'fired_while_inhibited={not held} fired_after_uninhibit={fired_after}')
    monitor.remove_watch(watch)

    # 4. power save
    def get_mode():
        reply = bus.call_sync('org.gnome.Mutter.DisplayConfig', '/org/gnome/Mutter/DisplayConfig',
                              'org.freedesktop.DBus.Properties', 'Get',
                              GLib.Variant('(ss)', ('org.gnome.Mutter.DisplayConfig', 'PowerSaveMode')),
                              GLib.VariantType('(v)'), Gio.DBusCallFlags.NONE, 2000, None)
        return reply.unpack()[0]

    changes = []
    bus.signal_subscribe('org.gnome.Mutter.DisplayConfig', 'org.freedesktop.DBus.Properties',
                         'PropertiesChanged', '/org/gnome/Mutter/DisplayConfig', None,
                         Gio.DBusSignalFlags.NONE,
                         lambda *args: changes.append(args[5].unpack()[1].get('PowerSaveMode')), )
    bus.call_sync('org.gnome.Mutter.DisplayConfig', '/org/gnome/Mutter/DisplayConfig',
                  'org.freedesktop.DBus.Properties', 'Set',
                  GLib.Variant('(ssv)', ('org.gnome.Mutter.DisplayConfig', 'PowerSaveMode', GLib.Variant('i', 3))),
                  None, Gio.DBusCallFlags.NONE, 2000, None)
    off = wait_until(lambda: get_mode() == 3, 3)
    poke()
    on = wait_until(lambda: get_mode() == 0, 3)
    wait_until(lambda: len(changes) >= 2, 1)
    result('power-save', off and on, f'off={off} woke_on_input={on} signals={changes}')

    window.destroy()
    sys.exit(0 if all(results) else 1)


if __name__ == '__main__':
    main()
