#!/usr/bin/env python3
"""Self-tests for streaming dictation. Runs a private, silent copy of stream-dictate.py (STREAM_DRY:
prints instead of typing, STREAM_QUIET: no chime or notification) and drives it with SIGUSR1, so the
owner's running service, focused window and screen are untouched. The live tests open the built-in
mic for a few seconds (they skip if it is busy, e.g. while F5 is held).

usage: test-dictation.py [--loopback]   (--loopback also plays a speech clip through the speakers)
Env: DICTATION_TEST_WAV (16 kHz speech clip, default the LibriSpeech clip from the installer bench),
     DICTATION_TEST_REF (its transcript), DICTATION_LOOPBACK_RAW (reuse a saved raw capture with
     --loopback instead of playing the clip). Exit status 1 if any test fails.
"""
import ast, importlib.util, os, signal, subprocess, sys, tempfile, time
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
BASE = os.path.expanduser("~/.local/share/mseries/stream")
PY = os.path.join(BASE, "venv/bin/python")
SCRIPT = os.path.join(HERE, "stream-dictate.py")
WAV = os.environ.get("DICTATION_TEST_WAV", os.path.join(BASE, "libri.wav"))
REF = os.environ.get("DICTATION_TEST_REF", "He hoped there would be stew for dinner, turnips and carrots and "
                     "bruised potatoes and fat mutton pieces to be ladled out in thick, peppered, flour-fattened sauce")
CARD = os.environ.get("STREAM_CARD", "hw:1,0")
results = []


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


ev = load(os.path.join(HERE, "mic-eval.py"), "mic_eval")
sd = ev.load_dictate()


def check(name, ok, detail=""):
    results.append(ok)
    print(f"{'PASS' if ok else 'FAIL'} {name}{': ' + detail if detail else ''}", flush=True)


def skip(name, why):
    print(f"SKIP {name}: {why}", flush=True)


class Daemon:
    """A private dictation daemon; toggle() is what F5 press/release does."""
    def __init__(self, **env):
        self.out = tempfile.TemporaryFile("w+")
        self.err = tempfile.TemporaryFile("w+")
        e = dict(os.environ, STREAM_DRY="1", STREAM_QUIET="1", **env)
        e.pop("STREAM_KEEP", None)
        self.p = subprocess.Popen([PY, "-I", SCRIPT], stdout=self.out, stderr=self.err, env=e)
        self.wait_for("ready,", 60)

    def log(self):
        self.err.seek(0)
        return self.err.read()

    def typed(self):
        self.out.seek(0)
        text = ""
        for line in self.out:
            if "type: " in line:
                text += ast.literal_eval(line.split("type: ", 1)[1])
            elif line.startswith("fallback: "):  # Whisper's offline pass, printed in dry mode
                text += line.split(": ", 1)[1].strip() + " "
        return text

    def wait_for(self, text, timeout, count=1):
        end = time.time() + timeout
        while time.time() < end:
            if self.log().count(text) >= count:
                return True
            if self.p.poll() is not None:
                raise SystemExit("daemon died:\n" + self.log())
            time.sleep(0.1)
        return False

    def toggle(self):
        self.p.send_signal(signal.SIGUSR1)

    def close(self):
        self.p.terminate()
        self.p.wait(5)


def mic_free():
    try:
        return open("/proc/asound/card1/pcm0c/sub0/status").read().strip() == "closed"
    except OSError:
        return False


def test_gate_synthetic():
    rng = np.random.default_rng(1)
    noise = (rng.normal(0, 0.006, 16000 * 4)).astype(np.float32)
    s_spread, s_act, _ = sd.speech_stats(noise)
    speech = noise.copy()
    t = np.arange(16000) / 16000
    for start in (0.5, 1.7, 2.9):  # three 0.6 s "words" at -20 dBFS
        i = int(start * 16000)
        speech[i:i + 9600] += 0.1 * np.sin(2 * np.pi * 220 * t[:9600]) * np.hanning(9600)
    v_spread, v_act, _ = sd.speech_stats(speech)
    click = noise.copy(); click[16000:16200] += 0.5  # an F5 key click must not count as speech
    c_spread, c_act, _ = sd.speech_stats(click)
    check("gate: steady noise is not speech", s_spread < sd.SPEECH_SPREAD_DB or s_act < 3,
          f"spread {s_spread:.1f} dB active {s_act}")
    check("gate: worded tone is speech", v_spread >= sd.SPEECH_SPREAD_DB and v_act >= 3,
          f"spread {v_spread:.1f} dB active {v_act}")
    check("gate: single click is not speech", c_spread < sd.SPEECH_SPREAD_DB or c_act < 3,
          f"spread {c_spread:.1f} dB active {c_act}")


