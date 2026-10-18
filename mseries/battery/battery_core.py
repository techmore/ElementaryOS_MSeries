"""Shared battery history code: sampling, SQLite storage, sessions, power events and runtime estimates.

Used by the logger service, the `mseries-battery` command and the Battery app. Everything here is plain
sysfs/procfs plus sqlite3, so it works on any Linux laptop; the Apple SMC hwmon "Total System Power" sensor
is used when it exists and the battery's own flow is the fallback.
"""
import glob
import json
import os
import sqlite3
import time

DB_PATH = os.path.join(os.environ.get("XDG_DATA_HOME", os.path.expanduser("~/.local/share")),
                       "mseries-battery", "history.db")
SAMPLE_SECONDS = 15
GAP_SECONDS = SAMPLE_SECONDS * 3      # a longer silence means suspend, shutdown or a crash
SESSION_GAP_SECONDS = 300             # discharge runs split when samples are further apart than this
RETENTION_DAYS = 90
EVENT_STEP_WATTS = 4.0                # system power change that is worth an event
EVENT_MIN_GAP_SECONDS = 60            # at most one event per minute

SCHEMA = """
CREATE TABLE IF NOT EXISTS samples (
    ts INTEGER PRIMARY KEY, status TEXT, ac INTEGER, pct REAL, energy_uwh INTEGER, full_uwh INTEGER,
    batt_w REAL, sys_w REAL, cpu_pct REAL, cpu_mhz REAL, load1 REAL, temp_c REAL, bright_pct REAL, top TEXT);
CREATE TABLE IF NOT EXISTS events (
    ts INTEGER, kind TEXT, delta_w REAL, before_w REAL, after_w REAL, cpu_pct REAL, culprit TEXT, detail TEXT);
CREATE INDEX IF NOT EXISTS events_ts ON events(ts);
"""


def rd(path, default=None):
    try:
        with open(path) as handle:
            return handle.read().strip()
    except OSError:
        return default


def rd_num(path, scale=1.0):
    value = rd(path)
    try:
        return float(value) * scale
    except (TypeError, ValueError):
        return None


def find_battery():
    """The laptop's own battery, not a mouse or keyboard (those report scope=Device)."""
    for node in sorted(glob.glob("/sys/class/power_supply/*")):
        if rd(node + "/type") == "Battery" and rd(node + "/scope", "System") != "Device":
            return node
    return None


def find_system_power():
    for label in glob.glob("/sys/class/hwmon/hwmon*/power*_label"):
        if (rd(label) or "").lower() == "total system power":
            return label.replace("_label", "_input")
    return None


def find_ac():
    for node in sorted(glob.glob("/sys/class/power_supply/*")):
        if rd(node + "/type") == "Mains":
            return node + "/online"
    return None


def connect(path=DB_PATH, readonly=False):
    if readonly:
        conn = sqlite3.connect("file:%s?mode=ro" % path, uri=True, timeout=10)
    else:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        conn = sqlite3.connect(path, timeout=10)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.executescript(SCHEMA)
    conn.row_factory = sqlite3.Row
    return conn


