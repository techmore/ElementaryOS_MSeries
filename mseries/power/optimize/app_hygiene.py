#!/usr/bin/python3
"""Identify (never stop or kill) the processes that hold CPU, grouped by app and Chromium/Electron profile.

  app_hygiene.py [--seconds 30] [--min 2.0] [--json]

For Chromium-family processes the app is taken from the executable and the profile from --user-data-dir,
and the process type (gpu-process, renderer, utility) from --type, so "Brave renderer at 20%" becomes
"brave (~/.config/brave-youtube) renderer pid N". Output is a report for the owner; acting on it
(closing a tab, quitting an app) is the owner's decision.
"""
import argparse
import json
import os
import sys
import time
from pathlib import Path

PROC = Path(os.environ.get('MSERIES_PROC', '/proc'))
HOME = os.path.expanduser('~')


def cmdline(pid):
    try:
        return (PROC / pid / 'cmdline').read_bytes().split(b'\0')
    except OSError:
        return []


def describe(pid, comm):
    args = [a.decode(errors='replace') for a in cmdline(pid) if a]
    app = os.path.basename(args[0]) if args else comm
    kind = profile = None
    for a in args[1:]:
        if a.startswith('--type='):
            kind = a.split('=', 1)[1]
        elif a.startswith('--user-data-dir='):
            profile = a.split('=', 1)[1].replace(HOME, '~')
    return app, kind or 'main', profile


def snap():
    out = {}
    for p in PROC.iterdir():
        if not p.name.isdigit():
            continue
        try:
            comm = (p / 'comm').read_text().strip()
            f = (p / 'stat').read_text().rsplit(')', 1)[1].split()
            out[p.name] = (comm, int(f[11]) + int(f[12]), int(f[19]))
        except (OSError, IndexError, ValueError):
            pass
    return out


def measure(seconds):
    hz = os.sysconf('SC_CLK_TCK')
    a = snap()
    time.sleep(seconds)
    b = snap()
    uptime = float((PROC / 'uptime').read_text().split()[0])
    rows = []
    for pid, (comm, t, start) in b.items():
        if pid not in a or a[pid][0] != comm:
            continue
        cpu = (t - a[pid][1]) / hz / seconds * 100
        age = max(1.0, uptime - start / hz)
        app, kind, profile = describe(pid, comm)
        rows.append({'pid': int(pid), 'comm': comm, 'app': app, 'type': kind, 'profile': profile,
                     'cpu': round(cpu, 1), 'lifetime_cpu': round(t / hz / age * 100, 1), 'age_min': round(age / 60)})
    return rows


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--seconds', type=float, default=30)
    ap.add_argument('--min', type=float, default=2.0, help='hide processes below this CPU%% (one core = 100)')
    ap.add_argument('--json', action='store_true')
    args = ap.parse_args(argv)
    rows = [r for r in measure(args.seconds) if r['cpu'] >= args.min]
    rows.sort(key=lambda r: -r['cpu'])
    if args.json:
        print(json.dumps(rows, indent=1))
        return 0
    groups = {}
    for r in rows:
        key = (r['app'], r['profile'])
        groups[key] = groups.get(key, 0) + r['cpu']
    print('window %.0f s; CPU%% of one core; "life" = average since the process started' % args.seconds)
    for (app, profile), cpu in sorted(groups.items(), key=lambda x: -x[1]):
        print('%6.1f%%  %s%s' % (cpu, app, ' (%s)' % profile if profile else ''))
        for r in rows:
            if (r['app'], r['profile']) == (app, profile):
                print('          %5.1f%% (life %5.1f%%, %4d min) %-12s pid %d' % (
                    r['cpu'], r['lifetime_cpu'], r['age_min'], r['type'], r['pid']))
    return 0


if __name__ == '__main__':
    sys.exit(main())
