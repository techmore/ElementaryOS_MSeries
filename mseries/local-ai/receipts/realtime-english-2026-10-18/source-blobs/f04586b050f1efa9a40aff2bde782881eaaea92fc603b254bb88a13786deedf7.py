#!/usr/bin/python3
"""File-only first-sample/close and cancellable silent child; no speech inference."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys
import threading
import time

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--wav', type=Path, required=True)
parser.add_argument('--receipt-dir', type=Path, required=True)
args = parser.parse_args()
assert os.environ.get('STREAM_DRY') == '1' and os.environ.get('STREAM_QUIET') == '1'
assert not any(os.environ.get(x) for x in ['STREAM_TEST_INSERT', 'STREAM_TEST_RAW', 'STREAM_TEST_WAV', 'STREAM_KEEP'])
output = args.receipt_dir.resolve(); output.mkdir(mode=0o700, exist_ok=False)
source = output / 'evaluated-source'; source.mkdir()
HERE = Path(__file__).resolve().parent
for name in ['stream-dictate.py', 'dictation_model.py', 'dictation_resources.py', 'dictation_status.py', 'capture-startup-smoke.py']:
    (source / name).write_bytes((HERE / name).read_bytes())
(source / 'machine.py').write_bytes((HERE.parent / 'local-ai/machine.py').read_bytes())
sys.path.insert(0, str(source))
spec = importlib.util.spec_from_file_location('capture_startup_stream', source / 'stream-dictate.py')
stream = importlib.util.module_from_spec(spec); spec.loader.exec_module(stream)
report = {'complete': False, 'passed': False, 'inference_runs': 0, 'microphone_recorded': False,
          'keyboard_device_opened': False, 'owner_windows_opened': False,
          'source_sha256': {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in source.glob('*.py')},
          'wav_sha256': hashlib.sha256(args.wav.read_bytes()).hexdigest(), 'kernel': os.uname().release}
d = stream.Dictation(); cap = None
try:
    cap, first = d.open_capture(['ffmpeg', '-nostdin', '-re', '-v', 'error', '-i', str(args.wav.resolve()),
                                '-f', 's16le', '-ac', '1', '-ar', '16000', '-'])
    assert cap and 0 < len(first) <= stream.CHUNK * 2
    stream.Dictation.close_capture(cap)
    assert cap.poll() is not None and cap.stdout.closed
    report.update(public_file_first_bytes=len(first), owned_file_child_closed=True)
    cap = None
    original = stream.subprocess.Popen; children = []
    def track(*a, **kw):
        child = original(*a, **kw); children.append(child); return child
    stream.subprocess.Popen = track
    timer = threading.Timer(.15, d.stop_evt.set); timer.start(); started = time.monotonic()
    try:
        assert d.open_capture([sys.executable, '-c', 'import time; time.sleep(60)']) == (None, None)
        assert len(children) == 1 and children[0].poll() is not None and children[0].stdout.closed
        report.update(release_during_first_read_closed_child=True, cancel_elapsed_s=time.monotonic() - started)
    finally:
        timer.cancel(); stream.subprocess.Popen = original
        for child in children:
            if child.poll() is None: stream.Dictation.close_capture(child)
    assert 'transcribe_cpp' not in sys.modules and not d.models.loaded
    report.update(complete=True, passed=True,
                  scope='Real public-file ffmpeg startup/close and cancellation of one owned silent Python child; no model, microphone or keyboard.')
except Exception as error:
    report['failure_kind'] = type(error).__name__
    raise
finally:
    if cap and cap.poll() is None: stream.Dictation.close_capture(cap)
    path = output / 'receipt.json'; path.write_text(json.dumps(report, indent=2) + '\n'); path.chmod(0o600)
print(json.dumps({'passed': report['passed'], 'inference_runs': 0}))
