#!/usr/bin/python3
"""Public English WAV → real CPU ASR → GTK4 question → existing4B → English WAV.

This joined workflow deliberately updates the question widget from actual ASR
results, as the earlier English panel harness did. It does NOT claim physical
F5 or IBus insertion acceptance; those have separate app-input qualifications.
The actual Voice Assistant completion gate and VoiceSession run unchanged except
speech is redirected to files. No microphone, playback, tool action or owner UI.
Run only under the root qualification queue's serialized quiet-admission lock.
"""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import threading
import time
import wave

HERE = Path(__file__).resolve().parent


def sha(path):
    value = hashlib.sha256()
    with Path(path).open('rb') as stream:
        while chunk := stream.read(8 * 1024 * 1024): value.update(chunk)
    return value.hexdigest()


def parse():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--receipt-dir', type=Path, required=True)
    parser.add_argument('--model', type=Path, required=True, help='Qualified CPU Nemotron Q8 port')
    parser.add_argument('--wav', type=Path, default=Path.home()/'.local/share/mseries/stream/libri.wav')
    parser.add_argument('--asr-python', type=Path, default=Path.home()/'.local/share/mseries/stream/venv/bin/python')
    parser.add_argument('--asr-library', type=Path, default=Path.home()/'.local/share/mseries/stream/native/transcribe-native-linux-aarch64-cpu-vulkan/libtranscribe.so')
    parser.add_argument('--asr-worker', action='store_true', help=argparse.SUPPRESS)
    return parser.parse_args()


def asr_worker(args):
    import numpy as np
    import transcribe_cpp as tc
    with wave.open(str(args.wav)) as wav:
        if (wav.getframerate(), wav.getnchannels(), wav.getsampwidth()) != (16000, 1, 2):
            raise ValueError('Expected16kHz mono signed16bit public PCM WAV')
        pcm = np.frombuffer(wav.readframes(wav.getnframes()), '<i2').astype(np.float32) / 32768
    loaded = time.monotonic()
    with tc.Model(str(args.model), backend='cpu') as model, model.session(n_threads=4) as session, session.stream(family=tc.ParakeetStreamOptions(att_context_right=1)) as stream:
        start, previous = time.monotonic(), ''
        print(json.dumps({'kind': 'audio-start', 'monotonic_s': start, 'duration_s': len(pcm)/16000,
                          'load_s': start-loaded}), flush=True)
        for offset in range(0, len(pcm), 1600):
            chunk = pcm[offset:offset+1600]
            time.sleep(max(0, start+(offset+len(chunk))/16000-time.monotonic()))
            stream.feed(chunk)
            text = stream.text().display.strip()
            if text != previous:
                print(json.dumps({'kind': 'text', 'text': text, 'final': False,
                                  'monotonic_s': time.monotonic(), 'audio_fed_s': (offset+len(chunk))/16000}), flush=True)
                previous = text
        stream.finalize()
        print(json.dumps({'kind': 'text', 'text': stream.text().display.strip(), 'final': True,
                          'monotonic_s': time.monotonic(), 'audio_fed_s': len(pcm)/16000}), flush=True)
    return 0


