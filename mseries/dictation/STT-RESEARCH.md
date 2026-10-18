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

---

# Addendum 2026-10-18 (b): macOS benchmark to match, and what ports to Asahi

Scope: public sources read 2026-10-18 (web search, `gh`). Nothing installed, downloaded, run or timed here.
"Unverified" = vendor, aggregator or model-card claim not reproduced. Extends sections 1 to 4 above; does not repeat them.
Section 4's recommendation (Parakeet TDT v3 via Voxtype ONNX) stands as stage 1; this addendum adds a better runtime
candidate for stages 3 and 4.

## A. macOS on Apple Silicon: the quality and latency bar

| Option | Engine / hardware path | Evidence found | Verdict |
|---|---|---|---|
| Apple SpeechAnalyzer / SpeechTranscriber (macOS 26) | Apple's own on-device model, system managed | One vendor-run test (Inscribe team, M2 Pro 32 GB, LibriSpeech): 2.12 % test-clean, 4.56 % test-other, versus Whisper Small (WhisperKit Core ML) 3.74 / 7.95, Whisper Base 5.42 / 12.51, legacy SFSpeechRecognizer 9.02 / 16.25. About 3x faster than Whisper Small. English only, read speech; the authors warn accents, meetings and distant audio may differ. No Parakeet in the test. Vendor-run, single machine | Strongest zero-install baseline on a Mac. Streaming volatile results exist in the API (Apple docs, not re-read today). No accent or technical-vocabulary data |
| Parakeet TDT 0.6B v3 via FluidAudio (Core ML / ANE) | ANE | Core ML model card: about 110x realtime batch on **M4 Pro**; FluidAudio streaming Parakeet EOU 120M: 12x RTFx, 4.9 % WER, M4 Pro. Third-party speed test (M4, one short clip): FluidAudio 0.19 s, parakeet-mlx 0.50 s, mlx-whisper large-v3-turbo 1.02 s | Best latency on macOS; no M1 Pro numbers found |
| parakeet-mlx, mlx-whisper, mlx-audio, mlx-qwen3-asr | MLX / Metal | Exist and work on macOS. mlx-audio and voxmlx (PyPI) offer Voxtral Realtime streaming with 4-bit weights; mlx-qwen3-asr offers 4/8-bit and streaming | Fine on a Mac. Not portable to Asahi as-is (MLX has no upstream Vulkan/Metal path on Linux) |
| Qwen3-ASR 0.6B / 1.7B | Audio encoder plus Qwen3 LM, Apache-2.0 (GGUF cards) | Card claims LibriSpeech-other 3.38 (1.7B) versus 3.97 for Whisper-large-v3 (third-party doc, unverified) | LLM-style decoder, strong English plus 30 languages, no streaming in the transcribe.cpp port |
| Qwen-Audio-3.0-ASR (arXiv 2609.07549, Sept 2026) | Closed or unknown; abstract only | Claims SOTA or competitive, a streaming variant, and native single-pass "transcription polishing" of disfluent speech. No numbers, sizes or weight release found on the abstract page | Watch item, not actionable |
| Voxtral Mini 4B Realtime | MLX (voxmlx) on Mac | Configurable 80 ms to 2.4 s delay (earlier section). No Apple-Silicon latency or WER data found | Interesting for words-while-speaking on a Mac; too big for Asahi CPU |
| Dictation apps | VoiceInk: whisper.cpp plus FluidAudio Parakeet plus GGUF; Hex, MacParakeet, Murmur: Parakeet TDT v3 via FluidAudio; Handy: Whisper plus Parakeet (v0.9.8, 2026-10-03, MIT, 34k stars); MacWhisper: Whisper family; Superwhisper: Whisper-family, an open feature request asks for MLX-accelerated Parakeet; Wispr Flow: cloud, about 700 ms, closed | App pages are mostly vendor or affiliate marketing; engine lists unverified except Handy and VoiceInk's own pages | The leading Mac apps converged on Parakeet TDT v3 locally; the premium products add an LLM cleanup stage (Wispr cloud, Superwhisper "modes") |

