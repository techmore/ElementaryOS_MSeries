# English F5: app integration, native options and voice replies

Read the [qualification index](QUALIFICATION-INDEX.md) before running anything.
It is the continuation record; completed trials and failures must be reused.
[Earlier latency research](REALTIME-ENGLISH.md) remains the benchmark baseline.
This report covers the subsequent controller/app implementation, not factory boot.

## Delivered design

F5 selects English Nemotron streaming on CPU, four threads, trained160ms operating
point. This setting is not a160ms end-to-end latency claim. English words stream
as the recognizer commits them. The original transcript is never replaced by a
grammar model. The separate Dictation panel offers English grammar after speech,
with optional cleanup previews in its own pane. Foreign-language controls are gone.

The existing F5 hold/toggle preference is preserved. With toggle, press F5 once to
start and again to finish; with hold, release to finish. Escape cancels pending
output. Typing ends dictation to avoid mixing typed and queued speech. The IBus
lease binds output to one active editable field, refuses passwords/unknown fields,
expires after120seconds and restores the prior input selection. No clipboard is
needed. Original words remain when a suggestion, model or input route fails.

**Stable-only app input is deliberate.** Native speculative composition initially
passed simple field checks, but Chromium rich compose confirmed a draft during
focus loss—even with IBus CLEAR mode. Those real failures remain published.
Speculative Preview is now suppressed in every app; stable committed words still
arrive during speech. Do not restore unsafe composition to obtain a faster number.

The controller enforces at least six GiB available desktop reserve, stops speech
at2700RPM/63°C, and reclaims idle models under pressure. Loading budgets are2GiB
for CPU/ANE and6GiB for MLX in addition to the reserve. Native worker IPC has an
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

All first words above preceded the10.435s audio end. These launch timings include
input preparation and model load; they differ from the0.851s feed-clock ASR
benchmark. Original four-toolkit harnesses incorrectly required nonempty native
preedit even though this recognizer committed words early. Their failing receipts
remain unchanged; a separate interpretation records the met early-visible-words
criterion from actual traces without repeating inference or improving WER scores.
The current harness uses the corrected criterion and stable-only input policy.

Newelle's real composer was26 ancestors below its active window. Its original
refusal is retained; the lookup now permits64nodes under the same0.6s deadline.
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

Residency is configurable from0–900seconds and yields to pressure. CPU defaults
to60seconds; ANE/MLX default to180 when selected without an existing residence
setting. Selection remains lazy: it does not open the microphone or run inference.
ANE uses the installed native Parakeet worker; optional `mlx` is the independently
qualified Parakeet/Vulkan pipeline with a separate mlx-audio0.5.6 overlay. The
owner's MLX Python installation is not replaced.

Nemotron MLX is a distinct, tested candidate: English8bit conversion plus scratch
mlx-audio0.5.9 provides a genuine cache-aware feed/step API. Three resident short
trials had first text1.105–1.129s, final tails3.87–4.10s and0% final normalized WER.
The prior Parakeet0.5.6 full-input/chunking description does not describe this API.

Two62.61s tests per engine concatenate the public clean clip six times. Each model
stays loaded for both trials; the second is genuinely resident. CPU completed at
62.658/62.672s, first words0.854/0.858s, final tails0.048/0.062s, aggregate CPU
76.52/78.98seconds and1.19% normalized WER each. These boundary errors remain.
A post-completion supervisor digest bug lost CPU's sensor summary; the live guard
ran but exact peak sensors are unavailable. Completed CPU tests were not repeated
to repair that missing telemetry. Initial harness import errors occurred before
model inference and are separately unscored.

Sustained MLX completed both resident trials:88.797/89.430s for62.61s audio,
first words1.084/1.059s, final tails26.187/26.820s, aggregate CPU19.15/19.77s
and0.595% WER in both. Retention did not resolve its growing backlog. The MLX
queue retained at least10.79GiB available and peaked at2527RPM/54.93°C. Its
allocator peak was947,654,656bytes, not whole-system memory. CPU remains the
realtime default for this tested pair; lower MLX CPU work can still suit offline work. Lower CPU time is not proof of lower total power; GPU energy was not
measured. Neither tiny/repeated clean corpora nor different model ports establish
a general accuracy or universal CPU/GPU ranking. Fan RPM is a noise proxy, not dBA.

## Optional English Voice Assistant

The separate Voice Assistant offers explicit Ask and an **off-by-default** option
to reply aloud after a completed F5 question. New F5, edits, Escape, Cancel and
window close revoke the old reply. It streams the existing local4B model into
bounded English sentences and an owned eSpeak process. Raw question/reply text
remain visible. No MCP, app actions, microphone daemon, cloud endpoint or WebRTC
connection is added. This is a half-duplex local voice interface, not an assertion
of natural voice quality or full-duplex conversation.

A synthetic text→4B→English WAV trial completed: first token1.733s, first sentence
2.182s, first WAV2.200s. The independently opened WAV contains1.794s of nonzero
22.05kHz PCM. Nothing was played. This is not a measured acoustic question-to-reply
latency. The joined test initially completed real ASR and the actual UI gate, but a
private test-bus health check refused the model before inference. That failure
remains. A corrected continuation reused the37 recorded real ASR events, avoiding
a duplicate ASR run: the actual UI gate started one real model reply and produced
nonzero English WAVs2.294s after the replayed audio end, with no duplicate request.
This is explicitly a replay continuation, not fresh microphone/acoustic latency.
It retained11.22GiB available at≤2511RPM/49.1°C. Piper/Kokoro natural voices remain separate unqualified work.

## Installation, rollback and evidence

After source/app checks pass and the reviewed PR merges, deployment uses:

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
Private logs/settings/real content/audio/model weights stay excluded. Publication
and installed checks will be recorded after their actual completion; source tests
alone do not establish a successful deployment or fresh human F5 microphone pass.
