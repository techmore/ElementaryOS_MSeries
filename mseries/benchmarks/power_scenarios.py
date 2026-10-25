#!/usr/bin/python3
"""Repeatable power scenarios for the desktop and the Rust compositor.

  python3 mseries/benchmarks/power_scenarios.py run --label dmabuf-off [--scenarios idle,scroll,video]
                                                    [--video FILE] [--minutes 5] [--force]
  python3 mseries/benchmarks/power_scenarios.py compare RESULT.json ...

Each `run` is one arm of an A/B trial: change one thing (a compositor flag, a kernel, a refresh rate),
log in again if needed, and run with a label describing it. `compare` refuses to call a winner unless
the arms alternate (A, B, A, B, ...) at least three times per label, as mseries/POWER-ROADMAP.md requires,
and reports medians with p10/p90.

Per scenario it records whole-system watts at 1 Hz after a warm-up, CPU busy %, the compositor's and
Xwayland's CPU % and wakeups/s, display/AOP mailbox interrupt rates, and the compositor's redraw-stats
journal lines. Run from an SSH session or a text console when possible, so the measuring terminal does
not redraw. The script never restarts the compositor, panels or dock, and restores anything it opens.
"""
import argparse
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'power'))
import sensors  # noqa: E402

RESULTS = Path(__file__).resolve().parent / 'results' / 'power'
COMPOSITOR_COMM = 'pantheon-compos'  # /proc comm is truncated to 15 characters
WATCHED_PROCESSES = {'compositor': COMPOSITOR_COMM, 'xwayland': 'Xwayland', 'gala': 'gala'}
QUIET_LOAD = 1.0
QUIET_BUSY_PCT = 5.0

SCROLL_PAGE = """<!doctype html><meta charset=utf-8><title>mseries scroll scenario</title>
<style>body{font:18px/1.6 sans-serif;margin:0 15%}p{margin:0 0 1em}</style>
<body><script>
for (let i = 0; i < 4000; i++) {
  const p = document.createElement('p');
  p.textContent = i + ' Lorem ipsum dolor sit amet, consectetur adipiscing elit, sed do eiusmod tempor.';
  document.body.appendChild(p);
}
let dir = 1;
function step() {
  window.scrollBy(0, 6 * dir);
  if (window.scrollY + innerHeight >= document.body.scrollHeight - 2 || window.scrollY <= 0) dir = -dir;
  requestAnimationFrame(step);
}
requestAnimationFrame(step);
</script>"""


def journal_redraw_lines(since_epoch):
    """Compositor redraw/metrics journal lines since a wall-clock time (empty if journalctl is missing)."""
    if not shutil.which('journalctl'):
        return []
    text = subprocess.run(['journalctl', '--user', '--no-pager', '-o', 'cat', f'_COMM={COMPOSITOR_COMM}',
                           '--since', f'@{int(since_epoch)}'], capture_output=True, text=True).stdout
    return [line for line in text.splitlines() if 'redraw stats' in line or 'pantheon_stats' in line]


def parse_redraw(lines):
    """Sum the key=value counters in redraw-stats lines (format may change; unknown lines are kept raw)."""
    totals = {}
    for line in lines:
        for key, value in re.findall(r'\b(commits|redraw_requests|vblanks|frames_queued|frames_empty)=(\d+)', line):
            totals[key] = totals.get(key, 0) + int(value)
    return totals


def quiet_check(seconds=10, root='/'):
    before = sensors.cpu_times(root)
    time.sleep(seconds)
    busy = sensors.cpu_busy_pct(before, sensors.cpu_times(root))
    load = sensors.load_average(root)
    problems = []
    if load is not None and load > QUIET_LOAD:
        problems.append(f'load average {load} > {QUIET_LOAD}')
    if busy is not None and busy > QUIET_BUSY_PCT:
        problems.append(f'CPU {busy}% busy > {QUIET_BUSY_PCT}%')
    return {'load_average': load, 'cpu_busy_pct': busy, 'problems': problems}