Take-away for the bar: on a Mac, the quality target is roughly "SpeechAnalyzer or Parakeet TDT v3, plus LLM cleanup, text
appearing at release or live". English WER of the best local models on LibriSpeech test-clean is 1.3 to 2.5 %; it is the
**noisy, accented, jargon-heavy dictation** where the gap to base.en shows, and nobody publishes that. We must measure it ourselves.

## B. Portability to Linux on Apple Silicon (Asahi, aarch64, Honeykrisp, no ANE)

Not portable: SpeechAnalyzer, Core ML / FluidAudio (ANE), MLX Metal. Upstream MLX has aarch64 Linux CPU wheels only
(section 2 above); the omarchy-mlx Vulkan fork is experimental. Voxtral Realtime and Qwen-class LLM-decoder models are
too heavy for 10 CPU cores in a live loop (unverified for this box, no data).

### New finding: transcribe.cpp (handy-computer) is the best portable runtime found

- Repo https://github.com/handy-computer/transcribe.cpp (MIT, 2,059 stars, pushed 2026-10-18, latest v0.4.0 released 2026-10-12). By the Handy author (CJ Pais); announced on the Mozilla AI blog 2026-06-30 per a secondary summary.
- ggml runtime with Metal, Vulkan, CUDA, HIP and a tinyBLAS CPU path. **v0.4.0 publishes a prebuilt `transcribe-native-0.4.0-linux-aarch64-cpu-vulkan.tar.gz`** (read from the GitHub release asset list). Vulkan build flag `-DTRANSCRIBE_VULKAN=ON`; the Arch AUR has `transcribe-cpp-vulkan`. Bindings: Python, Rust, Swift, TypeScript, C API.
- 16 model families, 60+ variants as GGUF, each WER-tested against its reference. Includes everything this research cares about in one runtime: Parakeet (TDT 0.6B v2/v3, `parakeet-unified-en-0.6b` streaming), **Nemotron Speech Streaming EN 0.6B and Nemotron 3.5 ASR Streaming** (true cache-aware streaming, `--stream-chunk-ms`, lookahead 0/80/480/1040 ms), **Moonshine Streaming tiny/small/medium**, Whisper large-v3-turbo, Cohere Transcribe, Qwen3-ASR, Canary-Qwen, Granite Speech 4.1 and 5.0 TurboCTC (Apache-2.0, 470M, offline), Voxtral Realtime, Silero VAD.
- Streaming API: `transcribe_stream_begin / feed / finalize`. This is the missing piece for "words appear while speaking": a small client can type stable partial text.
- Accuracy, LibriSpeech test-clean, Q8_0, transcribe.cpp's own pipeline (greedy): Parakeet TDT v2 1.69 %, v3 1.94 %, Nemotron streaming EN 2.31 % offline and **2.29 to 2.31 % streaming at 1.12 s chunk**, Moonshine streaming tiny 4.52 / small 2.54 / medium 2.16 %, Qwen3-ASR 0.6B 2.11 % / 1.7B 1.62 %, Granite 5.0 TurboCTC 1.33 %. Clean read speech only; do not compare these with the leaderboard averages in section 1 (different datasets).
- Speed published only for Apple M4 Max and Ryzen 7 4750U (mean of 3 after 1 warmup, not medians). Examples from the model cards: Moonshine streaming medium Q8_0 on M4 Max **CPU** 235 ms for an 11 s clip (46.8x), 1.12 s for 35 s; the Nemotron card shows about 330 ms CPU for the 11 s clip on M4 Max (Q4_K_M and Q8_0); on the Ryzen 4750U Vulkan, a 11 s clip took 424 to 426 ms for one table, and the Moonshine card shows Vulkan **slower** than CPU on some rigs. **No M1 Pro, Asahi or Honeykrisp numbers exist.** M4 Max CPU is certainly faster than an M1 Pro CPU; treat these as upper bounds.
- Caveats: the release is 6 days old, v0.x API; no issue mentioning Asahi or Honeykrisp was found (search returned none); Honeykrisp Vulkan compute correctness for ggml is unproven (Voxtype's author called it unstable for ggml-Vulkan in Aug 2026, section 2). Nemotron license is NVIDIA Open Model License (not OSI); Parakeet v3 CC-BY-4.0; Moonshine MIT; Granite 5.0 TurboCTC Apache-2.0 (non-commercial variant exists, avoid). Handy itself uses WebKitGTK and wtype/dotool on Linux and has its own post-process LLM hook (`--toggle-post-process`), but is a separate app from Voxtype; adopting it would replace our service.

### LLM-style cleanup (small local LLM post-process)

- Evidence is thin and mostly community: small fine-tunes exist (a 0.5B Qwen2.5 cleaner aimed at CPU; a Qwen3.5-2B QLoRA cleaner; a Reddit-reported 0.8B model), all vendor or model-card claims, none benchmarked by us.
- A second generation pass sits directly on the critical path between release and text (the Qwen-Audio-3.0 report states this cost explicitly). On this CPU, a 0.5B to 2B model emitting about 40 tokens will add roughly hundreds of ms to a few s (estimate, not measured).
- Reported failure mode: small models delete real content or keep the wrong side of a self-correction; prompting did not fix it, training data did. Mitigations: thinking off, length and edit-distance guard that falls back to the raw transcript, and cleanup only above a word-count threshold or on a separate hotkey.
- Parakeet TDT, Nemotron, Cohere and Qwen3-ASR already output punctuation and casing, so the cleanup LLM mostly removes fillers and fixes jargon. Test whether it is needed at all before shipping it.
- The repo already has a local LLM stack (mseries/local-ai). Cleanup must obey its admission policy so it does not fight the GPU worker.

### Ranked recommendation for Asahi (B)

1. **Parakeet TDT 0.6B v3 (or v2, English only) via the Voxtype ONNX binary.** Unchanged from section 4: lowest effort, one third-party M1 Pro Asahi success report.
2. **transcribe.cpp aarch64 prebuilt, Parakeet TDT v2/v3 Q8_0 on CPU, as the same-WAV A/B partner.** Same weights, different runtime; shows whether ggml/tinyBLAS beats ONNX Runtime on this CPU. Cheap: one tarball plus one GGUF.
3. **transcribe.cpp Nemotron Speech Streaming EN 0.6B Q8_0 (CPU first, Vulkan second), with a thin client that types partial text.** Best accuracy-vs-latency curve (about 2.3 % clean WER at 1.12 s chunks), the only candidate here giving true words-while-speaking. Licence is not OSI; needs a new client (Voxtype cannot do it).
4. **Moonshine Streaming small (140M, MIT).** Fallback streaming if Nemotron is too slow on CPU; lower accuracy margin unknown on noisy speech.
5. Whisper large-v3-turbo CPU or Vulkan (section 4, stage 3): only if Parakeet fails on the owner's accent or vocabulary.
6. Not recommended now: Voxtral Realtime 4B, Canary-Qwen, Qwen3-ASR 1.7B, Granite 4.1 2B (too heavy for live CPU use, unverified), MLX-based STT on Asahi.

### Concrete next step (no installs without the owner's approval of the scratch location; Mac not required)

Extend Stage 1 of section 4: in a scratch directory (not `/usr/local/bin`, not the live service), download the v0.4.0 aarch64 tarball and Q8_0 GGUFs for `parakeet-tdt-0.6b-v3`, `nemotron-speech-streaming-en-0.6b` and `moonshine-streaming-small`, verify SHA-256 against the release, and run `transcribe-cli` on the fixed WAV set. Then add the Voxtype ONNX Parakeet and the current Whisper `base.en` as comparators. Use WAV file input only; no microphone, no display, no services.

### Honest benchmark protocol (additions to section 4)

- Test set: 20 owner dictation clips (consent, hand-made references) with code terms, filenames, accented or fast speech, background noise, plus 20 public clips. LibriSpeech-clean alone proves nothing: every model above scores 1.3 to 2.5 % there.
- Metrics per engine: normalised WER (jiwer, identical normaliser), separate WER on a jargon-term list, time from end-of-audio to final text (median and p90, at least 10 runs per clip, warm), cold load time, peak RSS, CPU-seconds per audio second, fan RPM.
- Streaming: first-partial latency, final-minus-last-audio latency, and partial-text instability (percentage of words rewritten after first display) at chunk sizes 160, 560 and 1120 ms. Feed the WAV at real time pace.
- Cleanup: A/B each engine raw versus raw plus LLM cleanup on the same clips; score WER against the reference, count deleted content words, and time. Count a cleanup as a win only if it lowers WER or edit distance on at least 3 rounds without deletion errors.
- Protocol rules: ABBA ordering, discard first warm run, report N with every number, medians not means (vendor tables above are means of 3 and not comparable), CPU governor and thermals recorded, brightness, display and audio untouched. No word "confirmed" or "parity" from fewer than 3 rounds.

### Still unverified

- Any transcribe.cpp or Voxtype-ONNX speed on M1 Pro or Asahi; whether ggml-Vulkan is even correct on Honeykrisp for these encoders.
- Real accented or noisy WER of every model above; all numbers here are LibriSpeech or vendor tests.
- SpeechAnalyzer accuracy beyond the single Inscribe test; engines of Superwhisper, MacWhisper and Wispr Flow (only VoiceInk, Handy, Hex pages gave concrete lists).
- Qwen-Audio-3.0-ASR weights, size and licence.

### Sources (read 2026-10-18)

- transcribe.cpp repo, README, models docs, catalog, v0.4.0 release assets (2026-10-12): https://github.com/handy-computer/transcribe.cpp ; model card https://huggingface.co/handy-computer/moonshine-streaming-tiny-gguf ; Arch AUR https://aur.archlinux.org/packages/transcribe-cpp-vulkan (search snippet only)
- Handy v0.9.8 (2026-10-03) README: https://github.com/cjpais/Handy
- Apple SpeechAnalyzer vs Whisper (Inscribe, reported 2026-07-14): https://www.gigazine.net/gsc_news/en/20260714-apple-speech-analyzer-benchmark/
- FluidAudio benchmarks and Parakeet Core ML card: https://docs.fluidinference.com/reference/benchmarks.md , https://huggingface.co/FluidInference/parakeet-tdt-0.6b-v3-coreml
- Mac speed test (M4, one clip, 2025): https://github.com/anvanvan/mac-whisper-speedtest ; MLX benchmark paper https://arxiv.org/abs/2510.18921
- voxmlx: https://pypi.org/project/voxmlx/ ; mlx-audio https://github.com/Blaizzy/mlx-audio ; mlx-qwen3-asr https://github.com/moona3k/mlx-qwen3-asr/
- Qwen3-ASR GGUF cards: https://huggingface.co/handy-computer/Qwen3-ASR-1.7B-gguf ; Qwen-Audio-3.0-ASR report: https://arxiv.org/abs/2609.07549
- Mac dictation app comparisons (marketing, unverified): https://tryvoiceink.com/best-superwhisper-alternatives , https://wisprflow.ai/post/wispr-flow-vs-superwhisper , https://www.bitdoze.com/fluidvoice-mac-dictation/ , https://superwhisper.userjot.com/board/p/mlx-acceleration-for-local-parakeet-models
- Cleanup models (community, unverified): https://huggingface.co/abhiram3040/simplewords-dictation-cleanup-v2 , https://app.alphaneural.io/models/Quobi/Quill

## Addendum 2026-10-18 (c): ANE status on this machine (checked, not run)

- Running kernel `7.1.12-2-...-sep-ARCH` already loads `ane.ko`; `/dev/accel/accel0` exists (root:render). Nothing has been executed on it by us.
- omarchy-ane v0.4.9 (2026-10-16, https://github.com/joshuaswarren/omarchy-ane) lists **M1 Pro (T6000) as "on by default"**: bind plus exact fp16 execution, one passing row (H13 smoke). Its Parakeet encoder was shown bit-exact on M1 and M2 Max, not on M1 Pro.
- omarchy-mlx v0.7.33 (MIT, https://github.com/joshuaswarren/omarchy-mlx) ships `mlx-omarchy-parakeet` (Core ML Parakeet on the ANE; install with `install.sh --ane`) but marks the M1 Pro **Untested** for both GPU and ANE. No M1 Pro speed or WER figures exist publicly.
- Risk: upstream says a hung ANE submission needs a reboot. Next step is `omarchy-ane-check` (read-only), then `--smoke` (20 add calls), then Parakeet on a fixed WAV against the CPU path, medians of 10+ warm runs. Kernel-side findings go to DeepSeek via GitHub.
- Correction: ANE-PREFLIGHT.md (2026-10-12) says nothing is installed; the driver is now in the running kernel.

## Addendum 2026-10-18 (d): ANE run on this M1 Pro (measured once, not yet usable for dictation)

Setup, all under `~/.local/share/mseries/ane/` (nothing system-wide, no kernel/boot change): omarchy-ane v0.4.9 built from source; omarchy-mlx v0.7.33 aarch64 wheel (SHA-256 checked) in a venv with numpy and protobuf added; pinned Parakeet TDT 0.6B v3 Core ML reference (481 MB, 12 files hash-verified).

- `omarchy-ane-check`: all checks pass except a permission note (`/dev/accel/accel0` is root:render 0660; our user is in `render`).
- `omarchy-ane-smoke`: **20/20 calls bit-exact on t6000, median 0.049 ms.** The ANE executes on this Mac.
- `mlx-omarchy-parakeet verify` (pinned LibriSpeech clip, 10.4 s): runs end to end, transcript starts correct ("He hoped there would be stew for dinner, turnips and carrots...") but ends in garbage tokens, and status is **diverged** (`mel_sha256`, `encoder_hidden_sha256` do not match the golden). Likely related to the Mesa 26.0.8 warning (upstream wants 26.2.4+ for the MLX Vulkan kernels), unproven.
- Time: 63 s first run (one-time encoder emission), then 1.98 s and 1.96 s warm for 10.4 s of audio (2 runs, not a benchmark). Whisper base.en with 6 threads took 1.07 s median for 7 s. So no speed win yet.
- The shipped CLI only transcribes the pinned fixture; arbitrary audio is in `mlx/coreml/parakeet_dictation.py`, which upstream says is not qualified until a hardware acceptance receipt exists.

Not wired into F5. Next: update Mesa (kernel-adjacent graphics stack, ask owner), re-run verify, then try `parakeet_dictation` on owner clips against the CPU path with 10+ warm runs.

## Addendum 2026-10-18 (e): Mesa 26.2.4 private Honeykrisp fixes the Parakeet mismatch

- Ubuntu has no Mesa newer than 26.0.8, so the system Mesa was left alone. Built stock Mesa 26.2.4 (tarball SHA-256 `bce5f7fbebb934373b86c999a064d52fb5065878dc57f287f95346648ec832e9`, computed by us; Mesa publishes none) with only the Apple Vulkan driver (`-Dvulkan-drivers=asahi`, no GL/gallium) into `~/.local/share/mseries/ane/mesa-hk`, 636 steps, a few minutes with `-j6`. Used per process with `VK_DRIVER_FILES=~/.local/share/mseries/ane/mesa-hk/share/vulkan/icd.d/asahi_icd.aarch64.json`.
- `mlx-omarchy-parakeet verify` with that ICD: **status "match" on 3 of 3 runs** (mel and encoder hashes now equal the golden), where the system Mesa gave "diverged". So the old Mesa was the cause. (The trailing dots and stray characters in the transcript are in the pinned golden itself.)
- Speed unchanged: 1.99 s and 1.98 s warm for the 10.4 s clip (first run 35 s, one-time work). Whisper base.en at 6 threads was 1.07 s for 7 s of audio, so the ANE path is not faster yet; its benefit would be CPU and power, not measured.
- Still not wired into F5: the CLI only runs the pinned fixture; arbitrary audio needs `mlx/coreml/parakeet_dictation.py`, unqualified until a hardware acceptance run.
