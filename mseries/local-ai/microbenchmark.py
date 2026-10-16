#!/usr/bin/python3
"""Run runtime-native microbenchmarks with the same GPU lock and quiet/memory guard."""
import argparse
import fcntl
import json
import os
from pathlib import Path
import signal
import subprocess
import time

from machine import GIB, snapshot, violations


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('profile', choices=['everyday', 'compact', 'coder7', 'liquid', 'bonsai'])
    p.add_argument('--prompt', type=int, choices=[512, 4096], default=512)
    p.add_argument('--output', required=True, type=Path)
    args = p.parse_args()
    home = Path.home()
    config = json.loads((home / '.config/mseries-ai/profiles.json').read_text())
    profile = config['profiles'][args.profile]
    state = home / '.local/state/mseries-ai'; state.mkdir(parents=True, exist_ok=True)
    lock = (state / 'worker.lock').open('a')
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    policy = config['policy']
    refusal = violations(snapshot(), policy, int(profile['admission_gib'] * GIB))
    if refusal:
        raise SystemExit('Admission refused: ' + '; '.join(refusal))
    prefix = home / '.local/share/mlx-omarchy'
    if not prefix.exists(): prefix = Path('/usr/lib/omarchy-mlx')
    env = dict(os.environ, OMP_NUM_THREADS='2', OPENBLAS_NUM_THREADS='2', HF_HUB_OFFLINE='1',
               HF_HUB_DISABLE_TELEMETRY='1', OMARCHY_MLX_SYSTEM_PREFIX=str(prefix),
               VK_DRIVER_FILES=str(prefix / 'vulkan/honeykrisp_icd.aarch64.json'))
    if profile['engine'] == 'mlx':
        pins = {'compact': 'models--mlx-community--Qwen3-4B-Instruct-2507-4bit/snapshots/50d427756c6b1b2fe0c0a10f67fbda1fc8e82c1b',
                'everyday': 'models--mlx-community--Qwen3.5-9B-MLX-4bit/snapshots/938d8919941c6e7efd3c7150eff7fe9d12afa631'}
        model = str(home / '.cache/huggingface/hub' / pins[args.profile])
        command = [str(prefix / 'venv/bin/python'), '-m', 'mlx_lm.benchmark', '--model', model,
                   '-p', str(args.prompt), '-g', '128', '-n', '3', '--prefill-step-size', '256', '--delay', '15']
    else:
        binary = home / '.local/share/mseries-ai/llama/bin/llama-bench'
        if not binary.exists(): binary = Path('/usr/lib/mseries-ai/llama/bin/llama-bench')
        env['LD_LIBRARY_PATH'] = str(binary.parent)
        command = [str(binary), '-m', profile['model'], '-ngl', '99', '-t', '2', '-b', '256', '-ub', '128',
                   '-p', str(args.prompt), '-n', '128', '-r', '3', '--delay', '15', '-o', 'json']
    args.output.parent.mkdir(parents=True, exist_ok=True)
    report = {'profile': args.profile, 'command': command, 'policy': policy,
              'method': 'Runtime-native benchmark, 3 trials, 15-second cooling delay; MLX decode follows prompt, llama tg starts at its native default context. Do not treat these as identical cross-runtime workloads.',
              'samples': []}
    log = args.output.with_suffix('.log')
    started = time.monotonic()
    with log.open('w') as output:
        child = subprocess.Popen(['nice', '-n', '10'] + command, env=env, stdout=output, stderr=subprocess.STDOUT, start_new_session=True)
        def interrupted(_sig, _frame):
            raise KeyboardInterrupt
        signal.signal(signal.SIGTERM, interrupted)
        count = 0
        try:
            while child.poll() is None:
                sample = snapshot(); report['samples'].append(sample)
                reasons = violations(sample, policy)
                count = count + 1 if reasons else 0
                if count >= 3 or time.monotonic() - started > 1200:
                    report['stopped'] = reasons or ['20-minute limit']
                    os.killpg(child.pid, signal.SIGTERM)
                    break
                time.sleep(3)
        except KeyboardInterrupt:
            report['stopped'] = ['Interrupted by operator']
        finally:
            if child.poll() is None:
                os.killpg(child.pid, signal.SIGTERM)
            try: child.wait(timeout=20)
            except subprocess.TimeoutExpired:
                os.killpg(child.pid, signal.SIGKILL); child.wait()
            report['exit_code'] = child.returncode
            report['elapsed_s'] = time.monotonic() - started
            args.output.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({k: report[k] for k in ['profile', 'exit_code', 'elapsed_s']}))


if __name__ == '__main__':
    main()
