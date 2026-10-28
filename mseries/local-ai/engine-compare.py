#!/usr/bin/env python3
"""Guarded, rotated comparison of local engines on one Qwen3.5-2B checkpoint.

Arms (each a fresh process: load, one warmup on the same prompt, one measured request):
  mlx-5k      installed omarchy-mlx, default 5,000 work-group submit budget (baseline)
  mlx-120k    same runtime at last night's best 120,000 budget
  rapid-120k  Rapid-MLX loopback server at the 120,000 budget
  tensorfold  TensorFold native Vulkan server (ashhart/TensorFold PR 1517)

All four use the same weights, chat prompt, greedy decoding and token limit,
the shared worker lock, the 6 GiB desktop reserve and the 80 C limit. MLX arms
time in-process; server arms time a streamed loopback HTTP request. Those
boundaries differ, so compare servers with servers and MLX with MLX first.
"""
import argparse, fcntl, hashlib, json, os, signal, socket, subprocess, sys, tempfile, threading, time
import urllib.request, urllib.error
from pathlib import Path

from machine import GIB, snapshot, violations

HOME = Path.home()
# name: (dir, weights sha256, id@revision, admission GiB, MLX python, arms it can run)
MODELS = {
    'qwen2b': (HOME / '.cache/mseries-metal2vk/qwen35-2b',
               '713fe7e5d3c3965f7106b0d0ee17615f7869c23c8d327996df8c1196fbcf07d5',
               'mlx-community/Qwen3.5-2B-MLX-4bit@93760be4f1f69842a46bc13dbdc0f19e291392a3', 4.5,
               HOME / '.local/share/mlx-omarchy/venv/bin/python', ('mlx-5k', 'mlx-120k', 'rapid-120k', 'serve-120k', 'tensorfold')),
    'qwen4b': (HOME / '.cache/huggingface/hub/models--mlx-community--Qwen3.5-4B-MLX-4bit/snapshots/32f3e8ecf65426fc3306969496342d504bfa13f3',
               '5fb9acd0246866381cf8c5c354c6db1019f6498eec4ccb4f5edcc71ffeacb2db',
               'mlx-community/Qwen3.5-4B-MLX-4bit@32f3e8ecf65426fc3306969496342d504bfa13f3', 6.5,
               HOME / '.local/share/mlx-omarchy/venv/bin/python', ('mlx-5k', 'mlx-120k', 'rapid-120k', 'serve-120k')),
    'lfm3': (HOME / '.cache/mseries-metal2vk/lfm3-8bit',
             '2b06cea98d75527c248a0b04383f7cf0a1c72fb4ed7b45096618fc4e59d015ad',
             'LiquidAI/LFM3-1.7B-MLX-8bit@ee7667f3cfccb2a41725f91820531823fcabc6b7', 4.5,
             HOME / '.local/share/mlx-omarchy/venv/bin/python', ('mlx-5k', 'mlx-120k')),
}
MODEL, WEIGHTS_SHA, MODEL_ID, ALLOWANCE_GIB, MLX_PY, MODEL_ARMS = MODELS['qwen2b']
# MSERIES_HK_ICD selects a candidate driver built by honeykrisp-candidate.sh.
ICD = Path(os.environ.get('MSERIES_HK_ICD') or HOME / '.local/share/mlx-omarchy/vulkan/honeykrisp_icd.aarch64.json')
DRIVER = (ICD.parent / 'mesa-git-sha').read_text().strip() if (ICD.parent / 'mesa-git-sha').exists() else 'unknown'
RAPID_PATH = f"{HOME}/.cache/mseries-metal2vk/rapid-python:{HOME}/.cache/mseries-metal2vk/rapid-src"
RAPID_REV = '1d09cdb684bbf58fac130f5804b08ee2e1f56558'
TF_BIN = HOME / '.cache/mseries-tensorfold/src/zig-out/native/bin/tensorfold-native-vulkan'
TF_REV = '670902196c47f3e70e3f56ab933805713be31aa8'
PROMPT = 'Explain in plain language how a rainbow forms. Give four distinct sentences.'
LONG_PROMPT = ('Explain in detail how a rainbow forms, including refraction, reflection, color '
               'and viewing angle. Write at least 350 words.')
