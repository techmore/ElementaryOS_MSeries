# Maintenance checkpoint — October 21, 2026

Owner returned and requested continuation. **Next priority: identify and apply the intended kernel
change in the isolated source/build lane.** The owner called it a “kernel thing”
but did not identify the exact PR or version. Do not silently choose a candidate
or treat this checkpoint as a hardware deployment/boot-selection instruction.

## Resume review — October 21

[Immutable source hashes and review receipt](kernel-resume-review.json) now
record focused inspection of merged #139 at `644133b7799f`. The three shared
GPU/SEP gaps from our old 7.2 snapshot are addressed in these inspected paths:
render/compute call `read_supported`; SEP's OF table is not exported for autoload;
and capture-drain timeout continues suspend. The original merged GPU-reader
source passes **five host tests**, with a Result/EINVAL-only shim. This differs
from the older seven-test file; no equivalent whole-suite coverage is inferred.
Stock-bindgen layout policy is also already present, so do not reapply our old
local layout patch blindly when refreshing the source pin.

This is focused source evidence, not completion of all 64 review items or an
ARM64 kernel build. Upstream reports M1-family Touch ID reliability regressions
and a shared-DTB/5-cell-DART fallback compatibility requirement. Only about
4.9 GB was free locally; use the existing artifact-only ARM64 CI for full builds.
The exact intended kernel change was requested from the owner and remains
unresolved. No source/adoption pin, boot payload or live kernel was changed.

## Completed today

- Created and prompt-audited eight ElementaryOS maintenance tasks: kernel,
  power/performance, packages/rebuilds, app discovery, housekeeping/ready merges,
  factory/installer readiness, native desktop/customizations, security/provenance.
  All are paused for manual runs. [Saved prompts](tasks.json) retain the refined
  kernel and power instructions. The separately prepared Rupert suite follows
  the ElementaryOS work; its tasks have not run.
- Manually trialed tasks **01 then 02**, audited their evidence and refined each
  saved prompt. These were parent-chat trials, **not scheduler runs**; configured
  GPT-6 Luna/xhigh execution has not been evaluated. Task 03 has not started.
- No implementation, live kernel/boot/display/audio/service changes, suspend,
  reboot, application shutdown or optimization was applied by these trials.

The audit checkout was `7550f6590bc241a42da8ff3feff5ee909f503c7c`.
This checkpoint is prepared against newer `origin/dev`; observations below are
October 21 snapshots, not assertions that every later checkout/live state agrees.

## Kernel findings and next application decision

Observed running kernel: `7.1.12-elementary-aurora20-enh1`. Published `.20`
source is `c46d7dcdb8712ea9aeb0ce47b439ffae76371e55`; our enhancement overlay
and config are distinct. Do not compare a proposed patch only to release.json
and assume it describes the whole running kernel.

The existing `aurora/audit-upstream.py` completed using the October 18 energy
receipt: **59 branches, 23 open PRs, 10 immutable energy-file comparisons**.
Seven branches were new and integration changed against the prior 52-branch
receipt. [Full snapshot](kernel-upstream-snapshot.json) retains source heads and
coverage limits. Its ten file comparisons use the old local unified72 pin, not
new integration. No complete Linux-code audit is implied.

