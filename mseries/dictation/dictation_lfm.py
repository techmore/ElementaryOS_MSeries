"""F5 dictation through the shared LFM3-Audio assistant (mseries-assistd on 127.0.0.1:8772).

The model lives in assistd, so F5, F6 suggestions and the voice assistant share one resident copy.
This module only cuts the microphone stream into phrases at short pauses and sends each phrase
as a WAV to /v1/audio/transcriptions. Nothing is written to disk.
"""
import io, json, os, urllib.error, urllib.request, wave
import numpy as np

URL = os.environ.get('STREAM_LFM_URL', 'http://127.0.0.1:8772')
LANGUAGE = os.environ.get('STREAM_LFM_LANGUAGE', 'English')
PAUSE_S = float(os.environ.get('STREAM_LFM_PAUSE', '0.4'))   # silence that ends a phrase
MIN_PHRASE_S = 0.6                                             # shorter bursts wait for more audio
MAX_PHRASE_S = float(os.environ.get('STREAM_LFM_MAX_PHRASE', '8'))  # long runs are cut so text keeps coming
LOUD = 0.02             # chunk RMS that counts as clearly voiced (room noise here is ~0.003-0.008)
# What the model says for room noise or a breath. Dropped only when the phrase was barely voiced.
PHANTOMS = {'thank you', 'thanks', 'thank you for watching', 'thanks for watching', 'you', 'bye',
            'okay', 'oh', 'um', 'uh', 'hmm', 'mm', 'yeah', ''}
RATE = 16000


class LfmUnavailable(RuntimeError):
    pass


def _request(path, body=None, ctype='application/json', timeout=5):
    req = urllib.request.Request(URL + path, data=body, headers={'content-type': ctype} if body else {})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        try: msg = json.load(e).get('error', '')
        except Exception: msg = ''
        raise LfmUnavailable(msg or f'assistant returned HTTP {e.code}') from None
    except (urllib.error.URLError, OSError) as e:
        raise LfmUnavailable(f'assistant not reachable: {e}') from None


def wav_bytes(pcm16: bytes) -> bytes:
    out = io.BytesIO()
    with wave.open(out, 'wb') as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(RATE); w.writeframes(pcm16)
    return out.getvalue()


def voiced_seconds(pcm16: bytes, chunk_s=0.1) -> float:
    pcm = np.frombuffer(pcm16, np.int16).astype(np.float32) / 32768
    n = int(RATE * chunk_s)
    chunks = [pcm[i:i + n] for i in range(0, len(pcm) - n + 1, n)]
    return sum(chunk_s for c in chunks if float(np.sqrt((c ** 2).mean())) > LOUD)


def is_phantom(text: str, pcm16: bytes) -> bool:
    """A stock phrase from a barely voiced clip is the model filling silence, not speech."""
    words = ''.join(ch for ch in text.lower() if ch.isalpha() or ch == ' ').split()
    return ' '.join(words) in PHANTOMS and voiced_seconds(pcm16) < 0.5


class LfmModel:
    """Stands in for a local speech model: 'loading' only checks the service is up."""

    def __init__(self):
        health = _request('/health')
        if health.get('model') != 'lfm3-audio-2b':
            raise LfmUnavailable('unexpected assistant model')

    def warm(self):
        """Ask assistd to load the model now; F5 calls this on key press, in the background."""
        try:
            _request('/v1/warm', b'{}', timeout=60)
        except LfmUnavailable:
            pass  # the first phrase reports the real error

    def transcribe(self, pcm16: bytes, timeout=120) -> str:
        if len(pcm16) < RATE * 2 * 0.3:
            return ''
        result = _request(f'/v1/audio/transcriptions?language={LANGUAGE}', wav_bytes(pcm16), 'audio/wav', timeout)
        text = (result.get('text') or '').strip()
        return '' if is_phantom(text, pcm16) else text

    def close(self):
        pass


class PhraseCutter:
    """Feed 16 kHz s16 chunks; returns finished phrases (bytes) at pauses after speech."""

    def __init__(self, threshold=None):
        self.buf = bytearray()
        self.voiced = 0.0
        self.silent = 0.0
        self.floor = None
        self.threshold = threshold

    def _level(self, chunk):
        pcm = np.frombuffer(chunk, np.int16).astype(np.float32) / 32768
        return float(np.sqrt((pcm ** 2).mean())) if len(pcm) else 0.0

    def feed(self, chunk: bytes):
        secs = len(chunk) / (RATE * 2)
        level = self._level(chunk)
        self.floor = level if self.floor is None else min(self.floor * 1.002 + 1e-6, max(level, self.floor * 0.95))
        loud = level > (self.threshold if self.threshold is not None else max(0.006, (self.floor or 0) * 3))
        if not self.buf and not loud:
            return None  # leading silence is not sent
        self.buf += chunk
        if loud:
            self.voiced += secs; self.silent = 0.0
        else:
            self.silent += secs
        length = len(self.buf) / (RATE * 2)
        if (self.silent >= PAUSE_S and self.voiced >= MIN_PHRASE_S) or length >= MAX_PHRASE_S:
            return self.flush()
        if self.silent >= PAUSE_S * 3 and self.voiced < MIN_PHRASE_S:
            self.buf.clear(); self.voiced = self.silent = 0.0  # a click or breath, not a phrase
        return None

    def flush(self):
        out = bytes(self.buf) if self.voiced > 0.2 else b''
        self.buf.clear(); self.voiced = self.silent = 0.0
        return out or None
