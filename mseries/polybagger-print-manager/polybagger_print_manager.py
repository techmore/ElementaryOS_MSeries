#!/usr/bin/env python3
"""PolyBagger T1000 Print Manager: detect the Zebra label printer and verify ZPL jobs went through.

GUI (elementary OS, GTK3 + Granite):   ./polybagger_print_manager.py
Terminal:
  ./polybagger_print_manager.py --status                       USB + CUPS state, exit 0 ready / 2 not ready
  ./polybagger_print_manager.py --send FILE.zpl [--yes]        send raw ZPL and verify it, exit 0 pass / 1 fail / 2 not ready
  ./polybagger_print_manager.py --watch                        print a line each time the printer is plugged/unplugged
  ./polybagger_print_manager.py --sync [--pull]                refresh the offline label store (works with no network)
  ./polybagger_print_manager.py --setup                        create the raw CUPS queue (asks for admin auth)
Add --json to --status / --send for machine-readable output.
"""
import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
import threading
import time
import urllib.parse
from pathlib import Path

ZEBRA_VENDOR = "0a5f"
QUEUE_NAME = "Zebra"
DATA_DIR = Path.home() / ".local/share/polybagger-print-manager"
LOG_PATH = DATA_DIR / "log.jsonl"
STORE = DATA_DIR / "labels"  # offline copy of the label library; printing never needs the network
THRIL_REPO = Path.home() / "Projects/thril"
SOURCES = [THRIL_REPO / "poly-bagger/UPC Labels"]
PREFERRED = ["CCSBLACK_store_flash.zpl", "CCSBLACK_recall_flash.zpl", "ccs_black_label.zpl"]
JOB_TIMEOUT = 60

TEST_LABEL = "^XA\n^PW700\n^LL320\n^FO40,40^A0N,55,55^FDZEBRA LINK TEST^FS\n" \
             "^FO40,125^A0N,40,40^FD{stamp}^FS\n^FO40,205^GB620,70,5^FS\n^XZ\n"


def run(cmd, timeout=15):
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return r.returncode, (r.stdout + r.stderr).strip()
    except (subprocess.TimeoutExpired, FileNotFoundError) as e:
        return 127, str(e)


# ---------------------------------------------------------------- detection

def usb_zebras():
    """Zebra devices currently on the USB bus, read from sysfs (no lsusb needed)."""
    found = []
    for d in Path("/sys/bus/usb/devices").glob("*"):
        try:
            if (d / "idVendor").read_text().strip().lower() != ZEBRA_VENDOR:
                continue
            read = lambda n: (d / n).read_text().strip() if (d / n).exists() else ""
            found.append({"bus": d.name, "product": read("product"),
                          "serial": read("serial"), "manufacturer": read("manufacturer")})
        except OSError:
            pass
    return found


def usb_uri(dev):
    q = urllib.parse.quote
    uri = f"usb://{q(dev['manufacturer'] or 'Zebra Technologies')}/{q(dev['product'])}"
    return uri + (f"?serial={q(dev['serial'])}" if dev["serial"] else "")


def find_queue():
    """Return (name, device_uri) of the CUPS queue to use, or (None, None)."""
    _, out = run(["lpstat", "-v"])
    queues = re.findall(r"^device for (\S+): (.+)$", out, re.M)
    for name, uri in queues:
        if name == QUEUE_NAME:
            return name, uri
    for name, uri in queues:
        if re.search(r"zebra|ztc|zt\d", uri, re.I):
            return name, uri
    return None, None


def queue_state(name):
    """('idle'|'processing'|'disabled'|'unknown', [alert reasons])."""
    _, out = run(["lpstat", "-l", "-p", name])
    m = re.search(r"printer \S+ (?:is )?(idle|now printing|disabled)", out)
    state = {"idle": "idle", "now printing": "processing", "disabled": "disabled"}.get(m.group(1) if m else "", "unknown")
    alerts = re.search(r"Alerts?: (.*)", out)
    reasons = [] if not alerts or alerts.group(1).strip() == "none" else alerts.group(1).split()
    if "Waiting for printer to become available" in out:
        reasons.append("waiting-for-printer")
    return state, reasons


