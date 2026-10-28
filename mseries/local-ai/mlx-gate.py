#!/usr/bin/env python3
"""TensorFold-style correctness gate and tuning sweep for MLX on the M1 Pro.

Modeled on the gates TensorFold PR 1517 applies to its own Vulkan engine:
fail-closed finite checks, teacher-forced logits against an independent
reference, token-ID parity, and pre-declared non-inferiority margins.

Reference: the same pinned Qwen3.5-2B 4-bit checkpoint on MLX's *CPU* backend,
float parameters cast to float32. It shares the weights but not the GPU code
path, so it catches GPU kernel errors.

Pass rules, fixed before any candidate was measured (do not loosen after the fact):
  R1  every teacher-forced logit is finite;
  R2  teacher-forced argmax equals the reference argmax on every row whose
      reference top-1/top-2 margin is at least TIE_MARGIN (near-ties exempt);
  R3  pooled RMSE vs reference <= 1.05 x the baseline's, and every case <= 1.15 x
      (TensorFold's adopted non-inferiority margins);
  R4  free-running greedy IDs equal the baseline's, or first diverge at a row
      the reference marks as a near-tie.
The baseline (installed defaults) must pass R1 and R2 itself; R3/R4 are relative to it.

  mlx-gate.py reference            build and cache the CPU reference (once, slow)
  mlx-gate.py sweep [--configs ..] gate + time each config, baseline first
"""
import argparse, fcntl, hashlib, json, os, subprocess, sys, tempfile, time
from pathlib import Path

from machine import GIB, snapshot, violations

HOME = Path.home()
HERE = Path(__file__).resolve().parent
MODEL = HOME / '.cache/mseries-metal2vk/qwen35-2b'
WEIGHTS_SHA = '713fe7e5d3c3965f7106b0d0ee17615f7869c23c8d327996df8c1196fbcf07d5'
ICD = HOME / '.local/share/mlx-omarchy/vulkan/honeykrisp_icd.aarch64.json'
MLX_PY = HOME / '.local/share/mlx-omarchy/venv/bin/python'
REF_DIR = HOME / '.cache/mseries-mlx-gate/reference-v1'
POLICY = {'reserve_gib': 6, 'max_fan_rpm': float('inf'), 'max_temp_c': 80}
ALLOWANCE_GIB = 4.5
STEPS = 32
TIE_MARGIN = 0.5
POOLED_MARGIN, CASE_MARGIN = 1.05, 1.15

# Varied lengths and content, after TensorFold's 1-65 token prompt set.
CASES = {
    'rainbow': 'Explain in plain language how a rainbow forms. Give four distinct sentences.',
    'single': 'Hi',
    'unicode': 'Traduis en français et en japonais : « The weather is lovely today, isn’t it? » 🌦️',
    'code': 'Write a Python function that returns the n-th Fibonacci number iteratively, with a docstring and two doctests.',
    'prose': ('Summarize the following in two sentences. The committee met on Tuesday to review the '
              'budget for the new library wing. After a long discussion about costs, staffing and the '
              'construction timeline, members agreed to delay the vote until an independent estimate '
              'arrives next month.'),
    'math': 'A train leaves at 3:40 pm and travels 210 km at 84 km/h. At what time does it arrive? Show the steps.',
}

# Each config is env overrides on top of the installed defaults. Scheduling-only
# switches are documented upstream as bit-identical; SDPA_BF16_FAST is documented
# as changing token IDs on M1 and acts as the gate's negative control.
CONFIGS = {
    'baseline': {},
    'work20k': {'MLX_OMARCHY_BATCH_WORK': '20000'},
    'work80k': {'MLX_OMARCHY_BATCH_WORK': '80000'},
    'work120k': {'MLX_OMARCHY_BATCH_WORK': '120000'},
    'work-uncapped': {'MLX_OMARCHY_BATCH_WORK': '0'},
    'work120k-nodes8k': {'MLX_OMARCHY_BATCH_WORK': '120000', 'MLX_OMARCHY_BATCH_NODES': '8192'},
    'work120k-first64': {'MLX_OMARCHY_BATCH_WORK': '120000', 'MLX_OMARCHY_BATCH_FIRST': '64'},
    'work120k-wave': {'MLX_OMARCHY_BATCH_WORK': '120000', 'MLX_OMARCHY_WAVE_SCHED': '1'},
    'work120k-prio': {'MLX_OMARCHY_BATCH_WORK': '120000', 'MLX_OMARCHY_QUEUE_PRIORITY': 'medium'},
    'neg-sdpa-bf16-fast': {'MLX_OMARCHY_BATCH_WORK': '120000', 'MLX_OMARCHY_SDPA_BF16_FAST': '1'},
}


# ---------------------------------------------------------------- worker side (mlx venv)

def load(cpu):
    import mlx.core as mx
    from mlx_lm import load as mlx_load
    if cpu:
        mx.set_default_device(mx.cpu)
    model, tok = mlx_load(str(MODEL))
    if cpu:
        model.set_dtype(mx.float32)
    return mx, model, tok


