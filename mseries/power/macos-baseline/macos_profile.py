#!/usr/bin/env python3
"""macOS power baseline for the M1 Pro, so Linux has a measured target per category.

Run on the same MacBook Pro, booted into macOS, on battery:

    sudo python3 mseries/power/macos-baseline/macos_profile.py            # guided, all scenarios
    sudo python3 mseries/power/macos-baseline/macos_profile.py --only idle_minimal,idle_screen_off
    python3 mseries/power/macos-baseline/macos_profile.py --resummarize results/<run-dir>

Everything is read-only except what a scenario says it does (screen off, opening Safari, a CPU burst).
It never changes brightness, refresh rate, Wi-Fi or Bluetooth; it records them so the Linux run can match.

Sources:
  powermetrics (plist)  CPU/GPU/ANE power, per-cluster frequency, active and power-down residency,
                        per-process energy impact and wakeups, network and disk rates, thermal pressure
  ioreg AppleSmartBattery  whole-machine load (PowerTelemetryData.SystemLoad), battery V x I,
                        charge, health, cycles, temperature
  pmset / system_profiler / launchctl  inventory, sleep and wake history, assertions
Reports median and p10/p90 per metric, like the Linux harness (EFFICIENCY-GOALS.md, method).
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import math
import multiprocessing as mp
import os
import platform
import plistlib
import re
import shutil
import signal
import statistics
import subprocess
import sys
import threading
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
RESULTS = HERE / "results"

WEB_LOOP_URLS = [
    "https://en.wikipedia.org/wiki/Apple_M1",
    "https://github.com/techmore/ElementaryOS_MSeries",
    "https://news.ycombinator.com/",
    "https://www.bbc.com/news",
    "https://developer.mozilla.org/en-US/docs/Web/CSS",
    "https://elementary.io/",
]

# Each scenario: what the owner does, how long to sample, the powermetrics interval.
SCENARIOS = {
    "idle_minimal": dict(
        title="Idle floor, screen on, nothing open",
        prep="Quit every app except Terminal (Cmd-Q, check the Dock). Leave Wi-Fi and Bluetooth as you normally run them. "
             "Do not touch the Mac while it samples.",
        seconds=180, interval_ms=1000),
    "idle_as_used": dict(
        title="Idle with your usual apps open",
        prep="Open the apps you normally keep open on Linux (browser, Claude, ChatGPT, Signal, terminal). Let them settle, "
             "then leave the Mac alone.",
        seconds=180, interval_ms=1000),
    "idle_screen_off": dict(
        title="Idle, display asleep",
        prep="Same app state as idle_minimal. The script puts the display to sleep and wakes it when done.",
        seconds=150, interval_ms=1000, action="display_off"),
    "web_loop": dict(
        title="Scripted web browsing in Safari",
        prep="Safari will open a fixed list of pages, one every 15 s. Leave it alone.",
        seconds=180, interval_ms=1000, action="web_loop"),
    "video_local": dict(
        title="Local 1080p H.264 file in QuickTime",
        prep="QuickTime opens test-1080p-h264.mp4 (make_test_videos.sh, same file on Linux) and plays it windowed.",
        seconds=150, interval_ms=1000, action="video_local", video="test-1080p-h264.mp4"),
    "video_local_1440p": dict(
        title="Local 1440p (2K) H.264 file in QuickTime",
        prep="QuickTime opens test-1440p-h264.mp4 and plays it windowed.",
        seconds=150, interval_ms=1000, action="video_local", video="test-1440p-h264.mp4"),
    "video_local_2160p": dict(
        title="Local 2160p (4K) H.264 file in QuickTime",
        prep="QuickTime opens test-2160p-h264.mp4 and plays it windowed.",
        seconds=150, interval_ms=1000, action="video_local", video="test-2160p-h264.mp4"),
    "video_web": dict(
        title="YouTube 1080p in the browser",
        prep="Start a 1080p YouTube video windowed (Safari, and repeat with Brave to compare with Linux). "
             "Press Enter once it is playing.",
        seconds=150, interval_ms=1000),
    "video_web_1440p": dict(
        title="YouTube 1440p (2K) in the browser",
        prep="Same video, quality set to 1440p (gear icon), windowed. Press Enter once it is playing at 1440p.",
        seconds=150, interval_ms=1000),
    "video_web_2160p": dict(
        title="YouTube 2160p (4K) in the browser",
        prep="Same video, quality set to 2160p (gear icon), windowed. Press Enter once it is playing at 2160p.",
        seconds=150, interval_ms=1000),
    "cpu_burst": dict(
        title="All-core burst and return to idle",
        prep="Same app state as idle_minimal. The script loads every core for 20 s, then stops and watches it settle.",
        seconds=60, interval_ms=100, action="cpu_burst"),
}
DEFAULT_ORDER = ["idle_minimal", "idle_screen_off", "idle_as_used", "web_loop",
                 "video_local", "video_local_1440p", "video_local_2160p",
                 "video_web", "video_web_1440p", "video_web_2160p", "cpu_burst"]


def video_file(cfg, args):
    """The clip a video_local scenario plays: --video overrides 1080p, the rest come from --video-dir."""
    if cfg.get("video") == "test-1080p-h264.mp4" and args.video:
        path = Path(args.video).expanduser()
        return str(path) if path.is_file() else None
    path = Path(args.video_dir).expanduser() / cfg["video"]
    return str(path) if path.is_file() else None


def default_video_dir():
    """~/Movies of the person who ran sudo, not root's."""
    user = os.environ.get("SUDO_USER")
    home = Path(f"~{user}").expanduser() if user else Path.home()
    return str(home / "Movies")


