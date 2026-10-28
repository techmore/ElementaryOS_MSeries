#!/usr/bin/env python3
"""Streaming dictation: hold F5 (KEY_F14 after the hwdb remap), words are typed while you talk.

transcribe.cpp + English Nemotron (cache-aware streaming; Unified compatibility option). Committed text is append-only, so it is
typed as soon as it commits; whatever is still tentative is typed when you release the key.
Audio comes straight from the AOP mic (ALSA, float32) only while the key is held.
Audio is not saved by default; STREAM_KEEP is an explicit last-capture debug option.
Env: STREAM_MODEL, STREAM_SOURCE, STREAM_KEY (evdev code, default 184), STREAM_THREADS, STREAM_GAIN,
STREAM_DRY (print, do not type), STREAM_QUIET (no chime/notification), STREAM_TEST_WAV / STREAM_TEST_RAW.
"""
import math, os, queue, select, signal, struct, subprocess, sys, threading, time, wave, tempfile
import numpy as np
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from dictation_status import write_status
from dictation_resources import load_policy, reasons as resource_reasons
from dictation_model import LazyModel, ModelHeadroom

DEFAULT_MODEL = ('nemotron-speech-streaming-en-0.6b-Q8_0.gguf'
                 if os.environ.get('STREAM_ENGINE', 'nemotron') == 'nemotron'
                 else 'parakeet-unified-en-0.6b-Q4_K_M.gguf')
MODEL = os.environ.get('STREAM_MODEL', str(Path.home()/'.local/share/mseries/stream/models'/DEFAULT_MODEL))
UNVERIFIED_FALLBACK = os.environ.get("STREAM_UNVERIFIED_FALLBACK", "0") == "1"  # ydotool when the focused app exposes no accessible field
TOGGLE = os.environ.get("STREAM_MODE", "hold") == "toggle"  # toggle: press F5 once to start, again to finish
ENGINE = os.environ.get("STREAM_ENGINE", "nemotron")  # ane/mlx: resident Parakeet rolling pipelines; lfm3: shared assistd model
SOURCE = os.environ.get("STREAM_SOURCE", "direct")  # "direct" = ALSA hw capture, or a PipeWire node name
CARD = os.environ.get("STREAM_CARD", "hw:1,0")
# shift, ctrl, alt, super, caps lock, fn: pressing these alone is not typing
MODIFIER_KEYS = {29, 42, 54, 56, 58, 97, 100, 125, 126, 464}
ANE_HOLD = int(os.environ.get("STREAM_ANE_HOLD", "0"))  # newest agreed words kept back from typing
ANE_AGREE = int(os.environ.get("STREAM_ANE_AGREE", "2"))  # passes that must agree; 1 types the newest pass minus the held-back words
ANE_TRACE = bool(os.environ.get("STREAM_ANE_TRACE"))  # log audio time at every typed chunk (latency analysis)
ANE_INTERVAL = float(os.environ.get("STREAM_ANE_INTERVAL", "0.3"))  # seconds of new audio between partial passes
MAX_ANE_SECONDS = 600  # RAM bound for one held key
GAIN = os.environ.get("STREAM_GAIN", "60")


def make_chain(gain):
    """3 raw AOP channels -> mono, drop DC/rumble, band-limit before resampling, fixed gain, limiter.
    The AOP samples are float32 at about -80 dBFS room noise and -45 dBFS speech, hence the large gain."""
    return ("pan=mono|c0=0.333*c0+0.333*c1+0.333*c2,highpass=f=120,lowpass=f=7000,lowpass=f=7000,"
            f"volume={gain},alimiter=limit=0.9,aresample=async=1")


CHAIN = make_chain(GAIN)
# The AOP driver advertises every sample format but always delivers FLOAT_LE; ffmpeg's ALSA input
# defaults to s16le, which reads float halves as noise (the 2026-10-18 "mic sensitivity" blocker).
ALSA_IN = ["-f", "alsa", "-c:a", "pcm_f32le", "-channels", "3", "-sample_rate", "48000"]
# Whisper fallback gate: chunk-level spread (dB) between loud and quiet parts of the capture.
# Measured 2026-10-18 at gain 60 (mic-eval.py, test-dictation.py): room silence 1.4-4.4 dB, 0-1 active chunks; speech
# played at -20/-10/0 dB 10.5/17.1/22.3 dB with 14/43/59 active chunks (see README).
SPEECH_SPREAD_DB = float(os.environ.get("STREAM_SPEECH_DB", "8"))
KEEP = bool(os.environ.get("STREAM_KEEP"))
DRY = bool(os.environ.get("STREAM_DRY"))  # print instead of typing
POPUP = os.environ.get("STREAM_POPUP", "1")  # "0": no Listening/finished popups
QUIET = bool(os.environ.get("STREAM_QUIET"))  # tests: no chimes, no notifications
KEY = int(os.environ.get("STREAM_KEY", "184"))  # KEY_F14
THREADS = int(os.environ.get("STREAM_THREADS", "4"))
CHUNK = 1600  # 100 ms of 16 kHz samples
OUTPUT = os.environ.get('STREAM_OUTPUT', 'ydotool')  # IBus is opt-in until app acceptance passes
INPUT_CLIENT = str(Path(__file__).with_name('dictation-input-client.py'))
TEST_INSERT = os.environ.get('STREAM_TEST_INSERT') == '1'
if OUTPUT not in ('ibus', 'ydotool'):
    raise SystemExit('Unsupported dictation output; choose ibus or ydotool explicitly')
