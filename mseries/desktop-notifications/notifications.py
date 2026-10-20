#!/usr/bin/python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Ephemeral X11 desktop notification service; explicit execution only."""
import argparse
import sys

import dbus
import dbus.service
from dbus.mainloop.glib import DBusGMainLoop
from gi.repository import GLib
from model import Store

BUS = 'org.freedesktop.Notifications'
PATH = '/org/freedesktop/Notifications'


class Server(dbus.service.Object):
    def __init__(self, bus, view, schedule=GLib.timeout_add, cancel=GLib.source_remove):
        self.view = view
        self.store = Store(schedule, cancel, view.render,
                           self.NotificationClosed, self.ActionInvoked, view.muted)
        view.store = self.store
        super().__init__(bus, PATH)

    @dbus.service.method(BUS, in_signature='', out_signature='as')
    def GetCapabilities(self):
        return ['actions', 'body']

    @dbus.service.method(BUS, in_signature='', out_signature='ssss')
    def GetServerInformation(self):
        return ('M-Series Desktop Notifications', 'M-Series', '0.1.0', '1.2')

    @dbus.service.method(BUS, in_signature='susssasa{sv}i', out_signature='u', sender_keyword='sender')
    def Notify(self, app_name, replaces_id, app_icon, summary, body, actions,
               hints, expire_timeout, sender=None):
        # No hints or icon paths are opened or executed. Actions are returned to
        # clients, which alone decide how to activate their own applications.
        return self.store.notify(str(sender), replaces_id, app_name, summary,
                                 body, actions, expire_timeout)

    @dbus.service.method(BUS, in_signature='u', out_signature='', sender_keyword='sender')
    def CloseNotification(self, nid, sender=None):
        self.store.close(int(nid), 3, owner=str(sender))

    @dbus.service.signal(BUS, signature='us')
    def ActionInvoked(self, nid, key):
        pass

    @dbus.service.signal(BUS, signature='uu')
    def NotificationClosed(self, nid, reason):
        pass


def request_name(bus, replace=False):
    # Never queue behind or replace another daemon without an explicit flag.
    return dbus.service.BusName(BUS, bus=bus, allow_replacement=False,
                                replace_existing=replace, do_not_queue=True)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--replace', action='store_true',
                        help='explicitly request replacement if the current owner permits it')
    args = parser.parse_args(argv)
    # GTK is imported only on an explicit launch; tests can import dispatch safely.
    from popup import Popups, Gtk
    DBusGMainLoop(set_as_default=True)
    view = Popups()  # Fail before bus ownership when display is not X11.
    bus = dbus.SessionBus()
    try:
        name = request_name(bus, args.replace)
    except dbus.exceptions.NameExistsException:
        print('Another notification server owns the bus; no replacement performed.', file=sys.stderr)
        return 1
    server = Server(bus, view)
    # Keep ownership and export alive until the toolkit loop ends.
    try:
        Gtk.main()
    finally:
        server.store.clear()
        server.remove_from_connection()
        del name
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
