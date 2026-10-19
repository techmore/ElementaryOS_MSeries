# English F5 qualification: read this before doing any work

This is the canonical continuation ledger for the **M1 Pro j314s, 32 GB** speech
work. The [machine-readable index](qualification-index.json) records receipt paths,
hashes, source-manifest identities, model/runtime pins, status and quality scope.
Use the existing evidence before proposing another benchmark. A finished failure
is evidence to preserve, not permission to repeat it until it passes.

Snapshot: **October 18, 2026**. All model/app cohorts, joined voice continuation,
merged deployment and seven installed app routes are complete. No owned speech
queue remains active. PR #155 merged as `5c26ff6`; its CI and Pages byte check
passed. This update publishes the final deployment/installed evidence. Inspect
live units/receipts before future work; the snapshot is not a live process monitor.

**v0.0.1 release gate:** the owner subsequently tried physical F5 in the ChatGPT
desktop app and got no words or an unexpected prompt. Generic controller events
show two input refusals before microphone capture; the running app exposed no
focused editable field. This app-input failure is retained in the
[release receipts](../releases/v0.0.1/receipts/). A per-user accessibility/IBus
launcher correction is staged, with 17 passing contracts and verified desktop-entry
resolution. It requires a full owner-controlled app quit/relaunch and a fresh
physical F5 check. A later retry failed with the original process and no new flags still loaded;
activation is unproven. Staging is not a pass. The source-only English STT release
remains a candidate; no model benchmark was repeated and no v0.0.1 was published.

## Current decision and limits

- **Default candidate: Nemotron English Q8 on CPU, four threads, 160 ms trained
  chunk mode.** Its earlier three-run first-display median was 0.851 s on one
  clean public clip. The 160 ms setting is a model operating point, not measured
  end-to-end latency. The model artifact must have uppercase `Q8_0` and the pinned
  `90d8c897…` digest; the earlier NVIDIA GGUF was incompatible with this runtime.
- **Stable words stream into apps. Speculative native preedit is suppressed.**
  Brave committed a tentative composition on blur even with IBus CLEAR mode.
  Browser v3/v4 preserve that actual product failure. Stable-only browser v5
  passed exact multiline rich-compose/textarea, cancellation, focus and password
  checks. Do not restore speculative insertion to obtain a faster number.
- **MLX Nemotron exists and its true cache-aware API was tested.** The pinned
  mlx-audio0.5.9/8-bit conversion gave first text1.105–1.129 s and final tails
  3.87–4.10 s on the short clip, with zero normalized word errors across three
  runs. Sustained MLX also completed:62.61 s audio took88.797/89.430 s, with
  26.187/26.820 s tails and0.5952% normalized WER in both trials. Its process CPU
  time was19.15/19.77 s; it reduced CPU use while falling behind incoming audio.
  Keep the optional Parakeet
  MLX0.5.6 and native ANE engines selectable; they are distinct model/runtime
  combinations, not alternate names for the new Nemotron test.
- CPU sustained stress completed **two 62.61 s trials** at first text0.854/0.858 s,
  tails0.048/0.062 s and **1.19% normalized WER in both**. This repeats a clean
  clip six times; it is not a diverse conversational accuracy set. The supervisor
  failed while saving its sensor summary after CPU completion. Guard code ran,
  but its exact sustained CPU peak sensors are unavailable. **Do not rerun those
  completed CPU trials just to repair missing telemetry.**
- The joined workflow now passes as a **separately identified replay
  continuation**:37 already recorded real ASR events → actual question widget and
  focused-F5-completion gate → existing4B → English WAV. First question text was
  0.911 s after the replayed audio start; first WAV2.294 s after its replayed audio
  end. Original text stayed intact and only one voice request ran. The first
  attempt's completed ASR was reused after fixing an isolated-bus service-check
  harness bug; it was not another ASR quality run or an uninterrupted live test.