class Sampler:
    """Reads one snapshot of power, CPU and process state; keeps the previous counters for deltas."""

    def __init__(self, proc="/proc"):
        self.proc = proc
        self.battery = find_battery()
        self.sys_power = find_system_power()
        self.ac = find_ac()
        self.backlight = (glob.glob("/sys/class/backlight/*") or [None])[0]
        self.prev_cpu = None
        self.prev_procs = {}
        self.prev_time = None

    def cpu_times(self):
        fields = (rd(self.proc + "/stat") or "cpu 0 0 0 0").splitlines()[0].split()[1:]
        values = [int(v) for v in fields[:8]]
        idle = values[3] + values[4]
        return sum(values), idle

    def proc_ticks(self):
        ticks = {}
        for entry in os.listdir(self.proc):
            if not entry.isdigit():
                continue
            stat = rd("%s/%s/stat" % (self.proc, entry))
            if not stat:
                continue
            # comm may contain spaces and parentheses, so split on the last ')'
            head, _, tail = stat.rpartition(")")
            parts = tail.split()
            if len(parts) < 13:
                continue
            name = head.partition("(")[2]
            ticks[entry] = (name, int(parts[11]) + int(parts[12]))
        return ticks

    def cpu_mhz(self):
        freqs = [rd_num(p, 0.001) for p in glob.glob("/sys/devices/system/cpu/cpu[0-9]*/cpufreq/scaling_cur_freq")]
        freqs = [f for f in freqs if f]
        return sum(freqs) / len(freqs) if freqs else None

    def sample(self):
        now = int(time.time())
        total, idle = self.cpu_times()
        procs = self.proc_ticks()
        cpu_pct, top = None, []
        if self.prev_cpu:
            dt, di = total - self.prev_cpu[0], idle - self.prev_cpu[1]
            if dt > 0:
                cpu_pct = round(100.0 * (dt - di) / dt, 1)
                grouped = {}
                for pid, (name, used) in procs.items():
                    before = self.prev_procs.get(pid)
                    if before and before[0] == name and used >= before[1]:
                        grouped[name] = grouped.get(name, 0) + used - before[1]
                # process ticks are in the same units as /proc/stat, summed over all CPUs
                ranked = sorted(grouped.items(), key=lambda kv: -kv[1])[:3]
                top = [[name, round(100.0 * ticks / dt, 1)] for name, ticks in ranked if ticks > 0]
        self.prev_cpu, self.prev_procs = (total, idle), procs

        bat = self.battery
        status = (rd(bat + "/status") if bat else None) or "Unknown"
        ac_online = rd(self.ac) if self.ac else None
        ac = int(ac_online) if ac_online in ("0", "1") else (0 if status == "Discharging" else 1)
        energy = rd_num(bat + "/energy_now") if bat else None
        full = rd_num(bat + "/energy_full") if bat else None
        pct = rd_num(bat + "/capacity") if bat else None
        if energy is not None and full:
            pct = round(100.0 * energy / full, 2)
        power = rd_num(bat + "/power_now", 1e-6) if bat else None
        if power is None and bat:
            volts, amps = rd_num(bat + "/voltage_now", 1e-6), rd_num(bat + "/current_now", 1e-6)
            power = abs(volts * amps) if volts and amps else None
        batt_w = None
        if power is not None:
            power = abs(power)
            batt_w = -power if status == "Discharging" else (power if status == "Charging" else 0.0)
        sys_w = rd_num(self.sys_power, 1e-6) if self.sys_power else None
        if sys_w is None and batt_w is not None and status == "Discharging":
            sys_w = -batt_w
        temp = rd_num(bat + "/temp", 0.1) if bat else None
        bright = None
        if self.backlight:
            cur, top_b = rd_num(self.backlight + "/brightness"), rd_num(self.backlight + "/max_brightness")
            bright = round(100.0 * cur / top_b, 1) if cur is not None and top_b else None
        load = rd(self.proc + "/loadavg")
        return {"ts": now, "status": status, "ac": ac, "pct": pct,
                "energy_uwh": int(energy) if energy is not None else None,
                "full_uwh": int(full) if full is not None else None,
                "batt_w": batt_w, "sys_w": sys_w, "cpu_pct": cpu_pct, "cpu_mhz": self.cpu_mhz(),
                "load1": float(load.split()[0]) if load else None, "temp_c": temp, "bright_pct": bright,
                "top": json.dumps(top)}


COLUMNS = ["ts", "status", "ac", "pct", "energy_uwh", "full_uwh", "batt_w", "sys_w", "cpu_pct", "cpu_mhz",
           "load1", "temp_c", "bright_pct", "top"]


def store(conn, row):
    conn.execute("INSERT OR REPLACE INTO samples (%s) VALUES (%s)" % (",".join(COLUMNS), ",".join("?" * len(COLUMNS))),
                 [row[c] for c in COLUMNS])


