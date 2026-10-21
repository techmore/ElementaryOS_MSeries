"""Stand-in for the host side: a D-Bus Clipboard peer for QEMU's p2p display.
usage: clipboard-peer.py QMP_SOCK HOST_TEXT SECONDS
Prints guest grabs and the data fetched from the guest; offers HOST_TEXT to the guest."""
import os, socket, json, sys, time, threading
from gi.repository import Gio, GLib

qs, host_text, seconds = sys.argv[1], sys.argv[2], int(sys.argv[3])
MIME = "text/plain;charset=utf-8"
XML = """<node><interface name="org.qemu.Display1.Clipboard">
<method name="Register"/><method name="Unregister"/>
<method name="Grab"><arg type="u" name="selection" direction="in"/><arg type="u" name="serial" direction="in"/><arg type="as" name="mimes" direction="in"/></method>
<method name="Release"><arg type="u" name="selection" direction="in"/></method>
<method name="Request"><arg type="u" name="selection" direction="in"/><arg type="as" name="mimes" direction="in"/><arg type="s" name="reply_mime" direction="out"/><arg type="ay" name="data" direction="out"/></method>
<property name="Interfaces" type="as" access="read"/></interface></node>"""

s = socket.socket(socket.AF_UNIX); s.connect(qs); f = s.makefile("r"); f.readline()
def cmd(c, a=None, fds=None):
    data = (json.dumps({"execute": c, **({"arguments": a} if a else {})}) + "\n").encode()
    socket.send_fds(s, [data], fds) if fds else s.sendall(data)
    while True:
        l = f.readline()
        if '"return"' in l or '"error"' in l: return json.loads(l)
cmd("qmp_capabilities")
a, b = socket.socketpair()
cmd("getfd", {"fdname": "peer"}, [b.fileno()])
print("add_client", cmd("add_client", {"protocol": "@dbus-display", "fdname": "peer"}), flush=True)
f.close(); s.close()   # QMP serves one client per socket: do not hold it
gs = Gio.Socket.new_from_fd(os.dup(a.fileno()))
bus = Gio.DBusConnection.new_sync(gs.connection_factory_create_connection(), None,
        Gio.DBusConnectionFlags.AUTHENTICATION_CLIENT | Gio.DBusConnectionFlags.DELAY_MESSAGE_PROCESSING, None, None)
state = {"serial": 0}
loop = GLib.MainLoop()

def method_call(conn, sender, path, iface, name, params, inv):
    if name == "Grab":
        sel, ser, mimes = params.unpack()
        print(f"GUEST GRAB selection={sel} serial={ser} mimes={mimes}", flush=True)
        inv.return_value(None)
        if MIME in mimes:
            def fetch():
                proxy = Gio.DBusProxy.new_sync(bus, Gio.DBusProxyFlags.DO_NOT_LOAD_PROPERTIES, None, None, "/org/qemu/Display1/Clipboard", "org.qemu.Display1.Clipboard", None)
                try:
                    r = proxy.call_sync("Request", GLib.Variant("(uas)", (0, [MIME])), Gio.DBusCallFlags.NONE, 5000, None)
                    mime, data = r.unpack()
                    print("FETCHED FROM GUEST:", mime, bytes(data).decode("utf-8", "replace")[:200].replace("\n", "\\n"), flush=True)
                except GLib.Error as e:
                    print("fetch error", e.message, flush=True)
            threading.Thread(target=fetch, daemon=True).start()
    elif name == "Request":
        sel, mimes = params.unpack()
        print(f"GUEST PASTE REQUEST mimes={mimes} -> sending host text", flush=True)
        inv.return_value(GLib.Variant("(say)", (MIME, list(host_text.encode()))))
    else:
        inv.return_value(None)

def get_prop(conn, sender, path, iface, prop):
    return GLib.Variant("as", [])
info = Gio.DBusNodeInfo.new_for_xml(XML)
bus.register_object("/org/qemu/Display1/Clipboard", info.interfaces[0], method_call, get_prop, None)
bus.start_message_processing()
proxy = Gio.DBusProxy.new_sync(bus, Gio.DBusProxyFlags.DO_NOT_LOAD_PROPERTIES, None, None, "/org/qemu/Display1/Clipboard", "org.qemu.Display1.Clipboard", None)
def after_grab(p, res):
    try:
        p.call_finish(res); print("host grab accepted", flush=True)
    except GLib.Error as e:
        print("host grab error", e.message, flush=True)
def after_register(p, res):
    try:
        p.call_finish(res)
    except GLib.Error as e:
        print("register error", e.message, flush=True); return
    print("registered; offering host clipboard to the guest", flush=True)
    pass  # serial 0: the first grab of a session (spice-vdagentd counts from 0)
    p.call("Grab", GLib.Variant("(uuas)", (0, state["serial"], [MIME])), Gio.DBusCallFlags.NONE, 5000, None, after_grab)
proxy.call("Register", None, Gio.DBusCallFlags.NONE, 8000, None, after_register)
GLib.timeout_add_seconds(seconds, loop.quit)
loop.run()
try: proxy.call_sync("Unregister", None, Gio.DBusCallFlags.NONE, 3000, None)
except GLib.Error: pass
print("done", flush=True)
