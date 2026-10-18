#!/usr/bin/env python3
"""Offline streaming benchmark for transcribe.cpp models on a fixed 16 kHz mono WAV.
Feeds 100 ms chunks as fast as the model accepts them and reports, per run:
total compute time, real-time factor, audio time at first text, and final text.
usage: stream-bench.py MODEL.gguf AUDIO.wav [runs] [threads]"""
import os, sys, time, wave, statistics
import numpy as np
import transcribe_cpp as t

model_path, wav = sys.argv[1], sys.argv[2]
runs = int(sys.argv[3]) if len(sys.argv) > 3 else 3
threads = int(sys.argv[4]) if len(sys.argv) > 4 else 6
w = wave.open(wav)
assert w.getframerate() == 16000 and w.getnchannels() == 1
pcm = np.frombuffer(w.readframes(w.getnframes()), np.int16).astype(np.float32) / 32768
dur = len(pcm) / 16000
chunk = 1600
res = []
with t.Model(model_path) as m:
    for r in range(runs + 1):  # first run is a discarded warm-up
        with m.session(n_threads=threads) as s, s.stream() as st:
            t0 = time.perf_counter(); first = None
            for i in range(0, len(pcm), chunk):
                st.feed(pcm[i:i + chunk])
                if first is None and st.text().display.strip():
                    first = (i + chunk) / 16000
            st.finalize()
            total = time.perf_counter() - t0
            text = st.text().display.strip()
        if r:
            res.append((total, first))
            print(f"run {r}: compute {total:.2f}s for {dur:.1f}s audio (RTF {total/dur:.2f}), first text at audio t={first}s")
print("median compute %.2fs RTF %.2f" % (statistics.median(x[0] for x in res), statistics.median(x[0] for x in res) / dur))
print("text:", text)
