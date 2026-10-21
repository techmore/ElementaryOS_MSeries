#!/usr/bin/env python3
"""Serial vs parallel first-boot scheduling, on FAKE modules (#47).

This measures the scheduler (mseries/modrun.py) and the real lock/dependency graph
(mseries/enhance-modules.json), nothing else. Every module here is a sleep: no apt,
no download, no compile, no install script, no change to the system. The numbers
are SYNTHETIC. They show how much of the serial total the lock graph allows to
overlap, assuming modules do not slow each other down; real installs share CPU,
disk and network, so measure them on the Mac (see mseries/benchmarks/README.md).

  python3 mseries/benchmarks/installer-speed.py [--scale 0.02] [--jobs 5] [--repeat 3]
                                                [--what-if] [--out FILE.json]

--scale multiplies every module's duration (default 0.02: a 5-minute install
becomes 6 seconds). Durations are the issue's measured values where there is one
(brave 49 s, video 21 s, files 53 s, 2026-10-14 first boot) and round guesses for
the rest; they are inputs to this model, not measurements, and are labelled so in
the output.

--what-if adds a third row with the Wingpanel-plugin lock removed, to show what
relaxing that lock could be worth. It is not a recommendation: that lock is kept
until real timings justify the risk.
"""
import argparse
import json
import os
import statistics
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
MSERIES = os.path.dirname(HERE)
MODRUN = os.path.join(MSERIES, 'modrun.py')
GRAPH = os.path.join(MSERIES, 'enhance-modules.json')

# Seconds per module before scaling. "measured" values come from the issue (/var/log/
# elementary-mac-enhance.log on the M1 Pro, 2026-10-14); the rest are assumptions.
PROFILE = {
    'brave': (49, 'measured'), 'video': (21, 'measured'), 'files': (53, 'measured'),
    'gestures': (30, 'assumed'), 'network': (25, 'assumed'), 'quick': (40, 'assumed'),
    'sound': (18, 'assumed'), 'keyboard': (18, 'assumed'), 'osk': (25, 'assumed'),
    'battery-panel': (20, 'assumed'), 'netusage-policy': (1, 'assumed'),
    'desktop-user-deps': (2, 'assumed'),
}


def fake_graph(scale, drop_locks=()):
    with open(GRAPH, encoding='utf-8') as fh:
        real = json.load(fh)['tasks']
    tasks = {}
    for name, (seconds, _) in PROFILE.items():
        spec = real[name]
        tasks[name] = {
            'deps': spec.get('deps', []),
            'locks': [lock for lock in spec.get('locks', []) if lock not in drop_locks],
            'cmd': [sys.executable, '-c', f'import time; time.sleep({seconds * scale})'],
        }
    return tasks


def run_once(tasks, jobs):
    with tempfile.TemporaryDirectory() as tmp:
        graph = os.path.join(tmp, 'graph.json')
        summary = os.path.join(tmp, 'summary.json')
        with open(graph, 'w', encoding='utf-8') as fh:
            json.dump({'tasks': tasks}, fh)
        cmd = [sys.executable, MODRUN, 'run', '--graph', graph, '--summary-json', summary,
               '--no-replay', '--jobs', str(jobs)] + (['--serial'] if jobs == 1 else [])
        proc = subprocess.run(cmd, capture_output=True, text=True)
        if proc.returncode != 0:
            raise SystemExit(f'fake run failed:\n{proc.stdout}\n{proc.stderr}')
        with open(summary, encoding='utf-8') as fh:
            return json.load(fh)


def measure(label, tasks, jobs, repeat):
    docs = [run_once(tasks, jobs) for _ in range(repeat)]
    walls = [d['wall_s'] for d in docs]
    best = min(docs, key=lambda d: abs(d['wall_s'] - statistics.median(walls)))
    return {
        'label': label, 'jobs': jobs, 'repeat': repeat,
        'wall_s_median': round(statistics.median(walls), 3),
        'wall_s_runs': walls,
        'peak_concurrency': best['peak_concurrency'],
        'sum_task_wall_s': best['sum_task_wall_s'],
    }


def lower_bound(tasks, durations, jobs):
    """Fastest any schedule could finish: the longest lock chain, the longest module, or the work spread over the workers."""
    chains = {}
    for name, spec in tasks.items():
        for lock in spec['locks']:
            chains[lock] = chains.get(lock, 0) + durations[name]
    return max([max(durations.values()), sum(durations.values()) / jobs] + list(chains.values()))


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--scale', type=float, default=0.02)
    ap.add_argument('--jobs', type=int, default=5)
    ap.add_argument('--repeat', type=int, default=3)
    ap.add_argument('--what-if', action='store_true')
    ap.add_argument('--out')
    args = ap.parse_args()

    durations = {n: s * args.scale for n, (s, _) in PROFILE.items()}
    base = fake_graph(args.scale)
    rows = [measure('serial (default today)', base, 1, args.repeat),
            measure(f'parallel, {args.jobs} jobs, apt + Wingpanel locks', base, args.jobs, args.repeat)]
    if args.what_if:
        rows.append(measure(f'what-if: parallel, {args.jobs} jobs, Wingpanel lock removed',
                            fake_graph(args.scale, drop_locks=('wingpanel-plugins',)), args.jobs, args.repeat))
    serial = rows[0]['wall_s_median']
    for row in rows:
        row['speedup_vs_serial'] = round(serial / row['wall_s_median'], 2)
    bound = round(lower_bound(base, durations, args.jobs), 3)
    doc = {
        'synthetic': True,
        'note': 'Fake modules that only sleep; durations are the issue\'s measured first-boot values for brave, '
                'video and files and assumptions for the rest. Shows the scheduler and lock graph, not real '
                'install speed: real modules contend for CPU, disk and network.',
        'scale': args.scale, 'jobs': args.jobs,
        'module_seconds_unscaled': {n: {'seconds': s, 'basis': b} for n, (s, b) in PROFILE.items()},
        'unscaled_serial_total_s': sum(s for s, _ in PROFILE.values()),
        'lock_graph_lower_bound_s': bound,
        'rows': rows,
    }
    print('SYNTHETIC benchmark: fake sleep-only modules, real lock graph; not install measurements.')
    print(f'{"scenario":<58} {"wall s":>7} {"speedup":>8} {"peak":>5}')
    for row in rows:
        print(f'{row["label"]:<58} {row["wall_s_median"]:>7.2f} {row["speedup_vs_serial"]:>7.2f}x {row["peak_concurrency"]:>5}')
    print(f'lower bound for the locked graph at {args.jobs} jobs: {bound:.2f} s '
          f'(unscaled serial total {doc["unscaled_serial_total_s"]} s x scale {args.scale})')
    if args.out:
        with open(args.out, 'w', encoding='utf-8') as fh:
            json.dump(doc, fh, indent=2, sort_keys=True)
            fh.write('\n')


if __name__ == '__main__':
    sys.exit(main())
