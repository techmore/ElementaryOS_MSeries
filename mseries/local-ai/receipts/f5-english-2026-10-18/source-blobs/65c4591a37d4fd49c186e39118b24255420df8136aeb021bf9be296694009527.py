"""Parakeet TDT v3 on the Apple Neural Engine, as a drop-in speech model for the F5 controller.

AneModel owns the worker process (ane-worker-shim.py -> upstream parakeet_dictation), so
LazyModel can start it on first use and close() it when idle. Whole-utterance decoding: audio
is transcribed after F5 is released. Env: ANE_PREFIX, ANE_VK_ICD.
"""
import json, math, os, re, select, signal, struct, subprocess, threading, time

PREFIX = os.path.expanduser(os.environ.get("ANE_PREFIX", "~/.local/share/mlx-omarchy"))
ICD = os.path.expanduser(os.environ.get(
    "ANE_VK_ICD", "~/.local/share/mseries/ane/mesa-hk/share/vulkan/icd.d/asahi_icd.aarch64.json"))
SHIM = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ane-worker-shim.py")


def clean(text):
    """The model emits runs of '.' on trailing silence and the odd stray non-Latin token there.
    Drop runs of 3+ dots, then a trailing fragment that contains no Latin letter or digit."""
    text = re.sub(r"(?<=[A-Za-z0-9])\.{2,}", ".", text)
    text = re.sub(r"\.{2,}", " ", text)
    words = text.split()
    while words and not re.search(r"[A-Za-z0-9]", words[-1]):
        words.pop()
    return re.sub(r"\s+([,.;:!?])", r"\1", " ".join(words)).strip()


