#!/usr/bin/env python3
"""Render the recorded alternating M1 Pro batch-budget experiments."""
import json
from pathlib import Path
import statistics

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

root = Path(__file__).resolve().parent / 'receipts'
series = [
    (10000, root / '2026-10-27-batch-work-ab.json'),
    (20000, root / '2026-10-27-batch-work-20k-ab.json'),
    (40000, root / '2026-10-27-batch-work-40k-ab.json'),
]
fig, axes = plt.subplots(1, 3, figsize=(12.8, 5), sharey=True)
fig.patch.set_facecolor('#f7f8fa')
for ax, (budget, filename) in zip(axes, series):
    report = json.loads(filename.read_text())
    rows = report['runs']
    pairs = [(rows[a]['result'], rows[b]['result']) for a, b in ((0, 1), (3, 2), (4, 5))]
    gains = []
    for before, after in pairs:
        x, y = before['total_s'], after['total_s']
        gains.append(100 * (1 - y / x))
        ax.plot([0, 1], [x, y], color='#9aa9bd', lw=1.3, zorder=1)
        ax.scatter([0, 1], [x, y], c=['#52677f', '#117d8a'], s=40, zorder=2)
    ax.set_facecolor('#ffffff')
    ax.set_xticks([0, 1], ['5,000\nbaseline', f'{budget:,}\ncandidate'])
    ax.set_title(f'{budget:,} work groups', loc='left', fontsize=12, fontweight='bold')
    ax.grid(axis='y', color='#dce3eb', linewidth=.8)
    ax.set_axisbelow(True)
    ax.spines[['top', 'right']].set_visible(False)
    ax.set_ylim(1.05, 1.55)
    ax.text(.04, .05, f"Median paired time reduction: {statistics.median(gains):.1f}%\n"
            f"Submissions: {pairs[0][0]['counter_delta']['vk_submissions']} → "
            f"{pairs[0][1]['counter_delta']['vk_submissions']}",
            transform=ax.transAxes, fontsize=9, va='bottom', color='#263a4d',
            bbox={'facecolor': '#f1f6f8', 'edgecolor': 'none', 'pad': 6})
axes[0].set_ylabel('Request wall time, seconds (lower is better)')
fig.suptitle('M1 Pro: larger Vulkan batches reduce short Qwen request time',
             x=.08, ha='left', fontsize=15, fontweight='bold', color='#172c3d')
fig.text(.08, .89, 'Each line is one alternating pair · Qwen3.5 2B · 27 prompt + 32 generated tokens',
         fontsize=10, color='#475a6c')
fig.text(.08, .025, 'Three pairs per candidate; one prompt. Desktop frame pacing and broader model correctness are untested.',
         fontsize=9, color='#526477')
fig.subplots_adjust(left=.08, right=.98, bottom=.16, top=.79, wspace=.19)
fig.savefig(root / '2026-10-27-batch-work-ab.png', dpi=160, facecolor=fig.get_facecolor())
