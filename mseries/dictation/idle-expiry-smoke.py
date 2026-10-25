#!/usr/bin/python3
"""Real CPU model and automatic idle expiry; no inference, keyboard or microphone."""
import argparse
import hashlib
import importlib.metadata
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import time

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--receipt-dir', type=Path, required=True)
args = parser.parse_args()
assert os.environ.get('STREAM_DRY') == '1' and os.environ.get('STREAM_BACKEND') == 'cpu'
assert os.environ.get('STREAM_OUTPUT') == 'ibus' and os.environ.get('STREAM_QUIET') == '1'
assert not any(os.environ.get(x) for x in ['STREAM_TEST_INSERT', 'STREAM_TEST_WAV', 'STREAM_TEST_RAW', 'STREAM_KEEP'])
output = args.receipt_dir.resolve(); output.mkdir(mode=0o700, exist_ok=False)
source = output / 'evaluated-source'; source.mkdir()
HERE = Path(__file__).resolve().parent
for name in ['stream-dictate.py', 'dictation_model.py', 'dictation_status.py', 'dictation_resources.py', 'idle-expiry-smoke.py']:
    (source / name).write_bytes((HERE / name).read_bytes())
(source / 'machine.py').write_bytes((HERE.parent / 'local-ai/machine.py').read_bytes())
sys.path.insert(0, str(source))
from dictation_resources import load_policy, reasons, snapshot
spec = importlib.util.spec_from_file_location('idle_expiry_stream', source / 'stream-dictate.py')
stream = importlib.util.module_from_spec(spec); spec.loader.exec_module(stream)


def digest(path):
    value = hashlib.sha256()
    with path.open('rb') as handle:
        for block in iter(lambda: handle.read(1024**2), b''): value.update(block)
    return value.hexdigest()


def rss():
    return int(next(row.split()[1] for row in Path('/proc/self/status').read_text().splitlines()
                    if row.startswith('VmRSS:'))) * 1024


profile = Path.home() / '.config/mseries-ai/profiles.json'
report = {'complete': False, 'passed': False, 'state': 'waiting-for-quiet',
          'cohort': 'native-automatic-idle-expiry-v1', 'kernel': os.uname().release,
          'policy': load_policy(), 'profile_sha256': digest(profile),
          'source_sha256': {p.name: digest(p) for p in source.glob('*.py')},
          'microphone_recorded': False, 'keyboard_device_opened': False,
          'owner_windows_opened': False, 'inference_runs': 0, 'phases': []}


def save():
    temp = output / 'receipt.tmp'
    temp.write_text(json.dumps(report, indent=2) + '\n'); temp.chmod(0o600)
    os.replace(temp, output / 'receipt.json')


save()
stable = 0
while stable < 3:
    sample = snapshot()
    busy = subprocess.run(['pgrep', '-x', 'oha|rustc'], capture_output=True).returncode == 0
    ready = (not busy and not reasons(report['policy'], 1024**3, sample)
             and max(sample['fans_rpm'].values(), default=9999) < 2700
             and max(sample['temperatures_c'].values(), default=999) <= 63)
    stable = stable + 1 if ready else 0
    assert digest(profile) == report['profile_sha256'], 'Profile changed while waiting; inspect without mixed continuation'
    time.sleep(5)

d = None; samples = []
try:
    assert os.uname().release == report['kernel']
    report['model_sha256'] = digest(Path(stream.MODEL))
    report['native_library_sha256'] = digest(Path(os.environ['TRANSCRIBE_LIBRARY']))
    d = stream.Dictation()
    assert not d.models.loaded and 'transcribe_cpp' not in sys.modules
    report['phases'].append({'phase': 'before-native-import', 'rss_bytes': rss()})
    with d.models.use(lambda extra: not reasons(report['policy'], extra)) as model:
        report['phases'].append({'phase': 'native-model-resident', 'rss_bytes': rss()})
    report['versions'] = {'python': sys.version.split()[0], 'transcribe_cpp': importlib.metadata.version('transcribe_cpp'),
                          'numpy': importlib.metadata.version('numpy')}
    started = d.models.last_used
    report['state'] = 'waiting-for-automatic-expiry'; save()
    while d.models.loaded and time.monotonic() - started < 67:
        sample = snapshot(); samples.append(sample)
        assert digest(profile) == report['profile_sha256'] and os.uname().release == report['kernel']
        if reasons(report['policy'], sample=sample):
            report['interrupted'] = True
            raise RuntimeError('Owned idle test resource guard; no quality score')
        d.idle_tick()
        if d.models.loaded: time.sleep(1)
    elapsed = time.monotonic() - started
    assert not d.models.loaded and model._handle is None
    assert 60 <= elapsed <= 67, 'Release did not establish the configured timeout; inspect pressure and receipt'
    report['phases'].append({'phase': 'automatically-released', 'rss_bytes': rss()})
    report.update(complete=True, passed=True, state='complete', automatic_release_s=elapsed,
                  released_rss_bytes=report['phases'][1]['rss_bytes'] - rss(),
                  scope='Real sixty-second controller idle expiry and SDK handle close; no inference or physical F5 trial.')
except Exception as error:
    report['failure_kind'] = type(error).__name__
    raise
finally:
    if d: d.models.trim(force=True)
    if samples:
        report['resources'] = {'samples': len(samples), 'min_available_bytes': min(x['available_bytes'] for x in samples),
            'max_fan_rpm': max(max(x['fans_rpm'].values(), default=9999) for x in samples),
            'max_temp_c': max(max(x['temperatures_c'].values(), default=999) for x in samples)}
    save()
print(json.dumps({'passed': report['passed'], 'automatic_release_s': report['automatic_release_s']}))
