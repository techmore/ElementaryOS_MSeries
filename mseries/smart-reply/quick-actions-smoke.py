#!/usr/bin/python3
"""Smart Reply quick actions against a real GTK 4 text field, in a private session.

Run it as `python3 quick-actions-smoke.py [path/to/mseries-reply]` (default: the debug build). It re-launches itself under
`dbus-run-session -- xvfb-run`, starts its own ibus-daemon, AT-SPI bus and input service, shows one GTK 4 entry with
GTK_IM_MODULE=ibus, and presses real X keys on it with xdotool. It never touches the owner's IBus, session or apps. The
local model on 127.0.0.1:8766 is used for the revisions (the draft itself is a fixed string), so that must be running.
"""
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

HERE = Path(__file__).resolve()
REPO = HERE.parents[2]
BINARY = sys.argv[1] if len(sys.argv) > 1 else str(Path(os.environ.get("CARGO_TARGET_DIR", Path.home() / ".cache/cargo-target")) / "debug/mseries-reply")

if os.environ.get("MSERIES_REPLY_SMOKE") != "1":
    raise SystemExit(
        subprocess.run(
            ["dbus-run-session", "--", "xvfb-run", "-a", "-s", "-screen 0 900x500x24", "env", "MSERIES_REPLY_SMOKE=1",
             "GSETTINGS_BACKEND=memory", sys.executable, str(HERE), BINARY]
        ).returncode
    )

import gi  # noqa: E402

gi.require_version("IBus", "1.0")
from gi.repository import Gio, GLib, IBus  # noqa: E402

FIELD_APP = r'''
import gi, sys
gi.require_version("Gtk", "4.0")
from gi.repository import Gtk, GLib
out = sys.argv[1]
app = Gtk.Application(application_id="org.example.QuickActionsSmoke")
def activate(app):
    win = Gtk.ApplicationWindow(application=app, title="Smart Reply smoke")
    win.set_default_size(900, 120)
    entry = Gtk.Entry()
    entry.connect("changed", lambda e: open(out, "w").write(e.get_text()))
    win.set_child(entry)
    win.present()
    entry.grab_focus()
    print("ready", flush=True)
app.connect("activate", activate)
app.run([])
'''

failures = []
log = []


def check(name, ok, detail=""):
    log.append({"check": name, "ok": bool(ok), "detail": detail})
    if not ok:
        failures.append(name)


def pump(seconds=0.3):
    until = time.monotonic() + seconds
    while time.monotonic() < until:
        while GLib.MainContext.default().pending():
            GLib.MainContext.default().iteration(False)
        time.sleep(0.01)


def key(*keys):
    subprocess.run(["xdotool", "key", "--clearmodifiers", *keys], check=True)
    pump(0.25)


def clear():
    key("ctrl+a", "BackSpace")


def read(path):
    return Path(path).read_text() if Path(path).exists() else ""


