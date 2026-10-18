# English words while speaking: M1 Pro 32 GB, October 18, 2026

**Follow-through:** [English F5 app acceptance, sustained tests and deployment](F5-ENGLISH-ACCEPTANCE.md)
and [the canonical no-repeat ledger](QUALIFICATION-INDEX.md) track later work.
The Parakeet0.5.6 full-input API observation below does not apply to the subsequently
tested Nemotron0.5.9 cache-aware MLX feed/step implementation.

**Decision:** advance Nemotron's CPU streaming path for the next F5 integration;
retain native ANE and MLX Vulkan as qualified file-input alternatives. Nemotron
160 ms produced first draft words in **0.851 s median**, versus **1.452 s** for
MLX GPU Parakeet and **2.97 s warm committed output** for our ANE controller.
Those output policies differ. These are end-to-end streaming experiments on the
working Linux desktop, not advertised kernel throughput or a factory-image test.
The runtime and human F5 default were not changed by this benchmark.

The owner clarified **English speech → English text only**. Optional English
grammar suggestions belong in a separate field; raw words stay visible and are
never automatically replaced. Earlier foreign-language experiments remain
historical evidence and are excluded from this recommendation.

[Receipts, checksums, source snapshots and pins](../local-ai/receipts/realtime-english-2026-10-18/)
are public. [Source candidate PR155](https://github.com/techmore/ElementaryOS_MSeries/pull/155)
is draft: publication of measurements does not approve deployment of that branch.

## Measured streaming results

M1 Pro / 32 GB, elementary desktop, kernel `7.1.12-2-20261017.20-sep-ARCH`.
One public 10.435 s LibriSpeech clean English clip, three consecutive runs per row.
CPU streams received wall-paced 100 ms buffers. Model loading is separate and
reported in receipts. First run was retained, not discarded as warm-up. MLX had a
recorded 0.477 s silence initialization before its real trials. ANE's first run
was cold, followed by two runs reusing its worker. Rows ran in separate guarded
queues, not randomized ABBA pairs. Desktop/background allocations could change.

| Engine | First words, median (range), s | Final tail, median, s | Final normalized WER | Max sampled fan / temperature | Minimum available GiB |
|---|---:|---:|---:|---:|---:|
| Nemotron 0.6B Q8, CPU 4 threads, 160 ms operating point | 0.851 (0.845–0.851) | 0.059 | 0%, all 3 | 2518 RPM / 45.61°C | 16.76 |
| Nemotron, 560 ms operating point | 1.177 (1.174–1.179) | 0.106 | 0%, all 3 | 2518 / 45.61°C | 16.86 |
| Parakeet TDT v3, MLX Vulkan rolling draft | 1.452 (1.451–1.464) | 0.737 | 0%, all 3 | 2522 / 47.02°C | 10.89 |
| Moonshine tiny, official native ORT | 1.561 (1.544–1.567) | 0.636 | 14.29%, all 3 | 2519 / 43.91°C | 20.05 |
| Moonshine small, official native ORT | 1.590 (1.585–1.649) | 0.451 | 7.14%, all 3 | 2519 / 45.34°C | 19.04 |
| Parakeet Unified Q4, CPU 4 threads | 3.497 (3.489–3.563) | 1.455 | 0%, all 3 | 2531 / 47.76°C | 17.26 |
| Existing native ANE controller, two-pass committed words | 2.97 warm; 4.26 cold | 0.455* | Exact normalized words, all 3 | 2518 / 44.78°C | 15.26 |

*ANE tail is elapsed minus clip length, median of all three trials (0.25–0.66 s),
including capture/controller overhead. Other rows measure from audio-feed completion.
MLX's two-pass stable prefix appeared at 1.929 s median (1.896–1.942), separately
from its revisable draft. ANE includes worker startup on its cold trial; CPU/MLX
first-word numbers exclude model load. This is a comparison of usable pipelines,
not equal-policy silicon throughput or proof that CPU always beats ANE.

Nemotron CPU used about 1.25 GB peak process RSS at 160 ms. The 560 ms setting
roughly halved aggregate CPU time (7.0–7.2 versus 12.8–13.6 CPU seconds per clip)
while adding ~0.33 s to first words. It is a useful optional lower-work setting,
not a demonstrated battery saving. MLX reported 2,633,179,136 bytes peak allocator
memory. Its process-family RSS sampling excludes GPU allocations/other resident
services and is not a complete physical-memory measurement. ANE owned family RSS
sum peaked at 1,211,072,512 bytes; shared pages can be counted twice. Available
system RAM is the admission measure, not an estimate of model size.

Moonshine tiny substituted “flower-fat and sauce” and appended “you”; small used
“flower fattened sauce” and appended “Ross.” These completed failures are retained.
The official ORT runtime differs from the previously tested slower Moonshine GGUF
port; neither result should be attributed to every Moonshine implementation.

### Three additional speakers

One run per clip per engine; no selective retries. All six final transcripts had
zero normalized word errors on this small extension.

| LibriSpeech test-clean ID | Nemotron160 first draft, s | Unified CPU first draft, s |
|---|---:|---:|
| 1320-122617-0022 | 0.854 | 2.314 |
| 8455-210777-0028 | 1.160 | 3.467 |
| 1580-141083-0051 | 1.158 | 2.251 |

This is four clean literary speech clips overall, not a general accuracy ranking.
Noise, accents, names, code, interruptions, long dictation and the owner's live
microphone need separate qualification. Case/punctuation are ignored by WER;
transient “din”, “turnip” or other partial words remain visible in event traces.
Zero final WER does not mean every provisional token was correct.

## Actual English panel workflow

A wall-paced public WAV drove real Nemotron160 CPU ASR, actual GTK4 text widgets
in a private display/session, and the existing supervised Qwen3.5 4B MLX endpoint.
Original English appeared at **1.290 s** from child launch; the first optional
English suggestion appeared at **2.598 s**, during speech. Four grammar requests
completed in 1.30, 2.54, 3.40 and 4.31 s; the last started after speech ended.
Original text remained intact, the final exact-source suggestion enabled Copy,
and the first preview preceded the nominal 10.435 s audio end.

This passed on the receipt's frozen panel source. A later fix coalesces GTK's
transient delete/insert notifications; its separate synthetic native UI regression
passed with latest-only requests, stale rejection and no duplicate final review.
It has not repeated the real model cohort. The current source defaults to grammar
**after** dictation; live cleanup is opt-in to reduce work. These tests used no
microphone, physical F5 or owner app insertion. The earlier owner's human F5 pass
belongs to its older installed version, not this candidate.

Grammar is not semantic ground truth: previews can complete fragments or remove
list conjunctions. Keep raw text and require a deliberate copy. We do not use this
4B result as evidence for kernel diagnosis or automatic OS changes.

## What Apple actually exposes

Apple's public SpeechAnalyzer design decouples audio input and result streams,
uses audio sample time ranges, and can emit provisional “volatile” results that
revise until finalized. That is the UI behavior to reproduce: immediate draft
feedback with a clear final boundary. SpeechTranscriber serves Notes, Voice Memos
and Journal; AssetInventory manages its assets and updates. The service executes
outside an app's address space, which does not make its system RAM free.
[Apple WWDC25 explanation](https://developer.apple.com/videos/play/wwdc2025/277/).

This public API does not establish the exact current keyboard Dictation model,
neural architecture or per-operation ANE/GPU placement. Speech.framework and its
system assets are not a Linux backend we can install. The useful transferable
ideas are shared resident workers, cancellable sessions, draft/final separation
and managed assets. Apple's Dictation also permits typing during dictation on
Apple silicon; our append-only controller currently ends its session on typing.
[Mac Dictation behavior](https://support.apple.com/guide/mac-help/use-dictation-mh40584/mac).

## Omarchy MX / Mac / MLX audit

The [point-in-time audit](../local-ai/receipts/realtime-english-2026-10-18/source-audit.json)
fully enumerated 492 MLX, 168 ANE, 243 Omarchy Mac and 28 Mac package branches.
The snapshot is dated October18; branch names are not promises of newer code.

- MLX main `f6d3cca3dd3eb5d0711e1cbf2c5f5053c94be569`, release v0.7.33.
  Its GPU speech worker pins mlx-audio0.5.6 and Parakeet v3, skips unrelated
  model-family initialization, and performs a silence warm call. We reproduced
  that path on this M1 Pro using a scratch package overlay, without replacing
  installed packages. [Pinned worker](https://github.com/joshuaswarren/omarchy-mlx/blob/f6d3cca3dd3eb5d0711e1cbf2c5f5053c94be569/serve/mlx_omarchy_assistant/gpu_stt_worker.py).
- `agent/coreml-tdt-stream` is 1 commit ahead and 1906 behind that main. Its
  Parakeet comparison consumes captured encoder activations, not a ready live
  microphone/cache-aware encoder. `integration/tdt-decoder-stack` is 1 ahead /
  1838 behind. `agent/ParakeetWarm-w6Z` is 3 ahead / 1024 behind and concerns
  asset/startup work. `upstream/parakeet-worker-pcore` is 3 ahead / 48 behind.
  Inspect patches, prerequisites and tests before importing any of them.
- Native resident ANE and performance-core placement already exist in the
  installed upstream worker. Upstream's warm resident CLI improvement is useful
  prior art, not a fresh M1 Pro result. Re-decoding padded encoder prefixes and
  waiting for agreement still delays visible words.
  [Native Parakeet design](https://github.com/joshuaswarren/omarchy-mlx/blob/f6d3cca3dd3eb5d0711e1cbf2c5f5053c94be569/docs/parakeet.md).
- `maralcbr/omarchy-mx-mac` main `e5714f9d2fe27f6e4e54d47849b856c596d1a351`
  still configures Voxtype/base.en, F9/toggle and optional commented Ollama cleanup.
  It is not a replacement for the measured native stream.
  [Pinned config](https://github.com/maralcbr/omarchy-mx-mac/blob/e5714f9d2fe27f6e4e54d47849b856c596d1a351/default/voxtype/config.toml).
- Omacom Mac's current default is `quattro`; the audit pins its SHA separately.
  PRs732/712/711 concern webcam dictation overlays and audio source/filter
  handling. They do not establish an inference speedup. No audio stack changed.

The MLX package's `stream_generate` chunks full input (five-second defaults with
one-second overlap); a streaming name alone does not provide a cache-aware live
PCM API. Our measured rolling-prefix adapter is an experiment, not that API.
Native dispatch was not independently instrumented in these runs: we do not claim
zero CPU tensor operations merely because the selected backend is Vulkan/ANE.

## Compatibility, reproducibility and limits

Nemotron requires the **runtime-specific uppercase `...-Q8_0.gguf` port**, revision
`7df420cc3fb915a3b334560dac712af44fc41ef5`, SHA256
`90d8c89714cd31efc88be62a40c6b2bea57e0cc2063af1ffe2c28f1a228ca110`.
The original NVIDIA lowercase GGUF was rejected by transcribe.cpp0.4.0 with
unsupported architecture/status5; retain it as a format failure with no quality
score. Changing the artifact was a distinct compatibility fix, not a quality
rerun. [Port documentation](https://huggingface.co/handy-computer/nemotron-speech-streaming-en-0.6b-gguf),
[native stream options](https://github.com/handy-computer/transcribe.cpp/blob/main/docs/models/nemotron-speech-streaming-en-0.6b.md).

Other promising true-stream candidates include Moonshine's native runtime (tested
above), Qwen3-ASR and Voxtral Realtime. The latter two were not benchmarked here;
reference CUDA/macOS support or advertised delay does not prove Asahi operation.
[Moonshine](https://github.com/moonshine-ai/moonshine),
[Qwen ASR](https://huggingface.co/Qwen/Qwen3-ASR-0.6B),
[Voxtral Realtime](https://huggingface.co/mistralai/Voxtral-Mini-4B-Realtime-2602).

Every queue waited for idle/cool admission, preserved the six-GiB reserve and
stopped only owned workers at 2700 RPM or 63°C. No guard interrupted these
completed English cases. Other owner jobs were preserved. Fan RPM is a noise
proxy; no dBA, battery or wall-power measurement was made. The quieter guards are
stricter than the general 3500 RPM/80°C policy. No new microphone recording,
audio playback, kernel/boot/display/audio change or owner test window occurred.

Model manifests/digests, source hashes, selected bundle inventory and exact
frozen harnesses accompany the receipts. The ANE installed inventory was read
after trials and is labeled as such; it is not an independent dispatch trace.
MLX weights are CC-BY4.0; no weights/audio are redistributed. LibriSpeech is
CC-BY4.0, Vassil Panayotov, Guoguo Chen, Daniel Povey and Sanjeev Khudanpur,
[OpenSLR12](https://www.openslr.org/12). Derived PCM hashes, clip IDs and public
reference text are included. Signed download URLs, private settings, full logs,
real tasks/journals, credentials and microphone contents are excluded.

Next gates: integrate the selected Nemotron stream into the focus-bound F5
controller; show revisable drafts without typing unstable suffixes into arbitrary
apps; bound native IPC and close/interrupt races; test cancellation, timeout,
resource pressure and app focus changes;
then deploy and obtain an English human F5 acceptance. English-only product scope
is not a guarantee that an unconstrained model can never emit another language.
Broader voice interaction/WebRTC, agents and factory hardware boot remain separate.
