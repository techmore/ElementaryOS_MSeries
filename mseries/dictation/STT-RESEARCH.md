# Speech-to-text research for F5 dictation (2026-10-18)

Scope: public sources only, read 2026-10-18. Nothing was installed or run on this
machine; no number below is a measurement of the M1 Pro. "Unverified" means it comes
from a model card, README or secondary aggregator and was not reproduced.

Current setup: Voxtype 1.1.1 (`linux-aarch64-cpu` Whisper build), `base.en`, 4 s
`eager_processing` chunks (`mseries/dictation/config.toml`). Eager mode transcribes
fixed chunks while recording continues. It is chunked batch decoding, not a streaming
model.

## 1. Open-weight STT landscape

WER = average English WER on the Hugging Face Open ASR Leaderboard (8 read/meeting
datasets, no long-form) unless noted. The leaderboard page itself would not render for
our fetcher, so figures come from model cards or aggregators and are indicative.

| Model | Params | License | Avg WER | Streaming | aarch64 CPU / Vulkan notes |
|---|---|---|---|---|---|
| Whisper base.en (current) | 74M | MIT | about 10 to 11 (unverified, not on cards we read) | No (we chunk) | Works now via whisper.cpp |
| Whisper large-v3-turbo | 809M, 4 decoder layers | MIT | 7.83 (model card) | No | whisper.cpp CPU only on Asahi; no Vulkan binary in Voxtype aarch64 |
| distil-large-v3.5 | about 0.8B | MIT (unverified) | beats large-v3 on English per HF blog; no number seen | No | whisper.cpp-compatible (unverified) |
| Parakeet TDT 0.6B v3 | 600M | CC-BY-4.0 | 6.34 (card) | Via NeMo script only; not in Voxtype | **Verified by a third party on M1 Pro Asahi** via Voxtype ONNX build (issue 579) |
| Nemotron Speech Streaming EN 0.6B | 600M | NVIDIA Open Model License | 6.93 at 1.12 s, 7.07 at 0.56 s, 7.67 at 0.16 s, 8.43 at 0.08 s (card) | **Yes, cache-aware** | Needs NeMo, Riva, Transformers or NeMo-Speech.cpp (GGUF); no ONNX mentioned. Not in Voxtype. Untested on aarch64 |
| Nemotron 3.5 ASR Streaming 0.6B | 600M | unverified (a mirror says OpenMDW-1.1) | not read | Yes, 40 locales | as above |
| Canary-Qwen-2.5B | about 2.5B | unverified | about 5.63 (aggregator) | No | LLM decoder, too heavy for CPU dictation |
| Cohere Transcribe (2026-03-26) | 2B | Apache-2.0 | **5.42** (card), reported #1 | No (card recommends transformers or vLLM) | In Voxtype ONNX (q4f16, 1.5 GB). Voxtype README claims 9 to 11x realtime on Zen 4; its own guide labels CPU speed "Slow". ARM speed unknown |
| IBM Granite Speech 4.1 2B | 2B | unverified | 5.33 (one aggregator) | No | Unverified, not in Voxtype |
| Voxtral Mini 4B Realtime 2602 | about 4B (3.4B LM + 970M encoder) | Apache-2.0 | not read; Mistral says matches offline open models at 480 ms delay | **Yes, 80 ms to 2.4 s configurable** | Card says single GPU with 16 GB+ VRAM, BF16, vLLM. No CPU or ARM path found. Poor fit |
| Kyutai STT 1B en/fr, 2.6B en | 1B / 2.6B | not on page (check repo) | chart only, no numbers | **Yes**, 0.5 s (1B) / 2.5 s (2.6B) delay | Server targets CUDA/Rust; MLX variant is for macOS. No Linux aarch64 path found |
| Moonshine v2 streaming | 34M to 245M (aggregator) | MIT (English models, per repo) | claims parity with models 6x larger; no numbers read | **Yes**, sliding-window encoder (arXiv 2602.12241, Feb 2026) | Library lists Linux and Raspberry Pi. Voxtype's Moonshine engine is the older v1 batch ONNX model (base 61M, 237 MB, no punctuation) |
| SenseVoice / Paraformer / Dolphin | 220 MB to 938 MB | varies | not English-leading | No | In Voxtype ONNX; CJK focused, skip for English |