| Candidate | October 21 finding | Next disposition |
| --- | --- | --- |
| [Aurora #139](https://github.com/omacom/linux-aurora/pull/139) | Merged; final head `644133b7799f759c5bfd88507b6246d298b6509c`. Our local 7.2 manifest pins older `582e9ef3…`. | First source-review candidate: reconcile reviewed fixes, GPU UAPI/Mesa, SEP, config and boot/recovery before refreshing a build-only lane. No automatic promotion. |
| [#154](https://github.com/omacom/linux-aurora/pull/154) | `54a14dabb01600453995e0877bb630fa622ede4c`; concurrent DP-tunnel bandwidth sharing. Contributor evidence is J314C/M1 Max with tiled 5K. Default can limit a single monitor on a multi-output dock to HBR2. | Check actual WD22TB4 topology and desired modes before selecting. Not J314S qualification. |
| [#163](https://github.com/omacom/linux-aurora/pull/163) | `b8930ad8c5d319d74f9c284c764b7df29d879881`; newer-tree dock USB fix changes display-taken to ENOSPC. Our immutable .20 DCP producer returns EBUSY for non-H17P exhaustion and tipd deliberately expects it. | **Do not directly backport.** Reconcile producer and consumer semantics together. Contributor J413/M2 result is not a demonstrated J314S fix. |
| [#158](https://github.com/omacom/linux-aurora/pull/158) | Open 7.2.11 rebase at `bd526b3c11ccf8e91d6240261beb3219d8f17f03`. | Watch/review after resolving the older local candidate's parity gates; no local hardware acceptance. |
| [#170](https://github.com/omacom/linux-aurora/pull/170) | Draft J314S context-loss diagnostic, not a deep-sleep fix; contributor reports include physical-recovery requirements. | Exclude from routine maintenance trials. No energy improvement or safe context return established. |

Observed Omacom integration head was
`89f1e2bf2e4fac3889ab658fe1a6eb460c122fce`; Aurora Silicon's integration tip
was separately `899b412feda7f3155fae7e8e8fe7fbf82dd27ceb`. Do not conflate them.
Asahi and confirmed contributor refs were inventoried; only selected dock patches
were read deeply. Current-source redistribution/SPDX checks, source preparation,
builds and actual hardware qualification remain future work for any import.

**Resume order:** confirm which kernel candidate the owner means; refresh its
immutable head and applicable local baseline; perform semantic/dependency review;
prepare at most one pinned source/config change; build/check separately; retain
rollback and remaining hardware gates. Do not restart from old Fairydust reverse
engineering or launch task 03 as a substitute for this priority.

## Power findings and measurement limitations

Two 30-second **uncontrolled** SMC Total System Power windows measured:

| Window | Median W | p10 / p90 W | Evidence |
| --- | --- | --- | --- |
| In-use snapshot | 17.303 | 16.817 / 18.530 | [Context and summary](power-observation.json); first window raw watts were not retained. |
| Raw arithmetic check | 41.203 | 18.111 / 43.246 | [Raw readings and independent statistics](power-statistics-check.json); second window lacks complete workload controls. |

Neither establishes an idle floor, optimization, regression, battery-runtime
estimate or macOS parity. The variability rules out cherry-picking these as A/B.
One-core process percentages are not per-app watts. The first window showed
Rust compositor and active Electron apps; this is a profiling hypothesis only.

- Internal output was 3024×1964@120 Hz, scale 1.25, plus two 1080p60 DP outputs.
  Physical dock socket identity and sustained hardware VRR were not qualified.
- Raw backlight read 503 against max 500: retain the anomaly, not a calibrated
  brightness/luminance claim. Charger-online=1 coexisted with battery Discharging;
  SMC system power and signed net battery flow must remain distinct.
- A later ALSA snapshot had playback closed and safety capture RUNNING, so the
  historical always-running playback claim must not be repeated as current.
- `power/display_status.py` loses valid modes/layout when the Rust compositor
  lacks optional `PowerSaveMode`. `aurora/trial/capture-session.py` gates on its
  `available` field. **Next tooling fix:** separate capability/completeness and
  preserve DPMS unknown; review consumers/tests before weakening any gate.
- Later video-decode receipts supersede old blanket no-decode/H.264-only notes.
  Do not disable browser sandboxing to claim a power win. Prior refusal to close
  ChatGPT remains in effect; no app/service was closed or paused.

## Task refinements retained

The kernel task now distinguishes published, local-overlay and running baselines,
requires current PR state, pagination/coverage and producer/consumer review.
The power task requires raw samples and independently checked statistics, explicit
conditions/observer cost, partial display capabilities and historical-evidence
reconciliation. Neither may silently advance build pins or invent hardware or
power acceptance. Research-only findings can be retained without noisy report PRs.

Validation of this checkpoint: documentation/JSON review and `git diff --check`.
No code or hardware test result is created by publishing these notes. Original
raw/source-rich trial artifacts remain in the originating local chat outputs;
this directory preserves portable, reviewed summaries and selected receipts.
