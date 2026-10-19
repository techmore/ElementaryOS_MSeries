# English F5: app integration, native options and voice replies

Read the [qualification index](QUALIFICATION-INDEX.md) before running anything.
It is the continuation record; completed trials and failures must be reused.
[Earlier latency research](REALTIME-ENGLISH.md) remains the benchmark baseline.
This report covers the subsequent controller/app implementation, not factory boot.

**Later v0.0.1 gate:** physical F5 in the owner's ChatGPT app failed before
microphone capture because no focused editable field was exposed. The key was
received. A reviewed per-user launcher enables accessibility and IBus at the next
full owner-controlled app launch; 17 launcher contracts pass. Human acceptance
after that relaunch is pending. See the [candidate instructions](../releases/v0.0.1/README.md)
and [retained failure/staging receipts](../releases/v0.0.1/receipts/). Earlier
toolkit/real-app successes below do not erase this app-specific failure.

## Delivered design

F5 selects English Nemotron streaming on CPU, four threads, trained 160 ms operating
point. This setting is not a 160 ms end-to-end latency claim. English words stream
as the recognizer commits them. The original transcript is never replaced by a
grammar model. The separate Dictation panel offers English grammar after speech,
with optional cleanup previews in its own pane. Foreign-language controls are gone.

The existing F5 hold/toggle preference is preserved. With toggle, press F5 once to
start and again to finish; with hold, release to finish. Escape cancels pending
output. Typing ends dictation to avoid mixing typed and queued speech. The IBus
lease binds output to one active editable field, refuses passwords/unknown fields,
expires after 120 seconds and restores the prior input selection. No clipboard is
needed. Original words remain when a suggestion, model or input route fails.

**Stable-only app input is deliberate.** Native speculative composition initially
passed simple field checks, but Chromium rich compose confirmed a draft during
focus loss—even with IBus CLEAR mode. Those real failures remain published.
Speculative Preview is now suppressed in every app; stable committed words still
arrive during speech. Do not restore unsafe composition to obtain a faster number.

The controller enforces at least six GiB available desktop reserve, stops speech
at 2700 RPM / 63°C, and reclaims idle models under pressure. Loading budgets are 2 GiB
for CPU/ANE and 6 GiB for MLX in addition to the reserve. Native worker IPC has an
absolute deadline, bounded frames, owned process groups and cancellation/close
cleanup. Late native finalization/fallback results cannot enqueue after Escape,
typing or resource interruption. The fallback's own CPU child is monitored and
retired when cancelled. Other owner jobs, audio routing and the kernel stay alone.

## What the app tests prove

All tests used synthetic text/public-file audio and isolated application state.
No microphone, owner window, authenticated Gmail, message send, task-save action,
real journal or clipboard was used. Code/Newelle tests use their actual installed
applications; the toolkit cases cover native GTK3/GTK4/Qt6 and Brave form input.

| Case | Measured committed words from controller launch | Result/scope |
|---|---:|---|
| GTK3 field |2.549s|Exact final normalized English words|
| GTK4 field |2.368s|Exact final normalized English words|
| Qt6 editor |2.112s|Exact final normalized English words|
| Brave form |1.572s|Exact final normalized English words|
| Actual elementary Code editor |1.671s|Exact words; no file-save action requested|
| Actual Newelle composer |1.839s|Exact words; no Send/provider request|
| Actual Tasks entry |1.885s|Exact words in the genuinely focused entry, private headless Gala; no save action requested|
| Brave rich compose + multiline textarea |No ASR in this regression|Exact literal English, cancel/focus/password checks; Gmail-style local form only|

All first words above preceded the 10.435 s audio end. These launch timings include
input preparation and model load; they differ from the 0.851 s feed-clock ASR
benchmark. Original four-toolkit harnesses incorrectly required nonempty native
preedit even though this recognizer committed words early. Their failing receipts
remain unchanged; a separate interpretation records the met early-visible-words
criterion from actual traces without repeating inference or improving WER scores.
The current harness uses the corrected criterion and stable-only input policy.

