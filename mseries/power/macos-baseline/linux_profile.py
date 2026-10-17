#!/usr/bin/env python3
"""Linux side of the parity checklist: the same scenarios as macos_profile.py, same summary.json shape.

Run on the M1 Pro under elementary OS, on battery, at the brightness the macOS run recorded:

    python3 mseries/power/macos-baseline/linux_profile.py --video ~/Videos/test-1080p-h264.mp4
    python3 mseries/power/macos-baseline/linux_profile.py --only idle_minimal --scale 0.2     # quick try
    python3 mseries/power/macos-baseline/parity.py --linux-run results/linux-<stamp>/summary.json

No root needed. Read-only except what a scenario does (opening the browser, playing a file, a CPU burst).
It never changes brightness, refresh rate, display power, the audio stack or the kernel (AGENTS.md,
POWER-ROADMAP.md honesty rules). `idle_screen_off` asks the compositor to blank the panel only with --allow-blank.

Sources:
  whole machine   hwmon "Total System Power" (macsmc), else macsmc-battery power_now / current x voltage
  CPU             cpuidle state residency per cluster (WFI vs CPU PD), cpufreq, /proc/stat busy time
  wakeups         /proc/interrupts (all, and arch_timer), per-process CPU from /proc/<pid>/stat
  I/O             /proc/net/dev, /proc/diskstats
  battery         macsmc-battery charge, health, cycles, temperature
Median and p10/p90 per metric, like macos_profile.py and EFFICIENCY-GOALS.md.
"""
from __future__ import annotations

import argparse
import datetime as dt
import glob
import json
import multiprocessing as mp
import os
import platform
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from macos_profile import SCENARIOS, DEFAULT_ORDER, WEB_LOOP_URLS, stats, _busy  # noqa: E402

RESULTS = HERE / "results"
SYS = Path(os.environ.get("MSERIES_SYS", "/sys"))
PROC = Path(os.environ.get("MSERIES_PROC", "/proc"))
BAT = SYS / "class/power_supply/macsmc-battery"
CLK = os.sysconf("SC_CLK_TCK") if hasattr(os, "sysconf") else 100
COMPOSITOR = ("gala", "gnome-shell", "mutter", "kwin_wayland", "Xwayland")


def rd(path, default=None):
    try:
        return Path(path).read_text().strip()
    except Exception:  # noqa: BLE001
        return default


def num(path, default=None):
    v = rd(path)
    try:
        return int(v)
    except (TypeError, ValueError):
        try:
            return float(v)
        except (TypeError, ValueError):
            return default


def run(cmd, timeout=30):
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout).stdout
    except Exception as exc:  # noqa: BLE001
        return f"<error: {exc}>"


# ---------------------------------------------------------------- whole-machine power

def find_system_power():
    """hwmon input whose label is the SMC's whole-machine power, else None."""
    for lab in glob.glob(str(SYS / "class/hwmon/hwmon*/power*_label")):
        text = (rd(lab) or "").lower()
        if "total system" in text or text in ("system power", "system total"):
            return lab.replace("_label", "_input")
    return None


SYS_POWER = None


def read_power():
    out = {"t": time.time()}
    if SYS_POWER:
        v = num(SYS_POWER)
        out["system_load_w"] = v / 1e6 if v is not None else None      # hwmon power is in µW
    p = num(BAT / "power_now")
    if p is None:
        i, v = num(BAT / "current_now"), num(BAT / "voltage_now")
        p = abs(i * v) / 1e6 if i is not None and v is not None else None
    out["battery_flow_w"] = abs(p) / 1e6 if p is not None else None
    if out.get("system_load_w") is None:
        out["system_load_w"] = out["battery_flow_w"]
        out["system_load_source"] = "battery"
    out["charge_pct"] = num(BAT / "capacity")
    out["energy_uwh"] = num(BAT / "energy_now") or num(BAT / "charge_now")
    t = num(BAT / "temp")
    out["temp_c"] = t / 10 if t is not None else None
    out["external"] = (rd(BAT / "status") or "").lower() not in ("discharging",)
    return out


