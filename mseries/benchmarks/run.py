#!/usr/bin/python3
"""Benchmark suite for elementary OS on Apple Silicon (MacBook Pro 14" M1 Pro and friends).

  python3 mseries/benchmarks/run.py [--quick] [--skip gpu,disk,...] [--only power]

Writes mseries/benchmarks/results/<date>-<model>.json. Run on AC power with the machine otherwise idle; the
script refuses to run on battery (the on-battery CPU cap would skew results) unless --allow-battery is given.
Needs: sysbench fio glmark2-es2-wayland openssl p7zip-full (all in Ubuntu's archive).
"""
import argparse
import json
import os
import platform
import re
import shutil
import statistics
import subprocess
import sys
import tempfile
import time
from datetime import date
from pathlib import Path

RESULTS = Path(__file__).resolve().parent / 'results'
CPUS = os.cpu_count() or 1


def run(cmd, timeout=600, env=None):
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, env=env)
    return result.stdout + result.stderr


def read(path, default=''):
    try:
        return Path(path).read_text().strip()
    except OSError:
        return default


def temperature():
    """Highest SMC/hwmon temperature in degrees C, or None."""
    best = None
    for hwmon in Path('/sys/class/hwmon').glob('hwmon*'):
        for temp in hwmon.glob('temp*_input'):
            try:
                value = int(temp.read_text()) / 1000
            except (OSError, ValueError):
                continue
            best = value if best is None else max(best, value)
    return best


def system_info():
    model = read('/proc/device-tree/model').strip('\x00')
    mesa = run(['bash', '-c', "dpkg-query -W -f='${Version}' mesa-vulkan-drivers 2>/dev/null"]).strip()
    firefox = run(['bash', '-c', 'firefox --version 2>/dev/null']).strip()
    return {
        'date': date.today().isoformat(),
        'model': model,
        'kernel': platform.release(),
        'os': next((line.split('=', 1)[1].strip('"') for line in read('/etc/os-release').splitlines()
                    if line.startswith('PRETTY_NAME=')), ''),
        'cpus': CPUS,
        'memory_gib': round(int(re.search(r'MemTotal:\s+(\d+)', read('/proc/meminfo')).group(1)) / 1048576, 1),
        'governor': read('/sys/devices/system/cpu/cpu0/cpufreq/scaling_governor'),
        'power_profile': run(['powerprofilesctl', 'get']).strip(),
        'on_ac': read('/sys/class/power_supply/macsmc-ac/online') == '1',
        'mesa_vulkan_drivers': mesa,
        'firefox': firefox,
        'root_fs': run(['findmnt', '-no', 'FSTYPE,OPTIONS', '/']).strip()[:120],
        'start_temp_c': temperature(),
    }


def bench_cpu(quick):
    seconds = 5 if quick else 10
    out = {}
    for threads in (1, CPUS):
        text = run(['sysbench', 'cpu', '--cpu-max-prime=20000', f'--threads={threads}', f'--time={seconds}', 'run'])
        out[f'sysbench_prime_events_per_s_{threads}t'] = float(re.search(r'events per second:\s+([\d.]+)', text).group(1))
    text = run(['7z', 'b', f'-mmt={CPUS}'], timeout=300)
    total = [line for line in text.splitlines() if line.startswith('Tot:')]
    if total:
        out['7zip_total_mips'] = int(total[-1].split()[-1])
    for algorithm in ('aes-256-gcm', 'sha256'):
        text = run(['openssl', 'speed', '-seconds', '3', '-bytes', '16384', '-evp', algorithm])
        numbers = [line for line in text.splitlines() if line.startswith(algorithm)]
        if numbers:
            out[f'openssl_{algorithm}_mb_per_s_1t'] = round(float(numbers[-1].split()[-1].rstrip('k')) / 1000, 1)
    return out


def bench_memory(quick):
    out = {}
    total = '8G' if quick else '24G'
    for op in ('read', 'write'):
        for threads in (1, CPUS):
            text = run(['sysbench', 'memory', '--memory-block-size=1M', f'--memory-total-size={total}',
                        f'--memory-oper={op}', f'--threads={threads}', 'run'])
            out[f'memory_{op}_mib_per_s_{threads}t'] = float(re.search(r'\(([\d.]+) MiB/sec\)', text).group(1))
    return out


def bench_disk(quick):
    directory = Path.home() / '.cache' / 'mseries-bench'
    directory.mkdir(parents=True, exist_ok=True)
    seconds = 8 if quick else 15
    out = {}
    jobs = {
        'seq_read_1m': ['--rw=read', '--bs=1M', '--iodepth=8'],
        'seq_write_1m': ['--rw=write', '--bs=1M', '--iodepth=8'],
        'rand_read_4k_qd32': ['--rw=randread', '--bs=4k', '--iodepth=32'],
        'rand_write_4k_qd32': ['--rw=randwrite', '--bs=4k', '--iodepth=32'],
    }
    try:
        for name, args in jobs.items():
            text = run(['fio', '--name=' + name, f'--directory={directory}', '--size=2G', '--direct=1',
                        '--ioengine=libaio', '--refill_buffers', f'--runtime={seconds}', '--time_based',
                        '--output-format=json'] + args, timeout=120)
            data = json.loads(text[text.index('{'):])['jobs'][0]
            side = data['read'] if 'read' in args[0] else data['write']
            out[name + '_mb_per_s'] = round(side['bw_bytes'] / 1e6, 1)
            if 'rand' in args[0]:
                out[name + '_iops'] = int(side['iops'])
    finally:
        shutil.rmtree(directory, ignore_errors=True)
    return out


