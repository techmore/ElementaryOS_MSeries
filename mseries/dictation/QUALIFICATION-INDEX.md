# English F5 qualification: read this before doing any work

This is the canonical continuation ledger for the **M1 Pro j314s, 32 GB** speech
work. The [machine-readable index](qualification-index.json) records receipt paths,
hashes, source-manifest identities, model/runtime pins, status and quality scope.
Use the existing evidence before proposing another benchmark. A finished failure
is evidence to preserve, not permission to repeat it until it passes.

Snapshot refreshed: **2026-10-18, 14:03 EDT / 18:03 UTC**. Tasks ASR, both sustained
engine cohorts and the joined voice continuation are complete. Do not repeat
them. Remaining work is final merge/publication, deployment and installed-path
checks. A later reader must inspect the live units and receipts instead of
treating an older snapshot as current process status.

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

All trials preserve a six-GiB desktop reserve and quiet admission/stop guards.
Fan RPM is a noise proxy, not a dBA measurement. File tests do not establish a
new live microphone/physical-F5 acceptance, factory boot, battery or power result.

## Reuse these cohorts

Private work paths below are relative to the existing task's `work/` directory.
Sanitized copies are exported under
[f5-english-2026-10-18](../local-ai/receipts/f5-english-2026-10-18/); that folder is
checked separately against public byte digests. Final commit/Pages publication
is still a coordinator gate at this snapshot. Never publish private logs,
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
has not been established, not that unknown values match.

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

**All listed model/app cohorts are now terminal; these are recovery entry points,
not the next task. Do not run them for completed work.** Only after both
inspection and identity checks show a queue is no longer alive,
with genuinely incomplete work and no equivalent terminal attempt, its exact
guarded driver entry points are:

```bash
systemd-run --user --collect --unit=mseries-f5-sustained-qualification-resume /usr/bin/python3 "$WORK/run-sustained-f5-resume.py"
systemd-run --user --collect --unit=mseries-f5-tasks-qualification /usr/bin/python3 "$WORK/run-f5-tasks.py"
```

**Do not run these while their units exist and are active.** The drivers preserve
completed CPU work and existing attempts. An interrupted receipt/attempt may
need an explicit incomplete-only resume change by the coordinator; never delete
the file, bypass its existence check, overwrite a frozen source, reset a score
or launch the raw benchmark to force a retry. Compare the existing source hashes
before re-entry, because the current scratch drivers prepare their source tree.
Permanent upstream tracking is already the repository's six-hour watcher; do not
create another watcher or completion heartbeat.

The private maintenance helper refreshes receipt metadata without inference or
service changes, and preserves curated failure classifications:

```bash
python3 "$WORK/refresh-f5-index.py" --repo "$(git rev-parse --show-toplevel)" --require-public
```

Run it after the sanitized exporter/checksum refresh and after installed checks.
`original_receipt_sha256` identifies original private JSON bytes;
`public_receipt_sha256` identifies separately sanitized published JSON bytes.
They can differ legitimately. The helper verifies public bytes against
`checksums.json`; a missing or stale copy is not a publication pass. It reads only
explicitly allowlisted receipt paths and writes this JSON index; it never launches
an app, model or service. New cohorts still need a curated scope/classification.

## Remaining merge/deployment gates at this snapshot

1. Model/app and joined replay results are complete. Preserve them and the
   original failures; no model-quality benchmark is pending. The next tests are
   installed-path checks after deployment, not repeated model qualification.
2. Final contract/review checks must cover the current stable-only app policy,
   lifecycle/late-enqueue cancellation, six-GiB guards and installer rollback.
   Current Code/Newelle results identify their exact earlier source snapshots;
   no universal app or live microphone claim follows from them.
3. Sanitize receipts and reconcile this index, the report and public page. Merge
   only the checked final head, preserving other main changes; verify the actual
   Pages deployment and canonical bytes before saying it is published.
4. Wait for all owned inference workers to finish before installing/activating
   English F5. Use the reviewed private-backup installer, preserve the owner's
   toggle/hold choice and other drop-ins, reload only owned speech/input units,
   verify healthy readiness, and retain rollback. No owner audio/kernel/display
   or unrelated job changes. Native ANE/MLX remain explicit options.

The coordinator updates the pending outcomes and deployment receipt here once
those gates finish. Future work starts from this ledger, not from a new baseline.