def context():
    def out(cmd):
        try:
            return subprocess.run(cmd, capture_output=True, text=True, timeout=10).stdout.strip()
        except (OSError, subprocess.TimeoutExpired):
            return ''
    compositor = sensors.pids_named(COMPOSITOR_COMM)
    environ = {}
    if compositor:
        try:
            raw = Path(f'/proc/{compositor[0]}/environ').read_bytes().split(b'\0')
            environ = {k: v for k, _, v in (x.decode(errors='replace').partition('=') for x in raw)
                       if k.startswith('PANTHEON_') or k == 'RUST_LOG'}
        except OSError:
            pass
    return {
        'time': datetime.now(timezone.utc).isoformat(timespec='seconds'),
        'kernel': out(['uname', '-r']),
        'model': sensors.read('/proc/device-tree/model').strip('\x00'),
        'on_ac': sensors.on_ac(),
        'power_source': sensors.PowerSource().name,
        'backlight': sensors.backlight(),
        'power_profile': out(['powerprofilesctl', 'get']),
        'compositor_running': bool(compositor),
        'compositor_env': environ,
        'compositor_version': out(['dpkg-query', '-W', '-f=${Version}', 'pantheon-rust-compositor']),
        'drm_modes': {p.parent.name: sensors.read(p).splitlines()[:1]
                      for p in Path('/sys/class/drm').glob('card*-*/modes')
                      if sensors.read(p.parent / 'status') == 'connected'},
    }


class Opened:
    """A helper process the scenario starts and must stop afterwards."""

    def __init__(self, cmd):
        self.process = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                        start_new_session=True)

    def close(self):
        if self.process.poll() is None:
            try:
                os.killpg(self.process.pid, signal.SIGTERM)
                self.process.wait(timeout=10)
            except (ProcessLookupError, subprocess.TimeoutExpired):
                self.process.kill()


def start_idle(args, workdir):
    return None


def start_video(args, workdir):
    if not args.video:
        raise SkipScenario('no --video file given (use a local 1080p clip)')
    if not shutil.which('mpv'):
        raise SkipScenario('mpv is not installed')
    return Opened(['mpv', '--really-quiet', '--loop-file=inf', '--hwdec=auto-safe', '--no-audio',
                   '--fullscreen', args.video])


def start_scroll(args, workdir):
    browser = next((b for b in ('brave-browser', 'chromium', 'google-chrome') if shutil.which(b)), None)
    if browser is None:
        raise SkipScenario('no Chromium-family browser found')
    page = Path(workdir, 'scroll.html')
    page.write_text(SCROLL_PAGE)
    profile = Path(workdir, 'profile')
    return Opened([browser, f'--user-data-dir={profile}', '--no-first-run', '--no-default-browser-check',
                   '--disable-extensions', '--start-maximized', f'--app=file://{page}'])


class SkipScenario(Exception):
    pass


SCENARIOS = {'idle': start_idle, 'scroll': start_scroll, 'video': start_video}


def measure(seconds, power):
    procs = {name: sensors.pids_named(comm) for name, comm in WATCHED_PROCESSES.items()}
    procs = {name: pids[0] for name, pids in procs.items() if pids}
    before = {name: sensors.process_counters(pid) for name, pid in procs.items()}
    irq_before = sensors.interrupts()
    cpu_before = sensors.cpu_times()
    wall = time.time()
    started = time.monotonic()
    watts = sensors.sample(power, seconds)
    elapsed = time.monotonic() - started
    cpu_after = sensors.cpu_times()
    irq_after = sensors.interrupts()
    after = {name: sensors.process_counters(pid) for name, pid in procs.items()}
    redraw_lines = journal_redraw_lines(wall)
    return {
        'seconds': round(elapsed, 1),
        'watts': sensors.summarize(watts),
        'watts_samples': [None if w is None else round(w, 3) for w in watts],
        'cpu_busy_pct': sensors.cpu_busy_pct(cpu_before, cpu_after),
        'processes': {name: sensors.counters_delta(before[name], after[name], elapsed) for name in procs},
        'mailbox_irq_per_s': {k: v for k, v in sensors.interrupts_rate(irq_before, irq_after, elapsed).items()
                              if v > 0},
        'redraw_totals': parse_redraw(redraw_lines),
        'redraw_lines': redraw_lines,
    }


