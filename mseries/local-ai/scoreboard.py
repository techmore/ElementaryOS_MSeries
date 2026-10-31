#!/usr/bin/env python3
"""Rebuild the local AI engine scoreboard from committed receipts.

Reads receipts/*engine-compare-*.json (engine-compare.py), receipts/*mlx-gate-sweep*.json
(mlx-gate.py) and scoreboard-notes.json (rows measured elsewhere or reported by others),
plus completed macOS scoreboard receipts, then writes CSV, SVG and Markdown next to this script.
The newest receipt wins within each model revision, chip, OS, kernel, engine, driver and workload.
"""
import csv, json, re, statistics
from html import escape
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
TF_PRS = {'670902196c47f3e70e3f56ab933805713be31aa8': 'PR 1517', '92bb49db5c313c105cbf4b44638d1e1896615174': 'PR 1544', 'b3ab9ba217a80c63fcc48f7643ddfe339a8f4bdc': 'PR 1544 b3ab9ba'}
MODEL_NAMES = {'qwen2b': 'Qwen3.5-2B MLX 4-bit', 'qwen4b': 'Qwen3.5-4B MLX 4-bit', 'lfm3': 'LFM3-1.7B MLX 8-bit',
               'granite1b': 'Granite 4.0 1B MLX 4-bit (IBM, dense)'}
FIELDS = ['best', 'chip', 'os', 'model_reference', 'weights_sha1', 'weights_sha256', 'prompt_sha256', 'start_time', 'end_time', 'model', 'engine', 'settings', 'tokens', 'decode_tok_s', 'ttft_s', 'total_s', 'runs',
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


def chip_name(r, historical=False):
    explicit = r.get('chip') or r.get('hardware') or ''
    match = re.search(r'\bM[0-9]+(?:\s+(?:Pro|Max|Ultra))?\b', explicit, re.IGNORECASE)
    if match:
        return match.group(0)
    return explicit or ('M1 Pro' if historical else 'Unknown chip')


def measured_rows():
    gates = gate_results()
    latest = {}
    files = list(RECEIPTS.glob('*engine-compare-*.json'))
    # The installed TensorFold qualification stores its receipts in a subdirectory.
    files += [RECEIPTS / '2026-10-30-tensorfold-b3ab9ba' / f'compare-{size}.json' for size in ('short', 'long')]
    for f in sorted((p for p in files if p.exists()), key=lambda p: (p.parent.name[:10] if p.parent != RECEIPTS else p.name[:10], p.stem)):
        r = json.loads(f.read_text())
        if r.get('status') != 'complete':
            continue
        model = r.get('model_key', 'qwen2b')
        drv = r.get('driver', 'Honeykrisp Mesa 7faf04c065')
        conc = r.get('concurrency', 1)
        # Existing receipts belong to the documented M1 Pro; future unlabelled hardware stays unknown.
        date = f.parent.name[:10] if f.parent != RECEIPTS else f.name[:10]
        chip = chip_name(r, historical=date <= '2026-10-30')
        os_name = r.get('os') or ('Aurora Linux' if date <= '2026-10-30' else 'Unknown OS')
        for arm in r['arms']:
            latest[(model, arm, r['max_tokens'], drv, conc, chip, os_name, r.get('kernel', ''), r.get('model', 'unknown revision'), r.get('prompt_sha256', 'unknown prompt'), r.get('weights_sha256') or 'unknown weights')] = (f, r)
    rows = []
    for (model, arm, tokens, drv, conc, chip, os_name, _kernel, model_ref, prompt_hash, weights_hash), (f, r) in sorted(latest.items()):
        ok = [x for x in r['runs'] if x['arm'] == arm and 'text' in x and not x.get('error')]
        if not ok:
            continue
        texts = {x['text_sha256'] for x in ok}
        base_arm = 'mlx-5k' if 'mlx-5k' in r['arms'] else ('mlx-120k' if 'mlx-120k' in r['arms'] else None)
        base = {x['text_sha256'] for x in r['runs'] if x['arm'] == base_arm and 'text_sha256' in x}
        if arm == base_arm:
            same = 'reference'
        elif not base:
            every = {x['text_sha256'] for x in r['runs'] if 'text_sha256' in x}
            same = 'yes (engines in this run agree)' if len(every) == 1 else 'n/a (no MLX default in this run)'
        elif texts == base:
            same = 'yes'
        else:
            mt = next(x['text'] for x in r['runs'] if x['arm'] == base_arm and 'text' in x)
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
            'driver': drv, 'date': f.parent.name[:10] if f.parent != RECEIPTS else f.name[:10],
            'status': 'measured here', 'source': str(f.relative_to(HERE)), '_model': model, '_conc': conc, '_arm': arm,
            'chip': chip, 'os': os_name, 'model_reference': model_ref, 'prompt_sha256': prompt_hash,
            'weights_sha256': weights_hash, '_text_hashes': texts})
    # Most functional per model, length and load: the shortest typical reply (first token plus
    # REPLY_TOKENS at its streaming speed) among rows whose output matched and whose gate did not fail.
    for key in {(x['_model'], x['tokens'], x['_conc'], x['chip'], x['os'], x['model_reference'], x['prompt_sha256'], x['weights_sha256']) for x in rows}:
        group = [x for x in rows if (x['_model'], x['tokens'], x['_conc'], x['chip'], x['os'], x['model_reference'], x['prompt_sha256'], x['weights_sha256']) == key and x['gate'] != 'FAIL'
                 and x['same_output'].startswith(('yes', 'reference')) and x['decode_tok_s']]
        if group:
            min(group, key=lambda x: reply_s(x) or 1e9)['best'] = '★'
    return rows