class PowerSampler(threading.Thread):
    def __init__(self, period=1.0):
        super().__init__(daemon=True)
        self.period, self.samples, self._halt = period, [], threading.Event()

    def run(self):
        while not self._halt.is_set():
            self.samples.append(read_power())
            self._halt.wait(self.period)

    def stop(self):
        self._halt.set()
        self.join(timeout=5)


# ---------------------------------------------------------------- counters (sampled each interval, deltas)

def clusters():
    """{'e': [0,1], 'p0': [2..5], 'p1': [6..9]} from cpufreq policies, slowest first."""
    pols = []
    for pol in sorted(glob.glob(str(SYS / "devices/system/cpu/cpufreq/policy*"))):
        cpus = [int(x) for x in (rd(Path(pol) / "related_cpus") or "").split()]
        pols.append((num(Path(pol) / "cpuinfo_max_freq", 0), pol, cpus))
    pols.sort(key=lambda x: (x[0], x[2][:1]))
    out, pi = {}, 0
    for mx, pol, cpus in pols:
        if mx == pols[0][0] and "e" not in out:
            out["e"] = (pol, cpus)
        else:
            out[f"p{pi}"] = (pol, cpus)
            pi += 1
    return out


def cpuidle_times(cpu):
    """(time in shallowest state, time in deeper states) in µs."""
    shallow = deep = 0
    for st in sorted(glob.glob(str(SYS / f"devices/system/cpu/cpu{cpu}/cpuidle/state*"))):
        t = num(Path(st) / "time", 0)
        if st.endswith("state0"):
            shallow += t
        else:
            deep += t
    return shallow, deep


def proc_stat():
    line = (rd(PROC / "stat") or "cpu 0").splitlines()[0].split()[1:]
    v = [int(x) for x in line]
    idle = v[3] + (v[4] if len(v) > 4 else 0)
    return sum(v) - idle


def interrupts():
    total, timer = 0, None
    for line in (rd(PROC / "interrupts") or "").splitlines()[1:]:
        parts = line.split()
        counts = []
        for p in parts[1:]:
            if p.isdigit():
                counts.append(int(p))
            else:
                break
        s = sum(counts)
        total += s
        if "arch_timer" in line:
            timer = (timer or 0) + s
    return total, timer


def per_process():
    out = {}
    for d in glob.glob(str(PROC / "[0-9]*")):
        st = rd(Path(d) / "stat")
        if not st:
            continue
        try:
            comm = st[st.index("(") + 1:st.rindex(")")]
            rest = st[st.rindex(")") + 2:].split()
            ticks = int(rest[11]) + int(rest[12])
        except Exception:  # noqa: BLE001
            continue
        out[(d.rsplit("/", 1)[1], comm)] = ticks
    return out


def net_bytes():
    rx = tx = 0
    for line in (rd(PROC / "net/dev") or "").splitlines()[2:]:
        name, data = line.split(":", 1)
        if name.strip() == "lo":
            continue
        f = data.split()
        rx, tx = rx + int(f[0]), tx + int(f[8])
    return rx, tx


def disk_bytes():
    r = w = 0
    for line in (rd(PROC / "diskstats") or "").splitlines():
        f = line.split()
        if len(f) > 9 and (f[2].startswith("nvme") and "p" not in f[2][4:] or f[2].startswith("sd") and f[2][-1].isalpha()):
            r, w = r + int(f[5]) * 512, w + int(f[9]) * 512
    return r, w


def snapshot(cl):
    s = {"t": time.monotonic(), "busy": proc_stat(), "intr": interrupts(), "net": net_bytes(), "disk": disk_bytes(),
         "idle": {name: [cpuidle_times(c) for c in cpus] for name, (_, cpus) in cl.items()},
         "freq": {name: num(Path(pol) / "scaling_cur_freq") for name, (pol, _) in cl.items()}}
    return s


