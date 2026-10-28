#!/usr/bin/env python3
"""Rebuild the local AI engine scoreboard from committed receipts.

Reads receipts/*engine-compare-*.json (engine-compare.py), receipts/*mlx-gate-sweep*.json
(mlx-gate.py) and scoreboard-notes.json (rows measured elsewhere or reported by others),
then writes engine-scoreboard.csv and ENGINE-SCOREBOARD.md next to this script.
The newest receipt wins for each (model, engine, length). Run it after every new receipt.
"""
import csv, json, statistics
from pathlib import Path

HERE = Path(__file__).resolve().parent
RECEIPTS = HERE / 'receipts'
ARM_SETTINGS = {
    'mlx-5k': ('MLX (omarchy-mlx, in-process)', 'defaults (MLX_OMARCHY_BATCH_WORK fallback 5000)', 'baseline'),
    'mlx-120k': ('MLX (omarchy-mlx, in-process)', 'MLX_OMARCHY_BATCH_WORK=120000', 'work120k'),
    'rapid-120k': ('Rapid-MLX 1d09cdb (HTTP server)', 'MLX_OMARCHY_BATCH_WORK=120000', None),
    'serve-120k': ('mlx-omarchy-serve, mlx-lm backend, stock (HTTP server)', 'MLX_OMARCHY_BATCH_WORK=120000', None),
    'serve-nolp-120k': ('mlx-omarchy-serve + skip-logprob-read patch only (HTTP server)', 'MLX_OMARCHY_BATCH_WORK=120000', None),
    'serve-single-120k': ('experiment: serve-nolp-120k + Rapid-MLX singleton module loaded from its checkout', 'MLX_OMARCHY_BATCH_WORK=120000', None),
    'serve-patched-120k': ('mlx-omarchy-serve + our four server patches + batching of 4 (HTTP server; runs the everyday model)', 'MLX_OMARCHY_BATCH_WORK=120000', None),
    'tensorfold': ('TensorFold Vulkan (HTTP server)', 'serve --backend vulkan --context 1024 --no-thinking', None),
}
# Receipts record the TensorFold revision they ran; name the PR it came from.
TF_PRS = {'670902196c47f3e70e3f56ab933805713be31aa8': 'PR 1517', '92bb49db5c313c105cbf4b44638d1e1896615174': 'PR 1544'}
MODEL_NAMES = {'qwen2b': 'Qwen3.5-2B MLX 4-bit', 'qwen4b': 'Qwen3.5-4B MLX 4-bit', 'lfm3': 'LFM3-1.7B MLX 8-bit'}
FIELDS = ['best', 'model', 'engine', 'settings', 'tokens', 'decode_tok_s', 'ttft_s', 'total_s', 'runs',
          'same_output', 'gate', 'kernel', 'driver', 'date', 'status', 'source']


def med(xs):
    xs = [x for x in xs if x is not None]
    return statistics.median(xs) if xs else None


def fmt(x, nd=2):
    return '' if x is None else (f'{x:.{nd}f}' if isinstance(x, float) else str(x))


def gate_results():
    """config name -> (gate verdict, receipt) for each model, newest sweep wins."""
    out = {}
    for f in sorted(RECEIPTS.glob('*mlx-gate-sweep*.json')):
        r = json.loads(f.read_text())
        key = 'qwen2b' if '2B' in r.get('model', '') else r.get('model_key', '?')
        drv = r.get('driver', 'Honeykrisp Mesa 7faf04c065')
        for name, row in r.get('configs', {}).items():
            out[(key, drv, name)] = (row.get('gate'), f.name)
    return out


SHORT = {'mlx-5k': 'MLX in-process, default', 'mlx-120k': 'MLX in-process, tuned',
         'rapid-120k': 'Rapid-MLX server', 'serve-120k': 'Upstream server, stock',
         'serve-nolp-120k': 'Upstream server + logprob patch', 'serve-single-120k': 'Upstream + singleton (trial)',
         'serve-patched-120k': 'Upstream server, patched (ships)', 'tensorfold': 'TensorFold Vulkan'}
REPLY_TOKENS = 200


def reply_s(x):
    """What a person waits for a typical answer: first token plus REPLY_TOKENS more."""
    if not x['ttft_s'] or not x['decode_tok_s']:
        return None
    per = x['decode_tok_s'] / x['_conc']  # concurrent rows report the total; one reply streams at its share
    return x['ttft_s'] + REPLY_TOKENS / per


