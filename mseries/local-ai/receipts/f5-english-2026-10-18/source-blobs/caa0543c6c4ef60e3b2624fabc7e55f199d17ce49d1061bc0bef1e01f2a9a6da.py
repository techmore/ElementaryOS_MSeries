#!/usr/bin/python3
"""Real Brave rich-compose/textarea input check; no accounts, mic or inference.

Synthetic local data URL on a private Xvfb/IBus/session bus. This verifies the
editor/input boundary used by Gmail-like compose fields, not authenticated Gmail,
mail sending or model quality. Frozen source and bounded synthetic receipts only.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
import urllib.parse
import urllib.request


parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--receipt-dir", type=Path, required=True)
args = parser.parse_args()
HERE = Path(__file__).resolve().parent
if os.environ.get("MSERIES_BROWSER_EDITORS_SESSION") != "1":
    with tempfile.TemporaryDirectory(prefix="mseries-browser-editors-") as scratch:
        result = subprocess.run(["dbus-run-session", "--", "xvfb-run", "-a", "env",
            "MSERIES_BROWSER_EDITORS_SESSION=1", "MSERIES_INPUT_TEST_SESSION=1", "GSETTINGS_BACKEND=memory",
            "MSERIES_BROWSER_EDITORS_TEMP=" + scratch, sys.executable, str(Path(__file__).resolve()), *sys.argv[1:]])
        time.sleep(.5)  # Private portal mounts end with the private session bus.
    raise SystemExit(result.returncode)
assert os.environ.get("GSETTINGS_BACKEND") == "memory"
output = args.receipt_dir.resolve()
output.mkdir(parents=True, mode=0o700, exist_ok=False)
source = output / "evaluated-source"
source.mkdir(mode=0o700)
for name in ("dictation-input.py", "dictation-input-client.py", "f5-browser-editors-smoke.py"):
    (source / name).write_bytes((HERE / name).read_bytes())
(source / "machine.py").write_bytes((HERE.parent / "local-ai/machine.py").read_bytes())
sys.path.insert(0, str(source))
from machine import snapshot, violations, DEFAULT_POLICY

report = {"schema": 1, "complete": False, "passed": False, "cases": [],
    "method": "Real Brave X11 private local synthetic contenteditable and textarea via current focus-bound IBus bridge",
    "scope": "Gmail-style rich compose pattern only; no Gmail account or live mail integration tested",
    "microphone_recorded": False, "audio_played": False, "inference": False,
    "owner_windows_opened": False, "owner_profile_used": False, "mail_sent": False,
    "keyboard_device_opened": False, "physical_f5_tested": False,
    "runtime": {"kernel": os.uname().release},
    "source_sha256": {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in source.glob("*.py")}}
samples = []


def checkpoint():
    tmp = output / "receipt.tmp"
    tmp.write_text(json.dumps(report, indent=2) + "\n")
    tmp.chmod(0o600)
    tmp.replace(output / "receipt.json")


def guard(admission=False):
    item = snapshot()
    samples.append(item)
    if (violations(item, DEFAULT_POLICY, 512 * 1024 ** 2)
            or max(item["fans_rpm"].values(), default=9999) >= 2700
            or max(item["temperatures_c"].values(), default=999) >= (60 if admission else 63)):
        report["interrupted"] = "Quiet/reserve guard; fixture is incomplete and unscored"
        raise RuntimeError("Quiet/reserve guard interrupted this owned fixture")


def stop(child):
    if child is None:
        return
    try: os.killpg(child.pid, signal.SIGTERM)
    except ProcessLookupError: pass
    try: child.wait(3)
    except subprocess.TimeoutExpired:
        os.killpg(child.pid, signal.SIGKILL)
        child.wait(3)
    # Chromium helpers can outlive their leader, but remain in our fresh group.
    try: os.killpg(child.pid, signal.SIGKILL)
    except ProcessLookupError: pass


checkpoint()
directory = os.environ["MSERIES_BROWSER_EDITORS_TEMP"]
runtime = Path(directory) / "runtime"
runtime.mkdir(mode=0o700)
os.environ.update(IBUS_ADDRESS="unix:path=" + directory + "/bus", XMODIFIERS="@im=ibus",
    GTK_IM_MODULE="ibus", GDK_BACKEND="x11", GTK_A11Y="atspi", GIO_USE_VFS="local",
    GSK_RENDERER="cairo", LIBGL_ALWAYS_SOFTWARE="1", XDG_CACHE_HOME=directory + "/cache",
    XDG_CONFIG_HOME=directory + "/config", XDG_RUNTIME_DIR=str(runtime))
subprocess.run(["dbus-update-activation-environment", "XDG_RUNTIME_DIR", "DISPLAY", "XAUTHORITY",
                "XDG_CACHE_HOME", "XDG_CONFIG_HOME", "GSETTINGS_BACKEND"], check=True)
import gi
gi.require_version("IBus", "1.0")
from gi.repository import Gio, GLib, IBus
from websockets.sync.client import connect
daemon = engine = browser = ws = None


def pump(seconds=.15):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        while GLib.MainContext.default().pending():
            GLib.MainContext.default().iteration(False)
        time.sleep(.01)


def client(method, token=None, text="", *, refusal=False):
    argv = ["/usr/bin/python3", str(source / "dictation-input-client.py"), method]
    if token:
        argv.append(token)
    child = subprocess.Popen(argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    child.stdin.write(text)
    child.stdin.close()
    child.stdin = None
    deadline = time.monotonic() + 6
    while child.poll() is None:
        if time.monotonic() > deadline:
            child.kill(); child.wait()
            raise TimeoutError("Owned browser fixture input call expired")
        pump(.02)
    stdout, stderr = child.communicate()
    if refusal:
        assert child.returncode != 0, "Stale/sensitive insertion was accepted"
    else:
        assert child.returncode == 0, stderr[:300]
    return stdout.strip()


try:
    for _ in range(3):
        guard(admission=True)
        pump(.25)
    report["runtime"]["browser"] = subprocess.run(["brave-browser", "--version"], capture_output=True,
        check=True, text=True, timeout=5).stdout.strip()
    daemon = subprocess.Popen(["ibus-daemon", "--single", "--xim", "--emoji-extension", "disable",
        "--address", os.environ["IBUS_ADDRESS"], "--cache", "none"], start_new_session=True)
    pump(1)
    IBus.init()
    bus = IBus.Bus.new()
    assert bus.is_connected()
    connection = Gio.bus_get_sync(Gio.BusType.SESSION, None)
    connection.call_sync("org.a11y.Bus", "/org/a11y/bus", "org.freedesktop.DBus.Properties", "Set",
        GLib.Variant("(ssv)", ("org.a11y.Status", "IsEnabled", GLib.Variant("b", True))),
        None, Gio.DBusCallFlags.NONE, 3000, None)
    engine = subprocess.Popen(["/usr/bin/python3", str(source / "dictation-input.py")], start_new_session=True)
    pump(1)
    assert bus.set_global_engine("xkb:us::eng")
    profile = Path(directory) / "browser-profile"
    browser = subprocess.Popen(["brave-browser", "--user-data-dir=" + str(profile), "--ozone-platform=x11",
        "--disable-gpu", "--disable-background-networking", "--disable-extensions", "--disable-sync",
        "--no-first-run", "--no-default-browser-check", "--password-store=basic", "--remote-debugging-address=127.0.0.1",
        "--remote-debugging-port=0", "--host-resolver-rules=MAP * ~NOTFOUND", "--force-renderer-accessibility",
        "about:blank"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
    deadline = time.monotonic() + 15
    while not (profile / "DevToolsActivePort").exists():
        assert browser.poll() is None, "Owned browser exited"
        if time.monotonic() > deadline:
            raise TimeoutError("Owned browser debug endpoint unavailable")
        pump()
    port = int((profile / "DevToolsActivePort").read_text().splitlines()[0])
    with urllib.request.urlopen(f"http://127.0.0.1:{port}/json/list", timeout=3) as response:
        page = next(x for x in json.load(response) if x["type"] == "page")
    ws = connect(page["webSocketDebuggerUrl"], proxy=None, open_timeout=3)
    sequence = 0

    def cdp(method, params=None):
        global sequence
        sequence += 1
        ws.send(json.dumps({"id": sequence, "method": method, "params": params or {}}))
        while True:
            row = json.loads(ws.recv(timeout=5))
            if row.get("id") == sequence:
                if "error" in row:
                    raise RuntimeError(row["error"])
                return row.get("result", {})

    def js(expression):
        value = cdp("Runtime.evaluate", {"expression": expression, "returnByValue": True})
        assert "exceptionDetails" not in value, value
        return value["result"].get("value")

    html = '''<!doctype html><meta charset="utf-8"><title>Private English editor fixture</title>
    <label>Gmail-style rich compose</label><div id="rich" role="textbox" aria-label="Message body" contenteditable="true" style="white-space:pre-wrap;border:1px solid;padding:10px;min-height:80px"></div>
    <label>Multiline notes</label><textarea id="notes" rows="6"></textarea><input id="other"><input id="password" type="password">
    <script>window.events=[]; for(const id of ['rich','notes']) { const e=document.getElementById(id); for(const kind of ['compositionstart','compositionupdate','compositionend']) e.addEventListener(kind,x=>window.events.push({field:id,type:kind,text:x.data})); }</script>'''
    cdp("Page.navigate", {"url": "data:text/html," + urllib.parse.quote(html)})
    pump(1)
    cdp("Page.bringToFront")

    def focus(field):
        js("document.getElementById(" + json.dumps(field) + ").focus()")
        pump(.6)

    def value(field):
        return js("(()=>{const e=document.getElementById(" + json.dumps(field) + ");return e.isContentEditable?e.innerText:e.value})()")

    literal = 'Hello from the local English assistant.\nLiteral text: $() & <tag> "quoted".\nPlease keep these three lines.'
    preview = "Temporary English words while speaking"
    for field in ("rich", "notes"):
        guard()
        focus(field)
        token = client("begin")
        client("check", token)
        assert value(field) == "", "Check inserted text"
        client("preview", token, preview)
        pump(.2)
        events = js("window.events.filter(x=>x.field===" + json.dumps(field) + ")")
        assert any(x["type"] == "compositionupdate" and x["text"] == preview for x in events), "Native provisional text was not exposed"
        client("preview", token, "")
        pump(.2)
        assert value(field) == "", "Clearing provisional text left editor words"
        client("commit", token, literal)
        pump(.2)
        actual = value(field)
        assert actual == literal, repr(actual)
        client("preview", token, "This preview must be cancelled")
        client("cancel")
        pump(.2)
        assert value(field) == literal, "Cancellation committed provisional text"
        client("commit", token, " stale words", refusal=True)
        assert value(field) == literal
        assert bus.get_global_engine().get_name() == "xkb:us::eng"
        report["cases"].append({"field": field, "native_preview_visible": True, "preview_clear_exact": True,
            "multiline_literal_exact": True, "cancel_drops_preview": True, "stale_commit_refused": True,
            "native_engine_restored": True, "text": actual, "composition_events": events})
        checkpoint()
        # A new lease cannot cross into another field, even inside one page.
        token = client("begin")
        client("preview", token, "Do not move these provisional words")
        focus("other")
        client("check", token, refusal=True)
        client("commit", token, "wrong field", refusal=True)
        assert value("other") == ""
        assert value(field) == literal, "Focus change committed a provisional draft"
        client("finish", token)
        report["cases"][-1]["focus_change_clears_preview_and_refuses_commit"] = True
        checkpoint()
    focus("password")
    client("begin", refusal=True)
    assert value("password") == ""
    report.update(password_refused_and_untouched=True, complete=True, passed=True)
except Exception as error:
    report.update(failure_kind=type(error).__name__, failure_detail=str(error)[:500])
finally:
    if ws is not None:
        ws.close()
    for child in (browser, engine, daemon):
        stop(child)
    if samples:
        report["resources"] = {"samples": len(samples), "min_available_bytes": min(x["available_bytes"] for x in samples),
            "max_fan_rpm": max(max(x["fans_rpm"].values(), default=0) for x in samples),
            "max_temp_c": max(max(x["temperatures_c"].values(), default=0) for x in samples)}
    checkpoint()
print(json.dumps({"complete": report["complete"], "passed": report["passed"], "cases": len(report["cases"])}))
raise SystemExit(0 if report["passed"] else 1)