if TEST_INSERT and not (OUTPUT == 'ibus' and os.environ.get('MSERIES_INPUT_TEST_SESSION') == '1'
                        and os.environ.get('GSETTINGS_BACKEND') == 'memory'
                        and os.environ.get('STREAM_TEST_WAV') and not DRY):
    raise SystemExit('File-to-input test requires isolated session, IBus and explicit test audio')


def input_call(method, token=None, text=None):
    command = ['/usr/bin/python3', INPUT_CLIENT, method]
    if token is not None:
        command.append(token)
    return subprocess.run(command, input=text, text=True, capture_output=True, timeout=5, check=True).stdout.strip()


T0 = time.time()


def log(*a):
    print(*a, file=sys.stderr, flush=True)


def status(phase):
    if DRY or os.environ.get('STREAM_TEST_WAV') or os.environ.get('STREAM_TEST_RAW'):
        return
    try:
        write_status(phase, OUTPUT, ENGINE if ENGINE in ('ane','mlx') else ('cpu' if ENGINE=='nemotron' else os.environ.get('STREAM_BACKEND', 'auto')))
    except (OSError, ValueError):
        log('dictation lifecycle status unavailable')


def keyboard_device():
    block = open("/proc/bus/input/devices").read().split("\n\n")
    for b in block:
        if "Apple SPI Keyboard" in b or "Apple MTP Keyboard" in b:
            for tok in b.split():
                if tok.startswith("event"):
                    return "/dev/input/" + tok
    raise SystemExit("no Apple keyboard found")


def notify(msg, persistent=False):
    if QUIET:
        return
    if POPUP == "0" and (persistent or msg.startswith(("Preparing", "Dictation finished", "Dictation cancelled"))):
        return  # chimes stay; only errors and refusals pop up
    subprocess.Popen(["notify-send", "-t", "0" if persistent else "2500", "-i", "audio-input-microphone", "-a", "Dictation",
                      "-h", "string:x-canonical-private-synchronous:mseries-dictation", msg],
                     stderr=subprocess.DEVNULL)


def tone(freq, ms, vol=0.25):
    if QUIET:
        return
    path = os.path.join(tempfile.gettempdir(), f"mseries-chime-{freq}.wav")
    if not os.path.exists(path):
        n = int(16000 * ms / 1000)
        s = [int(32767 * vol * math.sin(2 * math.pi * freq * i / 16000) *
                 min(1, i / 200, (n - i) / 400)) for i in range(n)]
        with wave.open(path, "wb") as w:
            w.setnchannels(1); w.setsampwidth(2); w.setframerate(16000)
            w.writeframes(struct.pack("<%dh" % n, *s))
    subprocess.Popen(["pw-play", path], stderr=subprocess.DEVNULL)


def chime(kind):
    """macOS-style start/stop sounds: two soft bell notes, rising to start and falling to stop."""
    if QUIET:
        return
    path = os.path.join(os.environ.get("XDG_RUNTIME_DIR") or tempfile.gettempdir(), f"mseries-dictation-{kind}.wav")
    if not os.path.exists(path):
        rate, notes = 48000, ((784.0, 1174.7) if kind == "start" else (1174.7, 784.0))
        step, tail = int(rate * 0.085), int(rate * 0.32)
        out = [0.0] * (step + tail)
        for k, freq in enumerate(notes):
            for i in range(tail):
                t = i / rate
                env = min(1.0, i / (rate * 0.004)) * math.exp(-t * 14)
                out[k * step + i] += env * (math.sin(2 * math.pi * freq * t) + 0.25 * math.sin(4 * math.pi * freq * t))
        peak = max(abs(x) for x in out) or 1.0
        with wave.open(path, "wb") as w:
            w.setnchannels(1); w.setsampwidth(2); w.setframerate(rate)
            w.writeframes(struct.pack("<%dh" % len(out), *(int(32767 * 0.32 * x / peak) for x in out)))
    subprocess.Popen(["pw-play", "--media-role", "Notification", path], stderr=subprocess.DEVNULL)