def status():
    devs = usb_zebras()
    name, uri = find_queue()
    qstate, reasons = queue_state(name) if name else ("missing", [])
    uri_ok = True
    if devs and uri and devs[0]["serial"]:
        uri_ok = urllib.parse.quote(devs[0]["serial"]) in uri or devs[0]["serial"] in uri
    ready = bool(devs) and bool(name) and qstate in ("idle", "processing") and not reasons and uri_ok
    return {"usb": devs, "queue": name, "uri": uri, "queue_state": qstate,
            "reasons": reasons, "uri_matches_device": uri_ok, "ready": ready}


def setup_queue(dev):
    cmd = ["pkexec", "lpadmin", "-p", QUEUE_NAME, "-E", "-v", usb_uri(dev), "-m", "raw",
           "-o", "printer-is-shared=false"]
    return run(cmd, timeout=120)


# ---------------------------------------------------------------- sending

def check_zpl(path):
    """(ok, warnings) for a ZPL file before sending."""
    warns = []
    try:
        data = Path(path).read_text(errors="replace")
    except OSError as e:
        return False, [f"cannot read file: {e}"]
    if "^XA" not in data or "^XZ" not in data:
        return False, ["not ZPL: missing ^XA ... ^XZ"]
    if re.search(r"\^PON|\^FWN", data):
        warns.append("contains ^PON/^FWN, which this printer rejects ('Zebra is not ready'; see thril AGENTS.md)")
    return True, warns


def expectation(path):
    """What the operator should see after the job completes."""
    data = Path(path).read_text(errors="replace")
    if "^DF" in data and "^XF" not in data and "^PQ" not in data:
        return "store", "Stored to printer flash: no label should come out. Send the recall file to confirm."
    return "label", "A label should have printed."


def send_and_verify(path, queue, progress=lambda msg: None):
    """lp -o raw, then watch CUPS until the job is completed, cancelled or stuck."""
    t0 = time.time()
    rc, out = run(["lp", "-d", queue, "-n", "1", "-o", "raw", "-t", Path(path).name, str(path)], timeout=30)
    m = re.search(r"request id is (\S+)", out)
    if rc != 0 or not m:
        return {"ok": False, "stage": "submit", "detail": out or "lp failed"}
    job = m.group(1)
    progress(f"Submitted {job}")
    seen_active = False
    gone = 0
    while time.time() - t0 < JOB_TIMEOUT:
        _, active = run(["lpstat", "-W", "not-completed", "-o", queue])
        if job in active:
            seen_active, gone = True, 0
            state, reasons = queue_state(queue)
            progress(f"{job} in queue, printer {state}" + (f" ({', '.join(reasons)})" if reasons else ""))
        else:
            _, done = run(["lpstat", "-W", "completed", "-o", queue])
            if job in done:
                return {"ok": True, "stage": "completed", "job": job,
                        "seconds": round(time.time() - t0, 1), "detail": "CUPS reports the job completed"}
            gone += 1
            if gone >= 3:
                return {"ok": False, "stage": "vanished", "job": job,
                        "detail": "job left the queue without completing (cancelled or aborted)"}
        time.sleep(1)
    state, reasons = queue_state(queue)
    _, jobline = run(["lpstat", "-W", "not-completed", "-o", queue])
    return {"ok": False, "stage": "timeout", "job": job,
            "detail": f"not completed after {JOB_TIMEOUT}s; printer {state}, reasons: {reasons or 'none'}. {jobline}"}


def log_result(entry):
    try:
        LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with LOG_PATH.open("a") as f:
            f.write(json.dumps({"time": time.strftime("%Y-%m-%d %H:%M:%S"), **entry}) + "\n")
    except OSError:
        pass