- The optional voice reply test was **synthetic text → local LLM → English WAV**:
  first text1.733 s, first WAV2.200 s. No microphone or playback occurred. This is
  not a measured spoken-question-to-audible-answer delay; eSpeak is robotic.

All trials used a six-GiB reserve and quiet admission/stop guard policy; the
completed sustained CPU cohort’s exact sensor peaks are unavailable as recorded above.
Fan RPM is a noise proxy, not a dBA measurement. File tests do not establish a
new live microphone/physical-F5 acceptance, factory boot, battery or power result.

## Reuse these cohorts

Private work paths below are relative to the existing task's `work/` directory.
Sanitized copies are exported under
[f5-english-2026-10-18](../local-ai/receipts/f5-english-2026-10-18/); that folder is
checked separately against public byte digests. The initial implementation Pages
publication has verified CI/run/byte proof; final documentation publication is
verified after its merge and recorded in that PR’s body and task output. Never publish private logs,
profiles, real app contents, credentials, settings clones or microphone audio.

| Cohort | State and evidence to reuse |
|---|---|
| `realtime-speech-v1`, `realtime-nemotron-v2` | Completed baseline quality/latency, including Moonshine errors and CPU Nemotron160/560. Already published; no comparable repeat. |
| `english-realtime-v1`, `mlx-realtime-v1` | Completed native ANE, extra public speakers, English panel and Parakeet GPU results. ANE committed timing and GPU rolling drafts use different policies. |
| `unsupported-original-gguf` | Preserved unsupported-format failure; no accuracy score. |
| `f5-nemotron-mlx-v1` | Completed three real cache-aware MLX Nemotron short-file trials; preserve all warm/cold and tail timings. |
| `f5-optional-engines-v1` | Native ANE and optional Parakeet MLX actual controller/file checks passed with bounded worker IPC. Source manifests identify these older controller snapshots. |
| `f5-app-fixtures-v1` → `v3` | No-inference toolkit fixtures. Initial Brave assertion confused visible composition with permanent insertion; later fixture corrected that assumption. Retain all versions. |
| `f5-app-qualified-v1` | GTK3, GTK4, Qt6 and Brave real ASR reached exact normalized final words and early committed text. Original receipts fail an unnecessary provisional-event assertion. Keep their failure flags; use explicit post-hoc committed-text analysis, not rewritten passes. |
| `f5-real-app-fixtures-v1` → `v12` | No-ASR real-app setup, accessibility and focus diagnostics. Code first passed v2; Newelle v8; Tasks v12. Earlier launch/API/WM/focus failures remain. Some integration failures need their traces for precise harness-versus-product attribution; they are not model WER failures. |
| `f5-real-app-qualified-v1/code` | **Actual elementary Code ASR passed**, exact normalized words; first committed text1.671 s on the public clip. No rerun. |
| `f5-real-app-qualified-v1/newelle` | **Actual Newelle composer ASR passed**, exact normalized words; first committed text1.839 s. No model message was sent. No rerun. |
| `f5-real-tasks-qualified-v1` | **Actual Tasks ASR passed**, exact normalized words; first committed text1.885 s. Synthetic task was not saved. No rerun. |
| `f5-browser-editors-v1`, `v2` | Preserved harness failures: Chromium's sole `<br>` placeholder has `innerText='\n'`, even when empty. |
| `f5-browser-editors-v3`, `v4` | **Preserved product failures:** blur committed tentative rich-compose words; CLEAR mode alone did not solve it. |
| `f5-browser-editors-v5` | Stable-only policy passed real Brave local Gmail-style rich compose and multiline textarea. Native preview explicitly absent, literal text exact, stale/focus/password refused. No authenticated Gmail or mail-send claim. |
| `f5-sustained-v1` | Pre-inference Python import-scoping failures, unscored. |
| `f5-sustained-v2` | CPU and MLX two trials each complete. CPU sensor-summary save failure remains separate. MLX max2527RPM/54.927°C, minimum available11,585,667,072bytes; do not transfer those sensors to CPU. No rerun. |
| `f5-voice-v1` | Synthetic text-to-English-WAV passed and WAV verified; no microphone/playback, no tool or desktop action. |
| `f5-joined-voice-v1` | Completed real ASR trace preserved; voice stage stopped before inference because the private bus could not check the owner service. Keep the harness failure. |
| `f5-joined-voice-v2` | Actual voice UI completion gate/LLM/WAV passed by replaying v1's37 ASR events. No fresh ASR or microphone/playback. No duplicate request; original preserved. |
| `f5-payload-fixtures-v1` | No-inference app checks using the frozen installer payload; distinct from installed owner-session acceptance. |
| `f5-debug-env-v1` | Real no-inference systemd child proves inherited capture-retention/dry/file-test/forced-fallback variables are absent; no old settings file edited. |
| `f5-deployment-v1` | Read-only pass: installed source/model/native-library hashes, strict live settings, enabled listener/bridge readiness, toggle/input preservation, unchanged 4B and static ANE/MLX assets. |
| `f5-installed-v1` | Installed GTK4 actual public-file ASR plus GTK3/Qt6/Brave fixtures passed. Code/Newelle/Tasks commands failed argparse before launch because a required model argument was absent; retain those setup failures, no quality score. |
| `f5-installed-v2` | Only the three unstarted installed real-app fixtures, with corrected argv and no inference. Inspect these results rather than rerunning v1. |
| `f5-publication-v1` | PR #155 checked head, merge, successful Pages deployment and exact canonical byte equality. Separate from microphone acceptance. |