class MicIndicator:
    """The floating microphone (dictation-indicator.py) while the mic is open; falls back to a notification."""
    SCRIPT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "dictation-indicator.py")

    def __init__(self):
        self.proc = None
        self.next_level = 0.0

    def show(self):
        if QUIET or self.proc is not None:
            return
        try:
            self.proc = subprocess.Popen(["/usr/bin/python3", "-I", self.SCRIPT], stdin=subprocess.PIPE,
                                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, text=True)
        except OSError:
            self.proc = None
        threading.Thread(target=self._fallback_if_unsupported, args=(self.proc,), daemon=True).start()

    def _fallback_if_unsupported(self, proc):
        try:
            code = proc.wait(timeout=2) if proc else 3
        except subprocess.TimeoutExpired:
            return  # running: the indicator is up
        if code == 3 or proc is None:
            # No overlay support in this compositor: a notification with the microphone icon instead.
            subprocess.Popen(["notify-send", "-t", "0", "-i", "audio-input-microphone", "-a", "Dictation",
                              "-h", "string:x-canonical-private-synchronous:mseries-dictation",
                              "Listening\u2026"], stderr=subprocess.DEVNULL)

    def feed(self, pcm16):
        """Send the chunk's level, at most ~25 times a second."""
        proc = self.proc
        if proc is None or proc.poll() is not None or not pcm16:
            return
        now = time.monotonic()
        if now < self.next_level:
            return
        self.next_level = now + 0.04
        n = len(pcm16) // 2
        samples = struct.unpack("<%dh" % n, pcm16[:n * 2])
        rms = math.sqrt(sum(x * x for x in samples) / max(1, n)) / 32768
        try:
            proc.stdin.write(f"{rms:.4f}\n"); proc.stdin.flush()
        except (BrokenPipeError, OSError, ValueError):
            pass

    def hide(self):
        proc, self.proc = self.proc, None
        if proc is None:
            return
        try:
            proc.stdin.write("quit\n"); proc.stdin.close()
        except (BrokenPipeError, OSError, ValueError):
            pass
        try:
            proc.wait(timeout=1)
        except subprocess.TimeoutExpired:
            proc.kill()  # our own child only


def whisper_fallback(pcm16, cancelled=lambda: False):
    """One offline Voxtype/Whisper pass over the captured audio (kept in RAM only)."""
    try:
        # An anonymous, explicitly inherited descriptor avoids persistent audio
        # and predictable filenames, including when XDG_RUNTIME_DIR is absent.
        with os.fdopen(os.memfd_create('mseries-stt-fallback', os.MFD_CLOEXEC), 'w+b') as audio:
            os.fchmod(audio.fileno(), 0o600)
            with wave.open(audio, "wb") as w:
                w.setnchannels(1); w.setsampwidth(2); w.setframerate(16000); w.writeframes(pcm16)
            audio.flush(); audio.seek(0)
            path = '/proc/self/fd/' + str(audio.fileno())
            if cancelled(): return ''
            child = subprocess.Popen(["/usr/local/bin/voxtype", "transcribe", path], stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL, text=True, pass_fds=(audio.fileno(),))
            try:
                deadline = time.monotonic() + 30
                while True:
                    if cancelled() or time.monotonic() >= deadline: return ''
                    try:
                        output, _ = child.communicate(timeout=.25)
                        if child.returncode: return ''
                        break
                    except subprocess.TimeoutExpired: pass
            finally:
                if child.poll() is None:
                    child.terminate()
                    try: child.wait(1)
                    except subprocess.TimeoutExpired: child.kill(); child.wait()
            lines = [l.strip() for l in output.splitlines() if l.strip()]
            return lines[-1] if lines else ""
    except Exception as e:
        log("fallback failed:", repr(e))
        return ""


def speech_stats(pcm):
    """Speech-like energy in a capture: 100 ms chunk rms, quiet floor (20th percentile), loud level
    (95th percentile). Speech has pauses, so it shows a wide spread; steady room noise does not.
    Returns (spread_db, active_chunks, floor_rms)."""
    n = len(pcm) // CHUNK
    if n < 5:
        return 0.0, 0, 0.0
    rms = np.sqrt((pcm[:n * CHUNK].reshape(n, CHUNK).astype(np.float64) ** 2).mean(1)) + 1e-9
    floor, loud = np.percentile(rms, 20), np.percentile(rms, 95)
    return float(20 * np.log10(loud / floor)), int((rms > floor * 2.5).sum()), float(floor)


class Preview(str):
    pass


class Typer(threading.Thread):
    """Commit text and release its input session in order, off the audio thread."""
    def __init__(self, failure=None):
        super().__init__(daemon=True)
        self.q = queue.Queue()
        self.failed = False
        self.failure = failure
        self.epoch = 0
        self.process = None
        self.process_lock = threading.Lock()
        self.start()

    def run(self):
        while True:
            item = self.q.get()
            text, token = item[:2]
            epoch = item[2] if len(item) > 2 else self.epoch
            if isinstance(text, threading.Event):
                text.set()
                self.q.task_done()
                continue
            if epoch != self.epoch:
                self.q.task_done()
                continue
            if text is None:
                try:
                    input_call('finish', token)
                except (subprocess.SubprocessError, OSError):
                    self.failed = True
                    log('dictation input session could not finish')
                    if self.failure: self.failure()
                self.q.task_done()
                continue
            if isinstance(text, Preview) and not token:
                self.q.task_done(); continue
            if (text or isinstance(text, Preview)) and (DRY or (not TEST_INSERT and (os.environ.get("STREAM_TEST_WAV") or os.environ.get("STREAM_TEST_RAW")))):
                print(f"[{time.time() - T0:5.1f}s] type: {text!r}", flush=True)
            elif text or isinstance(text, Preview):
                try:
                    if OUTPUT == 'ibus' and token:
                        input_call('preview' if isinstance(text, Preview) else 'commit', token, str(text))
                    else:
                        with self.process_lock:
                            if epoch != self.epoch:
                                self.q.task_done(); continue
                            self.process = subprocess.Popen(["ydotool", "type", "--key-delay", "2", "--", text], stderr=subprocess.DEVNULL)
                            child = self.process
                        try:
                            if child.wait(5): raise subprocess.SubprocessError('Keyboard insertion failed')
                        except subprocess.TimeoutExpired:
                            child.kill(); child.wait(); raise
                        finally:
                            with self.process_lock: self.process = None
                except (subprocess.SubprocessError, OSError):
                    if epoch != self.epoch:
                        self.q.task_done(); continue
                    first_failure = not self.failed
                    self.failed = True
                    log('dictation insertion refused; no keyboard fallback')
                    if first_failure and self.failure: self.failure()
            self.q.task_done()

    def drain(self, timeout=15):
        finished = threading.Event()
        self.q.put((finished, None))
        return finished.wait(timeout)

    def finish(self, token):
        if token: self.q.put((None, token, self.epoch))

    def submit(self, text, token, epoch=None):
        self.q.put((text, token, self.epoch if epoch is None else epoch))

    def preview(self, text, token, epoch=None):
        if token: self.submit(Preview(text), token, epoch)

    def discard(self):
        with self.process_lock:
            self.epoch += 1
            if self.process and self.process.poll() is None:
                self.process.terminate()


