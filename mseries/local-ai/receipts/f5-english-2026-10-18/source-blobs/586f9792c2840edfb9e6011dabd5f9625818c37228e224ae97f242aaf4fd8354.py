"""Real private subprocesses exercise framing/lifecycle; no speech model or device."""
import importlib.util
from pathlib import Path
import sys
import threading
import time
import unittest

spec = importlib.util.spec_from_file_location('dictation_ane', Path(__file__).with_name('dictation_ane.py'))
ane = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ane)

WORKER = r'''
import json, os, signal, struct, subprocess, sys, time
mode = sys.argv[1]
child = None
if mode == 'descendant':
    child = subprocess.Popen([sys.executable, '-c', 'import signal,time; signal.signal(signal.SIGTERM,signal.SIG_IGN); time.sleep(60)'])
    time.sleep(.05)
if mode == 'blocked-write':
    time.sleep(60)
if mode == 'ignore-term':
    signal.signal(signal.SIGTERM, signal.SIG_IGN)
def exact(n):
    data = b''
    while len(data) < n:
        more = sys.stdin.buffer.read(n - len(data))
        if not more: sys.exit(0)
        data += more
    return data
while True:
    h = json.loads(exact(struct.unpack('<Q', exact(8))[0]))
    p = exact(h.get('payload_bytes', 0))
    if mode == 'crash': os._exit(7)
    if mode in ('hang', 'ignore-term'): time.sleep(60)
    if mode == 'delay': time.sleep(.25)
    if mode == 'short':
        sys.stdout.buffer.write(struct.pack('<Q', 100) + b'{'); sys.stdout.buffer.flush(); os._exit(0)
    if mode == 'oversized':
        sys.stdout.buffer.write(struct.pack('<Q', 2**63)); sys.stdout.buffer.flush(); time.sleep(60)
    r = {'id': h['id'], 'ok': True, 'transcript': 'English words', 'received': len(p)}
    if child is not None: r['child_pid'] = child.pid
    if mode == 'wrong-id': r['id'] += 1
    if mode == 'bool-id': r['id'] = True
    if mode == 'wrong-status': r['ok'] = 1
    if mode == 'payload-negative': r['payload_bytes'] = -1
    if mode == 'payload-bool': r['payload_bytes'] = True
    if mode == 'payload-oversized': r['payload_bytes'] = 2**63
    if mode == 'payload-valid': r['payload_bytes'] = 3
    b = json.dumps(r).encode() if mode != 'invalid-json' else b'not json'
    framed = struct.pack('<Q', len(b)) + b + (b'abc' if mode == 'payload-valid' else b'')
    # Deliberately fragment length, JSON and trailing payload writes.
    for offset in range(0, len(framed), 3):
        sys.stdout.buffer.write(framed[offset:offset + 3]); sys.stdout.buffer.flush()
'''