def mac_rows():
    """Read completed native Apple MLX receipts; do not assign Linux gate verdicts."""
    latest = {}
    for f in sorted(RECEIPTS.glob('*-macos-scoreboard-*.json')):
        r = json.loads(f.read_text())
        if r.get('status') != 'complete' or r.get('concurrency', 1) != 1:
            continue
        runs = [x for x in r.get('runs', []) if x.get('arm') == 'mac-mlx' and not x.get('error')]
        if len(runs) < 3 or any(x.get('decode_tps') is None or x.get('ttft_s') is None for x in runs):
            continue
        model = r['model_key']
        chip = chip_name(r)
        os_name = r.get('os', 'macOS')
        latest[(model, r['max_tokens'], chip, os_name, r.get('model', 'unknown revision'), r.get('prompt_sha256', 'unknown prompt'), r.get('weights_sha256') or 'unknown weights')] = (f, r, runs, chip, os_name)
    rows = []
    for (model, tokens, _, _, model_ref, prompt_hash, weights_hash), (f, r, runs, chip, os_name) in sorted(latest.items()):
        rows.append({'model': MODEL_NAMES.get(model, model), 'engine': 'Apple MLX (in-process)',
                     'settings': f"MLX {r.get('mlx_version', '?')}; mlx-lm {r.get('mlx_lm_version', '?')}",
                     'tokens': tokens, 'decode_tok_s': med([x['decode_tps'] for x in runs]),
                     'ttft_s': med([x['ttft_s'] for x in runs]), 'total_s': med([x['total_s'] for x in runs]),
                     'runs': len(runs), 'same_output': 'not compared with Linux', 'gate': 'not gated',
                     'kernel': r.get('kernel', ''), 'driver': r.get('driver', 'Apple Metal'),
                     'date': f.name[:10], 'status': 'measured here', 'source': f'receipts/{f.name}',
                     '_model': model, '_conc': 1, '_arm': 'mac-mlx', 'chip': chip, 'os': os_name,
                     'model_reference': model_ref, 'prompt_sha256': prompt_hash, 'weights_sha1': r.get('weights_sha1', ''),
                     'weights_sha256': weights_hash, 'start_time': runs[0].get('start_time', ''),
                     'end_time': runs[-1].get('end_time', ''),
                     '_text_hashes': ({x['text_sha256'] for x in runs} if all(x.get('text_sha256') for x in runs) else set())})
    return rows


def annotate_cross_platform(mac, linux):
    """Compare synthetic text hashes only for same model, prompt, length and in-process boundary."""
    for row in mac:
        refs = [x for x in linux if x['_arm'] in ('mlx-5k', 'mlx-120k') and x['_conc'] == 1
                and x['_model'] == row['_model'] and x['tokens'] == row['tokens']
                and x['model_reference'] == row['model_reference']
                and x['prompt_sha256'] == row['prompt_sha256']
                and x['weights_sha256'] == row['weights_sha256']
                and x['weights_sha256'] != 'unknown weights'
                and x['prompt_sha256'] != 'unknown prompt' and len(x['_text_hashes']) == 1]
        if refs and len(row['_text_hashes']) == 1:
            matches = sum(x['_text_hashes'] == row['_text_hashes'] for x in refs)
            row['same_output'] = f'text hash matches {matches}/{len(refs)} Linux MLX rows'
        else:
            row['same_output'] = 'no comparable Linux text hash'