# ---------------------------------------------------------------- helpers

def run(cmd, timeout=60, user=False):
    """Run a command, return stdout text ('' on failure). user=True drops to the invoking user."""
    if user and os.geteuid() == 0 and os.environ.get("SUDO_USER"):
        cmd = ["sudo", "-u", os.environ["SUDO_USER"]] + cmd
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout).stdout
    except Exception as exc:  # noqa: BLE001 - inventory is best effort
        return f"<error: {exc}>"


def stats(values):
    vals = sorted(v for v in values if isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v))
    if not vals:
        return None
    def pct(p):
        k = (len(vals) - 1) * p
        lo, hi = int(k), min(int(k) + 1, len(vals) - 1)
        return vals[lo] + (vals[hi] - vals[lo]) * (k - lo)
    return {"median": round(statistics.median(vals), 3), "p10": round(pct(0.10), 3),
            "p90": round(pct(0.90), 3), "n": len(vals)}


def signed(v):
    """ioreg prints negative amperage as unsigned 64-bit."""
    if isinstance(v, int) and v > 2**63:
        return v - 2**64
    return v


# ---------------------------------------------------------------- battery / system load sampler

def read_battery():
    try:
        raw = subprocess.run(["ioreg", "-arn", "AppleSmartBattery"], capture_output=True, timeout=10).stdout
    except (OSError, subprocess.TimeoutExpired):
        return {}
    try:
        b = plistlib.loads(raw)[0]
    except Exception:  # noqa: BLE001
        return {}
    tel = b.get("PowerTelemetryData") or {}
    volt = b.get("Voltage") or b.get("AppleRawBatteryVoltage")
    amp = signed(b.get("InstantAmperage", b.get("Amperage")))
    out = {
        "t": time.time(),
        "system_load_w": tel.get("SystemLoad", None) and tel["SystemLoad"] / 1000.0,
        "system_power_in_w": tel.get("SystemPowerIn", None) and tel["SystemPowerIn"] / 1000.0,
        "battery_power_w": tel.get("BatteryPower", None) and tel["BatteryPower"] / 1000.0,
        "battery_flow_w": (volt * amp / 1e6) if (volt and amp is not None) else None,
        "charge_pct": b.get("CurrentCapacity"),
        "raw_charge_mah": b.get("AppleRawCurrentCapacity"),
        "raw_max_mah": b.get("AppleRawMaxCapacity"),
        "design_mah": b.get("DesignCapacity"),
        "cycles": b.get("CycleCount"),
        "temp_c": (b["Temperature"] / 100.0) if b.get("Temperature") else None,
        "external": b.get("ExternalConnected"),
        "charging": b.get("IsCharging"),
    }
    return out


class BatterySampler(threading.Thread):
    def __init__(self, period=1.0):
        super().__init__(daemon=True)
        self.period, self.samples, self._halt = period, [], threading.Event()

    def run(self):
        while not self._halt.is_set():
            s = read_battery()
            if s:
                self.samples.append(s)
            self._halt.wait(self.period)

    def stop(self):
        self._halt.set()
        self.join(timeout=5)


# ---------------------------------------------------------------- powermetrics

def available_samplers():
    try:
        help_result = subprocess.run(["powermetrics", "-h"], capture_output=True, text=True, timeout=20)
        text = help_result.stdout + "\n" + help_result.stderr
    except (OSError, subprocess.TimeoutExpired):
        text = ""
    # Match the supported-samplers section, not the earlier --samplers option synopsis.
    section = text.partition("The following samplers are supported by --samplers:")[2]
    section = section.split("and the following sampler groups", 1)[0]
    found = set(re.findall(r"^\s+([a-z_]+)\s+", section, re.M))
    wanted = ["cpu_power", "gpu_power", "ane_power", "thermal", "tasks", "network", "disk", "battery"]
    have = [s for s in wanted if s in found]
    return have or ["cpu_power", "gpu_power", "tasks", "thermal"]


