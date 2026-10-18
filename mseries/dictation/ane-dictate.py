#!/usr/bin/env python3
"""Dictation on the Apple Neural Engine: hold F5 (KEY_F14 after the hwdb remap), speak, release.

Parakeet TDT 0.6B v3 (Core ML reference, encoder on the ANE via omarchy-ane, mel/decoder on the
Honeykrisp GPU) transcribes the whole utterance after release and the text is typed into the
focused field. Whole-utterance decoding is what gives word-for-word output: the model sees all
of the audio, nothing is revised after typing. Nothing is stored; audio stays in RAM.

Run as a service (needs the evdev keyboard and ydotool) or offline:
  ane-dictate.py --wav FILE [--repeat N]     transcribe a file and print text + timings
Env: ANE_PREFIX (default ~/.local/share/mlx-omarchy), ANE_VK_ICD (private Mesa 26.2.4 ICD),
     STREAM_CARD/STREAM_GAIN/STREAM_KEY (same meaning as stream-dictate.py), STREAM_DRY=1 (print only).
"""
import argparse, math, os, queue, re, signal, struct, subprocess, sys, tempfile, threading, time, wave
import json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from dictation_ane import AneModel as Worker, clean, split_points, transcribe_long  # noqa: E402

PREFIX = os.path.expanduser(os.environ.get("ANE_PREFIX", "~/.local/share/mlx-omarchy"))
ICD = os.path.expanduser(os.environ.get(
    "ANE_VK_ICD", "~/.local/share/mseries/ane/mesa-hk/share/vulkan/icd.d/asahi_icd.aarch64.json"))
CARD = os.environ.get("STREAM_CARD", "hw:1,0")
GAIN = os.environ.get("STREAM_GAIN", "0.2")
CHAIN = ("pan=mono|c0=0.333*c0+0.333*c1+0.333*c2,highpass=f=150,lowpass=f=7000,"
         f"volume={GAIN},alimiter=limit=0.9,aresample=async=1")
KEY = int(os.environ.get("STREAM_KEY", "184"))
DRY = bool(os.environ.get("STREAM_DRY"))
MAX_SECONDS = 600  # a held key longer than this is cut off (RAM bound)


def log(*a):
    print(*a, file=sys.stderr, flush=True)


def read_wav_f32(path):
    return subprocess.run(["ffmpeg", "-v", "error", "-i", path, "-f", "f32le", "-ac", "1", "-ar", "16000", "-"],
                          capture_output=True, check=True).stdout


def offline(path, repeat):
    w = Worker()
    pcm = read_wav_f32(path)
    dur = len(pcm) / 4 / 16000
    try:
        for i in range(repeat):
            t0 = time.perf_counter()
            raw = w.transcribe(pcm)
            dt = time.perf_counter() - t0
            print(f"run {i + 1}: {dt:.2f}s for {dur:.1f}s audio (RTF {dt / dur:.3f})")
        print("raw:  ", raw)
        print("clean:", clean(raw))
        if dur > 29:
            t0 = time.perf_counter()
            print("split:", transcribe_long(w, pcm), f"({time.perf_counter() - t0:.2f}s)")
    finally:
        w.close()


def notify(msg):
    subprocess.Popen(["notify-send", "-t", "2500", "-i", "audio-input-microphone", "-a", "Dictation",
                      "-h", "string:x-canonical-private-synchronous:mseries-dictation", msg],
                     stderr=subprocess.DEVNULL)


def tone(freq, ms, vol=0.25):
    path = os.path.join(tempfile.gettempdir(), f"mseries-chime-{freq}.wav")
    if not os.path.exists(path):
        n = int(16000 * ms / 1000)
        s = [int(32767 * vol * math.sin(2 * math.pi * freq * i / 16000) * min(1, i / 200, (n - i) / 400))
             for i in range(n)]
        with wave.open(path, "wb") as f:
            f.setnchannels(1); f.setsampwidth(2); f.setframerate(16000)
            f.writeframes(struct.pack("<%dh" % n, *s))
    subprocess.Popen(["pw-play", path], stderr=subprocess.DEVNULL)


