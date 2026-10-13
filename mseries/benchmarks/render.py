#!/usr/bin/python3
"""Regenerate the results table in README.md from results/*.json (newest last). Usage: python3 render.py"""
import json
from pathlib import Path

here = Path(__file__).resolve().parent
files = sorted(p for p in (here / 'results').glob('*.json') if not p.name.endswith('-quick.json'))
runs = [json.loads(p.read_text()) for p in files]
rows = [
    ('CPU single-thread, sysbench primes (events/s)', 'cpu', 'sysbench_prime_events_per_s_1t'),
    ('CPU all 10 cores, sysbench primes (events/s)', 'cpu', 'sysbench_prime_events_per_s_10t'),
    ('7-Zip built-in benchmark, total MIPS', 'cpu', '7zip_total_mips'),
    ('SHA-256, 1 thread (MB/s)', 'cpu', 'openssl_sha256_mb_per_s_1t'),
    ('Memory read, 1 thread (MiB/s)', 'memory', 'memory_read_mib_per_s_1t'),
    ('Memory read, 10 threads (MiB/s)', 'memory', 'memory_read_mib_per_s_10t'),
    ('Memory write, 1 thread (MiB/s)', 'memory', 'memory_write_mib_per_s_1t'),
    ('Memory write, 10 threads (MiB/s)', 'memory', 'memory_write_mib_per_s_10t'),
    ('Disk sequential read 1 MiB (MB/s)', 'disk', 'seq_read_1m_mb_per_s'),
    ('Disk sequential write 1 MiB (MB/s)', 'disk', 'seq_write_1m_mb_per_s'),
    ('Disk random read 4 KiB QD32 (IOPS)', 'disk', 'rand_read_4k_qd32_iops'),
    ('Disk random write 4 KiB QD32 (IOPS)', 'disk', 'rand_write_4k_qd32_iops'),
    ('Sustained all-core throughput drop over 60 s (%)', 'sustained', 'sustained_drop_pct'),
    ('GPU glmark2-es2 off-screen 1024x768 (score)', 'gpu', 'glmark2_es2_offscreen_1024x768_score'),
    ('Firefox headless start, warm (s)', 'startup', 'firefox_headless_start_s'),
    ('Chromium (snap) headless start, warm (s)', 'startup', 'chromium_snap_headless_start_s'),
]
header = '| Benchmark | ' + ' | '.join(f"{r['info']['date']} · {r['info']['kernel']}" for r in runs) + ' |'
lines = [header, '|---|' + '---|' * len(runs)]
for label, suite, key in rows:
    cells = []
    for run in runs:
        value = run['results'].get(suite, {}).get(key)
        cells.append('—' if value is None else (f'{value:,}' if isinstance(value, int) else str(value)))
    lines.append(f'| {label} | ' + ' | '.join(cells) + ' |')
table = '\n'.join(lines)

readme = here / 'README.md'
text = readme.read_text()
start, end = '<!-- results:start -->', '<!-- results:end -->'
text = text[:text.index(start) + len(start)] + '\n' + table + '\n' + text[text.index(end):]
readme.write_text(text)
print(table)
