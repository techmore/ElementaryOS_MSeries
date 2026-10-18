#!/usr/bin/python3
"""Alternating A/B power trials on the SMC "Total System Power" rail, with honest verdicts.

  power_ab.py observe --seconds 120                 one arm, conditions recorded, no change made
  power_ab.py ab --label X --a-cmd CMD --b-cmd CMD  pairs of arms in AB, BA, AB... order
        [--pairs 3] [--seconds 120] [--settle 20] [--interval 1] [--allow-ac] [--out DIR]
  power_ab.py summarize RESULT.json                 re-print the verdict of a saved run

Arm A is the baseline, arm B the candidate; `--a-cmd` / `--b-cmd` put the machine into that state (for
example `mseries-power-tune revert X` / `mseries-power-tune apply X`). Nothing here changes display,
audio or kernel state by itself; commands are the caller's responsibility.

Verdict rules (mseries/POWER-ROADMAP.md honesty rules):
  * at least 3 pairs; every pair is (A, B) measured back to back, order alternating;
  * conditions must match across arms: same power source, display connectors, backlight level, and
    arm CPU-busy medians within 5 points; on AC the run is only accepted with --allow-ac and is labelled;
  * an effect is reported only if every paired delta has the same sign AND |median delta| exceeds the
    noise floor, which is the spread of the A-arm medians across pairs (repeatability of the baseline)
    and at least 0.25 W. Otherwise the result is "inconclusive", with the reasons.
Stdlib only; the sysfs/proc roots are overridable (MSERIES_SYS, MSERIES_PROC) for tests.
"""
import argparse
import json
import os
import statistics
import subprocess
import sys
import time
from pathlib import Path

SYS = Path(os.environ.get('MSERIES_SYS', '/sys'))
PROC = Path(os.environ.get('MSERIES_PROC', '/proc'))
MIN_PAIRS = 3
MIN_EFFECT_W = 0.25
MAX_BUSY_GAP = 5.0


def read(path, default=None):
    try:
        return Path(path).read_text().strip()
    except OSError:
        return default


def power_input():
    """Path of the SMC total-system power sensor (microwatts)."""
    for hw in sorted((SYS / 'class/hwmon').glob('hwmon*')):
        if read(hw / 'name') != 'macsmc_hwmon':
            continue
        for label in sorted(hw.glob('power*_label')):
            if read(label) == 'Total System Power':
                return hw / label.name.replace('_label', '_input')
    raise SystemExit('no SMC "Total System Power" sensor found under %s' % SYS)


def cpu_times():
    fields = [int(x) for x in read(PROC / 'stat').splitlines()[0].split()[1:9]]
    return sum(fields), fields[3] + fields[4]


def quantile(values, q):
    s = sorted(values)
    if not s:
        return None
    pos = (len(s) - 1) * q
    lo = int(pos)
    hi = min(lo + 1, len(s) - 1)
    return s[lo] + (s[hi] - s[lo]) * (pos - lo)


def top_processes(seconds=0.0, limit=6):
    """CPU% per process over a short window (one core = 100), for recording, never for killing."""
    hz = os.sysconf('SC_CLK_TCK')

    def snap():
        out = {}
        for p in PROC.iterdir():
            if not p.name.isdigit():
                continue
            try:
                comm = (p / 'comm').read_text().strip()
                f = (p / 'stat').read_text().rsplit(')', 1)[1].split()
                out[p.name] = (comm, int(f[11]) + int(f[12]))
            except (OSError, IndexError, ValueError):
                pass
        return out
    a = snap()
    time.sleep(seconds)
    b = snap()
    rows = []
    for pid, (comm, t) in b.items():
        if pid in a and seconds > 0:
            rows.append((round((t - a[pid][1]) / hz / seconds * 100, 1), comm, int(pid)))
    rows.sort(reverse=True)
    return [{'cpu': c, 'comm': n, 'pid': p} for c, n, p in rows[:limit]]