def prompt_ids(tok, text):
    s = tok.apply_chat_template([{'role': 'user', 'content': text}], tokenize=False,
                                add_generation_prompt=True, enable_thinking=False)
    return tok.encode(s, add_special_tokens=False)


def greedy(mx, model, ids, steps):
    from mlx_lm.models.cache import make_prompt_cache
    cache = make_prompt_cache(model)
    logits = model(mx.array(ids)[None], cache=cache)[:, -1, :]
    out = []
    t0 = None
    for i in range(steps):
        nxt = int(mx.argmax(logits, axis=-1).item())
        if i == 0:
            t0 = time.monotonic()
        out.append(nxt)
        logits = model(mx.array([[nxt]]), cache=cache)[:, -1, :]
    mx.eval(logits)
    decode_s = time.monotonic() - t0
    return out, decode_s


def teacher_forced(mx, model, ids, gen):
    """Logits for the rows that predict each generated token (len(gen) rows)."""
    seq = ids + gen[:-1]
    logits = model(mx.array(seq)[None])[0, len(ids) - 1:, :].astype(mx.float32)
    mx.eval(logits)
    import numpy as np
    return np.array(logits)


def worker(mode, out_dir):
    import numpy as np
    cpu = mode == 'reference'
    mx, model, tok = load(cpu)
    out_dir = Path(out_dir); out_dir.mkdir(parents=True, exist_ok=True)
    meta = {}
    ref = None if cpu else json.loads((REF_DIR / 'meta.json').read_text())
    for name, text in CASES.items():
        ids = prompt_ids(tok, text)
        if not cpu:
            greedy(mx, model, ids, 4)  # warm the kernels for this shape
        gen, decode_s = greedy(mx, model, ids, STEPS)
        forced = ref['cases'][name]['ids'] if ref else gen
        logits = teacher_forced(mx, model, ids, forced)
        np.save(out_dir / f'{name}.npy', logits)
        meta[name] = {'prompt_tokens': len(ids), 'ids': gen, 'decode_s': decode_s,
                      'prompt_sha256': hashlib.sha256(json.dumps(ids).encode()).hexdigest()}
    (out_dir / 'meta.json').write_text(json.dumps({'cases': meta}, indent=1))


# ---------------------------------------------------------------- driver side