def split_points(pcm, window=1600, lo=15.0, hi=27.0, limit=29.0):
    """Cut utterances longer than ~29 s at the quietest 100 ms window in [lo, hi] s so the model's
    fixed 30 s chunking never lands inside a word. Returns byte offsets (f32le, 4 bytes/sample)."""
    import array
    a = array.array("f"); a.frombytes(pcm[: len(pcm) // 4 * 4])
    cuts, start, n = [], 0, len(a)
    while n - start > limit * 16000:
        best, at = None, None
        for i in range(start + int(lo * 16000), start + int(hi * 16000), window):
            e = sum(x * x for x in a[i:i + window])
            if best is None or e < best:
                best, at = e, i
        cuts.append(at * 4)
        start = at
    return cuts


def transcribe_long(worker, pcm):
    cuts = split_points(pcm)
    edges = [0, *cuts, len(pcm)]
    return " ".join(clean(worker.transcribe(pcm[a:b])) for a, b in zip(edges, edges[1:]))


class WorkerClosed(RuntimeError):
    """The owned speech worker has been retired; create a new model to retry."""


class FramedWorker:
    """Bounded, single-flight framing for an owned speech subprocess.

    The local deadline covers waiting for the request lock, writing audio and reading
    the complete reply, independently of the worker's own deadline implementation.
    A partial/invalid transaction retires the process: its framing cannot safely be
    reused. close/cancel never wait for the request lock and abort pending I/O.
    """
    MAX_REQUEST_BYTES = 16 * 1024 * 1024
    MAX_HEADER_BYTES = 256 * 1024
    MAX_REPLY_PAYLOAD_BYTES = 64 * 1024
    MAX_DEADLINE_MS = 90000

    def __init__(self, command, *, env=None):
        self.p = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                  env=env, bufsize=0, start_new_session=True)
        self.n = 0
        self.lock = threading.Lock()
        self._state_lock = threading.Lock()
        self._closed = threading.Event()
        self._reaped = threading.Event()
        self._shutdown_started = False
        os.set_blocking(self.p.stdin.fileno(), False)
        os.set_blocking(self.p.stdout.fileno(), False)

    @property
    def closed(self):
        return self._closed.is_set()

    def _check(self, deadline):
        if self.closed:
            raise WorkerClosed("Speech worker is closed")
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError("Speech worker IPC deadline exceeded")
        return remaining

    def _wait(self, fd, *, writing, deadline):
        while True:
            remaining = self._check(deadline)
            ready = select.select([] if writing else [fd], [fd] if writing else [], [],
                                  min(remaining, .05))
            if ready[1 if writing else 0]:
                return

    def _write(self, data, deadline):
        fd, offset = self.p.stdin.fileno(), 0
        view = memoryview(data)
        while offset < len(view):
            self._wait(fd, writing=True, deadline=deadline)
            try:
                count = os.write(fd, view[offset:offset + 65536])
            except BlockingIOError:
                continue
            if not count:
                raise RuntimeError("Speech worker input closed")
            offset += count

    def _read(self, size, deadline):
        fd, chunks, remaining = self.p.stdout.fileno(), [], size
        while remaining:
            self._wait(fd, writing=False, deadline=deadline)
            try:
                chunk = os.read(fd, min(remaining, 65536))
            except BlockingIOError:
                continue
            if not chunk:
                raise RuntimeError("Speech worker exited before its complete reply")
            chunks.append(chunk)
            remaining -= len(chunk)
        return b"".join(chunks)

    def request(self, header, payload=b"", deadline_ms=90000):
        if not isinstance(payload, (bytes, bytearray, memoryview)):
            raise TypeError("Speech payload must be bytes")
        if len(payload) > self.MAX_REQUEST_BYTES:
            raise ValueError("Speech request payload is too large")
        try:
            milliseconds = float(deadline_ms)
        except (TypeError, ValueError):
            raise ValueError("Speech deadline must be positive and finite") from None
        if not math.isfinite(milliseconds) or milliseconds <= 0:
            raise ValueError("Speech deadline must be positive and finite")
        milliseconds = min(milliseconds, self.MAX_DEADLINE_MS)
        deadline = time.monotonic() + milliseconds / 1000
        # Contention timeout does not invalidate the other in-flight request.
        while True:
            remaining = self._check(deadline)
            if self.lock.acquire(timeout=min(.05, remaining)):
                break
        try:
            self._check(deadline)
            self.n += 1
            frame = json.dumps({**header, "id": self.n, "payload_bytes": len(payload),
                                "deadline_ms": int(milliseconds)}).encode()
            if len(frame) > self.MAX_HEADER_BYTES:
                raise ValueError("Speech request header is too large")
            self._write(struct.pack("<Q", len(frame)), deadline)
            self._write(frame, deadline)
            self._write(payload, deadline)
            size, = struct.unpack("<Q", self._read(8, deadline))
            if not 0 < size <= self.MAX_HEADER_BYTES:
                raise RuntimeError("Speech worker reply header size is invalid")
            try:
                reply = json.loads(self._read(size, deadline))
            except (ValueError, UnicodeError):
                raise RuntimeError("Speech worker reply is not valid JSON") from None
            if not isinstance(reply, dict) or reply.get("id") != self.n or type(reply.get("ok")) is not bool:
                raise RuntimeError("Speech worker reply identity/status is invalid")
            extra = reply.get("payload_bytes", 0)
            if type(extra) is not int or not 0 <= extra <= self.MAX_REPLY_PAYLOAD_BYTES:
                raise RuntimeError("Speech worker reply payload size is invalid")
            self._read(extra, deadline)
            return reply
        except Exception:
            self.close()
            raise
        finally:
            self.lock.release()

    def close(self):
        """Retire/reap this private process group without waiting for blocked IPC."""
        with self._state_lock:
            self._closed.set()
            leader = not self._shutdown_started
            self._shutdown_started = True
        if not leader:
            self._reaped.wait(2)
            return
        try:
            # The worker can own native encoder/decoder subprocesses. Its fresh
            # session contains only our descendants, including after parent exit.
            try:
                os.killpg(self.p.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
            try:
                self.p.wait(.25)
            except subprocess.TimeoutExpired:
                pass
            try:
                os.killpg(self.p.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            self.p.wait(1)
        finally:
            for pipe in (self.p.stdin, self.p.stdout):
                pipe.close()
            self._reaped.set()

    cancel = close


class AneModel(FramedWorker):
    """The owned ANE worker process (parakeet_dictation --worker)."""

    def __init__(self):
        site = os.path.join(PREFIX, "venv/lib/python3.14/site-packages")
        env = dict(os.environ, OMARCHY_MLX_SYSTEM_PREFIX=PREFIX, PYTHONPATH=os.path.join(site, "mlx"))
        if os.path.exists(ICD):
            env["VK_DRIVER_FILES"] = ICD
        super().__init__([os.path.join(PREFIX, "venv/bin/python"), SHIM], env=env)

    def transcribe(self, pcm_f32, deadline_ms=90000):
        reply = self.request({"op": "transcribe", "sample_rate": 16000}, pcm_f32, deadline_ms)
        if not reply["ok"] or not isinstance(reply.get("transcript"), str):
            self.close()
            raise RuntimeError("ANE transcription failed: " + str(reply.get("kind", "invalid transcript"))[:128])
        return reply["transcript"]

    def transcribe_long(self, pcm):
        return transcribe_long(self, pcm)

    def warm(self):
        """Build/load the encoder now (cached on disk after the first ever run)."""
        self.transcribe(bytes(16000 * 4))


def norm(word):
    return re.sub(r"[^\w']", "", word.lower())


def stable_count(prev, new):
    """Words at the start that two consecutive partial transcripts agree on (punctuation ignored)."""
    n = 0
    for x, y in zip(prev, new):
        if norm(x) != norm(y):
            break
        n += 1
    return n


def drop_overlap(tail, words, longest=8):
    """A new segment starts a little before the old one's end: drop the leading words that repeat the
    last words already typed (needs at least two matching words so a genuine repeat survives)."""
    for k in range(min(longest, len(tail), len(words)), 1, -1):
        if tail[-k:] == [norm(w) for w in words[:k]]:
            return words[k:]
    return words