def conditions():
    """Read-only snapshot of state that changes power: source, battery, display connectors, backlight."""
    ps = SYS / 'class/power_supply'
    drm = {}
    for status in sorted((SYS / 'class/drm').glob('card*-*/status')):
        drm[status.parent.name] = read(status)
    backlight = {}
    for bl in sorted((SYS / 'class/backlight').glob('*')):
        backlight[bl.name] = read(bl / 'brightness')
    load = read(PROC / 'loadavg', '').split()[:3]
    return {
        'ac_online': read(ps / 'macsmc-ac/online'),
        'battery_status': read(ps / 'macsmc-battery/status'),
        'battery_capacity': read(ps / 'macsmc-battery/capacity'),
        'battery_energy_now': read(ps / 'macsmc-battery/energy_now'),
        'drm_connected': sorted(k for k, v in drm.items() if v == 'connected'),
        'backlight': backlight,
        'loadavg': load,
    }


def sample(seconds, interval=1.0):
    sensor = power_input()
    t0, i0 = cpu_times()
    watts = []
    n = max(1, int(round(seconds / interval)))
    for _ in range(n):
        time.sleep(interval)
        watts.append(int(read(sensor)) / 1e6)
    t1, i1 = cpu_times()
    busy = 100.0 * (1 - (i1 - i0) / (t1 - t0)) if t1 > t0 else 0.0
    return watts, busy


def arm_summary(watts, busy):
    return {
        'n': len(watts),
        'median': round(statistics.median(watts), 3),
        'mean': round(statistics.fmean(watts), 3),
        'p10': round(quantile(watts, 0.10), 3),
        'p90': round(quantile(watts, 0.90), 3),
        'min': round(min(watts), 3),
        'max': round(max(watts), 3),
        'cpu_busy': round(busy, 1),
    }


def run_arm(name, cmd, seconds, settle, interval):
    if cmd:
        subprocess.run(cmd, shell=True, check=True)
    time.sleep(settle)
    before = conditions()
    watts, busy = sample(seconds, interval)
    after = conditions()
    return {'arm': name, 'cmd': cmd, 'started': before, 'ended': after,
            'top': top_processes(min(2.0, interval * 2)), **arm_summary(watts, busy), 'samples': watts}


def display_key(c):
    return (tuple(c['drm_connected']), tuple(sorted(c['backlight'].items())))


def verdict(result, allow_ac=False):
    """Return (verdict string, reasons, stats). Pure function of a saved result."""
    pairs = result['pairs']
    reasons = []
    arms = [a for p in pairs for a in (p['A'], p['B'])]
    deltas = [p['B']['median'] - p['A']['median'] for p in pairs]
    a_meds = [p['A']['median'] for p in pairs]
    b_meds = [p['B']['median'] for p in pairs]
    stats = {
        'pairs': len(pairs),
        'A_median_of_medians': round(statistics.median(a_meds), 3) if a_meds else None,
        'B_median_of_medians': round(statistics.median(b_meds), 3) if b_meds else None,
        'paired_deltas_B_minus_A': [round(d, 3) for d in deltas],
        'median_delta': round(statistics.median(deltas), 3) if deltas else None,
        'A_repeat_spread': round(max(a_meds) - min(a_meds), 3) if a_meds else None,
    }
    if len(pairs) < MIN_PAIRS:
        reasons.append('only %d pair(s); need %d' % (len(pairs), MIN_PAIRS))
    sources = {(a['started']['ac_online'], a['ended']['ac_online']) for a in arms}
    if len({s for pair in sources for s in pair}) > 1:
        reasons.append('power source changed during the run')
    on_ac = any(a['started']['ac_online'] == '1' for a in arms)
    if on_ac and not allow_ac:
        reasons.append('on AC power: battery drain not measured; rerun on battery or pass --allow-ac')
    keys = {display_key(a['started']) for a in arms} | {display_key(a['ended']) for a in arms}
    if len(keys) > 1:
        reasons.append('display connectors or backlight changed between arms')
    busy = [a['cpu_busy'] for a in arms]
    if busy and max(busy) - min(busy) > MAX_BUSY_GAP:
        reasons.append('CPU busy differs %.1f-%.1f%% across arms (workload not matched)' % (min(busy), max(busy)))
    if deltas:
        same_sign = all(d > 0 for d in deltas) or all(d < 0 for d in deltas)
        floor = max(MIN_EFFECT_W, stats['A_repeat_spread'] or 0)
        stats['noise_floor_w'] = round(floor, 3)
        if not same_sign:
            reasons.append('paired deltas disagree in sign')
        if abs(stats['median_delta']) <= floor:
            reasons.append('median delta %.2f W within noise floor %.2f W' % (stats['median_delta'], floor))
    if reasons:
        return 'inconclusive', reasons, stats
    label = 'saving measured' if stats['median_delta'] < 0 else 'cost measured'
    if on_ac:
        label += ' (on AC, system rail only)'
    return label, [], stats