def sync_library(pull=False):
    """Copy new/changed .zpl labels from the thril checkout into the local store. Returns (copied, total, note)."""
    import hashlib, shutil
    note = ""
    if pull and (THRIL_REPO / ".git").is_dir():
        rc, out = run(["git", "-C", str(THRIL_REPO), "pull", "--ff-only", "-q"], timeout=20)
        note = "git pull ok" if rc == 0 else f"git pull failed (offline?): {out.splitlines()[-1] if out else rc}"
    STORE.mkdir(parents=True, exist_ok=True)
    sha = lambda f: hashlib.sha256(f.read_bytes()).hexdigest()
    copied = 0
    for src in SOURCES:
        for f in src.glob("*.zpl") if src.is_dir() else []:
            dst = STORE / f.name
            if not dst.exists() or sha(dst) != sha(f):
                shutil.copy2(f, dst); copied += 1
    files = sorted(STORE.glob("*.zpl"))
    (STORE / "manifest.json").write_text(json.dumps(
        {"synced_at": time.strftime("%Y-%m-%d %H:%M:%S"), "sources": [str(x) for x in SOURCES],
         "files": {f.name: sha(f) for f in files}}, indent=1))
    return copied, len(files), note


def label_files():
    try:
        sync_library()
    except OSError:
        pass
    if not STORE.is_dir():
        return []
    files = sorted(p for p in STORE.glob("*.zpl"))
    pref = [p for n in PREFERRED for p in files if p.name == n]
    return pref + [p for p in files if p not in pref]