def keyboard_device():
    for b in open("/proc/bus/input/devices").read().split("\n\n"):
        if "Apple SPI Keyboard" in b or "Apple MTP Keyboard" in b:
            for tok in b.split():
                if tok.startswith("event"):
                    return "/dev/input/" + tok
    raise SystemExit("no Apple keyboard found")


class Dictation:
    def __init__(self):
        self.worker = Worker()
        self.active = False
        self.stop_evt = threading.Event()
        self.typeq = queue.Queue()
        threading.Thread(target=self._typer, daemon=True).start()
        threading.Thread(target=self._warm, daemon=True).start()

    def _warm(self):  # the first call builds the encoder (tens of seconds once, then resident)
        try:
            self.worker.transcribe(bytes(16000 * 4))
            log("ANE worker warm")
        except Exception as e:
            log("warm-up failed:", e)

    def _typer(self):
        while True:
            text = self.typeq.get()
            if DRY:
                print("type:", repr(text), flush=True)
            else:
                subprocess.run(["ydotool", "type", "--key-delay", "2", "--", text], stderr=subprocess.DEVNULL)

    def start(self):
        if self.active:
            return
        self.active = True
        self.stop_evt.clear()
        tone(880, 90)
        notify("Listening…")
        threading.Thread(target=self.run, daemon=True).start()

    def stop(self):
        self.stop_evt.set()

    def run(self):
        cmd = ["ffmpeg", "-nostdin", "-v", "error", "-f", "alsa", "-channels", "3", "-sample_rate", "48000",
               "-i", CARD, "-af", CHAIN, "-ar", "16000", "-f", "f32le", "-"]
        cap = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        buf = bytearray()
        t_start = time.time()
        try:
            while time.time() - t_start < MAX_SECONDS:
                data = cap.stdout.read1(6400)
                if not data:
                    break
                buf += data
                if self.stop_evt.is_set():
                    time.sleep(0.15)  # short tail so the last word is not clipped
                    buf += cap.stdout.read1(6400) or b""
                    break
        finally:
            cap.terminate()
            try:
                cap.wait(2)
            except Exception:
                cap.kill()
            tone(440, 120)
        buf = buf[: len(buf) // 4 * 4]
        n_samples = len(buf) // 4
        if n_samples < 8000:  # under half a second
            self.active = False
            return
        t0 = time.perf_counter()
        try:
            text = transcribe_long(self.worker, bytes(buf))
        except Exception as e:
            log("ANE transcription failed:", e)
            notify("Dictation failed (ANE). See the service log.")
            text = ""
        finally:
            self.active = False
        log(f"{n_samples / 16000:.1f}s audio -> {len(text)} chars in {time.perf_counter() - t0:.2f}s")
        if text:
            self.typeq.put(text + " ")
        else:
            notify("Didn't catch that")


def service():
    d = Dictation()
    dev = keyboard_device()
    log("ready, keyboard", dev, "engine Parakeet TDT v3 on ANE")
    signal.signal(signal.SIGTERM, lambda *a: (d.worker.close(), os._exit(0)))
    signal.signal(signal.SIGUSR1, lambda *a: d.stop() if d.active else d.start())
    fmt = "llHHi"
    size = struct.calcsize(fmt)
    with open(dev, "rb", buffering=0) as f:
        while True:
            _, _, typ, code, val = struct.unpack(fmt, f.read(size))
            if typ == 1 and code == KEY:
                d.start() if val == 1 else d.stop() if val == 0 else None


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--wav")
    ap.add_argument("--repeat", type=int, default=3)
    a = ap.parse_args()
    offline(a.wav, a.repeat) if a.wav else service()