def isolated(args):
    root = args.receipt_dir.resolve()
    root.mkdir(mode=0o700, parents=True, exist_ok=False)
    source = root/'evaluated-source/dictation'; source.mkdir(parents=True)
    local_ai = source.parent/'local-ai'; local_ai.mkdir()
    names = ['voice-workflow-smoke.py', 'voice-assistant.py', 'dictation_voice.py',
             'dictation_status.py', 'dictation_resources.py', 'dictation_review.py',
             'review-smoke.py', 'realtime-bench.py']
    for name in names: (source/name).write_bytes((HERE/name).read_bytes())
    (local_ai/'machine.py').write_bytes((HERE.parent/'local-ai/machine.py').read_bytes())
    owner_bus = os.environ.get('DBUS_SESSION_BUS_ADDRESS', 'unix:path=/run/user/'+str(os.getuid())+'/bus')
    with tempfile.TemporaryDirectory(prefix='mseries-voice-workflow-') as directory:
        private = Path(directory)
        env = dict(os.environ)
        for key in ('DISPLAY', 'WAYLAND_DISPLAY', 'XAUTHORITY', 'DBUS_SESSION_BUS_ADDRESS',
                    'AT_SPI_BUS_ADDRESS', 'IBUS_ADDRESS'):
            env.pop(key, None)
        for variable, name in [('XDG_RUNTIME_DIR', 'runtime'), ('XDG_CONFIG_HOME', 'config'),
                               ('XDG_CACHE_HOME', 'cache'), ('XDG_DATA_HOME', 'data'),
                               ('XDG_STATE_HOME', 'state')]:
            path = private/name; path.mkdir(mode=0o700); env[variable] = str(path)
        env.update(MSERIES_VOICE_WORKFLOW_PRIVATE='1', MSERIES_VOICE_OWNER_BUS=owner_bus,
                   GSETTINGS_BACKEND='memory', GSK_RENDERER='cairo', GDK_BACKEND='x11',
                   NO_AT_BRIDGE='1', GTK_A11Y='none', GTK_USE_PORTAL='0', GIO_USE_VFS='local')
        config = private/'session.conf'
        config.write_text('<busconfig><type>session</type><listen>unix:tmpdir=/tmp</listen>'
                          '<auth>EXTERNAL</auth><policy context="default">'
                          '<allow send_destination="*"/><allow receive_sender="*"/>'
                          '<allow own="*"/></policy></busconfig>')
        return subprocess.run(['dbus-run-session', '--config-file='+str(config), '--',
                               'xvfb-run', '-a', sys.executable, str(source/Path(__file__).name),
                               *sys.argv[1:]], env=env).returncode


