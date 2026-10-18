#!/usr/bin/python3
# SPDX-License-Identifier: MIT
# Adapted from omacom/omarchy-mac-pkgs b5e10d3d; see UPSTREAM.md and LICENSE.omacom.
# summary=Show the battery draw, CPU activity, power settings and the last suspend's cost

import argparse
import math
import platform
import os
from pathlib import Path
import subprocess
import sys
import time

SYS = Path(os.environ.get('MSERIES_SYS_ROOT') or '/sys')
PROC = Path(os.environ.get('MSERIES_PROC_ROOT') or '/proc')
POWER_SUPPLY = Path(os.environ.get('MSERIES_POWER_SUPPLY_PATH') or SYS / 'class/power_supply')
SLEEP_COST = Path(__file__).resolve().with_name('sleep-cost')
TOP = 8


def read(path):
    try:
        return path.read_bytes().decode(errors='replace').strip('\0\n ')
    except OSError:
        return None


def number(text):
    try:
        return int(text)
    except (TypeError, ValueError):
        return None


def children(path, pattern='*'):
    try:
        return sorted(path.glob(pattern))
    except OSError:
        return []


def megahertz(text):
    value = number(text)
    return '?' if value is None else '%d' % (value // 1000)


def battery_section():
    lines, sources = [], []
    charger = any(read(supply / 'type') in ('Mains', 'USB') and read(supply / 'online') == '1'
                  for supply in children(POWER_SUPPLY))
    for supply in children(POWER_SUPPLY):
        kind = read(supply / 'type')
        if kind == 'Battery' and read(supply / 'present') != '0':
            now, full = number(read(supply / 'energy_now')), number(read(supply / 'energy_full'))
            power = number(read(supply / 'power_now'))
            status = read(supply / 'status') or 'unknown'
            line = '%s: %s' % (supply.name, status)
            if now is not None and full:
                line += ', %.1f of %.1f Wh (%.0f%%)' % (now / 1e6, full / 1e6, 100 * now / full)
            lines.append(line)
            # The SMC signs power_now by direction; status says which way.
            if power is None:
                lines.append('  Battery draw now: unknown')
            elif status == 'Charging':
                lines.append('  Charging at %.2f W' % (abs(power) / 1e6))
            elif charger and status != 'Discharging':
                lines.append('  Battery draw now: %.2f W; a charger powering the Mac hides its draw, so unplug it to measure.' % (abs(power) / 1e6))
            else:
                lines.append('  Battery draw now: %.2f W' % (abs(power) / 1e6))
        elif kind in ('Mains', 'USB'):
            state = {'1': 'connected', '0': 'not connected'}.get(read(supply / 'online'), 'unknown')
            sources.append('%s (%s power): %s' % (supply.name, kind, state))
    return lines + sources or ['No battery or power supply found.']


def jiffies(pid_directory):
    # (name, user + system ticks) from /proc/<pid>/stat.
    text = read(pid_directory / 'stat')
    if not text or ')' not in text:
        return None
    head, tail = text.rsplit(')', 1)
    fields = tail.split()
    try:
        return head.partition('(')[2], int(fields[11]) + int(fields[12]), int(fields[19])
    except (IndexError, ValueError):
        return None


def processes():
    found = {}
    for directory in children(PROC, '[0-9]*'):
        if directory.name == str(os.getpid()):
            continue
        sample = jiffies(directory)
        if sample:
            found[directory.name] = sample
    return found


def cpu_totals():
    # (busy, all) ticks across every CPU from /proc/stat.
    for line in (read(PROC / 'stat') or '').splitlines():
        if line.startswith('cpu '):
            # guest and guest_nice are already counted in user and nice.
            values = [int(value) for value in line.split()[1:9]]
            idle = values[3] + (values[4] if len(values) > 4 else 0)
            return sum(values) - idle, sum(values)
    return None


def activity_section(seconds, sleep=None):
    ticks = os.sysconf('SC_CLK_TCK')
    cpus = len(children(SYS / 'devices/system/cpu', 'cpu[0-9]*')) or os.cpu_count() or 1
    before, totals_before = processes(), cpu_totals()
    (sleep or time.sleep)(seconds)
    after, totals_after = processes(), cpu_totals()
    lines = ['CPU activity over %g s (share of one core; a measure of activity, not of power):' % seconds]
    if totals_before and totals_after and totals_after[1] > totals_before[1]:
        busy = (totals_after[0] - totals_before[0]) / (totals_after[1] - totals_before[1])
        lines.append('  All %d cores: %.0f%% busy' % (cpus, 100 * busy))
    used = []
    for pid, (name, total, born) in after.items():
        if pid in before and before[pid][0] == name and before[pid][2] == born and total > before[pid][1]:
            used.append(((total - before[pid][1]) / ticks / seconds, pid, name))
    for share, pid, name in sorted(used, reverse=True)[:TOP]:
        lines.append('  %5.1f%%  %-7s %s' % (100 * share, pid, name))
    if not used:
        lines.append('  No process used the CPU.')
    return lines


def frequency_section():
    lines = []
    for policy in children(SYS / 'devices/system/cpu/cpufreq', 'policy[0-9]*'):
        lines.append('%s (CPUs %s): %s, %s, hardware %s-%s MHz, allowed %s-%s MHz, now %s MHz' % (
            policy.name, read(policy / 'related_cpus') or '?', read(policy / 'scaling_driver') or '?',
            read(policy / 'scaling_governor') or '?',
            megahertz(read(policy / 'cpuinfo_min_freq')), megahertz(read(policy / 'cpuinfo_max_freq')),
            megahertz(read(policy / 'scaling_min_freq')), megahertz(read(policy / 'scaling_max_freq')),
            megahertz(read(policy / 'scaling_cur_freq'))))
    return lines or ['No CPU frequency scaling.']


def idle_section():
    cpuidle = SYS / 'devices/system/cpu/cpuidle'
    driver = read(cpuidle / 'current_driver')
    if not driver or driver == 'none':
        return ['No cpuidle driver.']
    lines = ['Driver %s, governor %s' % (driver, read(cpuidle / 'current_governor_ro') or read(cpuidle / 'current_governor') or '?')]
    for state in children(SYS / 'devices/system/cpu/cpu0/cpuidle', 'state[0-9]*'):
        disabled = ' (disabled)' if read(state / 'disable') == '1' else ''
        lines.append('  %s: %s, %s%s' % (state.name, read(state / 'name') or '?', read(state / 'desc') or '', disabled))
    return lines


def pmp_section():
    driver = SYS / 'bus/platform/drivers/apple_pmp'
    if not driver.is_dir():
        return ['PMP: no apple_pmp driver in this kernel.']
    bound = [link.name for link in children(driver) if link.is_symlink() and link.name != 'module']
    if bound:
        return ['PMP: apple_pmp bound to %s.' % ', '.join(bound)]
    return ['PMP: apple_pmp is present but bound to no device (the device tree does not enable it).']


def sleep_section():
    lines = ['Sleep states: %s' % (read(SYS / 'power/mem_sleep') or 'unknown')]
    if SLEEP_COST.exists():
        try:
            result = subprocess.run([sys.executable, '-I', str(SLEEP_COST), 'last'], capture_output=True, text=True, timeout=5)
            lines.append('Last suspend: ' + (result.stdout.strip() if result.returncode == 0 else 'unavailable'))
        except (OSError, subprocess.SubprocessError):
            lines.append('Last suspend: unavailable')
    return lines


def power_profile_section():
    try:
        result = subprocess.run(['powerprofilesctl', 'list'], capture_output=True, text=True, timeout=5)
    except (OSError, subprocess.SubprocessError):
        return []
    active = driver = None
    for line in result.stdout.splitlines():
        if line.startswith('* '):
            active = line[2:].rstrip(':')
        elif active and driver is None and 'PlatformDriver:' in line:
            driver = line.split(':', 1)[1].strip()
    if not active:
        return []
    line = 'Power profile: %s' % active
    if driver == 'placeholder':
        line += ' (placeholder platform driver; other per-profile policies may still apply)'
    return [line]


def main():
    parser = argparse.ArgumentParser(prog='mseries-power-report')
    parser.add_argument('--sample', type=float, default=10.0, help='seconds of CPU activity to sample')
    arguments = parser.parse_args()
    if not math.isfinite(arguments.sample) or not 0 < arguments.sample <= 300:
        parser.error('--sample must be finite and between 0 and 300 seconds')
    try:
        apple = platform.machine() == 'aarch64' and b'apple,' in (SYS / 'firmware/devicetree/base/compatible').read_bytes().lower()
    except OSError:
        apple = False
    if not apple:
        print('mseries-power-report: this is not an Apple Silicon Mac', file=sys.stderr)
        return 1
    model = read(SYS / 'firmware/devicetree/base/model')
    sections = [
        ('System', [line for line in ('Mac: ' + model if model else None, 'Kernel: ' + (read(PROC / 'sys/kernel/osrelease') or 'unknown')) if line]
         + power_profile_section()),
        ('Battery and power', battery_section()),
        ('CPU frequency limits', frequency_section()),
        ('CPU idle states', idle_section()),
        ('Power management processor', pmp_section()),
        ('Suspend', sleep_section()),
    ]
    for title, lines in sections:
        print(title)
        print('\n'.join('  ' + line for line in lines))
        print()
    print('Sampling CPU activity for %g s...' % arguments.sample, file=sys.stderr, flush=True)
    print('\n'.join(activity_section(arguments.sample)))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