def start_powermetrics(out_path, interval_ms, count, samplers):
    cmd = ["powermetrics", "-f", "plist", "-i", str(interval_ms), "-n", str(count),
           "-s", ",".join(samplers), "--show-process-energy", "-o", str(out_path)]
    return subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)


def parse_powermetrics(path):
    data = Path(path).read_bytes()
    out = []
    for chunk in data.split(b"\x00"):
        chunk = chunk.strip()
        if not chunk:
            continue
        try:
            out.append(plistlib.loads(chunk))
        except Exception:  # noqa: BLE001 - a truncated last sample
            continue
    return out


def mw(d, *keys):
    for k in keys:
        if isinstance(d.get(k), (int, float)):
            return d[k] / 1000.0
    return None


def flatten_sample(s):
    """One powermetrics sample -> flat metrics dict (watts, MHz, %)."""
    p = s.get("processor", {}) or {}
    g = s.get("gpu", {}) or {}
    row = {
        "t_elapsed_ns": s.get("elapsed_ns"),
        "cpu_w": mw(p, "cpu_power"),
        "gpu_w": mw(p, "gpu_power") if p.get("gpu_power") is not None else mw(g, "gpu_power"),
        "ane_w": mw(p, "ane_power"),
        "soc_combined_w": mw(p, "combined_power", "package_power"),
        "dram_w": mw(p, "dram_power"),
        "gpu_mhz": g.get("freq_hz") and g["freq_hz"] / 1e6,
        "gpu_active_pct": (1 - g["idle_ratio"]) * 100 if isinstance(g.get("idle_ratio"), (int, float)) else None,
        "thermal_pressure": s.get("thermal_pressure"),
    }
    for c in p.get("clusters", []) or []:
        name = (c.get("name") or "cluster").replace("-Cluster", "").lower()   # e, p0, p1
        row[f"{name}_mhz"] = c.get("freq_hz") and c["freq_hz"] / 1e6
        if isinstance(c.get("idle_ratio"), (int, float)):
            row[f"{name}_active_pct"] = (1 - c["idle_ratio"]) * 100
        cpus = c.get("cpus") or []
        downs = [x.get("down_ratio") for x in cpus if isinstance(x.get("down_ratio"), (int, float))]
        idles = [x.get("idle_ratio") for x in cpus if isinstance(x.get("idle_ratio"), (int, float))]
        if downs and idles and sum(idles) > 0:
            # share of idle time spent power-gated: Linux equivalent is CPU PD residency / all idle
            row[f"{name}_deep_idle_share_pct"] = 100 * sum(downs) / max(sum(idles), 1e-9)
    at = s.get("all_tasks") or {}
    row["idle_wakeups_per_s"] = at.get("idle_wakeups_per_s")
    row["intr_wakeups_per_s"] = at.get("intr_wakeups_per_s")
    row["cpu_ms_per_s_all"] = at.get("cputime_ms_per_s")
    row["energy_impact_all"] = at.get("energy_impact_per_s", at.get("energy_impact"))
    net = s.get("network") or {}
    row["net_in_Bps"], row["net_out_Bps"] = net.get("ibyte_rate"), net.get("obyte_rate")
    disk = s.get("disk") or {}
    row["disk_read_Bps"], row["disk_write_Bps"] = disk.get("rbytes_per_s"), disk.get("wbytes_per_s")
    return row


def task_table(samples, top=15):
    agg = {}
    for s in samples:
        for t in s.get("tasks", []) or []:
            key = t.get("name") or str(t.get("pid"))
            a = agg.setdefault(key, {"energy": [], "cpu_ms_s": [], "idle_wk": [], "intr_wk": []})
            a["energy"].append(t.get("energy_impact_per_s", t.get("energy_impact", 0)) or 0)
            a["cpu_ms_s"].append(t.get("cputime_ms_per_s", 0) or 0)
            a["idle_wk"].append(t.get("idle_wakeups_per_s", 0) or 0)
            a["intr_wk"].append(t.get("intr_wakeups_per_s", 0) or 0)
    n = max(len(samples), 1)
    rows = []
    for name, a in agg.items():
        # absent in a sample == 0 that second
        rows.append({"process": name,
                     "energy_impact": round(sum(a["energy"]) / n, 2),
                     "cpu_ms_per_s": round(sum(a["cpu_ms_s"]) / n, 2),
                     "idle_wakeups_per_s": round(sum(a["idle_wk"]) / n, 1),
                     "intr_wakeups_per_s": round(sum(a["intr_wk"]) / n, 1)})
    rows.sort(key=lambda r: r["energy_impact"], reverse=True)
    return rows[:top]