class Dictation:
    def __init__(self):
        idle = float(os.environ.get('STREAM_IDLE_SECONDS', '180' if ENGINE in ('ane', 'mlx') else '60'))
        if not 0 <= idle <= 900: raise ValueError('Speech residency must be between0 and900seconds')
        self.models = LazyModel(self.load_model, idle_seconds=idle)
        self.typer = Typer(self.insertion_failed)
        self.mic = MicIndicator()
        self.stop_feedback = True
        self.active = False
        self.worker = None
        self.stop_evt = threading.Event()
        self.input_token = None
        self.error = None
        self.cancelled = False
        self.interrupted = False
        self.next_trim = 0

    @staticmethod
    def load_model():
        # Importing the SDK loads its native backends too. Keep even that work
        # out of the listener's idle startup path.
        if ENGINE == 'ane':
            from dictation_ane import AneModel
            return AneModel()
        if ENGINE == 'mlx':
            from dictation_mlx import MlxModel
            return MlxModel()
        if ENGINE == 'lfm3':
            from dictation_lfm import LfmModel
            return LfmModel()
        if ENGINE not in ('stream', 'nemotron'): raise ValueError('Unknown speech engine')
        import transcribe_cpp as t
        return t.Model(MODEL, backend='cpu' if ENGINE == 'nemotron' else os.environ.get('STREAM_BACKEND', 'cpu'))

    @staticmethod
    def speech_policy():
        policy = load_policy()
        policy['reserve_gib'] = max(6, policy.get('reserve_gib',6))
        if ENGINE == 'lfm3':  # the model lives in assistd, which keeps its own reserve; match it
            policy['reserve_gib'] = float(os.environ.get('MSERIES_ASSIST_RESERVE_GIB', '6'))
        policy['max_fan_rpm'] = min(2700, policy.get('max_fan_rpm',2700))
        policy['max_temp_c'] = min(63, policy.get('max_temp_c',63))
        return policy

    def idle_tick(self):
        if self.active or time.monotonic() < self.next_trim:
            return
        if not self.models.loaded and self.error != 'ResourceGuard':
            return
        self.next_trim = time.monotonic() + 5
        if self.models.trim(force=bool(resource_reasons(self.speech_policy(), 256 * 1024**2))):
            log('idle speech model released; F5 listener remains ready')
        if self.error == 'ResourceGuard' and not resource_reasons(self.speech_policy(), 2*1024**3):
            self.error = None
            status('ready')

    def insertion_failed(self):
        self.typer.discard()
        self.stop_evt.set()
        if not self.cancelled:
            self.error = 'InputUnavailable'
            status('error')
            notify('Dictation stopped: text-field focus changed or input method unavailable')

    def start(self):
        if self.active or self.typer.q.unfinished_tasks:
            return
        self.active = True
        self.error = None
        self.cancelled = False
        self.interrupted = False
        self.typer.failed = False
        self.output_epoch = self.typer.epoch
        self.stop_evt.clear()
        self.input_token = None
        self.worker = threading.Thread(target=self.prepare, daemon=True)
        self.worker.start()

    def prepare(self):
        capture_started = False
        test = os.environ.get('STREAM_TEST_WAV') or os.environ.get('STREAM_TEST_RAW')
        try:
            self.policy = self.speech_policy()
            if self.stop_evt.is_set(): return
            if resource_reasons(self.policy, 256 * 1024**2): raise ModelHeadroom()
            if OUTPUT == 'ibus' and (TEST_INSERT or not (DRY or test)):
                try:
                    self.input_token = input_call('begin')
                except (subprocess.SubprocessError, OSError) as refusal:
                    # An app that exposes no accessibility tree (Electron, some Qt) cannot be verified;
                    # the owner allowed typing there. Sensitive, non-editable or cancelled refusals stay hard.
                    if UNVERIFIED_FALLBACK and 'UNVERIFIED-FIELD' in (getattr(refusal, 'stderr', '') or ''):
                        log('focused field not verifiable; typing through ydotool for this session')
                    else:
                        self.error = 'InputUnavailable'
                        reason = ((getattr(refusal, 'stderr', '') or '').strip().splitlines() or [''])[-1][:120]
                        log('dictation input refused before microphone capture' + (f': {reason}' if reason else ''))
                        notify('Dictation needs a supported editable text field. Focus the editor and try F5 again.')
                        return
            if self.stop_evt.is_set(): return
            if not self.models.loaded:
                status('loading')
                if not test: notify('Preparing speech model… Microphone is off. Wait for Listening.')
            with self.models.use(lambda extra: not resource_reasons(self.policy,
                    max(extra, (6 if ENGINE == 'mlx' else 0 if ENGINE == 'lfm3' else 2)*1024**3) if not self.models.loaded else extra)) as model:
                if self.stop_evt.is_set(): return
                if self.input_token:
                    # Loading can outlast the user's focus. Check the original
                    # lease again without inserting text or reading field text.
                    try: input_call('check', self.input_token)
                    except (subprocess.SubprocessError, OSError):
                        self.insertion_failed()
                        return
                if self.stop_evt.is_set(): return
                if resource_reasons(self.policy, 256 * 1024**2): raise ModelHeadroom()
                capture_started = True
                status('listening')
                if not test:
                    chime('start')
                    self.mic.show()
                    self.stop_feedback = False
                    notify('Listening… Press F5 again to finish; Escape cancels.' if TOGGLE else 'Listening… Release F5 to finish; Escape cancels.', persistent=True)
                self.run(model)
        except ModelHeadroom:
            self.error = 'ResourceGuard'
            notify('Dictation is waiting for memory or cooling headroom')
        except Exception as error:
            self.error = type(error).__name__
            log('speech preparation failed:', type(error).__name__)
            notify('Dictation could not prepare the speech model; microphone is off')
        finally:
            if self.error or self.cancelled or self.interrupted:
                self.typer.discard()
                if self.input_token:
                    try: input_call('cancel')
                    except (subprocess.SubprocessError, OSError): pass
            elif OUTPUT == 'ibus': self.typer.finish(self.input_token)
            # Ready means the original field includes the final queued output.
            # English grammar review must not polish a pre-flush prefix.
            status('finishing')
            if not self.typer.drain():
                self.error = 'InputDrainTimeout'
                if self.input_token:
                    try: input_call('cancel')
                    except (subprocess.SubprocessError, OSError): pass
            if not capture_started or self.error or self.cancelled or self.interrupted:
                try: self.models.trim(force=True)
                except Exception:
                    self.error = 'ModelReleaseUnavailable'
                    log('idle speech model release failed')
            if capture_started and not test:
                self.stopped_listening()
                notify('Dictation cancelled' if self.cancelled else ('Dictation stopped to preserve cooling or desktop memory' if self.error == 'ResourceGuard' else ('Dictation finished' if not self.error else 'Dictation could not finish')))
            self.active = False
            status('cancelled' if self.cancelled else ('waiting' if self.error == 'ResourceGuard' else ('error' if self.error else 'ready')))

    def stopped_listening(self):
        """Stop sound and hide the mic once, the moment listening ends (not after typing drains)."""
        if getattr(self, 'stop_feedback', True):
            return
        self.stop_feedback = True
        self.mic.hide()
        chime('stop')

    def stop(self):
        if self.active:
            self.stop_evt.set()
            self.stopped_listening()
            status('finishing')

    def interrupt(self):
        """The user started typing: end dictation now and drop words not yet typed, so nothing lands in the middle of their sentence."""
        if not self.active:
            return
        self.interrupted = True
        self.stop_evt.set()
        self.stopped_listening()
        self.typer.discard()
        self.abort_model()
        if OUTPUT == 'ibus':
            try: input_call('cancel')
            except (subprocess.SubprocessError, OSError): pass

    def abort_model(self):
        model = self.models.model
        if model is not None and hasattr(model, 'cancel'):
            model.cancel()

    def cancel(self):
        self.cancelled = True
        self.typer.discard()
        self.abort_model()
        self.stop()
        if OUTPUT == 'ibus':
            try:
                input_call('cancel')
            except (subprocess.SubprocessError, OSError):
                pass

    @staticmethod
    def close_capture(cap):
        try:
            cap.terminate()
            try: cap.wait(2)
            except subprocess.TimeoutExpired:
                cap.kill(); cap.wait(2)
        finally:
            cap.stdout.close()

    def open_capture(self, command):
        for _ in range(8):
            if self.stop_evt.is_set(): return None, None
            cap = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
            try:
                deadline = time.monotonic() + 2
                while not self.stop_evt.is_set() and time.monotonic() < deadline:
                    if not select.select([cap.stdout], [], [], .1)[0]: continue
                    first = cap.stdout.read1(CHUNK * 2)
                    if first: return cap, first
                    break
            except BaseException:
                self.close_capture(cap)
                raise
            self.close_capture(cap)
            self.stop_evt.wait(.1)
        return None, None

    def run_ane(self, model, cap, pending):
        """Rolling engine: re-decode the audio so far every ANE_INTERVAL s on the ANE and type the words two
        consecutive passes agree on (minus the newest, which may still change). Typed text is append-only."""
        from dictation_ane import clean, stable_count, norm, drop_overlap
        kept = bytearray(pending)
        t0 = time.time()
        # First decode initializes the resident worker; avoid a racing warm thread.
        seg = 0            # byte offset where the current segment starts
        typed_n = 0        # words of the current segment already typed
        prev = []          # previous pass's words
        last_len = 0
        flight = None      # (thread, result list, segment id)
        seg_id = 0
        total_typed = 0
        decode_errors = []

        def f32(buf):
            b = buf[:len(buf) // 2 * 2]
            return (np.frombuffer(bytes(b), np.int16).astype(np.float32) / 32768).astype('<f4').tobytes()

        def decode(buf):
            return clean(model.transcribe(f32(buf))).split()

        tail = []          # normalized last words typed, to trim the overlap after a segment cut
        after_cut = False

        def say(words):
            nonlocal total_typed, after_cut
            if after_cut and words:
                words = drop_overlap(tail, words)
                after_cut = False
            if ANE_TRACE and words:
                log(f"trace say audio_t={len(kept) / 32000:.2f} n={len(words)} words={' '.join(words)}")
            tail.extend(norm(w) for w in words)
            del tail[:-8]
            if words and not self.error and not self.cancelled and not self.interrupted:
                self.typer.submit(" ".join(words) + " ", self.input_token, getattr(self, "output_epoch", None))
                total_typed += len(words)

        def absorb(words):
            nonlocal typed_n, prev
            commit = max(typed_n, (stable_count(prev, words) if ANE_AGREE > 1 else len(words)) - ANE_HOLD)
            if commit > typed_n:
                say(words[typed_n:commit])
                typed_n = commit
            prev = words

        try:
            stopped_at = None
            next_guard = 0
            while len(kept) < MAX_ANE_SECONDS * 32000:
                now = time.monotonic()
                if now >= next_guard:
                    next_guard = now + 1
                    if resource_reasons(self.policy):
                        self.error = 'ResourceGuard'
                        self.stop_evt.set()
                if self.error or self.cancelled or self.interrupted:
                    self.abort_model()
                    return
                if self.stop_evt.is_set() and stopped_at is None:
                    stopped_at = time.time()
                if stopped_at and time.time() - stopped_at > 0.15:
                    break
                if decode_errors: raise RuntimeError('Rolling speech decode failed')
                if flight and not flight[0].is_alive():
                    if flight[2] == seg_id and flight[1]:
                        absorb(flight[1][0])
                    flight = None
                seg_len = len(kept) - seg
                if flight is None and seg_len > 16 * 32000:
                    # Long utterance: close this segment at its quietest 100 ms so the 30 s model window never splits a word.
                    lo, hi = len(kept) - 5 * 32000, len(kept) - 1 * 32000
                    x = np.frombuffer(bytes(kept[lo:hi // 2 * 2]), np.int16).astype(np.float32)
                    w = len(x) // 1600
                    cut = lo + int(np.argmin((x[:w * 1600].reshape(w, 1600) ** 2).sum(1))) * 3200
                    say(decode(kept[seg:cut])[typed_n:])
                    seg, typed_n, prev, last_len, seg_id, after_cut = cut, 0, [], 0, seg_id + 1, True
                    continue
                if flight is None and seg_len >= 32000 and seg_len - last_len >= ANE_INTERVAL * 32000:
                    last_len = seg_len
                    out = []
                    snapshot = bytes(kept[seg:])
                    def decode_once(b=snapshot, o=out):
                        try: o.append(decode(b))
                        except Exception as error: decode_errors.append(type(error).__name__)
                    th = threading.Thread(target=decode_once, daemon=True)
                    flight = (th, out, seg_id)
                    th.start()
                if not select.select([cap.stdout], [], [], .05)[0]:
                    continue
                data = cap.stdout.read1(CHUNK * 2)
                self.mic.feed(data)
                if not data:
                    break
                kept += data
            self.close_capture(cap)
            if flight:
                flight[0].join(10)
            if decode_errors: raise RuntimeError('Rolling speech decode failed')
            if flight and flight[0].is_alive():
                self.abort_model(); flight[0].join(2)
                raise TimeoutError('Rolling decoder did not finish')
            if len(kept) - seg >= 8000 and not self.interrupted and not self.cancelled and not self.error:
                status('finishing')
                t_dec = time.time()
                words = decode(kept[seg:])
                say(words[typed_n:])
                log(f"ane dictated {total_typed} words from {len(kept) / 32000:.1f}s; held {t_dec - t0:.1f}s, "
                    f"final pass {time.time() - t_dec:.2f}s")
            if not total_typed and not DRY and not self.cancelled and not self.interrupted:
                notify("Didn't catch that")
        except Exception as e:
            self.error = type(e).__name__
            log("ane error:", repr(e))
        finally:
            self.close_capture(cap)
            if flight and flight[0].is_alive():
                self.abort_model(); flight[0].join(2)

    def run_lfm(self, model, cap, pending):
        """LFM3-Audio: cut phrases at pauses, transcribe each in order on one worker, type as they return."""
        from dictation_lfm import PhraseCutter, LfmUnavailable
        cutter = PhraseCutter()
        # Load the model while the user talks instead of after the first phrase (cold load ~4 s).
        threading.Thread(target=model.warm, daemon=True).start()
        phrases = queue.Queue()
        typed = []
        t0 = time.time()

        def worker():
            while True:
                pcm = phrases.get()
                if pcm is None: return
                if self.error or self.cancelled or self.interrupted: continue
                try:
                    text = model.transcribe(pcm)
                except LfmUnavailable as e:
                    log('lfm3 transcription failed:', e)
                    self.error = 'SpeechUnavailable'; self.stop_evt.set()
                    notify(f'Dictation: {e}')
                    continue
                if text and not (self.error or self.cancelled or self.interrupted):
                    text = text + ' '
                    typed.append(text)
                    if DRY: print(text, flush=True)
                    else: self.typer.submit(text, self.input_token, getattr(self, 'output_epoch', None))

        w = threading.Thread(target=worker, daemon=True); w.start()
        try:
            buf = pending; stopped_at = None; next_guard = 0
            while True:
                now = time.monotonic()
                if now >= next_guard:
                    next_guard = now + 1
                    if resource_reasons(self.policy):
                        self.error = 'ResourceGuard'; self.stop_evt.set()
                if self.error or self.cancelled or self.interrupted: break
                if self.stop_evt.is_set() and stopped_at is None: stopped_at = time.time()
                if stopped_at and time.time() - stopped_at > 0.15: break
                if not select.select([cap.stdout], [], [], .1)[0]: continue
                data = cap.stdout.read1(CHUNK * 2)
                self.mic.feed(data)
                if not data: break
                buf += data
                while len(buf) >= CHUNK * 2:
                    done = cutter.feed(bytes(buf[:CHUNK * 2])); buf = buf[CHUNK * 2:]
                    if done: phrases.put(done)
            if not (self.error or self.cancelled or self.interrupted):
                rest = cutter.flush()
                if rest: phrases.put(rest)
        except Exception as e:
            self.error = type(e).__name__
            log('lfm3 stream error:', repr(e))
        finally:
            self.close_capture(cap)
            phrases.put(None)
            w.join(timeout=180)
        chars = sum(map(len, typed))
        log(f'dictated {chars} chars in {time.time() - t0:.1f}s with lfm3 ({len(typed)} phrases)')
        if not chars and not self.error and not self.cancelled and not DRY:
            notify("Didn't catch that")

    def run(self, model):
        test = os.environ.get("STREAM_TEST_WAV")  # offline test: play a file instead of the mic
        raw = os.environ.get("STREAM_TEST_RAW")  # offline test: a raw AOP capture (3ch f32 48 kHz) through CHAIN
        if test:
            cmd = ["ffmpeg", "-re", "-v", "error", "-i", test, "-f", "s16le", "-ac", "1", "-ar", "16000", "-"]
        elif raw:
            cmd = ["ffmpeg", "-nostdin", "-re", "-v", "error", "-f", "f32le", "-ac", "3", "-ar", "48000", "-i", raw,
                   "-af", CHAIN, "-ar", "16000", "-f", "s16le", "-"]
        elif SOURCE == "direct":  # open the AOP mic only while the key is held (36 ms to first audio)
            cmd = ["ffmpeg", "-nostdin", "-v", "error", *ALSA_IN, "-i", CARD, "-af", CHAIN, "-ar", "16000", "-f", "s16le", "-"]
        else:
            cmd = ["pw-cat", "--record", "--target", SOURCE, "--rate", "16000",
                   "--channels", "1", "--format", "s16", "--raw", "-"]
        # A failed/blocked first read must not leave a capture child alive,
        # and release during device startup must not start a later retry.
        cap, pending = self.open_capture(cmd)
        if cap is None:
            if self.stop_evt.is_set(): return
            log("could not open the microphone")
            self.error = 'CaptureUnavailable'
            notify('Could not open the microphone')
            return
        if ENGINE in ('ane', 'mlx'):
            return self.run_ane(model, cap, pending)
        if ENGINE == 'lfm3':
            return self.run_lfm(model, cap, pending)
        typed = ""
        t0 = time.time()
        kept = bytearray()
        try:
            options = {}
            if ENGINE == 'nemotron':
                from transcribe_cpp import ParakeetStreamOptions
                options['family'] = ParakeetStreamOptions(att_context_right=1)
            with model.session(n_threads=THREADS) as s, s.stream(**options) as st:
                buf = pending
                peak = sq = 0.0; n = 0
                stopped_at = None
                next_guard = 0
                while True:
                    now = time.monotonic()
                    if now >= next_guard:
                        next_guard = now + 1
                        if resource_reasons(self.policy):
                            self.error = 'ResourceGuard'
                            self.stop_evt.set()
                    if self.error or self.cancelled or self.interrupted:
                        break
                    if self.stop_evt.is_set() and stopped_at is None:
                        stopped_at = time.time()
                    if stopped_at and time.time() - stopped_at > 0.15:
                        break  # short tail so the last word is not clipped
                    if not select.select([cap.stdout], [], [], .1)[0]:
                        continue  # Keep stop/resource guards live if capture stalls.
                    data = cap.stdout.read1(CHUNK * 2)
                    self.mic.feed(data)
                    if not data:
                        break
                    buf += data
                    while len(buf) >= CHUNK * 2:
                        kept += buf[:CHUNK * 2]
                        pcm = np.frombuffer(buf[:CHUNK * 2], np.int16).astype(np.float32) / 32768
                        peak = max(peak, float(np.abs(pcm).max()))
                        sq += float((pcm ** 2).sum()); n += len(pcm)
                        buf = buf[CHUNK * 2:]
                        up = st.feed(pcm)
                        if self.error or self.cancelled or self.interrupted: break
                        if up.committed_changed:
                            c = st.text().committed
                            if c.startswith(typed) and len(c) > len(typed):
                                self.typer.submit(c[len(typed):], self.input_token, getattr(self, "output_epoch", None))
                                typed = c
                if self.error or self.cancelled or self.interrupted:
                    final = typed
                else:
                    st.finalize()
                    final = typed if self.error or self.cancelled or self.interrupted else st.text().display
                if final.startswith(typed):
                    rest = final[len(typed):]
                else:
                    rest = ""  # revised an already typed prefix: never retype or delete
                if rest.strip():
                    self.typer.submit(rest, self.input_token, getattr(self, "output_epoch", None))
                rms = (sq / max(n, 1)) ** 0.5
                spread, active, floor = speech_stats(np.frombuffer(bytes(kept), np.int16).astype(np.float32) / 32768)
                log(f"dictated {len(final)} chars in {time.time() - t0:.1f}s; audio peak {peak:.3f} rms {rms:.4f} "
                    f"floor {floor:.4f} spread {spread:.1f} dB active {active}")
                if os.environ.get("STREAM_FORCE_FALLBACK"):
                    final = ""  # test hook: pretend streaming recognized nothing
                if not self.error and not self.cancelled and not self.interrupted and not final.strip() and len(kept) > 16000 * 2 and spread >= SPEECH_SPREAD_DB and active >= 3:
                    # streaming heard nothing but there was sound: let Whisper have one offline pass
                    def cancelled_fallback():
                        if self.error or self.cancelled or self.interrupted: return True
                        if resource_reasons(self.policy):
                            self.error = 'ResourceGuard'; self.stop_evt.set(); return True
                        return False
                    redo = whisper_fallback(bytes(kept), cancelled=cancelled_fallback)
                    if self.error or self.cancelled or self.interrupted: redo = ""
                    if redo and not DRY:
                        self.typer.submit(redo + " ", self.input_token, getattr(self, "output_epoch", None))
                    elif redo:
                        print("fallback:", redo, flush=True)
                    final = redo or ""
                    log(f"whisper fallback: {len(final)} chars")
                if not final.strip() and not DRY and not (test or raw):
                    notify(f"Didn't catch that (mic level {rms * 100:.1f}%, peak {peak * 100:.0f}%)")
                if KEEP:  # debug only: last capture, in RAM (XDG_RUNTIME_DIR), overwritten each time
                    with wave.open(os.path.join(os.environ.get("XDG_RUNTIME_DIR", "/tmp"), "dictation-last.wav"), "wb") as w:
                        w.setnchannels(1); w.setsampwidth(2); w.setframerate(16000); w.writeframes(bytes(kept))
        except Exception as e:  # keep the daemon alive
            self.error = type(e).__name__
            log("stream error:", repr(e))
        finally:
            self.close_capture(cap)


def main():
    d = Dictation()
    if TEST_INSERT:
        d.start()
        if d.worker is None:
            raise SystemExit('File-to-input session refused')
        d.worker.join(timeout=60)
        if d.worker.is_alive():
            d.cancel()
            raise SystemExit('File-to-input session timed out')
        deadline = time.monotonic() + 10
        while d.typer.q.unfinished_tasks and time.monotonic() < deadline:
            time.sleep(.02)
        if d.error or d.typer.failed or d.typer.q.unfinished_tasks:
            raise SystemExit('File-to-input session failed')
        return
    dev = keyboard_device()
    log("ready, keyboard", dev, "model", os.path.basename(MODEL))
    status('ready')
    def terminate(*_):
        d.cancel()
        if d.worker: d.worker.join(5)
        d.models.trim(force=True)
        status('stopped')
        raise SystemExit(0)
    signal.signal(signal.SIGTERM, terminate)
    # `systemctl --user kill --kill-whom=main -s USR1 mseries-stream-dictate` toggles recording (self-test
    # without the key). Without --kill-whom=main systemd also signals the ffmpeg capture child, which dies.
    signal.signal(signal.SIGUSR1, lambda *a: d.stop() if d.active else d.start())
    fmt = "llHHi"
    size = struct.calcsize(fmt)
    with open(dev, "rb", buffering=0) as f:
        while True:
            d.idle_tick()
            if not select.select([f], [], [], 1)[0]: continue
            raw = f.read(size)
            if len(raw) != size: raise SystemExit('Keyboard input device disconnected')
            _, _, typ, code, val = struct.unpack(fmt, raw)
            if typ == 1 and code == 1 and val == 1:  # Escape cancels pending IBus insertion
                d.cancel()
            elif typ == 1 and val == 1 and code != KEY and code not in MODIFIER_KEYS and d.active:
                d.interrupt()  # End our append-only session to avoid interleaving typed text.
            if typ == 1 and code == KEY and TOGGLE:
                if val == 1:  # key repeat (val 2) and release are ignored
                    if d.active:
                        d.stop()
                    else:
                        log('F5 pressed; checking dictation admission and field metadata')
                        d.start()
            elif typ == 1 and code == KEY:
                if val == 1:
                    log('F5 pressed; checking dictation admission and field metadata')
                    d.start()
                elif val == 0:
                    d.stop()


if __name__ == "__main__":
    main()
