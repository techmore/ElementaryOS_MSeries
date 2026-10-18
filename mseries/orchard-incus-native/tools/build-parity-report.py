#!/usr/bin/env python3
"""Render the reviewed, source-pinned parity ledger; never infer support from a tab."""
import csv
import io
import json
from pathlib import Path

root = Path(__file__).resolve().parents[1]
catalog = json.loads((root / 'docs/upstream-parity.json').read_text())
base = f"https://github.com/andrew-waters/orchard/blob/{catalog['upstream_revision']}/"
rows = catalog['features']
counts = {status: sum(row['status'] == status for row in rows) for status in sorted({r['status'] for r in rows})}
lines = ['# Orchard upstream parity', '', f"Reviewed upstream: `{catalog['upstream_revision']}`.", '',
         'Scope: native Vala/GTK/Granite, Incus only. The owner selected an Incus-only runtime; no Podman, Docker or Apple runtime is installed by this work.', '',
         'This is a feature-by-feature comparison, not a claim of full parity. Implemented means a concrete UI/backend path exists; adapted means a native Incus counterpart exists with the stated behavior differences; partial means meaningful behavior is still missing; incompatible means the upstream contract is outside the installed runtime/platform target. Incus addition identifies scope beyond the upstream comparison. Tests and live verification are stated separately.', '',
         ', '.join(f'{status}: {count}' for status, count in counts.items()) + '.', '',
         catalog['compatibility_note'], '', 'Runtime references: ' + ', '.join(catalog['runtime_sources']), '']
for group in dict.fromkeys(row['group'] for row in rows):
    lines += [f'## {group}', '', '| Feature | Status | Native evidence / remaining work | Upstream evidence |', '|---|---|---|---|']
    for row in rows:
        if row['group'] != group:
            continue
        sources = ', '.join(f"[{Path(p).name}]({base}{p})" for p in row['upstream'])
        note = row['note'].replace('|', '\\|')
        lines.append(f"| {row['feature']} | {row['status']} | {note} | {sources} |")
    lines.append('')
lines += ['## Verification and limits', '', catalog['verification'], '',
          'The complete feature-view and service-symbol inventory is retained alongside this ledger. A source file appearing in the inventory does not imply its behavior has been ported. New upstream revisions require a new review.', '']
(root / 'docs/UPSTREAM-PARITY.md').write_text('\n'.join(lines))
with (root / 'docs/upstream-parity.csv').open('w', newline='') as stream:
    writer = csv.writer(stream, lineterminator="\n")
    writer.writerow(['id', 'group', 'feature', 'status', 'note', 'upstream'])
    for row in rows:
        writer.writerow([row['id'], row['group'], row['feature'], row['status'], row['note'], ';'.join(base + p for p in row['upstream'])])
print(f"Reviewed {len(rows)} capabilities: {counts}")
