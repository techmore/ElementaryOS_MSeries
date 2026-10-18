#!/usr/bin/env python3
"""Measure the built-in mic path end to end: capture -> filter chain -> Parakeet -> word error rate.

The AOP mic (ALSA hw:1,0) delivers 3 channels of 32-bit FLOAT at 48 kHz, whatever format is
requested (the driver advertises every format and never converts). This tool records that raw
stream once (optionally while playing a reference clip through the speakers), then runs any number
of ffmpeg filter chains over the same recording, so chains are compared on identical audio.

usage:
  mic-eval.py record OUT.f32 SECONDS [PLAY.wav]   raw 3ch float capture, optional playback (PLAY_VOLUME)
  mic-eval.py score RAW.f32 REFERENCE.txt|- [GAIN ...]   transcribe RAW through stream-dictate's chain
  mic-eval.py level RAW.f32                        per-channel rms/peak and speech-band rms in dBFS
Env: STREAM_MODEL, STREAM_THREADS (as stream-dictate.py). Nothing leaves the machine.
"""
import os, re, subprocess, sys, time
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
MODEL = os.environ.get("STREAM_MODEL", os.path.expanduser(
    "~/.local/share/mseries/stream/models/parakeet-unified-en-0.6b-Q4_K_M.gguf"))
THREADS = int(os.environ.get("STREAM_THREADS", "6"))


def load_dictate():
    import importlib.util
    spec = importlib.util.spec_from_file_location("stream_dictate", os.path.join(HERE, "stream-dictate.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def record(out, secs, play=None):
    cap = subprocess.Popen(["arecord", "-q", "-D", os.environ.get("STREAM_CARD", "hw:1,0"), "-f", "FLOAT_LE",
                            "-c", "3", "-r", "48000", "-d", str(secs), "-t", "raw", out])
    if play:
        time.sleep(0.8)
        subprocess.run(["pw-play", "--volume", os.environ.get("PLAY_VOLUME", "1.0"), play])
    cap.wait()


def db(x):
    return 20 * np.log10(max(x, 1e-12))


def level(raw):
    f = np.frombuffer(open(raw, "rb").read(), "<f4").reshape(-1, 3).astype(np.float64)
    f -= f.mean(0)
    spec = np.fft.rfft(f.mean(1))
    fr = np.fft.rfftfreq(len(f), 1 / 48000)
    band = spec.copy(); band[(fr < 300) | (fr > 3400)] = 0
    sb = np.fft.irfft(band, len(f))
    for c in range(3):
        print(f"ch{c}: rms {db(f[:, c].std()):6.1f} dBFS peak {db(np.abs(f[:, c]).max()):6.1f} dBFS")
    print(f"mix speech band 300-3400 Hz rms {db(sb.std()):6.1f} dBFS")
    print("channel correlation", np.round(np.corrcoef(f.T)[np.triu_indices(3, 1)], 3))


def to_pcm(raw, filt):
    r = subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-f", "f32le", "-ac", "3", "-ar", "48000", "-i", raw,
                        "-af", filt, "-ar", "16000", "-ac", "1", "-f", "s16le", "-"], capture_output=True, check=True)
    return np.frombuffer(r.stdout, np.int16).astype(np.float32) / 32768


def transcribe(model, pcm):
    with model.session(n_threads=THREADS) as s, s.stream() as st:
        for i in range(0, len(pcm), 1600):
            st.feed(pcm[i:i + 1600])
        st.finalize()
        return st.text().display.strip()


def words(s):
    return re.sub(r"[^a-z0-9' ]", " ", s.lower()).split()


def wer(ref, hyp):
    r, h = words(ref), words(hyp)
    d = list(range(len(h) + 1))
    for i in range(1, len(r) + 1):
        prev, d[0] = d[0], i
        for j in range(1, len(h) + 1):
            cur = min(d[j] + 1, d[j - 1] + 1, prev + (r[i - 1] != h[j - 1]))
            prev, d[j] = d[j], cur
    return d[len(h)] / max(len(r), 1)


def main():
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    cmd = sys.argv[1]
    if cmd == "record":
        record(sys.argv[2], int(sys.argv[3]), sys.argv[4] if len(sys.argv) > 4 else None)
    elif cmd == "level":
        level(sys.argv[2])
    elif cmd == "score":
        import transcribe_cpp as t
        ref = "" if sys.argv[3] == "-" else open(sys.argv[3]).read()
        sd = load_dictate()
        gains = sys.argv[4:] or [sd.GAIN]
        with t.Model(MODEL) as m:
            for g in gains:
                filt = os.environ.get("EVAL_CHAIN", "").replace("GAIN", g) or sd.make_chain(g)
                pcm = to_pcm(sys.argv[2], filt)
                text = transcribe(m, pcm)
                rms = float(np.sqrt((pcm ** 2).mean())); peak = float(np.abs(pcm).max())
                w = f" WER {wer(ref, text) * 100:5.1f}%" if ref else ""
                print(f"gain {g}: rms {rms:.4f} peak {peak:.3f}{w} words {len(words(text))}: {text}",
                      flush=True)
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main()
