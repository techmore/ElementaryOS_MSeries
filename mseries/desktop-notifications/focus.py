# SPDX-License-Identifier: GPL-3.0-or-later
"""Explicit-click focus bridge for BlueFerry on the M-Series compositor."""
import dbus

BLUEFERRY = 'io.weirdware.BlueFerry'
CLIENT = 'io.weirdware.BlueFerry.Gtk'


def trusted_target(bus, sender, hints):
    if str(hints.get('desktop-entry', '')) != CLIENT:
        return None
    try:
        return CLIENT if str(bus.get_name_owner(BLUEFERRY)) == str(sender) else None
    except dbus.DBusException:
        return None


def focus_existing(bus, target):
    """Focus only one existing matching client; never execute hint content."""
    if target != CLIENT:
        return
    proxy = bus.get_object('org.pantheon.gala',
                           '/org/pantheon/gala/DesktopInterface', introspect=False)
    interface = dbus.Interface(proxy, 'org.pantheon.gala.DesktopIntegration')

    def windows_received(windows):
        matches = [uid for uid, props in windows if str(props.get('app-id', '')) == target]
        if len(matches) == 1:
            interface.FocusWindow(matches[0], reply_handler=lambda: None,
                                  error_handler=lambda _error: None, timeout=2)

    interface.GetWindows(reply_handler=windows_received,
                         error_handler=lambda _error: None, timeout=2)