Newelle's real composer was 26 ancestors below its active window. Its original
refusal is retained; the lookup now permits 64 nodes under the same 0.6 s deadline.
Tasks required genuine focus in a private compositor; inactive/unfocused entry
refusals are preserved rather than weakening the field gate. Calendar's native
binary is absent on this host, so no Calendar-specific input pass is claimed.
Qt/browser coverage does not imply every Electron/custom editor is supported.

## Residency and sustained CPU versus MLX

The optional engine selector changes only its managed speech drop-in and owned
speech service. It preserves hold/toggle mode, other drop-ins and input settings:

```sh
python3 ~/.local/share/mseries/stream/dictation-engine.py --status
python3 ~/.local/share/mseries/stream/dictation-engine.py --select mlx --warm-seconds 600
python3 ~/.local/share/mseries/stream/dictation-engine.py --select ane --warm-seconds 180
python3 ~/.local/share/mseries/stream/dictation-engine.py --select nemotron --warm-seconds 60
```

Residency is configurable from 0–900 seconds and yields to pressure. CPU defaults
to 60 seconds; ANE/MLX default to 180 when selected without an existing residence
setting. Selection remains lazy: it does not open the microphone or run inference.
ANE uses the installed native Parakeet worker; optional `mlx` is the independently
qualified Parakeet/Vulkan pipeline with a separate mlx-audio 0.5.6 overlay. The
owner's MLX Python installation is not replaced.

Nemotron MLX is a distinct, tested candidate: English 8-bit conversion plus scratch
mlx-audio 0.5.9 provides a genuine cache-aware feed/step API. Three resident short
trials had first text 1.105–1.129 s, final tails 3.87–4.10 s and0% final normalized WER.
The prior Parakeet0.5.6 full-input/chunking description does not describe this API.

Two 62.61 s tests per engine concatenate the public clean clip six times. Each model
stays loaded for both trials; the second is genuinely resident. CPU completed at
62.658/62.672s, first words0.854/0.858s, final tails0.048/0.062s, aggregate CPU
76.52/78.98seconds and1.19% normalized WER each. These boundary errors remain.
A post-completion supervisor digest bug lost CPU's sensor summary; the live guard
ran but exact peak sensors are unavailable. Completed CPU tests were not repeated
to repair that missing telemetry. Initial harness import errors occurred before
model inference and are separately unscored.

Sustained MLX completed both resident trials: 88.797/89.430 s for 62.61 s audio,
first words 1.084/1.059 s, final tails 26.187/26.820 s, aggregate CPU 19.15/19.77 s
and 0.595% WER in both. Retention did not resolve its growing backlog. The MLX
queue retained at least 10.79 GiB available and peaked at 2527 RPM / 54.93°C. Its
allocator peak was 947,654,656 bytes, not whole-system memory. CPU remains the
realtime default for this tested pair; lower MLX CPU work can still suit offline work. Lower CPU time is not proof of lower total power; GPU energy was not
measured. Neither tiny/repeated clean corpora nor different model ports establish
a general accuracy or universal CPU/GPU ranking. Fan RPM is a noise proxy, not dBA.

## Optional English Voice Assistant

The separate Voice Assistant offers explicit Ask and an **off-by-default** option
to reply aloud after a completed F5 question. New F5, edits, Escape, Cancel and
window close revoke the old reply. It streams the existing local 4B model into
bounded English sentences and an owned eSpeak process. Raw question/reply text
remain visible. No MCP, app actions, microphone daemon, cloud endpoint or WebRTC
connection is added. This is a half-duplex local voice interface, not an assertion
of natural voice quality or full-duplex conversation.

A synthetic text → 4B→English WAV trial completed: first token 1.733 s, first sentence
2.182s, first WAV 2.200 s. The independently opened WAV contains 1.794 s of nonzero
22.05kHz PCM. Nothing was played. This is not a measured acoustic question-to-reply
latency. The joined test initially completed real ASR and the actual UI gate, but a
private test-bus health check refused the model before inference. That failure
remains. A corrected continuation reused the 37 recorded real ASR events, avoiding
a duplicate ASR run: the actual UI gate started one real model reply and produced
nonzero English WAVs 2.294 s after the replayed audio end, with no duplicate request.
This is explicitly a replay continuation, not fresh microphone/acoustic latency.
It retained 11.22 GiB available at ≤2511 RPM / 49.1°C. Piper/Kokoro natural voices remain separate unqualified work.