def add_event(conn, ts, kind, delta_w=None, before_w=None, after_w=None, cpu_pct=None, culprit=None, detail=None):
    conn.execute("INSERT INTO events VALUES (?,?,?,?,?,?,?,?)",
                 (ts, kind, delta_w, before_w, after_w, cpu_pct, culprit, detail))


def explain_change(prev, row):
    """Best guess at why system power moved, from what else changed between the two samples."""
    if prev["ac"] != row["ac"]:
        return "Charger " + ("connected" if row["ac"] else "unplugged")
    if prev["bright_pct"] is not None and row["bright_pct"] is not None and abs(row["bright_pct"] - prev["bright_pct"]) >= 10:
        return "Screen brightness %d%% → %d%%" % (prev["bright_pct"], row["bright_pct"])
    cpu_a, cpu_b = prev["cpu_pct"], row["cpu_pct"]
    if cpu_a is not None and cpu_b is not None and abs(cpu_b - cpu_a) >= 15:
        return "CPU load %d%% → %d%%" % (cpu_a, cpu_b)
    return "Other (GPU, display, radios, charging)"


class EventDetector:
    """Watches system power for steps and for suspend gaps."""

    def __init__(self):
        self.recent = []
        self.last_row = None
        self.last_event = 0

    def feed(self, conn, row):
        prev = self.last_row
        if prev and row["ts"] - prev["ts"] > GAP_SECONDS:
            lost = (prev["pct"] or 0) - (row["pct"] or 0)
            add_event(conn, prev["ts"], "gap", detail=json.dumps({
                "seconds": row["ts"] - prev["ts"], "pct_from": prev["pct"], "pct_to": row["pct"],
                "on_battery": not row["ac"]}))
            self.recent = []
        watts = row["sys_w"]
        if prev and watts is not None and len(self.recent) >= 3 and row["ts"] - prev["ts"] <= GAP_SECONDS:
            baseline = sum(self.recent[-3:]) / 3
            delta = watts - baseline
            if abs(delta) >= EVENT_STEP_WATTS and row["ts"] - self.last_event >= EVENT_MIN_GAP_SECONDS:
                top = json.loads(row["top"] or "[]")
                add_event(conn, row["ts"], "rise" if delta > 0 else "drop", round(delta, 2), round(baseline, 2),
                          round(watts, 2), row["cpu_pct"], top[0][0] if top else None, explain_change(prev, row))
                self.last_event = row["ts"]
        if watts is not None:
            self.recent = (self.recent + [watts])[-6:]
        self.last_row = row


def prune(conn, days=RETENTION_DAYS):
    cutoff = int(time.time()) - days * 86400
    conn.execute("DELETE FROM samples WHERE ts < ?", (cutoff,))
    conn.execute("DELETE FROM events WHERE ts < ?", (cutoff,))
    conn.commit()


def fetch(conn, since, until=None):
    until = until or int(time.time()) + 1
    return [dict(r) for r in conn.execute("SELECT * FROM samples WHERE ts >= ? AND ts <= ? ORDER BY ts", (since, until))]


def sessions(rows):
    """Unplugged runs: consecutive discharging samples, split by gaps (suspend) and by plugging in."""
    result, current = [], []

    def close():
        if len(current) >= 2:
            first, last = current[0], current[-1]
            span = last["ts"] - first["ts"]
            used = ((first["energy_uwh"] or 0) - (last["energy_uwh"] or 0)) / 1e6
            watts = [r["sys_w"] for r in current if r["sys_w"] is not None]
            cpu = [r["cpu_pct"] for r in current if r["cpu_pct"] is not None]
            full_wh = (last["full_uwh"] or 0) / 1e6
            avg_w = used * 3600 / span if span > 0 and used > 0 else (sum(watts) / len(watts) if watts else None)
            result.append({
                "start": first["ts"], "end": last["ts"], "seconds": span,
                "pct_start": first["pct"], "pct_end": last["pct"], "wh_used": round(used, 2),
                "avg_w": round(avg_w, 2) if avg_w else None,
                "avg_cpu": round(sum(cpu) / len(cpu), 1) if cpu else None,
                "projected_hours": round(full_wh / avg_w, 1) if avg_w and full_wh else None})
        current.clear()

    for row in rows:
        if row["ac"] or row["status"] not in ("Discharging",):
            close()
            continue
        if current and row["ts"] - current[-1]["ts"] > SESSION_GAP_SECONDS:
            close()
        current.append(row)
    close()
    return result


