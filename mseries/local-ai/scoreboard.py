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
    'serve-120k': ('mlx-omarchy-serve, mlx-lm backend (HTTP server; runs the everyday model)', 'MLX_OMARCHY_BATCH_WORK=120000', None),
    'tensorfold': ('TensorFold Vulkan PR 1517 (HTTP server)', 'serve --backend vulkan --context 1024 --no-thinking', None),
}
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


def measured_rows():
    gates = gate_results()
    latest = {}
    for f in sorted(RECEIPTS.glob('*engine-compare-*.json')):
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
            'status': 'measured here', 'source': f'receipts/{f.name}', '_model': model, '_conc': conc})
    # Most functional per model and length: fastest decode among rows whose output matched
    # and whose gate did not fail.
    for key in {(x['_model'], x['tokens'], x['_conc']) for x in rows}:
        group = [x for x in rows if (x['_model'], x['tokens'], x['_conc']) == key and x['gate'] != 'FAIL'
                 and x['same_output'].startswith(('yes', 'reference')) and x['decode_tok_s']]
        if group:
            max(group, key=lambda x: x['decode_tok_s'])['best'] = '★'
    return rows


def chart(rows):
    """Plain SVG bar chart of decode tok/s, one block per (model, tokens); no plotting deps."""
    groups = {}
    for x in sorted(rows, key=lambda x: (x['_model'], x['tokens'], x['_conc'], -(x['decode_tok_s'] or 0))):
        groups.setdefault((x['model'], x['tokens'], x['_conc']), []).append(x)
    top = max((x['decode_tok_s'] or 0 for x in rows), default=1)
    w, label_w, bar_w, row_h = 760, 300, 380, 22
    y = 30; parts = []
    for (model, tokens, conc), xs in groups.items():
        head = f'{model}, {tokens} tokens' + (f', {conc} requests at once (total)' if conc > 1 else '')
        parts.append(f'<text x="8" y="{y}" class="h">{head}</text>'); y += 10
        for x in xs:
            v = x['decode_tok_s'] or 0; bw = max(2, bar_w * v / top)
            cls = 'best' if x.get('best') else 'bar'
            name = x['engine'].split(' (')[0].split(',')[0] + (' tuned' if '120000' in x['settings'] else ' default' if 'defaults' in x['settings'] else '')
            name += ' · ' + x['driver'].split()[-1][:6]
            parts.append(f'<text x="8" y="{y + 15}" class="l">{name}</text>'
                         f'<rect x="{label_w}" y="{y + 3}" width="{bw:.1f}" height="{row_h - 6}" class="{cls}"/>'
                         f'<text x="{label_w + bw + 6:.1f}" y="{y + 15}" class="v">{v:.1f} tok/s{" ★" if x.get("best") else ""}</text>')
            y += row_h
        y += 18
    style = ('<style>text{font:13px sans-serif;fill:#1f2933}.h{font-weight:600}.v{fill:#52606d}'
             '.bar{fill:#9fb3c8}.best{fill:#2f6fde}@media (prefers-color-scheme:dark){text{fill:#e4e7eb}.v{fill:#cbd2d9}'
             '.bar{fill:#52606d}.best{fill:#5b9bf8}}</style>')
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{y}" viewBox="0 0 {w} {y}">'
            f'<title>Decode speed by engine on Apple M1 Pro</title>{style}{"".join(parts)}</svg>\n')


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
          'One table for every engine we run or watch on the M1 Pro. ★ marks the most functional setup per model and '
          'length: the fastest decode whose output matched every other engine and whose correctness gate did not fail. '
          'Regenerate with `python3 mseries/local-ai/scoreboard.py` after adding a receipt. Tracked in the '
          '"Local AI engine scoreboard" issue.', '',
          '![Decode speed by engine](engine-scoreboard.svg)', '',
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
           '(mlx-lm `94cdcae`, used by its oMLX packaging) is tested as a separate engine, not adopted as our default.', '',
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
