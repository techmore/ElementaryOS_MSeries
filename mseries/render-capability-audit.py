#!/usr/bin/env python3
"""Validate the pinned capability ledger and render its progressively enhanced page."""
import argparse
from collections import Counter
import html
import json
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / 'docs/capabilities.json'
PAGE = ROOT / 'docs/capabilities.html'
AREAS = ('Hardware', 'Desktop', 'Connectivity', 'Apps', 'AI & speech', 'Delivery')
STAGES = ('Recorded outcome', 'Limited qualification', 'Staged', 'Source reviewed', 'Blocked')
ORIGINS = ('Custom implementation', 'Downstream patch', 'Ported upstream behavior',
           'Upstream integration', 'Mixed integration and custom UI')
BASE = 'https://github.com/techmore/ElementaryOS_MSeries'


def escape(value):
    return html.escape(str(value), quote=True)


def validate(data):
    assert data['schema_version'] == 1
    assert re.fullmatch(r'\d{4}-\d{2}-\d{2}', data['audited_on'])
    revision = data['source_revision']
    assert re.fullmatch(r'[0-9a-f]{40}', revision)
    tracked = set(subprocess.check_output(
        ['git', 'ls-tree', '-r', '--name-only', revision], cwd=ROOT, text=True).splitlines())
    ids = set()
    required = ('title', 'provided', 'verification', 'limitation', 'next_step', 'delivery')
    for entry in data['entries']:
        identity = entry['id']
        assert re.fullmatch(r'[a-z][a-z0-9-]+', identity) and identity not in ids, identity
        ids.add(identity)
        assert entry['area'] in AREAS, identity
        assert entry['stage'] in STAGES, identity
        assert entry['kind'] in ('Fix', 'Enhancement'), identity
        assert entry['origin'] in ORIGINS, identity
        assert entry['priority'] in ('P1', 'P2', 'P3'), identity
        assert all(isinstance(entry[k], str) and entry[k].strip() for k in required), identity
        assert entry['source'] and entry['evidence'], identity
        for group in ('source', 'checks', 'evidence'):
            for path in entry[group]:
                assert not Path(path).is_absolute() and '..' not in Path(path).parts, path
                assert path in tracked or any(p.startswith(path.rstrip('/') + '/') for p in tracked), (identity, path)
                assert (ROOT / path).exists(), (identity, path)
    assert ids
    assert all(finding['entry'] in ids for finding in data['findings'])
    assert all(item['url'].startswith(BASE + '/') for item in data['exclusions'])


def source_links(entry, revision):
    blocks = []
    for group, label in (('source', 'Implementation / wiring'), ('checks', 'Check definitions'), ('evidence', 'Evidence / context')):
        links = []
        for path in entry[group]:
            target = 'tree' if (ROOT / path).is_dir() else 'blob'
            links.append(f'<li><a href="{BASE}/{target}/{revision}/{escape(path)}">{escape(path)}</a></li>')
        if links:
            blocks.append(f'<div><h4>{label}</h4><ul>{"".join(links)}</ul></div>')
    return ''.join(blocks)


