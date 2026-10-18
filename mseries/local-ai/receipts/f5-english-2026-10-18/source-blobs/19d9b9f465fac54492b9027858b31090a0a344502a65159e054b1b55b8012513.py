#!/usr/bin/python3
"""File-paced English Nemotron MLX cache-aware API probe; no mic or app input.

Run under the qualification supervisor's memory/fan/temperature/process guards.
Uses a scratch mlx-audio 0.5.9 overlay and a verified local model snapshot; never
downloads, installs packages, rewrites the model, or changes the default device.
"""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys
import threading
import time
import wave


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("model", "modules", "wav", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--reference-file", type=Path)
    parser.add_argument("--trials", type=int, default=3)
    parser.add_argument("--delay-ms", type=int, choices=(80, 160, 560, 1120), default=160)
    args = parser.parse_args()
    if args.output.exists():
        raise SystemExit("Retain existing evidence")
    receipt = {
        "complete": False, "engine": "mlx-vulkan-nemotron-cache-aware",
        "harness_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "microphone_recorded": False, "owner_windows_opened": False,
        "scope": ("Wall-paced 100 ms public file PCM through the actual cache-aware "
                  "feed/step/close API. No prefix re-decoding or desktop insertion. "
                  "MLX dispatch hardware has not been independently instrumented."),
        "requested_chunk_mode_ms": args.delay_ms, "trials": [],
    }

    def checkpoint():
        tmp = args.output.with_suffix(".tmp")
        tmp.write_text(json.dumps(receipt, indent=2) + "\n")
        tmp.replace(args.output)

    checkpoint()
    try:
        os.environ["HF_HUB_OFFLINE"] = "1"
        sys.path.insert(0, str(args.modules))
        import importlib.metadata
        import numpy as np
        import mlx.core as mx
        if importlib.metadata.version("mlx-audio") != "0.5.9":
            raise RuntimeError("This probe requires the pinned scratch mlx-audio0.5.9")
        # Omarchy's MIT GPU worker uses this lazy family import to avoid unrelated
        # model-family initialization (notably a Granite CPU float64 filterbank).
        family = "mlx_audio.stt.models"
        spec = importlib.util.find_spec(family)
        sys.modules[family] = importlib.util.module_from_spec(spec)
        from mlx_audio.stt.utils import load_model
        spec = importlib.util.spec_from_file_location(
            "realtime_metrics", Path(__file__).with_name("realtime-bench.py"))
        metrics = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(metrics)
        reference = (args.reference_file.read_text().strip()
                     if args.reference_file else metrics.REFERENCE)
        with wave.open(str(args.wav)) as wav:
            if (wav.getframerate(), wav.getnchannels(), wav.getsampwidth()) != (16000, 1, 2):
                raise ValueError("Expected16kHz mono signed16bit PCM WAV")
            pcm = np.frombuffer(wav.readframes(wav.getnframes()), "<i2").astype(np.float32) / 32768
        receipt.update({"mlx_version": mx.__version__, "mlx_audio_version": "0.5.9",
                        "audio_duration_s": len(pcm) / 16000,
                        "audio_sha256": hashlib.sha256(args.wav.read_bytes()).hexdigest(),
                        "reference": reference})
        started = time.monotonic()
        with mx.stream(mx.gpu):
            model = load_model(args.model, strict=True)
        receipt["load_s"] = time.monotonic() - started
        # The older MLX-layout conversion uses model_type=nemotron_asr, whereas
        # the new native HF conversion calls it nemotron_asr_streaming. Both are
        # English weights; set the trained context via the model's public config
        # attribute because transcription_delay_ms only handles the latter alias.
        lookahead = {80: 0, 160: 1, 560: 6, 1120: 13}[args.delay_ms]
        model.default_att_context_size = [70, lookahead]
        receipt.update({"model_type": model.model_type,
                        "attention_context": model.default_att_context_size,
                        "native_transformers_first_chunk_policy": model.model_type == "nemotron_asr_streaming",
                        "model_source_pin": json.loads((args.model / "source-pin.json").read_text()),
                        "runtime_source_pin": json.loads((args.modules / "source-pin.json").read_text())})
        checkpoint()
        for trial in range(args.trials):
            with mx.stream(mx.gpu):
                session = model.create_streaming_session(temperature=0.0, language="en")
            start = time.monotonic()
            events, feed_errors = [], []
            stop = threading.Event()
            fed = {"samples": 0, "finished_s": None}

            def feeder():
                try:
                    for offset in range(0, len(pcm), 1600):
                        chunk = pcm[offset:offset + 1600]
                        if stop.wait(max(0, start + (offset + len(chunk)) / 16000 - time.monotonic())):
                            return
                        session.feed(chunk)
                        fed["samples"] += len(chunk)
                    session.close()
                    fed["finished_s"] = time.monotonic() - start
                except Exception as error:
                    feed_errors.append(error)

            thread = threading.Thread(target=feeder, daemon=True)
            thread.start()
            text = ""
            try:
                while not session.done:
                    if feed_errors:
                        raise feed_errors[0]
                    if time.monotonic() - start > 180:
                        raise TimeoutError("Cache-aware session exceeded180s")
                    with mx.stream(mx.gpu):
                        deltas = session.step(max_decode_tokens=4)
                    if deltas:
                        text += "".join(deltas)
                        events.append({"wall_s": time.monotonic() - start,
                                       "audio_fed_s": fed["samples"] / 16000,
                                       "text": text})
                    else:
                        time.sleep(0.002)
                elapsed = time.monotonic() - start
            finally:
                stop.set()
                thread.join(2)
                session.cancel()
            receipt["trials"].append({
                "run": trial + 1, "first_text_s": events[0]["wall_s"] if events else None,
                "first_text_before_audio_end": bool(events and events[0]["wall_s"] < len(pcm) / 16000),
                "final_after_audio_s": elapsed - len(pcm) / 16000,
                "audio_feed_finished_s": fed["finished_s"], "elapsed_s": elapsed,
                "final_text": text, "normalized_wer": metrics.wer(reference, text),
                "events": events, "mlx_peak_memory_bytes": int(mx.get_peak_memory()),
            })
            checkpoint()
        receipt["complete"] = True
        checkpoint()
    except Exception as error:
        receipt.update({"failure_kind": type(error).__name__,
                        "failure_detail": str(error)[:1200], "quality_score": None})
        checkpoint()
        raise


if __name__ == "__main__":
    main()