# ---------------------------------------------------------------- scenario actions

def _busy(stop_at):
    x = 0
    while time.time() < stop_at:
        x = (x * 1103515245 + 12345) & 0xFFFFFFFF


def display_off():
    run(["pmset", "displaysleepnow"])


def display_on():
    run(["caffeinate", "-u", "-t", "2"])


def web_loop(stop_evt):
    i = 0
    while not stop_evt.is_set():
        run(["open", "-a", "Safari", WEB_LOOP_URLS[i % len(WEB_LOOP_URLS)]], user=True)
        i += 1
        stop_evt.wait(15)


def video_local(path):
    # QuickTime's document dictionary exposes file/name, not a stable document ID.
    path = str(Path(path).resolve())
    script = ('tell application "QuickTime Player"\n'
              f'set targetFile to POSIX file {json.dumps(path)}\n'
              'repeat with existing in documents\n'
              'try\nif (file of existing as text) is (targetFile as text) then return "already-open"\nend try\n'
              'end repeat\nset clip to open targetFile\n'
              'set looping of clip to true\nplay clip\nreturn playing of clip\nend tell')
    result = run(["osascript", "-e", script], user=True).strip()
    if result != "true":
        raise RuntimeError("QuickTime could not play the requested clip (close an already-open test clip first)")
    return path


def video_stop(path):
    if path:
        script = ('tell application "QuickTime Player"\n'
                  f'set targetFile to POSIX file {json.dumps(path)}\n'
                  'repeat with clip in documents\ntry\n'
                  'if (file of clip as text) is (targetFile as text) then\n'
                  'close clip saving no\nexit repeat\nend if\nend try\nend repeat\nend tell')
        run(["osascript", "-e", script], user=True)


def stop_requested(_signum, _frame):
    raise KeyboardInterrupt


def cleanup_process(proc):
    if proc is None:
        return
    if proc.poll() is None:
        proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait()


def validate_run_args(ap, args):
    if not math.isfinite(args.scale) or args.scale <= 0:
        ap.error("--scale must be finite and greater than zero")
    if args.settle < 0:
        ap.error("--settle must be nonnegative")
    order = args.only.split(",") if args.only else DEFAULT_ORDER
    if any(name not in SCENARIOS for name in order):
        ap.error("--only contains an unknown scenario")
    return order


# ---------------------------------------------------------------- inventory: what macOS is doing