class WorkerIPC(unittest.TestCase):
    def worker(self, mode='normal'):
        worker = ane.FramedWorker([sys.executable, '-u', '-c', WORKER, mode])
        self.addCleanup(worker.close)
        return worker

    def assert_reaped(self, worker):
        self.assertTrue(worker.closed)
        self.assertIsNotNone(worker.p.poll())
        self.assertTrue(worker.p.stdin.closed)
        self.assertTrue(worker.p.stdout.closed)

    def test_fragmented_reply_and_trailing_payload_preserve_next_frame(self):
        worker = self.worker('payload-valid')
        for i in range(1, 4):
            reply = worker.request({'op': 'transcribe'}, b'12345678', deadline_ms=1000)
            self.assertEqual((reply['id'], reply['received'], reply['transcript']), (i, 8, 'English words'))
        self.assertFalse(worker.closed)

    def test_peer_crash_and_truncated_reply_are_terminal(self):
        for mode in ('crash', 'short'):
            with self.subTest(mode=mode):
                worker = self.worker(mode)
                with self.assertRaisesRegex(RuntimeError, 'complete reply'):
                    worker.request({'op': 'transcribe'}, deadline_ms=1000)
                self.assert_reaped(worker)
                with self.assertRaises(ane.WorkerClosed):
                    worker.request({'op': 'transcribe'})

    def test_untrusted_size_identity_status_and_json_are_rejected_without_allocation(self):
        for mode in ('oversized', 'wrong-id', 'bool-id', 'wrong-status', 'invalid-json',
                     'payload-negative', 'payload-bool', 'payload-oversized'):
            with self.subTest(mode=mode):
                worker = self.worker(mode)
                start = time.monotonic()
                with self.assertRaises(RuntimeError):
                    worker.request({'op': 'transcribe'}, deadline_ms=1000)
                self.assertLess(time.monotonic() - start, 2)
                self.assert_reaped(worker)

    def test_reply_timeout_is_enforced_locally_and_worker_reaped(self):
        worker = self.worker('hang')
        start = time.monotonic()
        with self.assertRaises(TimeoutError):
            worker.request({'op': 'transcribe'}, deadline_ms=100)
        self.assertLess(time.monotonic() - start, 1)
        self.assert_reaped(worker)

    def test_audio_write_is_bounded_when_peer_never_reads(self):
        worker = self.worker('blocked-write')
        start = time.monotonic()
        with self.assertRaises(TimeoutError):
            worker.request({'op': 'transcribe'}, b'\0' * (1024 * 1024), deadline_ms=100)
        self.assertLess(time.monotonic() - start, 1)
        self.assert_reaped(worker)

    def test_lock_wait_timeout_does_not_abort_inflight_or_corrupt_next_reply(self):
        worker = self.worker('delay')
        results = []
        def first():
            results.append(worker.request({'op': 'transcribe'}, deadline_ms=2000))
        thread = threading.Thread(target=first)
        thread.start()
        self.addCleanup(thread.join, 2)
        deadline = time.monotonic() + 1
        while not worker.lock.locked() and time.monotonic() < deadline:
            time.sleep(.001)
        self.assertTrue(worker.lock.locked())
        with self.assertRaises(TimeoutError):
            worker.request({'op': 'transcribe'}, deadline_ms=50)
        thread.join(2)
        self.assertFalse(thread.is_alive())
        self.assertEqual(results[0]['id'], 1)
        self.assertFalse(worker.closed)
        self.assertEqual(worker.request({'op': 'transcribe'}, deadline_ms=1000)['id'], 2)

    def test_cancel_aborts_inflight_and_queued_calls_without_waiting_for_lock(self):
        worker = self.worker('ignore-term')
        results = []
        def request():
            try:
                worker.request({'op': 'transcribe'})
            except Exception as error:
                results.append(type(error))
        threads = [threading.Thread(target=request) for _ in range(3)]
        for thread in threads: thread.start()
        self.addCleanup(lambda: [thread.join(2) for thread in threads])
        deadline = time.monotonic() + 1
        while not worker.lock.locked() and time.monotonic() < deadline:
            time.sleep(.001)
        # Let the child install its SIGTERM handler, forcing bounded escalation.
        time.sleep(.05)
        start = time.monotonic()
        closers = [threading.Thread(target=worker.cancel) for _ in range(3)]
        for closer in closers: closer.start()
        for closer in closers: closer.join(2)
        for thread in threads: thread.join(2)
        self.assertLess(time.monotonic() - start, 2)
        self.assertTrue(all(not thread.is_alive() for thread in [*threads, *closers]))
        self.assertEqual(results, [ane.WorkerClosed] * 3)
        self.assert_reaped(worker)
        worker.close()  # Repeated close remains safe after all pipes are closed.

    def test_close_kills_only_its_owned_descendant_group(self):
        worker = self.worker('descendant')
        child_pid = worker.request({'op': 'transcribe'}, deadline_ms=1000)['child_pid']
        # Inspect only this synthetic child; zombies are no longer running.
        def alive():
            try:
                state = Path(f'/proc/{child_pid}/stat').read_text().split(') ', 1)[1].split()[0]
                return state not in ('Z', 'X')
            except FileNotFoundError:
                return False
        self.assertTrue(alive())
        worker.close()
        deadline = time.monotonic() + 1
        while alive() and time.monotonic() < deadline:
            time.sleep(.01)
        self.assertFalse(alive())
        self.assert_reaped(worker)

    def test_invalid_local_request_never_launches_inference_or_corrupts_stream(self):
        worker = self.worker()
        for milliseconds in (0, -1, float('nan'), float('inf'), 'invalid'):
            with self.subTest(milliseconds=milliseconds), self.assertRaises(ValueError):
                worker.request({'op': 'transcribe'}, deadline_ms=milliseconds)
        with self.assertRaises(ValueError):
            worker.request({}, b'\0' * (worker.MAX_REQUEST_BYTES + 1))
        self.assertEqual(worker.request({'op': 'transcribe'}, deadline_ms=1000)['id'], 1)

    def test_ane_runtime_failure_and_nontext_transcript_retire_worker(self):
        # No actual AneModel construction: exercise the adapter against synthetic replies.
        for reply in ({'ok': False, 'kind': 'DeadlineExceeded'}, {'ok': True, 'transcript': 123}):
            model = object.__new__(ane.AneModel)
            model.request = lambda *args, reply=reply, **kwargs: reply
            closed = []
            model.close = lambda: closed.append(True)
            with self.assertRaises(RuntimeError):
                model.transcribe(b'\0' * 4)
            self.assertEqual(closed, [True])


if __name__ == '__main__':
    unittest.main()
