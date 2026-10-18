#!/usr/bin/python3
"""Resident-model CPU/MLX English cache-aware comparison; file input only.

Both paths receive identical wall-paced 100ms PCM, context right=1 (160ms
operating point). The public clip is repeated whole six times by default.
No warm-up result is discarded: trial one is the first resident decode;
trial two reuses the exact model. An external supervisor owns quiet admission,
thermal/memory guards, serialized inference and cancellation of this process.
"""
import argparse
import hashlib
import importlib.util
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import resource
import sys
import threading
import time
import wave


def digest(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        while chunk := stream.read(8 * 1024 * 1024): h.update(chunk)
    return h.hexdigest()


def task_cpu():
    """Linux per-thread CPU work, including native inference/driver threads."""
    ticks = os.sysconf('SC_CLK_TCK')
    result = {}
    for task in Path('/proc/self/task').glob('*'):
        try:
            fields = (task / 'stat').read_text().rsplit(') ', 1)[1].split()
            result[task.name] = {'cpu_s': (int(fields[11]) + int(fields[12])) / ticks,
                                 'name': (task / 'comm').read_text().strip()}
        except (OSError, ValueError, IndexError): pass
    return result


def rss():
    return int(Path('/proc/self/statm').read_text().split()[1]) * os.sysconf('SC_PAGE_SIZE')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--engine', choices=('cpu', 'mlx'), required=True)
    for name in ('wav', 'model', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--modules', type=Path, help='Pinned scratch mlx-audio0.5.9 overlay (MLX only)')
    parser.add_argument('--reference-file', type=Path)
    parser.add_argument('--model-pin', type=Path)
    parser.add_argument('--trials', type=int, default=2)
    parser.add_argument('--repeats', type=int, default=6)
    parser.add_argument('--duration', type=float, help='Approximate duration of whole repeated clips; effective duration is recorded')
    args = parser.parse_args()
    if args.output.exists(): raise SystemExit('Retain existing completed or interrupted evidence')
    if not 1 <= args.trials <= 4 or not 1 <= args.repeats <= 20:
        raise SystemExit('Use1..4trials and1..20whole clip repeats')
    if args.engine == 'mlx' and args.modules is None:
        raise SystemExit('--modules is required for the MLX scratch overlay')
    data = {'complete': False, 'engine': args.engine, 'kernel': platform.release(),
            'python': sys.version, 'harness_sha256': digest(Path(__file__)),
            'microphone_recorded': False, 'owner_windows_opened': False,
            'requested_duration_s': args.duration, 'feed_chunk_s': .1,
            'attention_context_right': 1, 'requested_chunk_mode_ms': 160,
            'scope': 'Repeated clean public file; cache-aware API; no prefix re-decoding, microphone, app insertion or general accuracy claim. First resident trial is retained; model is reused unchanged.',
            'trials': []}

    def checkpoint():
        tmp = args.output.with_suffix('.tmp')
        tmp.write_text(json.dumps(data, indent=2) + '\n'); tmp.replace(args.output)

    checkpoint()
    model = None
    try:
        imports = time.monotonic()
        import numpy as np
        spec = importlib.util.spec_from_file_location('realtime_metrics', Path(__file__).with_name('realtime-bench.py'))
        metrics = importlib.util.module_from_spec(spec); spec.loader.exec_module(metrics)
        with wave.open(str(args.wav)) as audio:
            if (audio.getframerate(), audio.getnchannels(), audio.getsampwidth()) != (16000, 1, 2):
                raise ValueError('Expected16kHz mono signed16bit PCM WAV')
            single = np.frombuffer(audio.readframes(audio.getnframes()), '<i2').astype(np.float32) / 32768
        if not len(single): raise ValueError('The public WAV is empty')
        duration_single = len(single) / 16000
        repeats = args.repeats
        if args.duration is not None:
            repeats = round(args.duration / duration_single)
            if not 1 <= repeats <= 20 or abs(args.duration - repeats * duration_single) > .1:
                raise ValueError('--duration must approximate a whole number of public clips (within0.1s)')
        pcm = np.tile(single, repeats)
        reference_single = args.reference_file.read_text().strip() if args.reference_file else metrics.REFERENCE
        reference = ' '.join([reference_single] * repeats)
        duration = len(pcm) / 16000
        data.update({'single_audio_duration_s': duration_single, 'audio_duration_s': duration,
                     'audio_sha256': digest(args.wav), 'repeats': repeats,
                     'reference': reference, 'reference_words': len(metrics.normalized(reference))})
        if args.engine == 'cpu':
            import transcribe_cpp as tc
            data['transcribe_cpp_version'] = importlib.metadata.version('transcribe-cpp')
            data['model_sha256'] = digest(args.model)
            if args.model_pin: data['model_source_pin'] = json.loads(args.model_pin.read_text())
            data['threads_requested'] = 4
        else:
            os.environ['HF_HUB_OFFLINE'] = '1'
            sys.path.insert(0, str(args.modules))
            import mlx.core as mx
            if importlib.metadata.version('mlx-audio') != '0.5.9':
                raise RuntimeError('Requires pinned scratch mlx-audio0.5.9')
            # Same lazy family import as upstream's MIT GPU worker and our
            # short-file probe: avoid unrelated Granite CPU float64 setup.
            family = 'mlx_audio.stt.models'
            spec = importlib.util.find_spec(family)
            sys.modules[family] = importlib.util.module_from_spec(spec)
            from mlx_audio.stt.utils import load_model
            data.update({'mlx_version': mx.__version__, 'mlx_audio_version': '0.5.9',
                         'model_source_pin': json.loads((args.model / 'source-pin.json').read_text()),
                         'runtime_source_pin': json.loads((args.modules / 'source-pin.json').read_text()),
                         'mlx_cpu_dispatch_instrumented': False})
        data['import_and_asset_verification_s'] = time.monotonic() - imports
        loaded = time.monotonic()
        if args.engine == 'cpu':
            model = tc.Model(str(args.model), backend='cpu')
        else:
            with mx.stream(mx.gpu): model = load_model(args.model, strict=True)
            model.default_att_context_size = [70, 1]
            data['model_type'] = model.model_type
            data['attention_context'] = model.default_att_context_size
        data['load_s'] = time.monotonic() - loaded
        checkpoint()
        for index in range(args.trials):
            trial = {'run': index + 1, 'complete': False,
                     'resident_state': 'first_decode_after_load' if index == 0 else 'same_model_retained_after_previous_trial',
                     'events': [], 'feed_events': [], 'ten_second_intervals': [],
                     'first_text_s': None, 'final_text': '', 'normalized_wer': None}
            data['trials'].append(trial)
            checkpoint()
            events, feeds = trial['events'], trial['feed_events']
            text, decode_s = '', 0.0
            baseline_threads = task_cpu()
            peak_rss, thread_max = [rss()], {}
            sample_stop = threading.Event()

            def sample():
                while not sample_stop.wait(.1):
                    try: peak_rss[0] = max(peak_rss[0], rss())
                    except OSError: pass
                    for tid, row in task_cpu().items():
                        old = thread_max.get(tid, {'cpu_s': 0})
                        if row['cpu_s'] >= old['cpu_s']: thread_max[tid] = row

            sampler = threading.Thread(target=sample, daemon=True); sampler.start()
            if args.engine == 'mlx': mx.reset_peak_memory()
            process_start = time.process_time()
            start = time.monotonic()
            next_checkpoint = 10
            fed = {'samples': 0, 'finished_s': None}

            def record(value, final=False):
                nonlocal text
                if value != text or final:
                    text = value
                    events.append({'wall_s': time.monotonic() - start,
                                   'audio_fed_s': fed['samples'] / 16000,
                                   'text': text, 'final': final})

            def feed_record(offset, chunk, call):
                due = start + (offset + len(chunk)) / 16000
                time.sleep(max(0, due - time.monotonic()))
                before = time.monotonic()
                call(chunk)
                after = time.monotonic()
                fed['samples'] += len(chunk)
                feeds.append({'audio_end_s': fed['samples'] / 16000,
                              'wall_start_s': before - start, 'wall_end_s': after - start,
                              'feed_call_s': after - before, 'lateness_s': max(0, before - due)})

            try:
                if args.engine == 'cpu':
                    with model.session(n_threads=4) as session, session.stream(family=tc.ParakeetStreamOptions(att_context_right=1)) as stream:
                        for offset in range(0, len(pcm), 1600):
                            def cpu_feed(chunk): stream.feed(chunk)
                            feed_record(offset, pcm[offset:offset + 1600], cpu_feed)
                            decode_s += feeds[-1]['feed_call_s']
                            record(stream.text().display)
                            if time.monotonic() - start >= next_checkpoint:
                                next_checkpoint += 10; checkpoint()
                        fed['finished_s'] = time.monotonic() - start
                        before = time.monotonic(); stream.finalize(); decode_s += time.monotonic() - before
                        record(stream.text().display, True)
                else:
                    with mx.stream(mx.gpu):
                        session = model.create_streaming_session(temperature=0.0, language='en')
                    stop, errors = threading.Event(), []
                    def feeder():
                        try:
                            for offset in range(0, len(pcm), 1600):
                                if stop.is_set(): return
                                feed_record(offset, pcm[offset:offset + 1600], session.feed)
                            session.close(); fed['finished_s'] = time.monotonic() - start
                        except Exception as error: errors.append(error)
                    thread = threading.Thread(target=feeder, daemon=True); thread.start()
                    try:
                        while not session.done:
                            if errors: raise errors[0]
                            if time.monotonic() - start > duration * 3 + 30:
                                raise TimeoutError('Sustained session exceeded its bound')
                            before = time.monotonic()
                            with mx.stream(mx.gpu): deltas = session.step(max_decode_tokens=4)
                            decode_s += time.monotonic() - before
                            if deltas: record(text + ''.join(deltas))
                            else: time.sleep(.002)
                            if time.monotonic() - start >= next_checkpoint:
                                next_checkpoint += 10; checkpoint()
                        record(text, True)
                    finally:
                        stop.set(); session.cancel(); thread.join(2)
                        if thread.is_alive(): raise RuntimeError('MLX feeder did not exit after cancellation')
                elapsed, cpu_s = time.monotonic() - start, time.process_time() - process_start
            finally:
                sample_stop.set(); sampler.join(1)
                peak_rss[0] = max(peak_rss[0], rss())
                for tid, row in task_cpu().items():
                    old = thread_max.get(tid, {'cpu_s': 0})
                    if row['cpu_s'] >= old['cpu_s']: thread_max[tid] = row
            for tid, row in thread_max.items():
                row['work_s'] = max(0, row['cpu_s'] - baseline_threads.get(tid, {'cpu_s': 0})['cpu_s'])
            for lo in range(0, int(duration) + 1, 10):
                hi = min(lo + 10, duration)
                chosen_feeds = [row for row in feeds if lo < row['audio_end_s'] <= hi]
                chosen_events = [row for row in events if lo <= row['wall_s'] < lo + 10]
                if hi > lo:
                    trial['ten_second_intervals'].append({
                        'source_audio_start_s': lo, 'source_audio_end_s': hi,
                        'feed_count': len(chosen_feeds),
                        'feed_compute_s': sum(row['feed_call_s'] for row in chosen_feeds),
                        'max_feed_lateness_s': max((row['lateness_s'] for row in chosen_feeds), default=None),
                        'display_updates_in_wall_interval': len(chosen_events),
                        'last_feed_wall_s': chosen_feeds[-1]['wall_end_s'] if chosen_feeds else None})
            trial.update({'complete': True, 'first_text_s': next((row['wall_s'] for row in events if row['text'].strip()), None),
                          'audio_feed_finished_s': fed['finished_s'], 'final_after_audio_s': elapsed - duration,
                          'elapsed_s': elapsed, 'cpu_s': cpu_s, 'cpu_s_per_audio_s': cpu_s / duration,
                          'decode_call_wall_s': decode_s, 'decode_call_note': 'API wall time; MLX includes no-op step polls, CPU includes feed/finalize',
                          'peak_sampled_rss_bytes': peak_rss[0],
                          'lifetime_peak_rss_bytes': resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024,
                          'thread_work': thread_max, 'thread_work_sum_s': sum(row['work_s'] for row in thread_max.values()),
                          'final_text': text, 'normalized_wer': metrics.wer(reference, text)})
            if args.engine == 'mlx': trial['mlx_peak_memory_bytes'] = int(mx.get_peak_memory())
            checkpoint()
        data['complete'] = True
        checkpoint()
    except Exception as error:
        data.update({'failure_kind': type(error).__name__, 'failure_detail': str(error)[:1200], 'quality_score': None})
        checkpoint()
        raise
    finally:
        if args.engine == 'cpu' and model is not None: model.close()


if __name__ == '__main__': main()