def inventory(outdir: Path):
    inv = outdir / "inventory"
    inv.mkdir(parents=True, exist_ok=True)
    cmds = {
        "sw_vers.txt": ["sw_vers"],
        "hw.txt": ["sysctl", "hw.model", "machdep.cpu.brand_string", "hw.memsize", "hw.perflevel0.logicalcpu",
                   "hw.perflevel1.logicalcpu", "kern.boottime"],
        "pmset_settings.txt": ["pmset", "-g", "custom"],
        "pmset_live.txt": ["pmset", "-g"],
        "pmset_assertions.txt": ["pmset", "-g", "assertions"],
        "pmset_therm.txt": ["pmset", "-g", "therm"],
        "pmset_batt.txt": ["pmset", "-g", "batt"],
        "pmset_stats.txt": ["pmset", "-g", "stats"],
        "pmset_sched.txt": ["pmset", "-g", "sched"],
        "pmset_log.txt": ["pmset", "-g", "log"],
        "launchctl_system.txt": ["launchctl", "list"],
        "ps.txt": ["ps", "-axo", "pid,ppid,user,%cpu,rss,etime,comm"],
        "displays.json": ["system_profiler", "-json", "SPDisplaysDataType"],
        "power.json": ["system_profiler", "-json", "SPPowerDataType"],
        "bluetooth.json": ["system_profiler", "-json", "SPBluetoothDataType"],
        "wifi.json": ["system_profiler", "-json", "SPAirPortDataType"],
        "usb.json": ["system_profiler", "-json", "SPUSBDataType"],
        "audio.json": ["system_profiler", "-json", "SPAudioDataType"],
        "backlight.txt": ["ioreg", "-w0", "-r", "-d", "1", "-c", "AppleARMBacklight"],   # -w0: no 80-column cut
        "battery_ioreg.plist": ["ioreg", "-arn", "AppleSmartBattery"],
    }
    for name, cmd in cmds.items():
        if shutil.which(cmd[0]) or os.path.exists(cmd[0]):
            (inv / name).write_text(run(cmd, timeout=120))
    user_agents = run(["launchctl", "list"], user=True)
    (inv / "launchctl_user.txt").write_text(user_agents)

    summary = {}
    summary["macos"] = " ".join(run(["sw_vers", "-productVersion"]).split()) + " (" + \
        " ".join(run(["sw_vers", "-buildVersion"]).split()) + ")"
    summary["model"] = run(["sysctl", "-n", "hw.model"]).strip()
    summary["chip"] = run(["sysctl", "-n", "machdep.cpu.brand_string"]).strip()
    summary["process_count"] = max(len((inv / "ps.txt").read_text().splitlines()) - 1, 0)
    # without root, launchctl list shows the user domain, so the system count is unknown
    summary["launchd_system_jobs"] = (max(len((inv / "launchctl_system.txt").read_text().splitlines()) - 1, 0)
                                      if os.geteuid() == 0 else None)
    summary["launchd_user_jobs"] = max(len(user_agents.splitlines()) - 1, 0)
    b = read_battery()
    if b.get("raw_max_mah") and b.get("design_mah"):
        summary["battery_health_pct"] = round(100 * b["raw_max_mah"] / b["design_mah"], 1)
    summary["battery_cycles"] = b.get("cycles")
    summary["on_battery"] = not b.get("external")
    summary["brightness"] = parse_brightness((inv / "backlight.txt").read_text() if (inv / "backlight.txt").exists() else "")
    summary["display"] = parse_display(inv / "displays.json")
    summary["pmset"] = parse_pmset((inv / "pmset_settings.txt").read_text())
    summary["sleep_history"] = sleep_drain((inv / "pmset_log.txt").read_text())
    summary["assertions"] = [l.strip() for l in (inv / "pmset_assertions.txt").read_text().splitlines()
                             if re.search(r"pid \d+", l)][:25]
    summary["bluetooth_on"] = _json_find(inv / "bluetooth.json", "controller_state")
    summary["wifi"] = _json_find(inv / "wifi.json", "spairport_current_network_information")
    (inv / "summary.json").write_text(json.dumps(summary, indent=2, default=str))
    return summary


def _json_find(path, key):
    try:
        obj = json.loads(Path(path).read_text())
    except Exception:  # noqa: BLE001
        return None
    stack = [obj]
    while stack:
        o = stack.pop()
        if isinstance(o, dict):
            for k, v in o.items():
                if key in k:
                    return v
                stack.append(v)
        elif isinstance(o, list):
            stack.extend(o)
    return None


def parse_brightness(text):
    """IODisplayParameters on AppleARMBacklight: slider position and, on newer macOS, the panel's nits."""
    def block(key):
        m = re.search(r'"%s"=\{([^}]*)\}' % key, text)
        return {k: int(v) for k, v in re.findall(r'"(\w+)"=(-?\d+)', m.group(1))} if m else None
    b = block("brightness")
    if not b or "value" not in b:
        return None
    mn, mx = b.get("min", 0), b.get("max", 65536)
    out = {"raw": b["value"], "min": mn, "max": mx, "pct": round(100 * (b["value"] - mn) / max(mx - mn, 1), 1)}
    nits = block("BrightnessMilliNits")
    if nits and "value" in nits:
        out["nits"] = round(nits["value"] / 1000, 1)      # match Linux by nits, not by slider percent
    return out


def parse_display(path):
    try:
        d = json.loads(Path(path).read_text())
        for gpu in d.get("SPDisplaysDataType", []):
            for disp in gpu.get("spdisplays_ndrvs", []):
                if "internal" in json.dumps(disp).lower():
                    return {k: v for k, v in disp.items()             # serial stays local (public repo)
                            if not isinstance(v, (dict, list)) and "serial" not in k}
    except Exception:  # noqa: BLE001
        pass
    return None


def parse_pmset(text):
    out, section = {}, None
    for line in text.splitlines():
        if line.strip().endswith(":") and "Power" in line:
            section = "battery" if "Battery" in line else "ac"
            out[section] = {}
        elif section and line.strip():
            parts = line.split()
            if len(parts) >= 2:
                out[section][parts[0]] = " ".join(parts[1:])
    return out


SLEEP_RE = re.compile(r"^(\d{4}-\d\d-\d\d \d\d:\d\d:\d\d [+-]\d{4})\s+(Sleep|Wake|DarkWake)\s+.*?\(Charge:\s*(\d+)%\)", re.I)


