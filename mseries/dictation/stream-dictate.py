#!/usr/bin/env python3
"""Streaming dictation: hold F5 (KEY_F14 after the hwdb remap), words are typed while you talk.

transcribe.cpp + Parakeet Unified (cache-aware streaming). Committed text is append-only, so it is
typed as soon as it commits; whatever is still tentative is typed when you release the key.
Audio comes straight from the AOP mic (ALSA, float32) only while the key is held. Nothing is stored.
Env: STREAM_MODEL, STREAM_SOURCE, STREAM_KEY (evdev code, default 184), STREAM_THREADS, STREAM_GAIN,
STREAM_DRY (print, do not type), STREAM_QUIET (no chime/notification), STREAM_TEST_WAV / STREAM_TEST_RAW.
"""
import math, os, queue, signal, struct, subprocess, sys, threading, time, wave, tempfile
import numpy as np
import transcribe_cpp as t
from pathlib import Path

MODEL = os.environ.get("STREAM_MODEL", os.path.expanduser(
    "~/.local/share/mseries/stream/models/parakeet-unified-en-0.6b-Q4_K_M.gguf"))
SOURCE = os.environ.get("STREAM_SOURCE", "direct")  # "direct" = ALSA hw capture, or a PipeWire node name
CARD = os.environ.get("STREAM_CARD", "hw:1,0")
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
QUIET = bool(os.environ.get("STREAM_QUIET"))  # tests: no chimes, no notifications
KEY = int(os.environ.get("STREAM_KEY", "184"))  # KEY_F14
THREADS = int(os.environ.get("STREAM_THREADS", "6"))
CHUNK = 1600  # 100 ms of 16 kHz samples
OUTPUT = os.environ.get('STREAM_OUTPUT', 'ydotool')  # IBus is opt-in until app acceptance passes
INPUT_CLIENT = str(Path(__file__).with_name('dictation-input-client.py'))


def input_call(method, token=None, text=None):
    command = ['/usr/bin/python3', INPUT_CLIENT, method]
    if token is not None:
        command.append(token)
    return subprocess.run(command, input=text, text=True, capture_output=True, timeout=3, check=True).stdout.strip()


T0 = time.time()


def log(*a):
    print(*a, file=sys.stderr, flush=True)


def keyboard_device():
    block = open("/proc/bus/input/devices").read().split("\n\n")
    for b in block:
        if "Apple SPI Keyboard" in b or "Apple MTP Keyboard" in b:
            for tok in b.split():
                if tok.startswith("event"):
                    return "/dev/input/" + tok
    raise SystemExit("no Apple keyboard found")