USAGE_BANDS = [("Idle", 0, 10), ("Light", 10, 30), ("Moderate", 30, 60), ("Heavy", 60, 101)]


def usage_profile(rows):
    """Average draw while unplugged by CPU load band, and what that means for runtime at full charge."""
    out = []
    full_wh = next((r["full_uwh"] / 1e6 for r in reversed(rows) if r["full_uwh"]), None)
    discharging = [r for r in rows if not r["ac"] and r["sys_w"] is not None and r["cpu_pct"] is not None]
    for name, low, high in USAGE_BANDS:
        sel = [r for r in discharging if low <= r["cpu_pct"] < high]
        if not sel:
            out.append({"band": name, "cpu_range": "%d–%d%%" % (low, min(high, 100)), "samples": 0,
                        "hours": 0.0, "avg_w": None, "runtime_h": None})
            continue
        avg = sum(r["sys_w"] for r in sel) / len(sel)
        out.append({"band": name, "cpu_range": "%d–%d%%" % (low, min(high, 100)), "samples": len(sel),
                    "hours": round(len(sel) * SAMPLE_SECONDS / 3600, 2), "avg_w": round(avg, 2),
                    "runtime_h": round(full_wh / avg, 1) if full_wh and avg > 0 else None})
    return out


def top_culprits(rows, limit=5):
    """Processes that used the most CPU while unplugged, as share of unplugged time."""
    totals, samples = {}, 0
    for r in rows:
        if r["ac"]:
            continue
        samples += 1
        for name, cpu in json.loads(r["top"] or "[]"):
            totals[name] = totals.get(name, 0) + cpu
    if not samples:
        return []
    ranked = sorted(totals.items(), key=lambda kv: -kv[1])[:limit]
    return [{"name": n, "avg_cpu": round(v / samples, 1)} for n, v in ranked]


def estimate_runtime(rows, window_seconds=3600):
    """Hours left at the recent draw, and hours from full at the same draw. None while plugged in."""
    if not rows:
        return {}
    last = rows[-1]
    recent = [r for r in rows if r["ts"] >= last["ts"] - window_seconds and r["sys_w"] is not None and not r["ac"]]
    if not recent or last["ac"]:
        return {}
    avg = sum(r["sys_w"] for r in recent) / len(recent)
    if avg <= 0:
        return {}
    left = (last["energy_uwh"] or 0) / 1e6 / avg
    full = (last["full_uwh"] or 0) / 1e6 / avg
    return {"avg_w": round(avg, 2), "hours_left": round(left, 2), "hours_full": round(full, 2)}


def battery_health():
    bat = find_battery()
    if not bat:
        return {}
    full, design = rd_num(bat + "/energy_full"), rd_num(bat + "/energy_full_design")
    return {"full_wh": full / 1e6 if full else None, "design_wh": design / 1e6 if design else None,
            "health_pct": round(100.0 * full / design, 1) if full and design else None,
            "cycles": rd_num(bat + "/cycle_count"), "model": rd(bat + "/model_name"),
            "limit_pct": rd_num(bat + "/charge_control_end_threshold"),
            "temp_c": rd_num(bat + "/temp", 0.1)}


def events(conn, since, limit=200):
    return [dict(r) for r in conn.execute("SELECT * FROM events WHERE ts >= ? ORDER BY ts DESC LIMIT ?", (since, limit))]


def fmt_hours(hours):
    if hours is None:
        return "—"
    minutes = int(round(hours * 60))
    return "%dh %02dm" % (minutes // 60, minutes % 60) if minutes >= 60 else "%d min" % minutes