def bench_sustained(quick):
    """All cores for 60 s, throughput per 10 s window plus temperature, to show thermal behaviour."""
    seconds = 30 if quick else 60
    before = temperature()
    text = run(['sysbench', 'cpu', '--cpu-max-prime=20000', f'--threads={CPUS}', f'--time={seconds}',
                '--report-interval=10', 'run'], timeout=200)
    windows = [float(x) for x in re.findall(r'eps: ([\d.]+)', text)]
    return {'sustained_eps_per_10s_window': windows,
            'sustained_drop_pct': round(100 * (1 - min(windows) / max(windows)), 1) if windows else None,
            'temp_before_c': before, 'temp_after_c': temperature()}


def bench_gpu(quick):
    if not shutil.which('glmark2-es2-wayland'):
        return {'skipped': 'glmark2-es2-wayland not installed'}
    text = run(['glmark2-es2-wayland', '--off-screen', '-s', '1024x768'], timeout=900)
    score = re.search(r'glmark2 Score:\s+(\d+)', text)
    renderer = re.search(r'GL_RENDERER:\s+(.+)', text)
    return {'glmark2_es2_offscreen_1024x768_score': int(score.group(1)) if score else None,
            'gl_renderer': renderer.group(1).strip() if renderer else None}


def timed(cmd, runs=3):
    samples = []
    for _ in range(runs):
        start = time.perf_counter()
        subprocess.run(cmd, capture_output=True, timeout=120)
        samples.append(time.perf_counter() - start)
    return round(statistics.median(samples), 2)


def bench_startup(quick):
    out = {}
    profile = tempfile.mkdtemp(prefix='bench-ff-')
    if shutil.which('firefox'):
        out['firefox_headless_start_s'] = timed(['firefox', '--headless', '--profile', profile, '--screenshot',
                                                 os.path.join(profile, 'x.png'), 'about:blank'])
    shutil.rmtree(profile, ignore_errors=True)
    if shutil.which('chromium'):
        out['chromium_snap_headless_start_s'] = timed(['chromium', '--headless', '--screenshot=/tmp/bench-ch.png',
                                                       'about:blank'])
    return out


def bench_boot(quick):
    text = run(['systemd-analyze', 'time'])
    match = re.search(r'= ([\d.]+(?:min )?[\d.]+m?s)', text)
    # The passphrase prompt is part of the firmware/loader time; the userspace figure is the fair one.
    return {'systemd_analyze': text.strip().splitlines()[0],
            'note': 'includes the time spent typing the NVMe passphrase, so compare userspace only'}


def bench_power(quick):
    """Idle whole-system power plus compositor CPU/wakeups. Opt-in (--only power): it needs a quiet machine.

    For A/B trials of a compositor or kernel change use power_scenarios.py directly with --label and compare.
    """
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import power_scenarios
    target = Path(tempfile.mkdtemp(prefix='bench-power-')) / 'power.json'
    try:
        power_scenarios.main(['run', '--label', 'run.py', '--scenarios', 'idle', '--out', str(target),
                              '--minutes', '1' if quick else '5', '--warmup', '15' if quick else '60'])
    except SystemExit as refusal:  # busy machine or no power sensor: record why instead of aborting run.py
        shutil.rmtree(target.parent, ignore_errors=True)
        return {'skipped': str(refusal.code)}
    data = json.loads(target.read_text())
    shutil.rmtree(target.parent, ignore_errors=True)
    idle = data['scenarios']['idle']
    return {'qualified': data['qualified'], 'source': data['context']['power_source'],
            'backlight_pct': (data['context']['backlight'] or {}).get('pct'),
            'idle_watts': idle['watts'], 'idle_cpu_busy_pct': idle['cpu_busy_pct'],
            'idle_processes': idle['processes'], 'idle_mailbox_irq_per_s': idle['mailbox_irq_per_s']}


SUITES = {'cpu': bench_cpu, 'memory': bench_memory, 'disk': bench_disk, 'sustained': bench_sustained,
          'gpu': bench_gpu, 'startup': bench_startup, 'boot': bench_boot, 'power': bench_power}
OPT_IN = {'power'}  # only with --only; it refuses to run on a busy machine


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--quick', action='store_true', help='shorter runs (smoke test, not for publishing)')
    parser.add_argument('--skip', default='', help='comma separated suites to skip: ' + ','.join(SUITES))
    parser.add_argument('--only', default='', help='comma separated suites to run (includes opt-in: power)')
    parser.add_argument('--allow-battery', action='store_true')
    parser.add_argument('--out')
    args = parser.parse_args()

    info = system_info()
    if not info['on_ac'] and not args.allow_battery:
        sys.exit('Plug in the charger first (on battery the CPU is capped), or pass --allow-battery.')
    skip = set(filter(None, args.skip.split(',')))
    only = set(filter(None, args.only.split(',')))
    results = {}
    for name, suite in SUITES.items():
        if name in skip or (only and name not in only) or (not only and name in OPT_IN):
            continue
        print(f'== {name}', flush=True)
        started = time.time()
        try:
            results[name] = suite(args.quick)
        except Exception as error:  # keep going; record what failed
            results[name] = {'error': f'{type(error).__name__}: {error}'}
        print(json.dumps(results[name]), f'({time.time() - started:.0f}s)', flush=True)
        time.sleep(15 if name in ('sustained', 'cpu') else 2)  # let temperatures settle between suites

    info['end_temp_c'] = temperature()
    payload = {'info': info, 'results': results, 'quick': args.quick}
    RESULTS.mkdir(exist_ok=True)
    slug = re.sub(r'[^a-z0-9]+', '-', info['model'].lower()).strip('-') or 'machine'
    target = Path(args.out) if args.out else RESULTS / f"{info['date']}-{slug}{'-quick' if args.quick else ''}.json"
    target.write_text(json.dumps(payload, indent=2) + '\n')
    print('saved', target)


if __name__ == '__main__':
    main()