def sleep_drain(log):
    """Battery-only sleep periods from pmset's log: % per hour and DarkWakes per hour.

    A period runs from the first Sleep after a full wake to the next full Wake. In between macOS logs DarkWakes and
    'Back to Sleep' Sleep lines (maintenance, Power Nap); those count as the same period. If the charger is attached
    mid-sleep, the period ends at the last reading still on battery.
    """
    events = []
    for line in log.splitlines():
        m = SLEEP_RE.search(line)
        if not m:
            continue
        on_batt = bool(re.search(r"Using Batt", line, re.I))
        when = dt.datetime.strptime(m.group(1), "%Y-%m-%d %H:%M:%S %z")
        events.append((when, m.group(2).lower(), int(m.group(3)), on_batt))
    periods = []
    i = 0
    while i < len(events):
        w, kind, chg, batt = events[i]
        if kind != "sleep" or not batt:
            i += 1
            continue
        darkwakes, last, j = 0, events[i], i + 1
        while j < len(events) and events[j][1] != "wake" and events[j][3]:
            darkwakes += events[j][1] == "darkwake"
            last = events[j]
            j += 1
        end = events[j] if j < len(events) and events[j][1] == "wake" and events[j][3] else last
        hours = (end[0] - w).total_seconds() / 3600
        if hours >= 0.5:
            periods.append({"start": w.isoformat(), "hours": round(hours, 2), "pct_lost": chg - end[2],
                            "pct_per_hour": round((chg - end[2]) / hours, 3), "darkwakes": darkwakes,
                            "darkwakes_per_hour": round(darkwakes / hours, 2),
                            "ended": "wake" if end is not last else "charger or log end"})
        i = max(j, i + 1)
    rates = [p["pct_per_hour"] for p in periods]
    return {"periods": periods[-20:], "pct_per_hour": stats(rates),
            "darkwakes_per_hour": stats([p["darkwakes_per_hour"] for p in periods])}


# ---------------------------------------------------------------- run one scenario

def run_scenario(name, cfg, outdir: Path, samplers, args):
    print(f"\n=== {name}: {cfg['title']} ===\n{cfg['prep']}")
    video = video_file(cfg, args) if cfg.get("action") == "video_local" else None
    if cfg.get("action") == "video_local" and not video:
        print(f"  skipped: {cfg['video']} not in {args.video_dir} (run make_test_videos.sh)")
        return None
    if not args.yes:
        input("Press Enter to start (Ctrl-C to skip the rest)... ")
    settle = args.settle
    print(f"  settling {settle} s ...")
    time.sleep(settle)

    raw = outdir / "raw" / f"{name}.plist"
    raw.parent.mkdir(parents=True, exist_ok=True)
    seconds = cfg["seconds"] * args.scale
    if cfg.get("action") == "cpu_burst":
        seconds = max(seconds, 30)  # retain the 5 s lead-in, 20 s load and recovery even in quick runs
    count = max(1, math.ceil(seconds * 1000 / cfg["interval_ms"]))
    batt = BatterySampler(period=1.0 if cfg["interval_ms"] >= 1000 else 0.5)
    stop_evt = threading.Event()
    helper = pm = clip = None
    action = cfg.get("action")
    procs = []
    t0 = time.time()
    try:
        if action == "display_off":
            display_off()
            time.sleep(3)
        elif action == "web_loop":
            helper = threading.Thread(target=web_loop, args=(stop_evt,), daemon=True)
            helper.start()
        elif action == "video_local":
            clip = video_local(video)
            time.sleep(5)
        batt.start()
        pm = start_powermetrics(raw, cfg["interval_ms"], count, samplers)
        t0 = time.time()
        if action == "cpu_burst":
            time.sleep(5)
            burst_start = time.time()
            stop_at = burst_start + 20
            for _ in range(os.cpu_count() or 10):
                proc = mp.Process(target=_busy, args=(stop_at,))
                proc.start()
                procs.append(proc)
        while pm.poll() is None:
            el = int(time.time() - t0)
            print(f"\r  sampling {el:>4}/{int(seconds)} s", end="", flush=True)
            time.sleep(1)
    finally:
        stop_evt.set()
        try:
            cleanup_process(pm)
        finally:
            if batt.ident is not None:
                batt.stop()
            for proc in procs:
                if proc.is_alive():
                    proc.terminate()
                proc.join(timeout=5)
            if action == "display_off":
                display_on()
            if clip:
                video_stop(clip)
            if helper:
                helper.join(timeout=5)
    print()
    err = pm.stderr.read().decode(errors="replace") if pm and pm.stderr else ""
    if pm and pm.returncode:
        raise RuntimeError(f"powermetrics failed ({pm.returncode}): {err.strip()}")
    if err.strip():
        (outdir / "raw" / f"{name}.stderr.txt").write_text(err)
    (outdir / "raw" / f"{name}.battery.json").write_text(json.dumps(batt.samples))
    meta = {"name": name, "title": cfg["title"], "interval_ms": cfg["interval_ms"], "started": t0, "video": video}
    if action == "cpu_burst":
        meta["burst_offset_s"] = burst_start - t0
    (outdir / "raw" / f"{name}.meta.json").write_text(json.dumps(meta))
    return summarize_scenario(outdir, name)