def measured_rows():
    gates = gate_results()
    latest = {}
    for f in sorted(RECEIPTS.glob('*engine-compare-*.json'), key=lambda f: f.stem):  # stem: '-round2' sorts after its base
        r = json.loads(f.read_text())
        if r.get('status') != 'complete':
            continue
        model = r.get('model_key', 'qwen2b')
        drv = r.get('driver', 'Honeykrisp Mesa 7faf04c065')
        conc = r.get('concurrency', 1)
        for arm in r['arms']:
            latest[(model, arm, r['max_tokens'], drv, conc)] = (f, r)
    rows = []
    for (model, arm, tokens, drv, conc), (f, r) in sorted(latest.items()):
        ok = [x for x in r['runs'] if x['arm'] == arm and 'text' in x and not x.get('error')]
        if not ok:
            continue
        texts = {x['text_sha256'] for x in ok}
        base = {x['text_sha256'] for x in r['runs'] if x['arm'] == 'mlx-5k' and 'text_sha256' in x}
        if arm == 'mlx-5k':
            same = 'reference'
        elif not base:
            every = {x['text_sha256'] for x in r['runs'] if 'text_sha256' in x}
            same = 'yes (engines in this run agree)' if len(every) == 1 else 'n/a (no MLX default in this run)'
        elif texts == base:
            same = 'yes'
        else:
            mt = next(x['text'] for x in r['runs'] if x['arm'] == 'mlx-5k' and 'text' in x)
            at = ok[0]['text']
            i = next((i for i, (u, v) in enumerate(zip(mt, at)) if u != v), min(len(mt), len(at)))
            same = f'no: diverges after {i} of {len(mt)} chars'
        engine, settings, gate_key = ARM_SETTINGS[arm]
        if arm == 'tensorfold':
            rev = r.get('tensorfold_rev', '')
            engine = engine.replace('Vulkan', 'Vulkan ' + TF_PRS.get(rev, rev[:10] or 'unknown rev'))
        if conc > 1:
            settings += f' · {conc} requests at once (decode = total tok/s)'
        gate = gates.get((model, drv, gate_key), (None, None))[0] if gate_key else None
        rows.append({
            'model': MODEL_NAMES.get(model, model), 'engine': engine, 'settings': settings, 'tokens': tokens,
            'decode_tok_s': med([x.get('decode_tps') for x in ok]), 'ttft_s': med([x['ttft_s'] for x in ok]),
            'total_s': med([x['total_s'] for x in ok]), 'runs': len(ok),
            'same_output': same if len(texts) == 1 else f'{same}; {len(texts)} variants across its own runs',
            'gate': gate or 'not gated', 'kernel': r.get('kernel', ''),
            'driver': drv, 'date': f.name[:10],
            'status': 'measured here', 'source': f'receipts/{f.name}', '_model': model, '_conc': conc, '_arm': arm})
    # Most functional per model, length and load: the shortest typical reply (first token plus
    # REPLY_TOKENS at its streaming speed) among rows whose output matched and whose gate did not fail.
    for key in {(x['_model'], x['tokens'], x['_conc']) for x in rows}:
        group = [x for x in rows if (x['_model'], x['tokens'], x['_conc']) == key and x['gate'] != 'FAIL'
                 and x['same_output'].startswith(('yes', 'reference')) and x['decode_tok_s']]
        if group:
            min(group, key=lambda x: reply_s(x) or 1e9)['best'] = '★'
    return rows


