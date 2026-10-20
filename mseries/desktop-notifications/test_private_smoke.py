#!/usr/bin/python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Explicit private display/bus smoke; never started by unit test discovery."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parent


def inside():
    if os.environ.get('MSERIES_PRIVATE_NOTIFICATION_SMOKE') != '1':
        raise RuntimeError('Run without arguments to create the private display and bus')
    import dbus
    from dbus.mainloop.glib import DBusGMainLoop
    DBusGMainLoop(set_as_default=True)
    from popup import Popups, Gtk, Gdk
    from notifications import Server, request_name, BUS, PATH

    def pump(until=lambda: False, timeout=1):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            while Gtk.events_pending():
                Gtk.main_iteration_do(False)
            from gi.repository import GLib
            context = GLib.MainContext.default()
            while context.pending():
                context.iteration(False)
            if until():
                return
            time.sleep(0.005)
        if not until():
            raise AssertionError('Private event loop timed out')

    if os.environ.get("MSERIES_SMOKE_DARK") == "1":
        Gtk.Settings.get_default().set_property("gtk-application-prefer-dark-theme", True)
    view = Popups()
    bus = dbus.SessionBus(private=True)
    name = request_name(bus)
    server = Server(bus, view)
    client = dbus.SessionBus(private=True)
    try:
        request_name(client)
    except dbus.exceptions.NameExistsException:
        pass
    else:
        raise AssertionError('Second server stole or queued the private name')
    proxy = client.get_object(BUS, PATH, introspect=False)
    iface = dbus.Interface(proxy, BUS)
    actions, closed, errors = [], [], []
    client.add_signal_receiver(lambda n, a: actions.append((int(n), str(a))),
                               signal_name='ActionInvoked', dbus_interface=BUS)
    client.add_signal_receiver(lambda n, r: closed.append((int(n), int(r))),
                               signal_name='NotificationClosed', dbus_interface=BUS)

    anchor = Gtk.Window(title='Private focus anchor')
    anchor.set_default_size(200, 100)
    anchor.show_all()
    pump(lambda: anchor.get_window() is not None)
    anchor_id = anchor.get_window().get_xid()
    subprocess.run(['xdotool', 'windowfocus', str(anchor_id)], check=True)
    focus = subprocess.check_output(['xdotool', 'getwindowfocus'], text=True).strip()

    def notify(replaces=0, timeout=0, title='Fixture title', body='Synthetic message only'):
        result = []
        iface.Notify('Fixture App', dbus.UInt32(replaces), '', title, body,
                     dbus.Array(['default', 'Open', 'reply', 'Reply'], signature='s'),
                     dbus.Dictionary({'omarchy-exec-argv': 'NEVER EXECUTE',
                                      'image-path': '/never/open/this'}, signature='sv'),
                     dbus.Int32(timeout), reply_handler=lambda n: result.append(int(n)),
                     error_handler=errors.append)
        pump(lambda: bool(result or errors))
        assert not errors, errors
        return result[0]

    ids = [notify(title='Title ' + str(n)) for n in range(3)]
    pump(lambda: len(view.windows) == 3)
    # Settle allocation and map events before measuring real X windows.
    for _ in range(40):
        pump(lambda: True)
        time.sleep(0.01)
    assert subprocess.check_output(['xdotool', 'getwindowfocus'], text=True).strip() == focus
    area = view.area()
    geometry = []
    for nid in reversed(ids):
        w = view.windows[nid][1]
        x, y = w.get_position()
        width, height = w.get_size()
        assert x >= area[0] and y >= area[1], (x, y, area)
        assert x + width <= area[0] + area[2], (x, width, area)
        assert y + height <= area[1] + area[3], (y, height, area)
        assert w.get_window().get_window_type() == Gdk.WindowType.TEMP
        geometry.append((x, y, width, height))
    assert geometry[0][0] + geometry[0][2] == area[0] + area[2] - 16, geometry
    assert geometry[0][1] + geometry[0][3] == area[1] + area[3] - 16, geometry
    assert all(geometry[i][1] - (geometry[i + 1][1] + geometry[i + 1][3]) >= 12
               for i in range(2)), geometry
    screenshot = os.environ.get('MSERIES_SMOKE_SCREENSHOT')
    if screenshot:
        view.display.sync()
        screen = Gdk.get_default_root_window()
        pixbuf = Gdk.pixbuf_get_from_window(screen, 0, 0, 1280, 800)
        pixbuf.savev(screenshot, 'png', [], [])

    def buttons(widget):
        result = [widget] if isinstance(widget, Gtk.Button) else []
        if isinstance(widget, Gtk.Container):
            for child in widget.get_children():
                result += buttons(child)
        return result

    reply = next(b for b in buttons(view.windows[ids[-1]][1])
                 if b.get_accessible().get_name() == 'Reply')
    wx, wy = view.windows[ids[-1]][1].get_position()
    bx, by = reply.translate_coordinates(view.windows[ids[-1]][1], 0, 0)
    allocation = reply.get_allocation()
    subprocess.run(["xdotool", "mousemove", "--sync",
                    str(wx + bx + allocation.width // 2),
                    str(wy + by + allocation.height // 2), "click", "1"], check=True)
    pump(lambda: (ids[-1], 'reply') in actions and (ids[-1], 4) in closed)
    assert (ids[-1], 4) in closed
    assert subprocess.check_output(['xdotool', 'getwindowfocus'], text=True).strip() == focus
    body = next(b for b in buttons(view.windows[ids[-2]][1])
                if isinstance(b.get_child(), Gtk.Box))
    body.clicked()
    pump(lambda: (ids[-2], 'default') in actions)
    assert actions == [(ids[-1], 'reply'), (ids[-2], 'default')], actions
    # Replacement, explicit close, expiry and DND all traverse real D-Bus dispatch.
    assert notify(replaces=ids[0], title='Replacement') == ids[0]
    result = []
    iface.CloseNotification(ids[0], reply_handler=lambda: result.append(True), error_handler=errors.append)
    pump(lambda: (ids[0], 3) in closed)
    expiring = notify(timeout=30)
    pump(lambda: (expiring, 1) in closed)
    if view.settings:
        view.settings.set_boolean('do-not-disturb', True)  # memory backend only
        suppressed = notify()
        pump(lambda: (suppressed, 4) in closed)
        assert not server.store.items and not view.windows
    assert not errors, errors
    print('PASS: private D-Bus dispatch, exact Reply/default signals, bounded stack,')
    print('      bottom-right geometry, unchanged X11 focus, close/expiry/DND; geometry:', geometry)
    server.store.clear()
    server.remove_from_connection()
    anchor.destroy()
    client.close()
    del name
    bus.close()


def main():
    if len(sys.argv) > 1:
        inside()
        return
    with tempfile.TemporaryDirectory(prefix='mseries-popup-smoke-') as scratch:
        env = dict(os.environ, MSERIES_PRIVATE_NOTIFICATION_SMOKE='1',
                   GDK_BACKEND='x11', GSETTINGS_BACKEND='memory', HOME=scratch,
                   XDG_CONFIG_HOME=scratch, XDG_STATE_HOME=scratch,
                   XDG_RUNTIME_DIR=scratch, PYTHONDONTWRITEBYTECODE='1')
        env.pop('DBUS_SESSION_BUS_ADDRESS', None)
        env.pop('DISPLAY', None)
        subprocess.run(['xvfb-run', '-a', '-s', '-screen 0 1280x800x24',
                        'dbus-run-session', '--config-file=' + str(ROOT / 'test-bus.conf'),
                        sys.executable, str(Path(__file__).resolve()), '--inside'],
                       env=env, check=True, timeout=25)


if __name__ == '__main__':
    main()
