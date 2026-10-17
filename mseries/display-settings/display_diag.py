"""Plain-language display diagnostics from facts the kernel and desktop already expose.

collect() gathers the facts; diagnose() is pure so it can be tested with made-up facts.
Each finding is (severity, title, detail, fix) with severity in ok/info/warn/bad and fix
either None or "reapply" (the app offers a button).
"""
import glob, os, re, subprocess

OK, INFO, WARN, BAD = "ok", "info", "warn", "bad"


def _read(path):
    try:
        with open(path) as f:
            return f.read().strip()
    except OSError:
        return None


def collect(gala_outputs):
    """gala_outputs: {connector: {"modes": [(w,h,rate)], "current": (w,h,rate)|None, "preferred": (...)}}."""
    drm = {}
    for d in glob.glob("/sys/class/drm/card*-*"):
        name = os.path.basename(d).split("-", 1)[1]
        drm[name] = {"status": _read(d + "/status"), "enabled": _read(d + "/enabled"),
                     "kernel_modes": len((_read(d + "/modes") or "").split()),
                     "edid": os.path.getsize(d + "/edid") if os.path.exists(d + "/edid") else 0}
    tb = []
    for d in glob.glob("/sys/bus/thunderbolt/devices/*"):
        n = _read(d + "/device_name")
        if n:
            tb.append(n)
    try:
        log = subprocess.run(["dmesg"], capture_output=True, text=True, timeout=5).stdout.splitlines()
    except Exception:
        log = []
    keep = re.compile(r"DP2HDMI HPD|set_digital_out_mode finished|swallowed swap.*(timin|timings)|DPRX|"
                      r"DP source (preparation|stop) failed|\(DP\): (activating|not active)|DP OUT resource")
    return {"gala": gala_outputs, "drm": drm, "thunderbolt": tb,
            "log": [l for l in log if keep.search(l)][-400:],
            "dprx_bypass": _read("/sys/module/thunderbolt/parameters/dprx_bypass")}


def _last(log, pat):
    idx = -1
    for i, l in enumerate(log):
        if re.search(pat, l):
            idx = i
    return idx


def diagnose(f):
    out = []
    gala, drm, log = f["gala"], f["drm"], f["log"]
    ext_drm = {n: v for n, v in drm.items() if not n.startswith("eDP")}
    connected = [n for n, v in ext_drm.items() if v["status"] == "connected"]

    # Kernel sees a monitor, desktop doesn't.
    for n in connected:
        gname = next((g for g in gala if g == n or g.split("-")[0] == n.split("-")[0]), None)
        if gname is None:
            out.append((BAD, f"{n}: detected by the kernel but not in the desktop",
                        "The display driver reports a monitor, but the desktop has no output for it.", "reapply"))
    # A completed modeset is not a picture: the display coprocessor logs "swallowed swap" when it
    # discards frames Gala submits (controller power 0 / timings not enabled). Judge by those.
    hp = _last(log, r"DP2HDMI HPD irq, connected:1")
    ms = _last(log, r"set_digital_out_mode finished")
    swallowed = _last(log, r"swallowed swap")
    for n in connected:
        if swallowed > ms:
            out.append((BAD, f"{n}: detected, but the display engine is discarding frames",
                        "The monitor is plugged in and a mode may have been set, but the display coprocessor is "
                        "dropping the frames the desktop sends ('controller power 0, timings not enabled'). The "
                        "screen will be black or say 'no signal'. Re-applying the mode sometimes recovers it.", "reapply"))
        elif ms >= 0 and ms >= hp:
            out.append((INFO, f"{n}: mode set, no dropped frames logged",
                        "The display engine accepted a mode and is not discarding frames. This cannot confirm that "
                        "the monitor is showing a picture; if it is black, report it.", None))
        elif hp > ms:
            out.append((WARN, f"{n}: plugged in, waiting for a video mode",
                        "The link came up but no mode has been set since the plug-in.", "reapply"))
        else:
            out.append((INFO, f"{n}: monitor detected", "No mode-set recorded yet in this boot's log.", None))
    if not connected:
        out.append((INFO, "No external display detected",
                    "Nothing is reporting hot-plug on the built-in HDMI. Check the cable, that the monitor is on "
                    "and on the right input, then replug.", None))

    # Dock over USB4 but no video from it.
    docks = [n for n in f["thunderbolt"] if "dock" in n.lower() or "wd22" in n.lower()]
    if docks:
        formed = _last(log, r"\(DP\): activating")
        failed = _last(log, r"DP source preparation failed")
        timeout = _last(log, r"DPRX read timeout")
        dock_out = [n for n in connected if n.startswith("DP-")]
        if dock_out:
            out.append((OK, f"{docks[0]}: video output present", "The dock's display is exposed to the desktop.", None))
        elif failed >= 0:
            out.append((WARN, f"{docks[0]}: connected, display tunnel starts but the Mac's display engine times out",
                        "USB devices on the dock work. The dock's video link is created, then the display coprocessor "
                        "does not finish link setup (DP source preparation failed). Known limit of this kernel; use the "
                        "built-in HDMI for now.", None))
        elif timeout >= 0:
            out.append((WARN, f"{docks[0]}: connected, but its monitor does not answer",
                        "The tunnel formed but the monitor behind the dock did not respond to DisplayPort queries.", None))
        elif formed >= 0:
            out.append((INFO, f"{docks[0]}: video tunnel formed, waiting", "Link created; no result yet.", None))
        else:
            out.append((INFO, f"{docks[0]}: connected for USB, no video yet",
                        "The dock is online but nothing is plugged into its HDMI/DisplayPort, or the monitor "
                        "has not reported itself yet. Wake the monitor / select its input, or replug the cable "
                        "at the dock.", None))
        if f.get("dprx_bypass") == "N":
            out.append((WARN, "DPRX bypass is off", "Unplugging the dock now can hang the USB4 port.", None))

    # Mode limits per output.
    for name, g in gala.items():
        if name.startswith("eDP"):
            continue
        modes = g["modes"]
        big = [m for m in modes if m[0] >= 3840]
        if big and max(m[2] for m in big) < 31:
            out.append((INFO, f"{name}: 4K is only offered at {max(m[2] for m in big):.0f} Hz",
                        "The monitor/cable/port combination does not advertise a faster 4K mode, so it is not selectable.", None))
        if g["current"] and g["preferred"] and g["current"][:2] != g["preferred"][:2]:
            out.append((INFO, f"{name}: not at its preferred resolution",
                        f"Running {g['current'][0]}x{g['current'][1]}, the monitor prefers {g['preferred'][0]}x{g['preferred'][1]}.", None))
    return out