def fmt_arm(a):
    return '%s: median %.2f W (p10 %.2f, p90 %.2f, n=%d), CPU %.1f%%' % (
        a['arm'], a['median'], a['p10'], a['p90'], a['n'], a['cpu_busy'])


def print_result(result, allow_ac):
    v, reasons, stats = verdict(result, allow_ac)
    print('label: %s' % result['label'])
    for i, p in enumerate(result['pairs'], 1):
        print('pair %d (%s): %s | %s' % (i, p['order'], fmt_arm(p['A']), fmt_arm(p['B'])))
    print(json.dumps(stats))
    print('verdict: %s' % v)
    for r in reasons:
        print('  - %s' % r)
    return v


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest='cmd', required=True)
    ob = sub.add_parser('observe')
    ob.add_argument('--seconds', type=float, default=120)
    ob.add_argument('--interval', type=float, default=1.0)
    ob.add_argument('--out')
    ab = sub.add_parser('ab')
    ab.add_argument('--label', required=True)
    ab.add_argument('--a-cmd', default='')
    ab.add_argument('--b-cmd', default='')
    ab.add_argument('--pairs', type=int, default=3)
    ab.add_argument('--seconds', type=float, default=120)
    ab.add_argument('--settle', type=float, default=20)
    ab.add_argument('--interval', type=float, default=1.0)
    ab.add_argument('--allow-ac', action='store_true')
    ab.add_argument('--out')
    ab.add_argument('--end-on-b', action='store_true', help='do not return to arm A after the last pair')
    sm = sub.add_parser('summarize')
    sm.add_argument('file')
    sm.add_argument('--allow-ac', action='store_true')
    args = ap.parse_args(argv)

    if args.cmd == 'summarize':
        result = json.loads(Path(args.file).read_text())
        print_result(result, args.allow_ac or result.get('allow_ac', False))
        return 0
    if args.cmd == 'observe':
        arm = run_arm('observe', '', args.seconds, 0, args.interval)
        print(fmt_arm(arm))
        print(json.dumps({k: arm['started'][k] for k in ('ac_online', 'battery_status', 'drm_connected', 'loadavg')}))
        print('top: ' + ', '.join('%s %.1f%%' % (t['comm'], t['cpu']) for t in arm['top']))
        if args.out:
            Path(args.out).write_text(json.dumps(arm, indent=1))
        return 0

    pairs = []
    for i in range(args.pairs):
        order = 'AB' if i % 2 == 0 else 'BA'
        got = {}
        for name in order:
            cmd = args.a_cmd if name == 'A' else args.b_cmd
            got[name] = run_arm(name, cmd, args.seconds, args.settle, args.interval)
            print('pair %d %s' % (i + 1, fmt_arm(got[name])), flush=True)
        pairs.append({'order': order, 'A': got['A'], 'B': got['B']})
    result = {'label': args.label, 'allow_ac': args.allow_ac, 'when': time.strftime('%Y-%m-%dT%H:%M:%S%z'),
              'kernel': os.uname().release, 'seconds': args.seconds, 'settle': args.settle, 'pairs': pairs}
    if args.out:
        out = Path(args.out)
        out.mkdir(parents=True, exist_ok=True)
        path = out / ('%s-%s.json' % (args.label, time.strftime('%Y%m%d-%H%M%S')))
        path.write_text(json.dumps(result, indent=1))
        print('saved %s' % path)
    print_result(result, args.allow_ac)
    # Leave the machine in the baseline (A) state: an odd number of pairs ends on arm B.
    if args.a_cmd and pairs and pairs[-1]['order'] == 'AB' and not args.end_on_b:
        subprocess.run(args.a_cmd, shell=True, check=True)
        print('restored arm A state')
    return 0


if __name__ == '__main__':
    sys.exit(main())