def workflow(args):
    root = args.receipt_dir.resolve()
    assert os.environ.get('MSERIES_VOICE_WORKFLOW_PRIVATE') == '1'
    assert os.environ.get('GSETTINGS_BACKEND') == 'memory'
    sys.path.insert(0, str(HERE)); sys.path.insert(0, str(HERE.parent/'local-ai'))
    import dictation_status
    import dictation_voice
    from dictation_resources import snapshot, reasons
    # The only owner-session D-Bus operation is a read-only active-state check.
    # Speech, HTTP and ASR never start/stop services or change the active profile.
    original_run = subprocess.run
    def service_check(command, *positional, **keywords):
        if isinstance(command, (list, tuple)) and command and command[0] == 'systemctl':
            if list(command) != ['systemctl', '--user', 'is-active', '--quiet', 'mseries-ai-everyday.service']:
                raise RuntimeError('Qualification refuses service mutations or another profile')
            keywords['env'] = dict(os.environ, DBUS_SESSION_BUS_ADDRESS=os.environ['MSERIES_VOICE_OWNER_BUS'])
        return original_run(command, *positional, **keywords)
    subprocess.run = service_check
    spec = importlib.util.spec_from_file_location('voice_workflow_metadata', HERE/'review-smoke.py')
    bench = importlib.util.module_from_spec(spec); spec.loader.exec_module(bench)
    identity = bench.metadata()
    dictation_voice.quiet_guard()
    # Verify the expected existing model BEFORE the source text is submitted.
    review = bench.review
    opener = review.urllib.request.build_opener(review.urllib.request.ProxyHandler({}), review.NoRedirect())
    rows = review.request(opener, '/models', timeout=4)['data']
    model, = [row['id'] for row in rows]
    if not model.endswith('/'+bench.MODEL_REVISION):
        raise RuntimeError('Existing endpoint differs from the qualified default; preserve the owner profile')
    policy = dict(identity['policy']); policy['reserve_gib'] = max(6, policy.get('reserve_gib', 6))
    report = {'schema': 1, 'complete': False, 'passed': False, 'language': 'English',
              'scope': 'Joined public-file CPU Nemotron ASR -> direct question-widget updates -> actual GTK4 focused-F5-completion gate -> real existing4B VoiceSession -> English WAV files. Direct widget updates are not IBus/physical-key acceptance.',
              'microphone_recorded': False, 'owner_windows_opened': False, 'audio_playback': False,
              'app_insertion_claim': False, 'tools': False, 'runtime': identity,
              'model_sha256': sha(args.model), 'wav_sha256': sha(args.wav),
              'asr_library_sha256': sha(args.asr_library),
              'source_sha256': {path.relative_to(HERE.parent).as_posix(): sha(path) for path in HERE.parent.rglob('*.py')},
              'source_events': [], 'reply_events': [], 'voice_stages': []}
    spec = importlib.util.spec_from_file_location('joined_voice_panel', HERE/'voice-assistant.py')
    panel = importlib.util.module_from_spec(spec); spec.loader.exec_module(panel)
    import gi
    gi.require_version('Gtk', '4.0')
    from gi.repository import GLib
    started, phase = time.monotonic(), ['ready']
    stop, asr_error, asr_final = threading.Event(), [], threading.Event()
    asr, reader, app = None, None, None
    sessions, samples = [], []
    next_sample = 0
    checkpoint_lock = threading.Lock()
    def checkpoint():
        with checkpoint_lock:
            tmp = root/'receipt.tmp'
            with tmp.open('w') as stream:
                os.fchmod(stream.fileno(), 0o600); json.dump(report, stream, indent=2)
            tmp.replace(root/'receipt.json')
    def pump(seconds=.05):
        nonlocal next_sample
        until = time.monotonic()+seconds
        while time.monotonic() < until:
            while GLib.MainContext.default().pending(): GLib.MainContext.default().iteration(False)
            if asr_error: raise RuntimeError('Owned ASR event stream failed: '+asr_error[0])
            if time.monotonic() >= next_sample:
                measured = snapshot(); samples.append(measured); next_sample = time.monotonic()+.5
                if (reasons(policy, 0, measured)
                        or max(measured['fans_rpm'].values(), default=9999) >= 2700
                        or max(measured['temperatures_c'].values(), default=999) >= 63):
                    report['interruption'] = 'quiet-or-reserve-guard'
                    raise RuntimeError('Quiet policy interrupted owned joined workflow')
            time.sleep(.005)
    def until(condition, timeout):
        end = time.monotonic()+timeout
        while not condition():
            if time.monotonic() >= end: raise TimeoutError('Owned joined workflow exceeded its bound')
            pump()
    class FileOnlySession(dictation_voice.VoiceSession):
        def __init__(self): super().__init__(); sessions.append(self)
        def run(self, text, *, on_text, speak):
            stage = {'source': text, 'started_s': time.monotonic()-started,
                     'requested_by_actual_ui': True, 'speech_phase_at_start': phase[0], 'completed': False}
            report['voice_stages'].append(stage)
            try:
                if not speak: raise RuntimeError('UI did not request its explicit spoken-reply flow')
                value = super().run(text, on_text=on_text, speak=False, wav_dir=root/'english-wav')
                stage.update(value, voice_clock_origin_s=self.started-started)
                return value
            except Exception as error:
                stage.update(failure_kind=type(error).__name__, failure_detail=str(error)[:300]); raise
            finally: checkpoint()
    panel.VoiceSession = FileOnlySession
    dictation_status.read_status = lambda: {'phase': phase[0], 'pid': os.getpid(), 'updated_at': time.time()}
    checkpoint()
    try:
        app = panel.application_class()()
        assert app.register(None); app.activate()
        report['automatic_default_off'] = not app.automatic.get_active()
        assert report['automatic_default_off']
        app.automatic.set_active(True)  # Deliberately enable only this isolated test instance.
        app.original.grab_focus(); pump(.2)
        def shown(_):
            report['reply_events'].append({'wall_s': time.monotonic()-started, 'text': app.text(app.reply),
                                           'speech_phase': phase[0]})
        app.reply.get_buffer().connect('changed', shown)
        phase[0] = 'listening'; app.poll()
        if app.window.get_focus() != app.original: raise RuntimeError('Private question focus unavailable')
        environment = dict(os.environ, TRANSCRIBE_LIBRARY=str(args.asr_library), OMP_NUM_THREADS='4', OPENBLAS_NUM_THREADS='1')
        log = (root/'private-asr.log').open('w')
        asr = subprocess.Popen([str(args.asr_python), '-u', str(Path(__file__).resolve()), *sys.argv[1:], '--asr-worker'],
                               stdout=subprocess.PIPE, stderr=log, text=True, env=environment, start_new_session=True)
        log.close()
        def read():
            try:
                for line in asr.stdout:
                    if len(line) > 8192: raise RuntimeError('ASR event size bound exceeded')
                    row = json.loads(line)
                    def update(row=row):
                        if stop.is_set(): return False
                        if row['kind'] == 'audio-start':
                            report['audio_start_s'] = row['monotonic_s']-started
                            report['audio_duration_s'] = row['duration_s']; report['asr_load_s'] = row['load_s']
                        else:
                            app.original.get_buffer().set_text(row['text'])
                            report['source_events'].append({**row, 'widget_wall_s': time.monotonic()-started})
                            if row['final']:
                                phase[0] = 'finishing'; asr_final.set()
                            app.poll()
                        return False
                    GLib.idle_add(update)
            except Exception as error: asr_error.append(type(error).__name__)
        reader = threading.Thread(target=read, daemon=True); reader.start()
        until(lambda: asr.poll() is not None and asr_final.is_set(), 70)
        if asr.returncode: raise RuntimeError('Owned CPU ASR failed')
        reader.join(2)
        report['asr_process_finished_s'] = time.monotonic()-started
        phase[0] = 'ready'; app.poll()
        until(lambda: len(report['voice_stages']) == 1 and app.session is None, 100)
        stage, = report['voice_stages']
        if not stage.get('completed'): raise RuntimeError('Joined local voice stage failed')
        if stage['speech_phase_at_start'] != 'ready': raise RuntimeError('Voice began before final original text')
        original, reply = app.text(app.original), app.text(app.reply)
        assert original == report['source_events'][-1]['text'] == stage['source']
        assert reply == stage['reply'] and reply.strip()
        assert stage['audio_files'] and not stage['playback']
        wave_checks = []
        for path in stage['audio_files']:
            with wave.open(path) as audio:
                raw = audio.readframes(audio.getnframes())
                assert audio.getnframes() > 0 and raw and any(raw)
                wave_checks.append({'name': Path(path).name, 'sha256': sha(path),
                                    'frames': audio.getnframes(), 'sample_rate': audio.getframerate(),
                                    'duration_s': audio.getnframes()/audio.getframerate()})
        spec = importlib.util.spec_from_file_location('joined_metrics', HERE/'realtime-bench.py')
        metrics = importlib.util.module_from_spec(spec); spec.loader.exec_module(metrics)
        audio_end = report['audio_start_s']+report['audio_duration_s']
        first_question = next(row['widget_wall_s'] for row in report['source_events'] if row['text'].strip())
        first_reply = next(row['wall_s'] for row in report['reply_events'] if row['text'].strip())
        report.update(complete=True, passed=True, original_preserved=True,
                      final_question=original, final_reply=reply, normalized_asr_wer=metrics.wer(metrics.REFERENCE, original),
                      first_question_from_audio_start_s=first_question-report['audio_start_s'],
                      first_question_before_audio_end=first_question<audio_end,
                      first_reply_after_audio_end_s=first_reply-audio_end,
                      first_token_after_audio_end_s=stage['voice_clock_origin_s']+stage['first_token_s']-audio_end,
                      first_wav_after_audio_end_s=stage['voice_clock_origin_s']+stage['first_wav_s']-audio_end,
                      wav_checks=wave_checks, no_duplicate_voice_request=len(report['voice_stages'])==1,
                      profile_runtime_unchanged=bench.metadata()==identity)
        assert report['first_question_before_audio_end'] and report['profile_runtime_unchanged']
        checkpoint()
    except Exception as error:
        report.update(failure_kind=type(error).__name__, failure_detail=str(error)[:300],
                      quality_score=None, functional_result=False)
        raise
    finally:
        stop.set()
        for session in sessions: session.cancel()
        if asr is not None and asr.poll() is None:
            os.killpg(asr.pid, signal.SIGTERM)
            try: asr.wait(2)
            except subprocess.TimeoutExpired: os.killpg(asr.pid, signal.SIGKILL); asr.wait(2)
        if reader is not None: reader.join(2)
        if app is not None: app.window.close(); app.quit()
        if samples:
            report['resources'] = {'samples': len(samples), 'min_available_bytes': min(row['available_bytes'] for row in samples),
                                   'max_fan_rpm': max(max(row['fans_rpm'].values(), default=9999) for row in samples),
                                   'max_temp_c': max(max(row['temperatures_c'].values(), default=999) for row in samples)}
        checkpoint()
        subprocess.run = original_run
    return 0


def main():
    args = parse()
    if args.asr_worker: return asr_worker(args)
    if os.environ.get('MSERIES_VOICE_WORKFLOW_PRIVATE') != '1': return isolated(args)
    return workflow(args)


if __name__ == '__main__': raise SystemExit(main())
