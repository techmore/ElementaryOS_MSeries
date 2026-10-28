#!/usr/bin/env python3
"""Plot completed pairs from the guarded 256-token experiments."""
import json
from pathlib import Path
import statistics
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

root = Path(__file__).resolve().parent / 'receipts'
series = [(80000, root / '2026-10-27-batch-work-80k-long.json'),
          (120000, root / '2026-10-27-batch-work-120k-long.json')]
fig, axes = plt.subplots(1, 2, figsize=(10, 5), sharey=True)
for ax, (budget, path) in zip(axes, series):
    report = json.loads(path.read_text())
    rows = report['runs']
    pairs = [(rows[a]['result'], rows[b]['result']) for a, b in ((0, 1), (3, 2), (4, 5)) if max(a, b) < len(rows)]
    gains = []
    for baseline, candidate in pairs:
        before, after = baseline['total_s'], candidate['total_s']
        gains.append(100 * (1 - after / before))
        ax.plot([0, 1], [before, after], color='#9aa9bd', lw=1.4)
        ax.scatter([0, 1], [before, after], c=['#52677f', '#117d8a'], s=42, zorder=2)
    ax.set_xticks([0, 1], ['5,000\nbaseline', f'{budget:,}\ncandidate'])
    ax.set_title(f'{budget:,} work groups', loc='left', fontweight='bold')
    ax.grid(axis='y', color='#dce3eb')
    ax.spines[['top', 'right']].set_visible(False)
    ax.text(.05, .05, f"Median time reduction: {statistics.median(gains):.1f}%\n{len(pairs)} completed pairs", transform=ax.transAxes,
            bbox={'facecolor':'#f1f6f8', 'edgecolor':'none', 'pad':6}, fontsize=9)
axes[0].set_ylabel('Request wall time, seconds (lower is better)')
fig.suptitle('M1 Pro: Qwen 2B generates 256 tokens', x=.1, ha='left', fontweight='bold')
fig.text(.1, .03, 'GTK animation active; 80k stopped before the third pair due to the memory guard.', fontsize=9)
fig.subplots_adjust(left=.1, bottom=.19, top=.86, right=.98, wspace=.14)
fig.savefig(root / '2026-10-27-batch-work-long.png', dpi=160)
