# SPDX-License-Identifier: GPL-3.0-or-later
"""Native taskbar notification center API. No phone writes or message sends."""
import json
import os
import re
import subprocess

import dbus
import dbus.service
from gi.repository import Gio, GLib

from focus import CLIENT, focus_existing, trusted_target
from history import History

INTERFACE = 'org.techmore.MSeries.Notifications1'
PATH = '/org/techmore/MSeries/Notifications'


def desktop_id(hints):
    value = str(hints.get('desktop-entry', ''))
    return value if re.fullmatch(r'[A-Za-z0-9_.-]{1,200}', value) else ''


def message_handle(hints, trusted):
    if not trusted:
        return ''
    try:
        raw = str(hints.get('omarchy-exec-argv', ''))
        if len(raw) > 4096:
            return ''
        argv = json.loads(raw)
        if (not isinstance(argv, list) or len(argv) != 4 or argv[1:3] !=
                ['-m', 'blueferry.client_activation']):
            return ''
        value = argv[3]
        if not isinstance(value, str) or not value.startswith('--message='):
            return ''
        value = value[len('--message='):]
        return value if re.fullmatch(r'[A-Za-z0-9_-]{1,1024}', value) else ''
    except (ValueError, TypeError):
        return ''


class Center(dbus.service.Object):
    def __init__(self, bus, server, view):
        self.bus, self.server, self.view = bus, server, view
        self.history = History()
        super().__init__(bus, PATH)
        if view.settings is not None:
            view.settings.connect('changed::do-not-disturb', lambda *_args: self.Changed())

    def remember(self, nid, app, summary, body, actions, hints, sender):
        trusted = trusted_target(self.bus, sender, hints)
        self.history.add(nid, app, summary, body, actions, desktop_id(hints),
                         message_handle(hints, trusted))
        self.Changed()

    @dbus.service.method(INTERFACE, in_signature='', out_signature='s')
    def GetStatus(self):
        return json.dumps(dict(unread=self.history.unread, dnd=self.view.muted()))

    @dbus.service.method(INTERFACE, in_signature='u', out_signature='s')
    def ListNotifications(self, limit):
        return json.dumps(self.history.list(limit, self.server.store.items))

    @dbus.service.method(INTERFACE, in_signature='', out_signature='u')
    def MarkAllRead(self):
        count = self.history.mark_all_read()
        # Reason 4 clears desktop popups without asking BlueFerry to mark phone
        # messages read (which it does for deliberate dismissal, reason 2).
        self.server.store.clear()
        self.Changed()
        return count

    @dbus.service.method(INTERFACE, in_signature='b', out_signature='b')
    def SetDoNotDisturb(self, enabled):
        if self.view.settings is None:
            raise dbus.DBusException('Desktop DND settings are unavailable',
                                     name=INTERFACE + '.Unavailable')
        if not self.view.settings.set_boolean('do-not-disturb', bool(enabled)):
            raise dbus.DBusException('Could not save Do Not Disturb',
                                     name=INTERFACE + '.SaveFailed')
        self.Changed()
        return self.view.muted()

    @dbus.service.method(INTERFACE, in_signature='u', out_signature='b')
    def OpenNotification(self, nid):
        return self.InvokeAction(nid, 'default')

    @dbus.service.method(INTERFACE, in_signature='us', out_signature='b')
    def InvokeAction(self, nid, action):
        nid, action = int(nid), str(action)
        entry = self.history.entries.get(nid)
        if entry is None or action not in ('default', 'reply'):
            return False
        if action == 'reply' and 'reply' not in entry['actions']:
            return False
        if nid in self.server.store.items and action in entry['actions']:
            self.server.store.activate(nid, action)
            return True
        if entry['handle']:
            # Fixed installed helper and one validated opaque handle. None of
            # the notification's executable argv is ever executed.
            environment = dict(os.environ)
            environment.pop('GDK_BACKEND', None)
            try:
                subprocess.Popen(['/usr/bin/python3', '-m', 'blueferry.client_activation',
                                  '--message=' + entry['handle']], env=environment,
                                 stdin=subprocess.DEVNULL, start_new_session=True)
            except OSError:
                return False
            self._focus_later()
        elif action == 'default' and entry['desktop']:
            name = entry['desktop']
            info = Gio.DesktopAppInfo.new(name if name.endswith('.desktop') else name + '.desktop')
            if info is None:
                return False
            try:
                info.launch([], None)
            except GLib.Error:
                return False
        else:
            return False
        self.history.read(nid)
        self.Changed()
        return True

    def _focus_later(self):
        def raise_client():
            try:
                focus_existing(self.bus, CLIENT)
            except dbus.DBusException:
                pass
            return False
        GLib.timeout_add(350, raise_client)

    def read(self, nid):
        self.history.read(nid)
        self.Changed()

    @dbus.service.signal(INTERFACE, signature='')
    def Changed(self):
        pass