def run(args):
    if sensors.on_ac() is False and args.require_ac:
        sys.exit('On battery but --require-ac was given.')
    power = sensors.PowerSource()
    if power.watts() is None:
        sys.exit('No whole-system power reading: no SMC Total System Power rail, and battery flow is '
                 'meaningless on the charger.')
    print('checking that the machine is quiet (10 s)...', flush=True)
    quiet = quiet_check()
    if quiet['problems'] and not args.force:
        sys.exit('Not quiet: ' + '; '.join(quiet['problems']) + '. Stop builds/agents, or pass --force '
                 '(the result is then marked unqualified).')
    payload = {'label': args.label, 'context': context(), 'quiet': quiet,
               'qualified': not quiet['problems'], 'warmup_s': args.warmup, 'scenarios': {}}
    for name in args.scenarios.split(','):
        print(f'== {name}', flush=True)
        workdir = tempfile.mkdtemp(prefix=f'mseries-power-{name}-')
        opened = None
        try:
            opened = SCENARIOS[name](args, workdir)
            time.sleep(args.warmup)
            payload['scenarios'][name] = measure(args.minutes * 60, power)
            summary = payload['scenarios'][name]
            print(json.dumps({'watts': summary['watts'], 'compositor': summary['processes'].get('compositor')}),
                  flush=True)
        except SkipScenario as reason:
            payload['scenarios'][name] = {'skipped': str(reason)}
            print('skipped:', reason, flush=True)
        finally:
            if opened:
                opened.close()
            shutil.rmtree(workdir, ignore_errors=True)
        time.sleep(5)
    RESULTS.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime('%Y%m%dT%H%M%S')
    slug = re.sub(r'[^A-Za-z0-9]+', '-', args.label).strip('-') or 'run'
    target = Path(args.out) if args.out else RESULTS / f'{stamp}-{slug}.json'
    target.write_text(json.dumps(payload, indent=2) + '\n')
    print('saved', target)
    return target


def alternation_ok(labels):
    """True when two labels strictly alternate and each appears at least three times."""
    distinct = list(dict.fromkeys(labels))
    if len(distinct) != 2:
        return False
    if any(labels.count(label) < 3 for label in distinct):
        return False
    return all(a != b for a, b in zip(labels, labels[1:]))


def compare(paths):
    runs = []
    for path in paths:
        data = json.loads(Path(path).read_text())
        runs.append((data['context']['time'], data))
    runs.sort(key=lambda item: item[0])
    labels = [data['label'] for _, data in runs]
    report = {'order': labels, 'alternation_ok': alternation_ok(labels),
              'all_qualified': all(data.get('qualified') for _, data in runs), 'scenarios': {}}
    scenarios = sorted({name for _, data in runs for name in data['scenarios']})
    for name in scenarios:
        per_label = {}
        for _, data in runs:
            result = data['scenarios'].get(name, {})
            if 'watts' in result and result['watts'].get('n'):
                per_label.setdefault(data['label'], []).append(result['watts']['median'])
        report['scenarios'][name] = {label: {'runs': len(values), **sensors.summarize(values)}
                                     for label, values in per_label.items()}
    if not report['alternation_ok']:
        report['verdict'] = 'not comparable: need two labels alternating A,B,A,B,... with at least 3 runs each'
    elif not report['all_qualified']:
        report['verdict'] = 'indicative only: at least one run was taken on a busy machine (--force)'
    else:
        report['verdict'] = 'comparable'
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest='command', required=True)
    r = sub.add_parser('run', help='measure one arm')
    r.add_argument('--label', required=True, help='what this arm is, e.g. dmabuf-on or 60hz')
    r.add_argument('--scenarios', default='idle,scroll')
    r.add_argument('--video', help='local video file for the video scenario')
    r.add_argument('--minutes', type=float, default=5)
    r.add_argument('--warmup', type=float, default=60)
    r.add_argument('--force', action='store_true', help='run even when the machine is busy (unqualified)')
    r.add_argument('--require-ac', action='store_true')
    r.add_argument('--out')
    c = sub.add_parser('compare', help='compare alternating arms')
    c.add_argument('results', nargs='+')
    args = parser.parse_args(argv)
    if args.command == 'run':
        unknown = set(args.scenarios.split(',')) - set(SCENARIOS)
        if unknown:
            parser.error('unknown scenarios: ' + ','.join(sorted(unknown)))
        run(args)
    else:
        print(json.dumps(compare(args.results), indent=2))


if __name__ == '__main__':
    main()