def delta_row(a, b, cl):
    dt_s = max(b["t"] - a["t"], 1e-6)
    row = {"cpu_ms_per_s_all": (b["busy"] - a["busy"]) * 1000 / CLK / dt_s,
           "intr_wakeups_per_s": (b["intr"][0] - a["intr"][0]) / dt_s,
           # arch_timer ticks are the closest analogue to macOS idle wakeups; absent counter = unmeasured, not 0
           "idle_wakeups_per_s": (b["intr"][1] - a["intr"][1]) / dt_s if a["intr"][1] is not None else None,
           "net_in_Bps": (b["net"][0] - a["net"][0]) / dt_s, "net_out_Bps": (b["net"][1] - a["net"][1]) / dt_s,
           "disk_read_Bps": (b["disk"][0] - a["disk"][0]) / dt_s,
           "disk_write_Bps": (b["disk"][1] - a["disk"][1]) / dt_s}
    for name in cl:
        sh = sum(y[0] - x[0] for x, y in zip(a["idle"][name], b["idle"][name]))
        dp = sum(y[1] - x[1] for x, y in zip(a["idle"][name], b["idle"][name]))
        ncpu = len(cl[name][1]) or 1
        if sh + dp > 0:
            row[f"{name}_deep_idle_share_pct"] = 100 * dp / (sh + dp)
        row[f"{name}_active_pct"] = max(0.0, 100 - 100 * (sh + dp) / 1e6 / dt_s / ncpu)
        if b["freq"].get(name):
            row[f"{name}_mhz"] = b["freq"][name] / 1000
    return row


# ---------------------------------------------------------------- inventory

def inventory(outdir: Path):
    inv = outdir / "inventory"
    inv.mkdir(parents=True, exist_ok=True)
    cmds = {"uname.txt": ["uname", "-a"], "os-release.txt": ["cat", "/etc/os-release"],
            "ps.txt": ["ps", "-eo", "pid,ppid,user,%cpu,rss,etime,comm"],
            "systemd_running.txt": ["systemctl", "list-units", "--type=service", "--state=running", "--no-legend"],
            "systemd_user_running.txt": ["systemctl", "--user", "list-units", "--type=service", "--state=running",
                                         "--no-legend"],
            "power_profile.txt": ["powerprofilesctl", "get"], "mseries_power.txt": ["mseries-power", "status"],
            "inhibitors.txt": ["systemd-inhibit", "--list", "--no-pager"],
            "rfkill.txt": ["rfkill", "list"], "lsusb.txt": ["lsusb"],
            "asound_pcm_status.txt": ["sh", "-c", "grep -H . /proc/asound/card*/pcm*/sub0/status 2>/dev/null"],
            "wakeup_sources.txt": ["cat", "/sys/kernel/debug/wakeup_sources"],
            "suspend_journal.txt": ["journalctl", "-b", "-1", "-u", "systemd-suspend", "--no-pager", "-o", "short-iso"]}
    for name, cmd in cmds.items():
        if shutil.which(cmd[0]):
            (inv / name).write_text(run(cmd, timeout=60))
    count = lambda n: max(len((inv / n).read_text().splitlines()) - (1 if n == "ps.txt" else 0), 0) \
        if (inv / n).exists() else None  # noqa: E731
    full, design = num(BAT / "energy_full") or num(BAT / "charge_full"), \
        num(BAT / "energy_full_design") or num(BAT / "charge_full_design")
    bl = sorted(glob.glob(str(SYS / "class/backlight/*")))
    bright = None
    if bl:
        v, mx = num(Path(bl[0]) / "brightness"), num(Path(bl[0]) / "max_brightness")
        if v is not None and mx:
            bright = {"raw": v, "max": mx, "pct": round(100 * v / mx, 1), "device": Path(bl[0]).name}
    pcm = (inv / "asound_pcm_status.txt").read_text() if (inv / "asound_pcm_status.txt").exists() else ""
    summary = {
        "os": (rd("/etc/os-release") or "").split("PRETTY_NAME=")[-1].split("\n")[0].strip('"') or platform.platform(),
        "kernel": platform.release(),
        "model": rd("/proc/device-tree/model", "").replace("\x00", ""),
        "process_count": count("ps.txt"),
        "systemd_running_services": count("systemd_running.txt"),
        "systemd_user_running_services": count("systemd_user_running.txt"),
        "power_profile": (rd(inv / "power_profile.txt") or "").strip() or None,
        "battery_health_pct": round(100 * full / design, 1) if full and design else None,
        "battery_cycles": num(BAT / "cycle_count"),
        "charge_limit": num(BAT / "charge_control_end_threshold"),
        "on_battery": (rd(BAT / "status") or "").lower() == "discharging",
        "brightness": bright,
        "mem_sleep": rd(SYS / "power/mem_sleep"),
        "speaker_pcm_running": "state: RUNNING" in pcm,
        "system_power_source": SYS_POWER or "battery power_now",
    }
    (inv / "summary.json").write_text(json.dumps(summary, indent=2))
    return summary