Takeaways:

- Accuracy leaders in 2026 are LLM-decoder or large encoder-decoder models (Cohere
  Transcribe, Granite, Canary-Qwen). Best accuracy per CPU cost is Parakeet TDT 0.6B
  (about 6.3 WER, fastest class by RTFx on GPU; aggregator figure about 3300 RTFx, unverified).
- True streaming among models we could plausibly run on this laptop: Nemotron streaming
  0.6B (best accuracy-vs-latency curve, but no ready runtime in Voxtype) and Moonshine v2
  (tiny, not yet exposed by Voxtype). Voxtral Realtime and Kyutai are GPU-server class.
- Parakeet TDT, Whisper and Cohere via Voxtype are push-to-talk batch engines.
  For hold-to-talk dictation of 1 to 30 s, batch latency after release is what matters;
  Voxtype's own Moonshine doc makes the same argument.

## 2. MLX and GPU compute on Asahi

MLX on Linux:

- Upstream MLX 0.32.4 (2026-10-14) publishes `manylinux_2_35_aarch64` wheels for
  CPython 3.10 to 3.15, plus a `mlx-cpu` aarch64 wheel (PyPI JSON, read today). So a
  **CPU-only upstream MLX is installable on aarch64 Linux**. Requires glibc 2.35+; Ubuntu-based
  elementary OS 8 qualifies (not checked here). Upstream CUDA backend is NVIDIA only. Upstream
  has no Vulkan or Asahi GPU backend.
- GPU on Asahi: `joshuaswarren/omarchy-mlx` (pushed 2026-10-18, 94 stars) is a patch set
  giving `import mlx.core` a Vulkan backend on Honeykrisp, plus Core ML/ANE experiments. This
  is the "private MLX v0.7.33" this repo already pins (`mseries/local-ai/receipts/2026-10-16/source-pins.json`).
  Its README says "no Metal and no CPU fallback", so it is a different build from the upstream CPU wheel and the two
  should not be mixed in one venv.
- mlx-whisper 0.4.3 depends on `mlx>=0.11`, `torch`, `numba`, `tiktoken`. mlx-audio 0.5.9
  depends on `mlx>=0.31.1`, `transformers>=5.14`, `sounddevice`. parakeet-mlx 0.5.3 depends on
  `mlx>=0.22.1`, `librosa`. All are pure Python on top of `mlx`, so they should import on the
  CPU wheel, but **no report of any of them running on Asahi was found**. Unverified. Expect
  the CPU path to lose to ONNX Runtime and whisper.cpp NEON; MLX CPU is not tuned for speech.
  The omarchy-mlx fork's Vulkan MLX has not been shown running these STT packages either.
- ANE: omarchy-mlx ships `mlx-omarchy-parakeet` (Core ML Parakeet encoder on the ANE) with M1 listed as "Parakeet
  islands", M1 Max "whole encoder", and **M1 Pro "Untested"**. Our own ANE-PREFLIGHT.md shows only build and overlay
  compatibility, not execution. Treat ANE STT as out of scope for now.

Vulkan/Honeykrisp for llama.cpp and ggml:

