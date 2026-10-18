"""Bounded work queues, independent of GTK and Incus for deterministic tests."""
from collections import deque
from threading import Lock


class LatestRead:
    """One running read and one replaceable request; deliver only the newest result.

    submit and completion run on the UI thread. launch(fn, complete) does work
    off-thread and returns to the UI thread with (result, error).
    """
    def __init__(self, launch):
        self.launch = launch
        self.version = 0
        self.running = False
        self.pending = None

    def invalidate(self):
        self.version += 1
        self.pending = None

    def submit(self, fn, done, fail):
        self.version += 1
        self.pending = (self.version, fn, done, fail)
        if not self.running:
            self._start()

    def _start(self):
        version, fn, done, fail = self.pending
        self.pending = None
        self.running = True
        def complete(result, error):
            self.running = False
            if version == self.version:
                fail(error) if error else done(result)
            if self.pending is not None:
                self._start()
        self.launch(fn, complete)


class OutputMailbox:
    """Keep a bounded tail and schedule at most one UI delivery per burst.

    schedule must enqueue drain on the UI thread (it must not call it inline).
    Only producers use put; the UI thread takes data with take.
    """
    def __init__(self, schedule, limit=65536):
        self.schedule = schedule
        self.limit = limit
        self.chunks = deque()
        self.size = 0
        self.dropped = 0
        self.scheduled = False
        self.lock = Lock()

    def put(self, text):
        with self.lock:
            self.chunks.append(text)
            self.size += len(text)
            while self.size > self.limit:
                extra = self.size - self.limit
                chunk = self.chunks.popleft()
                trim = min(extra, len(chunk))
                if trim < len(chunk):
                    self.chunks.appendleft(chunk[trim:])
                self.size -= trim
                self.dropped += trim
            notify = not self.scheduled
            self.scheduled = True
        if notify:
            self.schedule()

    def take(self):
        with self.lock:
            text = ''.join(self.chunks)
            if self.dropped:
                text = f"[Skipped {self.dropped:,} characters of fast output]\n" + text
            self.chunks.clear()
            self.size = self.dropped = 0
            self.scheduled = False
            return text