# ---------------------------------------------------------------- scenarios

def blank(on):
    """Mutter DisplayConfig PowerSaveMode: 0 on, 3 off. Only with --allow-blank (display power is owner-gated)."""
    run(["gdbus", "call", "--session", "--dest", "org.gnome.Mutter.DisplayConfig", "--object-path",
         "/org/gnome/Mutter/DisplayConfig", "--method", "org.freedesktop.DBus.Properties.Set",
         "org.gnome.Mutter.DisplayConfig", "PowerSaveMode", f"<{0 if on else 3}>"])


def web_loop(stop_evt, browser):
    i = 0
    while not stop_evt.is_set():
        subprocess.Popen([browser, WEB_LOOP_URLS[i % len(WEB_LOOP_URLS)]],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        i += 1
        stop_evt.wait(15)


def run_scenario(name, cfg, outdir: Path, cl, args):
    print(f"\n=== {name}: {cfg['title']} ===")
    prep = cfg["prep"].replace("Safari", args.browser).replace("QuickTime", "mpv (--hwdec=vaapi)")
    print(prep)
    action = cfg.get("action")
    if action == "video_local" and not args.video:
        print("  skipped: no --video file given")
        return None
    if action == "display_off" and not args.allow_blank:
        print("  skipped: blanking the panel is a display-power change; rerun with --allow-blank if the owner agrees")
        return None
    if not args.yes:
        input("Press Enter to start (Ctrl-C to stop) ... ")
    print(f"  settling {args.settle} s ...")
    time.sleep(args.settle)

    step = cfg["interval_ms"] / 1000.0
    seconds = cfg["seconds"] * args.scale
    stop_evt, helper, player, procs = threading.Event(), None, None, []
    if action == "display_off":
        blank(False)
        time.sleep(3)
    elif action == "web_loop":
        helper = threading.Thread(target=web_loop, args=(stop_evt, args.browser), daemon=True)
        helper.start()
    elif action == "video_local":
        player = subprocess.Popen(["mpv", "--hwdec=vaapi", "--loop=inf", "--really-quiet", args.video])
        time.sleep(5)

    pw = PowerSampler(period=min(1.0, max(step, 0.2)))
    pw.start()
    t0 = time.monotonic()
    procs_before = per_process()
    rows, prev = [], snapshot(cl)
    burst_offset = None
    while time.monotonic() - t0 < seconds:
        el = time.monotonic() - t0
        if action == "cpu_burst" and burst_offset is None and el >= 5:
            burst_offset = el
            stop_at = time.time() + 20
            procs = [mp.Process(target=_busy, args=(stop_at,)) for _ in range(os.cpu_count() or 10)]
            for p in procs:
                p.start()
        time.sleep(step)
        cur = snapshot(cl)
        r = delta_row(prev, cur, cl)
        r["cpu_w"] = None                                   # rails not read on Linux yet (C1, G1)
        rows.append(r)
        prev = cur
        print(f"\r  sampling {int(el):>4}/{int(seconds)} s", end="", flush=True)
    print()
    procs_after = per_process()
    elapsed = time.monotonic() - t0
    for p in procs:
        p.join()
    stop_evt.set()
    pw.stop()
    if action == "display_off":
        blank(True)
    if player:
        player.terminate()

    raw = outdir / "raw"
    raw.mkdir(parents=True, exist_ok=True)
    (raw / f"{name}.rows.json").write_text(json.dumps(rows))
    (raw / f"{name}.power.json").write_text(json.dumps(pw.samples))
    top = {}
    for key, ticks in procs_after.items():
        d = ticks - procs_before.get(key, ticks)
        if d > 0:
            top[key[1]] = top.get(key[1], 0) + d
    tops = sorted(({"process": k, "cpu_ms_per_s": round(v * 1000 / CLK / elapsed, 2)} for k, v in top.items()),
                  key=lambda r: r["cpu_ms_per_s"], reverse=True)[:15]
    meta = {"name": name, "title": cfg["title"], "interval_ms": cfg["interval_ms"], "top_processes": tops}
    if burst_offset is not None:
        meta["burst_offset_s"] = burst_offset
    (raw / f"{name}.meta.json").write_text(json.dumps(meta))
    return summarize(outdir, name)


def summarize(outdir: Path, name):
    raw = outdir / "raw"
    if not (raw / f"{name}.rows.json").exists():
        return None
    rows = json.loads((raw / f"{name}.rows.json").read_text())
    pw = json.loads((raw / f"{name}.power.json").read_text())
    meta = json.loads((raw / f"{name}.meta.json").read_text())
    keys = sorted({k for r in rows for k, v in r.items() if isinstance(v, (int, float))})
    m = {k: stats([r.get(k) for r in rows]) for k in keys}
    for k in ("system_load_w", "battery_flow_w", "temp_c"):
        m[k] = stats([p.get(k) for p in pw])
    if len(pw) > 1 and pw[0].get("energy_uwh") and pw[-1].get("energy_uwh"):
        hrs = (pw[-1]["t"] - pw[0]["t"]) / 3600
        if hrs > 0:
            m["drain_w_from_energy"] = {"median": round((pw[0]["energy_uwh"] - pw[-1]["energy_uwh"]) / 1e6 / hrs, 2),
                                        "note": "energy_now first vs last; coarse over short runs"}
    out = {"name": name, "title": meta.get("title"), "samples": len(rows),
           "on_battery": bool(pw) and not any(p.get("external") for p in pw),
           "system_load_source": "battery" if any(p.get("system_load_source") for p in pw) else "smc",
           "metrics": {k: v for k, v in m.items() if v}, "top_processes": meta.get("top_processes", [])}
    comp = [r for r in out["top_processes"] if r["process"] in COMPOSITOR]
    if comp:
        out["compositor"] = comp[0]
    if "burst_offset_s" in meta:
        out["burst"] = burst(rows, pw, meta)
    return out


def burst(rows, pw, meta):
    """Ramp from P-cluster clock (CPU rail is not readable yet); back-to-idle from whole-machine power."""
    step = meta["interval_ms"] / 1000.0
    start = int(meta["burst_offset_s"] / step)
    pm = [r.get("p0_mhz") or 0 for r in rows]
    peak = max(pm[start:] or [0])
    if not peak:
        return {"note": "scaling_cur_freq not readable; no ramp measured"}
    ramp = next((i for i in range(start, len(pm)) if pm[i] >= 0.9 * peak), None)
    end = start + int(20 / step)
    act = [r.get("p0_active_pct") or 0 for r in rows]
    idle = sorted(act[:max(start, 1)])[len(act[:max(start, 1)]) // 2] if start else 0
    back = next((i for i in range(end, len(act)) if act[i] <= idle + 5), None)
    return {"ramp_to_90pct_ms": round((ramp - start) * step * 1000) if ramp is not None else None,
            "back_to_idle_s": round((back - end) * step, 2) if back is not None else None,
            "peak_p_mhz": round(peak), "note": "ramp from P-cluster clock, back-to-idle from P-cluster activity"}


def write_summary(outdir, inv, scen):
    doc = {"generated": dt.datetime.now().isoformat(timespec="seconds"), "host": platform.node(), "side": "linux",
           "inventory": inv, "scenarios": scen}
    (outdir / "summary.json").write_text(json.dumps(doc, indent=2, default=str))
    print(f"\nWrote {outdir / 'summary.json'}")
    for name, s in scen.items():
        if s:
            mm = s["metrics"]
            g = lambda k: f"{mm[k]['median']:.2f}" if k in mm else "-"  # noqa: E731
            print(f"  {name:<16} system {g('system_load_w'):>6} W  CPU busy {g('cpu_ms_per_s_all'):>7} ms/s  "
                  f"timer {g('idle_wakeups_per_s'):>7}/s  E deep {g('e_deep_idle_share_pct')}%")


def main():
    global SYS_POWER
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--only")
    ap.add_argument("--video", help="the same 1080p H.264 file used on macOS")
    ap.add_argument("--browser", default="xdg-open", help="browser command for web_loop (default xdg-open)")
    ap.add_argument("--settle", type=int, default=20)
    ap.add_argument("--scale", type=float, default=1.0)
    ap.add_argument("--yes", action="store_true")
    ap.add_argument("--allow-blank", action="store_true", help="let idle_screen_off blank the panel (owner-gated)")
    ap.add_argument("--inventory-only", action="store_true")
    ap.add_argument("--resummarize")
    args = ap.parse_args()

    SYS_POWER = find_system_power()
    if args.resummarize:
        outdir = Path(args.resummarize)
        inv = json.loads((outdir / "inventory/summary.json").read_text()) if (outdir / "inventory/summary.json").exists() else {}
        scen = {p.name.split(".")[0]: summarize(outdir, p.name.split(".")[0]) for p in sorted((outdir / "raw").glob("*.rows.json"))}
        write_summary(outdir, inv, scen)
        return
    if platform.system() != "Linux":
        sys.exit("Run this on elementary OS on the M1 Pro; macos_profile.py is the macOS side.")
    outdir = RESULTS / f"linux-{dt.datetime.now().strftime('%Y-%m-%d-%H%M')}"
    outdir.mkdir(parents=True, exist_ok=True)
    print(f"Output: {outdir}\nWhole-machine power from: {SYS_POWER or 'battery power_now (SMC sensor not found)'}")
    if not (rd(BAT / "status") or "").lower() == "discharging":
        print("WARNING: not discharging. Unplug the charger for comparable numbers.")
    inv = inventory(outdir)
    print(f"  {inv['os']} {inv['kernel']}, {inv['process_count']} processes, {inv['systemd_running_services']} running "
          f"services, brightness {inv['brightness']}, profile {inv['power_profile']}")
    scen = {}
    if not args.inventory_only:
        cl = clusters()
        print("clusters: " + ", ".join(f"{k}={v[1]}" for k, v in cl.items()))
        order = args.only.split(",") if args.only else DEFAULT_ORDER
        try:
            for name in order:
                scen[name] = run_scenario(name, SCENARIOS[name], outdir, cl, args)
                write_summary(outdir, inv, scen)
        except KeyboardInterrupt:
            print("\nStopped; keeping the scenarios already done.")
    write_summary(outdir, inv, scen)


if __name__ == "__main__":
    main()