def test_capture_format():
    if not mic_free():
        return skip("mic delivers float32", "mic busy")
    with tempfile.NamedTemporaryFile(suffix=".f32") as f:
        subprocess.run(["arecord", "-q", "-D", CARD, "-f", "FLOAT_LE", "-c", "3", "-r", "48000", "-d", "1",
                        "-t", "raw", f.name], check=True)
        x = np.frombuffer(open(f.name, "rb").read(), "<f4").reshape(-1, 3)
    ok = len(x) > 40000 and np.isfinite(x).all() and np.abs(x.mean(0)).max() < 1e-3 and x.std(0).max() < 0.05
    check("mic delivers float32 audio (finite, no DC, quiet)", bool(ok),
          f"{len(x)} frames, std {np.round(x.std(0), 6).tolist()}, mean {np.abs(x.mean(0)).max():.2e}")


def test_offline_wav():
    if not os.path.exists(WAV):
        return skip("offline clip", WAV + " missing")
    d = Daemon(STREAM_TEST_WAV=WAV)
    try:
        d.toggle()
        d.wait_for("dictated", 40)
        time.sleep(0.5)
        text = d.typed()
        w = ev.wer(REF, text)
        check("offline clip streams correct text", w <= 0.1, f"WER {w * 100:.1f}% '{text.strip()[:60]}…'")
    finally:
        d.close()


def test_live_silence_and_reopen():
    if not mic_free():
        return skip("live mic", "mic busy")
    d = Daemon()
    try:
        d.toggle(); time.sleep(4); d.toggle()
        ok = d.wait_for("dictated", 15)
        log = d.log()
        check("live mic: 4 s of room silence types nothing", ok and not d.typed().strip() and "fallback" not in log,
              [l for l in log.splitlines() if "dictated" in l][-1:][0] if ok else "no result")
        for i, hold in enumerate((0.4, 0.8, 1.5, 0.5, 2.5)):
            time.sleep(0.3)
            d.toggle(); time.sleep(hold); d.toggle()
            d.wait_for("dictated", 15, count=i + 2)
        n = d.log().count("dictated")
        check("live mic: 5 rapid press/release cycles reopen the mic", n == 6 and "could not open" not in d.log(),
              f"{n - 1}/5 captures")
    finally:
        d.close()


def test_loopback():
    saved = os.environ.get("DICTATION_LOOPBACK_RAW")  # reuse a capture (mic-eval.py record) instead of playing
    if not saved and not mic_free():
        return skip("loopback", "mic busy")
    with tempfile.NamedTemporaryFile(suffix=".f32") as tmp:
        f = open(saved) if saved else tmp
        if not saved:
            ev.record(f.name, 12, WAV)
        d = Daemon(STREAM_TEST_RAW=f.name)
        try:
            d.toggle()
            d.wait_for("dictated", 40)
            time.sleep(0.5)
            text = d.typed()
            w = ev.wer(REF, text)
            line = [l for l in d.log().splitlines() if "dictated" in l][-1:]
            check("loopback: clip through speakers -> mic -> text", w <= 0.1,
                  f"WER {w * 100:.1f}%; {line[0].split(': ', 1)[-1] if line else ''}")
        finally:
            d.close()
        if not os.path.exists("/usr/local/bin/voxtype"):
            return skip("loopback: Whisper fallback", "voxtype not installed")
        d = Daemon(STREAM_TEST_RAW=f.name, STREAM_FORCE_FALLBACK="1")
        try:
            d.toggle()
            d.wait_for("whisper fallback", 60)
            time.sleep(0.5)
            d.out.seek(0)  # streaming text is printed before the forced fallback: score the fallback alone
            fb = " ".join(l.split(": ", 1)[1].strip() for l in d.out if l.startswith("fallback: "))
            w = ev.wer(REF, fb)
            check("loopback: Whisper fallback gate fires on speech and transcribes it", bool(fb) and w <= 0.25,
                  f"WER {w * 100:.1f}% '{fb}'")
        finally:
            d.close()


def main():
    test_gate_synthetic()
    test_capture_format()
    test_offline_wav()
    test_live_silence_and_reopen()
    if "--loopback" in sys.argv:
        test_loopback()
    print(f"{sum(results)}/{len(results)} passed")
    sys.exit(0 if all(results) else 1)


if __name__ == "__main__":
    main()
