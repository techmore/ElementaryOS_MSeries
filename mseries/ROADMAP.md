# Roadmap, features and follow-ups (MacBook Pro 14" M1 Pro, elementary OS 9 on Asahi)

## Add Tasks from the panel — 2026-10-18

The Tasks tab now has a compact title entry, Add button and writable-list selector.
Enter or Add creates an undated task in the same EDS list as elementary Tasks.
The default list is selected initially; explicit list choices persist while the
panel runs. Pending saves block duplicate submissions and keep the popup open.
Errors retain the draft, and unavailable/read-only lists cannot receive tasks.

Debug and installed release builds pass all seventeen private plugin/EDS workflow
groups. New coverage checks Enter/Add, correct-list persistence, literal titles,
metadata, duplicate suppression and unavailable-list draft recovery. Real task
and event comparisons are read-only; no personal task was created by tests.
Six image-wiring checks pass. The release build is installed and Wingpanel reloaded.
[Usage and tests](calendar/README.md#adding-tasks-in-the-panel).


## Complete Tasks from the panel — 2026-10-18

Task rows now have accessible checkboxes that update the same EDS records as
elementary Tasks. Pending saves disable repeat activation; read-only or
unavailable lists disable completion. Failed saves restore the checkbox and
show a retry error. Clicking a completion checkbox keeps the panel open.

The model refetches the latest source/UID/recurrence record before changing it,
preserving newer edits. EDS’s completion helper handles repeating tasks on a
worker thread; saves record UTC modification time and sequence. Tests use only
owned synthetic data on a private bus. Fourteen plugin/EDS groups pass, including
checkbox completion metadata, stale edits, source identity, recurring
advancement, failure recovery and all existing agenda modes/navigation.
The release build is installed; real task/event row comparisons are read-only
and pass. Six image-wiring tests pass. No personal task was completed by tests.
[Behavior and tests](calendar/README.md#completing-tasks-in-the-panel).


## Factory pinned-component development dependencies — 2026-10-18

The chroot retry staged Brave and compiled the network plugin, then identified
missing Quick Settings PackageKit headers. An audit of the pinned component
build definitions added PackageKit/AccountsService/portal/Wayland, keyboard XML/XKB
and zlib development requirements explicitly. Six image-wiring tests pass.
The ISO rebuild and fresh installed YouTube qualification remain in progress.


## Orchard session memory and native qualification — 2026-10-18

Fixed three retained-object paths in the installed Python/GTK4 manager:
read-only Run output now disables GTK undo; deleted guests release output
buffers after active commands finish (rename preserves output across stale
listings); creation/name/image-search forms disconnect owned signal callbacks
on response/destruction. Hidden dashboard cards are pruned even off-page, and
image selection releases its read slot. The synthetic 12-identity / 72 MiB UTF-8
probe grew RSS 153.05 MiB before / 6.75 MiB after and ended with 12 / zero cached
buffers. The 60-form probe retained 60 dialogs plus 540 input/support wrappers
before / none after. RSS is not a portable pass/fail threshold.

Real Wayland/Vulkan + elementary blueberry qualification: baseline 12.7 minutes,
candidate 14.7 minutes; three cycles each (33 main workflow groups per build),
then another 11 groups against the installed candidate with stricter runner
scope guards. Candidate runtime hashes match all probes and the installed
package. All groups passed; owned guests were removed and original guest states
preserved. Native logs contain no unexpected UI errors or GTK warnings/criticals.
The separate Vala manager/panel was not requalified.

Candidate post-workflow idle lasted ten minutes; after the first minute settled,
app CPU averaged 0.451% of one core, with 0.305% reaped CLI-client CPU separately.
Focused intervals measured 0.526% app CPU (390 seconds), inactive 0.250% (143 seconds).
Focus was sampled, not inferred; baseline idle was inactive, so these are not
matched-focus speedup figures. Median RSS 149.88 MiB, PSS 91.69 MiB, private
74.55 MiB; settled RSS fell 1.52 MiB and private fell 0.75 MiB. FDs varied 49–51
and threads 13–14 with short-lived polls, ending at 49/13. Rows/cards/histories
stayed at two; reads/timers at two, output buffers at zero. After-cycle buffers
were 4→8→12 before / 0→0→0 after; GC-tracked process object counts (including
the harness) were roughly flat after the fix. A bare GTK FileDialog control
held 39 FDs through 20 API cancellations and a 60-second settle, with no retained
FileDialog wrappers. Warm graphics/GVFS caches are distinct from object leaks.

Repeated action-to-presentation p95 was 22.32–35.73 ms across the three candidate
probes (18 programmatic actions each, 120 Hz feedback), without a material
regression relative to these baseline runs. This is not physical input-to-photon
or a zero-jank claim. Desktop applications/builds continued during the audit.

Verification: 117 Python tests, 111 passed / six opt-in live tests skipped;
all five ARM64 CI jobs passed, including the new GTK/Granite regression job.
The live runner rejects non-Wayland sessions before waiting, records five-second
RSS/PSS/private/CPU/FD/thread/cache samples, supports repeated unique fixtures,
stops on window closure and fails on workflow/cleanup errors. Scope guards cover
backend writes, direct Run/Terminal launches, both file-transfer directions,
host mounts and symlink escapes. An additional installed-build live cycle
verified these stricter guards. Earlier XWayland/interrupted pilots are excluded
from the native comparison; the separate 30-minute installed-window observation
is labeled XWayland in the receipt.

From `mseries/orchard-incus`, reproduce with `GDK_BACKEND=wayland python3 tools/qualify-wayland.py --source "$PWD" --output /new/empty/dir --run --cycles 3 --idle-before 120 --idle-after 600`.
Independent no-Incus probe: `xvfb-run -a env -u DBUS_SESSION_BUS_ADDRESS GSK_RENDERER=cairo GDK_BACKEND=x11 python3 tools/probe-output-retention.py --output /new/retention.json`.
Evidence: `mseries/orchard-incus/audit/2026-10-18-session.json`, corresponding
before/after JSONL samples, and `docs/orchard-incus.html`. The long-session driver
revision is recorded separately from the later scope hardening; runtime hashes
are identical. Installed with `sh mseries/orchard-incus/install.sh` and standard
Orchard reopened as a native Wayland client, with a clean startup log.

Remaining: multi-hour/day stability, controlled thermal/battery measurements,
huge fleets, other themes/scales, physical keyboard/focus traversal and interactive
upload/download/Console input. No kernel, bootloader, audio or global display
settings were changed. Next: qualify these remaining environments as needed.

## Installed-boot and image build blockers corrected — 2026-10-18

The first retry staged Brave successfully, then exposed builders running outside
the root containing BuildPackages. A `.chroot` build driver now runs them in that
root. A separate older-image rehearsal found nested Ubuntu ARM64 EFI wrappers
rejected by systemd-stub. Build-time kernel preparation now embeds the actual
Linux payload and retains the vendor wrapper/provenance. A diagnostic guest
reached its installed erofs /usr and first-boot GUI after this correction.
Six kernel-input and five image-wiring regressions pass. New ISO assembly,
blank-disk install, dock matching and YouTube playback remain pending.

## Combined compact Upcoming and period views — 2026-10-18

Integrated main's Month/Week/Day agendas and readable neutral event cards with
the compact Upcoming default. Upcoming remains independent of calendar browsing
and spans the next 30 local dates; explicit period views and their navigation
remain available. Event title/time share one compact row. Expand a row for its
calendar/location/description; full titles retain hover text. Tasks stays compact.

All eleven actual-plugin/EDS groups pass, covering Upcoming boundaries, all
period modes, recurring/multi-day events, descriptions, navigation, retained
mode, task completion and live source changes. Both earlier implementation
histories are retained below. Factory build/boot remains unverified.


## Compact upcoming agenda — 2026-10-18

Event title and time now share one line with tighter row padding and date
headings. Task rows have less vertical spacing and compact subtitles.
Ellipsized event/task titles and task details retain full hover text.
The Upcoming 30-day label and date grouping remain. Integrated current main's
standalone factory account frontend and preserved both documentation histories.

Validation: native ARM64 build and existing real-plugin EDS/navigation
regressions; rendered Events and Tasks previews. Authenticated read-only
calendar/task comparisons pass, and the release build is installed locally.
Five image-wiring regressions pass. Factory boot remains separate.


## Upcoming calendar agenda — 2026-10-18

Events now always displays a rolling 30-day agenda, explicitly labeled
“Upcoming · next 30 days” and grouped by local date with Today/Tomorrow headings.
The independent EDS view spans month boundaries and is unaffected by browsing
the left calendar. Ongoing events stay visible; ended and out-of-range events
are hidden. A minute timer while open updates expiry and daily range rollover.
Tasks retains its shared EDS data. The prior Calendar Today-navigation fix is
preserved. [Behavior and install](calendar/README.md).

Validation: native ARM64 build, real-plugin EDS regressions for rolling range,
ongoing/past/boundary events and calendar navigation, plus existing live
edit/completion/source tests. The release build is installed and Wingpanel
loaded its new module. Authenticated read-only comparisons with real Google
events and Tasks pass without logging titles or modifying records. Four image
wiring tests pass. Factory build/boot remains unverified.

## OpenCode browser accounts from CodexBar + — 2026-10-18

The native Connect sheet now offers browser sign-in to save a second OpenCode account for
existing dropdown switching. Official CLI device login stores/activates it; previous credentials
are verified intact. API-key setup remains available. Duplicate accounts, cancellation and
abandoned attempts have explicit handling; account/plan/usage refresh follows completion.
Ten new login tests and native build/tests pass; live approval-link/cancel smoke preserved saved
accounts. Remaining acceptance: owner browser approval for a distinct account and dropdown switch.
See [the port notes](CODEXBAR-PORT.md#opencode-account-switching).

## Month/Week/Day agenda views — 2026-10-18

Implemented and deployed period selectors and arrows, grouped dates, readable
source-colored cards with time/calendar/location/description, bounded scrolling
and synchronized date selection. Tasks stays independent; Today retains the
chosen mode. Replaced relative carousel bookkeeping with actual grid months to
reject stale page notifications during opening/navigation.

Ten isolated real-plugin/EDS workflow groups pass in light and dark modes and
against the installed production library. Five merged-tree image-wiring tests
and focused shell/whitespace checks pass; synthetic previews inspected. Wingpanel
reloaded and mapped-library inode verified. Next: owner acceptance on real
accounts; Google remote sync, other locales and factory boot remain separate.
[Views and validation](calendar/README.md#month-week-and-day-views).

## Fresh YouTube ISO qualification in progress — 2026-10-18

Initial run 39126016747 failed before Brave staging because the calendar's GNOME
Settings dependency is excluded by elementary's package policy. Both ARM64
consumers and the Apple overlay now use the existing launcher's supported
`gnome-online-accounts-gtk` frontend. Five image-wiring tests pass, including the
package-policy regression. ISO rebuild, blank-disk installation, dock matching and
in-guest YouTube playback remain pending.

## Calendar Today navigation regression resolved — 2026-10-18

Repeated Today clicks during a return from another month could reuse the relative
month offset, request invalid carousel pages and desynchronize the heading and
agenda. Fixed the return/reset path and arrow bounds, and labeled the control
Today. Fresh ARM64 build and six installed-plugin EDS groups pass, including a
regression that fails on the previous library; four image-wiring tests also pass.
Deployed and reloaded Wingpanel, verifying the installed library mapping.
Remaining: owner confirmation with real accounts; no personal events were changed.
See [calendar navigation](calendar/README.md#month-navigation-and-today).

## Factory YouTube browser included — 2026-10-18

Brave 1.97.59 arm64 is now checksum-pinned and bundled under `/usr/lib/mseries-brave`
in both factory consumers. The YouTube launcher prefers it, without a first-login
browser download. Vendor resources/licenses, provenance and hash manifest survive
factory pruning; final hooks verify payload integrity and library resolution.
Six packaging regressions, four image wiring tests, real staging/finalization,
empty-profile Xvfb rendering and clean Resolute dependency checks pass. Headless
DOM timeout is retained as a limitation. New ISO/hardware boot and YouTube/AVD/DRM
playback still need qualification.
[Packaging and update instructions](video-decode/README.md#factory-brave-runtime--2026-10-18).

## Merged calendar desktop deployment — 2026-10-18

Merged Events/Tasks plugin built and installed with the maintained installer;
five isolated workflow groups pass against the deployed library. Wingpanel
reloaded and its new process mapping matches the installed calendar inode.
Next acceptance is the owner's clock-dropdown check and optional Google sign-in/
remote event round trip; factory hardware qualification remains separate.

## Calendar integration on main — 2026-10-18

Events/Tasks agenda, account setup, installer and factory payload are integrated.
Merged-source ARM64 build, five isolated EDS workflow groups, four image-wiring
tests, focused shell checks and README links pass. README no longer labels the
calendar work as awaiting integration. Remaining acceptance: owner Google OAuth
and remote event sync, factory assembly/boot, and account-backed desktop use.
See [calendar setup and checks](calendar/README.md). The test harness isolates
portal activation so its temporary session cleans up without document mounts.

## Calendar Events/Tasks tabs and Google account setup — 2026-10-18

The clock dropdown's right pane now has Events and Tasks tabs. Events follows
its selected day; Tasks reads all incomplete items from elementary Tasks' EDS
lists, including due-only and undated items. Activating a task opens Tasks.
Calendar Accounts opens the desktop Google/online-account sign-in. No desktop
Google account was configured at verification time: owner OAuth consent and a
real Google Calendar round trip remain required; local tests do not claim them.

Pinned datetime source `d0b3a703a7efbb5b3040d7be1ccb616eeb919c54` plus
`datetime-agenda-tabs.patch` retains upstream notices. Native ARM64 compilation
and five isolated real-plugin/EDS test groups pass: tabs/shared event UIDs,
live edits, completion/deletion, enable/disable and sources added/removed after
opening. Async source connections and generation checks reject stale views;
changed/deleted events requery their source, preserving recurring siblings.
All-day events use date semantics; undated tasks do not create calendar dots.
The release installer completed locally; the installed production plugin passes
the same five test groups. Wingpanel was reloaded and its mapped plugin inode
matched the newly installed library.
Four image-wiring tests and shell/diff checks pass. Runtime account/Tasks/EDS
packages are in both arm64 consumers; plugin and license survive pruning.
Factory image assembly/boot and Google network sync are still unverified.

[Build, install, restore, account setup and tests](calendar/README.md).
Installer: `bash mseries/install-calendar-agenda.sh`; rollback:
`bash mseries/install-calendar-agenda.sh --uninstall`. Reload Wingpanel after
installation. Next: owner selects Calendar Accounts → Google, completes sign-in,
enables Calendar and confirms a known remote event appears on its date.


## README status overview — 2026-10-18

The [README fixes/tests/remaining-work overview](../README.md#fixes-tests-and-remaining-work)
summarizes desktop and external docks, panel, kernel, power/performance parity,
CPU/GPU and local-LLM file access. Keep its pending gates aligned with the
evidence linked there as results land. Full-height hardware acceptance, dock
stability/sleep, Touch ID, factory hardware boot and matched macOS comparisons
remain open; this documentation pass does not complete those gates.

## YouTube assets on fresh installs — 2026-10-18

The default enhancement payload now installs the YouTube launcher and scalable
logo system-wide, with a checkout-independent Exec and the dock's existing window
identity. Factory prune and `/usr` artifact checks pass. Both ARM64 consumers
refresh the icon/application caches and install the container dependencies; the
transform's Brave first-boot module also carries them. Empty-user GTK4 lookup and
offline staging checks pass. Factory Brave package provisioning, a new ISO build
and fresh hardware playback remain open.
[Details](video-decode/README.md#youtube-launcher-icon--2026-10-18).

## Orchard real Wayland qualification and cleanup protection — 2026-10-18

- Verified the installed Python/GTK4 foreground app on real `GdkWaylandDisplay`/`GdkWaylandToplevel`, Vulkan and the elementary blueberry stylesheet at 120 Hz. This was not Xvfb or forced Cairo. Final run: 11 live workflow groups passed, including stale-inventory duplicate-name preservation, container/VM creation, agent-backed VM Run, lifecycle/pause/resume, snapshots/restore, clone/rename/delete, real Terminal login, native elementary backup Save portal/archive validation, file listing and CLI transfer round trip, mounted-folder reads, TCP proxy, bounded Unicode output, and cancellation cleanup. All audit fixtures were swept; original guests were preserved.
- Fixed a serious creation cleanup issue: names alone no longer authorize cleanup. Each launch carries `user.orchard.creation-token`; failed/cancelled cleanup verifies it before touching operations/instances, starts after client exit and uses bounded CLI requests. Missing/malformed ownership data fails closed. Duplicate names are rejected before launch and in the form. The live negative case confirmed an existing disposable guest survives a failed same-name request.
- Also fixed idempotent bulk settings and per-instance metadata serialization (self-induced ETag races), duplicate clicks, stale rename/filtered selection, explicit VM Secure Boot choice, agent guidance/Console launcher, a scrolling creation form, full-name tooltip and the Devices page's nested-scroll collapse.
- Final metrics (810 completed presentation records / 811 frames, eight seconds; 18 actions): frame-start→presentation median 21.923 ms / p95 29.630 / max 38.619; action→presentation median 26.257 / p95 33.620 / max 38.442; presented spacing p95 17.124 ms. Simple GTK control median 20.606 / p95 24.472 ms in a separate run. These are compositor feedback, not physical input-to-photon or a zero-jank guarantee; early action measurements used a different attribution rule and are not an improvement baseline.
- Checks: 103 tests, 97 pass / six opt-in live tests skipped, with fatal GTK criticals enabled for the GUI checks; final live run had one expected duplicate-name error and no unexpected errors/GTK warnings. Source/install parity passed. Installed with `sh mseries/orchard-incus/install.sh`; reopen Orchard to load it.
- Reproduction/evidence: `tools/qualify-wayland.py`, `tools/wayland-save-portal.py`, `tools/wayland-frame-control.py`, `audit/2026-10-18-wayland.json`, `docs/orchard-incus.html`. Driver waits for mapped/painted dialogs, guards fixture names/resources and records source hashes. An early pre-map driver response crashed GTK Wayland; invalid early attempts, foreground text interference and too-short agent waits are documented separately from the final passing run.
- Remaining qualification: physical input/focus traversal, interactive upload/download chooser selection and Console input, long-duration RSS/thermal soak, very large real fleets, other themes/scales, and the separate Vala manager/panel. No kernel, bootloader, display or audio configuration was changed.


## Orchard native developer UX and performance audit — 2026-10-18

- Enhanced the installed Python/GTK4 app in `mseries/orchard-incus/`: sidebar name/image/status/IP search and no-match state; native keyboard-accessible dashboard buttons; shortcut help/menu and view shortcuts; 780px header and scrolling Devices form; refresh indicator and safer loading/settings ownership.
- Bounded/coalesced work: latest-result-only tab/resource/catalog reads, 20s JSON reads, timer/theme/monitor cleanup, event follow-up debounce, chunked UTF-8 command output (64K-character pending mailbox/256K-character text tail), dashboard construction in 16-card batches, viewport-only chart updates, unchanged-presentation caching, linear history pruning. Busy operations no longer start twice or change another selected instance's detail.
- Verified: 86 Python tests (80 pass, six live tests skipped), including real local noisy subprocess and fatal GTK critical checks; Vala manager + Wingpanel compiled and all five Meson suites passed under Xvfb. Live read-only preflight/list passed, two existing instances preserved.
- Synthetic full-history 500-instance median UI-thread updates: Instances 55.57→4.72 ms, Dashboard 26.18→5.91 ms in one sequential run. Initial list update 93.93 ms excludes deferred dashboard construction. These are not real Wayland frame-latency or long-duration memory results.
- Evidence/method: `mseries/orchard-incus/audit/2026-10-18.json`, `tools/audit-ui.py`, and `docs/orchard-incus.html`. Remaining: virtualized rows for very large fleets, real Wayland/manual workflow qualification, and choosing/removing duplicate manager launchers. Vala UI/performance was not modified.
- Install: `sh mseries/orchard-incus/install.sh` preserves one previous package. Source/install parity checked after deployment. Reopen Orchard to load new Python code; no owner's running window, container, kernel, display or audio configuration was restarted.


## Orchard for Incus narrow-window fixes — 2026-10-17

Found at 760 px: the window was forced to ~850 px, and the instance action row
(with the More menu holding Clone/Rename/Delete) was clipped off-screen.
Fixes in `mseries/orchard-incus/`: action row is a wrapping FlowBox (hidden
buttons leave no gap, FlowBox children are not extra tab stops); stat tiles use
`ui.TileRow` and wrap 2+2 when narrow; filter box shortened; instance sidebar
240 px (was 290); detail margins 20 px; declared minimum window is now 780x480
(was 760x480, which the content could not honour). Screenshots checked at
780x480 and 1180x740, no clipping; wide layout unchanged.
- Tests: 71 run, 6 live skipped, all pass; `tests/test_layout.py` (2, need a
  display; run under xvfb-run) guards tile wrapping and action-row shrink.
- Installed with `./install.sh`. Not verified: elementary stylesheet/Wayland,
  the other tabs (Snapshots/Run/Files/Devices/Settings) and dialogs at narrow
  width, More-menu popover contents, keyboard focus order. Sidebar IPs truncate
  at 240 px.
## Orchard for Incus charts — 2026-10-17

`mseries/orchard-incus/`: charts now say what they show. Large charts (Dashboard
totals, instance Overview) draw the scale top-left and the covered time span
("last 4.5 min") top-right, and show "Collecting data…" until 3 samples exist.
CPU charts auto-scale with a 10% floor instead of a fixed 100% (idle looks idle,
busy multi-core is no longer clipped); the scale label keeps that honest.
Small sidebar/dashboard sparklines stay unlabelled. Logic in
`backend.chart_top/chart_ready/span_text`.
- Tests: 69 run, 6 live skipped, all pass (7 new). Checked headlessly: live
  shoot.py pages (collecting state) and a synthetic full-history render, dark.
- Installed with `./install.sh`. Not verified: light theme with full history,
  real Wayland/elementary stylesheet, narrow 760 px.
## Orchard for Incus UI/UX pass — 2026-10-17

Reviewed every page from headless screenshots (`mseries/orchard-incus/tools/shoot.py`
under Xvfb with the cairo renderer, a throwaway XDG_STATE_HOME and no D-Bus
session; read-only against the live Incus; nothing shown on the real display).
Changes, all in `mseries/orchard-incus/`:
- Instance actions are contextual (`backend.visible_actions`): running shows
  Stop/Restart/Pause/Shell/Snapshot, stopped shows Start/Snapshot. Delete moved
  out of the primary row into the More menu ("Delete…", red, still confirms).
- Images: Container/VM badge per row (identical-title rows are now
  distinguishable), alias shown, Delete is a quiet icon button with tooltip and
  accessible name.
- Storage: usage gauge (LevelBar, warns at 85%/95%) with percentage, from
  `backend.parse_space`.
- Filter box only shows on the Instances page; Ctrl+F jumps there first.
- Tests: 62 run, 6 live skipped, all pass (11 new). Screenshots checked in light
  1180x740 and dark 900x600. Installed with `./install.sh` (backup in `.prev`).
- Not verified: real-display rendering with the elementary stylesheet and
  Wayland (screenshots use the default GTK theme under X11); clicking through
  actions (nothing was started, stopped or deleted); narrow 760 px layout; the
  More-menu popover; keyboard focus order. Dashboard/chart axis labels and the
  empty-history look of the charts are still open.
## Orchard for Incus (Python) audit and fixes — 2026-10-17

Audit of `mseries/orchard-incus/` (installed copy was identical to source):
- Fixed: every `incus` call defaulted to a 600 s timeout, so a hung daemon
  stacked a new `incus list` thread every 3 s and never tripped the
  two-failure check. Now `backend.IncusTimeout` (a RuntimeError), a 20 s
  `POLL_TIMEOUT` for the list refresh, and an in-flight guard in `refresh()`.
- Fixed: any unrecognised Incus error was shown as "Incus isn't running" and
  the real message dropped. Socket/connect errors keep that wording; others now
  show "Incus reported an error" with the message.
- Fixed: `install.sh` deleted the old code before copying. It now stages,
  keeps one backup as `~/.local/share/orchard-incus/orchard_incus.prev`, then
  swaps; a stale `.new` dir from a crashed run is cleaned.
- Tests: `cd mseries/orchard-incus && python3 -m unittest discover -s tests`
  = 51 run, 6 live skipped, all pass (9 new: timeouts, preflight wording,
  install idempotence/backup/uninstall in a temp HOME).
- Live read-only check: `preflight()` None in 0.01 s, `list` 2 instances 0.01 s.
- Installed with `./install.sh` (backup in `orchard_incus.prev`).
- Not verified: the GTK window itself (refresh guard and problem page were
  compile-checked only, not exercised; app was not running, nothing relaunched);
  the 6 live tests; the Vala app build. Not changed: the monitor thread
  flaps `monitor_ok` every ~5 s when the daemon is down.
- Noted, not touched: stale `com.github.techmore.orchard-incus` launcher,
  desktop file and `liborchard-incus.so` (Vala app) coexist with the Python
  app's `io.github.techmore.OrchardIncus.desktop`: two menu entries.
- Next: pick the canonical implementation; build/test the Vala app.

## Orchard for Incus upstreamed into this repo — 2026-10-17

Both Orchard for Incus implementations now live in `ElementaryOS_MSeries`
(previously only on the `claude/airplay-destinations` branch and in the
separate `techmore/orchard-incus` repo):

- `mseries/orchard-incus/` — Python/GTK 4 app (installed to
  `~/.local/share/orchard-incus`, launcher `~/.local/bin/orchard-incus`),
  imported from `claude/airplay-destinations` @ 0eeefa7. Tests:
  `cd mseries/orchard-incus && python3 -m unittest discover -s tests`
  (42 run, 6 live tests skipped).
- `mseries/orchard-incus-native/` — Vala/Granite app + Wingpanel indicator,
  imported from `techmore/orchard-incus` `codex/wingpanel-indicator` @ 3913611
  (no build output; MIT LICENSE and NOTICE.md with Orchard attribution kept).
  Not rebuilt or re-tested during the import.
- Installed copy of the Python app was byte-identical to the source (diff clean).
- Not done: audit/fix pass (error states, install idempotence), Vala build
  and tests, deciding which implementation is canonical.
- Next: choose canonical implementation, then audit failure states
  (incus missing/permission denied/daemon down) with tests first.

## YouTube launcher logo — 2026-10-18

The contained Brave YouTube shortcut uses a bundled scalable YouTube play-button
icon, also installed for the current user. Desktop entry, SVG and GTK icon lookup
checks pass; live dock appearance after reopening remains to confirm.
[Installation instructions](video-decode/README.md#youtube-launcher-icon--2026-10-18).

## Dock startup and focus audit — 2026-10-18

Reviewed the pending startup fix against current main and added quiet repeated
activation plus wrapper stop forwarding/child reaping. Delayed Gala readiness,
stale workspace removals and false stock fallback now have regression coverage.
Two native production-method harnesses, seven generated-wrapper groups, eight
boot-profile tests, the ARM64 composed dock build and eleven isolated Wayland
groups pass. The latter retain focus and typed input during repeated activation.
Current dock remains stopped; no live redeployment. The reported floating dock
still needs physical-session/restart/monitor-transition qualification.
[Implementation and test scope](display-space/README.md#dock-activation-and-session-stops).

## Dock-aware window space — 2026-10-18

Visible dock space is reserved by the native compositor; hiding returns it to
maximized and half/quarter-snapped windows. Quarter layouts reflow, manual sizes
remain, fullscreen retains the monitor, and overlap hiding stays stable after
reveal. Installed into the private Gala and both quarter-plugin directories;
loads next sign-in. Ten isolated real-dock/GTK checks, nine existing snapping
checks, ARM64 builds and shell checks pass. Physical-monitor confirmation remains.
[Behavior, tests and install commands](display-space/README.md#dock-space-follows-visibility).


## Built-in VRR and boot space — 2026-10-18

[Scoped result and next-kernel checklist](aurora/hardware-tests/2026-10-18-j314s-vrr-and-boot-archive.md):
Aurora .20's builtin VRR is selected and retained in the current desk profile;
owner confirms both displays look normal and the dock works. External fixed
1080p/60 mode/layout preserved. Kernel VRR activation was brief (3/25 samples),
so sustained VRR, focus/presentation behavior, docking transitions and sleep
remain open. This display change must be controlled in future energy comparisons.
Four bootloader backups and seven retired Fairydust test files were archived
locally; six test entries removed. `/boot` reached 214.02 MiB free (~58% used
at cleanup). Aurora and stock recovery files remain; historical Fairydust-default
instructions below are superseded for the owner's current host, not removed
from factory/source tooling.


## Universal speech-to-text priority — 2026-10-18

Owner order: universal F5 dictation, deeper troubleshooting/optimization, then a
low-overhead machine assistant; Gmail preferred for future mail coverage.
Prepared IBus/AT-SPI output now preserves compose keys, uses shared resource
limits, private lifecycle status and anonymous-RAM fallback. Fifteen contracts,
GTK/Qt/Brave and synthetic Electron field checks pass. One guarded public-clip
CPU speech-to-GTK check passed at 0% normalized WER, 4.31 s first text and max
2525 RPM; no general accuracy/acoustic/speedup claim. Stage-only rollback passed
without restarting the original F5. Actual activation/rollback, real human F5,
remaining app sessions and optional grammar/translation review remain. Existing
browsers need accessibility on their next launch; no owner window is closed.
[Current implementation/evidence](dictation/README.md).

## Native full-height desktop and compact dock — 2026-10-18

The [J314 native desktop profile](display-space/README.md) restores the 74-pixel
camera strip with a protected Wingpanel clock layout, compact overlap-hiding dock
and persistent monitor-clamped placement. Installed on the current transformed
M1 Pro; ARM64 builds, eight boot helper tests, GTK allocation and payload checks
pass. The separate full-height normal-boot choice preserves recovery and the
already queued one-shot kernel trial. At the owner’s request, that queued
`.20-enh1` trial now also uses `appledrm.show_notch=1`, so one normal reboot
loads the trial and full-height layout together. Full-height hardware boot/clock/monitor
switching and dock placement persistence still need post-reboot confirmation.
Factory images retain their cropped initial mode. See the latest handoff for
commands, runtime warnings and rollback.


## .20-enh1 one-shot hardware trial staged — 2026-10-18

[Trial and rollback guide](aurora/trial/README.md): next boot selects
`elementary-aurora20-enh1`; later boots default to the retained .20 kernel.
Matched J314S DTB/shared m1n1 payload and existing fallback files are unchanged.
The first 120-second active-desktop baseline and GPU/filesystem smoke tests
completed. Identity-pinned user capture runs automatically on the next trial
boot after login/settling. Candidate boot, complete hardware/suspend/recovery
and controlled AB/BA energy qualification remain open; no savings claimed.

## Power audit and dock status on `.20` — 2026-10-18

[Power audit](power/AUDIT-2026-10-18.md): 19-22 W observed docked with two displays under an active desktop; no idle
figure, no savings applied or claimed. Next: a quiet-machine A/B (all apps closed, fixed brightness, three
alternating arms) and a docked-vs-undocked comparison. [Aurora status](aurora/STATUS-2026-10-18-AFTER-20.md): no
release after `.20`; draft 7.2.10 PR #139 not J314S-tested. On `.20` the dock links, trains 4 lanes and exposes a 4K
`DP-2` with EDID (G3/G4 by logs); owner to confirm picture/port (G5) and stability.

## Aurora energy and frozen feature releases — 2026-10-18

[Implemented plan](aurora/ENERGY-PORT-PLAN-2026-10-18.md) refreshes 52 branches /
12 PR heads, integrates existing source ports and pins a separate 7.2.10 unified
WIP build. The running J314S `.20` baseline has measured artifact identities
and scoped hardware receipts, frozen as experimental exp1. Stable promotion
requires a complete feature matrix, three boot IDs, sleep cycles and matched
energy pairs. A 64-fix review inventory keeps 7.2 build-only pending shared
GPU/SEP parity; `.20-enh1` is the first hardware candidate. Freeze history is
checked in CI; future captures include active refresh/VRR/display-power state.
Native builds/inspection passed for both profiles. `.20-enh1` also has a
[frozen, hardware-untested build prerelease](https://github.com/techmore/ElementaryOS_MSeries/releases/tag/mseries-aurora20-enh1-2026.10.18-build1)
with complete source/config/provenance retained. Full hardware/energy
qualification remains; no savings claimed.

## Persistent window snapping — 2026-10-18

Half snapping is now enforced by the OS dconf policy. A native Gala plugin adds
corner drag quarters and Super+Alt+U/I/J/K (also Super+keypad 7/9/1/3).
Installed on the working desktop, activation pending next sign-in. All four
keyboard layouts, four corner drags and Escape cancellation pass in an isolated
Wayland desktop. Physical multi-display checks remain. Factory staging includes
the half-snap policy; native quarter plugin packaging is still separate.
Details: [window-snapping/README.md](window-snapping/README.md).

## Omacom userspace support — 2026-10-17

[Audit and implementation](OMACOM-IMPROVEMENTS.md): sleep-energy records and
power report are staged by manual/transform/factory diagnostics. Touch ID
readiness and first-refresh/installer fixes are implemented. Bluetooth recovery
and built-in-key remaps are available as separate opt-ins. Offline fixtures
cover charging/clock/failure cases, controller-specific recovery and staging;
Linux CI also reads a real FAT ESP without root. Target-machine suspend,
notification, SEP, radio recovery and keymap qualification remain open. No
battery-life gain or factory hardware boot is claimed.

## Aurora enhancements source candidate — 2026-10-17

[Integration guide](aurora/enhancements/README.md): udmabuf/system heap, scoped
M3 Air thermal and camera fixes, rebased optional SMC battery properties, and
an explicit eGPU config profile. Complete source-build/CI lane uses distinct
kernel/package identities and retains the released .20 recovery candidate.
Local tests pass; ARM64 build verification is tracked in the enhancement CI.
No live deployment or measured power gain. #122/#127 display rebases and
selective Neo work remain outstanding; older duplicate branches are not imported.



## Aurora branch enhancement inventory — 2026-10-17

[All-branch audit](aurora/UPSTREAM-BRANCH-AUDIT-2026-10-17.md): 51 upstream
branches and 11 open PR heads reviewed against `.20`. Most are already in its
history; VRR support is already in the current kernel too. First qualify the
released J314S kernel and compositor. Further candidates are split udmabuf
support for local AI, scoped M3 Air thermal/camera fixes and rebased M3 display
work. Clean patch application/host tests are not hardware qualification. No
additional source or runtime enhancement was enabled by this investigation.

## Aurora 20 upstream kernel candidate — 2026-10-17

The upstream `.20` kernel now has an optional Debian payload build, versioned
`elementary-aurora20` entry and matched m1n1/J314S DT staging tool. Original
source, build recipe, licenses and hashes are retained; 9 new offline regressions
and the local package admission checks pass. [Port guide](aurora/README.md).
Next: review shared boot.bin/fallback compatibility, then a controlled hardware
batch on the J314S + WD22TB4. No deployment, dock-picture, Touch ID enrollment,
recovery-boot or factory-ISO qualification is claimed by this port.


## Dock code review and validation — 2026-10-17

The [dock code review](fairydust/usb4/DOCK-CODE-REVIEW.md) records collector/staging fixes,
36 offline unittest cases, production-function contracts and reproducible E3/E4 DT checks now in CI.
The last retained E4 record is armed without a recorded boot outcome; no dock HDMI picture is claimed.
Keep E4's loss of built-in HDMI separate from the older fallback-compatible deployment contract.


> **PRIMARY GOAL:** a picture on the WD22TB4 dock's HDMI from elementary OS on this j314s.
> Current blocker is **G3**: the DCP firmware must set link rate + lane count, then read EDID.
> Aurora has j314s Thunderbolt-display prior art; check it before more RE. This dock HDMI path remains unqualified.
> Gates, prior art and rules: [fairydust/usb4/PRIMARY-GOAL.md](fairydust/usb4/PRIMARY-GOAL.md).

## Power code audit (2026-10-17)

Power policy now reports write failures, bounds CPU caps, restarts policy on charger change,
and ships the profile watcher through both the live and immutable image paths. Baseline collectors
clean up interrupted workloads/display blanking and avoid stale parity imports. Offline power regressions
are in CI. No battery-life gain or hardware qualification is implied: paired battery runs, real unplug/replug,
profile switches, media playback, suspend and display restore still require target-device validation.

## Power and dock documentation entry point (2026-10-17)

Use the [power evidence map](power/README.md) for the canonical plan, 52-item parity checklist,
retained baseline runs and newer dock branch frontier. Active macOS/Linux workload parity is not yet measured;
the committed macOS capture contains inventory and historical sleep only. Older dock rows below are historical
planning context; consult the pinned dock branch ledger before continuing display experiments.


> **Everything currently staged and waiting for a reboot is listed in
> [`REBOOT-QUEUE.md`](REBOOT-QUEUE.md)** — what each reboot unlocks, what to
> verify, how to revert, and what does *not* need one. Start there before
> rebooting for any feature below.

## R1/R2 first-boot fixes staged — 2026-10-16

The first controlled boot (11:45:04–11:47:13) ran with the exact intended
parameters and all five rebuilt modules loaded; the bridge engaged on the dock
tunnel (`0:5 <-> 1:14`) and failed in the DP-IN path (first attempt
`-ENOLINK` with HPD low; second attempt a `dpin_init` Oops on a stale PHY),
and a Gala/simpledrm race crashed the desktop before collection. Source
revision `46bb8b6` (public patch 0011) fixes both DP-IN failures; five
modules rebuilt, all offline suites pass, and the refreshed payload was
re-staged and re-installed through the reviewed sequence (rollback → stage →
verify → plan → apply): image `486be1d9…`, same `custom.cfg` (`9eadf091…`)
and fallback-safe `boot.bin` (`6702f2c7…`); rollback set
`/home/sdolbec/dptunnel-logs/rollback-46bb8b6` (the c6fd906 set is
superseded). `next_entry` is empty; no boot armed or performed. The
`mseries-gala-failed` marker was removed and the `lightdm-wait-for-drm.conf`
drop-in is installed (effective next boot, unverified); the remaining
session-race item is shortening appledrm registration. Record:
[evidence/2026-10-16-r1-r2-fix-and-restage.md](fairydust/usb4/evidence/2026-10-16-r1-r2-fix-and-restage.md).

## Controlled-test preparation resumed — 2026-10-16

The owner resumed at fallback compatibility, with no repeated discovery.
Patch 0010 preserves DCP's original phys and every existing PHY dependency;
only the new driver consumes apple,dp-tunnel-phy through a managed getter.
Independent source review and 11 lookup fault/refcount groups pass. Static
fallback compatibility is addressed; fallback boot/runtime remains untested.

The frozen source c6fd906 was clean-rebuilt for all five modules, followed by
version/layout/export checks and actual staged-image verification. The new
initramfs alone carries the new modules and metadata; root modules, original
initramfs, kernel/default and existing GRUB entries remain untouched. The
separate entry uses bypass=1 and timeout=15000. Exact artifacts, hash-guarded
installer, rollback and collector: [CONTROLLED-TEST.md](fairydust/usb4/CONTROLLED-TEST.md).
The earlier root-module-replacing installer is superseded for this test.
No reboot, module reload/unbind, cable move or hardware success is claimed.
**Deployment status: STAGED AND VERIFIED (superseded by the re-stage above).**
The new initramfs, append-only
custom.cfg and fallback-compatible boot.bin are installed and hash-checked.
Original boot/config/grubenv backups were verified at
`/home/sdolbec/dptunnel-logs/rollback-c6fd906`. Root modules, original initramfs,
kernel/default and grubenv are unchanged. No reboot is armed (`next_entry` empty)
or performed; running modules remain unchanged. Next is one deliberate one-shot
boot of `elementary-usb4-dpin-controlled` (with the `46bb8b6` payload), then
the recorded read-only collector.

Last updated 2026-10-16. Day-to-day pending checks live in the robot: `mseries-verify status`
(seed: `mseries/local-ai/verify-checks.json`). This file is the human-readable plan.

## Stopped at source checkpoint — 2026-10-16

The owner requested a natural stopping point. Patches 0007–0009 now save the
DCP-before-DPRX bridge with source ownership, cancellation and router lifetime
handling. Final changed module builds pass; 27 bridge groups plus the earlier
29 logic groups pass, along with two board checks. Clean patch application
byte-matches 14 reviewed source files. These are offline checks, not monitor
progress: no new wake, unbypassed DPRX response, EDID/modes or picture.

No new driver, initramfs or boot payload was installed or loaded; no reboot
or cable change occurred in this batch. Only the build dependency pahole was
installed. The prepared boot payload remains a private candidate.

**Resume blocker:** the global boot.bin device tree replaces DCP's PHY with a
new DP-IN provider. Resolve default/fallback-kernel compatibility and a tested
rollback plan before deployment; a stock kernel may lack that provider.
Initramfs/module staging and the first hardware test remain undone. Do not
install the prepared payload merely because the source checks passed.

See [bridge implementation and validation](fairydust/usb4/DCP-SOURCE-BRIDGE.md).

Dock-video update 2026-10-16:

[Implementation and DeepSeek handoff](fairydust/usb4/DPIN-IMPLEMENTATION.md)
now contains additional patches 0004–0006: DP-IN resources/IRQ, inactive/ACK
handshake, shared ATC tunnel clocks and DCP callback/HPD/error integration.
29 production-logic groups and 2 compiled-board checks pass; complete Apple
DRM/PHY relocatable objects and target/control DTBs build, binding documents
and DP-IN-filtered DTB schema validate. Ghidra independently corroborates
selected REA findings. Full MODPOST/production-config/runtime checks remain.
No new module/DTB/kernel was installed, no reboot or cable move performed.

The [frontier ledger](fairydust/usb4/STATE-OF-PLAY.md) incorporates the separate
recorded live 0003 HPD-selection fix: `0:5 <-> 1:14`, but DPRX still times out.
Dock HPD establishes sink presence, not a working pixel chain. DP-IN source
is a draft, not a solved hardware path. Next resolve router DPRX versus DCP
ACTIVATE ordering using existing inputs; do not repeat discovery or count
another build as monitor detection. The owner now allows batched deployment/reboot/cable changes if needed, but
subsequently requested stopping at the source checkpoint above. One Git writer; preserve other agents' notes.

**Historical constraint (superseded by the authorization above): no M1 Pro
reboot or power cycle.** Earlier macOS cutover
and guest-boot instructions are future reference only. Current next work is
read-only live enumeration/recovery diagnosis using the Neo where useful,
with hard timeouts in delegated workers and 30-second progress updates. The
Neo cannot install a boot-time hypervisor under the already-running target.

Owner's port2 role attempt returned EIO without a role change. A fixed,
mapping-checked [CD321x read diagnostic](fairydust/usb4/inspect-cd321x-io.py)
is prepared for the owner's regular Terminal; six offline tests and sysfs
dry-run pass. No task/configuration writes or live I2C reads were performed
by this preparation. EIO cause remains unresolved; see the current handoff.

[Earlier bounded live checks](fairydust/usb4/evidence/2026-10-16-neo-live-status.md)
confirm Neo sleep assertions and Dell USB inventory, but no proxy endpoint or
external display picture. The physical dock identity/topology remains
unconfirmed. Compiler smoke has passed; the M1 Pro native baseline, approved
guest route and hardware trace remain. Keep SSH work off the primary chat.

MacBook Neo recorder now reached by SSH; key login installed and verified.
Sleep assertions are active on Neo and the Linux target. Private Python,
matching m1n1 source/build and dependencies are staged; offline checks pass
on Darwin ARM64. See [recorder setup](fairydust/usb4/NEO-RECORDER-SETUP.md)
for verified results and USB/guest gates still remaining.

[`Complete macOS cutover checklist`](fairydust/usb4/MACOS-CUTOVER-CHECKLIST.md)
is published with a native collector, IORegistry metadata parser and raw
DPTX trace hook. Native baseline collection is deferred until fresh reboot
authorization. Full MMIO capture needs
the Neo recorder and matching target XNU kernelcache; the earlier iBoot recipe
was incorrect. Twelve offline tests pass; no macOS trace or picture yet.

[`DP-IN/AUX audit`](fairydust/usb4/DPIN-AUX-AUDIT.md) identifies the missing
Apple DP-IN node family and corrects the macOS capture plan. The current
force-link probe reaches DCP but leaves the display disconnected. Future
capture needs DP-IN ranges from macOS IODeviceTree or the m1n1 ADT and the DCP
in a two-host macOS hypervisor session; this is not currently authorized. The owner's
sudo ADT export on Asahi failed with `EPERM`; strict `/dev/mem` is enabled
and the ADT memory driver is not built. No display, kernel, or hardware
qualification is claimed.
The specific regression reports and reproduction steps are tracked in
[`BUG-FIX-ROADMAP.md`](BUG-FIX-ROADMAP.md).
OS 9 implementation progress and Claude Code takeover tasks are in
[`OS9-HANDOFF.md`](OS9-HANDOFF.md).
The first factory arm64 ISO build succeeded on October 13; artifact details
and remaining verification are in [`FIRST-ISO-BUILD.md`](FIRST-ISO-BUILD.md).
Hardware boot remains unverified.
The earlier local ISO reached the graphical installer in an isolated ARM64
KVM VM; see [`VM-SMOKE-TEST.md`](VM-SMOKE-TEST.md). Repeat this on the image
with the corrected live-session hardware overlay before progressing.

## Done and verified

| Feature | How | Evidence |
|---|---|---|
| Local desktop and personal AI | Private MLX v0.7.33 + Newelle summary memory + typed OS MCP | Default Qwen3.5 4B: 9/15 short tasks, 9/9 corrected MCP workflows and personal-memory recall; Qwen9: 12/15 short tasks, later reserve interruption; [full qualification](local-ai/receipts/2026-10-16.md) |
| Quiet inference and coding profiles | One worker, six-GiB reserve, early cooling and hard fan/temperature limits; Crush 16K profile | Real Crush edit passed; Bonsai corrected MCP 9/9 and native decode 5.571 tokens/s complete; resumed 12/15 short tasks retain earlier fan interruption and are not a quiet-policy pass |
| Kernel and developer branch watch | Live fault signatures/previous boot; six-hour all-head and PR discovery | Six-hour watcher active on main; verified repair run retained 1,180 public branch heads and 193 PR heads, zero fetch errors; small-model repair advice remains excluded after two failed trials |
| CodexBar quota ETA | Visible per-limit forecasts and the earliest available limit in the bar; exhausted quotas show reset time | 11 ETA tests, 5 refresh tests, GTK render probe, and installed-module/live-snapshot checks passed |
| CodexBar popover redesign | Quota / Sessions / Spend tabs so nothing sits below the fold; level-colored limits with one caption line each; a quiet bar that only adds ETA on a real warning, labels non-session windows ("7D 35%") and dims when cached; plan chips, status dots, explained empty/error states with actions; no rebuild or flicker between unchanged polls; accessible labels | 3 Meson suites (incl. 9 presentation cases), 16 headless Xvfb renders (8 states x light/dark), no-rebuild stability probe (verified against a mutant), module installed; takes effect at next login |
| CodexBar usage freshness | One-minute backend polling; asynchronous five-second panel reads; throttled refresh on open | Meson policy tests and delayed-IPC GTK probe passed; installed on the working desktop |
| Login-screen stall fixed | `lightdm` drop-in waits for the eDP connector; display crossbar in the fairydust initramfs (`install-initramfs-crossbar.sh`) | greeter 119.7 s -> 0.82 s; dp-xbar deferrals 14 -> 0; first-dcp -> DRM 2.57 s -> 0.01 s |
| USB4 dock data (hub, mouse, headset, 1 Gb/s Ethernet) | Custom kernel `fairydust-usb4`, m1n1 + DTBs, thunderbolt quirks (`mseries/fairydust/usb4/`) | checks `dock-usb4-ethernet`, `dock-dp-retry-silent` passed |
| Boots Linux by default | Fairydust default helper is implemented, preserving stock Asahi as recovery; applying the persistent override is still pending. The last recorded stock-kernel boot lost dock mouse and Ethernet. | Apply the helper, then confirm kernel, m1n1/DTB chain, dock USB and Ethernet on-device. |
| Network indicator speed, connected-only Wi-Fi list, and usage views | Installed on the M1 Pro; user `netusage` service is active. Manual post-install includes the panel module and user logger. Overlay now includes the matching panel package for version-gated plugin compilation, then preserves the plugin. | Rebuild the image and verify the plugin loads against the final panel; check joined-network collapse, chevron expansion, and menu rendering. |
| Rounded screen corners | patched Gala, radius 14 (`install-gala-screen-corners.sh`) | **needs your look**: `gala-corners-look` |
| Pastel blue/rose theme | `install-theme-tweaks.sh` | **needs your look**: `colors-look` |
| Memory/swap/service tuning | `install-system-tuning.sh` (zram, no ModemManager/AppCenter daemon) | `zram-swap`, `services-trimmed` |
| Speaker tuning | `install-pipewire-lv2.sh` + `install-audio-stack.sh --with-dsp` | `audio-output-ok` passed |
| Battery charge limit 80% + on-battery CPU cap | `install-power.sh` (`mseries-power`) | limit verified; on-battery path simulated, real unplug pending (`power-battery-policy`) |
| Native Firefox (no snap) | `install-native-firefox.sh` | runs |
| Wi-Fi resume fix | `mseries-wifi-resume-fix` (2026-10-14: no longer aborts when the driver is already unloaded; reinstall pending on the M1 Pro) | CI test |
| Tracks upstream | merged `elementary/os` main @ 7024fd0 | `UPSTREAM-PINS.md` |
| Benchmarks | `mseries/benchmarks/` | see `benchmarks/README.md` |

## Owner roadmap: integrate Omarchy M, then migrate to Rust

Follow the Omarchy M people/projects, inventory and integrate their applicable
code into ElementaryOS_MSeries, qualify the complete behavior, then convert the
maintained implementation to Rust with measured performance and parity checks.
See [OMARCHY-M-ROADMAP.md](OMARCHY-M-ROADMAP.md) and the pinned discovery roster
in [upstreams/omarchy-m.json](upstreams/omarchy-m.json). Integration and the Rust
migration remain ongoing; announcement targets are not hardware test results.

## Implemented; runtime validation pending

**New feature request (2026-10-14):** [atomic app deployment and faster package
delivery](ATOMIC-APP-DEPLOYMENT.md). Stage verified releases, switch atomically,
retain rollback, and benchmark Flatpak/Nix alternatives to the current app
install workflow. The observed system uses apt; the reported slowdown is not yet
measured. Backend selection and implementation are open.
The manual installer batch now reuses successful metadata refreshes until a
repository/key changes and logs stage durations; real timing results are pending.
An opt-in Signal prototype (`install-signal.sh --atomic`) now stages verified
releases and supports selector rollback. Fault/concurrency tests pass; real
desktop update/rollback and backend selection remain pending.

The network/DNS logger now uses noninteractive authorization and installs a
polkit rule for read-only DNS monitoring by administrators, addressing repeated
desktop authentication prompts. Apply the updated logger installer once with
sudo available to enable DNS collection without dialogs.

| Feature | Change | Next check |
|---|---|---|
| Deferred per-user setup | Firstboot prepares CodexBar and Widevine tools and DNS policy; the user timer installs apps/services and stops after completion. Staged-root tests cover payload delivery, timer enablement and completion handling. | Verify a fresh desktop user's setup, including starting then quitting Brave to create its profile. |
| Keyboard brightness slider | Added to Pantheon's Quick Settings gear menu by `install-quick-settings-brightness.sh`; included in manual post-install, transform firstboot, and now the Apple Silicon overlay build. | Rebuild the image, then confirm it appears and changes the keyboard backlight on the live desktop. |
| OpenCode Go in M-series CodexBar | The wrapper passes an explicit API key from `auth.json`, falling back to the active unexpired OAuth access token in OpenCode v2’s `credential` table. Live account quota works; seven-day local token counts accompany it in the panel and card. | Live OAuth quota verified on 0.77.0; wrapper/helper tests and port checks pass. OAuth refresh remains OpenCode’s responsibility. |

## Open problems

Owner boot policy: use the installed Fairydust USB4 kernel by default and retain
stock Asahi for recovery. Apply with
`sudo bash mseries/fairydust/usb4/set-default-kernel.sh --apply`; the stock boot
on October 14 did not enumerate the dock's mouse or Ethernet.

| Problem | Why | Next step |
|---|---|---|
| **Built-in display dims unexpectedly** (owner-reported urgent bug, 2026-10-14) | The user installer disables ambient screen adjustment and idle dimming, and the image enhancement layer supplies the same defaults to new sessions. Manual brightness, blanking, and suspend remain available. | Apply the brightness stage, then confirm on AC/battery and through suspend/resume. If brightness still changes, capture the backlight value and related power-service logs. Cause remains unconfirmed. |
| Homeboard elementary Tasks sync bridge | It needs `gir1.2-ecal-2.0` and `gir1.2-edataserver-1.2`, then owner Google sign-in. Only the browser launcher is installed so far. | Install the two system packages with admin access, run the upstream Linux installer, and let the owner complete Google sign-in. Do not save credentials in this repository. |
| Emporia elementary desktop client | The Linux client requires WebKitGTK 6; the public HTTPS origin is still gated on TLS and authentication, while a second local poller could duplicate the active SER8 collector. | Install the WebKit dependency, configure only the owner's existing collector tunnel or a verified authenticated HTTPS origin, and test the client without enabling a collector. |
| **Expand elementary root using the 112 GiB gap** | Gap is before the Asahi stub/EFI/root unit; the added Btrfs member would require early LUKS unlock and initramfs discovery | Verify gap was prepared by Asahi Installer, review read-only preflight and verified backups; see [`procedures/ROOT-EXPANSION.md`](procedures/ROOT-EXPANSION.md) |
| **Monitor through the dock** (2 DP + HDMI on a WD22TB4) | Needs DisplayPort tunnelling inside USB4 (unimplemented upstream; Sven Peter: "requires reverse engineering that is not done yet"). The CD321x firmware picks USB4 and Linux has no mode control, so a fall-back to plain DP Alt Mode can't be forced. **Owner directed the RE path (2026-10-15): make the dock work, not the Mac's own ports.** The display crossbar already knows how to route the controller to the ACIO DP IN adapters (`dpin0`/`dpin1`); the missing piece is "who drives the DP IN adapter, and when". Experiment 1 is implemented and awaiting a hardware boot — see [`fairydust/usb4/DP-TUNNEL-RE.md`](fairydust/usb4/DP-TUNNEL-RE.md). Non-dock fallbacks are in [`fairydust/usb4/DOCK-VIDEO-DECISION.md`](fairydust/usb4/DOCK-VIDEO-DECISION.md). | Build the `-dptunnel` kernel (`FAIRYDUST_DP_TUNNEL=1`, or the `fairydust_tunnel` CI dispatch), boot it with `thunderbolt.allow_dp_tunnel=1`, run [`fairydust/usb4/test-dp-tunnel.sh`](fairydust/usb4/test-dp-tunnel.sh), and force the controller link through the connector `force_link` debugfs. Then replace the hammer with the real trigger; the last step needs a macOS m1n1-hypervisor trace from a second computer. |
| Suspend with a USB4 dock attached | `thunderbolt-apple-acio` vetoes suspend by design; the Mac stays awake with the display off | Needs the ACIO sleep/wake handshake (large). Cheap option: a clean "docked lid" mode that locks and stops the 30 s retries. |
| USB-C (non-USB4) devices lost across suspend | `phy-apple-atc` / `dwc3-apple` have no system-sleep PM; tipd resume only re-enables the IRQ | Kernel fix, tested with the user present. |
| Lid-open login needs a power-button press | Resume and greeter start correctly in the log; the panel or input does not respond until the power key | Trace one resume (see BUG-FIX-ROADMAP.md). |
| Dock Ethernet icon dies and is recreated | RTL8153B renamed eth0 to enx...; fresh NetworkManager profile each time; `rtl8153b-2.fw` missing | Add firmware, pin one profile, retest. |
| Wingpanel crash `PanelWindow.on_realize` | Upstream bug; Gala respawns the panel | Report upstream (not done). |
| **One-command installer untested on hardware** | `bin/elementary-mac-setup` + `mseries/install-unlock-screen.sh` (elementary-branded LUKS unlock screen) were written without a spare Mac; only the state machine/config logic is unit-tested | Run on a backed-up Asahi Alarm BTRFS install; confirm plymouth/keymap hook order, passphrase entry, LightDM autologin, then drop this row |
| Hardware video decode after long uptime | H.264 decode at 720p, 1080p and 4K works on the current kernel; the usb4.4 kernel includes a fix for large fragmented allocations | After long uptime on usb4.4, run `mseries/check-video-decode.sh` without compacting memory first. |

## M1 Pro parity with Omarchy M (audited 2026-10-14 against omarchy-mac-pkgs 222f7a8)

Done on the running system: Wi-Fi resume fix, speaker safety and DSP, ambient keyboard light, battery charge limit, dock hub/mouse/Ethernet, docked lid mode, zram and service trimming. Remaining, in order:

1. ~~Port `omarchy-audio-watchdog` (audio-stack self-repair) to Pantheon.~~ Installed on the M1 Pro 2026-10-14 with `sudo bash mseries/enhance.sh --only audio`, together with the no-suspend and headset-mic WirePlumber rules (rules apply at the next login).
2. Decide the Apple function-key default (`fnmode`), then make it explicit.
3. Mic mapping (`omarchy-audio-asahi-mic-map`) re-homed to the elementary audio session.
4. Lid-open login and Touch ID research (see Stretch goal 0).
5. Verify the usb4.4 kernel's AVD allocation fix after long uptime; the VA-API bridge and H.264 720p/1080p/4K decode already work on the current kernel.
6. Put the tested audio chain into the factory image.

Performance work stays measured: use `mseries/benchmarks/` before and after each change and keep the medians.

## Stretch goals (rough order of value)

0. **Apple ecosystem gaps: iCloud password sync and iMessage** (reported 2026-10-14; see `BUG-FIX-ROADMAP.md`). OpenBubbles is the first candidate for iMessage.
0. **ArtCraft apps as native Adobe and Office replacements** (evaluation requested 2026-10-14; see `BUG-FIX-ROADMAP.md`). Build, license-check and benchmark each Rust app on aarch64 before packaging.
0. ~~Native macOS installer modelled on `omacom/omarchy-mac-installer`~~ **Not pursued** (owner, 2026-10-14). Study kept in [`MAC-INSTALLER-PLAN.md`](MAC-INSTALLER-PLAN.md).
0. **Optimization repo created** (2026-10-15): [techmore/ElementaryOS_MSeries_Optimization](https://github.com/techmore/ElementaryOS_MSeries_Optimization); see [`OPTIMIZATION.md`](OPTIMIZATION.md).
0. **Efficiency goal: run minimal, scale fast** (requested 2026-10-15; targets, method and suspects in [`EFFICIENCY-GOALS.md`](EFFICIENCY-GOALS.md)). Today about 11.7 W on battery in light use, about 2x to 3x Apple's published light-use figures.
0. **Battery drain, phone-tether internet and minimum brightness** (reported 2026-10-14; rows in `BUG-FIX-ROADMAP.md`). The owner suspects the planned Rust battery-profile migration might fix the drain; measurement says the largest found cause was an audio rule, not the profile code, so port it for safety (see `EDGE-AND-RUST-PLAN.md`) but test the claim with before and after power readings.
0. **Universal Siri/Whisper-like speech to text** (requested 2026-10-14; see `BUG-FIX-ROADMAP.md`). Dictate into any focused text field in any app, plus a later voice-assistant layer. Local only (no audio leaves the Mac). Candidate engine: whisper.cpp or similar on the M1 Pro (Vulkan on Honeykrisp, or CPU); universal insertion through an IBus input method (works for GTK, Qt and Electron apps) rather than per-app plugins. Depends on the built-in microphone working: the Asahi mic mapping from Omarchy is not ported yet (parity list item 3). F5 hold-to-talk dictation installed 2026-10-18 (Voxtype + Whisper base.en); live speech round trip unverified, see `mseries/dictation/README.md`.
0. **Stay within 24 h of upstream, and port privileged code to Rust** (requested 2026-10-14; plan in [`EDGE-AND-RUST-PLAN.md`](EDGE-AND-RUST-PLAN.md)). Watched projects: [`WATCHLIST.md`](WATCHLIST.md).
0. **Minimum brightness** (requested 2026-10-14). Investigated and implemented 2026-10-16: the hardware floor is 2 nits, Mutter capped controls at 5, keys now walk an even 25-step ladder through logind, and a patched Gala adds four software steps below 2 nits. Owner validation is the next step; the phased plan (BR-01..BR-21), acceptance criteria and test protocol are in `BRIGHTNESS.md`.
0. **True Tone-like display** (requested 2026-10-14; see `BUG-FIX-ROADMAP.md`). Shift the display's white point toward the room light. Apple's True Tone uses a multi-channel sensor; the M1 Pro ambient light sensor (`iio:device1`, `aop-sensors-als`) exposes only `in_illuminance_input` (lux) on this kernel, so a faithful version is not possible yet. Interim plan: map lux plus time of day to a colour temperature through the colour plugin's night-light path (`night-light-temperature`, currently 4500 K, night light off), with slow easing and an off switch. Must not touch brightness (ambient auto-brightness stays off, see the dimming fix).
0. **Lid open shows the login screen, with Touch ID.** Today the login needs a power-button press after resume (bug tracked in `BUG-FIX-ROADMAP.md`). First fix the wake path; then investigate fingerprint login. No Linux driver for the Mac Touch ID sensor (Secure Enclave) is known to this project, so treat Touch ID as research, not a plan.

1. **Dock video via m1n1 hypervisor trace.** Needs a second computer (below). Result would also help every Asahi user.
2. ~~**Panel toggle for the battery charge limit**~~ Done 2026-10-13: a switch in the gear menu (`quick-settings/ChargeLimit.vala`, polkit action in `power/`). Pending your click-through: check `charge-limit-toggle`.
2b. **Sound Output switcher and AirPlay destinations** Built 2026-10-16, merged 2026-10-18: a Mac-style output list in the gear menu (`quick-settings/AudioOutput*.vala`) with a dot per AirPlay receiver (`quick-settings/AirPlayOutputs.vala`, `airplay/`). Discovery through `install-airplay-discovery.sh`, the helper through `install-airplay-outputs.sh`. Headless tests pass; audible AirPlay and the live panel are not verified.
3. ~~**Docked lid mode**~~ Done 2026-10-13: `install-docked-lid.sh` (user service). Real lid close pending: check `docked-lid-works`.
4. ~~**Linux VMs with KVM**~~ Guide written 2026-10-13: [`KVM-VMS.md`](KVM-VMS.md) (boot verified headless; graphics, networking address and benchmark overhead not yet measured). Scripted end to end 2026-10-16: [`vms/mseries-vm`](vms/README.md) creates, fetches media for and runs the guests (elementary OS, Windows 11 ARM64, Omarchy 4), with a 71-check hermetic suite in CI.
5. **Publish benchmark history** for every kernel/Mesa update, plot trends.
6. **Install media / transform script** for other M1/M2 Macs (see `TRANSFORM-DESIGN.md`).
7. **Tether continuity add-on**: pinned, removable ARM64 package installer and optional Brave integration are implemented (merged to main 2026-10-14); iPhone/Brave qualification remains. Current BlueZ 5.85 is below Tether's 5.86 minimum for Messages. See [`TETHER-CONTINUITY.md`](TETHER-CONTINUITY.md).
8. **Native battery time-to-full:** implemented as an optional patch and installer for elementary's Power indicator; built and installed on the M1 desktop. See [`BATTERY-ETA.md`](BATTERY-ETA.md).
9. **Torrential ARM64 native app port and optimization.** Native GTK/Granite
    package installed on the desktop; official Ubuntu torrent data transfer
    and full-ISO SHA-256 verified; RPC pause/resume checks passed. UI interaction,
    close/reopen state restoration, and measured optimization remain. Upstream source and packages stay local pending a
    license grant. See [`TORRENTIAL-PORT.md`](TORRENTIAL-PORT.md).
10. **Report upstream bugs** (Wingpanel crash: draft in `upstream/`). ~~PipeWire missing LV2 plugin in Ubuntu~~: not a bug. Ubuntu ships `libspa-filter-graph-plugin-lv2.so` in `libspa-0.2-modules-extra` (checked 2026-10-13, 1.6.2-1ubuntu1.2, the same version as the installed PipeWire). The notes saying Ubuntu omits it missed that package. Next step: install it instead of building the plugin in `install-pipewire-lv2.sh`, and add it to the factory image. Not yet tested with the Asahi audio chain.

Not realistic here: macOS 27 guests (`MACOS-VM.md`), Mac mini M4 (Asahi has no M4 support: no installer, no GPU
driver, M3 only now nearing a first release).

## Second computers available for the m1n1 hypervisor trace

The tracer (m1n1 `proxyclient`) is plain Python over USB serial, so the other machine does not need Asahi Linux, only
Python, a USB-C cable and permission to attach a USB serial device.

| Machine | Verdict |
|---|---|
| Chromebook | Possible via the Linux (Crostini) container with USB passthrough; flaky for raw serial. Second choice. |
| Work Mac (MDM, user is admin) | Best candidate if MDM allows USB serial devices. Everything lives in a user-space Python venv (`pip install pyserial construct`); no system changes. Check policy first, keep it light. |
| Windows PC (password protected) | Skip. |

## How to follow up

- `mseries-verify status` shows what is waiting; `mseries-verify run --notify` re-checks now.
- `python3 mseries/benchmarks/run.py` reruns the benchmarks (plug in the charger).
- Recovery for boot problems: `mseries/fairydust/usb4/RECOVERY.md`.

## Factory image checkpoint — 2026-10-13

Corrected CI image run 38410538372 succeeded at source 32877a7; actual
liveiso hardware helper payload verification passed. See FIRST-ISO-BUILD.md
for provenance and checksum. Next verify the downloaded corrected ISO and
repeat the VM smoke boot, then resolve the Asahi kernel/firmware packaging
gaps. Apple hardware boot remains pending.


Enhanced-kernel test path: pinned Fairydust + USB4 Debian packaging is now
implemented and compiling locally; see fairydust/debian/README.md and the
local kernel monitor. After package inspection, integrate it as an opt-in
experimental image alongside the required pinned m1n1/DTB path. Host boot
remains unchanged. Generic Ubuntu Asahi candidate is a packaging reference,
not a replacement for the enhanced test kernel.


Native Fairydust kernel Debian image package builds, with required modules and
Mac DTB. Next adapt maintainer hooks/m1n1/DTBs for opt-in mkosi image testing;
no kernel package installation or kernel VM boot has happened yet.


The optional Fairydust mkosi profile is staged with its kernel and hashed
m1n1/U-Boot package pipeline. It remains QEMU-only until an image-specific
m1n1 boot.bin/ESP step is implemented; no Mac boot claim.


The Ubuntu Asahi m1n1 binary string check confirms its USB4 tunables; the
opt-in workflow pins those packages. This is only a static component check;
ESP/m1n1 boot packaging and a native Mac test are still open.

## Local general agent (October 13)

Crush + Qwen3.5-9B uses the private Honeykrisp GPU runtime, with an on-demand
user service and native robot-menu launcher. Full prompt prefill required
256-token chunks to fit GPU scratch; a short API response, synthetic tool call
and full Crush answer have completed. The final 32k context/one-cache profile
is memory-admitted; it is not a full-context capacity benchmark. NAS connection
awaits the owner's share path/address. ANE activation remains a separate boot
trial; existing staged artifacts do not prove execution.

## GitHub upstream monitoring — 2026-10-14

`Watch public upstreams` runs every six hours and on demand. It combines
`local-ai/people-watch.json` subscriptions with the explicit branches in
`upstreams/omarchy-m.json`, and maintains one issue with pending revisions,
release changes and fetch failures. Closing the issue acknowledges observations;
new changes reopen it. Failed fetches preserve the last successful observation
and fail the Action. No upstream code is automatically merged or deployed.
The native macOS installer remains reference-only, per the owner decision.

## Factory configuration delivery — 2026-10-14

The Apple overlay finalize hook now exports its surviving `/etc` files to
`/usr/share/factory/etc` and generates individual tmpfiles copy/link entries.
This carries Wi-Fi enablement, module options and brightness autostart into
the `/usr`-only sysupdate artifact. Missing files are populated even when
parent directories already exist; administrator edits are preserved.
Export happens after pruning so unrelated base configuration is not claimed.
Implementation reviewed; no tests or image build run in this batch.

Remaining: build and boot qualification; shared enhancement-module integration,
canonical power helper under `/usr`, baked application dependencies and an
immutable-safe per-user setup path. The existing enhancement firstboot job
uses apt/build writes to `/usr` and cannot be enabled unchanged on EROFS.

## Offline factory enhancements integrated — 2026-10-14

Apple overlay finalize now stages `tuning,power,audio,session,theme,payload`
through the shared enhancement installer, then merges them after pruning.
The immutable power helper, polkit policy and compiled Quick Settings now
agree on `/usr/libexec/mseries/power`; `/usr/bin/mseries-power` supplies the CLI.
Both arm64 consumers explicitly install the runtime and CodexBar Qt dependencies.
Netusage authorization is baked, and a factory readiness file replaces the
otherwise unreachable firstboot dependency marker for per-user setup.

Dconf sources/profile are merged with distribution defaults and compiled with
the target binary before pruning. An early service recompiles persistent
`/etc` defaults before login after updates. Per-file factory copies preserve
administrator settings, including existing profiles that do not select local
defaults; those profiles require explicit selection to use these settings.

Per-user setup stops polling after CodexBar/netusage finish if the default
Brave profile is absent. A profile-change path unit wakes DRM setup later and
restarts retries until Brave closes and installation succeeds. Custom profile
locations retain timer polling. The image still does not bake Brave, video
decode, gestures or the remaining patched desktop components; their apt/build
firstboot modules stay disabled on immutable `/usr`. Speaker safety and full
hardware qualification remain separate requirements.

Reviewed twice by a subagent and corrected its findings. No tests or image
build were run in this batch. Existing pruning fixture now mocks its absent
target dconf compiler; that fixture is not target compilation evidence.
Next: build/boot qualification and bake the remaining network-dependent modules.

## Factory gestures baked at build time — 2026-10-14

Added `build-touchegg` at upstream 2.0.18 commit
`fc30d316e163f4504043353d6610e670ce5c6439` (GPL-3.0-or-later).
CMake builds with the CMake 4 compatibility option and explicit /usr + /etc
paths. Only the daemon, its configuration, service, license/provenance and
build recipe survive pruning. The X11 client autostart is omitted because
Gala consumes the daemon directly. Both image consumers install its runtime
libraries. Offline enablement and a vendor preset cover live and immutable
images; leaf factory export carries the service link. Udev's sysusers file
provides the service's input group.

The manual installer now fetches the same exact commit rather than a mutable
tag. Added Touchegg to GitHub upstream subscriptions. Subagent reviewed source
dependencies, paths, activation and licensing. No tests/build or physical
gesture qualification were run. Remaining browser, video and desktop patches
still require build-time integration; factory hardware qualification is open.

## Factory video-decode bridge candidate — 2026-10-14

Added `build-video-decode` using the existing manual installer's exact c653eaa
archive and SHA256. Meson builds/installs the stripped VA-API shared library;
finalize retains it, the Asahi alias and GPL/source/support documentation.
Competing canonical libraries or foreign Asahi aliases fail closed. Runtime
libva/libdrm and vainfo are declared in both arm64 consumers. The fragmentation
mitigation is shared with the manual installer and exported as a factory default.
Added the source to GitHub watch subscriptions and corrected stale PORT-MAP rows.

This packages a bridge candidate, not qualified hardware decode. The pinned
upstream explicitly has no supported matrix rows, and its M1/T8103 hardware
evidence does not qualify M1 Pro. AV1 compilation requires modern UAPI headers
but proves no hardware AV1 support. Kernel `apple_avd`, matching firmware,
codec/client checks and factory build/boot qualification remain open.
Subagent source/implementation review; no tests or image build run.

Final live/sysupdate post-install hooks also check package ownership of both
VA driver paths, catching a consumer Mesa package collision after overlay
application. Missing ownership metadata or inconsistent payload fails the build.

## Factory sound/keyboard fixes and panel artifact checks — 2026-10-14

Added pinned sound and keyboard builds to the Apple overlay and matching
packages/dependencies to both consumers. Pruning retains their plugins, licenses,
patches and build recipes. `panel-factory-pins.json` inventories all four panel
plugins; each builder records the actual plugin SHA256 and its source metadata.
Both final-image hooks reject missing/changed plugin bytes, incompatible package
versions and mismatched provenance. The recorder checks the build script's
source revision against the pin table before recording it.

Version checks now allow Debian epochs/packaging suffixes while rejecting
`8.0.30` as a substitute for `8.0.3`. The keyboard patch also initializes an
already-active layout's checked state before listening for subsequent changes.
Added the two elementary sources to GitHub subscriptions.

Subagent implemented/reviewed source/dependency and artifact-check pieces;
parent integrated image hooks and initial-state fix. No tests or build run.
Pinned upstream Meson/license contents could not be fetched in this turn;
dependency/license audit used repository installers and installed package
metadata, and the build refuses missing upstream license files. Network access
for Git required sandbox escalation. Factory load/render/boot qualification,
browser integration and remaining Files/Gala patches remain open.

- Universal dark mode switch built 2026-10-16 (`mseries/dark-mode/`, `install-dark-mode.sh`);
  live switch, Brave/Flatpak follow-through and the timer await the owner; Qt and Ghostty open.

- Power and battery roadmap written 2026-10-16 (`POWER-ROADMAP.md`): goals, baseline, workstreams A to G, phases 0 to 4,
  owner decisions list. First free change installed: Electron apps to native Wayland at next login.

- Local AI follow-through (October 16): newer Qwen3.5 4B 9/15 short tasks and 9/9 corrected MCP workflows; older Qwen3 4B 6/9 corrected workflows. Final app, coding and native throughput tests wait for idle windows while other owner tests continue. See the October 16 qualification receipt for current status.

- Measured default is now Qwen3.5 4B: real Newelle/MCP, separate-process memory and Crush edit passed. Qwen9 moved to larger-budget optional presets after the live reserve guard stopped it. Small-model repair advice failed and is excluded; deterministic kernel/app watching is active. Bonsai and the synthetic Tasks-to-note bridge remain in qualification.

- Local AI publication/candidate follow-through (October 16): PR #58 merged, benchmark page live, enhanced six-hour branch watch verified (1,105 heads; zero fetch errors). Bonsai completed 9/9 corrected MCP and native 5.571 decode tokens/s; resumed task 12/15 includes prior fan interruption and is not a quiet-policy pass. Tested Qwen3.5 4B remains default. Broad app adapters and full factory hardware qualification remain open.

- MCP app follow-through: create-only local Assistant Tasks adapter and settings-preserving tool refresh implemented. Concurrent/retry/conflict EDS checks and 53 contracts pass. Model note-to-task/instruction rejection (three repeats) wait for cool/idle windows; see local-ai/APP-INTEGRATION.md. Calendar writes and browser/mail/messaging adapters remain open.

- Developer watcher recovery (October 18): treat exact deleted named-ref responses as absent observations, preserving pending history and continuing branch/PR discovery. Two regression contracts and a full candidate dispatch pass; verify main dispatch after merge. This repair is independent of draft Calendar/browser/Mail GPU qualification (#86).

- MCP Tasks qualification complete: note-to-task/scoped read-back 3/3 and file-instruction rejection 3/3; all synthetic sources removed. URLError checkpoint retained. PR #66 publishes data and app coverage; default restore waits for quiet admission. Calendar writes, browser/mail adapters, Tasks GUI/reminders and full factory hardware qualification remain open.

- Agent-first Pantheon feature proposal (October 18): shared broker/permissions and durable alerts before UI, native app adapters, speech-to-text/speech-to-speech, and explicitly paired WebRTC interaction. See [design and acceptance plan](local-ai/PANTHEON-MCP-DESIGN.md). Proposal only; no new alert broker, voice conversation or WebRTC service installed.

- Upstream performance review (October 18): MLX main d8ac5fe is 28 commits ahead of tested 33630f9. Native-GQA is a candidate; numerically rejected gather routes remain excluded. Mac/MX notification-agent/voice patterns and oMLX options inform the agent-first design. [Pinned comparison and experiment plan](local-ai/UPSTREAM-FEATURE-COMPARISON.md); no runtime/governor changes or M1 Pro speedup claimed.
## CodexBar native Claude account switching — 2026-10-18

Implemented app session capture, one-time native sign-in setup, and **CLI only / Switch both** choices.
The app restarts for a native switch; its encrypted login is restored without changing preferences.
Missing sessions are labelled **app sign-in needed**. Both native accounts are now saved on this desktop. Automated snapshot round trips, rollback and
setup recovery pass. A real native account-2 → account-1 round trip completed, and the owner confirmed
the Gmail account’s chats remained visible without signing in again. See
[CODEXBAR-PORT.md](CODEXBAR-PORT.md) for the repeatable workflow and limitations.


### CodexBar account quota UX and sign-in — 2026-10-18

Alternate accounts now expose 5-hour and weekly/monthly quota separately, each with a reset countdown,
in dense dropdown rows and a second panel line. OpenCode duplicate OAuth records are collapsed into
distinct account/workspace identities. Codex + provides browser sign-in without replacing the current
login, using a native Granite window with progress and cancellation. Formatting, login isolation and
OpenCode read-only/deduplication tests pass; port compatibility and headless light/dark probes pass. The owner verified that a second real Codex account appears after the new browser sign-in flow.

Secondary quota balances are colour coded per window, matching the usage bar thresholds, while reset
countdowns stay muted. The Codex account dialog now uses a centered brand panel, stronger typography,
a compact instruction card and native actions. Light/dark render checks cover the visual changes.


### CodexBar account-choice hints — 2026-10-18

Yellow stars identify the service/account with the highest usable remaining quota percentage, using
its tightest reported limit so an exhausted five-hour session does not win on weekly balance. Red
exclamation marks independently identify the next weekly reset, including secondary accounts. Markers
include explanatory tooltips; ties are marked, stale/unknown data is excluded, and monthly resets do
not qualify. Selection tests and light/dark fixtures cover the behavior.

- Owner priority refinement (October 18): universal native dictation first, stronger on-demand troubleshooting/optimization second, lightweight everyday machine interface third. Share the existing worker and typed broker; deterministic idle alerts and command routing must not require continuous inference. Gmail is the preferred later mail adapter. See [three-tier acceptance requirements](local-ai/PANTHEON-MCP-DESIGN.md#owner-priority-three-tiers). Live dictation services have passed an activation/rollback cycle, but native input-source selection resets remain a blocker; isolated text insertion is not a stable desktop rollout.

- Universal F5 input follow-through (October 18): activated CPU/IBus with per-utterance engine acquisition/restoration; no native source list edits or IBus restart. Seventeen contracts and GTK/Qt/Brave/synthetic-Electron field checks pass, including focus/password and owner-layout preservation. Changed-source public-clip speech-to-field WER0, first5.09s, maxfan2523RPM; failures retained. Human F5 and optional grammar/translation review remain pending. Everyday4B stopped itself on reserve guard and must pass admission before resuming; no simultaneous-residency claim.


### CodexBar native account-sheet refinement — 2026-10-18

All provider add prompts share a refined Granite sheet: raised brand emblem, elementary accent icons,
framed instruction rows, concise copy and native footer buttons. Codex waiting, success and retry
states follow the same design with explicit keyboard defaults and bounded helper detail. Browser
sign-in, account storage and Claude native-app sessions retain their existing behavior. Four Meson
suites and 12 light/dark render previews pass; real authentication was previously owner-verified and
was not repeated for this visual change. The separate OpenCode API-key entry window is unchanged.


### OpenCode native API-key window — 2026-10-18

The separate OpenCode key-entry window now matches CodexBar's Granite account sheet: raised brand
mark, elementary theme accents, framed sections, labeled masked input and native Cancel/Connect
buttons. Inline checking/error states provide progress and retry focus. Existing key validation,
storage and browser/embedded sign-in methods are preserved. Six light/dark previews, mocked
cancel/invalid/rejected/success checks, four Meson suites and the port compatibility check pass.
No real authentication was repeated. Runtime GI dependencies are explicit in the panel installer.


### OpenCode one-click account entry — 2026-10-18

OpenCode **+** now opens the native API-key sheet directly; the redundant Continue popup is removed.
The existing sign-in helper, validation/storage and result/refresh flow remain intact. Module build
and four Meson suites pass; no live sign-in was required for this routing change.


### Direct Claude sign-in and account levels — 2026-10-18

Claude **+** now starts browser sign-in immediately. Dropdown active and saved-account identities
show their reported plan, with a quiet “Plan unavailable” when metadata is missing. Codex uses its
existing claims, Claude projects subscription labels from saved/live login metadata, and OpenCode
uses reported plan metadata where available. Four Meson suites, 35 Claude/9 OpenCode tests, port
compatibility, and light/dark normal-width render checks pass. Native Claude sessions and provider
authentication methods are preserved; live reauthentication was not repeated for this UI change.


### OpenCode actual subscription level — 2026-10-18

OpenCode OAuth account badges now read the workspace's current Go/Go Plus product from the official
Console status API. The live account resolves to Go. A future renewal tier or quota limit is never
used as the current level; unreadable/expired subscriptions keep an unavailable label where no
reported metadata is usable. Read-only workspace-scoped lookup, bounded timeout/body, no login or
token mutation. Seventeen helper tests, four Meson suites, port check and light/dark renders pass.

- Human F5 acceptance remains failed: owner saw a microphone desktop function rather than listening. Physical F5 remap matches listenerF14; exact prompt/app context pending. Optional GTK4 review UI/local transformation path is source-only, with22 contracts and synthetic wiring pass; no model-quality or live deployment claim. Fix F5 before panel rollout; preserve reserve/quiet admission.

- F5 diagnostics (October 18): fixed3s parent/4s client timeout mismatch, bounded field ancestor checks and async startup, deployed anonymous key/refusal tracing;23 contracts and isolated native/framework checks pass. Owner F5 failure remains unresolved pending popup/app detail. A single frozen six-case grammar/translation queue waits for quiet/default-model admission; preserve its service/checkpoint and completed failures.

- IBus reconnect recovery (October 18): Always restart the owned bridge on clean disconnect; Wants+After avoids speech-model reloads; restore native input only when global engine is empty. Private GTK reconnect and exact installed-unit clean TERM/manual stop tests pass,24 contracts. Earlier recovery and fixture failures retained. Graphical-session lifetime wiring checked, actual logout untested. Human F5 retry/model review/merge remain pending. Idle ASR pressure-release coverage is still open.


### OpenCode dropdown account switching — 2026-10-18

Secondary saved browser accounts now have Switch, using OpenCode's official service-backed auth
command and verifying the resulting selection. Identity/usage follow the active v2 credential,
with native OAuth refresh and pending-read invalidation. Workspace labels distinguish choices;
unusable sign-ins explain the need to sign in again. Twenty-five helper tests, 13 wrapper tests,
four Meson suites, port check and light/dark previews pass. Live same-account saved-session round trip
passed and the original selection was restored; distinct-account round trips use temporary fixtures.

- Local review pilot:6 completed synthetic requests,5/6 limited checks; French identifier PWNED→PWNÉ remains failed, grammar literal remains unpolished. All within policy,1.99–3.43s warm path and≤2516RPM/min9.48GiB available. Separate English/German/Japanese probes complete3/3 limited checks. Actual public-file ASR→GTK4 panel→French translation→grammar→private copy passes functional checks, preserving semantic errors (stew→soup; bruised→crushed potatoes). Original/intermediate preserved; three explicit review modes,28 contracts. No physical F5 or broad translation-quality pass; panel rollout still waits for human F5 recovery. Source/receipts are merged through PR86 with initial Pages publication verified; on-device idle-pressure release and physical F5 remain open.

- On-demand speech candidate:46 contracts plus actual private Qt6/Brave/GTK4 Wayland Check/stale-focus refusal pass. One new CPU file→field/close/reload fixture reclaimed784MiB; separate no-inference timer test released at61.00s, reclaiming767MiB. Both≥11.07GiB available, reported0RPM/<40.0C. Retained allocator/library memory and long-run stability remain limits. Not deployed over pending human F5 retry; optional panel uninstalled. Publish tested opt-in code/receipts with physical F5, rollout and continuous translation gates explicit; merge alone does not complete the goal.

- Publication follow-through: PR86 merged077bfe5; current-source CI39130696811 passed all5 jobs. Initial Pages39138713351 succeeded and canonical report bytes matched reviewed source.46 dictation/72 assistant/6 image checks pass. Publishing the opt-in candidate does not complete physical F5, panel/lazy rollout or continuous translation gates.
