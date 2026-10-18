#!/usr/bin/env python3
"""Synthetic GTK output/guest churn probe. Never calls Incus or changes guests.

Use Xvfb/Cairo to isolate retained text from native renderer allocations.
The source option allows the same probe to compare installed and candidate code.
RSS is an observation, not a portable pass/fail memory threshold.
"""
import argparse
import gc
import hashlib
import json
from pathlib import Path
import sys
import tempfile
from unittest.mock import patch

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--source', type=Path, default=Path(__file__).resolve().parents[1])
parser.add_argument('--output', type=Path, required=True)
args = parser.parse_args()
if args.output.exists():
    parser.error('Use a new output file')
sys.path.insert(0, str(args.source))
from orchard_incus.window import Window
from gi.repository import Gtk, GLib

app = Gtk.Application(application_id='io.github.techmore.OrchardRetentionProbe')
app.register(None)
context = GLib.MainContext.default()
report = {'method': 'Synthetic stopped-guest churn; 12 identities, 64 output chunks per guest; no Incus; GTK undo/cache retention, not native frame timing',
          'source_sha256': {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                            for p in (args.source / 'orchard_incus').glob('*.py')},
          'snapshots': [], 'output_characters': 0, 'output_utf8_bytes': 0}

def settle():
    for _ in range(100):
        if not context.pending():
            break
        context.iteration(False)

def snapshot(stage):
    gc.collect()
    status = dict(x.split(':', 1) for x in Path('/proc/self/status').read_text().splitlines())
    report['snapshots'].append({'stage': stage, 'rss_kib': int(status['VmRSS'].split()[0]),
                               'buffers': len(win.exec_bufs),
                               'characters': sum(b.get_char_count() for b in win.exec_bufs.values()),
                               'undoable_buffers': sum(b.get_can_undo() for b in win.exec_bufs.values())})

with tempfile.TemporaryDirectory() as directory, \
     patch('orchard_incus.window.STATE_FILE', directory + '/state.json'), \
     patch.object(Window, 'check_incus'), patch.object(Window, 'bg'), patch.object(Window, 'read'):
    win = Window(app)
    try:
        snapshot('start')
        for guest in range(12):
            name = f'output-probe-{guest}'
            win.show([{'name': name, 'status': 'Stopped', 'type': 'container', 'config': {}, 'state': {}}])
            for chunk in range(64):
                text = str(chunk) + ' λ' * 32768 + '\n'
                report['output_characters'] += len(text)
                report['output_utf8_bytes'] += len(text.encode())
                win.append_out(name, text)
            settle()
        snapshot('after-output-churn')
        win.show([])
        settle()
        snapshot('empty-inventory')
    finally:
        win.close()
        settle()
args.output.parent.mkdir(parents=True, exist_ok=True)
args.output.write_text(json.dumps(report, indent=2) + '\n')
print(json.dumps(report, indent=2))
