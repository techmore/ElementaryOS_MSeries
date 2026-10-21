# On-demand maintenance queue

Snapshot: 2026-10-21. All eight MSeries and eight Rupert presets are **PAUSED**.
They are reusable run-on-demand tasks; no unattended run or next task was enabled.
The saved MSeries prompts and local preset identifiers are in
[task-presets.json](task-presets.json). This is a documentation snapshot, not an
importable scheduler configuration. Live local presets remain authoritative.
Rupert's separate queue is listed by metadata only; no Rupert task was run here.

## Run order and audit rules

Run **one task at a time**, audit its actual receipts and conclusions, refine its
prompt from concrete issues, and only then choose the next task. Resume selected
unfinished work before repeating discovery. Read current AGENTS.md, branching
rules, the latest handoff and owned work. Reconcile observed upstream refs,
build pins, installed files and actually loaded code. Reuse existing receipts;
keep unknown acceptance and unmeasured benefit unknown. Maintenance presets do
not inherit the one-off boot/install/merge permissions from this chat.

| # | MSeries task | Current checkpoint |
|---|---|---|
| 01 | Apple Silicon kernel enhancements | Manual pass audited/refined; Aurora 7.2 wip2 refreshed, built twice, booted and all three dock ports confirmed. Actual .20 recovery and suspend remain open. |
| 02 | Power and performance optimization | Earlier manual pass audited/refined. No controlled savings claim. Reconcile newly staged compositor before further measurements. |
| 03 | Package updates and stack rebuild | Queued; no new pass in this continuation. |
| 04 | Useful apps and upstream discovery | Queued; consider modern Omacom/Omarchy apps with license and native integration review. |
| 05 | Housekeeping and ready PR merges | Manual owner-authorized cleanup merged #359, #357 and #364. Audit later ready PRs separately. |
| 06 | Factory image and installer readiness | Queued; factory assembly is not a successful hardware boot. |
| 07 | Native desktop and customization upkeep | Attention fix, display diagnostics and within-scan EDID reuse staged for next login; actual acceptance pending. |
| 08 | Security, provenance and recovery audit | Queued; retain source/license/artifact and recovery boundaries. |

Task 01/02 prompts contain refinements from the actual manual trials. Other
presets retain their initial audit wording; their first real run still needs a
result audit. These parent-chat runs were not executions of the configured
Luna scheduler model. This export changes no prompt, model, schedule or status.

## Start here in the next chat

1. Read the newest entry in `mseries/OS9-HANDOFF.md` and this queue. Refresh Git
   remote/PR state rather than relying on a remembered merge status.
2. Establish running kernel, compositor PID/executable hash, package version and
   whether the next-login candidate has actually loaded. No automatic logout,
   reboot, kernel re-arm, panel restart or stable promotion.
3. Owner chooses the next attended login. Then verify toolkit `present()` raises
   and focuses the intended window, typing behavior, popup routing, internal
   recovery display and dock picture/input. Pointer warping was not added.
4. Repeat matched port moves with the new lifecycle logs. Initial pilot times
   are approximately 4.5 s from partner detection to compositor-active, sampled
   every 0.5 s; they are not cable-to-picture or statistical speed comparisons.
5. Owner-controlled return to persistent default `.20` must still prove actual
   fallback before suspend/power qualification. Continue task 02 only with a
   recorded settled workload; no automatic next maintenance task.

## Durable evidence

- Kernel/source/CI/boot: `mseries/aurora/unified72/BOOT-TRIAL.md` and its JSON receipts.
- All-port results: `mseries/aurora/hardware-tests/2026-10-21-j314s-wip2-first-boot/PORT-TIMINGS.md`.
- Upstream review: `mseries/aurora/unified72/UPSTREAM-CANDIDATES.md`. No new local
  dock driver patch exists; a host-only DART fixture adaptation is a candidate.
  No upstream issue, PR or comment was published.
- Display trace and optimization: `mseries/pantheon-rust-compositor/DISPLAY-LIFECYCLE.md`.
- Exact local deployment and rollback: `mseries/pantheon-rust-compositor/receipts/2026-10-21-activation-displaytrace2-deployment.json`.

Rupert queue: integration/sync; performance/database; dependencies/rebuild;
useful projects/product opportunities; housekeeping/merges; release/backup/recovery;
onboarding/workflow usability; security/tenant isolation/data protection.
Start Rupert after the owner chooses to switch projects.