The earlier publication is [PR162](https://github.com/techmore/ElementaryOS_MSeries/pull/162),
merge`87f4a7b88c947d6c0d8e59cf3dd54aaf636ff3d2`; its CI and Pages verification
are recorded in [publication-v1.json](../local-ai/receipts/realtime-english-2026-10-18/publication-v1.json).
That publication does **not** establish deployment of the newer F5 implementation.
The earlier foreign-language experiments predate the owner's English-only
correction; they are historical evidence, excluded from the product and never
to be resumed for this task.

## Equality, resumption and scoring

An equivalent trial requires the same **machine, kernel, model byte digest and
context, native library/backend binary and package revisions, frozen harness and
production source manifest, guard policy, audio/reference/workload, resident
cold/warm state, app/runtime, checkpoint stage and metric definition**. Keep the
outcome separate: changing a failed result's label must never make it eligible
for another comparable trial. Missing pins mean an identical-state comparison
has not been established, not that unknown values match. Documentation-only
changes, another checkout or missing telemetry do not justify repeating a
finished benchmark. A materially changed model/backend needs a scoped new
question and identity, with the previous result retained as its baseline.

`complete:false` alone is insufficient to decide whether to resume. A terminated
assertion or unsupported-runtime result is terminal evidence; an interrupted
model trial is unscored; a partial live checkpoint is still owned work. Inspect
its paired supervisor attempt, unit and log. Preserve completed successes,
quality errors and integration failures. A concrete source/harness fix gets a
new identity and a written reason; it does not erase the old receipt.

Do not compare first display, first committed insertion and final tail as one
latency. Keep load/compilation, first decode after load and resident reuse
separate. A short clean-file WER is not general accent/noise/coding accuracy.

## Exact continuation procedure

Run from the repository root. These are inspection commands first; none starts
another worker. `$WORK` is the existing task's work directory, the parent of this
checkout. If using a different checkout, set it to the existing work location.

```bash
WORK=$(dirname "$(git rev-parse --show-toplevel)")
systemctl --user show mseries-f5-sustained-qualification-resume.service mseries-f5-tasks-qualification.service -p Id -p ActiveState -p MainPID -p ExecMainStatus
journalctl --user -u mseries-f5-sustained-qualification-resume.service -u mseries-f5-tasks-qualification.service -n 30 --no-pager
lslocks --output PID,COMMAND,PATH
cat "$WORK/f5-sustained-v2/cpu.json"
cat "$WORK/f5-sustained-v2/cpu-supervisor-receipt-failure.json"
cat "$WORK/f5-sustained-v2/mlx.json"
find "$WORK/f5-real-tasks-qualified-v1" -maxdepth 2 -name '*receipt.json' -o -name '*attempt.json'
```

The shared serial lock is **`$WORK/realtime-speech-v1/queue.lock`**. An active unit
may be waiting on that lock or on cooling; neither state justifies launching a
second queue. The now-completed owned units were
`mseries-f5-sustained-qualification-resume.service` and
`mseries-f5-tasks-qualification.service`.

**All listed model/app cohorts are terminal. Do not restart their units or
drivers.** The unit names above are for read-only inspection. Old drivers can
prepare source trees before checking existing attempts; accidentally restarting
one can damage frozen evidence even if inference is skipped. New work must
identify a distinct acceptance gap and cohort identity, reusing completed evidence.
Resume a future interrupted queue only from its recorded incomplete checkpoint,
without deleting attempts, resetting scores or rewriting frozen sources.
Permanent upstream tracking is already the repository's six-hour watcher; do not
create another watcher or completion heartbeat.

The repository maintenance helper refreshes receipt metadata without inference or
service changes, and preserves curated failure classifications:

```bash
python3 mseries/dictation/refresh-qualification-index.py --work-dir "$WORK" --require-public
```

Run it after the sanitized exporter/checksum refresh and after installed checks.
`original_receipt_sha256` identifies original private JSON bytes;
`public_receipt_sha256` identifies separately sanitized published JSON bytes.
They can differ legitimately. The helper verifies public bytes against
`checksums.json`; a missing or stale copy is not a publication pass. It reads only
explicitly allowlisted receipt paths and writes this JSON index; it never launches
an app, model or service. New cohorts still need a curated scope/classification.

## Completion record and separate future work

PR #155 passed all six checked-head CI jobs in run `39152857333`, merged as
`5c26ff6c2ff38c89c401c0d109a61244146868d8`, and published through successful
Pages run `39152966394`. Canonical HTTP 200 bytes matched the reviewed page
SHA256 `dc5434eec3c707f70942f2468b941287af673328a9527b6775fbfee50dfa9b9a`.
See `f5-publication-v1/receipt.json`; this proof identifies that earlier page,
not a retroactive byte claim about the subsequent deployment report update.

The reviewed English installer activated the merged source. Static/live checks
passed: exact runtime/model/library bytes, strict CPU/IBus environment with
capture-retention/test overrides absent, enabled ready listener/bridge, preserved
toggle/input settings, unchanged everyday 4B, retained ANE/MLX assets and private
rollback. Seven installed app routes passed: one GTK4 public-file ASR smoke and
six no-inference app fixtures. Code/Newelle/Tasks installed fixtures cover
field discovery, lease/cancel and restoration, not another positive text-commit
or ASR run; earlier real-app ASR receipts remain their positive evidence.
The post-deployment `classification.json` pins an independent source/AST audit:
Tasks' core files exactly match deployment; Code/Newelle retain identical Commit
validation/body and committed-word handler subtrees despite preview/cancel fixes.
Their earlier ASR is not relabeled as a later-source trial.
The original three argument-parsing failures
remain; only their unstarted fixtures continued. Supervisor samples retained
10.48 GiB available at ≤2530 RPM / 49.01°C with no guard interruption. Post-fixture
readiness/preservation passed. No completed model benchmark was repeated.

The earlier scoped deployment is complete; the later v0.0.1 physical ChatGPT
acceptance gate above remains open. Authenticated Gmail, native Calendar GUI,
natural voice/full-duplex WebRTC, indefinite soak, battery/power and factory boot
remain distinct future work. They do not justify rerunning the completed cohorts.
A future backend/model change needs a new scoped question and explicit identity.
Final documentation CI/Pages verification is recorded after its actual success in
the publication PR body and task output; never infer it from a successful HTTP
request alone. This ledger is the starting point for all continuation work.