with tempfile.TemporaryDirectory(prefix="mseries-quick-") as d:
    env = dict(os.environ)
    env.update(
        IBUS_ADDRESS=f"unix:path={d}/bus", HOME=f"{d}/home", XDG_CACHE_HOME=f"{d}/cache", XDG_CONFIG_HOME=f"{d}/config",
        XDG_DATA_HOME=f"{d}/data", GIO_USE_VFS="local", GTK_IM_MODULE="ibus", GDK_BACKEND="x11",
        GTK_A11Y="atspi", GTK_USE_PORTAL="0",
    )
    os.environ.update(env)
    Path(f"{d}/home").mkdir()
    procs = []
    service_log = f"{d}/service.log"
    entry_text = f"{d}/entry.txt"
    try:
        procs.append(subprocess.Popen(["ibus-daemon", "--single", "--emoji-extension", "disable", "--address",
                                       env["IBUS_ADDRESS"], "--cache", "none"], env=env))
        time.sleep(1)
        IBus.init()
        bus = IBus.Bus.new()
        assert bus.is_connected()
        # The panel that draws candidate windows (the desktop session runs its own; this one is private to the test).
        procs.append(subprocess.Popen(["/usr/libexec/ibus-ui-gtk3"], env=env))
        pump(1)
        procs.append(subprocess.Popen([BINARY, "input-service"], env=env, stderr=open(service_log, "w")))
        pump(1.5)
        app = subprocess.Popen([sys.executable, "-c", FIELD_APP, entry_text], env=env, stdout=subprocess.PIPE, text=True)
        procs.append(app)
        assert app.stdout.readline().strip() == "ready"
        pump(1.5)
        subprocess.run(["xdotool", "search", "--name", "Smart Reply smoke", "windowfocus"], check=False)
        pump(0.5)
        # The desktop's own input method, which the service restores afterwards.
        assert bus.set_global_engine("xkb:us::eng")
        pump(0.5)

        conn = Gio.bus_get_sync(Gio.BusType.SESSION, None)

        def call(method, args=None, timeout=8000):
            return conn.call_sync("org.techmore.SmartReplyInput", "/org/techmore/SmartReplyInput",
                                  "org.techmore.SmartReplyInput", method, args, None, Gio.DBusCallFlags.NONE, timeout, None)

        lines = [(False, "Sam", "Are we still on for lunch?"), (True, "Me", "Yes, noon works."),
                 (False, "Sam", "Great. Thai place or the deli?")]

        def hold(draft, with_context=True):
            inline = call("Begin").unpack()[0]
            if with_context:
                call("SetContext", GLib.Variant("(sa(bss)s)", ("org.example.Chat", lines, "")))
            call("Finish", GLib.Variant("(s)", (draft,)))
            return inline

        def wait_for(needle, seconds=60, more_than=0):
            until = time.monotonic() + seconds
            while time.monotonic() < until:
                pump(0.3)
                if read(service_log).count(needle) > more_than:
                    return True
            return False

        def shot(name):
            try:
                from PIL import ImageGrab

                ImageGrab.grab(xdisplay=os.environ["DISPLAY"]).save(f"{d}/{name}.png")
            except Exception as error:  # screenshots are a convenience, not a check
                print("no screenshot:", error)

        # 1. The draft is held with its conversation; Alt+R rewords it and Tab inserts the new text.
        inline = hold("Thai sounds great.")
        check("draft shown inline in a GTK 4 field", inline)
        pump(0.5)
        shot("held")
        key("alt+r")
        check("Alt+R starts a quick action", wait_for("quick action Reword", 5))
        check("nothing was typed into the field by Alt+R", read(entry_text) == "", read(entry_text))
        shot("drafting")
        check("the redraft finishes", wait_for("quick action Reword done", 90))
        pump(0.5)
        shot("revised")
        key("Tab")
        revised = read(entry_text)
        check("Tab inserts the revised draft (not empty, no hint text)", bool(revised) and "Alt+" not in revised and "—" not in revised, revised)
        pump(0.5)

        # 1b. Alt+P, Alt+C and Alt+T (thinking on) go through the same path with their own instruction.
        for chord, name in (("alt+p", "MorePolite"), ("alt+c", "MoreConcise"), ("alt+t", "ThinkHarder")):
            clear()
            hold("Thai sounds great, see you at noon.")
            key(chord)
            check(f"{chord} runs {name} to the end", wait_for(f"quick action {name} done", 200 if name == "ThinkHarder" else 90))
            pump(0.5)
            key("Tab")
            check(f"{chord} result is inserted", bool(read(entry_text)) and "Alt+" not in read(entry_text) and "think>" not in read(entry_text), read(entry_text))

        # 2. Alt+= takes a note typed into the engine's own line, then redrafts with it.
        clear()
        hold("Thai sounds great.")
        key("alt+equal")
        pump(0.5)
        for ch in "I am late":
            key("space" if ch == " " else ch)
        shot("context")
        check("typing the note puts nothing in the field", read(entry_text) == "", read(entry_text))
        key("BackSpace")
        key("e")
        key("Return")
        check("Enter starts the context redraft", wait_for("quick action AddContext", 5))
        check("the context redraft finishes", wait_for("quick action AddContext done", 90))
        pump(0.5)
        key("Tab")
        contextual = read(entry_text)
        check("Tab inserts the contextual draft", bool(contextual) and "Extra context" not in contextual, contextual)

        # 3. Esc in the note goes back to the draft, which Tab then inserts unchanged.
        clear()
        hold("Deli works for me.")
        key("alt+equal")
        key("x")
        key("Escape")
        key("Tab")
        check("Esc leaves the note and the draft survives", read(entry_text) == "Deli works for me.", read(entry_text))

        # 4. A plain key (even the letter r) abandons the draft and types normally.
        clear()
        hold("Deli works for me.")
        key("r")
        pump(0.5)
        key("Tab")
        check("a plain key abandons the draft and is typed", read(entry_text).startswith("r") and "Deli" not in read(entry_text), read(entry_text))

        # 4b. The bar: the IBus panel draws the quick actions as clickable candidates; a click must run the action
        # without moving keyboard focus (the draft stays held, then Tab inserts the new one).
        clear()
        hold("Deli works for me.")
        pump(1.0)
        shot("bar")
        windows = subprocess.run(["xdotool", "search", "--onlyvisible", "--class", "ibus-ui-gtk3"], capture_output=True, text=True).stdout.split()
        check("the panel shows the bar (a candidate window is visible)", bool(windows), str(windows))
        if windows:
            geometry = subprocess.run(["xdotool", "getwindowgeometry", "--shell", windows[0]], capture_output=True, text=True).stdout
            g = dict(line.split("=") for line in geometry.split() if "=" in line)
            x, y, w, h = int(g["X"]), int(g["Y"]), int(g["WIDTH"]), int(g["HEIGHT"])
            done_before = read(service_log).count("quick action Reword done")
            focused_before = subprocess.run(["xdotool", "getwindowfocus"], capture_output=True, text=True).stdout.strip()
            # first button: a little in from the left edge, vertically centred
            subprocess.run(["xdotool", "mousemove", str(x + 30), str(y + h // 2), "click", "1"], check=False)
            check("clicking the first button runs Reword", wait_for("bar button 0 clicked", 5))
            check("the click did not move keyboard focus", subprocess.run(["xdotool", "getwindowfocus"], capture_output=True, text=True).stdout.strip() == focused_before)
            check("the bar's redraft finishes", wait_for("quick action Reword done", 90, done_before))
            pump(0.5)
            key("Tab")
            check("Tab inserts the redrafted text after a click", bool(read(entry_text)) and read(entry_text) != "Deli works for me." and "Alt+" not in read(entry_text), read(entry_text))
        else:
            key("Escape")

        # 4c. A refusal reason is shown in the field itself, and typing dismisses it.
        clear()
        shown = call("Say", GLib.Variant("(s)", ("There is no incoming message to reply to.",))).unpack()[0]
        check("Say shows the reason in the field", shown)
        pump(0.5)
        shot("notice")
        key("x")
        pump(0.5)
        check("typing dismisses the notice and is typed normally", read(entry_text) == "x", read(entry_text))

        # 5. Without a conversation the actions are not offered and Alt+R is the app's own key.
        clear()
        hold("Deli works for me.", with_context=False)
        key("alt+r")
        key("Tab")
        check("no conversation: Alt+R does nothing, Tab still inserts", read(entry_text) == "Deli works for me.", read(entry_text))
        if os.environ.get("SMOKE_SHOTS"):
            for png in Path(d).glob("*.png"):
                png.replace(Path(os.environ["SMOKE_SHOTS"]) / f"quick-{png.name}")
    except BaseException:
        import traceback

        traceback.print_exc()
        failures.append("exception")
    finally:
        print(Path(service_log).read_text()[-3000:] if Path(service_log).exists() else "")
        for proc in reversed(procs):
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
        print(json.dumps(log, indent=1))
        raise SystemExit(1 if failures else 0)
