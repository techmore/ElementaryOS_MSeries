#!/usr/bin/env python3
"""Guarded, alternating Qwen Vulkan submission-budget experiment."""
import argparse
import ctypes
import fcntl
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time

from machine import GIB, snapshot, violations

FIELDS = ('gpu_primitive_dispatches', 'vk_submissions', 'vk_buffer_copies',
          'vk_buffer_fills', 'vk_compute_dispatches', 'omarchy_finalize_calls',
          'commit_calls_with_work', 'commit_calls_noop', 'barriers_emitted', 'barriers_skipped')
PROMPT = 'Explain in plain language how a rainbow forms. Give four distinct sentences.'
LONG_PROMPT = 'Explain in detail how a rainbow forms, including refraction, reflection, color and viewing angle. Write at least 350 words.'


def worker(model, output, long_run):
    import mlx.core as mx
    from mlx_lm import load, stream_generate
    from mlx_lm.sample_utils import make_sampler

    class Trace(ctypes.Structure):
        _fields_ = [(name, ctypes.c_uint64) for name in FIELDS]

    lib = ctypes.CDLL(str(Path(mx.__file__).parent / 'lib/libmlx.so'))
    lib.mlx_omarchy_trace_snapshot_abi_size.restype = ctypes.c_uint64
    if lib.mlx_omarchy_trace_snapshot_abi_size() != ctypes.sizeof(Trace):
        raise RuntimeError('Trace ABI mismatch; refusing unsafe snapshot')
    lib.mlx_omarchy_trace_snapshot.argtypes = [ctypes.POINTER(Trace)]
    lib.mlx_omarchy_trace_snapshot.restype = None

    def counters():
        trace = Trace()
        lib.mlx_omarchy_trace_snapshot(ctypes.byref(trace))
        return {key: int(getattr(trace, key)) for key in FIELDS}

    model_obj, tokenizer = load(str(model))
    prompt = tokenizer.apply_chat_template([{'role': 'user', 'content': LONG_PROMPT if long_run else PROMPT}],
                                          tokenize=False, add_generation_prompt=True,
                                          enable_thinking=False)
    # One full warmup on exactly the same prompt; no model cache is shared.
    for _ in stream_generate(model_obj, tokenizer, prompt, max_tokens=32, sampler=make_sampler(temp=0)):
        pass
    mx.synchronize()
    before = counters()
    started = time.monotonic()
    first = None
    tokens = []
    last = None
    for result in stream_generate(model_obj, tokenizer, prompt, max_tokens=256 if long_run else 32, sampler=make_sampler(temp=0)):
        if first is None:
            first = time.monotonic() - started
        tokens.append(result.token)
        last = result
    mx.synchronize()
    elapsed = time.monotonic() - started
    after = counters()
    data = {'first_s': first, 'total_s': elapsed, 'tokens': tokens,
            'prompt_tokens': last.prompt_tokens if last else None,
            'generation_tps': last.generation_tps if last else None,
            'measured_start_monotonic': started, 'measured_end_monotonic': time.monotonic(),
            'counter_delta': {key: after[key] - before[key] for key in FIELDS}}
    output.write_text(json.dumps(data))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--model', type=Path, required=True)
    parser.add_argument('--checkpoint', choices=['qwen2b', 'qwen4b'], default='qwen2b')
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--candidate', type=int, choices=[10000, 20000, 40000, 80000, 120000], default=10000)
    parser.add_argument('--worker', action='store_true')
    parser.add_argument('--desktop-probe', action='store_true')
    parser.add_argument('--long-run', action='store_true', help='Generate up to 256 tokens with a long-form prompt')
    parser.add_argument('--wave-ab', action='store_true', help='Compare wave scheduling off/on at the candidate budget')
    parser.add_argument('--admission-wait-seconds', type=int, default=0, help='Wait up to this long for each guarded admission')
    args = parser.parse_args()
    if not 0 <= args.admission_wait_seconds <= 300:
        parser.error('--admission-wait-seconds must be between 0 and 300')
    if args.worker:
        worker(args.model, args.output, args.long_run)
        return
    checkpoints = {
        'qwen2b': ('713fe7e5d3c3965f7106b0d0ee17615f7869c23c8d327996df8c1196fbcf07d5', 4.5,
                   'mlx-community/Qwen3.5-2B-MLX-4bit@93760be4f1f69842a46bc13dbdc0f19e291392a3'),
        'qwen4b': ('5fb9acd0246866381cf8c5c354c6db1019f6498eec4ccb4f5edcc71ffeacb2db', 6.5,
                   'mlx-community/Qwen3.5-4B-MLX-4bit@32f3e8ecf65426fc3306969496342d504bfa13f3'),
    }
    expected_digest, allowance_gib, model_id = checkpoints[args.checkpoint]
    weights = args.model / 'model.safetensors'
    if not weights.is_file():
        raise SystemExit('Expected pinned Qwen weights are missing')
    with weights.open('rb') as handle:
        digest = hashlib.file_digest(handle, 'sha256').hexdigest()
    if digest != expected_digest:
        raise SystemExit('Qwen weights do not match the selected pinned checkpoint')
    home = Path.home()
    lock = (home / '.local/state/mseries-ai/worker.lock').open('a')
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    policy = {'reserve_gib': 6, 'max_fan_rpm': float('inf'), 'max_temp_c': 80}
    rows = []
    report = {'status': 'running', 'prompt_sha256': hashlib.sha256((LONG_PROMPT if args.long_run else PROMPT).encode()).hexdigest(),
              'model': model_id, 'weights_sha256': digest, 'admission_gib': allowance_gib,
              'sequence': [5000, args.candidate, args.candidate, 5000, 5000, args.candidate],
              'max_tokens': 256 if args.long_run else 32, 'wave_ab': args.wave_ab, 'runs': rows}
    if args.wave_ab:
        report['sequence'] = [args.candidate] * 6
    args.output.parent.mkdir(parents=True, exist_ok=True)
    try:
        with tempfile.TemporaryDirectory(prefix='mseries-batch-work-') as temp:
            for index, budget in enumerate(report['sequence']):
                deadline = time.monotonic() + args.admission_wait_seconds
                while True:
                    initial = snapshot()
                    reasons = violations(initial, policy, extra_bytes=int(allowance_gib * GIB))
                    if not reasons:
                        break
                    if time.monotonic() >= deadline:
                        raise RuntimeError('Admission refused: ' + '; '.join(reasons))
                    print('Waiting for admission: ' + '; '.join(reasons), flush=True)
                    time.sleep(min(5, max(0, deadline - time.monotonic())))
                result = Path(temp) / f'{index}.json'
                env = os.environ.copy()
                for key in list(env):
                    if key.startswith('MLX_OMARCHY_'):
                        del env[key]
                env.update(VK_DRIVER_FILES=str(home / '.local/share/mlx-omarchy/vulkan/honeykrisp_icd.aarch64.json'),
                           MLX_OMARCHY_BATCH_WORK=str(budget), HF_HUB_OFFLINE='1',
                           OMP_NUM_THREADS='2', OPENBLAS_NUM_THREADS='2')
                wave_enabled = args.wave_ab and index in (1, 2, 5)
                if wave_enabled:
                    env['MLX_OMARCHY_WAVE_SCHED'] = '1'
                command = [str(home / '.local/share/mlx-omarchy/venv/bin/python'), __file__, '--worker',
                           '--model', str(args.model), '--output', str(result)]
                if args.long_run:
                    command.append('--long-run')
                probe_file = Path(temp) / f'frames-{index}.json'
                probe = None
                if args.desktop_probe:
                    probe = subprocess.Popen(['/usr/bin/python3', str(Path(__file__).with_name('desktop-frame-probe.py')), str(probe_file)])
                    time.sleep(2)
                with tempfile.TemporaryFile(mode='w+t') as log:
                    try:
                        child = subprocess.Popen(command, env=env, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
                    except BaseException:
                        if probe is not None:
                            probe.terminate()
                            probe.wait(timeout=10)
                        raise
                    started = time.monotonic()
                    bad = 0
                    samples = []
                    stopped = None
                    try:
                        while child.poll() is None:
                            sample = snapshot()
                            samples.append({'available_bytes': sample['available_bytes'],
                                            'max_fan_rpm': max(sample['fans_rpm'].values(), default=0),
                                            'max_temp_c': max(sample['temperatures_c'].values(), default=0)})
                            reasons = violations(sample, policy)
                            bad = bad + 1 if reasons else 0
                            if bad >= 3 or time.monotonic() - started > 180:
                                stopped = reasons or ['timeout']
                                os.killpg(child.pid, signal.SIGTERM)
                                break
                            time.sleep(1)
                        child.wait(timeout=10)
                    finally:
                        if child.poll() is None:
                            os.killpg(child.pid, signal.SIGKILL)
                            child.wait()
                        if probe is not None:
                            probe.terminate()
                            probe.wait(timeout=10)
                    log.seek(0)
                    entry = {'budget': budget, 'wave_enabled': wave_enabled, 'exit': child.returncode, 'stopped': stopped,
                             'admission_available_bytes': initial['available_bytes'], 'samples': samples,
                             'log_tail': log.read()[-1500:]}
                    rows.append(entry)
                    if child.returncode or stopped or not result.exists():
                        raise RuntimeError('Worker did not complete')
                    entry['result'] = json.loads(result.read_text())
                    if args.desktop_probe:
                        if not probe_file.exists() or probe.returncode:
                            raise RuntimeError('Desktop frame probe did not complete')
                        entry['desktop_probe'] = json.loads(probe_file.read_text())
                print(f"run {index + 1} budget {budget}: {entry['result']['total_s']:.3f}s, "
                      f"{entry['result']['counter_delta']['vk_submissions']} submits, wave={wave_enabled}", flush=True)
                time.sleep(2)
        report['status'] = 'complete'
    except BaseException as exc:
        report['status'] = 'interrupted'
        report['error'] = str(exc)
        raise
    finally:
        args.output.write_text(json.dumps(report, indent=2) + '\n')
        lock.close()


if __name__ == '__main__':
    main()
