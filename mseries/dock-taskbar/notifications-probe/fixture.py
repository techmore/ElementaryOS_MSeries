#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0
"""Synthetic Notifications1 service, run only inside run.sh's private bus."""
import json
import os
from pathlib import Path
import sys

from gi.repository import Gio, GLib

BUS = "org.freedesktop.Notifications"
PATH = "/org/techmore/MSeries/Notifications"
IFACE = "org.techmore.MSeries.Notifications1"
XML = """<node><interface name="org.techmore.MSeries.Notifications1">
  <method name="GetStatus"><arg type="s" direction="out"/></method>
  <method name="ListNotifications"><arg type="u" direction="in"/><arg type="s" direction="out"/></method>
  <method name="MarkAllRead"><arg type="u" direction="out"/></method>
  <method name="SetDoNotDisturb"><arg type="b" direction="in"/><arg type="b" direction="out"/></method>
  <method name="OpenNotification"><arg type="u" direction="in"/><arg type="b" direction="out"/></method>
  <method name="InvokeAction"><arg type="u" direction="in"/><arg type="s" direction="in"/><arg type="b" direction="out"/></method>
  <signal name="Changed"/>
</interface></node>"""
state = {"unread": 2, "dnd": True}
reject_dnd = True
calls = set()


def call(conn, sender, path, iface, method, args, invocation):
    global reject_dnd
    print(method, args.unpack(), flush=True)
    calls.add(method)
    if method == "GetStatus":
        result = GLib.Variant("(s)", (json.dumps(state),))
    elif method == "ListNotifications":
        assert args.unpack() == (50,)
        rows = [] if state["unread"] == 0 else [dict(
            id=7, app="Fixture", summary="A new message is ready",
            body="Open the conversation to read or reply.", received_at=1792500000,
            read=False, open_available=True, can_reply=True), dict(
            id=8, app="Long-text fixture", summary="Long synthetic summary " * 10,
            body="Synthetic body <b>literal</b> " * 40, received_at=1792499700,
            read=False, open_available=False, can_reply=False)]
        result = GLib.Variant("(s)", (json.dumps(rows),))
    elif method == "MarkAllRead":
        assert {"OpenNotification", "InvokeAction", "SetDoNotDisturb"} <= calls
        state["unread"] = 0
        result = GLib.Variant("(u)", (2,))
    elif method == "SetDoNotDisturb":
        assert args.unpack() == (False,)
        if reject_dnd:
            reject_dnd = False
            invocation.return_dbus_error(IFACE + ".FixtureFailure", "Synthetic failure")
            return
        state["dnd"] = args.unpack()[0]
        result = GLib.Variant("(b)", (state["dnd"],))
    else:
        assert (method == "OpenNotification" and args.unpack() == (7,)) or (
            method == "InvokeAction" and args.unpack() == (7, "reply"))
        result = GLib.Variant("(b)", (True,))
    invocation.return_value(result)
    if method in ("MarkAllRead", "SetDoNotDisturb"):
        conn.emit_signal(None, path, iface, "Changed", None)


info = Gio.DBusNodeInfo.new_for_xml(XML)


def bus_acquired(conn, name):
    conn.register_object(PATH, info.interfaces[0], call, None, None)


def name_acquired(conn, name):
    Path(sys.argv[1]).touch()


if __name__ == "__main__":
    if os.environ.get("MSERIES_NOTIFICATION_PRIVATE_FIXTURE") != "1":
        sys.exit("Refusing bus ownership: run the isolated notifications-probe/run.sh "
                 "(requires MSERIES_NOTIFICATION_PRIVATE_FIXTURE=1).")
    if len(sys.argv) != 2:
        sys.exit("Usage: fixture.py READY_FILE (private test session only)")
    Gio.bus_own_name(Gio.BusType.SESSION, BUS, Gio.BusNameOwnerFlags.NONE,
                     bus_acquired, name_acquired, lambda *_: sys.exit(1))
    GLib.MainLoop().run()