def chart(rows):
    """Dot plots grouped by model, output length and load; separate scales per metric."""
    groups = {}
    for x in sorted(rows, key=lambda x: (x['_model'], x['tokens'], x['_conc'], x['chip'], x['os'], x['_arm'], x['driver'])):
        groups.setdefault((x['model'], x['tokens'], x['_conc'], x.get('model_reference', 'unknown revision'), x.get('prompt_sha256', 'unknown prompt'), x.get('weights_sha256', 'unknown weights')), []).append(x)
    label_w, panel_w, gap, row_h = 340, 205, 24, 22
    w = label_w + 3 * (panel_w + gap) + 20
    panels = [('First token (s): lower', lambda x: x['ttft_s'], '{:.2f}'),
              ('Decode (tok/s): higher', lambda x: x['decode_tok_s'], '{:.1f}'),
              (f'{REPLY_TOKENS}-token estimate (s): lower', reply_s, '{:.1f}')]
    y = 26
    parts = ['<circle cx="13" cy="11" r="4" class="mac"/><text x="23" y="15" class="legend">macOS</text><circle cx="90" cy="11" r="4" class="linux"/><text x="100" y="15" class="legend">Aurora Linux — labels identify chip and engine; driver in tooltip</text>']
    for (model, tokens, conc, model_ref, prompt_hash, weights_hash), xs in groups.items():
        revision = model_ref.rsplit('@', 1)[-1][:8] if '@' in model_ref else 'revision unknown'
        head = f'{model} · rev {revision} · weights {weights_hash[:8]} · prompt {prompt_hash[:8]} · {tokens}-token limit' + (f' · {conc} requests (aggregate decode)' if conc > 1 else ' · one request')
        parts.append(f'<text x="8" y="{y + 14}" class="h">{escape(head)}</text>'); y += 22
        for i, (title, _, _) in enumerate(panels):
            parts.append(f'<text x="{label_w + i * (panel_w + gap)}" y="{y + 12}" class="a">{escape(title)}</text>')
        y += 21
        tops = []
        for _, f, _ in panels:
            vals = [v for v in (f(x) for x in xs) if v is not None and v > 0]
            tops.append(max(vals) if vals else 1)
        base_y = y
        for x in xs:
            is_mac = x['_arm'] == 'mac-mlx'
            os_short = 'macOS' if is_mac else ('Aurora' if 'Aurora' in x['os'] else x['os'])
            if not is_mac and 'wip' in x['kernel']:
                os_short += ' wip' + x['kernel'].split('wip')[-1].split('-')[0]
            engine = 'Apple MLX in-process' if is_mac else SHORT.get(x['_arm'], x['_arm'])
            if not is_mac and '7faf' in x['driver']:
                engine += ' · old driver'
            label = f"{x['chip']} · {os_short} · {engine}"
            parts.append(f'<text x="8" y="{y + 14}" class="l">{escape(label)}</text>')
            for i, (title, f, fmt_) in enumerate(panels):
                v = f(x); x0 = label_w + i * (panel_w + gap)
                if v is None:
                    parts.append(f'<text x="{x0}" y="{y + 14}" class="v">n/a</text>'); continue
                dx = (panel_w - 52) * max(0, v) / tops[i]
                cls = 'mac' if is_mac else 'linux'
                tip = escape(f"{label}; {x['driver']}; {title}: {fmt_.format(v)}; {x['runs']} runs")
                parts.append(f'<g><title>{tip}</title><circle cx="{x0 + dx:.1f}" cy="{y + 10}" r="4.5" class="{cls}"/>'
                             f'<text x="{x0 + dx + 8:.1f}" y="{y + 14}" class="v">{fmt_.format(v)}</text></g>')
            y += row_h
        for i in range(3):
            x0 = label_w + i * (panel_w + gap)
            parts.append(f'<line x1="{x0}" y1="{base_y}" x2="{x0}" y2="{y}" class="axis"/>')
        y += 20
    style = ('<style>svg{background:#fcfcfb}text{font:12px system-ui,sans-serif;fill:#151515}.h{font-weight:650}'
             '.a,.v{font-size:11px;fill:#52514e}.legend{font-size:11px;fill:#52514e}'
             '.mac{fill:#c35425}.linux{fill:#286db8}.axis{stroke:#c3c2b7;stroke-width:1}'
             '@media (prefers-color-scheme:dark){svg{background:#1a1a19}text{fill:#f0efec}.a,.v,.legend{fill:#c3c2b7}'
             '.mac{fill:#fb9a64}.linux{fill:#65aaf5}.axis{stroke:#52514e}}</style>')
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{y}" viewBox="0 0 {w} {y}">'
            f'<title>Local AI model timings by chip, operating system and engine</title>{style}{"".join(parts)}</svg>\n')