ARMS = ('mlx-5k', 'mlx-120k', 'rapid-120k', 'serve-120k', 'tensorfold')
SERVE = HOME / '.local/bin/mlx-omarchy-serve'  # what model-worker.py runs for the everyday model
CONCURRENCY = 1
POLICY = {'reserve_gib': 6, 'max_fan_rpm': float('inf'), 'max_temp_c': 80}
DEADLINE_S = 300
MODEL_NAME = 'qwen2b'
LFM3_MODULE_SHA = 'a4096cddc8f0d3f7923008b2e6afb896dabc9aef963a5ebe7d76d13a6069b0c4'


def select_model(name):
    global MODEL, WEIGHTS_SHA, MODEL_ID, ALLOWANCE_GIB, MLX_PY, MODEL_ARMS
    MODEL, WEIGHTS_SHA, MODEL_ID, ALLOWANCE_GIB, MLX_PY, MODEL_ARMS = MODELS[name]


def mlx_worker(prompt_text, max_tokens, output):
    """Runs inside the mlx-omarchy venv: load, warm up, time one greedy generation."""
    t0 = time.monotonic()
    if MODEL_NAME == 'lfm3':
        # mlx-lm 0.31.3 has no LFM3; load the pinned model file from mlx-lm PR 2016
        # (head 9027ac5b), as the 2026-10-27 LFM3 smoke test did.
        import hashlib as _h, importlib.util as _u
        f = HOME / '.local/share/mseries-ai/runtime/lfm3.py'
        if _h.sha256(f.read_bytes()).hexdigest() != LFM3_MODULE_SHA:
            raise SystemExit('unexpected lfm3.py')
        spec = _u.spec_from_file_location('mlx_lm.models.lfm3', f)
        mod = _u.module_from_spec(spec); sys.modules[spec.name] = mod; spec.loader.exec_module(mod)
    from mlx_lm import load, stream_generate
    from mlx_lm.sample_utils import make_sampler
    import mlx.core as mx
    model, tok = load(str(MODEL))
    prompt = tok.apply_chat_template([{'role': 'user', 'content': prompt_text}], tokenize=False,
                                     add_generation_prompt=True, enable_thinking=False)
    for _ in stream_generate(model, tok, prompt, max_tokens=max_tokens, sampler=make_sampler(temp=0)):
        pass
    mx.synchronize()
    ready = time.monotonic() - t0
    start = time.monotonic(); first = None; tokens = []; text = ''
    for r in stream_generate(model, tok, prompt, max_tokens=max_tokens, sampler=make_sampler(temp=0)):
        if first is None:
            first = time.monotonic() - start
        tokens.append(r.token); text += r.text
    mx.synchronize()
    output.write_text(json.dumps({'ready_s': ready, 'ttft_s': first, 'total_s': time.monotonic() - start,
                                  'completion_tokens': len(tokens), 'text': text}))


def served_model(port):
    with urllib.request.urlopen(f'http://127.0.0.1:{port}/v1/models', timeout=10) as r:
        return json.load(r)['data'][0]['id']


def stream_chat(port, prompt_text, max_tokens, model):
    payload = {'model': model, 'messages': [{'role': 'user', 'content': prompt_text}],
               'max_tokens': max_tokens, 'temperature': 0, 'stream': True,
               'stream_options': {'include_usage': True},
               'chat_template_kwargs': {'enable_thinking': False}}
    req = urllib.request.Request(f'http://127.0.0.1:{port}/v1/chat/completions',
                                 data=json.dumps(payload).encode(), headers={'Content-Type': 'application/json'})
    start = time.monotonic(); first = None; text = ''; deltas = 0; usage = None
    with urllib.request.urlopen(req, timeout=DEADLINE_S) as r:
        for raw in r:
            line = raw.decode().strip()
            if not line.startswith('data:'):
                continue
            body = line[5:].strip()
            if body == '[DONE]':
                break
            event = json.loads(body)
            usage = event.get('usage') or usage
            for choice in event.get('choices') or []:
                piece = (choice.get('delta') or {}).get('content') or ''
                if piece:
                    if first is None:
                        first = time.monotonic() - start
                    text += piece; deltas += 1
    total = time.monotonic() - start
    count = (usage or {}).get('completion_tokens') or deltas
    return {'ttft_s': first, 'total_s': total, 'completion_tokens': count,
            'token_count_source': 'usage' if usage else 'stream deltas', 'text': text}


