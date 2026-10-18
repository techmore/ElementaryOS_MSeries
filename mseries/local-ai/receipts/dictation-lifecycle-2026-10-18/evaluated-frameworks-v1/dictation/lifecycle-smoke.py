#!/usr/bin/python3
"""Owned child for gtk-input-smoke --lifecycle-check: public file, never a microphone."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys
import time

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--receipt', type=Path, required=True)
args = parser.parse_args()
assert os.environ.get('MSERIES_INPUT_TEST_SESSION') == '1'
assert os.environ.get('GSETTINGS_BACKEND') == 'memory'
assert os.environ.get('STREAM_TEST_INSERT') == '1' and os.environ.get('STREAM_TEST_WAV')
assert os.environ.get('STREAM_BACKEND') == 'cpu' and os.environ.get('STREAM_OUTPUT') == 'ibus'
assert not args.receipt.exists(), 'Retain the completed lifecycle receipt'
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
spec = importlib.util.spec_from_file_location('dictation_lifecycle_real', HERE / 'stream-dictate.py')
stream = importlib.util.module_from_spec(spec); spec.loader.exec_module(stream)
from dictation_resources import load_policy, reasons, snapshot


def rss():
    return int(next(row.split()[1] for row in Path('/proc/self/status').read_text().splitlines()
                    if row.startswith('VmRSS:'))) * 1024


def digest(path):
    value = hashlib.sha256()
    with path.open('rb') as source:
        for block in iter(lambda: source.read(1024**2), b''): value.update(block)
    return value.hexdigest()


report = {'complete': False, 'passed': False, 'microphone_recorded': False,
          'keyboard_device_opened': False, 'owner_windows_opened': False,
          'cohort': 'on-demand-speech-lifecycle-v1', 'phases': [], 'kernel': os.uname().release,
          'policy': load_policy(), 'wav_sha256': digest(Path(os.environ['STREAM_TEST_WAV'])),
          'model_sha256': digest(Path(stream.MODEL)),
          'source_sha256': {p.name: digest(p) for p in HERE.glob('*.py')}}
native = Path(os.environ['TRANSCRIBE_LIBRARY'])
report['native_library_sha256'] = digest(native)
samples = []


def checkpoint():
    args.receipt.write_text(json.dumps(report, indent=2) + '\n')
    args.receipt.chmod(0o600)


def phase(name):
    sample = snapshot(); samples.append(sample)
    assert not reasons(report['policy'], sample=sample), 'Owned lifecycle resource guard'
    report['phases'].append({'phase': name, 'rss_bytes': rss()})
    checkpoint()


d = None
try:
    d = stream.Dictation()
    assert not d.models.loaded and 'transcribe_cpp' not in sys.modules
    phase('idle-before-native-import')
    d.start()
    deadline = time.monotonic() + 90
    while d.worker.is_alive() or d.typer.q.unfinished_tasks:
        sample = snapshot(); samples.append(sample)
        if reasons(report['policy'], sample=sample):
            d.cancel(); raise RuntimeError('Owned lifecycle resource guard')
        if time.monotonic() > deadline:
            d.cancel(); raise TimeoutError('Owned lifecycle child timed out')
        time.sleep(.1)
    assert not d.error and not d.typer.failed and d.models.loaded
    phase('resident-after-file-to-field')
    old = d.models.model
    assert d.models.trim(force=True) and not d.models.loaded
    assert old._handle is None, 'Pinned SDK close did not release its native handle'
    phase('released-after-file-to-field')
    with d.models.use(lambda extra: not reasons(report['policy'], extra)) as reloaded:
        assert reloaded is not old and reloaded._handle is not None
        assert not d.models.trim(force=True), 'Closed an active native lease'
        phase('reloaded-without-second-inference')
    assert d.models.trim(force=True) and reloaded._handle is None
    phase('released-after-reload')
    loaded = report['phases'][1]['rss_bytes']
    released = report['phases'][2]['rss_bytes']
    report['released_rss_bytes'] = loaded - released
    assert report['released_rss_bytes'] >= 512 * 1024**2, 'Machine-specific release benefit not established'
    report.update(complete=True, passed=True, inference_runs=1,
                  scope='One new lifecycle fixture, not a repeated accuracy/throughput ranking; second load performs no inference.')
except Exception as error:
    report['failure_kind'] = type(error).__name__
    raise
finally:
    if d:
        if d.active: d.cancel(); d.worker.join(5)
        d.models.trim(force=True)
    if samples:
        report['resources'] = {'samples': len(samples),
            'min_available_bytes': min(s['available_bytes'] for s in samples),
            'max_fan_rpm': max(max(s['fans_rpm'].values(), default=9999) for s in samples),
            'max_temp_c': max(max(s['temperatures_c'].values(), default=999) for s in samples)}
    checkpoint()