def chart(rows):
    """Small multiples, no plotting deps: per (model, length, load) block, one row per engine and three
    panels on their own scales - first token (lower is better), streaming speed (higher is better) and the
    wait for a typical reply. Two measures never share an axis. Blue is the best value in its panel;
    ★ by a name is the block's shortest typical reply among rows that matched and passed the gate."""
    groups = {}
    for x in sorted(rows, key=lambda x: (x['_model'], x['tokens'], x['_conc'], reply_s(x) or 1e9)):
        groups.setdefault((x['model'], x['tokens'], x['_conc']), []).append(x)
    label_w, panel_w, gap, row_h = 250, 190, 34, 22
    w = label_w + 3 * (panel_w + gap)
    panels = [('First token, s · lower is better', lambda x: x['ttft_s'], '{:.2f} s'),
              ('Streaming, tok/s · higher is better', lambda x: x['decode_tok_s'], '{:.1f}'),
              (f'Typical reply ({REPLY_TOKENS} tokens), s · lower', reply_s, '{:.1f} s')]
    y = 24; parts = []
    for (model, tokens, conc), xs in groups.items():
        head = f'{model} · {tokens}-token test' + (f' · {conc} requests at once (streaming = total)' if conc > 1 else ' · one request')
        parts.append(f'<text x="8" y="{y}" class="h">{head}</text>'); y += 8
        for i, (title, _, _) in enumerate(panels):
            parts.append(f'<text x="{label_w + i * (panel_w + gap)}" y="{y + 12}" class="a">{title}</text>')
        y += 18
        tops, bests = [], []
        for _, f, _ in panels:
            vals = sorted(v for v in (f(x) for x in xs) if v)
            # Cap at 3x the median so one very slow engine does not flatten the rest; clipped bars end in '›'.
            tops.append(min(vals[-1], 3 * vals[len(vals) // 2]) if vals else 1)
            bests.append(None)
        for i, (title, f, _) in enumerate(panels):
            vals = [f(x) for x in xs if f(x)]
            if vals:
                bests[i] = max(vals) if 'higher' in title else min(vals)
        base_y = y
        for x in xs:
            arm = x['_arm']
            name = SHORT.get(arm, arm) + (' · old driver' if '7faf' in x['driver'] else '')
            weight = ' class="l s"' if arm == 'serve-patched-120k' else ' class="l"'
            parts.append(f'<text x="8" y="{y + 14}"{weight}>{name}{" ★" if x.get("best") else ""}</text>')
            for i, (title, f, fmt_) in enumerate(panels):
                v = f(x); x0 = label_w + i * (panel_w + gap)
                if v is None:
                    parts.append(f'<text x="{x0}" y="{y + 14}" class="v">n/a</text>'); continue
                clipped = v > tops[i]
                bw = max(2, (panel_w - 52) * min(v, tops[i]) / tops[i])
                cls = 'best' if v == bests[i] else 'bar'
                tip = f'{name}: {title.split(" ·")[0]} {fmt_.format(v)}'
                parts.append(f'<g><title>{tip}</title><rect x="{x0}" y="{y + 3}" width="{bw:.1f}" height="{row_h - 8}" rx="2" class="{cls}"/>'
                             f'<text x="{x0 + bw + 5:.1f}" y="{y + 14}" class="v">{"› " if clipped else ""}{fmt_.format(v)}</text></g>')
            y += row_h
        for i in range(3):
            x0 = label_w + i * (panel_w + gap)
            parts.append(f'<line x1="{x0}" y1="{base_y}" x2="{x0}" y2="{y}" class="axis"/>')
        y += 22
    style = ('<style>svg{background:#fcfcfb}text{font:13px system-ui,sans-serif;fill:#0b0b0b}.h{font-weight:600}'
             '.a{font-size:11px;fill:#52514e}.v{fill:#52514e;font-size:12px}.s{font-weight:600}'
             '.bar{fill:#a3a29b}.best{fill:#2a78d6}.axis{stroke:#c3c2b7;stroke-width:1}'
             '@media (prefers-color-scheme:dark){svg{background:#1a1a19}text{fill:#f0efec}.a,.v{fill:#c3c2b7}'
             '.bar{fill:#6b6a64}.best{fill:#3987e5}.axis{stroke:#52514e}}</style>')
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{y}" viewBox="0 0 {w} {y}">'
            f'<title>First token, streaming speed and reply time by engine on Apple M1 Pro</title>'
            f'<rect width="100%" height="100%" class="bg" fill="none"/>{style}{"".join(parts)}</svg>\n')


def main():
    rows = measured_rows()
    notes = json.loads((HERE / 'scoreboard-notes.json').read_text())['rows']
    with (HERE / 'engine-scoreboard.csv').open('w', newline='') as fh:
        w = csv.DictWriter(fh, fieldnames=FIELDS + ['blocker'], extrasaction='ignore')
        w.writeheader()
        for x in rows:
            w.writerow({k: (fmt(v) if isinstance(v, float) else v) for k, v in x.items()})
        for n in notes:
            w.writerow({**n, 'best': ''})
    md = ['# Local AI engine scoreboard', '',
          'One table for every engine we run or watch on the M1 Pro. ★ marks the most functional setup per model, length and load: the shortest typical reply '
          '(first token plus 200 tokens) whose output matched every other engine and whose correctness gate did not fail. '
          'Regenerate with `python3 mseries/local-ai/scoreboard.py` after adding a receipt. Tracked in the '
          '"Local AI engine scoreboard" issue.', '',
          '![First token, streaming speed and typical reply time by engine](engine-scoreboard.svg)', '',
          f'Each block is one model and load; each panel has its own scale. **First token** is the wait before text '
          f'appears, **streaming** is decode speed after that, and **typical reply** is first token plus {REPLY_TOKENS} '
          'tokens at that speed (for several requests at once, one request\'s share). Blue is the best value in each '
          'panel; a bar ending in › is clipped at three times the block\'s median.', '',
          '## Measured on this machine', '',
          '| ★ | Model | Engine | Settings | Tokens | Decode tok/s | TTFT s | Total s | Runs | Same output as MLX default | Gate | Kernel | Driver | Date | Receipt |',
          '|---|---|---|---|---:|---:|---:|---:|---:|---|---|---|---|---|---|']
    for x in sorted(rows, key=lambda x: (x['_model'], x['tokens'], -(x['decode_tok_s'] or 0))):
        b = '**' if x.get('best') else ''
        md.append(f"| {x.get('best', '')} | {x['model']} | {b}{x['engine']}{b} | `{x['settings']}` | {x['tokens']} | "
                  f"{b}{fmt(x['decode_tok_s'])}{b} | {fmt(x['ttft_s'])} | {fmt(x['total_s'])} | {x['runs']} | {x['same_output']} | "
                  f"{x['gate']} | `{x['kernel']}` | {x['driver']} | {x['date']} | [{Path(x['source']).name}]({x['source'].replace('receipts/', 'receipts/')}) |")
    md += ['', '## Watched or reported elsewhere (not comparable to the table above)', '',
           '| Model | Engine | Settings | Decode | Status | Blocker | Source |', '|---|---|---|---|---|---|---|']
    for n in notes:
        md.append(f"| {n['model']} | {n['engine']} | {n['settings']} | {n['decode_tok_s']} | {n['status']} | {n['blocker']} | {n['source']} |")
    md += ['', '## How we track upstream', '',
           'The engines above move fast, so this page is a living record on `dev`, not a one-off report.', '',
           '1. **Watch.** `people-watch.json` and `branch-watch.json` list the people and repos we follow '
           '(Joshua Warren\'s omarchy-mlx, metal2vk, omarchy-cluster, ane-linux-experiments, TensorFold and its fork). '
           '`github-watch.py` runs every 6 hours (`.github/workflows/upstream-watch.yml`) and keeps one '
           '"Upstream watch" issue listing unacknowledged pushes, branches and PRs.',
           '2. **Triage.** For each flagged change, decide whether it can affect a row here (new engine, runtime pin bump, '
           'kernel or driver change). Record that decision on the scoreboard tracking issue.',
           '3. **Re-test.** Build it in a private prefix (never system-wide), run its own gates first '
           '(`tensorfold-vulkan.sh test` / `gpu`, `mlx-gate.py sweep`), then `engine-compare.py` with the same '
           'models, prompts and guards.',
           '4. **Publish.** Commit the new receipt JSON, run `scoreboard.py`, and open a PR to `dev` with the regenerated '
           'CSV, SVG and this page. Rows are replaced by the newest receipt; old receipts stay for history.',
           '5. **Adopt.** A setting becomes our default only when it holds ★ *and* passes the MLX gate; '
           'change defaults in a separate PR.',
           '6. **Version steps follow upstream.** We move mlx-lm (now 0.31.3) and the omarchy-mlx pin (now v0.7.33, '
           '`33630f9c`) only when omarchy-mlx moves its own `install.sh` default or cuts a release. Its 0.32 line '
           '(mlx-lm `94cdcae`, used by its oMLX packaging) is tested as a separate engine, not adopted as our default. `install-omlx.sh` installs oMLX that way (its own venv under `~/.local/share/omlx-linux`) for engine-compare\'s `omlx-120k` arm.', '',
           'Rules: everything is documented in our own repo only; we do not post to upstream projects. '
           'Rows under "reported elsewhere" are other people\'s numbers on other hardware and are never ranked against ours.', '',
           '## Reproduce', '',
           '- Kernel `7.2.11-elementary-aurora72-wip4` (techmore/ElementaryOS_MSeries-Kernel), Apple M1 Pro 32 GB.',
           '- GPU driver: private Honeykrisp ICD shipped by omarchy-mlx, selected per process only: '
           '`VK_DRIVER_FILES=$HOME/.local/share/mlx-omarchy/vulkan/honeykrisp_icd.aarch64.json`. Desktop Mesa is untouched.',
           '- Guards on every run: shared worker lock, 6 GiB desktop memory reserve, 80 °C limit, one engine at a time.',
           '- Same prompt, greedy decoding, no thinking; each run is a fresh process with one warmup, three rotated rounds.',
           '- MLX rows time in-process; server rows time a streamed loopback HTTP request. Compare like with like.', '',
           '```bash',
           'cd mseries/local-ai',
           'python3 engine-compare.py --model qwen2b            # 32 tokens; add --long for 256',
           'python3 engine-compare.py --model qwen4b --admission-wait-seconds 1800',
           'python3 engine-compare.py --model lfm3',
           'python3 mlx-gate.py reference && python3 mlx-gate.py sweep',
           './tensorfold-vulkan.sh build && ./tensorfold-vulkan.sh gpu',
           'python3 scoreboard.py',
           '```', '']
    (HERE / 'engine-scoreboard.svg').write_text(chart(rows))
    (HERE / 'ENGINE-SCOREBOARD.md').write_text('\n'.join(md))
    print(f'{len(rows)} measured rows, {len(notes)} noted rows')


if __name__ == '__main__':
    main()
