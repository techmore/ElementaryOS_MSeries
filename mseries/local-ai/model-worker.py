#!/usr/bin/python3
"""Supervise only our inference child, preserving desktop memory and quiet limits."""
import argparse
import fcntl
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

from machine import DEFAULT_POLICY, GIB, snapshot, violations, cooling_action


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('profile', choices=['everyday', 'compact', 'personal', 'coder', 'coder7', 'coder-large', 'liquid', 'bonsai', 'compact35'])
    args = parser.parse_args()
    home = Path.home()
    config = json.loads((home / '.config/mseries-ai/profiles.json').read_text())
    lock_dir = home / '.local/state/mseries-ai'
    lock_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    lock = (lock_dir / 'worker.lock').open('a')
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        print('ADMISSION REFUSED: another managed model is running', flush=True)
        return 3
    profile = config['profiles'][args.profile]
    policy = dict(config.get('policy', DEFAULT_POLICY))
    initial = snapshot()
    reasons = violations(initial, policy, int(profile['admission_gib'] * GIB))
    if reasons:
        print('ADMISSION REFUSED: ' + '; '.join(reasons), flush=True)
        return 3
    baseline = max(initial['fans_rpm'].values())
    policy.setdefault('cool_fan_rpm', min(baseline + 300, policy['max_fan_rpm'] - 200))
    policy.setdefault('resume_fan_rpm', min(baseline + 100, policy['cool_fan_rpm'] - 100))
    print(f"QUIET POLICY: baseline {baseline:.0f} RPM; pause {policy['cool_fan_rpm']:.0f}; resume {policy['resume_fan_rpm']:.0f}; hard stop {policy['max_fan_rpm']}", flush=True)
    env = dict(os.environ, OMP_NUM_THREADS='2', OPENBLAS_NUM_THREADS='2',
               HF_HUB_OFFLINE='1', TRANSFORMERS_OFFLINE='1', HF_HUB_DISABLE_TELEMETRY='1')
    prefix = home / '.local/share/mlx-omarchy'
    if not prefix.exists():
        prefix = Path('/usr/lib/omarchy-mlx')
    env['OMARCHY_MLX_SYSTEM_PREFIX'] = str(prefix)
    env['VK_DRIVER_FILES'] = str(prefix / 'vulkan/honeykrisp_icd.aarch64.json')
    if profile['engine'] == 'mlx':
        launcher = home / '.local/bin/mlx-omarchy-serve'
        if not launcher.exists():
            launcher = Path('/usr/bin/mlx-omarchy-serve')
        command = [str(launcher), 'serve', profile['model'],
                   '--context', str(profile['context']), '--prompt-cache-size', str(profile.get('prompt_cache_size', 1)),
                   '--host', '127.0.0.1', '--port', str(profile['port']), '--offline', '--yes']
        if 'weights_gib' in profile:
            command += ['--weights-gib', str(profile['weights_gib'])]
    else:
        driver = home / '.local/share/mlx-omarchy/vulkan/honeykrisp_icd.aarch64.json'
        if not driver.exists():
            driver = Path('/usr/lib/omarchy-mlx/vulkan/honeykrisp_icd.aarch64.json')
        env['VK_DRIVER_FILES'] = str(driver)
        binary = home / '.local/share/mseries-ai/llama/bin/llama-server'
        if not binary.exists():
            binary = Path('/usr/lib/mseries-ai/llama/bin/llama-server')
        env['LD_LIBRARY_PATH'] = str(binary.parent)
        command = [str(binary),
                   '-m', profile['model'], '-ngl', '99', '-c', str(profile['context']),
                   '-np', '1', '-t', '2', '-b', '256', '-ub', '128',
                   '--jinja', '--alias', 'local-coder', '--host', '127.0.0.1', '--port', str(profile['port'])]
    child = subprocess.Popen(command, env=env, start_new_session=True)
    stopping = False
    cooling = False
    cooling_since = 0
    burst_until = 0

    def group_signal(sig):
        try:
            os.killpg(child.pid, sig)
        except ProcessLookupError:
            pass

    def stop(_sig=None, _frame=None):
        nonlocal stopping
        stopping = True
        if child.poll() is None:
            group_signal(signal.SIGCONT)
            child.terminate()

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    consecutive = 0
    try:
        while child.poll() is None and not stopping:
            measured = snapshot()
            reasons = violations(measured, policy)
            consecutive = consecutive + 1 if reasons else 0
            if consecutive >= 3:
                print('QUIET POLICY STOP: ' + '; '.join(reasons), flush=True)
                stop()
                break
            now = time.monotonic()
            action = cooling_action(measured, cooling, policy, now - cooling_since)
            if not cooling and burst_until:
                action = 'pause' if now >= burst_until else None
            if action == 'pause':
                group_signal(signal.SIGSTOP)
                cooling = True
                cooling_since = now
                burst_until = 0
                print('QUIET COOLING: pausing owned model submissions', flush=True)
            elif action in ('resume', 'burst'):
                group_signal(signal.SIGCONT)
                cooling = False
                burst_until = now + policy.get('burst_s', 6) if action == 'burst' else 0
                print('QUIET COOLING: resuming owned model' + (' for a bounded burst' if burst_until else ''), flush=True)
            time.sleep(policy.get('sample_s', 3))
    finally:
        if child.poll() is None:
            stop()
            try:
                child.wait(timeout=20)
            except subprocess.TimeoutExpired:
                group_signal(signal.SIGKILL)
                child.wait()
    return 0 if stopping else child.returncode


if __name__ == '__main__':
    sys.exit(main())