## Installation, rollback and evidence

PR #155 merged as `5c26ff6c2ff38c89c401c0d109a61244146868d8` after all six
head-specific CI checks passed. The installer activated that merged payload on
October 18. To reproduce the managed installation with already verified assets:

```sh
python3 mseries/install-dictation-english.py --activate nemotron \
  --model-source /path/to/verified/nemotron-speech-streaming-en-0.6b-Q8_0.gguf \
  --mlx-model-dir /path/to/verified/mlx-parakeet \
  --mlx-modules /path/to/separate/mlx-audio-0.5.6
```

The installer preserves private SHA-checked backups, streams large model copies
and rollback, stops its ASR before replacing runtime files, and reloads only the
owned input bridge/speech service. Managed activation unsets inherited capture-retention
and test/debug environment overrides; a real no-inference systemd child verifies
that precedence. Older drop-ins remain intact for rollback. It never restarts IBus, Wingpanel or another
owner job. `--stage-only` refuses an active ASR. The installed
`dictation-english-manage.py --rollback` restores the prior payload and engine;
`dictation-engine.py --rollback` restores only the latest managed engine change.

[Sanitized receipts](../local-ai/receipts/f5-english-2026-10-18/) include exact public
source snapshots, model/runtime pins, metric traces and retained failures.
Private logs/settings/real content/audio/model weights stay excluded.

The [deployment receipt](../local-ai/receipts/f5-english-2026-10-18/f5-deployment-v1/receipt.json)
verifies all installed runtime/panel/voice/manager bytes against the merged source,
both CPU model pins, the native library, strict live IBus/CPU settings, idle listener
and bridge readiness, enabled services, unchanged input settings/toggle mode and
an unchanged existing 4B process. ANE/MLX assets remain available without loading
another model. No microphone, playback, owner window, menu bar, kernel or audio
routing change was made. Private rollback checkpoints are retained; rolling back
can restore the former debug settings as well as the old engine.

Installed acceptance passed in seven distinct routes: GTK4 actual public-file
ASR (first committed field text 2.608 s from controller launch, exact normalized
English words), plus GTK3/Qt6/Brave no-inference field fixtures and Code/Newelle/Tasks
field-discovery/lease/cancel fixtures. The latter three intentionally do not
commit positive text or run ASR; they prove suppressed preview, stale-token
rejection and input restoration on the installed payload. Positive real-app
insertion evidence remains the separately pinned earlier ASR cohorts above.
A [source compatibility audit](../local-ai/receipts/f5-english-2026-10-18/f5-postdeploy-v1/classification.json)
confirms Tasks' core files match the deployed payload exactly. Code/Newelle's
earlier snapshots differ in speculative-preview suppression and cancellation
hardening; their bridge Commit validation/body and committed-word handler AST
subtrees are unchanged. This is a scoped evidence-reuse argument, not a claim
that those earlier ASR trials ran the later full source.
Every frozen payload matches the installed deployment hashes. Three initial
real-app commands failed argument parsing before launch because the queue omitted
required `--model`; those setup failures remain in `f5-installed-v1`. Only their
unstarted fixture stages continued in `f5-installed-v2`, without ASR or repeating
the four completed toolkit cases. Aggregate half-second supervisor samples kept
at least **10.48 GiB available**, at **≤2530 RPM / 49.01°C**, with no guard
interruption. These are fan/temperature proxies, not acoustic or power readings.
The [post-fixture receipt](../local-ai/receipts/f5-english-2026-10-18/f5-postdeploy-v1/receipt.json)
confirms the same idle listener, unchanged input settings and existing 4B process. A fresh physical-F5/microphone check
in the owner's normal session remains human acceptance, not an automated claim.

The [implementation publication proof](../local-ai/receipts/f5-english-2026-10-18/f5-publication-v1/receipt.json)
records successful CI run `39152857333`, Pages run `39152966394`, and canonical
HTTP 200 / exact reviewed-page byte equality. Final deployment evidence is
published in the subsequent documentation update.