- omarchy-mlx ENGINES.md reports llama.cpp (Vulkan) on Honeykrisp with patches under review
  (omacom/mesa PR 6) giving 13 to 18x decode gains versus system Mesa 26.2.3 on M1 Max / base M1
  (author's numbers, not reproduced; not M1 Pro; LLM workloads, not Whisper).
- whisper.cpp v1.9.5 (2026-10-06) has a ggml Vulkan backend, and its Docker Vulkan image is amd64 only. The Voxtype
  author also stated Honeykrisp was "not stable enough to test ggml-Vulkan against" in Aug 2026
  (issue 579 reporter). Voxtype ships a Vulkan binary for x86_64 only; **no aarch64 Vulkan asset exists in 1.1.1**.
  Using Vulkan Whisper here means building Voxtype or whisper.cpp from source against the patched Mesa. Gain is
  unknown: Whisper encoders are matmul heavy, so large-v3-turbo could benefit, but no data exists.

## 3. Voxtype engine support (v1.1.1, released 2026-10-15)

- aarch64 release assets: `cpu` (Whisper), `onnx` (all ONNX engines), `audio-bridge`, `osd`, `osd-gtk4`,
  `osd-quickshell`. No aarch64 Vulkan or CUDA.
- ONNX engines: Parakeet (English, TDT 0.6B v2/v3), Moonshine (v1 batch), SenseVoice, Paraformer, Dolphin,
  Omnilingual, Cohere Transcribe. Switch with `voxtype setup onnx --enable` then `engine = "parakeet"`
  (README, docs/PARAKEET.md). Models load on first use and unload when idle.
- Streaming: Voxtype has `eager_processing` (chunked) for Whisper, and a cloud streaming engine (Soniox). No local
  streaming-model engine (Nemotron, Moonshine v2) was found in its docs.
- Field report: Parakeet TDT 0.6B v3 ONNX runs on an M1 Pro under Asahi with Voxtype 1.0.0-rc2 (issue 579, 2026-08-18);
  2.4 GB model download; output correct; no latency numbers given. Only a cosmetic ORT CPU vendor warning.
- Known Parakeet issue from its docs: can repeat words ("no no no"). Cohere and Parakeet TDT output punctuation;
  Moonshine v1 and Whisper (via Voxtype) need post-processing.

## 4. Recommendation and staged plan

Adopt next: **Parakeet TDT 0.6B v3 via the Voxtype ONNX binary**, with the Whisper `cpu` build kept as the fallback.
Reasons: only high-accuracy option with a third-party M1 Pro Asahi success report and zero new code on our side
(same hotkey, typing, service). Expected gain is lower English WER (about 6.3 versus roughly 10 for base.en)
and punctuation. True streaming is not part of this stage.

Stage 0, baseline (no installs on the owner's running setup): build a fixed test set. Use 30 to 50 clips: about
half LibriSpeech/TEDLIUM-style public audio with reference text, plus 20 clips of the owner's own dictation
(recorded with consent) with hand-made references including commands, filenames, code terms. Store under
`mseries/dictation/bench/` (not committed if personal).

Stage 1, A/B offline, in a scratch directory, not touching the live service or audio devices: run each engine
on the same WAV files with the Voxtype CLI (`voxtype transcribe`-style file input if supported; otherwise the
engines' own runners). Compare Whisper base.en, small.en, large-v3-turbo (whisper.cpp), Parakeet TDT v3,
Moonshine base, and Cohere Transcribe q4f16. Metrics, each with N runs, **medians and spread, not means**:

| Metric | How |
|---|---|
| WER and punctuation-insensitive WER | jiwer after identical text normalisation, per clip then median and pooled |
| Time to text after release | wall clock from end of audio to final string, median and p90, 10 runs per clip |
| RTF | decode seconds / audio seconds, warm (second run onward) and cold model load separately |
| Peak RSS | `/usr/bin/time -v` |
| Thermals/noise | fan RPM sampled during runs; the local-ai README already treats RPM as a noise proxy |
| Battery energy | optional, only on battery, same clip loop |

Rules: same clips, same order, CPU idle baseline recorded, alternate engine order between rounds
(ABBA), discard the first warm-up run, report the clip count with every number, and do not call a result
"confirmed" or "parity" from fewer than 3 rounds. Keep the owner's brightness, display and audio settings
untouched; use WAV file input rather than the live microphone.

Stage 2, live trial: switch only `engine = "parakeet"` in the user config, keep the Whisper config next to it
for a one-line rollback, and have the owner use it for a week. Log nothing about content.

Stage 3, Vulkan Whisper (optional, research): build whisper.cpp with `GGML_VULKAN=1` against the patched
Honeykrisp stack in a scratch prefix and benchmark large-v3-turbo CPU versus Vulkan with the Stage 1 harness.
Only worth doing if Stage 1 shows large-v3-turbo is the preferred accuracy and CPU time is the problem.
It competes with the MLX LLM worker for the GPU, so it must respect the local-ai admission policy.

Stage 4, real streaming (watch list, no work yet): Nemotron streaming 0.6B (needs a runtime: NeMo-Speech.cpp
GGUF is the likeliest on aarch64) and Moonshine v2 streaming (MIT, small). Both require a custom client
that types partial text; Voxtype does not do this today. Ask upstream (peteonrails/voxtype) whether a local
streaming engine is planned before building anything. MLX-based STT (mlx-whisper, parakeet-mlx, mlx-audio) is a
low priority: no Asahi evidence and the CPU wheel is unlikely to beat ONNX Runtime.

Unverified or open questions:

- ARM CPU speed of Parakeet v3 and Cohere Transcribe on this M1 Pro (all speed claims above are x86 or GPU).
- Exact WER of base.en and distil-large-v3.5 on the same leaderboard.
- Licenses for Kyutai, Granite 4.1 and Nemotron 3.5; the model cards must be read before any redistribution.
- Whether Voxtype's ONNX build fits next to the current `cpu` binary at `/usr/local/bin/voxtype` (the installer
  pins a SHA-256 for the `cpu` asset; an ONNX switch needs a second pinned hash).

## Sources

- Voxtype v1.1.1 release assets and README, docs (MOONSHINE.md, PARAKEET.md, MODEL_SELECTION_GUIDE.md, CONFIGURATION.md): https://github.com/peteonrails/voxtype (read 2026-10-18 via gh)
- Voxtype issue 579, Asahi M1 Pro Parakeet field report (2026-08-18): https://github.com/peteonrails/voxtype/issues/579
- Cohere Transcribe model card (2026-03): https://huggingface.co/CohereLabs/cohere-transcribe-03-2026
- Parakeet TDT 0.6B v3 (2025-08-14): https://huggingface.co/nvidia/parakeet-tdt-0.6b-v3
- Nemotron Speech Streaming EN 0.6B (2026-03): https://huggingface.co/nvidia/nemotron-speech-streaming-en-0.6b
- Nemotron 3.5 ASR Streaming 0.6B (2026-06-04): https://huggingface.co/nvidia/nemotron-3.5-asr-streaming-0.6b
- Whisper large-v3-turbo: https://huggingface.co/openai/whisper-large-v3-turbo
- Open ASR Leaderboard blog (2025-11): https://huggingface.co/blog/open-asr-leaderboard
- Aggregators (secondary, unverified): https://codesota.com/speech/stt-leaderboard , https://northflank.com/blog/best-open-source-speech-to-text-stt-model-in-2026-benchmarks
- Moonshine v2 paper (2026-02): https://arxiv.org/abs/2602.12241 ; repo and license: https://github.com/moonshine-ai/moonshine
- Kyutai STT: https://kyutai.org/stt
- Voxtral Mini 4B Realtime 2602: https://huggingface.co/mistralai/Voxtral-Mini-4B-Realtime-2602 , https://mistral.ai/news/voxtral-transcribe-2
- MLX PyPI wheels (0.32.4, 2026-10-14): https://pypi.org/project/mlx/ , https://pypi.org/project/mlx-cpu/ ; mlx-whisper, mlx-audio, parakeet-mlx metadata via https://pypi.org/pypi/<name>/json
- omarchy-mlx (Vulkan/ANE MLX for Asahi): https://github.com/joshuaswarren/omarchy-mlx
- whisper.cpp v1.9.5 (2026-10-06): https://github.com/ggml-org/whisper.cpp
- Local: `mseries/local-ai/README.md`, `mseries/local-ai/ANE-PREFLIGHT.md`, `mseries/install-dictation.sh`, `mseries/dictation/config.toml`
