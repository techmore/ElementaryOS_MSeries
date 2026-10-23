#!/usr/bin/python3
"""Idle and power-save checks against a nested pantheon-compositor (run by run.sh).

Uses GnomeDesktop.IdleMonitor, the libgnome-desktop-4 client gsd-power uses,
so discovery through the ObjectManager is exercised exactly as in a session.
Input is injected into the nested window with xdotool on $HOST_DISPLAY.

  1. an idle watch fires after ~1.5 s without input;
  2. a user-active watch fires on input, and idle time drops back near zero;
  3. a GTK 4 window inhibiting idle (zwp_idle_inhibit_v1) holds idle time at
     zero; after it uninhibits, the idle watch fires again;
  4. DisplayConfig PowerSaveMode=3 reads back 3; input wakes it back to 0,
     and a blank right after input does not lock;
  5. a blank after more than 5 s idle locks (PANTHEON_IDLE_LOCK=0 in run.sh)
     with the real gtklock, and once woken, typing on the lock screen gets
     frame callbacks (it used to draw one frame and then freeze).
Prints one RESULT line per check.
"""
import os
import re
import subprocess
import sys
import time
from pathlib import Path

import gi

gi.require_version('GnomeDesktop', '4.0')
gi.require_version('Gtk', '4.0')
from gi.repository import Gio, GLib, GnomeDesktop, Gtk  # noqa: E402

HOST_DISPLAY = os.environ['HOST_DISPLAY']
results = []
loop = GLib.MainLoop()


def focus_nested_window(env):
    """Give the nested compositor's X window keyboard focus (Xvfb has no WM)."""
    windows = subprocess.run(['xdotool', 'search', '--pid', os.environ['COMP_PID']],
                             env=env, capture_output=True, text=True).stdout.split()
    for window in windows:
        subprocess.run(['xdotool', 'windowfocus', window], env=env, capture_output=True)


def poke():
    env = dict(os.environ, DISPLAY=HOST_DISPLAY)
    focus_nested_window(env)
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


def screensaver_active(bus):
    reply = bus.call_sync('org.gnome.ScreenSaver', '/org/gnome/ScreenSaver', 'org.gnome.ScreenSaver',
                          'GetActive', None, GLib.VariantType('(b)'), Gio.DBusCallFlags.NONE, 2000, None)
    return reply.unpack()[0]


def set_mode(bus, mode):
    bus.call_sync('org.gnome.Mutter.DisplayConfig', '/org/gnome/Mutter/DisplayConfig',
                  'org.freedesktop.DBus.Properties', 'Set',
                  GLib.Variant('(ssv)', ('org.gnome.Mutter.DisplayConfig', 'PowerSaveMode', GLib.Variant('i', mode))),
                  None, Gio.DBusCallFlags.NONE, 2000, None)


def type_text(text):
    env = dict(os.environ, DISPLAY=HOST_DISPLAY)
    focus_nested_window(env)
    subprocess.run(['xdotool', 'type', '--delay', '120', text], env=env, check=False)


def key_events(log):
    """wl_keyboard.key events the locker has received (WAYLAND_DEBUG=1 log)."""
    try:
        return len(re.findall(r'wl_keyboard#?@?\d+\.key\(', log.read_text(errors='replace')))
    except OSError:
        return 0


def frame_dones(log):
    """wl_callback.done events the locker has received (WAYLAND_DEBUG=1 log)."""
    try:
        return len(re.findall(r'wl_callback#?@?\d+\.done\(', log.read_text(errors='replace')))
    except OSError:
        return 0


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
    poke()  # a blank right after input is not an idle blank, so it must not lock
    set_mode(bus, 3)
    off = wait_until(lambda: get_mode() == 3, 3)
    wait_until(lambda: False, 1)
    locked_after_manual_blank = screensaver_active(bus)
    poke()
    on = wait_until(lambda: get_mode() == 0, 3)
    wait_until(lambda: len(changes) >= 2, 1)
    result('power-save', off and on and not locked_after_manual_blank,
           f'off={off} woke_on_input={on} signals={changes} locked={locked_after_manual_blank}')

    # 5. idle blank locks; the lock screen then keeps drawing while typing
    wait_until(lambda: False, 6)  # idle for more than the 5 s threshold
    set_mode(bus, 3)
    locked = wait_until(lambda: screensaver_active(bus), 10)
    lock_log = Path(os.environ['LOCK_LOG'])
    poke()
    woke = wait_until(lambda: get_mode() == 0, 3)
    wait_until(lambda: False, 1.5)
    before, keys_before = frame_dones(lock_log), key_events(lock_log)
    type_text('abcdef')
    wait_until(lambda: False, 1.5)
    after, keys_after = frame_dones(lock_log), key_events(lock_log)
    keys = keys_after - keys_before
    result('idle-lock', locked and woke and keys >= 12 and after > before,
           f'locked={locked} woke={woke} key events reaching the lock screen={keys} '
           f'frame callbacks while typing={after - before}')

    window.destroy()
    sys.exit(0 if all(results) else 1)


if __name__ == '__main__':
    main()
