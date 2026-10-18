#!/usr/bin/env python3
"""Streaming dictation: hold F5 (KEY_F14 after the hwdb remap), words are typed while you talk.

transcribe.cpp + Parakeet Unified (cache-aware streaming). Committed text is append-only, so it is
typed as soon as it commits; whatever is still tentative is typed when you release the key.
Audio comes from the PipeWire source made by aop-mic.sh. Nothing is stored.
Env: STREAM_MODEL, STREAM_SOURCE, STREAM_KEY (evdev code, default 184), STREAM_THREADS.
"""
import math, os, queue, signal, struct, subprocess, sys, threading, time, wave, tempfile
import numpy as np
import transcribe_cpp as t

MODEL = os.environ.get("STREAM_MODEL", os.path.expanduser(
    "~/.local/share/mseries/stream/models/parakeet-unified-en-0.6b-Q4_K_M.gguf"))
SOURCE = os.environ.get("STREAM_SOURCE", "mseries-builtin-mic")
KEY = int(os.environ.get("STREAM_KEY", "184"))  # KEY_F14
THREADS = int(os.environ.get("STREAM_THREADS", "6"))
CHUNK = 1600  # 100 ms of 16 kHz samples


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


def tone(freq, ms, vol=0.25):
    path = os.path.join(tempfile.gettempdir(), f"mseries-chime-{freq}.wav")
    if not os.path.exists(path):
        n = int(16000 * ms / 1000)
        s = [int(32767 * vol * math.sin(2 * math.pi * freq * i / 16000) *
                 min(1, i / 200, (n - i) / 400)) for i in range(n)]
        with wave.open(path, "wb") as w:
            w.setnchannels(1); w.setsampwidth(2); w.setframerate(16000)
            w.writeframes(struct.pack("<%dh" % n, *s))
    subprocess.Popen(["pw-play", path], stderr=subprocess.DEVNULL)


class Typer(threading.Thread):
    """Types text through ydotool in order, off the audio thread."""
    def __init__(self):
        super().__init__(daemon=True)
        self.q = queue.Queue()
        self.start()

    def run(self):
        while True:
            text = self.q.get()
            if text and os.environ.get("STREAM_TEST_WAV"):
                print(f"[{time.time() - T0:5.1f}s] type: {text!r}", flush=True)
            elif text:
                subprocess.run(["ydotool", "type", "--key-delay", "2", "--", text],
                               stderr=subprocess.DEVNULL)
            self.q.task_done()


class Dictation:
    def __init__(self):
        self.model = t.Model(MODEL)
        self.typer = Typer()
        self.active = False
        self.worker = None
        self.stop_evt = threading.Event()

    def start(self):
        if self.active:
            return
        self.active = True
        self.stop_evt.clear()
        if not os.environ.get("STREAM_TEST_WAV"):
            tone(880, 90)
        self.worker = threading.Thread(target=self.run, daemon=True)
        self.worker.start()

    def stop(self):
        if self.active:
            self.stop_evt.set()

    def run(self):
        test = os.environ.get("STREAM_TEST_WAV")  # offline test: play a file instead of the mic
        cmd = (["ffmpeg", "-re", "-v", "error", "-i", test, "-f", "s16le", "-ac", "1", "-ar", "16000", "-"]
               if test else ["pw-cat", "--record", "--target", SOURCE, "--rate", "16000",
                             "--channels", "1", "--format", "s16", "--raw", "-"])
        cap = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        typed = ""
        t0 = time.time()
        try:
            with self.model.session(n_threads=THREADS) as s, s.stream() as st:
                buf = b""
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
                        pcm = np.frombuffer(buf[:CHUNK * 2], np.int16).astype(np.float32) / 32768
                        buf = buf[CHUNK * 2:]
                        up = st.feed(pcm)
                        if up.committed_changed:
                            c = st.text().committed
                            if c.startswith(typed) and len(c) > len(typed):
                                self.typer.q.put(c[len(typed):])
                                typed = c
                st.finalize()
                final = st.text().display
                if final.startswith(typed):
                    rest = final[len(typed):]
                else:
                    rest = ""  # revised an already typed prefix: never retype or delete
                if rest.strip():
                    self.typer.q.put(rest)
                log(f"dictated {len(final)} chars in {time.time() - t0:.1f}s")
        except Exception as e:  # keep the daemon alive
            log("stream error:", repr(e))
        finally:
            cap.terminate()
            if not os.environ.get("STREAM_TEST_WAV"):
                tone(440, 120)
            self.active = False


def main():
    d = Dictation()
    dev = keyboard_device()
    log("ready, keyboard", dev, "model", os.path.basename(MODEL))
    signal.signal(signal.SIGTERM, lambda *a: os._exit(0))
    fmt = "llHHi"
    size = struct.calcsize(fmt)
    with open(dev, "rb", buffering=0) as f:
        while True:
            raw = f.read(size)
            _, _, typ, code, val = struct.unpack(fmt, raw)
            if typ == 1 and code == KEY:
                if val == 1:
                    d.start()
                elif val == 0:
                    d.stop()


if __name__ == "__main__":
    main()
