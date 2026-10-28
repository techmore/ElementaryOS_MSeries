#!/usr/bin/env python3
"""Short isolated MLX model smoke, using the shared worker lock and resource guard."""
import argparse
import fcntl
import importlib.util
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

from machine import GIB, snapshot, violations


def worker(args):
    if args.lfm3_module:
        spec = importlib.util.spec_from_file_location('mlx_lm.models.lfm3', args.lfm3_module)
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
    from mlx_lm import load, generate
    start = time.monotonic()
    model, tokenizer = load(str(args.model))
    print('LOAD_SECONDS', round(time.monotonic() - start, 2), flush=True)
    prompt = tokenizer.apply_chat_template(
        [{'role': 'user', 'content': 'What is 12 plus 7? Reply with the number only.'}],
        tokenize=False, add_generation_prompt=True, enable_thinking=False)
    answer = generate(model, tokenizer, prompt=prompt, max_tokens=24, verbose=False)
    print('RESPONSE', answer, flush=True)
    if answer.strip() != '19':
        raise SystemExit('Unexpected answer; investigate rather than treating as a pass')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--model', required=True, type=Path)
    parser.add_argument('--admission-gib', required=True, type=float,
                        help='Model-specific memory allowance, in addition to the 6 GiB desktop reserve')
    parser.add_argument('--lfm3-module', type=Path)
    parser.add_argument('--allow-fan-above-3500', action='store_true',
                        help='Only when the owner explicitly authorizes more fan noise')
    parser.add_argument('--worker', action='store_true', help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.worker:
        worker(args)
        return
    if not 0 < args.admission_gib <= 64:
        raise SystemExit('Admission allowance must be greater than 0 and at most 64 GiB')
    if not args.model.is_dir():
        raise SystemExit('Local model directory not found')
    home = Path.home()
    lock = (home / '.local/state/mseries-ai/worker.lock').open('a')
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    policy = {'reserve_gib': 6, 'max_fan_rpm': float('inf') if args.allow_fan_above_3500 else 3500,
              'max_temp_c': 80}
    initial = snapshot()
    reasons = violations(initial, policy, extra_bytes=int(args.admission_gib * GIB))
    print('ADMISSION_AVAILABLE_GIB', round(initial['available_bytes'] / GIB, 2), 'reasons', reasons, flush=True)
    if reasons:
        raise SystemExit('Admission refused')
    env = os.environ.copy()
    for key in list(env):
        if key.startswith('MLX_OMARCHY_M2V_') or key == 'MLX_OMARCHY_METAL_KERNEL_BACKEND':
            del env[key]
    env.update(VK_DRIVER_FILES=str(home / '.local/share/mlx-omarchy/vulkan/honeykrisp_icd.aarch64.json'),
               MLX_OMARCHY_METAL_KERNEL_BACKEND='auto', MLX_OMARCHY_M2V_SUMMARY='1',
               HF_HUB_OFFLINE='1', OMP_NUM_THREADS='2', OPENBLAS_NUM_THREADS='2')
    command = [str(home / '.local/share/mlx-omarchy/venv/bin/python'), __file__, '--worker', '--model', str(args.model),
               '--admission-gib', str(args.admission_gib)]
    if args.lfm3_module:
        command += ['--lfm3-module', str(args.lfm3_module)]
    child = subprocess.Popen(command, env=env, start_new_session=True)
    started = time.monotonic()
    count = 0
    stopped = None
    try:
        while child.poll() is None:
            reasons = violations(snapshot(), policy)
            count = count + 1 if reasons else 0
            if count >= 3 or time.monotonic() - started > 180:
                stopped = reasons or ['180-second deadline']
                os.killpg(child.pid, signal.SIGTERM)
                break
            time.sleep(1)
        child.wait(timeout=10)
    finally:
        if child.poll() is None:
            os.killpg(child.pid, signal.SIGKILL)
            child.wait()
    print('EXIT', child.returncode, 'ELAPSED_SECONDS', round(time.monotonic() - started, 2), 'STOPPED', stopped, flush=True)
    if child.returncode or stopped:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
