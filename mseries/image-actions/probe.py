#!/usr/bin/python3
"""Isolated real conversion, GTK capture and notification integration probe."""
import argparse
from pathlib import Path
from types import SimpleNamespace
import tempfile
import threading
import time
import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Granite", "7.0")
gi.require_version("GdkPixbuf", "2.0")
from gi.repository import Gtk, GdkPixbuf, GLib, Gio, Granite
import app

parser = argparse.ArgumentParser()
parser.add_argument("output", type=Path)
parser.add_argument("--dark", action="store_true")
parser.add_argument("--width", type=int, default=560)
options = parser.parse_args()
options.output.mkdir(parents=True, exist_ok=True)
Gtk.init()
Granite.init()
Gtk.Settings.get_default().set_property("gtk-application-prefer-dark-theme", options.dark)
notifications = []
bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
xml = Gio.DBusNodeInfo.new_for_xml('''<node><interface name="org.freedesktop.Notifications">
<method name="Notify"><arg type="s" direction="in"/><arg type="u" direction="in"/><arg type="s" direction="in"/>
<arg type="s" direction="in"/><arg type="s" direction="in"/><arg type="as" direction="in"/><arg type="a{sv}" direction="in"/>
<arg type="i" direction="in"/><arg type="u" direction="out"/></method>
<method name="GetCapabilities"><arg type="as" direction="out"/></method>
</interface></node>''')
def method(connection, sender, path, interface, name, parameters, invocation):
    if name == "Notify":
        notifications.append(parameters.unpack())
        invocation.return_value(GLib.Variant("(u)", (1,)))
    else:
        invocation.return_value(GLib.Variant("(as)", (["body"],)))
registration = bus.register_object("/org/freedesktop/Notifications", xml.interfaces[0], method, None, None)
owner = Gio.bus_own_name_on_connection(bus, "org.freedesktop.Notifications", Gio.BusNameOwnerFlags.NONE, None, None)

def capture(window, path):
    paintable = Gtk.WidgetPaintable.new(window)
    snapshot = Gtk.Snapshot.new()
    paintable.snapshot(snapshot, window.get_width(), window.get_height())
    node = snapshot.to_node()
    assert node is not None
    window.get_native().get_renderer().render_texture(node, None).save_to_png(str(path))

started, release = threading.Event(), threading.Event()
real_encoder = app.PixbufEncoder
class Encoder(real_encoder):
    def __call__(self, *args):
        started.set()
        if not release.wait(10):
            raise RuntimeError("Probe did not release encoder")
        return super().__call__(*args)
app.PixbufEncoder = Encoder

with tempfile.TemporaryDirectory() as temp:
    source = Path(temp) / "AirDrop photo with a longer filename.png"
    image = GdkPixbuf.Pixbuf.new(GdkPixbuf.Colorspace.RGB, True, 8, 32, 24)
    image.fill(0x4488CC88)
    image.savev(str(source), "png", [], [])
    original = source.read_bytes()
    deadline = time.monotonic() + 20
    state = [False]
failures = []
    def ready(application):
        Gtk.Settings.get_default().set_property("gtk-application-prefer-dark-theme", options.dark)
        application.window.set_default_size(options.width, 360)
        def step():
            if time.monotonic() > deadline:
                raise RuntimeError("Image-action probe timed out")
            if not state[0] and started.is_set():
                assert application.busy
                capture(application.window, options.output / "progress.png")
                state[0] = True
                release.set()
            elif state[0] and not application.busy and notifications:
                assert application.status.get_text() == "1 copy saved · 0 failed"
                assert application.button.get_label() == "Close"
                assert notifications[0][3] == "Image conversion finished"
                assert source.read_bytes() == original
                output = source.with_suffix(".jpg")
                assert GdkPixbuf.Pixbuf.new_from_file(str(output)).get_width() == 32
                capture(application.window, options.output / "success.png")
                application.window.close()
                return False
            return True
        def tick():
            try:
                return step()
            except BaseException as error:
                failures.append(error)
                release.set()
                application.quit()
                return False
        GLib.timeout_add(250, tick)
    code = app.run_gui(SimpleNamespace(format="jpeg", files=[str(source)]), ready)
    assert not failures, failures
    assert code == 0 and state[0] and notifications
print("PASS: native progress/result, real JPEG, unchanged original and notification")