def label_preview(path):
    """(pixbuf|None, caption) rendered from the ^GFA graphics in a ZPL file. A recall file
    (^XF) is resolved to the sibling file that stores that format (^DF)."""
    from gi.repository import GdkPixbuf, GLib
    path = Path(path)
    data = path.read_text(errors="replace")
    note = ""
    m = re.search(r"\^XF(\S+?)\^FS", data)
    if m:
        name = m.group(1)
        src = next((q for q in path.parent.glob("*.zpl") if f"^DF{name}" in q.read_text(errors="replace")), None)
        if not src:
            return None, f"Recalls {name} from printer flash (no stored copy found next to this file)"
        data, note = src.read_text(errors="replace"), f"Recalls {name} from printer flash. Stored copy: {src.name}. "
    pw = re.search(r"\^PW(\d+)", data); ll = re.search(r"\^LL(\d+)", data)
    gfx = [(int(x), int(y), int(bpr), h) for x, y, bpr, h in
           re.findall(r"\^FO(\d+),(\d+)\^GFA,\d+,\d+,(\d+),([0-9A-Fa-f]+)", data)]
    if not gfx:
        return None, note + "No bitmap graphic in this file (text/barcode commands only)."
    lut = [b"".join(b"\x00\x00\x00" if b >> (7 - i) & 1 else b"\xff\xff\xff" for i in range(8)) for b in range(256)]
    W = int(pw.group(1)) if pw else max(x + bpr * 8 for x, _, bpr, _ in gfx)
    H = int(ll.group(1)) if ll else max(y + len(h) // 2 // bpr for x, y, bpr, h in gfx)
    canvas = bytearray(b"\xff" * (W * H * 3))
    for x, y, bpr, hexdata in gfx:
        raw = bytes.fromhex(hexdata[: len(hexdata) // 2 * 2])
        for r in range(len(raw) // bpr):
            if y + r >= H: break
            row = b"".join(lut[b] for b in raw[r * bpr:(r + 1) * bpr])[: max(0, (W - x)) * 3]
            canvas[((y + r) * W + x) * 3: ((y + r) * W + x) * 3 + len(row)] = row
    pb = GdkPixbuf.Pixbuf.new_from_bytes(GLib.Bytes.new(bytes(canvas)), GdkPixbuf.Colorspace.RGB, False, 8, W, H, W * 3)
    return pb, f"{note}{W}x{H} dots, {W/203:.1f} x {H/203:.1f} in at 203 dpi"


# ---------------------------------------------------------------- CLI

def describe(st):
    if not st["usb"]:
        return "NOT DETECTED: no Zebra on USB (plug in / power on the printer, try another cable or port)"
    d = st["usb"][0]
    line = f"USB: {d['product']} serial {d['serial'] or '?'}"
    if not st["queue"]:
        return line + "\nCUPS: no queue. Run: ./polybagger_print_manager.py --setup"
    line += f"\nCUPS: queue '{st['queue']}' is {st['queue_state']}" + (f", alerts: {' '.join(st['reasons'])}" if st["reasons"] else "")
    if not st["uri_matches_device"]:
        line += "\nWARNING: queue points at a different serial than the plugged-in printer"
    return line + ("\nREADY" if st["ready"] else "\nNOT READY")


def cli(args):
    if args.setup:
        st = status()
        if not st["usb"]:
            print("No Zebra on USB; plug it in first."); return 2
        rc, out = setup_queue(st["usb"][0]); print(out or "queue created"); return 0 if rc == 0 else 1
    if args.sync:
        c, n, note = sync_library(pull=args.pull); print(f"{n} labels in {STORE} ({c} updated) {note}".strip()); return 0
    if args.watch:
        prev = None
        while True:
            cur = bool(usb_zebras())
            if cur != prev:
                print(time.strftime("%H:%M:%S"), "Zebra PLUGGED IN" if cur else "Zebra UNPLUGGED", flush=True)
                prev = cur
            time.sleep(1)
    st = status()
    if args.status or not args.send:
        print(json.dumps(st, indent=2) if args.json else describe(st))
        return 0 if st["ready"] else 2
    ok, warns = check_zpl(args.send)
    if not ok:
        print("ERROR:", warns[0]); return 1
    if not st["ready"]:
        print(describe(st)); return 2
    for w in warns:
        print("WARNING:", w, file=sys.stderr)
    res = send_and_verify(args.send, st["queue"], progress=lambda m: print(" ", m, file=sys.stderr))
    kind, hint = expectation(args.send)
    res.update(file=str(args.send), expect=hint)
    if res["ok"] and not args.yes and sys.stdin.isatty():
        res["operator_confirmed"] = input(f"{hint} Did it? [y/N] ").strip().lower().startswith("y")
    log_result(res)
    print(json.dumps(res, indent=2) if args.json else
          ("PASS" if res["ok"] else "FAIL") + f": {res['detail']}" + (f" ({res['job']}, {res['seconds']}s)" if res["ok"] else ""))
    return 0 if res["ok"] else 1


# ---------------------------------------------------------------- GUI

CSS = b"""
.zl label { font-size: 15px; }
.zl label.zl-title { font-size: 28px; font-weight: 700; }
.zl label.zl-row-title { font-size: 16px; font-weight: 600; }
.zl label.zl-row-sub { font-size: 13px; opacity: 0.7; }
.zl label.zl-caption { font-size: 13px; opacity: 0.7; }
.zl list row { padding: 10px 14px; }
.zl .zl-card { padding: 18px; border-radius: 10px; }
.zl button.zl-send { font-size: 17px; font-weight: 600; padding: 12px 34px; }
.zl button { padding: 8px 16px; }
.zl .zl-ok { color: @success_color; } .zl .zl-bad { color: @error_color; }
"""


def kind_of(path):
    try:
        d = Path(path).read_text(errors="replace")
    except OSError:
        return "Unreadable"
    if "^XF" in d: return "Recalls from printer flash"
    if "^DF" in d: return "Stores to printer flash (no label)"
    return "Prints a label"


def gui():
    import gi
    gi.require_version("Gtk", "3.0")
    from gi.repository import Gtk, GLib, Gio, Gdk
    try:
        gi.require_version("Granite", "1.0")
        from gi.repository import Granite
    except (ValueError, ImportError):
        Granite = None

    STEPS = [("usb", "Zebra detected on USB"), ("queue", "CUPS queue exists"),
             ("ready", "Queue enabled, nothing stuck"), ("file", "ZPL file valid"),
             ("sent", "Job sent to CUPS"), ("done", "Printer accepted the job")]
    ICON = {"ok": "process-completed-symbolic", "bad": "dialog-error-symbolic", "todo": "media-record-symbolic"}

    def lbl(text="", cls=None, xalign=0.0, wrap=False):
        l = Gtk.Label(label=text, xalign=xalign, wrap=wrap)
        if cls: l.get_style_context().add_class(cls)
        return l

    class Win(Gtk.ApplicationWindow):
        def __init__(self, app):
            super().__init__(application=app, default_width=1120, default_height=800)
            self.get_style_context().add_class("zl")
            prov = Gtk.CssProvider(); prov.load_from_data(CSS)
            Gtk.StyleContext.add_provider_for_screen(Gdk.Screen.get_default(), prov, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
            self.busy = False; self.last = None; self.recent = {}; self.was_plugged = None
            self.files = list(label_files()); self.kinds = {}

            hb = Gtk.HeaderBar(show_close_button=True, title="PolyBagger Print Manager"); self.set_titlebar(hb)
            self.search = Gtk.SearchEntry(placeholder_text="Search labels", width_chars=30)
            self.search.connect("search-changed", lambda *_: self.listbox.invalidate_filter())
            hb.set_custom_title(self.search)
            openb = Gtk.Button.new_from_icon_name("document-open-symbolic", Gtk.IconSize.LARGE_TOOLBAR)
            openb.set_tooltip_text("Open a ZPL file…"); openb.connect("clicked", self.on_browse); hb.pack_start(openb)
            syncb = Gtk.Button.new_from_icon_name("view-refresh-symbolic", Gtk.IconSize.LARGE_TOOLBAR)
            syncb.set_tooltip_text("Update offline label store from GitHub"); syncb.connect("clicked", self.on_sync); hb.pack_start(syncb)
            if Granite:
                s = Granite.Settings.get_default(); g = Gtk.Settings.get_default()
                dark = lambda *_: setattr(g.props, "gtk_application_prefer_dark_theme", s.props.prefers_color_scheme == Granite.SettingsColorScheme.DARK)
                dark(); s.connect("notify::prefers-color-scheme", dark)

            accel = Gtk.AccelGroup(); self.add_accel_group(accel)
            self.search.add_accelerator("grab-focus", accel, Gdk.KEY_f, Gdk.ModifierType.CONTROL_MASK, Gtk.AccelFlags.VISIBLE)

            paned = Gtk.Paned(orientation=Gtk.Orientation.HORIZONTAL, position=340); self.add(paned)

            # left: label list
            self.listbox = Gtk.ListBox(selection_mode=Gtk.SelectionMode.SINGLE)
            self.listbox.set_filter_func(self.row_visible)
            self.listbox.connect("row-selected", lambda *_: self.update_preview())
            self.empty = lbl("No labels match", "zl-caption", 0.5); self.empty.set_margin_top(24)
            left = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
            sw = Gtk.ScrolledWindow(); sw.add(self.listbox)
            left.pack_start(sw, True, True, 0); left.pack_start(self.empty, False, False, 0)
            paned.pack1(left, False, False)
            for p in self.files: self.add_row(p)

            # right: status, preview, actions
            right = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16, margin=24)
            overlay = Gtk.Overlay(); overlay.add(right); paned.pack2(overlay, True, False)
            self.toast = Granite.WidgetsToast.new("") if Granite and hasattr(Granite, "WidgetsToast") else None
            if self.toast: overlay.add_overlay(self.toast)

            banner = Gtk.Box(spacing=18)
            self.big = Gtk.Image(pixel_size=64)
            tb = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4, valign=Gtk.Align.CENTER)
            self.title = lbl("", "zl-title"); self.sub = lbl("", "zl-caption", wrap=True)
            tb.pack_start(self.title, False, False, 0); tb.pack_start(self.sub, False, False, 0)
            banner.pack_start(self.big, False, False, 0); banner.pack_start(tb, True, True, 0)
            right.pack_start(banner, False, False, 0)

            pcard = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8); pcard.get_style_context().add_class("card")
            pcard.get_style_context().add_class("zl-card")
            self.pname = lbl("Select a label", "zl-row-title")
            self.preview = Gtk.Image(); self.preview_cap = lbl("", "zl-caption", wrap=True)
            pcard.pack_start(self.pname, False, False, 0); pcard.pack_start(self.preview, True, True, 6)
            pcard.pack_start(self.preview_cap, False, False, 0)
            right.pack_start(pcard, True, True, 0)

            grid = Gtk.Grid(row_spacing=8, column_spacing=12); self.rows = {}
            for i, (k, text) in enumerate(STEPS):
                img = Gtk.Image(icon_name=ICON["todo"]); sp = Gtk.Spinner()
                st = Gtk.Stack(); st.add_named(img, "img"); st.add_named(sp, "spin")
                det = lbl("", "zl-caption", 1.0); det.set_hexpand(True)
                grid.attach(st, 0, i, 1, 1); grid.attach(lbl(text), 1, i, 1, 1); grid.attach(det, 2, i, 1, 1)
                self.rows[k] = (img, sp, st, det)
            exp = Gtk.Expander(label="Checks", expanded=True); exp.add(grid); right.pack_start(exp, False, False, 0)

            self.confirm = Gtk.InfoBar(message_type=Gtk.MessageType.QUESTION, revealed=False, no_show_all=True)
            self.confirm_lab = lbl("", wrap=True); self.confirm.get_content_area().add(self.confirm_lab)
            self.confirm.add_button("Yes", Gtk.ResponseType.YES); self.confirm.add_button("No", Gtk.ResponseType.NO)
            self.confirm.connect("response", self.on_confirm); right.pack_start(self.confirm, False, False, 0)

            self.setup_btn = Gtk.Button(label="Set Up Printer Queue…"); self.setup_btn.connect("clicked", self.on_setup)
            self.cancel_btn = Gtk.Button(label="Cancel Stuck Jobs"); self.cancel_btn.get_style_context().add_class("destructive-action")
            self.cancel_btn.connect("clicked", self.on_cancel_jobs)
            self.test_btn = Gtk.Button(label="Send Test Label"); self.test_btn.connect("clicked", self.on_test)
            self.send_btn = Gtk.Button(label="Send to Printer"); self.send_btn.get_style_context().add_class("suggested-action")
            self.send_btn.get_style_context().add_class("zl-send"); self.send_btn.connect("clicked", self.on_send)
            bb = Gtk.Box(spacing=10)
            for b in (self.setup_btn, self.cancel_btn): bb.pack_start(b, False, False, 0)
            bb.pack_end(self.send_btn, False, False, 0); bb.pack_end(self.test_btn, False, False, 0)
            right.pack_start(bb, False, False, 0)

            lexp = Gtk.Expander(label="Log"); lsw = Gtk.ScrolledWindow(min_content_height=90)
            self.log = Gtk.TextView(editable=False, monospace=True); lsw.add(self.log); lexp.add(lsw)
            right.pack_start(lexp, False, False, 0)

            GLib.timeout_add_seconds(1, self.poll)
            self.show_all(); self.confirm.hide()
            first = self.listbox.get_row_at_index(0)
            if first: self.listbox.select_row(first)
            self.refresh(first=True)
            shot = os.environ.get("PBPM_SHOT")
            if shot:  # dev aid: save a PNG of the window content, then quit
                def snap():
                    import cairo
                    c = self.get_child(); a = c.get_allocation()
                    surf = cairo.ImageSurface(cairo.FORMAT_ARGB32, a.width, a.height)
                    cr = cairo.Context(surf); cr.set_source_rgb(1, 1, 1); cr.paint(); c.draw(cr)
                    surf.write_to_png(shot); self.get_application().quit(); return False
                GLib.timeout_add(1500, snap)

        # -- label list
        def add_row(self, path):
            self.kinds[path] = kind = kind_of(path)
            row = Gtk.ListBoxRow(); row.path = path
            box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
            box.pack_start(lbl(path.stem.replace("_", " "), "zl-row-title"), False, False, 0)
            box.pack_start(lbl(f"{kind} · {max(1, path.stat().st_size // 1024) if path.stat().st_size >= 1024 else path.stat().st_size} {"KB" if path.stat().st_size >= 1024 else "bytes"}", "zl-row-sub"), False, False, 0)
            row.add(box); self.listbox.add(row); row.show_all(); return row

        def row_visible(self, row):
            q = self.search.get_text().strip().lower()
            ok = not q or all(w in (row.path.stem + " " + self.kinds.get(row.path, "")).lower().replace("_", " ") for w in q.split())
            return ok

        def current_file(self):
            r = self.listbox.get_selected_row(); return r.path if r else None

        def say(self, msg):
            b = self.log.get_buffer(); b.insert(b.get_end_iter(), time.strftime("%H:%M:%S ") + msg + "\n")

        def mark(self, key, state, detail=""):
            img, sp, st, det = self.rows[key]
            if state == "work": sp.start(); st.set_visible_child_name("spin")
            else:
                sp.stop(); img.set_from_icon_name(ICON[state], Gtk.IconSize.LARGE_TOOLBAR); st.set_visible_child_name("img")
            det.set_text(detail)

        def update_preview(self):
            p = self.current_file()
            self.empty.set_visible(self.listbox.get_row_at_index(0) is None)
            if not p: return
            self.pname.set_text(p.stem.replace("_", " "))
            try:
                pb, cap = label_preview(p)
            except Exception as e:
                pb, cap = None, f"No preview: {e}"
            if pb:  # labels are sent upside down; invert for auditing only
                from gi.repository import GdkPixbuf
                pb = pb.rotate_simple(GdkPixbuf.PixbufRotation.UPSIDEDOWN)
                cap += ". Preview inverted 180° for auditing only; the file is sent as-is."
                w = 640
                pb = pb.scale_simple(w, int(pb.get_height() * w / pb.get_width()), 2)
                self.preview.set_from_pixbuf(pb)
            else: self.preview.clear()
            self.preview_cap.set_text(cap)

        def poll(self):
            if bool(usb_zebras()) != self.was_plugged and not self.busy: self.refresh()
            return True

        def refresh(self, first=False):
            self.st = st = status(); plugged = bool(st["usb"])
            if not first and plugged != self.was_plugged:
                msg = "Zebra plugged in" if plugged else "Zebra unplugged"; self.say(msg)
                if self.toast: self.toast.set_title(msg); self.toast.send_notification()
            self.was_plugged = plugged
            d = st["usb"][0] if plugged else None
            self.mark("usb", "ok" if plugged else "bad", f"{d['product']} · {d['serial']}" if d else "not found")
            self.mark("queue", "ok" if st["queue"] else ("bad" if plugged else "todo"), st["queue"] or "none")
            self.mark("ready", "ok" if st["ready"] else ("bad" if st["queue"] else "todo"),
                      st["queue_state"] + (f" · {' '.join(st['reasons'])}" if st["reasons"] else ""))
            for k in ("file", "sent", "done"): self.mark(k, "todo")
            icon, title, sub = (("printer", "Printer ready", "Pick a label on the left and press Send.") if st["ready"] else
                                ("printer-error", "Detected, not ready",
                                 "Create the printer queue." if not st["queue"] else
                                 "A job is stuck waiting for the printer. Check power, media and ribbon, then cancel stuck jobs." if "waiting-for-printer" in st["reasons"] else
                                 "Check the queue and printer alerts.") if plugged else
                                ("printer-error", "No Zebra detected", "Plug in the USB cable and power the printer on. This window updates by itself."))
            self.big.set_from_icon_name(icon, Gtk.IconSize.DIALOG); self.big.set_pixel_size(64)
            self.title.set_text(title); self.sub.set_text(sub)
            self.setup_btn.set_visible(plugged and not st["queue"])
            self.cancel_btn.set_visible("waiting-for-printer" in st["reasons"])
            self.send_btn.set_sensitive(st["ready"] and not self.busy); self.test_btn.set_sensitive(st["ready"] and not self.busy)

        # -- actions
        def on_browse(self, _):
            dlg = Gtk.FileChooserNative(title="Open ZPL file", transient_for=self, action=Gtk.FileChooserAction.OPEN)
            f = Gtk.FileFilter(); f.set_name("ZPL"); f.add_pattern("*.zpl"); f.add_pattern("*.ZPL"); dlg.add_filter(f)
            if dlg.run() == Gtk.ResponseType.ACCEPT:
                self.listbox.select_row(self.add_row(Path(dlg.get_filename())))

        def on_sync(self, _):
            def work():
                c, n, note = sync_library(pull=True)
                def done():
                    self.say(f"Label store: {n} labels, {c} updated. {note}")
                    for p in sorted(STORE.glob("*.zpl")):
                        if p not in self.kinds: self.add_row(p)
                GLib.idle_add(done)
            threading.Thread(target=work, daemon=True).start()

        def on_setup(self, _):
            self.say("Creating CUPS queue (authentication required)…")
            def work():
                rc, out = setup_queue(self.st["usb"][0])
                GLib.idle_add(lambda: (self.say("Queue created" if rc == 0 else f"Setup failed: {out}"), self.refresh()))
            threading.Thread(target=work, daemon=True).start()

        def on_cancel_jobs(self, _):
            rc, out = run(["cancel", "-a", self.st["queue"]]); self.say(f"Cancelled queued jobs: {out or 'ok'}"); self.refresh()

        def on_test(self, _):
            fd, tmp = tempfile.mkstemp(suffix=".zpl")
            os.write(fd, TEST_LABEL.format(stamp=time.strftime("%Y-%m-%d %H:%M:%S")).encode()); os.close(fd)
            self.start_send(Path(tmp), temp=True)

        def on_send(self, _):
            p = self.current_file()
            if p: self.start_send(p)

        def start_send(self, path, temp=False):
            for k in ("file", "sent", "done"): self.mark(k, "todo")
            last = self.recent.get(str(path))
            if last and time.time() - last < 120 and not temp:
                d = Gtk.MessageDialog(transient_for=self, message_type=Gtk.MessageType.WARNING, buttons=Gtk.ButtonsType.NONE,
                                      text="Sent this file moments ago",
                                      secondary_text=f"{path.name} was sent {int(time.time() - last)} s ago. Send it again?")
                d.add_button("Cancel", Gtk.ResponseType.CANCEL); d.add_button("Send Again", Gtk.ResponseType.OK)
                resp = d.run(); d.destroy()
                if resp != Gtk.ResponseType.OK: return
            self.recent[str(path)] = time.time()
            ok, warns = check_zpl(path)
            if not ok: self.mark("file", "bad", warns[0]); return
            self.mark("file", "ok", f"{path.stat().st_size // 1024} KB" + (" · warning" if warns else ""))
            for w in warns: self.say("WARNING: " + w)
            self.busy = True; self.send_btn.set_sensitive(False); self.test_btn.set_sensitive(False)
            self.confirm.hide(); self.mark("sent", "work"); self.sub.set_text("Sending…")
            queue = self.st["queue"]
            def work():
                res = send_and_verify(path, queue, progress=lambda m: GLib.idle_add(self.say, m))
                GLib.idle_add(self.finish, path, res, temp)
            threading.Thread(target=work, daemon=True).start()

        def finish(self, path, res, temp):
            self.busy = False; res["file"] = str(path)
            if res["ok"]:
                self.mark("sent", "ok", res["job"]); self.mark("done", "ok", f"{res['seconds']} s")
                _, hint = expectation(path)
                self.title.set_text("Print command went through"); self.sub.set_text(res["detail"])
                self.confirm_lab.set_text(hint + "\nDid that happen?"); self.confirm.set_revealed(True); self.confirm.show_all()
                self.last = res
            else:
                self.mark("sent", "ok" if res.get("job") else "bad", res.get("job", "")); self.mark("done", "bad", res["stage"])
                self.big.set_from_icon_name("printer-error", Gtk.IconSize.DIALOG)
                self.title.set_text("Print did NOT go through"); self.sub.set_text(res["detail"]); log_result(res)
            self.say(("PASS " if res["ok"] else "FAIL ") + res["detail"])
            if temp: os.unlink(path)
            st = status(); self.st = st
            self.cancel_btn.set_visible("waiting-for-printer" in st["reasons"])
            self.send_btn.set_sensitive(st["ready"]); self.test_btn.set_sensitive(st["ready"])

        def on_confirm(self, bar, resp):
            if self.last:
                self.last["operator_confirmed"] = resp == Gtk.ResponseType.YES
                log_result(self.last); self.say(f"Operator confirmed: {self.last['operator_confirmed']}")
            bar.set_revealed(False); bar.hide()

    class App(Gtk.Application):
        def __init__(self):
            super().__init__(application_id="io.techmore.PolyBaggerPrintManager", flags=Gio.ApplicationFlags.FLAGS_NONE)
        def do_activate(self):
            (self.props.active_window or Win(self)).present()

    return App().run([])


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--status", action="store_true"); ap.add_argument("--send", metavar="FILE")
    ap.add_argument("--watch", action="store_true"); ap.add_argument("--setup", action="store_true")
    ap.add_argument("--sync", action="store_true", help="refresh the offline label store"); ap.add_argument("--pull", action="store_true", help="with --sync: git pull the thril repo first")
    ap.add_argument("--json", action="store_true"); ap.add_argument("--yes", action="store_true", help="skip the 'did it print?' prompt")
    a = ap.parse_args()
    sys.exit(cli(a) if (a.status or a.send or a.watch or a.setup or a.sync) else gui())
