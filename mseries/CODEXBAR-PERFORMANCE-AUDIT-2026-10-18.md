# CodexBar performance, modularity and Wingpanel watch — 2026-10-18

Scope: our custom Wingpanel indicator, local session/history readers, shared cache,
helper invocation, installation payloads and the live panel/launcher. This is not an
exhaustive audit of the unrelated kernel, image, Orchard, dictation or provider apps.
Upstream CodexBar remains v0.77.0; its IPC schema is unchanged.

## Implemented findings

| Finding | Change | Evidence |
| --- | --- | --- |
| Both OpenCode readers decoded lifetime history for a 30-day UI; one also retained all SQL rows with `fetchall` | Shared `codexbar_history.py`: read-only URI, inclusive timestamp bounds before JSON decoding, streamed aggregation without a per-message list, common windows/token accounting | Old/future records excluded, boundary records counted, reserved URI characters work, DB bytes unchanged, malformed/schema cases covered |
| Repeated native helper plumbing had no overall deadline or stdout limit | `HelperProcess.vala` reads asynchronously in chunks, caps stdout at 4 MiB, rejects invalid UTF-8/NULs, terminates/reaps its disposable read child on failure | Stalled helper keeps the main loop responsive; timeout, overflow, nonzero exit, malformed bytes and subsequent recovery tested |
| Completing account/local helpers spawned new snapshot commands only to repaint UI | Coalesce helper completions into an idle repaint of cached validated entries; update hints/cards directly | Integration probe asserts exactly one initial snapshot after helper completion and none for two preference changes |
| Session data was parsed and validated again during rendering | Render the validated cached session array | Native ingestion/recovery and token layout probes pass |
| Every file event in the CodexBar settings directory scheduled preference reloads | React only to `wingpanel.json` and its atomic-rename target; retain polling fallback for directory replacement | Live preference replacements still update the UI without IPC |
| Exponential backoff computed huge integers before applying its one-hour cap | Bound the exponent first | Normal delays unchanged; an enormous corrupt failure counter returns the cap |
| Short manual survival checks could not observe later panel/launcher failures | Installed read-only `codexbar-wingpanel-watch.py` plus this chat's five-minute heartbeat | Tracks PID/start identity, Gala parent, CPU/RSS/FDs, panel warnings and panel/launcher coredump metadata; no process control |

Deadlines: local snapshots 5 seconds; local activity helpers 30 seconds; account
helpers 120 seconds. They do not apply to interactive login, switching or save
operations. Read helpers can retain their own shorter network/subprocess limits.
Common Meson source lists keep the deployed module and integration probes aligned.
The runner bounds its direct child; nested helper subprocesses retain their own
existing timeouts. Timer cadence and upstream network refresh policy are unchanged.

## Measured improvement and limits

`python3 mseries/bench-codexbar-history.py` compares the public pre-audit revision
`2235e9ed6a40f7066aaee639c1b19902c4d8d33e` with the new local reader. The synthetic
unindexed database has 20,000 forty-day-old rows and 100 recent rows, each with
2 KiB of irrelevant padding. Three repetitions include tracemalloc overhead.
[Receipt](codexbar-audit/2026-10-18-history-benchmark.json): identical displayed
periods; median 371.25 → 17.56 ms; peak Python allocation 46.96 → 0.01 MiB.
This is a reader benchmark under active desktop load, not a whole-panel speed,
SQLite engine memory, energy or leak measurement. A database without an appropriate
existing index still requires a scan; no index/schema is added to the owner's DB.

Validation: all 15 native Meson targets; eight synthetic performance/watch tests;
17 cache, seven session and 25 OpenCode helper tests; deployment fixture and six
image-wiring tests; full v0.77.0 port check including live IPC schema. An overlapping validation run exposed non-atomic shared fixture generation
(JSON was briefly empty); fixture replacement is now atomic and the clean native
run passes. The unchanged-snapshot render probe also reports stable widgets. Tests use
private synthetic profiles, never switch accounts or signal the live desktop.

## Live launcher observation

Wingpanel PID 335310 is a direct child of the running Gala launcher PID 2678, not
a separate systemd user service. Its executable matches the installed lifetime-fixed
core. It started at 14:23:25, after the previous task's activation; no new Wingpanel
coredump accompanies that PID change. The cause of that earlier restart is
unclassified, not asserted to be a crash or attributed to another task.

During a separate 80.2-second observation, the same panel and launcher remained
present, with no new panel events/coredumps or journal read failures. Five samples:
RSS fixed at 192,928 KiB, 50 descriptors, interval CPU about 0.30–0.55% of one core
(the initial sample spans an earlier interval). This does not prove leak freedom
or long-run stability. The known empty-FlowBox startup warning remains separate
from the [repaired popup lifetime defect](CODEXBAR-CRASH-2026-10-18.md).

The watch stores a bounded private checkpoint under `~/.cache/codexbar-mseries`,
using a lock to serialize overlapping observations. It stores event categories and
identifiers, never raw journal text, core contents or credentials. Journal output
fields exclude core environment/memory/stack payloads. It reports journal failures
or event-bound overflow rather than treating them as healthy. A PID transition
without exit evidence is explicitly unclassified. The heartbeat stays quiet while
unchanged and never restarts, kills, attaches to or launches desktop applications.
Checks depend on the Codex app/host being available; this is not a kernel-level or
continuous availability guarantee.

## Next measured work

1. Saved OpenCode account plan/quota reads are still serial and lack the persistent
   per-account TTL/backoff already used by Codex/Claude. Add workspace/account-scoped
   caching and an explicit force-refresh contract before adding bounded concurrency.
   Keep active-account quota owned by the upstream snapshot; never cache credentials.
2. Codex/Claude reparsing of a changed growing transcript starts at the beginning.
   Benchmark a large active transcript, then consider incremental offsets with
   rewrite/rotation detection and duplicate/cumulative-counter correctness. The
   current recent-file cap does not bound traversal of arbitrarily many old files;
   expose coverage rather than silently presenting a truncated index as complete.
3. `Indicator.vala` still combines widget construction, account hints and orchestration.
   Extract provider card renderers next, keeping native widget ownership explicit.
   Broad UI restructuring should retain the popup, ingestion, switching and layout
   regressions; the current extraction isolates transport without replacing the UI.
4. Profile native CPU/allocation after the next login activates this module. Do not
   infer a whole-panel improvement from the Python microbenchmark or reload a healthy
   panel solely to get a new measurement.

Deployment stages the native improvements without reloading Wingpanel. Python
helper improvements and the watch are available on the next invocation; native
transport/repaint changes load at the next login or an owner-requested reload.