def render(data):
    revision = data['source_revision']
    entries = data['entries']
    stage_counts = Counter(e['stage'] for e in entries)
    entries = sorted(entries, key=lambda e: (e['priority'], AREAS.index(e['area']), e['title']))
    cards = []
    for entry in entries:
        text = ' '.join(str(entry[k]) for k in ('title', 'area', 'kind', 'origin', 'stage', 'provided', 'verification', 'limitation', 'next_step', 'delivery'))
        attrs = ' '.join(f'data-{key}="{escape(entry[key])}"' for key in ('area', 'stage', 'kind', 'origin', 'priority'))
        cards.append(f'''<article class="entry" id="{entry['id']}" data-entry {attrs} data-search="{escape(text)}">
<div class="entry-heading"><div><p class="eyebrow">{escape(entry['area'])} · {escape(entry['kind'])} · {escape(entry['priority'])}</p><h3><a href="#{entry['id']}">{escape(entry['title'])}</a></h3></div><span class="stage stage-{escape(entry['stage'].lower().replace(' ', '-'))}">{escape(entry['stage'])}</span></div>
<p>{escape(entry['provided'])}</p>
<p class="limit"><strong>Limits.</strong> {escape(entry['limitation'])}</p>
<p class="next"><strong>Next iteration.</strong> {escape(entry['next_step'])}</p>
<details><summary>Ownership, delivery and evidence</summary><dl><dt>What is ours</dt><dd>{escape(entry['origin'])}</dd><dt>Delivery</dt><dd>{escape(entry['delivery'])}</dd><dt>Verification scope</dt><dd>{escape(entry['verification'])}</dd></dl><div class="sources">{source_links(entry, revision)}</div></details>
</article>''')
    observation = data.get("runtime_observation", {})
    observed = (f'<p class="note">Later read-only observation: kernel release <code>{escape(observation["kernel_release"])}</code>, installed compositor package <code>{escape(observation["installed_compositor_package"])}</code>, at {escape(observation["captured_utc"])}. {escape(observation["scope"])}</p>' if observation else "")
    options = lambda values: ''.join(f'<option value="{escape(v)}">{escape(v)}</option>' for v in values)
    findings = ''.join(f'<li><a href="#{f["entry"]}">{escape(f["title"])}</a><p>{escape(f["detail"])}</p></li>' for f in data['findings'])
    exclusions = ''.join(f'<li><a href="{escape(item["url"])}">{escape(item["title"])}</a><p>{escape(item["reason"])}</p></li>' for item in data['exclusions'])
    return f'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Fixes &amp; enhancements — ElementaryOS M-Series</title>
