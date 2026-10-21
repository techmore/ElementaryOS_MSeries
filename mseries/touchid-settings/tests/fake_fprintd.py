#!/usr/bin/env python3
"""A fake net.reactivated.Fprint for exercising the Touch ID page.

Runs on the *session* bus only, holds fingerprints in memory, and streams
EnrollStatus signals on a timer. It never touches /dev/sep-bio or the real
Secure Enclave. Usage: fake_fprintd.py [--fingers a,b] [--stages N] [--fail-at N]
"""
import argparse
import sys

import gi
gi.require_version("Gio", "2.0")
from gi.repository import Gio, GLib

XML = """
<node>
  <interface name="net.reactivated.Fprint.Manager">
    <method name="GetDefaultDevice"><arg type="o" direction="out"/></method>
  </interface>
  <interface name="net.reactivated.Fprint.Device">
    <method name="Claim"><arg type="s" direction="in"/></method>
    <method name="Release"/>
    <method name="EnrollStart"><arg type="s" direction="in"/></method>
    <method name="EnrollStop"/>
    <method name="ListEnrolledFingers"><arg type="s" direction="in"/><arg type="as" direction="out"/></method>
    <method name="DeleteEnrolledFinger"><arg type="s" direction="in"/></method>
    <property name="name" type="s" access="read"/>
    <property name="num-enroll-stages" type="i" access="read"/>
    <property name="finger-needed" type="b" access="read"/>
    <property name="finger-present" type="b" access="read"/>
    <signal name="EnrollStatus"><arg type="s"/><arg type="b"/></signal>
  </interface>
</node>
"""

DEVICE = "/net/reactivated/Fprint/Device/0"
args = None
fingers = []
claimed = False
enroll_timer = 0
pending_finger = None
stage = 0
log = lambda *a: print("[fake-fprintd]", *a, file=sys.stderr, flush=True)


def prop(conn, name, value):
    """Emit fprintd's finger-needed / finger-present property change."""
    conn.emit_signal(None, DEVICE, "org.freedesktop.DBus.Properties", "PropertiesChanged",
                     GLib.Variant("(sa{sv}as)", ("net.reactivated.Fprint.Device", {name: GLib.Variant("b", value)}, [])))


def emit(conn, status, done):
    conn.emit_signal(None, DEVICE, "net.reactivated.Fprint.Device", "EnrollStatus",
                     GLib.Variant("(sb)", (status, done)))


def tick(conn):
    global stage, enroll_timer, pending_finger
    stage += 1
    if args.fail_at and stage == args.fail_at:
        emit(conn, "enroll-failed", True)
        enroll_timer = 0
        return False
    if args.duplicate_at and stage == args.duplicate_at:
        emit(conn, "enroll-duplicate", True)
        enroll_timer = 0
        return False
    if stage % 5 == 3:
        emit(conn, "enroll-retry-scan", False)
        return True
    if args.finger_events:
        prop(conn, "finger-present", True)
        GLib.timeout_add(args.interval // 3, lambda: (prop(conn, "finger-present", False), False)[1])
    emit(conn, "enroll-stage-passed", False)
    if stage >= args.stages:
        fingers.append(pending_finger)
        emit(conn, "enroll-completed", True)
        enroll_timer = 0
        return False
    return True


def on_call(conn, sender, path, iface, method, params, inv):
    global claimed, enroll_timer, pending_finger, stage
    log(method, params.unpack())
    if method == "GetDefaultDevice":
        inv.return_value(GLib.Variant("(o)", (DEVICE,)))
    elif method == "Claim":
        claimed = True
        inv.return_value(None)
    elif method == "Release":
        claimed = False
        inv.return_value(None)
    elif method == "EnrollStart":
        if not claimed:
            inv.return_dbus_error("net.reactivated.Fprint.Error.ClaimDevice", "claim first")
            return
        pending_finger, stage = params.unpack()[0], 0
        inv.return_value(None)
        if args.finger_events:
            prop(conn, "finger-needed", True)
        enroll_timer = GLib.timeout_add(args.interval, tick, conn)
    elif method == "EnrollStop":
        if enroll_timer:
            GLib.source_remove(enroll_timer)
            enroll_timer = 0
        inv.return_value(None)
    elif method == "ListEnrolledFingers":
        if not fingers:
            inv.return_dbus_error("net.reactivated.Fprint.Error.NoEnrolledPrints", "no prints")
        else:
            inv.return_value(GLib.Variant("(as)", (list(fingers),)))
    elif method == "DeleteEnrolledFinger":
        name = params.unpack()[0]
        if name in fingers:
            fingers.remove(name)
        inv.return_value(None)


def on_get(conn, sender, path, iface, prop):
    if prop == "name":
        return GLib.Variant("s", "Fake secure enclave fingerprint sensor")
    if prop == "num-enroll-stages":
        return GLib.Variant("i", args.stages)
    if prop in ("finger-needed", "finger-present"):
        return GLib.Variant("b", False)


def main():
    global args
    p = argparse.ArgumentParser()
    p.add_argument("--fingers", default="")
    p.add_argument("--stages", type=int, default=8)
    p.add_argument("--interval", type=int, default=450)
    p.add_argument("--fail-at", type=int, default=0)
    p.add_argument("--duplicate-at", type=int, default=0)
    p.add_argument("--finger-events", action="store_true")
    args = p.parse_args()
    fingers.extend(f for f in args.fingers.split(",") if f)
    nodes = Gio.DBusNodeInfo.new_for_xml(XML)

    def bus_acquired(conn, name):
        conn.register_object("/net/reactivated/Fprint/Manager", nodes.interfaces[0], on_call, None, None)
        conn.register_object(DEVICE, nodes.interfaces[1], on_call, on_get, None)

    Gio.bus_own_name(Gio.BusType.SESSION, "net.reactivated.Fprint", Gio.BusNameOwnerFlags.NONE,
                     bus_acquired, lambda *_: log("ready"), lambda *_: sys.exit("name taken"))
    GLib.MainLoop().run()


main()
