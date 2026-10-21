#!/usr/bin/python3
"""Shared power and activity sensors for MacBook (Apple SMC) laptops running elementary OS.

One place to find the SMC "Total System Power" rail, battery flow, AC state and the per-process and
interrupt counters that power benchmarks need. Every reader takes a `root` so tests can point it at a
fixture tree. Nothing here writes to sysfs or keeps a thread running.

Total System Power is whole-machine draw on AC and on battery. Battery `power_now` is only the flow in
or out of the battery (zero or negative while charging), so it is a fallback for when the SMC rail is
missing, and only while discharging.
"""
import math
import os
import time
from pathlib import Path

SYSTEM_POWER_LABEL = 'total system power'


def read(path, default=''):
    try:
        return Path(path).read_text().strip()
    except OSError:
        return default


def number(path):
    try:
        value = float(read(path))
    except ValueError:
        return None
    return value if math.isfinite(value) else None


def find_system_power(root='/'):
    """Path of the SMC Total System Power input (microwatts), or None. Found by label, never by hwmonN."""
    candidates = []
    for label in sorted(Path(root, 'sys/class/hwmon').glob('hwmon*/power*_label')):
        if read(label).lower() == SYSTEM_POWER_LABEL:
            preferred = read(label.parent / 'name') == 'macsmc_hwmon'
            candidates.append((not preferred, label.with_name(label.name.replace('_label', '_input'))))
    return sorted(candidates)[0][1] if candidates else None


def find_battery(root='/'):
    for supply in sorted(Path(root, 'sys/class/power_supply').glob('*')):
        if read(supply / 'type') == 'Battery' and read(supply / 'scope') != 'Device':
            return supply
    return None


def on_ac(root='/'):
    """True/False when a Mains supply exists, else None."""
    mains = [s for s in sorted(Path(root, 'sys/class/power_supply').glob('*')) if read(s / 'type') == 'Mains']
    if not mains:
        return None
    return any(read(s / 'online') == '1' for s in mains)


def battery_flow_watts(root='/'):
    """Signed battery flow in watts (negative = discharging, as macsmc reports it), or None."""
    battery = find_battery(root)
    if battery is None:
        return None
    value = number(battery / 'power_now')
    return None if value is None else value / 1e6


class PowerSource:
    """Reads whole-system watts: the SMC rail when present, else battery flow while discharging."""

    def __init__(self, root='/'):
        self.root = root
        self.rail = find_system_power(root)
        self.name = 'smc_total_system_power' if self.rail else 'battery_flow'

    def watts(self):
        if self.rail is not None:
            value = number(self.rail)
            return None if value is None else value / 1e6
        if on_ac(self.root):
            return None  # battery flow says nothing about system draw on the charger
        flow = battery_flow_watts(self.root)
        return None if flow is None else abs(flow)


def percentile(values, fraction):
    values = sorted(values)
    if not values:
        return None
    index = (len(values) - 1) * fraction
    lo, hi = math.floor(index), math.ceil(index)
    return values[lo] + (values[hi] - values[lo]) * (index - lo)


def summarize(values):
    """Median and p10/p90 (the repo's reporting rule), plus n/min/max. Ignores None samples."""
    values = [v for v in values if v is not None]
    if not values:
        return {'n': 0}
    return {'n': len(values), 'median': round(percentile(values, 0.5), 3),
            'p10': round(percentile(values, 0.1), 3), 'p90': round(percentile(values, 0.9), 3),
            'min': round(min(values), 3), 'max': round(max(values), 3)}


def cpu_times(root='/'):
    """(busy, total) jiffies from the aggregate /proc/stat line."""
    fields = read(Path(root, 'proc/stat')).splitlines()[0].split()[1:]
    values = [int(x) for x in fields[:8]]
    idle = values[3] + values[4]
    return sum(values) - idle, sum(values)


