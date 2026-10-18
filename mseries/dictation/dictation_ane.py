"""Parakeet TDT v3 on the Apple Neural Engine, as a drop-in speech model for the F5 controller.

AneModel owns the worker process (ane-worker-shim.py -> upstream parakeet_dictation), so
LazyModel can start it on first use and close() it when idle. Whole-utterance decoding: audio
is transcribed after F5 is released. Env: ANE_PREFIX, ANE_VK_ICD.
"""
import json, os, re, struct, subprocess, sys, threading

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


class AneModel:
    """The owned ANE worker process (parakeet_dictation --worker) with its framing protocol."""

    def __init__(self):
        site = os.path.join(PREFIX, "venv/lib/python3.14/site-packages")
        env = dict(os.environ, OMARCHY_MLX_SYSTEM_PREFIX=PREFIX, PYTHONPATH=os.path.join(site, "mlx"))
        if os.path.exists(ICD):
            env["VK_DRIVER_FILES"] = ICD
        self.p = subprocess.Popen(
            [os.path.join(PREFIX, "venv/bin/python"), SHIM],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, env=env)
        self.n = 0
        self.lock = threading.Lock()

    def transcribe(self, pcm_f32, deadline_ms=90000):
        with self.lock:
            self.n += 1
            head = json.dumps({"op": "transcribe", "id": self.n, "sample_rate": 16000,
                               "deadline_ms": deadline_ms}).encode()
            head = json.dumps({**json.loads(head), "payload_bytes": len(pcm_f32)}).encode()
            self.p.stdin.write(struct.pack("<Q", len(head)) + head + pcm_f32)
            self.p.stdin.flush()
            raw = self.p.stdout.read(8)
            if len(raw) < 8:
                raise RuntimeError("ANE worker exited")
            (size,) = struct.unpack("<Q", raw)
            reply = json.loads(self.p.stdout.read(size))
            extra = int(reply.get("payload_bytes", 0))
            if extra:
                self.p.stdout.read(extra)
            if not reply.get("ok"):
                raise RuntimeError(f"{reply.get('kind')}: {reply.get('error')}")
            return reply["transcript"]

    def close(self):
        try:
            head = json.dumps({"op": "close", "id": 0}).encode()
            self.p.stdin.write(struct.pack("<Q", len(head)) + head)
            self.p.stdin.flush()
            self.p.wait(5)
        except Exception:
            self.p.kill()



    def transcribe_long(self, pcm):
        return transcribe_long(self, pcm)

    def warm(self):
        """Build/load the encoder now (cached on disk after the first ever run)."""
        self.transcribe(bytes(16000 * 4))
