# Experimental quiet troubleshooting and optimization agent

Status: source draft, disabled, uninstalled and unqualified. It is excluded from
English F5 STT-only v0.0.1. No dedicated 9B inference has run. The installed legacy
collector has not been replaced, and no new profile/unit or accepted qualification
file has been provisioned.

The implementation adds a private bounded kernel/application alert inbox and an
explicit analysis client. SQLite preserves source cursors and event identities,
groups repeated alerts without double-counting restart replay, records collection
gaps and uses versioned acknowledgement. Acknowledgement records attention, not
repair. Retention is capped at 256 alerts, 2,048 events, 64 gaps and eight sources. The new
collector never starts a model or displays a notification, even when the old
automatic-diagnosis marker exists.

An explicitly opened GTK inbox can request evidence-bound analysis of one alert,
a chosen bounded text file, or a performance snapshot. English output separates
observations, hypotheses, unknowns and fixed read-only check identifiers. There
are no shell/repair tools or automatic changes. Supplied log text is untrusted.
JSON structure and lexical guards cannot prove a diagnosis correct; independent
semantic review is required before qualification.

The intended dedicated candidate is the already cached Apache-2.0
`mlx-community/Qwen3.5-9B-MLX-4bit` at
`938d8919941c6e7efd3c7150eff7fe9d12afa631`, initially 4K context. Its older 12/15
short-task score is not diagnosis evidence. Everyday 4B's two unsupported repair
failures remain excluded. The existing MLX v0.7.33 commit
`33630f9c1eeefe5fc985a28bed0585432c2c014e`, mlx-lm 0.31.3 and libmlx SHA256
`1187d5715b66edd47518ba59950813bb78a7bd3383327ced369699bc9521c176` are retained.
Private compute Mesa remains at `7faf04c065c5376d2d58a1e5b33a60118109c99e`.
No kernel, driver or runtime update was installed for this phase.

The isolated endpoint is 127.0.0.1:8772. A dedicated supervised request requires
at least 9 GiB model admission plus the six-GiB desktop reserve, fans below 2,600 RPM
and temperature below 58 C. Its owned worker stops on the first sample at 2,700 RPM
or 63 C and yields to F5. Other selected profiles are preserved. Only explicit
exclusive admission may temporarily release an enabled idle everyday 4B; process
ownership, existing connections and F5 are checked repeatedly. Observed idle
cannot prevent a new client after the final check; that race remains a limitation.
Model/service lifecycle behavior is not yet qualified with real inference.

A sixteen-case harness separates 12 core and four held-out cases, freezes sources,
model/runtime/kernel/policy/workload identity, checkpoints incomplete work and
retains completed successes and failures. Historical/recovered faults, hostile
logs, missing telemetry, memory pressure, matched measurements and warmup/load
confounds are included. Automatic rubric success never grants qualification.

The retained current-source synthetic alert subprocess test passed 11/11:
200 repeated faults replayed twice without duplicate counts, restart cursor,
other-user filtering, versioned acknowledgement and recurrence reopening. Its
two samples over 0.322 seconds retained 12,646,318,080 bytes at ≤2,506 RPM / 43.239 C.
No real journal, model, owner window or notification was involved. This does not
establish live collector overhead, long-run stability, acoustic noise or power.

The first aggregate failed 134 tests / one failure due to frozen-import isolation.
The next aggregate failed 136 tests / one newly added orphan-source fixture error.
Both private logs are retained. After the concrete corrections, 136 contracts
passed in 3.413 s. That result predates the subsequent independent review fixes;
current verification is recorded in the adjacent source manifest/contract receipt.
Unclosed worker-lock/SQLite ResourceWarnings remain documented. Raw logs,
real journals, user settings and diagnostic jobs are not published.

Independent review required stronger acceptance identity for prompt/contract,
model bytes and frozen source/fixture integrity, plus attribution/recovery of
interrupted systemd starts/stops. These fixes must be covered by synthetic
contracts before any installer or real model run. No ambiguous owner process
may be stopped to make cleanup appear successful.

Next: complete reversible diagnostic-only installer/unit/profile staging and
rollback; qualify quiet real 9B startup, independent core/held-out semantics,
abstention, F5 interruption/cancel/pressure cleanup and conditional 4B restoration;
then validate permitted collector metadata, GTK interaction and bounded idle/soak
cost. Never induce kernel faults or run an autonomous heavy-model repair loop.
The existing six-hour repository watcher continues candidate discovery. Popular
models, developer branches and upstream performance patches need separately
identified evidence on this M1 Pro before replacing a pin.

Final independent review retained an unsolved fixed-unit startup attribution
race: an owner can start the same unit between the inactive check and our start
request. Start success and a new InvocationID do not prove ownership. Therefore
`OWNED_START_READY=False` is the first normal session action and blocks all
service mutations, even if someone creates an accepted model receipt. A uniquely
attributable per-session worker is required before enabling this runtime.
Lifecycle tests mock that hard gate to test mechanics; they do not qualify a
production launch. Direct generation remains a research API for an externally
owned, admitted server, not a production enablement path.

After these concrete source fixes, the final cross-suite check passed **152 tests
in 3.423 seconds**. Four worker-lock warnings remained. This run emitted no SQLite
warning; the earlier six remain recorded and are not claimed fixed. The retained
[synthetic contract receipt](receipts/diagnostic-foundation-2026-10-18/synthetic-contracts-v4.json)
and [source manifest](receipts/diagnostic-foundation-2026-10-18/source-manifest.json)
identify this final draft. No real model, service or journal work ran.