def concurrent_chat(port, prompt_text, max_tokens, model):
    """CONCURRENCY streamed requests at once. Each gets its own prefix so no prompt cache
    can serve one request from another; the aggregate is all tokens over the shared wall time."""
    results = [None] * CONCURRENCY
    def one(i):
        try:
            results[i] = stream_chat(port, f'Request {i + 1} of {CONCURRENCY}. ' + prompt_text, max_tokens, model)
        except Exception as exc:
            results[i] = {'error': f'{type(exc).__name__}: {exc}'}
    threads = [threading.Thread(target=one, args=(i,)) for i in range(CONCURRENCY)]
    start = time.monotonic()
    for t in threads: t.start()
    for t in threads: t.join()
    wall = time.monotonic() - start
    bad = [r for r in results if not r or 'error' in r]
    if bad:
        raise RuntimeError(f'{len(bad)} of {CONCURRENCY} concurrent requests failed: {bad[0]}')
    tokens = sum(r['completion_tokens'] for r in results)
    per = sorted((r['completion_tokens'] - 1) / (r['total_s'] - r['ttft_s']) for r in results
                 if r['ttft_s'] is not None and r['total_s'] > r['ttft_s'] and r['completion_tokens'] > 1)
    return {'concurrency': CONCURRENCY, 'wall_s': wall, 'aggregate_tok_s': tokens / wall,
            'per_request_decode_median': per[len(per) // 2] if per else None,
            'ttft_s': sorted(r['ttft_s'] for r in results)[len(results) // 2], 'total_s': wall,
            'completion_tokens': tokens, 'text': results[0]['text'], 'requests': results}


def server_command(arm, port):
    if arm == 'serve-120k':
        gib = sum(f.stat().st_size for f in MODEL.glob('*.safetensors')) / GIB
        return [str(SERVE), 'serve', str(MODEL), '--server', 'mlx-lm', '--context', '4096',
                '--weights-gib', f'{gib:.2f}', '--host', '127.0.0.1', '--port', str(port), '--offline', '--yes']
    if arm == 'tensorfold':
        return [str(TF_BIN), 'serve', str(MODEL), '--backend', 'vulkan', '--host', '127.0.0.1',
                '--port', str(port), '--context', '1024', '--no-thinking', '--no-update-check']
    return [str(MLX_PY), '-m', 'rapid_mlx.server', '--model', str(MODEL), '--no-mllm',
            '--host', '127.0.0.1', '--port', str(port)]


def env_for(arm, tmp):
    env = {k: v for k, v in os.environ.items() if not k.startswith('MLX_OMARCHY_')}
    env.update(VK_DRIVER_FILES=str(ICD), HF_HUB_OFFLINE='1', OMP_NUM_THREADS='2', OPENBLAS_NUM_THREADS='2')
    if arm != 'tensorfold':
        env['MLX_OMARCHY_BATCH_WORK'] = '5000' if arm == 'mlx-5k' else '120000'
    if arm == 'rapid-120k':
        env.update(PYTHONPATH=RAPID_PATH, RAPID_MLX_TELEMETRY='0', DO_NOT_TRACK='1',
                   RAPID_MLX_PREFIX_CACHE_AUTOLOAD='0', XDG_CONFIG_HOME=f'{tmp}/config',
                   XDG_CACHE_HOME=f'{tmp}/cache', XDG_STATE_HOME=f'{tmp}/state')
    return env


def run_arm(arm, prompt_text, max_tokens, tmp):
    """One fresh process for `arm` under the resource guard; returns its row."""
    started = time.monotonic(); outcome = {}
    log = tempfile.TemporaryFile(mode='w+t', dir=tmp)
    if arm.startswith('mlx'):
        out = Path(tmp) / f'{arm}.json'
        cmd = [str(MLX_PY), __file__, '--worker', '--model', MODEL_NAME, '--max-tokens', str(max_tokens),
               '--prompt', prompt_text, '--worker-output', str(out)]
    else:
        with socket.socket() as s:
            s.bind(('127.0.0.1', 0)); port = s.getsockname()[1]
        cmd = server_command(arm, port)
    child = subprocess.Popen(cmd, env=env_for(arm, tmp), stdout=log, stderr=subprocess.STDOUT,
                             start_new_session=True, cwd=tmp)

    def drive():
        try:
            while True:
                if child.poll() is not None:
                    raise RuntimeError(f'server exited during startup ({child.returncode})')
                if time.monotonic() - started > 180:
                    raise RuntimeError('server readiness timeout')
                ready = False
                for path in ('/health', '/healthz', '/v1/models'):
                    try:
                        with urllib.request.urlopen(f'http://127.0.0.1:{port}{path}', timeout=2):
                            ready = True; break
                    except (OSError, urllib.error.HTTPError):
                        pass
                if ready:
                    break
                time.sleep(0.5)
            model = served_model(port)
            stream_chat(port, prompt_text, max_tokens, model)  # warmup on the same prompt
            outcome['ready_s'] = time.monotonic() - started
            if CONCURRENCY == 1:
                outcome.update(stream_chat(port, prompt_text, max_tokens, model), served_model=model)
            else:
                outcome.update(concurrent_chat(port, prompt_text, max_tokens, model), served_model=model)
        except Exception as exc:
            outcome['error'] = f'{type(exc).__name__}: {exc}'

    driver = None if arm.startswith('mlx') else threading.Thread(target=drive, daemon=True)
    if driver:
        driver.start()
    samples = []; bad = 0; stopped = None
    try:
        while (driver.is_alive() if driver else child.poll() is None):
            s = snapshot()
            samples.append({'t': round(time.monotonic() - started, 2), 'available_gib': round(s['available_bytes'] / GIB, 3),
                            'max_temp_c': max(s['temperatures_c'].values(), default=0),
                            'max_fan_rpm': max(s['fans_rpm'].values(), default=0)})
            reasons = violations(s, POLICY); bad = bad + 1 if reasons else 0
            if bad >= 3 or time.monotonic() - started > DEADLINE_S:
                stopped = reasons or ['deadline']; break
            if driver:
                driver.join(1)
            else:
                time.sleep(1)
    finally:
        if child.poll() is None:
            os.killpg(child.pid, signal.SIGTERM)
            try:
                child.wait(timeout=15)
            except subprocess.TimeoutExpired:
                os.killpg(child.pid, signal.SIGKILL); child.wait()
        if driver:
            driver.join(timeout=5)
    if arm.startswith('mlx') and not stopped:
        if child.returncode == 0 and out.exists():
            outcome.update(json.loads(out.read_text()))
        else:
            outcome['error'] = f'worker exit {child.returncode}'
    log.seek(0); tail = log.read()[-4000:]; log.close()
    row = {'arm': arm, 'stopped': stopped, 'samples': samples, 'log_tail': tail, **outcome}
    if 'text' in row:
        row['text_sha256'] = hashlib.sha256(row['text'].encode()).hexdigest()
        n, ttft, total = row['completion_tokens'], row['ttft_s'], row['total_s']
        row['decode_tps'] = (row['aggregate_tok_s'] if 'aggregate_tok_s' in row else
                             (n - 1) / (total - ttft) if n > 1 and ttft is not None and total > ttft else None)
    row['min_available_gib'] = min((x['available_gib'] for x in samples), default=None)
    row['peak_temp_c'] = max((x['max_temp_c'] for x in samples), default=None)
    return row


def admit(wait_s):
    deadline = time.monotonic() + wait_s
    while True:
        s = snapshot(); reasons = violations(s, POLICY, extra_bytes=int(ALLOWANCE_GIB * GIB))
        if not reasons:
            return s
        if time.monotonic() >= deadline:
            raise RuntimeError('Admission refused: ' + '; '.join(reasons))
        print('waiting for admission: ' + '; '.join(reasons), flush=True)
        time.sleep(10)


def median(xs):
    xs = sorted(x for x in xs if x is not None)
    return None if not xs else (xs[len(xs) // 2] if len(xs) % 2 else (xs[len(xs) // 2 - 1] + xs[len(xs) // 2]) / 2)


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--worker', action='store_true', help=argparse.SUPPRESS)
    p.add_argument('--worker-output', type=Path, help=argparse.SUPPRESS)
    p.add_argument('--prompt', help=argparse.SUPPRESS)
    p.add_argument('--model', choices=list(MODELS), default='qwen2b')
    p.add_argument('--max-tokens', type=int, default=32)
    p.add_argument('--long', action='store_true', help='256 tokens from the long-form prompt')
    p.add_argument('--rounds', type=int, default=3)
    p.add_argument('--concurrency', type=int, default=1, help='server arms only: requests at once')
    p.add_argument('--arms', default=','.join(ARMS))
    p.add_argument('--admission-wait-seconds', type=int, default=0)
    p.add_argument('--output', type=Path)
    a = p.parse_args()
    global MODEL_NAME, CONCURRENCY
    MODEL_NAME = a.model
    CONCURRENCY = a.concurrency
    select_model(a.model)
    if a.worker:
        return mlx_worker(a.prompt, a.max_tokens, a.worker_output)
    arms = [x for x in a.arms.split(',') if x and x in MODEL_ARMS and not (CONCURRENCY > 1 and x.startswith('mlx'))]
    if not arms:
        p.error(f'no runnable arms for {a.model}; it supports {",".join(MODEL_ARMS)}')
    prompt_text, max_tokens = (LONG_PROMPT, 256) if a.long else (PROMPT, a.max_tokens)
    global DEADLINE_S
    if a.long:
        DEADLINE_S = 600  # TensorFold's unbatched decode needs ~100 s per 256-token request
    with (MODEL / 'model.safetensors').open('rb') as f:
        if hashlib.file_digest(f, 'sha256').hexdigest() != WEIGHTS_SHA:
            raise SystemExit('Qwen weights do not match the pinned checkpoint')
    if 'tensorfold' in arms and not TF_BIN.exists():
        raise SystemExit('TensorFold server missing: run tensorfold-vulkan.sh build')
    out = a.output or Path(__file__).resolve().parent / 'receipts' / (
        f"{time.strftime('%Y-%m-%d')}-engine-compare-{a.model}-{'long' if a.long else 'short'}"
        + ('' if DRIVER == '7faf04c065' else f'-hk{DRIVER}') + (f'-c{CONCURRENCY}' if CONCURRENCY > 1 else '')
        + ('' if tuple(arms) == tuple(x for x in MODEL_ARMS if x != 'serve-120k') else '-' + '+'.join(arms)) + '.json')
    lock = (HOME / '.local/state/mseries-ai/worker.lock').open('a')
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    report = {'status': 'running', 'model_key': a.model, 'model': MODEL_ID, 'weights_sha256': WEIGHTS_SHA, 'kernel': os.uname().release, 'driver': 'Honeykrisp Mesa ' + DRIVER,
              'tensorfold_rev': TF_REV, 'rapid_rev': RAPID_REV, 'prompt_sha256': hashlib.sha256(prompt_text.encode()).hexdigest(),
              'max_tokens': max_tokens, 'policy': {**POLICY, 'max_fan_rpm': None}, 'allowance_gib': ALLOWANCE_GIB,
              'arms': arms, 'concurrency': CONCURRENCY, 'runs': []}
    try:
        with tempfile.TemporaryDirectory(prefix='engine-compare-', dir=HOME / '.cache') as tmp:
            for r in range(a.rounds):
                order = arms[r % len(arms):] + arms[:r % len(arms)]  # rotate so no arm always goes first
                for arm in order:
                    s = admit(a.admission_wait_seconds)
                    row = run_arm(arm, prompt_text, max_tokens, tmp)
                    row.update(round=r + 1, admission_available_gib=round(s['available_bytes'] / GIB, 3))
                    report['runs'].append(row)
                    out.parent.mkdir(parents=True, exist_ok=True)
                    out.write_text(json.dumps(report, indent=2) + '\n')
                    if row.get('error') or row.get('stopped'):
                        print(f"round {r + 1} {arm}: FAILED {row.get('error') or row.get('stopped')}", flush=True)
                        print(row['log_tail'][-1500:], flush=True)
                    else:
                        print(f"round {r + 1} {arm}: ttft {row['ttft_s']:.3f}s total {row['total_s']:.3f}s "
                              f"{row['completion_tokens']} tok {row['decode_tps'] or 0:.2f} tok/s", flush=True)
                    time.sleep(3)
        report['status'] = 'complete'
    except BaseException as exc:
        report['status'] = 'interrupted'; report['error'] = str(exc); raise
    finally:
        summary = {}
        for arm in arms:
            ok = [x for x in report['runs'] if x['arm'] == arm and 'text' in x and not x.get('error')]
            summary[arm] = {'ok_runs': len(ok), 'median_ttft_s': median([x['ttft_s'] for x in ok]),
                            'median_total_s': median([x['total_s'] for x in ok]),
                            'median_decode_tps': median([x['decode_tps'] for x in ok]),
                            'texts': sorted({x['text_sha256'][:12] for x in ok})}
        report['summary'] = summary
        out.write_text(json.dumps(report, indent=2) + '\n'); lock.close()
        print(json.dumps(summary, indent=2))


if __name__ == '__main__':
    main()
