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

from machine import DEFAULT_POLICY, GIB, snapshot, violations, cooling_action, runtime_prefix


def serve_patch(env, prefix):
    """Put our patched mlx-lm server copy (serve-patch.sh) ahead of the installed one.

    Three private patches on upstream's own launcher: skip the per-token logprob read nobody asked
    for, keep a lone request's KV cache unbatched (Rapid-MLX's singleton fast path), and build the
    detokenizer's vocabulary map once instead of twice per request, and send 2-6 token prompt
    passes through the batched one-row kernel. Qwen 2B 33 -> 56 tok/s and first token
    0.62 -> 0.25 s, identical text. Used only while the installed server.py still matches the
    one the copy was built from; MSERIES_SERVE_PATCH=0 turns it off.
    """
    copy = Path.home() / '.local/share/mseries-ai/serve-patch'
    if env.get('MSERIES_SERVE_PATCH') == '0' or not (copy / 'mlx_lm/server.py').exists():
        return
    import hashlib
    installed = next((prefix / 'venv/lib').glob('python3.*/site-packages/mlx_lm/server.py'), None)
    try:
        stamp = (copy / 'source-server-sha256').read_text().strip()
        current = hashlib.sha256(installed.read_bytes()).hexdigest() if installed else ''
    except OSError:
        stamp, current = 'missing', ''
    if stamp != current:
        print('SERVE PATCH: skipped, installed mlx-lm changed; rerun serve-patch.sh build', flush=True)
        return
    env['PYTHONPATH'] = str(copy) + (':' + env['PYTHONPATH'] if env.get('PYTHONPATH') else '')
    print('SERVE PATCH: skip-logprob-read + singleton cache + small rows + detokenizer map', flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('profile', choices=['everyday', 'quality', 'coder9', 'compact', 'personal', 'coder', 'coder7', 'coder-large', 'liquid', 'bonsai', 'compact35'])
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
        lock.close()
        return 3
    profile = config['profiles'][args.profile]
    policy = dict(config.get('policy', DEFAULT_POLICY))
    initial = snapshot()
    reasons = violations(initial, policy, int(profile['admission_gib'] * GIB))
    if reasons:
        print('ADMISSION REFUSED: ' + '; '.join(reasons), flush=True)
        lock.close()
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
        # The M1 Pro (G13S) is uncalibrated in omarchy-mlx and falls back to a 5000 work-group submit
        # budget. 120k passes the MLX gate with identical output and decodes faster (Qwen 2B 48.9 -> 56.4,
        # Qwen 4B 23.1 -> 27.0 tok/s on Honeykrisp 9323171c12). An explicit value in the environment wins.
        env.setdefault('MLX_OMARCHY_BATCH_WORK', '120000')
        serve_patch(env, prefix)
        # Batch parallel requests (agents, assistant + chat) instead of queueing them; the launcher
        # reserves each extra request's KV at the profile's context before it starts
        # (configure-serve-concurrency.py). 8 parallel requests: first tokens by 1.4-1.8 s, not 5.9 s.
        env.setdefault('MSERIES_SERVE_CONCURRENCY', str(profile.get('concurrency', 4)))
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
    policy_stopped = False
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
            reasons = violations(measured, policy)
            consecutive = consecutive + 1 if reasons else 0
            if consecutive >= 3:
                print('QUIET POLICY STOP: ' + '; '.join(reasons), flush=True)
                policy_stopped = True
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
        lock.close()
    return 3 if policy_stopped else (0 if stopping else child.returncode)


if __name__ == '__main__':
    sys.exit(main())