def run_child(mode, out_dir, env_over, deadline):
    env = {k: v for k, v in os.environ.items() if not k.startswith('MLX_OMARCHY_')}
    env.update(VK_DRIVER_FILES=str(ICD), HF_HUB_OFFLINE='1', OMP_NUM_THREADS='4', **env_over)
    log = tempfile.TemporaryFile(mode='w+t')
    child = subprocess.Popen([str(MLX_PY), __file__, '--worker', mode, '--out', str(out_dir)],
                             env=env, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
    start = time.monotonic(); bad = 0; stopped = None; low = None; hot = 0
    try:
        while child.poll() is None:
            s = snapshot(); r = violations(s, POLICY)
            low = min(low or 1e9, s['available_bytes'] / GIB); hot = max(hot, max(s['temperatures_c'].values(), default=0))
            bad = bad + 1 if r else 0
            if bad >= 3 or time.monotonic() - start > deadline:
                stopped = r or ['deadline']; os.killpg(child.pid, 15); break
            time.sleep(1)
        child.wait(timeout=20)
    finally:
        if child.poll() is None:
            os.killpg(child.pid, 9); child.wait()
    log.seek(0); tail = log.read()[-3000:]
    return {'exit': child.returncode, 'stopped': stopped, 'seconds': round(time.monotonic() - start, 1),
            'min_available_gib': round(low or 0, 2), 'peak_temp_c': hot, 'log_tail': tail}


def admit(wait_s):
    end = time.monotonic() + wait_s
    while True:
        r = violations(snapshot(), POLICY, extra_bytes=int(ALLOWANCE_GIB * GIB))
        if not r:
            return
        if time.monotonic() > end:
            raise SystemExit('Admission refused: ' + '; '.join(r))
        print('waiting for admission: ' + '; '.join(r), flush=True); time.sleep(10)


def score(cand_dir, ref, base=None):
    import numpy as np
    meta = json.loads((cand_dir / 'meta.json').read_text())['cases']
    out = {'cases': {}, 'violations': []}
    se_sum = 0.0; n_sum = 0
    for name in CASES:
        r = np.load(REF_DIR / f'{name}.npy'); c = np.load(cand_dir / f'{name}.npy')
        if not np.isfinite(c).all():
            out['violations'].append(f'R1 {name}: non-finite logits')
        top2 = np.sort(r, axis=1)[:, -2:]; margin = top2[:, 1] - top2[:, 0]
        ra, ca = r.argmax(1), c.argmax(1)
        flips = [int(i) for i in np.nonzero((ra != ca) & (margin >= TIE_MARGIN))[0]]
        if flips:
            out['violations'].append(f'R2 {name}: argmax differs at non-tie rows {flips}')
        err = (c.astype(np.float64) - r) ** 2
        rmse = float(np.sqrt(err.mean())); se_sum += float(err.sum()); n_sum += err.size
        ids, ref_ids = meta[name]['ids'], ref['cases'][name]['ids']
        div = next((i for i, (a, b) in enumerate(zip(ids, ref_ids)) if a != b), None)
        out['cases'][name] = {'rmse': rmse, 'argmax_agree': float((ra == ca).mean()), 'non_tie_flips': flips,
                              'ids': ids, 'first_divergence_vs_reference': div,
                              'decode_tok_s': (STEPS - 1) / meta[name]['decode_s']}
    out['pooled_rmse'] = (se_sum / n_sum) ** 0.5
    out['median_decode_tok_s'] = sorted(c['decode_tok_s'] for c in out['cases'].values())[len(CASES) // 2]
    if base:
        if out['pooled_rmse'] > POOLED_MARGIN * base['pooled_rmse']:
            out['violations'].append(f"R3 pooled RMSE {out['pooled_rmse']:.4g} > {POOLED_MARGIN} x baseline {base['pooled_rmse']:.4g}")
        for name, c in out['cases'].items():
            b = base['cases'][name]
            if c['rmse'] > CASE_MARGIN * b['rmse']:
                out['violations'].append(f"R3 {name}: RMSE {c['rmse']:.4g} > {CASE_MARGIN} x baseline {b['rmse']:.4g}")
            div = next((i for i, (x, y) in enumerate(zip(c['ids'], b['ids'])) if x != y), None)
            c['first_divergence_vs_baseline'] = div
            if div is not None:
                r = np.load(REF_DIR / f'{name}.npy'); t = np.sort(r[div])[-2:]
                if t[1] - t[0] >= TIE_MARGIN:
                    out['violations'].append(f'R4 {name}: greedy IDs diverge from baseline at non-tie step {div}')
    out['pass'] = not out['violations']
    return out


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--worker'); p.add_argument('--out')
    p.add_argument('mode', nargs='?', choices=['reference', 'sweep'])
    p.add_argument('--configs', default=','.join(CONFIGS))
    p.add_argument('--admission-wait-seconds', type=int, default=0)
    p.add_argument('--output', type=Path)
    a = p.parse_args()
    if a.worker:
        return worker(a.worker, a.out)
    if not a.mode:
        p.error('mode required')
    with (MODEL / 'model.safetensors').open('rb') as f:
        if hashlib.file_digest(f, 'sha256').hexdigest() != WEIGHTS_SHA:
            raise SystemExit('Qwen weights do not match the pinned checkpoint')
    lock = (HOME / '.local/state/mseries-ai/worker.lock').open('a')
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    if a.mode == 'reference':
        admit(a.admission_wait_seconds)
        tmp = REF_DIR.with_name(REF_DIR.name + '.partial')
        res = run_child('reference', tmp, {}, 3600)
        if res['exit'] != 0 or res['stopped']:
            print(json.dumps(res, indent=1)); raise SystemExit('reference build failed')
        tmp.rename(REF_DIR)
        print(f"reference written to {REF_DIR} in {res['seconds']} s")
        return
    if not (REF_DIR / 'meta.json').exists():
        raise SystemExit('no reference: run `mlx-gate.py reference` first')
    ref = json.loads((REF_DIR / 'meta.json').read_text())
    names = [c for c in a.configs.split(',') if c]
    if 'baseline' in names:
        names.remove('baseline')
    names.insert(0, 'baseline')
    out = a.output or HERE / 'receipts' / f"{time.strftime('%Y-%m-%d')}-mlx-gate-sweep.json"
    report = {'model': 'mlx-community/Qwen3.5-2B-MLX-4bit@93760be4', 'weights_sha256': WEIGHTS_SHA,
              'kernel': os.uname().release, 'steps': STEPS, 'tie_margin': TIE_MARGIN,
              'margins': {'pooled': POOLED_MARGIN, 'case': CASE_MARGIN}, 'cases': list(CASES), 'configs': {}}
    base = None
    with tempfile.TemporaryDirectory(prefix='mlx-gate-', dir=HOME / '.cache') as tmp:
        for name in names:
            admit(a.admission_wait_seconds)
            d = Path(tmp) / name
            res = run_child('candidate', d, CONFIGS[name], 900)
            row = {'env': CONFIGS[name], **{k: v for k, v in res.items() if k != 'log_tail'}}
            if res['exit'] != 0 or res['stopped']:
                row.update(gate='ERROR', log_tail=res['log_tail'])
            else:
                row.update(score(d, ref, base))
                row['gate'] = 'PASS' if row['pass'] else 'FAIL'
                if name == 'baseline':
                    if not row['pass']:
                        print('baseline fails R1/R2 against the CPU reference; stopping'); report['configs'][name] = row; break
                    base = row
            report['configs'][name] = row
            out.write_text(json.dumps(report, indent=1) + '\n')
            print(f"{name:20s} {row['gate']:5s} decode {row.get('median_decode_tok_s', 0):6.2f} tok/s  "
                  f"pooled-RMSE {row.get('pooled_rmse', float('nan')):.4g}  {'; '.join(row.get('violations', []))[:160]}", flush=True)
    lock.close()


if __name__ == '__main__':
    main()