def cpu_busy_pct(before, after):
    busy, total = after[0] - before[0], after[1] - before[1]
    return round(100 * busy / total, 1) if total > 0 else None


def load_average(root='/'):
    parts = read(Path(root, 'proc/loadavg')).split()
    return float(parts[0]) if parts else None


def pids_named(comm, root='/'):
    out = []
    for entry in Path(root, 'proc').glob('[0-9]*'):
        if read(entry / 'comm') == comm:
            out.append(int(entry.name))
    return sorted(out)


def process_counters(pid, root='/'):
    """CPU ticks (user+system, all threads) and context switches for one process, or None if gone."""
    stat = read(Path(root, 'proc', str(pid), 'stat'))
    if not stat:
        return None
    fields = stat[stat.rindex(')') + 2:].split()
    ticks = int(fields[11]) + int(fields[12])
    switches = 0
    for task in Path(root, 'proc', str(pid), 'task').glob('*'):
        for line in read(task / 'status').splitlines():
            if line.startswith(('voluntary_ctxt_switches', 'nonvoluntary_ctxt_switches')):
                switches += int(line.split()[1])
    return {'ticks': ticks, 'ctxt_switches': switches}


def counters_delta(before, after, seconds, hz=None):
    """Per-second CPU % and wakeups for a process between two process_counters() snapshots."""
    if not before or not after or seconds <= 0:
        return None
    hz = hz or os.sysconf('SC_CLK_TCK')
    return {'cpu_pct': round(100 * (after['ticks'] - before['ticks']) / hz / seconds, 2),
            'ctxt_switches_per_s': round((after['ctxt_switches'] - before['ctxt_switches']) / seconds, 1)}


def interrupts(match=('mbox',), root='/'):
    """Total count per /proc/interrupts line whose description contains any of `match`."""
    lines = read(Path(root, 'proc/interrupts')).splitlines()
    if not lines:
        return {}
    cpus = len(lines[0].split())
    out = {}
    for line in lines[1:]:
        parts = line.split()
        if len(parts) <= cpus or not parts[0].endswith(':'):
            continue
        counts = parts[1:cpus + 1]
        if not all(c.isdigit() for c in counts):
            continue
        description = parts[cpus + 1:]
        # The device name (last word, e.g. "38bc08000.mbox-recv") is stable across boots; IRQ numbers are not.
        if description and any(m in description[-1] for m in match):
            out[description[-1]] = out.get(description[-1], 0) + sum(int(c) for c in counts)
    return out


def interrupts_rate(before, after, seconds):
    return {k: round((after[k] - before[k]) / seconds, 1) for k in after if k in before and seconds > 0}


def backlight(root='/'):
    for device in sorted(Path(root, 'sys/class/backlight').glob('*')):
        current, maximum = number(device / 'brightness'), number(device / 'max_brightness')
        if current is not None and maximum:
            return {'device': device.name, 'brightness': int(current), 'max': int(maximum),
                    'pct': round(100 * current / maximum, 1)}
    return None


def sample(source, seconds, interval=1.0, clock=time.monotonic, sleep=time.sleep):
    """Sample `source.watts()` every `interval` seconds for `seconds`; returns the list of readings."""
    readings = []
    deadline = clock() + seconds
    next_tick = clock()
    while next_tick < deadline:
        readings.append(source.watts())
        next_tick += interval
        delay = next_tick - clock()
        if delay > 0:
            sleep(delay)
    return readings


if __name__ == '__main__':
    import argparse
    import json
    parser = argparse.ArgumentParser(description='Sample whole-system power at 1 Hz.')
    parser.add_argument('seconds', type=int, nargs='?', default=60)
    args = parser.parse_args()
    power = PowerSource()
    before = cpu_times()
    values = sample(power, args.seconds)
    print(json.dumps({'source': power.name, 'watts': summarize(values),
                      'cpu_busy_pct': cpu_busy_pct(before, cpu_times()), 'on_ac': on_ac()}))