def main():
    rows = measured_rows()
    mac = mac_rows()
    annotate_cross_platform(mac, rows)
    notes = json.loads((HERE / 'scoreboard-notes.json').read_text())['rows']
    with (HERE / 'engine-scoreboard.csv').open('w', newline='') as fh:
        w = csv.DictWriter(fh, fieldnames=FIELDS + ['blocker'], extrasaction='ignore', lineterminator='\n')
        w.writeheader()
        for x in rows:
            w.writerow({k: (fmt(v) if isinstance(v, float) else v) for k, v in x.items()})
        for x in mac:
            w.writerow({k: (fmt(v) if isinstance(v, float) else v) for k, v in x.items()})
        for n in notes:
            w.writerow({**n, 'best': ''})
    md = ['# Local AI engine scoreboard', '',
          'Chip and OS labels distinguish measurements. The Linux table’s ★ marks the most functional setup per model, length and load: the shortest typical reply '
          '(first token plus 200 tokens) whose output matched every other engine and whose correctness gate did not fail. '
          'Regenerate with `python3 mseries/local-ai/scoreboard.py` after adding a receipt. Tracked in the '
          '"Local AI engine scoreboard" issue.', '',
          '![Dot plots of first token, decode speed and reply time by chip, operating system and engine](engine-scoreboard.svg)', '',
          'Each dot is a measured engine configuration. Chip, OS and driver are identified; macOS and Aurora have different runtime versions and conditions. '
          'The plots group the same model revision, weight hash, prompt hash and token limit, but do not establish token or numerical equivalence across systems. '
          'First token and estimated reply time are lower-is-better; decode is higher-is-better. The 200-token value extrapolates from measured decode speed. HTTP and in-process timing boundaries differ. '
          'No dot implies a winner across systems. The Linux-only star and gates below are unchanged.', '',
          '## Aurora Linux measurements', '',
          '| ★ | Chip | OS | Model | Engine | Settings | Token limit | Decode tok/s | TTFT s | Total s | Runs | Same output as reference in receipt | Gate | Kernel | Driver | Date | Receipt |',
          '|---|---|---|---|---|---|---:|---:|---:|---:|---:|---|---|---|---|---|---|']
    for x in sorted(rows, key=lambda x: (x['_model'], x['tokens'], -(x['decode_tok_s'] or 0))):
        b = '**' if x.get('best') else ''
        md.append(f"| {x.get('best', '')} | {x['chip']} | {x['os']} | {x['model']} | {b}{x['engine']}{b} | `{x['settings']}` | {x['tokens']} | "
                  f"{b}{fmt(x['decode_tok_s'])}{b} | {fmt(x['ttft_s'])} | {fmt(x['total_s'])} | {x['runs']} | {x['same_output']} | "
                  f"{x['gate']} | `{x['kernel']}` | {x['driver']} | {x['date']} | [{Path(x['source']).name}]({x['source'].replace('receipts/', 'receipts/')}) |")
    md += ['', '## Native macOS measurements', '',
           '| Chip | OS | Model | Token limit | Decode tok/s | TTFT s | Total s | Runs | Linux MLX text | Start (local) | End (local) | Model SHA-1 | Kernel | Receipt |',
           '|---|---|---|---:|---:|---:|---:|---:|---|---|---|---|---|---|']
    for x in sorted(mac, key=lambda x: (x['_model'], x['tokens'], x['chip'], x['os'])):
        md.append(f"| {x['chip']} | {x['os']} | {x['model']} | {x['tokens']} | {fmt(x['decode_tok_s'])} | {fmt(x['ttft_s'])} | {fmt(x['total_s'])} | {x['runs']} | {x['same_output']} | {x['start_time']} | {x['end_time']} | `{x['weights_sha1']}` | `{x['kernel']}` | [{Path(x['source']).name}]({x['source']}) |")
    md += ['', 'These rows are Apple MLX in-process measurements. Text-hash matches cover these prompts only and do not establish token identity or numerical fidelity. '
           'LFM3 used the project-pinned injected implementation; its tokenizer emitted a custom-code prompt and continued without approval, '
           'and Transformers reported a model-type compatibility warning. See its receipts. M4 appears only when measured receipts identify an M4 chip and OS.', '',
           '## Watched or reported elsewhere (not comparable to the table above)', '',
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
           '6. **Version steps follow upstream.** Check the current installer pins and deployment receipt; qualify any newer runtime in an isolated environment before changing the default.', '',
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
           'python3 engine-compare.py --model granite1b',
           'python3 mlx-gate.py reference && python3 mlx-gate.py sweep',
           './tensorfold-vulkan.sh build && ./tensorfold-vulkan.sh gpu',
           'python3 scoreboard.py',
           '```', '']
    (HERE / 'engine-scoreboard.svg').write_text(chart(rows + mac))
    (HERE / 'ENGINE-SCOREBOARD.md').write_text('\n'.join(md))
    print(f'{len(rows)} Linux rows, {len(mac)} macOS rows, {len(notes)} noted rows')


if __name__ == '__main__':
    main()