<meta name="description" content="An evidence-backed audit of M-Series fixes, custom features, upstream integrations and remaining acceptance work.">
<link rel="stylesheet" href="capabilities.css"><script src="capabilities.js" defer></script></head>
<body><a class="skip" href="#catalog">Skip to the catalog</a><header><nav aria-label="Site"><a href="index.html">← M-Series</a><a href="features.html">Features</a><a href="bug-fixes.html">Bug history</a><a href="support.html">Hardware evidence</a></nav>
<p class="eyebrow">Project capability audit · {escape(data['audited_on'])}</p><h1>Fixes &amp; enhancements</h1>
<p class="intro">What we add, what we integrate, and what the evidence supports. Every entry separates ownership, delivery, verification and the next useful iteration.</p>
<div class="stats" aria-label="Audit scope"><p><strong>{len(entries)}</strong><span>scoped audit entries</span></p><p><strong>{stage_counts['Recorded outcome']}</strong><span>with a recorded outcome</span></p><p><strong>{stage_counts['Staged']}</strong><span>staged updates</span></p><p><strong>{stage_counts['Blocked']}</strong><span>blocked outcomes</span></p></div>
<p class="note">This is a dated review of the transformed J314S desktop and its source. Factory-image and other-machine acceptance are separate. Entry counts describe audit coverage; each entry states its own delivery and evidence.</p></header>
<main>{observed}<section class="panel" aria-labelledby="iteration-title"><p class="eyebrow">Where to iterate next</p><h2 id="iteration-title">Finish acceptance before widening the claims</h2><p>Start with <a href="#kernel-wip2">fallback recovery</a>, <a href="#screenshot-retention">real screenshot attachment</a>, <a href="#english-f5">ChatGPT F5 after relaunch</a>, and <a href="#taskbar">the complete taskbar/focus combination</a>. Touch ID has a separate <a href="#touch-id">approved guard trial and matching gate</a>. P1/P2/P3 are this audit’s triage priorities, with P1 first.</p></section>
<details class="panel"><summary>What this audit corrected · {len(data['findings'])} findings</summary><ul class="findings">{findings}</ul></details>
<details class="panel" id="method"><summary>How to read the evidence and provenance</summary>
<p>{escape(data['scope'])}</p><dl class="legend"><dt>Recorded outcome</dt><dd>A dated operation or hardware observation exists, within the entry’s stated scope.</dd><dt>Limited qualification</dt><dd>Implementation and some fixture, build or runtime evidence exist; listed acceptance remains incomplete.</dd><dt>Staged</dt><dd>A later installation/load/activation boundary remains. Read the exact delivery field.</dd><dt>Source reviewed</dt><dd>Source/wiring and any listed check definitions were inspected; an end-to-end outcome is not established here.</dd><dt>Blocked</dt><dd>A specific blocker prevents the advertised end outcome or public delivery.</dd></dl>
<p><strong>Ownership.</strong> Custom implementation names project-authored behavior; downstream patch modifies an existing app; ported behavior translates upstream work; integration packages/configures another project. Mixed entries identify the custom surface and its upstream dependencies. These labels are attribution boundaries, not new license grants.</p>
<p><strong>Test scope.</strong> Links labeled “Check definitions” show retained tests, not a claim that every app suite was rerun during this documentation audit. Existing outcomes are described and linked separately. Source review is scoped capability verification, not an exhaustive security audit.</p>
<p>Source snapshot: <a href="{BASE}/tree/{revision}"><code>{revision[:12]}</code></a>. Later work must update the ledger with new evidence; changing a date alone does not qualify a feature.</p></details>
<section id="catalog" aria-labelledby="catalog-title"><h2 id="catalog-title">Explore the catalog</h2><form id="filters" class="filters" hidden><label class="search">Search fixes, features and limits<input id="search" type="search" name="query" placeholder="Try screenshot, Bluetooth, source, recovery…"></label><label>Area<select name="area"><option value="">All areas</option>{options(AREAS)}</select></label><label>Evidence stage<select name="stage"><option value="">All stages</option>{options(STAGES)}</select></label><label>Change<select name="kind"><option value="">Fixes and enhancements</option>{options(('Fix', 'Enhancement'))}</select></label><label>Ownership<select name="origin"><option value="">All ownership types</option>{options(ORIGINS)}</select></label><label>Priority<select name="priority"><option value="">All priorities</option>{options(('P1', 'P2', 'P3'))}</select></label><button type="reset">Clear filters</button></form>
<p id="results" class="result-count" aria-live="polite" role="status">{len(entries)} audit entries. Sorted by priority, then area.</p><p id="empty" class="panel" hidden>No entries match these filters. Try fewer words or clear the filters.</p><noscript><p>All entries and their evidence are available below. Browser scripting enables optional search and filters.</p></noscript>
<div class="entries">{''.join(cards)}</div></section>
<section class="panel" aria-labelledby="excluded-title"><h2 id="excluded-title">Tracked separately from provided capabilities</h2><ul class="findings">{exclusions}</ul><p>Open pull-request status is the observation at this audit’s source snapshot. Follow the linked PR for later changes.</p></section></main>
<footer><p>Reviewed {escape(data['audited_on'])} · <a href="capabilities.json">Download the structured audit</a> · <a href="build-status.html">Live builds and publication</a></p><p>Source: <a href="{BASE}/blob/{revision}/AGENTS.md">project evidence rules</a> and the implementation, check and evidence links in every entry. The static page is generated from the structured ledger and remains readable without JavaScript.</p></footer></body></html>
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true', help='validate ledger and reject stale generated HTML')
    args = parser.parse_args()
    data = json.loads(DATA.read_text())
    validate(data)
    output = render(data)
    if args.check:
        if not PAGE.exists() or PAGE.read_text() != output:
            raise SystemExit('capabilities.html is stale: run python3 mseries/render-capability-audit.py')
    else:
        PAGE.write_text(output)
    print(f'Capability ledger: {len(data["entries"])} unique entries; pinned source paths and generated HTML valid')


if __name__ == '__main__':
    main()