def summarize_scenario(outdir: Path, name):
    raw = outdir / "raw" / f"{name}.plist"
    if not raw.exists():
        return None
    samples = parse_powermetrics(raw)
    meta_p = outdir / "raw" / f"{name}.meta.json"
    # Metadata is committed only after successful collection and cleanup. Do not score interrupted raw files.
    if not samples or not meta_p.exists():
        return None
    meta = json.loads(meta_p.read_text())
    batt_p = outdir / "raw" / f"{name}.battery.json"
    batt = json.loads(batt_p.read_text()) if batt_p.exists() else []
    rows = [flatten_sample(s) for s in samples]
    keys = sorted({k for r in rows for k, v in r.items() if isinstance(v, (int, float)) and k != "t_elapsed_ns"})
    metrics = {k: stats([r.get(k) for r in rows]) for k in keys}
    for k in ("system_load_w", "battery_flow_w", "battery_power_w", "system_power_in_w", "temp_c"):
        metrics[k] = stats([b.get(k) for b in batt])
    # what is outside the SoC rails: display, backlight, Wi-Fi, SSD, audio amps, PMIC losses
    if metrics.get("system_load_w") and metrics.get("soc_combined_w"):
        metrics["rest_of_machine_w"] = {"median": round(metrics["system_load_w"]["median"] -
                                                        metrics["soc_combined_w"]["median"], 3),
                                        "note": "system_load median minus SoC combined median"}
    if batt and len(batt) > 1 and batt[0].get("raw_charge_mah") and batt[-1].get("raw_charge_mah"):
        hrs = (batt[-1]["t"] - batt[0]["t"]) / 3600
        if hrs > 0:
            metrics["drain_mah_per_h"] = {"median": round((batt[0]["raw_charge_mah"] - batt[-1]["raw_charge_mah"]) / hrs, 1),
                                           "note": "first vs last raw charge; coarse over short runs"}
    out = {"name": name, "title": meta.get("title"), "samples": len(samples),
           "on_battery": bool(batt) and all(b.get("external") is False for b in batt),
           "metrics": {k: v for k, v in metrics.items() if v},
           "top_processes": task_table(samples)}
    if "burst_offset_s" in meta:
        out["burst"] = burst_analysis(rows, meta)
    return out


def burst_analysis(rows, meta):
    """Time from load start until CPU power reaches 90% of peak, and until it falls back near idle."""
    step = meta.get("interval_ms", 100) / 1000.0
    cpu = [r.get("cpu_w") or 0 for r in rows]
    if not cpu or not any(r.get("cpu_w") is not None for r in rows):
        return None
    start_i = int(meta["burst_offset_s"] / step)
    lead = cpu[:max(start_i, 1)]
    idle = statistics.median(lead) if lead else 0
    peak = max(cpu[start_i:] or [0])
    ramp_i = next((i for i in range(start_i, len(cpu)) if cpu[i] >= 0.9 * peak), None)
    end_i = start_i + int(20 / step)
    back_i = next((i for i in range(end_i, len(cpu)) if cpu[i] <= max(idle * 1.5, idle + 0.3)), None)
    pmhz = [r.get("p0_mhz") or r.get("p_mhz") or 0 for r in rows]
    return {"idle_cpu_w": round(idle, 3), "peak_cpu_w": round(peak, 3),
            "ramp_to_90pct_ms": round((ramp_i - start_i) * step * 1000) if ramp_i is not None else None,
            "back_to_idle_s": round((back_i - end_i) * step, 2) if back_i is not None else None,
            "peak_p_mhz": round(max(pmhz), 0) if pmhz else None,
            "note": f"sampled every {int(step * 1000)} ms, so ramp resolution is one sample"}


# ---------------------------------------------------------------- main

