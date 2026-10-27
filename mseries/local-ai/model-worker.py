#!/usr/bin/python3
"""Supervise only our inference child, preserving desktop memory and quiet limits."""
import argparse
import fcntl
import json
import math
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

from machine import DEFAULT_POLICY, GIB, snapshot, violations, cooling_action, runtime_prefix


def load_config(path, home):
    standard = home / '.config/mseries-ai/profiles.json'
    selected = standard if path is None else path
    config = json.loads(selected.read_text())
    if selected != standard and standard.is_file():
        # An isolated profile must still honor stricter owner-wide limits.
        baseline = dict(DEFAULT_POLICY)
        baseline.update(json.loads(standard.read_text()).get('policy', {}))
        for key, value in config.get('policy', {}).items():
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
                raise ValueError('Invalid isolated quiet policy: ' + key)
            baseline[key] = max(6, baseline.get(key, 6), value) if key == 'reserve_gib' else min(baseline.get(key, value), value)
        config['policy'] = baseline
    return config


def profile_policy(config, profile, name):
    """Profile overrides can tighten resource limits, never relax global ones."""
    policy = dict(DEFAULT_POLICY)
    policy.update(config.get('policy', {}))
    override = profile.get('policy', {})
    for key, value in override.items():
        if key not in {'reserve_gib', 'max_fan_rpm', 'max_temp_c', 'cool_fan_rpm',
                       'resume_fan_rpm', 'cool_temp_c', 'resume_temp_c', 'sample_s',
                       'admission_fan_rpm', 'admission_temp_c', 'stop_after_samples'}:
            raise ValueError('Unsupported per-profile policy: ' + key)
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
            raise ValueError('Invalid per-profile quiet policy: ' + key)
        if key == 'reserve_gib':
            policy[key] = max(6, policy.get(key, 6), value)
        else:
            policy[key] = min(policy.get(key, value), value)
    policy['reserve_gib'] = max(6, policy.get('reserve_gib', 6))
    if name == 'diagnostic':
        # Dedicated diagnosis always has a strict first-sample stop. A custom
        # config cannot weaken these ceilings or the six-GiB desktop reserve.
        for key, ceiling in {'max_fan_rpm': 2700, 'max_temp_c': 63,
                             'cool_fan_rpm': 2600, 'resume_fan_rpm': 2520,
                             'cool_temp_c': 58, 'resume_temp_c': 55,
                             'admission_fan_rpm': 2600, 'admission_temp_c': 58,
                             'sample_s': 1, 'stop_after_samples': 1}.items():
            policy[key] = min(policy.get(key, ceiling), ceiling)
    return policy


def policy_violations(sample, policy, extra_bytes=0, *, admission=False, strict=False):
    reasons = violations(sample, policy, extra_bytes)
    if strict or admission:
        fan_limit = policy.get('admission_fan_rpm', policy['max_fan_rpm']) if admission else policy['max_fan_rpm']
        temp_limit = policy.get('admission_temp_c', policy['max_temp_c']) if admission else policy['max_temp_c']
        if max(sample['fans_rpm'].values(), default=0) >= fan_limit:
            reasons.append('fan RPM reached the diagnostic quiet limit')
        if max(sample['temperatures_c'].values(), default=0) >= temp_limit:
            reasons.append('temperature reached the diagnostic quiet limit')
    return list(dict.fromkeys(reasons))


def diagnostic_speech_busy():
    """Dictation wins priority; absence of a verifiable idle state fails closed."""
    try:
        from diagnostic_runtime import speech_idle
        return not speech_idle()
    except (OSError, ValueError, ImportError, subprocess.SubprocessError):
        return True


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('profile', choices=['everyday', 'quality', 'coder9', 'compact', 'personal', 'coder', 'coder7', 'coder-large', 'liquid', 'bonsai', 'compact35', 'diagnostic'])
    parser.add_argument('--config', type=Path, help='Read a separate profile file; never rewrite global assistant settings')
    args = parser.parse_args()
    home = Path.home()
    config = load_config(args.config, home)
    lock_dir = home / '.local/state/mseries-ai'
    lock_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    lock = (lock_dir / 'worker.lock').open('a')
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        print('ADMISSION REFUSED: another managed model is running', flush=True)
        return 3
    profile = config['profiles'][args.profile]
    policy = profile_policy(config, profile, args.profile)
    initial = snapshot()
    reasons = policy_violations(initial, policy, int(max(9, profile['admission_gib']) * GIB) if args.profile == 'diagnostic' else int(profile['admission_gib'] * GIB),
                                admission=args.profile == 'diagnostic')
    if reasons:
        print('ADMISSION REFUSED: ' + '; '.join(reasons), flush=True)
        return 3
    if args.profile == 'diagnostic' and diagnostic_speech_busy():
        print('ADMISSION REFUSED: F5 priority; speech is busy or idle state is unavailable', flush=True)
        return 3
    baseline = max(initial['fans_rpm'].values())
    policy.setdefault('cool_fan_rpm', min(baseline + 300, policy['max_fan_rpm'] - 200))
    policy.setdefault('resume_fan_rpm', min(baseline + 100, policy['cool_fan_rpm'] - 100))
    print(f"QUIET POLICY: baseline {baseline:.0f} RPM; pause {policy['cool_fan_rpm']:.0f}; resume {policy['resume_fan_rpm']:.0f}; hard stop {policy['max_fan_rpm']}", flush=True)
    env = dict(os.environ, OMP_NUM_THREADS='2', OPENBLAS_NUM_THREADS='2',
               HF_HUB_OFFLINE='1', TRANSFORMERS_OFFLINE='1', HF_HUB_DISABLE_TELEMETRY='1')
    prefix = runtime_prefix(home)
    env['OMARCHY_MLX_SYSTEM_PREFIX'] = str(prefix)
    env['VK_DRIVER_FILES'] = str(prefix / 'vulkan/honeykrisp_icd.aarch64.json')
    if profile['engine'] == 'mlx':
        from runtime_recovery import recover
        recovered = recover(prefix)
        if recovered: print(f'RECOVERY: removed {recovered} dead CLI reservations; reserve unchanged', flush=True)
        launcher = home / '.local/bin/mlx-omarchy-serve' if prefix == home / '.local/share/mlx-omarchy' else Path('/usr/bin/mlx-omarchy-serve')
        command = [str(launcher), 'serve', profile['model'],
                   '--context', str(profile['context']), '--prompt-cache-size', str(profile.get('prompt_cache_size', 1)),
                   '--host', '127.0.0.1', '--port', str(profile['port']), '--offline', '--yes']
        if 'weights_gib' in profile:
            command += ['--weights-gib', str(profile['weights_gib'])]
    else:
        driver = prefix / 'vulkan/honeykrisp_icd.aarch64.json'
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
        if stopping:
            return  # Repeated SIGTERM must not interrupt the CLI's reservation cleanup.
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
            reasons = policy_violations(measured, policy, strict=args.profile == 'diagnostic')
            if args.profile == 'diagnostic' and diagnostic_speech_busy():
                print('QUIET POLICY STOP: F5 priority; diagnostic inference interrupted (unscored)', flush=True)
                stop()
                break
            consecutive = consecutive + 1 if reasons else 0
            if consecutive >= policy.get('stop_after_samples', 3):
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
                child.wait(timeout=30)
            except subprocess.TimeoutExpired:
                group_signal(signal.SIGKILL)
                child.wait()
    return 0 if stopping else child.returncode


if __name__ == '__main__':
    sys.exit(main())