def notify(msg):
    if QUIET:
        return
    subprocess.Popen(["notify-send", "-t", "2500", "-i", "audio-input-microphone", "-a", "Dictation",
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


def whisper_fallback(pcm16):
    """One offline Voxtype/Whisper pass over the captured audio (kept in RAM only)."""
    path = os.path.join(os.environ.get("XDG_RUNTIME_DIR", "/tmp"), "dictation-fallback.wav")
    try:
        with wave.open(path, "wb") as w:
            w.setnchannels(1); w.setsampwidth(2); w.setframerate(16000); w.writeframes(pcm16)
        r = subprocess.run(["/usr/local/bin/voxtype", "transcribe", path], capture_output=True,
                           text=True, timeout=30)
        lines = [l.strip() for l in r.stdout.splitlines() if l.strip()]
        return lines[-1] if lines else ""
    except Exception as e:
        log("fallback failed:", repr(e))
        return ""
    finally:
        try:
            os.remove(path)
        except OSError:
            pass


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


class Typer(threading.Thread):
    """Types text through ydotool in order, off the audio thread."""
    def __init__(self):
        super().__init__(daemon=True)
        self.q = queue.Queue()
        self.start()

    def run(self):
        while True:
            text, token = self.q.get()
            if text and (os.environ.get("STREAM_TEST_WAV") or os.environ.get("STREAM_TEST_RAW") or DRY):
                print(f"[{time.time() - T0:5.1f}s] type: {text!r}", flush=True)
            elif text:
                try:
                    if OUTPUT == 'ibus':
                        input_call('commit', token, text)
                    else:
                        subprocess.run(["ydotool", "type", "--key-delay", "2", "--", text],
                                       stderr=subprocess.DEVNULL)
                except (subprocess.SubprocessError, OSError):
                    log('dictation insertion refused; no keyboard fallback')
                    notify('Dictation stopped: text-field focus changed or input method unavailable')
            self.q.task_done()

    def submit(self, text, token):
        self.q.put((text, token))


class Dictation:
    def __init__(self):
        self.model = t.Model(MODEL)
        self.typer = Typer()
        self.active = False
        self.worker = None
        self.stop_evt = threading.Event()
        self.input_token = None

    def start(self):
        if self.active:
            return
        if OUTPUT == 'ibus' and not (DRY or os.environ.get('STREAM_TEST_WAV') or os.environ.get('STREAM_TEST_RAW')):
            try:
                self.input_token = input_call('begin')
            except (subprocess.SubprocessError, OSError):
                notify('Select a normal text field with the Dictation input method')
                return
        self.active = True
        self.stop_evt.clear()
        if not (os.environ.get("STREAM_TEST_WAV") or os.environ.get("STREAM_TEST_RAW")):
            tone(880, 90)
            notify("Listening…")
        self.worker = threading.Thread(target=self.run, daemon=True)
        self.worker.start()

    def stop(self):
        if self.active:
            self.stop_evt.set()

    def cancel(self):
        self.stop()
        if OUTPUT == 'ibus':
            try:
                input_call('cancel')
            except (subprocess.SubprocessError, OSError):
                pass

    def run(self):
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
        for attempt in range(8):  # the previous capture may still hold the device for a moment
            cap = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
            first = cap.stdout.read1(CHUNK * 2)
            if first:
                break
            cap.wait()
            time.sleep(0.1)
        else:
            log("could not open the microphone")
            self.active = False
            return
        pending = first
        typed = ""
        t0 = time.time()
        kept = bytearray()
        try:
            with self.model.session(n_threads=THREADS) as s, s.stream() as st:
                buf = pending
                peak = sq = 0.0; n = 0
                stopped_at = None
                while True:
                    if self.stop_evt.is_set() and stopped_at is None:
                        stopped_at = time.time()
                    if stopped_at and time.time() - stopped_at > 0.15:
                        break  # short tail so the last word is not clipped
                    data = cap.stdout.read1(CHUNK * 2)
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
                        if up.committed_changed:
                            c = st.text().committed
                            if c.startswith(typed) and len(c) > len(typed):
                                self.typer.submit(c[len(typed):], self.input_token)
                                typed = c
                st.finalize()
                final = st.text().display
                if final.startswith(typed):
                    rest = final[len(typed):]
                else:
                    rest = ""  # revised an already typed prefix: never retype or delete
                if rest.strip():
                    self.typer.submit(rest, self.input_token)
                rms = (sq / max(n, 1)) ** 0.5
                spread, active, floor = speech_stats(np.frombuffer(bytes(kept), np.int16).astype(np.float32) / 32768)
                log(f"dictated {len(final)} chars in {time.time() - t0:.1f}s; audio peak {peak:.3f} rms {rms:.4f} "
                    f"floor {floor:.4f} spread {spread:.1f} dB active {active}")
                if os.environ.get("STREAM_FORCE_FALLBACK"):
                    final = ""  # test hook: pretend streaming recognized nothing
                if not final.strip() and len(kept) > 16000 * 2 and spread >= SPEECH_SPREAD_DB and active >= 3:
                    # streaming heard nothing but there was sound: let Whisper have one offline pass
                    redo = whisper_fallback(bytes(kept))
                    if redo and not DRY:
                        self.typer.submit(redo + " ", self.input_token)
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
            log("stream error:", repr(e))
        finally:
            cap.terminate()
            try:
                cap.wait(2)
            except Exception:
                cap.kill()
            if not (test or raw):
                tone(440, 120)
            self.active = False


def main():
    d = Dictation()
    dev = keyboard_device()
    log("ready, keyboard", dev, "model", os.path.basename(MODEL))
    signal.signal(signal.SIGTERM, lambda *a: os._exit(0))
    # `systemctl --user kill --kill-whom=main -s USR1 mseries-stream-dictate` toggles recording (self-test
    # without the key). Without --kill-whom=main systemd also signals the ffmpeg capture child, which dies.
    signal.signal(signal.SIGUSR1, lambda *a: d.stop() if d.active else d.start())
    fmt = "llHHi"
    size = struct.calcsize(fmt)
    with open(dev, "rb", buffering=0) as f:
        while True:
            raw = f.read(size)
            _, _, typ, code, val = struct.unpack(fmt, raw)
            if typ == 1 and code == 1 and val == 1:  # Escape cancels pending IBus insertion
                d.cancel()
            if typ == 1 and code == KEY:
                if val == 1:
                    d.start()
                elif val == 0:
                    d.stop()


if __name__ == "__main__":
    main()