def write_summary(outdir: Path, inv, scen):
    doc = {"generated": dt.datetime.now().isoformat(timespec="seconds"), "host": platform.node(),
           "inventory": inv, "scenarios": scen}
    (outdir / "summary.json").write_text(json.dumps(doc, indent=2, default=str))
    print(f"\nWrote {outdir / 'summary.json'}")
    for name, s in scen.items():
        if not s:
            continue
        m = s["metrics"]
        def g(k):
            return f"{m[k]['median']:.2f}" if k in m and "median" in m[k] else "-"
        print(f"  {name:<18} system {g('system_load_w'):>6} W  SoC {g('soc_combined_w'):>6} W  "
              f"CPU {g('cpu_w'):>5}  GPU {g('gpu_w'):>5}  rest {g('rest_of_machine_w'):>6}  "
              f"wakeups/s {g('idle_wakeups_per_s')}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--only", help="comma-separated scenarios (default: all)")
    ap.add_argument("--video", help="1080p file for video_local (default: test-1080p-h264.mp4 in --video-dir)")
    ap.add_argument("--video-dir", default=default_video_dir(),
                    help="where make_test_videos.sh put test-{1080p,1440p,2160p}-h264.mp4 (default ~/Movies)")
    ap.add_argument("--settle", type=int, default=20, help="seconds to wait before each sample (default 20)")
    ap.add_argument("--scale", type=float, default=1.0, help="multiply every scenario length (0.2 for a quick try)")
    ap.add_argument("--yes", action="store_true", help="do not wait for Enter between scenarios")
    ap.add_argument("--inventory-only", action="store_true", help="only record what macOS is running and its settings")
    ap.add_argument("--resummarize", help="rebuild summary.json from an existing run directory")
    ap.add_argument("--list", action="store_true", help="list scenarios and exit")
    ap.add_argument("--any-mac", action="store_true", help="allow a Mac other than the 14-inch M1 Pro")
    args = ap.parse_args()
    order = validate_run_args(ap, args)

    if args.list:
        for k in DEFAULT_ORDER:
            print(f"{k:<18} {SCENARIOS[k]['title']}")
        return
    if args.resummarize:
        outdir = Path(args.resummarize)
        inv_p = outdir / "inventory" / "summary.json"
        inv = json.loads(inv_p.read_text()) if inv_p.exists() else {}
        scen = {p.stem: summarize_scenario(outdir, p.stem) for p in sorted((outdir / "raw").glob("*.plist"))}
        write_summary(outdir, inv, scen)
        return
    if platform.system() != "Darwin":
        sys.exit("Run this on macOS (it is the reference side). Use --resummarize to re-read a run elsewhere.")
    if os.geteuid() != 0 and not args.inventory_only:      # inventory and sleep history need no root
        sys.exit("powermetrics needs root: sudo python3 " + " ".join(sys.argv))

    signal.signal(signal.SIGTERM, stop_requested)
    model = run(["sysctl", "-n", "hw.model"]).strip()
    chip = run(["sysctl", "-n", "machdep.cpu.brand_string"]).strip()
    print(f"This Mac: {model}, {chip}")
    if model not in ("MacBookPro18,3", "MacBookPro18,4") and not args.any_mac:
        sys.exit("The Linux numbers are from the 14-inch M1 Pro (MacBookPro18,3/18,4). Run this on that machine, "
                 "booted into macOS, or pass --any-mac to record this Mac anyway (not comparable).")
    stamp = dt.datetime.now().strftime("%Y-%m-%d-%H%M%S-%f")
    outdir = RESULTS / f"macos-{stamp}"
    outdir.mkdir(parents=True, exist_ok=False)
    print(f"Output: {outdir}")
    b = read_battery()
    if b.get("external"):
        print("WARNING: the charger is connected. Unplug it: on AC, SystemLoad is not what the battery would see.")
    print("Recording what macOS is running and its power settings ...")
    inv = inventory(outdir)
    print(f"  macOS {inv.get('macos')}, {inv.get('process_count')} processes, "
          f"{inv.get('launchd_system_jobs')} system + {inv.get('launchd_user_jobs')} user launchd jobs, "
          f"brightness {inv.get('brightness')}")
    scen = {}
    write_summary(outdir, inv, scen)
    if not args.inventory_only:
        samplers = available_samplers()
        print(f"powermetrics samplers: {', '.join(samplers)}")
        try:
            for name in order:
                scen[name] = run_scenario(name, SCENARIOS[name], outdir, samplers, args)
                write_summary(outdir, inv, scen)          # keep partial results
        except KeyboardInterrupt:
            print("\nStopped; keeping the scenarios already done.")
    write_summary(outdir, inv, scen)
    user = os.environ.get("SUDO_USER")
    if user:
        run(["chown", "-R", user, str(outdir)])


if __name__ == "__main__":
    main()
