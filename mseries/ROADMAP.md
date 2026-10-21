## Development website publishing — 2026-10-21

Public Pages documentation follows `dev/docs` by owner choice; `main` remains the frozen stable OS line. Keep site claims tied to dated receipts and verify Pages after merged documentation updates. The October 21 reconciliation covers wip2 dock tests, Touch ID blocking, Messages and screenshot retention without claiming stable/hardware/power qualification beyond the receipts.

## On-demand maintenance continuation — 2026-10-21

Queue/prompts and next-chat instructions: [maintenance/README.md](maintenance/README.md).
All 16 presets stay paused; continue one at a time. Kernel/dock/popup PRs #359,
#357 and #364 merged to dev. All three dock ports confirmed. Attention fix,
bounded display lifecycle logging and within-scan EDID read reuse installed for
next login, not currently loaded; no measured speedup. Actual .20 recovery,
suspend and controlled power remain open. Read latest handoff before proceeding.

# Roadmap, features and follow-ups (MacBook Pro 14" M1 Pro, elementary OS 9 on Asahi)

## Software Updates app — 2026-10-21

Rust + Granite 7 window over `mseries-update status --json` with a polkit-authorised helper; tests and CI render every state headless.
Not run on the M1 or against a real repository yet. Next: package it into the `dev`/`stable` suites, a Switchboard pane, translations, an
update notification. [Details](updates-app/README.md).

## Customer update mechanism (first slice) — 2026-10-21

`mseries-update` stages signed `mseries-*` package updates, applies them before the next login and rolls back
automatically (failed apply, interrupted power, or no healthy login). Opt-in, nothing restarts Wingpanel or the dock.
Design, decisions for the owner (repo hosting, signing key custody, first components) and the unverified list:
[UPDATER-DESIGN.md](UPDATER-DESIGN.md). Not published or run on hardware yet. Next: owner decisions, then the signed `dev`/`stable`
suites, `run_module` .deb-first (#52), a Switchboard pane reading `status --json`.

## Optional emulation source provenance — 2026-10-21

MuVM/libkrun/libkrunfw version tags now bind to immutable source commits; existing
caches must match origin/revision and have clean source before privileged work.
Eleven offline regressions pass; no emulation rebuild or host installation. Next:
qualify a future owner-authorized rebuild with the recorded source identities.
[Receipt](upstream-audits/security/2026-10-21-muvm-source-provenance.md).

## Daedalus portal and NmapUI desktop experience — 2026-10-21

Daedalus `main` is CI-green with review fixes and an elementary look; NmapUI has a native window, dock actions and a
Wingpanel scan-summary indicator running here. Next: move to TM-NmapUI-elementary (replace the Werkzeug dev-server
unit), verify dock progress live, run a scan on the current network. Production gates (host access, signing, Google
Admin consent, physical fleet) remain open. [Details](OS9-HANDOFF.md).

## All three wip2 dock ports pass scoped picture — 2026-10-21

Later rear-left picture supersedes initial failure. All 3 ports show 1080p/60;
one-cycle polling≈4.5s partner→active desktop each, with label/boundary corrections
and 0.5 s resolution disclosed. Not a speed ranking or pixel latency benchmark.
New read-only timing tool and 5 tests; existing 71 Aurora tests pass after dev
conflict resolution. Next dev merge, exact lifecycle tracing and actual `.20`
recovery; boot default unchanged, no stable promotion/power claim.
[Timing follow-up](aurora/hardware-tests/2026-10-21-j314s-wip2-first-boot/PORT-TIMINGS.md).

## Aurora 7.2 first boot: GPU/fsync pass, port acceptance incomplete — 2026-10-21

Actual wip2 boot/Image identity, package/91 early modules and unchanged legacy
shared payload verified; one-shot consumed, `.20` remains normal default.
Five-minute boot/PMP/idle and M1 Pro GLES shader/readback plus 1 MiB fsync pass.
Owner confirms internal display/input and front-left dock picture (slow to
appear); hinge-side left port picture fails, right untested. External 1080p/60
observed. Next matched physical-port evidence and real `.20` recovery; no
suspend, stable or energy-improvement acceptance.
[Report](aurora/hardware-tests/2026-10-21-j314s-wip2-first-boot/REPORT.md).

## Deferred reboot: mismatch triage and test readiness — 2026-10-21

24 mechanically-neither patches triaged: 19 source contracts retained,
five deeper/partial reviews open. Full 64-fix semantics and hardware acceptance
remain unqualified. Exact private post-boot collector/smoke commands are ready;
compiler/EGL/GLES/GI dependencies exist. No hardware tests or installed changes.
The one-shot remains armed for the owner's later attended reboot.
[Audit](aurora/unified72/static-contract-review-2026-10-21.json),
[manual sequence](aurora/unified72/BOOT-TRIAL.md#manual-collection-after-the-attended-wip2-boot).

## Aurora 7.2 one-shot armed — 2026-10-21

Repeat native CI 39601423970 passed both matrix jobs. Owner-authorized one-shot
`elementary-aurora72-wip2-trial` is armed; `.20` remains persistent default,
old/shared payload bytes are unchanged, no reboot yet. Next is owner/Claude
attended reboot, basic unlock/display/input and manual qualification, then
actual `.20` recovery. Hardware/suspend/power acceptance remains open.
[Arming receipt](aurora/unified72/one-shot-armed-2026-10-21.json).
This supersedes the unarmed staging status below.

## Aurora 7.2 staged for an attended trial — 2026-10-21

Merged #139 `644133b7799f` wip2 passed native build, independent artifact audit,
legacy-DTB/unlock checks and bounded DART/DCP/radio host controls. Owner approved
unarmed staging: separate package/Image/initramfs and non-default GRUB entry are
installed, all 2,042 regular package files verified. `.20` stays default;
`next_entry` empty, old fallback assets/shared `boot.bin` unchanged; no reboot.
71 repository unit tests pass. [Receipt and boundaries](aurora/unified72/boot-preflight-2026-10-21.json).
Next: owner/Claude-coordinated attended one-shot boot, actual Mesa/display/unlock
acceptance and return-to-.20 recovery. Full semantic parity, suspend and power
qualification remain open; no measured power win.
[First-boot plan](aurora/unified72/BOOT-TRIAL.md).

## October 21 maintenance checkpoint: kernel application next

*Superseded:* the Aurora 7.2 wip2 staging, one-shot and first-boot entries above record what happened next.

Kernel and power maintenance prompts were manually trialed, evidence-audited and
refined; all eight recurring tasks remain paused. No measured optimization or
new kernel adoption follows. **Next:** identify the owner's intended kernel
candidate and prepare its pinned source/config/build change before continuing
with package task 03. Reconcile #139's merged upstream state, avoid a direct #163
backport, and retain exact boot/recovery qualification gates. Power tooling also
needs capability-aware display capture without silently accepting missing DPMS.
See [the handoff and retained evidence](maintenance/2026-10-21/README.md).


## Native Messages experience landed — 2026-10-20

PR #353 merged to `dev` (`0bb46b7d`), including PR #352's media links, name
resolution and unread dots (the two entries below). Messages now has a native,
Apple-like conversation experience on the same BlueFerry backend: colour-coded
avatars, grouped bubbles with time headings, optimistic sending that never
doubles a message, link and media previews, an offline banner with Retry
Connection, a New Message sheet with recents, keyboard shortcuts, and a code
split into controller / model / widgets / style modules. Installed and running
on the owner's desktop. Tests: 30 model, 5 media, 47 GTK; CI green. Open:
in-app group participant confirmation, shortcuts overlay, opt-in Enter-to-send,
live media-link check. Details: `OS9-HANDOFF.md` (same date) and
`phone-setup/README.md`.

## Messages media links — 2026-10-20

Added bounded public-HTTPS image/GIF previews and YouTube thumbnail/title cards.
Uses a separate two-worker pool, RAM-only capped cache and decoded-frame bounds;
private-network targets, credentials and nonstandard ports are rejected. Sent
links auto-load, incoming links require Load Preview unless already cached.
Real test links sent to self were received fully in backend threads; MAP subject
summaries truncated longer bodies to 128 characters, so summary equality alone
was an inadequate receipt. Actual GTK rendering passed for YouTube 480×360
thumbnail, photo 500×477 and GIF 400×400/44 frames, including frame advancement,
light/dark/narrow review. Playback opens YouTube externally; MAP image/GIF
attachment payloads remain unavailable. Tests: 11 message models, five media
models, 17 private GTK checks. README includes the requested frontend integration
prompt; this is the existing GTK/Granite-over-BlueFerry architecture.

## Messages readability and unread indicators — 2026-10-20

Enlarged sidebar names to 1.4em and favorite names to 1.1em semibold. Added
blue unread dots immediately left of avatars in list and favorites, preserving
their position when photos load. Cached phonebook is now paged fully and used
for exact unique name resolution, with upstream-style NANP alternate matching;
groups, ambiguous contacts and international suffixes are never guessed.
Snapshot-only messages contribute explicit unread state. 11 model and 16 private
GTK checks pass. Phonebook refreshed (727 address entries). Three user-authorized
YouTube/photo/GIF text links were sent to self and verified as full incoming
backend messages. MAP summaries truncate long subjects at 128 characters; native
image/video/GIF rendering remains unfinished, and attachment payloads remain
unavailable through this MAP path. Pin snapshot is still not imported.

## Four-across contact favorites and Applications launcher — 2026-10-20

Favorites now use a four-column photo/initials grid above ordinary conversations,
with a themed horizontal separator. Search reflows tiles; selection preserves
drafts. 15 private GTK tests pass; light/dark/narrow fixtures reviewed. Installed
for next Messages launch. Applications entry is visible and missing icon fixed
by the scoped hicolor index/cache. No panel/dock restart.

## Verification-code offers — 2026-10-20

Installed/enabled helper adds near-pointer code cards, an available shortcut and explicit
AT-SPI field insertion. Native keyboard-to-field and private Brave copy-only
paths are covered by synthetic fixtures; direct Chromium fill needs an extension.
Offers are memory-only, expire in five minutes and respect SMS domain binding.
Installer/uninstaller preserves unrelated shortcuts and existing Messages/phone
services. Owner-field/compositor placement/focus qualification remains open.
See [implementation and limits](phone-setup/VERIFICATION-CODES.md).

## PR #343 source-merge qualification passed — 2026-10-20

Production GTK launcher controls pass light/dark visual inspection and real
private-display click/hover/menu/Escape/typing checks. Mixed and uniform window
identities dispatch the expected compositor actions; transient menus are correct.
The canonical clean build now runs these checks in CI. Receipts/screenshots:
`mseries/dock-tests/receipts/qualification-343-2026-10-20/`. No desktop deployment
or Wingpanel restart. Next: updated-head CI and source merge; hardware deployment
acceptance remains separate and requires its own authorization.

## PR #339 superseded; review hardening retained — 2026-10-20

Reconciled with concurrent #342; its startup/focus markers and focused-blue
style are preserved. Fixed ambiguous app matching, mixed-identity activation and
invalid transient app-management actions.
Five native tests, eight wrapper checks, complete taskbar build/preservation and
private focus/typing checks pass. Source-only review receipt and screenshot are
retained under `mseries/dock-tests/receipts/review-339-2026-10-20/`. No deployment
or Wingpanel restart. Next: owner recovery confirmation, representative visual/
input acceptance and separately authorized deployment for the hardening follow-up.
The coordinator closed #339 as superseded by #342 during this review; do not reopen
the obsolete PR. The original tracking integration has already landed.

## Tracking draft reconciled with canonical taskbar preparation — 2026-10-20

Draft #339 now uses #341's canonical `mseries/dock-taskbar/prepare-source.sh`
for both its production-method test and its explicit build-only mode. The latter
hashes Taskbar.vala, StartMenu.vala, TaskbarCodexBar.vala and all copied shared
CodexBar Vala sources before applying the experimental tracking patch, verifies
all remain byte-identical, performs the complete build/schema and GTK hover/focus
checks, then exits before installation. Default installation remains unchanged.
Three tracking regressions, eight wrapper tests, the full canonical native build
and the real GTK hover/focus/leave/pin probe pass against dev `689ffdf6`.
No live files, settings or services were changed. The deployed #341 taskbar and
icons remain under the recovery coordinator's ownership; #339 remains draft and
undeployed pending its review/visual/input/deployment gates.

## Draft app tracking preserves complete taskbar source — 2026-10-20

The app-ID/running-pill fix is now source-only and includes an explicit
`--build-running-apps-only` qualification mode. It applies after the complete
Windows taskbar patch, requires Taskbar.vala and the taskbar-mode schema,
verifies Taskbar.vala remains byte-identical, builds and exits before install.
Default installation is unchanged. Three native resolver/AppSystem tests and
eight wrapper regressions pass; the complete taskbar+tracking native build passes.
The earlier incompatible deployment was rolled back; the restored live Windows
taskbar binary/schema and official Teams/Outlook icons/pins are preserved.
No live deployment is part of this draft. Owner recovery confirmation and
isolated combined-taskbar UI/focus/typing validation remain gates. See
`mseries/DOCK-APP-TRACKING.md` for the incident boundary and next work.

## Import the iPhone's Messages pins — requested 2026-10-20

The cache fallback now has a concrete public Mac reference (Beeper) and passes
actual Foundation read/export/failure fixtures on ARM macOS 15/26 and Intel
macOS 26. No-account probes identify an absent cache; process-role rejection is
no longer a blanket read blocker. All CI images report SIP disabled, so owner
account/FDA/SIP-enabled access and NAS transfer remain unverified. Updated small
kit performs no security changes and retains source modification time. The
earlier process-gate interpretation below is superseded by this result.

PR #349 merged as `6b1d520c675a227394b5a5a88298083f71e81657` after all checks
passed. Ordered native import/review and encrypted mapping storage are staged
for next Messages launch. Owner account export, SIP-enabled access and actual
transfer/import remain unqualified; no successful owner macOS trip is promised.

Open feature: native Pin/Unpin, a qualified ordered Mac snapshot import, then
direct Linux synchronization of Apple's pin-settings store. Research found
private IMCore/KVS interfaces and public Mac examples; no supported public
Linux API or implemented BlueFerry/RustPush phone-pin sync was found. Local
BlueFerry stars are separate preferences. Preserve exact order, distinguish
snapshot/stale/unavailable from live sync, and resolve groups using verified
identity rather than names. No Mac export or phone pin access is qualified yet.
See [source review and implementation gates](phone-setup/PIN-SYNC-RESEARCH.md).

## Desktop message notification popups — 2026-10-20

Added `mseries/desktop-notifications/` and `mseries/install-desktop-notifications.sh`.
The user-local service is enabled/active as `mseries-desktop-notifications.service`,
using GTK3/Xwayland override-redirect popups for placement without a compositor
or Wingpanel restart. It implements the freedesktop notification interface,
shows up to three bottom-right cards, preserves focus, and dispatches supplied
Open/Reply actions. It retains no history; no notification center, inline reply,
images, sound, or native Wayland placement is claimed. Existing DND is respected;
per-app elementary notification preferences and full accessibility qualification
remain open. The installer stages by default; `--activate` enables/restarts only
this service. BlueFerry uses the existing separate version-matched backend overlay
at `~/.local/share/blueferry-unread-fix`; its Reply action patch is retained here
as `blueferry-reply.patch`. That patch derives from GPL-2.0-or-later BlueFerry
(https://github.com/erikwb/blueferry); this repository does not redistribute its
full source. Rebase the backend overlay after package upgrades.

Validation: 9 model/dispatch tests and private Xvfb/D-Bus smoke runs in light and
Adwaita dark passed. Actual pointer Reply/default actions, bus-owner refusal,
replacement, expiry, close and DND were checked using synthetic content only.
Retained screenshots are fixtures. Live synthetic notification geometry was
360x180 at (2043,1375) on workarea (0,0,2419,1571), exactly 16 pixels from right
and bottom. The service remains active/enabled and BlueFerry remains active.
BlueFerry notification tests (92) and combined overlay tests (201) passed; its
Reply action opens the existing conversation through opaque-handle activation.
No real phone messages were sent or deliberately marked read by these checks.
Actual phone-notification click-to-app focus and next-login startup remain
unverified. This is transformed-desktop work, not factory-image qualification.

## Working iPhone messages and native Messages app — 2026-10-20

The controlled 5.87 trial now has **real send and receive evidence**. Root-owned
BlueZ 5.87 bluetoothd/obexd/client run from a scoped prefix; bearer methods were
verified on the actual daemon. The fresh upstream Connect-first pairing exposed
Hands-Free and produced Classic + LE keys. After the owner enabled the newly
visible Show Message Notifications switch, MAP/MNS opened. One authorized self
text was sent and received, followed by an authorized contact test and two real
incoming replies. Contacts retained; optional ANCS remains unavailable. No
message contents, phone numbers or keys enter Git. The combination worked; the
trial does not isolate a single causal change.

Fixed the live candidate's version-detection mismatch by matching bluetoothctl
to the daemon in scoped service/launcher PATHs. BlueFerry otherwise read distro
CLI 5.85 and selected compatibility despite 5.87 running. Persistent drop-ins
are installed without restarting the working message session. Reproducible
installer/rollback: `mseries/install-messaging-bluez.sh`. Distro binaries,
kernel/bootloader and Wingpanel remain untouched. The pairing flow removed only
BlueFerry's phone-audio restriction; normal Hands-Free is now offered.

New `mseries-messages` / Messages desktop entry: GTK 4 + Granite 7, conversation
sidebar/search, plain-text bubbles, explicit contact/address selection,
contact-photo avatars with initials fallback, larger sidebar names,
multiline composer/Ctrl+Enter, per-conversation drafts while open, pending and
retry states, responsive navigation, theme following and original app icon.
Backend transport, encrypted history and group routing stay upstream. Setup
hands off to this native client; advanced group setup remains in BlueFerry.

Inbox catch-up queries up to 200 phone-exposed recent entries at open/reconnect
and logind resume,
on manual refresh and after five minutes between successful reads, using wall
time so suspend counts. Snapshot merges preserve known group routes and dedupe
MAP handles. Inbox-only snapshots stay in memory; no plaintext archive is added.
A live query returned 11 entries. Complete iCloud history and sent-history import
are not supported; controlled sleep/missed-message recovery and reboot remain
unverified. Source details: `phone-setup/UPSTREAM-REVIEW.md`, user behavior and
rollback: `phone-setup/README.md`.

Contact-photo caching was explicitly requested and enabled; a real PBAP sync
returned 727 contacts and 34 photos while MAP stayed connected.

Verification: 26 setup/protocol/reconnect/model tests and 9 private-display GTK
checks; light/dark/narrow synthetic screenshots reviewed. Draft routing across
conversation switches, duplicate-send prevention, failed-send retry retention,
group identity tokens, malicious addresses, search, offline state and narrow
navigation covered. Live native app started, MAP stayed connected, and recent
inbox rendering loaded without startup errors. Final send through the redesigned
composer and assistive-technology traversal remain hardware/UI follow-ups.
Localization strings are extractable; translated catalogs are not shipped.


## Transparent Outlook icon; dock deployment recovered — 2026-10-20

Outlook now fetches the transparent, checksum-pinned Office SVG directly from
Microsoft's CDN. The old white-backed touch icon was removed locally. GTK
resolves the SVG and its corner alpha is verified zero. Teams/Outlook icons,
launcher entries and dock pins are retained; both launchers advertise their
observed Brave StartupWMClass. Fourteen offline web-launcher tests pass.

A live app-tracking experiment incorrectly rebuilt the dock without the owner's
existing Windows Taskbar.vala customization, replacing the intended bottom bar.
The recovery chat restored the retained pre-change binary, SHA256
`960642d81bd83c4ec06be02c6a37ffa6967a874ddd42e4011827bc696002541f`.
This chat verified that hash, active dock service and private `taskbar-mode=true`.
All further dock deployments/restarts are stopped pending owner recovery
confirmation. Icons/launchers remain installed; native tracking/pill changes
were rolled back with the incompatible executable. The experimental source and
tests are retained separately in this task's scratch directory, not wired into
the installer. Any future tracking fix must preserve the complete customized
taskbar source and be isolated-tested first. No compositor or Wingpanel restart
was performed. The safe icon/launcher PR excludes the native dock experiment.

## Work Mode and Teams/Outlook deployment — 2026-10-20

Historical 11:39 deployment snapshot. The later #338 recovery entry above
supersedes the dock binary and launcher/icon status; its owner-recovery hold
remains in force. This receipt does not authorize another dock deployment.

Merged dev `8d85efe` is installed: Work Mode helper/settings, native dock, Teams
and Outlook shortcuts, and compositor package. Wingpanel and the running
compositor are unchanged; the compositor loads at next login. A concurrent dock
service restart was observed; its current binary matches the installed build.
Existing settings/pins/wallpaper and Brave session selection are preserved.
See OS9-HANDOFF.md and the deployment receipt for checks and backups. Respect
the #338 recovery hold before further dock deployment or restart; native
taskbar/window-clearance and Teams/Outlook qualification remain open.

## Work Mode integration reconciled — 2026-10-20

#329 now preserves current gesture/cursor and floating-window clearance behavior
alongside taskbar modes, and selects the size-system token appropriate to the dock.
Nine Work Mode tests, 41 compositor tests, strict Clippy, native dock/settings builds
and private window/focus/typing checks pass. #337's status-note conflicts are
reconciled and 14 offline Teams/Outlook tests pass. No live desktop deployment.
See OS9-HANDOFF.md for receipts. Next: updated-head CI before merging, then the
remaining native taskbar/network and Teams/Outlook qualification checks.

### Size-system continuation (#332), 2026-10-21

Managed taskbar sizing now follows the shared dock tokens; app typography and
strict lint coverage are expanded. Owner-selected RepoBar taskbar24pt remains
intentional. Isolated builds/tests pass; module load and mixed-monitor acceptance
remain pending. Wingpanel dynamic sizing is held because a whole-content
transform can double-apply text scale to upstream absolute/rem fonts. Qt/Electron
font-only integration also remains open. See `ui-scale/SIZE-SYSTEM.md`.
CI's absent AccountsService exposed a fixture assumption, now corrected with typed
private portal/Switcheroo services and a private logical system bus. The complete
native dock suite and fatal-critical cached-widget regression pass without owner
system services. The subsequent missing Gala keybindings schema is now supplied
as an exact pinned, test-only consumed-key fixture. Runtime schema roots exclude
all host schemas, and the cached-widget preflight asserts its four-schema inventory.
Build-tool metadata lookup remains unchanged. Current-head hosted confirmation
remains the merge gate.

## Teams official dock icon and Outlook Mail shortcut — 2026-10-20

Owner requested the official Teams dock icon and that the dock Mail button open
Outlook Web. Teams now fetches the website's icon directly from Microsoft's CDN,
verifies the pinned source checksum, extracts the original 256-pixel PNG without
alteration, and refreshes the local GTK icon cache. The Microsoft asset is not
redistributed in Git. Teams was pinned through `install-teams.sh --pin`.
`install-outlook-web.py` replaces only the elementary Mail dock pin with Outlook
Web in Brave's Default profile; the original launcher order is backed up locally.
The system mailto handler remains `io.elementary.mail.desktop`. No panel/dock
restart or media-stack changes. The Outlook launch was accepted by the existing
Brave session; authenticated mailbox access was not observed.

Fourteen offline tests pass, including actual Gio Outlook dispatch with a recording
browser, pin preservation/idempotence, official-icon checksum rejection, unchanged
ICO-to-PNG extraction and offline icon preservation. The host GTK icon theme now
resolves Teams to the official PNG and Outlook to the installed elementary Mail
icon. Both desktop entries validate. Owner sign-in to Teams remains confirmed;
live media, dock grouping and Outlook mailbox operation remain unverified.

## Open PR integration review — 2026-10-20

Scratch-ignore PR #335 merged. Reviewed #322/#334/#320/#312/#324/#326 with
combined-source CI and preserved both sets of conflicting status notes. Local
Teams, calendar tracker, bundled identity, 33 compositor tests and isolated
gesture rendering pass. CodexBar v0.78.0 custom-port check and routine staging
pass; the module loads at next login without a panel restart. See OS9-HANDOFF.md
for receipts and GitHub PRs for final merge outcomes. Next: #329 needs runtime
conflict resolution and checks for its latest taskbar/compositor head; intentional
drafts remain gated. Native gesture and live UI qualification remain open.

## Gesture package staged for next login — 2026-10-20 (Codex)

PR #326 CI passed before the latest cursor integration. Merged `dev` through
`6073858` into the feature branch, keeping the themed cursor and all three
settings watchers. Its 33 all-feature tests pass. The first release package
(PR-only source `806cde7`) was deliberately not installed: another task had
staged compositor `432fe4b` with unmerged Windows Work Mode/top-panel/taskbar
clearance changes. A separate `codex/gesture-deployment` branch combines those
exact installed compositor changes with gestures at `314652f`; PR #326 does not
absorb the unrelated Work Mode feature. Combined build passes 38 all-feature
tests, warnings-denied all-feature Clippy, release packaging and the isolated
GTK Cairo gesture pixel/state smoke. The packaging helper now honors
`CARGO_TARGET_DIR` for shared worktree builds.

Installed `0.1.0+git432fe4b+gestures.20261020` with `sudo -n dpkg -i`, followed
only by `systemctl --user daemon-reload`. Production binary excludes the
`gesture-probe` socket and retains the Work Mode D-Bus panel interface. Strict
schema validation, all shared-library resolution, installed payload SHA-256,
`gsettings get org.techmore.mseries.gestures four-finger-pinch-in` (`'launcher'`),
and the installer's read-only `--verify` pass. Compositor PID 1944 and Wingpanel
PID 2135/start times and the running compositor executable hash are unchanged:
**installed but not loaded**. No compositor restart or logout was requested.
The dock PID changed 153271 → 160644 at 10:38:17 during concurrent work; this
task issued no dock restart and the unit contents did not change. Dock is
active; attribution of that separate restart is unverified, so an unchanged
whole-session claim is not made.

Package, exact prior-binary rollback .deb, deployment JSON and smoke receipts
are retained in `~/Documents/Codex/gesture-animation-package-20261020/`.
See `mseries/pantheon-rust-compositor/GESTURE-DEPLOYMENT-2026-10-20.md` for source
revisions, hashes, rollback command and limits. Next: owner logs out/in normally
when ready; then qualify physical workspace/overview gestures, tap/natural
scroll preferences, native pacing, multiple monitors and mixed XWayland windows.

## Finger-following workspace and overview gestures — 2026-10-20 (Codex)

Continued PR #326 from `codex/gesture-animation` and merged latest `dev`
through `25011bc`, retaining the newer dock clearance implementation.
`gesture_animation.rs` now tracks swipe progress, velocity and a bounded
critically damped release spring. Horizontal swipes render the active and
adjacent workspaces offset under the fingers, resisting at the ends; vertical
swipes scale/move windows toward or away from the overview grid. Workspace,
focus and client geometry change only at completion. Cancelled/short swipes
spring back. Escape, clicks, locks, grabs, session suspension, device removal,
workspace changes and replacement gestures discard stale previews. The release
animation honors `org.gnome.desktop.interface enable-animations`. Thumbnail
rectangles preserve aspect ratio without enlargement. The steady overview
still configures clients once at completion; it is not yet a persistent
thumbnail compositor. Both native and nested renderers share scene assembly,
and hidden neighbor windows receive frame callbacks while previewed.

Validation: 32 all-feature compositor tests pass; default and all-feature
Clippy checks pass with warnings denied. The private `gesture-probe` build
feature permits deterministic nested swipe input and is absent from normal
package builds. Its self-contained Xvfb/D-Bus/GTK Cairo smoke passes actual
pixel-bound checks for workspace displacement, cancel/restore, edge resistance,
overview shrink/separation/open/close, interrupted springs and reduced-motion
release. Selected screenshots were inspected and a 3.5-second motion recording
was retained under `mseries/pantheon-rust-compositor/gesture-tests/receipts/2026-10-20/`.
Reproduction commands and measured limits are in that directory's parent README.
The first GTK Vulkan fixture run lost nested surfaces; the Cairo fixture is the
qualified path, not a Vulkan pass. Three lint-only cleanups in the newly merged
`pantheon_shell.rs` retain the dock behavior. `git diff --check` passes.

No animation package installed and no live desktop restarted. The independently
staged dock compositor package remains separate. Next: physical M-series
trackpad tuning (360 units per output, 8-unit axis threshold), native frame
pacing, multiple-output/mixed-XWayland previews and hardware lock/grab tests.

## Trackpad gesture review and dev integration — 2026-10-20 (Codex)

Continued PR #326 on `claude/trackpad-gestures`. Merged `origin/dev` at
`1740443`, resolving the two handoff/roadmap conflicts while retaining both
sets of entries and the newer corner-snapping implementation. Review fixed
in-flight gestures surviving a lock or pointer grab: owned actions now check
availability on updates and release; locking cancels sequences before focus
moves; native session suspension and device removal cancel sequences too.
Window cycling now restricts candidates to managed application windows on the
active workspace. Invalid/zero/negative pinch scales cannot launch an app.
The touchpad `click-method=none` setting now explicitly disables libinput's
software click method (the Rust input 0.10 enum omits this C API value).

Verification: `cargo test -p pantheon-compositor` passes 16 tests (including
cancelled/invalid pinch regression cases); `cargo clippy -p pantheon-compositor
--all-targets -- -D warnings` and the same command with `--features native-drm`
pass. `glib-compile-schemas --strict --dry-run` on the packaged schema passes;
`bash mseries/pantheon-rust-compositor/test-session-units.sh` passes (the host's
unrelated spice-vdagent unit emits an existing Install-section warning).
`git diff --check` passes. Updated the compositor README, architecture status
and public performance page to describe implemented versus unqualified work.
No package installed and no running session restarted. Physical device
configuration, lock/grab interruption on hardware and actual application zoom
remain unverified. Next: native trackpad qualification and finger-following
workspace/overview animation; actions still fire on release.

## Rust compositor: macOS-style trackpad gestures and touchpad settings — 2026-10-20 (Claude)

Branch `claude/trackpad-gestures` (from `origin/dev`). The live session runs
`pantheon-compositor --backend native`. Before this change it recognized only
3-finger workspace and overview swipes, never applied libinput device options
(so tap-to-click stayed off whatever Switchboard said) and sent no gestures to
applications.

- `src/touchpad.rs`: reads `org.gnome.desktop.peripherals.touchpad` and
  `.mouse` (tap-to-click, tap-and-drag/lock, tap button map, natural scroll,
  two-finger/edge scrolling, disable-while-typing, middle-click emulation,
  left-handed, click method, speed, accel profile, send-events). It applies
  them to each libinput device when the device is added. A GSettings watcher
  re-applies them to every known device when a key changes, so the
  Switchboard Mouse & Touchpad plug works live.
- `zwp_pointer_gestures_v1` (v3) is now registered. Gestures the compositor
  does not claim are sent to the focused client: two-finger pinch-to-zoom,
  unbound swipes, and every hold gesture (GTK uses holds to stop kinetic
  scrolling).
- `src/gestures.rs` rewritten around bindings read live from elementary's
  `io.elementary.desktop.wm.gestures` (3/4-finger horizontal: switch-to-workspace,
  move-to-workspace, switch-windows; swipe up: multitasking-view,
  toggle-maximized). New `org.techmore.mseries.gestures` schema (shipped in
  the package under `session/usr/share/glib-2.0/schemas`) adds the pinch
  elementary lacks: `four-finger-pinch-in` defaults to `launcher` (Launchpad);
  `three-finger-pinch-in` defaults to `none`. With the overview open, any
  multi-finger vertical swipe closes it (macOS swipe-down). Five fingers use
  the four-finger bindings. New compositor actions: move the focused window
  to the adjacent workspace and follow it; cycle windows on the workspace.

Verification (this host, no session taken over, nothing installed):
`cargo check -p pantheon-compositor --bins --features native-drm`, `cargo clippy`
(default workspace and `native-drm`, all targets) clean, `cargo test -p
pantheon-compositor` 14/14 pass (9 gesture, 2 touchpad, 3 overview).
`glib-compile-schemas --strict --dry-run` accepts the new schema. Headless smoke
(Xvfb + `dbus-run-session`, private `XDG_RUNTIME_DIR`, nested Winit backend):
a GTK Wayland client saw `zwp_pointer_gestures_v1` v3 and created swipe, pinch
and hold gesture objects.

Not verified: physical trackpad behaviour (the nested backend emits no
gestures), libinput option application on the real device, thresholds
(90 px swipe, 0.7 pinch scale) on the M1 Pro panel, and app pinch-zoom in
Firefox/GTK. The new binary is not installed; that needs a package build and a
compositor restart, which ends the owner's session. Next: finger-following
(1:1) workspace and overview animations, and a pinch-out action (show
desktop) once the compositor has that action.
## Dropdown and Orchard visual polish — 2026-10-20

Branch `codex/panel-ui-polish` applies the UI specialist skill to CodexBar, Quick
Settings, Orchard and Battery's dropdown. The owner prioritized Orchard visual
polish before feature expansion. Changes include readable CodexBar cards, labeled
Quick Settings sliders, grouped Orchard dropdown metrics/instance rows, a
responsive Orchard dashboard and selection-only bulk toolbar, and a compact
Battery summary with expandable activity and an explicit app launcher.

Validation: CodexBar's 17 tests and custom-port check pass (pin remains v0.78.0);
Orchard's five native suites pass, including seven indicator transitions, row
identity on unchanged refresh and selection/clear behavior. Patched Quick Settings
and Power modules compile; private BlueZ checks and shared slider/Battery summary
probes pass. Light/dark private renders were inspected. CI coverage now includes
the shared widget probes and native Orchard build/tests. See `PANEL-UI-REVIEW.md`
for details and limitations. No panel reload; Quick Settings/Power/Orchard are
built but not installed. CodexBar post-push staging passed all 17 tests, and the panel/daemon PID lists
were unchanged. Its module loads at next login; native Settings takes effect
on next launch. Receipt: `receipts/panel-ui-codexbar-stage-2026-10-20.json`.

## Top bar increased to 130% and managed service restored — 2026-10-20

Owner reported that 115% was not visibly larger and confirmed the target is
Wingpanel in the Rust desktop session. Increased `CONTENT_SCALE` to 1.30 for
all groups together, with matching production measurement/coordinate tests and
CI wording. Built and installed the updated panel; `test-panel-scale.sh` passed.

Found the manually launched panel was no longer running, while the native
`pantheon-wingpanel.service` had stayed inactive since the original reload.
Restored the existing managed service instead of launching another unmanaged
instance. This uses its existing `GSK_RENDERER=gl` setting for the Rust compositor;
the earlier manual launch had omitted that setting and logged repeated Vulkan
surface-loss warnings. The service is active (PID 153373), its executable bytes
match the newly installed build, and its renderer environment is `gl`. CodexBar
hover information remains off; upstream pin remains v0.78.0. Physical visual
size awaits owner feedback. Future reloads in the Rust session should use
`systemctl --user restart pantheon-wingpanel.service`.

## Entire top bar enlarged 15% — 2026-10-20

Owner clarified that the whole top bar should be bigger. Added
`wingpanel-content-scale.patch`: native IndicatorBar measurement and allocation
scale all three groups by 1.15, including Applications, clock, explicit icon/font
sizes, CodexBar, RepoBar, status controls and their spacing. This replaces the
uncommitted CodexBar-only size adjustment, so CodexBar is not scaled twice.
Notch/monitor geometry remains in monitor coordinates. Both native Wingpanel
installers apply the patch; CI runs the isolated scale check.

Built and installed with `bash mseries/install-wingpanel-codexbar-left.sh` and
reloaded Wingpanel using `GDK_BACKEND=wayland` (PID 117166; running executable
bytes match the installed binary). The CodexBar hover preference remains false;
upstream CodexBar pin remains v0.78.0. `test-panel-scale.sh` passed for production
measurement and 1.15 coordinate transforms. `test-panel-startup.sh` passed,
including monitor-width measurement, 20 clock reparent transitions and Gala
readiness. Physical visual size and dropdown interaction await owner feedback.
Next: tune only if the owner wants a different scale.

## CodexBar hover information toggle — 2026-10-20

Added **Display > Wingpanel > Hover information**, default off, stored locally as
`showHoverInfo` in `~/.config/codexbar/wingpanel.json`. It gates pointer tooltips
throughout the panel subtree, including provider marks, quota dots and hints.
Menu tooltips and accessible labels remain available. Atomic preference changes
apply to cached widgets without a provider request. Set the owner's preference
to false, installed with `bash mseries/deploy-codexbar.sh --restart`, and loaded
the module in the running Wayland Wingpanel (PID 75113; mapped inode matches the
installed module). The interrupted reload needed an explicit relaunch with
`GDK_BACKEND=wayland` because the executor exports `GDK_BACKEND=x11`. The existing
CodexBar daemon stayed running (PID 2088). Upstream pin remains v0.78.0.

Verification: native build and all 17 Meson tests passed, including preference
persistence/default-off and recursive live hover enable/disable checks;
`bash mseries/check-codexbar-port.sh` passed. Pointer behavior on the physical
desktop has not been visually inspected. Next: owner can enable the toggle to
restore hover details if desired.
## GitHub deployment outcomes in Calendar — 2026-10-20

A GitHub tab tracks Rupert deployment ready (#207 in techmore/rupert) and
Daedalus deployment ready (#17 in techmore/tm-daedalus), with stable priority,
native sub-issue gate progress, next actions, exact-commit CI and blueprint/
milestone/PR links. Refresh is read-only on opening, manually and every five
minutes while visible; offline evidence retains its date. Unknown/skipped/
cancelled checks do not count as passing. Release/recovery and operator
acceptance stay explicit GitHub gates. The feature uses the existing gh login.
Local native compilation and offline GTK/EDS integration are validated; live
menu activation waits for the next login. See mseries/calendar/README.md.

## Microsoft Teams web desktop integration — 2026-10-20

No prior Teams native port was found in the repository or remote branches. Per
owner direction, `codex/teams-native` adds the actual Microsoft Teams web client
as a per-user application shortcut, with an isolated Chrome/Edge mode and an
explicit `--use-brave-session` mode. The latter reuses the selected regular Brave
profile through Brave itself; no cookies, password databases or tokens are copied.
Installed on this J314S using Brave 155.1.97.59, profile `Default`. Chrome
155.0.8059.84 arm64 was also installed from Google's official package as the
Microsoft-listed browser fallback. Its package selected Chrome as default;
Brave was restored (`xdg-settings get default-web-browser` reports
`brave-browser.desktop`). No panel restart or audio-stack changes.

Verification: ten offline launcher/integration tests pass, including real Gio
Desktop Exec parsing with special paths, deep-link validation, private isolated
profiles, preserving sessions across reinstall/uninstall, and sharing the Brave
profile without copying it. Shell syntax, ShellCheck and desktop-file validation
pass. Local `--check` confirms Brave session mode; launch was dispatched to the
browser. A separate temporary in-app browser reached Microsoft's sign-in page.
Owner confirmed that the Brave workflow worked and signed them in. Dock
grouping, message delivery, notifications, camera/microphone, screen sharing
and meeting join remain unverified. This is a web integration, not a native Teams reimplementation or
factory-image qualification. See `mseries/teams-web/README.md` for commands,
support boundaries and sources. Next: a real meeting/media and notification check; use Chrome mode if Brave is incompatible with the tenant.
## UI fixes installed after PR #321 — 2026-10-20

PR #321 merged into `dev` as `9cb1c70`; all ten CI checks passed. Updated the
existing Orchard launcher binary at `~/.local/bin/com.github.techmore.orchard-incus`,
Battery UI at `/usr/libexec/mseries/battery/mseries-battery-app.py`, and Apple
Passwords UI at `~/.local/share/mseries/icloud-passwords/gui/app.py`. Each installed
file byte-matches the tested build/source. Existing Battery core and Passwords
worker already matched the merged source, so no full installer was rerun.

Installed-file smoke checks passed on private Xvfb/D-Bus with temporary config/data:
Battery mapped and handled a mocked dark preference notification; Passwords
scrolled at 540 × 420 and allowed Sign In focus with its worker stubbed; the actual
installed Orchard binary stayed alive without GTK criticals. No live application,
logger, panel, account, VM or wallpaper was restarted/changed. Reopen Orchard for
Incus, Battery and Apple Passwords (Experimental) to load the fixes. Live user
interaction and hardware theme switching remain to be tried. File hashes and
backup location: `mseries/receipts/ui-consistency-install-2026-10-20.json`.
## Repository housekeeping — 2026-10-20

Updated the owner checkout by 21 commits to `8ed3a76`, backed up two
byte-identical untracked documents now tracked by dev, and pruned three
registrations for missing worktree directories. All 43 existing worktrees,
local branches, and unrelated drafts remain. Git connectivity and whitespace
checks pass. Five other worktrees have local changes and remain untouched.
See OS9-HANDOFF.md for commands and backup location. Next: review open
feature PRs under their own CI and qualification gates.

## Permanent Pantheon dock and floating-window clearance — 2026-10-20

Owner visually confirmed the native Pantheon dock, then explicitly requested
permanent enablement and windows moving out of its way. Executed
`mseries/dock-policy/enable-permanent.sh`: removed bounded-trial hooks and
pending autostart, stopped trial timers, removed disabled marker, selected
48-pixel icons and auto-hide `never`, and started the regular session dock.
Live verification: service active, `RuntimeMaxUSec=infinity`, no trial stop
hook; Rust session already wants the dock at subsequent logins. Recorded the
new owner authorization in the policy copies and live config.

Rust compositor now fits ordinary floating Wayland and XWayland windows into
the work area when panels change, moving them first and shrinking only if
needed. Existing maximized/tiled handling remains; fullscreen and X11
override-redirect surfaces keep their special behavior. It neither raises
windows nor changes keyboard focus. Hidden-dock expansion does not restore
previous floating positions/sizes. Clients may enforce minimum sizes.

Verification: all 18 native-feature compositor unit tests pass, including
three new move/shrink/offset geometry cases; release build succeeds. Private
Xvfb/D-Bus integration passes bottom-edge X11 clearance, native/X11 snapping,
minimize/restore, focus preservation on initial/repeated dock activation, and
typing. Python controller tests (5) and shell syntax pass. Installed package `0.1.0+gitdbc7b14` using `sudo dpkg -i`;
service daemon-reload completed without restarting the dock or compositor.
The new binary is staged for next login; native hardware window movement remains
pending that login. The live dock remains the patched Vala/GTK Pantheon dock
hosted by Rust; no Rust dock rewrite is claimed.

Next: load the staged compositor at a normal login and visually verify
window clearance with both monitors.


## Dock test stopped before launch — 2026-10-20

Post-reboot owner reported no dock. Retained report at
`~/Documents/Codex/2026-10-20/yo/outputs/dock-trial.json` records left snap
width 960 versus monitor width 2419, then preflight failure; the dock unit
never started. Live D-Bus now exposes `FocusRoutingVersion=1`. Added explicit
`--dock-only` mode, retaining compositor identity, Start, focus/typing checks,
independent timer, RuntimeMaxSec and exact opt-out restoration. Preserve the
first terminal report rather than overwriting it on a later Stop click.

Validated with Python compilation (warnings treated as errors) and all five
controller safety tests. Installed the updated controller and requested the
owner's saved GUI approval for a 60-second dock-only trial; result goes to
`~/.local/state/mseries/dock-trial/dock-only-20261020.json`. The dock-only attempt ran 09:47:11–09:47:14: typing passed, then a focus
departure stopped it. Owner saw no dock. Journal confirms a first panel buffer.
Live preferences are overlapping-window auto-hide and 24-pixel icons. Added
`--visible` for temporarily disabling auto-hide with 48-pixel icons, restoring
preferences on normal finish/close. Presented the required approval for this
visibility test; result pending in `visible-20261020.json`. Rust workspace has
no dock crate: the current dock is the patched Vala/GTK dock hosted by the Rust
compositor; a full Rust dock port is still outstanding. Next: inspect this receipt and dock journal; investigate
the separate snap geometry discrepancy.



## Claude account and usage display — 2026-10-20

CodexBar now selects the Claude app account for the main quota when its login differs
from the CLI, and names the CLI login separately. Current profile metadata corrects
stale Pro labels after Max upgrades. Verified with live account metadata, 43 helper
tests, 17 panel test groups and the custom-port check; split-login fixtures render in
both themes. Routine deployment stages the native module for next login; live visual
acceptance remains pending.

## October 20 desktop focus and snapping

- Implemented XWayland tiling/monitor movement, left/right drag snap zones, panel
  first-buffer/activation focus protections, and an explicit window-recovery
  chooser. See [focus audit](pantheon-rust-compositor/FOCUS-AUDIT-2026-10-20.md).
- Keep the live dock opt-out while the older compositor runs; qualify the new
  native login before considering dock activation. Physical edge dragging,
  mixed-display snapping and all context-menu paths remain owner acceptance.
- `.20-enh1` is booted with PMP ready and two connected displays. Earlier scoped
  GPU/fsync captures passed; the current capture failed because Rust lacks
  DisplayConfig `PowerSaveMode`, not because display enumeration failed.
  Suspend/resume, recovery boots, sustained VRR and matched energy A/B remain open.

### Native UI responsiveness and display labels — 2026-10-21 (#242)

Canonical Troubleshooter verification and AirPlay GUI operations now use bounded
background workers with pending/error/retry behavior. Verification cancels/reaps
its owned helper on close; stale UI completions are ignored. Display arrangement
uses bounded system-font labels, full tooltips/accessibility summaries and visible
keyboard focus with selection that does not apply a display configuration.

Private real-GTK checks pass in light/dark at actual scale1/2, plus six fake-display
canvas tests, 73 local-AI unit tests and six AirPlay core tests. A new CI job retains
source-bound fixtures. See `ui-audit/NATIVE-UI-2026-10-21.md` and its 38-family
inventory. This fixes three confirmed blockers; it does not close the full native
release gate or qualify all keyboard/screen-reader/device/account workflows.
No live model, audio, display, panel or installed application was changed.

## Native UI consistency review — 2026-10-20

Branch `codex/ui-consistency-review` applies the new UI specialist skill. Orchard
now keeps primary actions in the header and puts secondary destinations in a
named menu; filters and bulk actions wrap, long names ellipsize with tooltips,
and changed controls have accessible labels. Apple Passwords scrolls its login
form and sizes stack pages independently. Orchard and Battery follow Granite's
color preference at startup and on notifications.

Verification: Orchard compiled and passed all four component tests; its UI
fixture renders at 720 × 640 with a long name in both themes, while the original
header's 761-pixel minimum fails the narrow-window check. All nine Passwords GUI
tests passed, including a short window with enlarged text; the original login
allocates 574 pixels for a 420-pixel request. Battery passed 26 tests including
startup/live color preference checks. Six light/dark screenshots were inspected.
`git diff --check` passed. See `mseries/UI-CONSISTENCY-REVIEW.md` for the review,
commands, limits and follow-ups. These changes are not installed; the running
desktop is unchanged. Next: review the PR, then qualify the installed apps;
follow up on remaining dialogs, Battery refresh state and theme/contrast gaps.

## UI consistency skill — 2026-10-20

Branch `codex/mseries-ui-specialist` adds the repository-owned
`.agents/skills/elementaryos-mseries-ui-specialist/` and an `AGENTS.md` entry
for automatic use during UI work, with implicit invocation explicitly enabled
in `agents/openai.yaml`. Inspected GTK 4/Granite 7 Vala and Python screens, Wingpanel 9
indicators, the Switchboard/libadwaita Work Mode plug, and two retained
Troubleshooter screenshots at `ed0d31a`. The skill records Apple's design
standards as the owner's quality reference and explicitly links the original
`swiftui-specialist` at upstream revision
`6f9ff8d5ad6000491cb0f483a776b7062e41cd97`; no upstream Apple content is vendored.

Verification: skill-creator `quick_validate.py` passed; relative reference links
and fully qualified repository source paths checked; pinned upstream entry
point retrieved successfully; `git diff --check` passed. This is guidance only:
no application UI, runtime packages, panel or wallpaper changed. Other screen
families were source-inspected, not newly rendered or hardware-qualified.
Next: apply the skill to the next scoped UI change and refine conventions from
that review; the source map is an inspection baseline, not a frozen design.

## Windows Work Mode work-network trigger — 2026-10-20

Windows Work Mode can now be limited to work networks identified by public IP or CIDR,
combined with the weekday schedule. Lookup is cached per uplink and only made when the
other rules pass. Remaining: visual panel review, a real scheduled/network transition,
and the active dock appearance.

## Work Mode wallpaper — 2026-10-20

Added a native Switchboard panel under Personal with a Windows Work Mode switch, a
work-wallpaper picker with four bundled original choices and custom image support,
weekday scheduling, and start/end times. A per-user systemd timer checks once a
minute and restores the wallpaper that was active
before Work Mode began. The panel, timer, and bundled Windows 11-inspired Blue
Flow wallpaper, Blue Ribbons, Violet Arc, and Forest Flow are installed on the
J314S desktop. The three newer choices are original bundled artwork. Work Mode remains off, so
the existing wallpaper is unchanged. The Switchboard constructor-order crash
is fixed; System Settings exits cleanly on relaunch. An isolated GSettings
run passed apply/restore checks without changing the live desktop. Visual panel
inspection and a real scheduled transition remain open.

PR #311 merged the dock integration and visible rename to Windows Work Mode; it
is installed on the J314S desktop. The mode remains off, preserving the current
wallpaper and dock preferences. While active it adapts elementary's existing
dock to 40-pixel icons with auto-hide disabled, keeping the user's pinned apps
and native running-window behavior; preferences are restored when the mode ends.
The UI has not been visually inspected, and a real scheduled transition remains
open. Start, Search, system tray and widgets are outside this partial dock
implementation.

For additional wallpaper choices, Windows itself supports Store themes and a
daily Spotlight image ([Microsoft personalization guide](https://support.microsoft.com/en-us/windows/experience/personalization/personalize-your-windows-experience-with-themes),
[background guide](https://support.microsoft.com/en-us/windows/experience/personalization/change-the-desktop-background-in-windows)). Microsoft’s
copyright guidance says redistribution needs an express license or permission
([reuse guidance](https://www.microsoft.com/en-us/legal/intellectualproperty/copyright/permissions)).
Do not scrape or bundle Spotlight or Windows theme files into this repo. The
panel already accepts a user-local image; any bundled set should use original
artwork or assets with explicit redistribution rights and per-file license
notes.

## Mutter-minimal viable Rust for elementaryOS M-series — started 2026-10-18

The `619ca5c` workspace slice is committed and pushed. A current ARM64 release
candidate was packaged locally and checked in private Xvfb: Winit and XWayland
started, and Zenity appeared in the compositor's live Gala-compatible window
snapshot with focus and the expected two-workspace count. On 2026-10-19 the
opt-in LightDM session also completed its first native M1 Pro login and scanout:
kernel DRM state showed the compositor's AR30 framebuffer active at 3024x1964,
and the owner confirmed the desktop was usable. Startup felt slow; Wingpanel,
the bottom dock and a colored wallpaper/background were absent in the Rust
session. A five-minute rollback returned LightDM to Gala, where the owner
reported the background had returned. The native display path and automatic
rollback are proven, but full Pantheon readiness and daily-use stability are
not. Installed Wingpanel also
connected in private Xvfb, sent shell v2 panel requests, allocated SHM buffers,
and received a valid nested `GetCurrentState` response. It is not evidence for
physical keyboard input or full shell integration. A private GTK/Wayland
Zenity field now also receives nested key events and commits Japanese text
through IBus/Mozc `mozc-jp` with a private Hiragana-on profile. F5 app behavior,
host source switching, native input and full experimental Pantheon shell
integration remain unqualified.

Working title: `Mutter-Minimal-Viable-Rust_elementaryos-mseries`. The owner
clarified that the goal is to identify and implement the compositor features
needed by the M-series/Pantheon experience, not port Mutter or reproduce all
its features. The scoped requirements and upstream feature radar are in
[`pantheon-rust-compositor/README.md`](pantheon-rust-compositor/README.md) and
[`EXPERIENCE-REQUIREMENTS.md`](pantheon-rust-compositor/EXPERIENCE-REQUIREMENTS.md).
The list is grounded in this repo's notch-aware panel, dock work area, display
profiles/hotplug, window snapping, input and session work. Features such as
Xwayland, IBus, accessibility and screencasting are conditional on an actual
supported workflow. The measured M1 Pro requires cross-device rendering:
Asahi `/dev/dri/card1` supplies EGL/renderD128 but no KMS resources, while Apple
`/dev/dri/card2` owns connected displays and has no EGL device. The opt-in Smithay nested prototype in
`rust/pantheon-compositor/` passes local `cargo check` and `cargo build`. It
advertises Pantheon's protocol v2, places
panel surfaces using anchor/size/offset, and applies exclusive panel geometry
when configuring maximized windows. A changed panel work area now reconfigures
already maximized windows, while unchanged panel repaints do not send redundant
configures. Work-area caches now cover every active output; maximized/fullscreen
windows and popup constraints use the output containing their window, and panel
removal triggers work-area reflow. New committed toplevels are centered and
cascaded in the focused window's work area, falling back to the pointer output
and then the primary output; they are activated and focused. Absolute pointer events map to all logical
outputs. The configured primary connector is retained through monitor profile
application and hotplug while it remains connected, falling back to eDP or the
first available output. These new behaviors are compile-checked but not runtime-qualified. The
v2 protocol probe completed a nested Xvfb run and sent panel requests over the
Wayland socket. Installed Wingpanel 8.0.4 also connected in an
isolated nested Wayland run, sent `get_panel`, anchor and hide-mode requests,
and attached SHM buffers. It reports the absent `org.gnome.Mutter.DisplayConfig`
service. The prototype now returns its read-only `GetCurrentState` query using
all tracked output modes and logical positions, and increments the state serial
on output add/update/remove before emitting `MonitorsChanged`; Wingpanel connects without the
missing-service error. `ApplyMonitorsConfig` validates connector assignments,
mode IDs, scale and transform, applies native DRM mode changes through Smithay's
shared output manager with rollback, and applies temporary layout changes.
Method 2 saves a per-user monitor profile and native startup restores it.
Native output disable/re-enable is implemented, including persistence of the
enabled state and keeping disabled connectors in the monitor inventory.
Native transitions keep existing outputs live while staging replacements, and
can atomically reassign one CRTC to a different connector when the encoder
supports it. Outputs outside the requested set are retired after all requested
outputs are active; failures attempt to restore the prior set, modes and layout.
The path builds but still needs hardware and failure qualification.
Mirroring, unsupported properties and nested Winit monitor-set changes remain
rejected. Both default and native DRM builds compile; live native mode and
output-set changes remain unqualified. The compositor advertises
`wp_fractional_scale_v1` and `wp_viewporter`, updating window surface scale
preferences from mapped outputs. Moving surfaces across differently scaled
outputs still needs runtime verification. The compositor also serves Wingpanel's `org.gnome.Shell`
accelerator API and matched `Super+N` to an `AcceleratorActivated` signal during
an isolated nested run. `xdg-activation-v1` now validates recent seat-backed
tokens, consumes them after use and raises/focuses mapped target windows when
the session is unlocked; app launch flows remain unverified. The
`xdg_toplevel.set_minimized` request now unmaps and retains windows, which valid activation requests
can restore at their previous position; this is not runtime-qualified.
The compositor now handles the existing half-snap and quarter-snap keyboard
chords, uses the focused window's output work area, and reflows tracked tiles
when work areas change. `Super+Shift+Left/Right` moves a window to the adjacent
output while preserving its work-area offset or tile position. This code is
compile-checked only. It loads shortcut arrays from the installed Mutter,
Pantheon and GNOME GSettings schemas at session startup, with built-in defaults
when those schemas are unavailable. Drag-to-corner preview, live binding
reload, multi-output behavior, and runtime snapping qualification remain open.
The keyboard's XKB model, active layout, options, and repeat settings now load
from the user's GNOME input-source and keyboard schemas. A one-second settings
poll applies layout/option and repeat changes to connected Wayland clients.
Live behavior has only been compile-checked. The M1 Pro currently selects US
XKB with `ctrl:swap_lwin_lctl`; its installed `mozc-jp` IBus source is inactive
and remains conditional.
Quarter drag previews now appear in the 40-logical-pixel output corners,
Escape cancels the snap, fixed-size windows are excluded, and release applies
the selected quarter. This path is compile-checked only.
`ShowOSD` renders a minimal brightness/volume indicator with icon and level
meter; text labels, full Pantheon styling, lock-screen action modes and physical
media-key activation remain unimplemented or unqualified. Relative pointer motion now
updates pointer focus and drives the compositor's existing move/resize grabs;
xdg popup requests now install Smithay keyboard/pointer grabs for managed
toplevel roots. Both features build locally; popup behavior has not been
runtime-qualified. Autohide, blur, multi-output reflow, monitor mode
application, Dock behavior and full session integration remain unqualified.
The first internal-panel native scanout is confirmed; external output, input,
stability and comparative performance work remains. A public search found elementary's
[Gala](https://github.com/elementary/gala) still based on libmutter, with no
first-party Rust compositor to reuse. The WD22TB4 HDMI G3 DCP/kernel blocker
remains a separate workstream. Read-only enumeration on the current M-series
host found the Asahi GPU at `/dev/dri/card1`, Apple display controller at
`/dev/dri/card2`, and connected `eDP-1`/`DP-2` outputs; this is device presence,
not evidence of compositor modesetting. The opt-in native DRM path is
implemented while keeping nested Winit as the default. The `native-drm`
Smithay dependency feature now compiles locally after installing
`libseat-dev`. The non-invasive `pantheon-drm-probe` reports the Asahi renderer
on card1/renderD128, with KMS resource queries unsupported there. Card2 owns
`eDP-1` and currently reports external connectors disconnected; card2 has no
EGL device. A 2026-10-19 release-mode preflight allocated scanout-capable
DMA-BUFs at the preferred 3024×1964 size on Asahi and imported AB30, AR30, AB24
and AR24 into Apple GBM using the implicit modifier. Apple `ADDFB2` rejected
AB30 with `EINVAL`; it accepted AR30, AB24 and AR24. Each unassigned test
framebuffer was immediately removed. Native output formats now omit AB30 and
prefer the three accepted formats. The probe did not acquire DRM master, attach
a framebuffer to a plane, modeset, or change output state. This establishes
cross-device import and KMS framebuffer registration. All three DRM plane
objects also advertise AR30, AB24 and AR24, though the non-master query reports
no current CRTC/framebuffer assignment. Plane routing, atomic modesetting,
visible scanout and failure handling remain first-session requirements for
this M1 Pro, not optional general multi-GPU support. The executable now keeps nested Winit as
its default and provides an explicit `--backend native` path behind
`native-drm`; this wires libseat,
libinput, connected outputs on the first usable KMS device, calloop rendering
and vblank completion. It prioritizes eDP and places additional outputs to its
right. DisplayConfig no longer advertises a fabricated Winit output in native
mode. Both build configurations pass locally. Native mode has not been
launched because it deliberately takes over the active display. Connector
addition/removal reconciliation is implemented with a two-second poll. On
hotplug, connected outputs keep their current positions and new outputs are
placed after the existing layout. Hotplug, saved-layout restore, session
switching and actual M-series scanout remain unqualified. Local
`cargo check --bins` and `cargo build --bins` pass with and without
`native-drm`; they establish compilation only, not successful
connector modesetting.

Read-only DisplayConfig now lists the modes reported by each native DRM
connector, including current/preferred flags and timing-derived refresh rates.
It still cannot apply a requested mode, position, scale or transform; native
mode/layout configuration and rollback are the next display-settings work.

Smithay's `ext-session-lock-v1` is implemented in both rendering backends:
applications are hidden behind lock surfaces or black, input is confined to
the locker, and lock confirmation waits for each mapped output to present a
cleared frame. Default and `native-drm` builds pass. Real locker behavior,
authentication/PAM integration, nested runtime behavior and native lock/unlock
remain unqualified; the compositor does not provide the lock-screen UI.

The compositor can now optionally send systemd `READY=1` after its Wayland
listener and selected backend initialize (`--notify-systemd`). On native
startup, readiness follows renderer and connected-output initialization. This
provides a truthful readiness boundary used by the repository-only opt-in
service; it does not install or switch the host login session. Native
runtime/session behavior remains unqualified.

A separate `pantheon-rust-wayland` session payload now mirrors the installed
GNOME session/systemd contract: a unique login entry, a compositor component
hidden under systemd, a notify service with an explicit Wayland socket, and a
session-target drop-in preserving the installed Pantheon support services.
The service retries unexpected exits after two seconds, capped at three starts
per minute, then requests the session shutdown target. It is repository-only
and has not been installed or runtime-qualified. The next gate is native-session
qualification in an isolated login, including socket/environment handoff,
ordinary apps, lock/logout and failure recovery.

The experimental compositor can now be deployed onto the existing stack beside
Gala with `mseries/install-pantheon-rust-compositor.sh` (dry run by default;
`--status`/`--verify` read-only; `--install`, `--select`, `--restore-gala`,
`--uninstall` need root and `--yes`). The Gala package, binary and
`pantheon-wayland` session entry are never modified, no unit is started or
enabled, and selecting the Rust session only rewrites the LightDM autologin
drop-in with a backup. `summarize-metrics.py` reduces the retained session
captures to per-process mean/median/min/max, and the public performance page
`docs/rust-compositor-performance.html` (linked from the build monitor)
publishes them with the honest status: idle compositor CPU is about 11.1 % of
one core in both sessions under unmatched workloads, whole-system power is
unmeasured, and no performance win is established.

The prototype now recognizes native libinput touchpad swipes for workspace
navigation and the overview: non-cancelled three-or-more-finger swipes that
pass a 90-logical-pixel threshold with horizontal dominance select the adjacent
workspace in the content-following direction and stop at the first/last
workspace, and an upward swipe of the same size toggles the grid overview.
Gestures are ignored while the session is locked or a move, resize or popup
grab is active; pinch gestures remain unrecognized. The state machine lives in
`rust/pantheon-compositor/src/gestures.rs` with unit tests; `cargo test -p
pantheon-compositor` passes, both default and `native-drm` builds check, and
clippy is clean.

`PerformAction(1)` no longer errors: it toggles a grid overview ("expose")
implemented in `rust/pantheon-compositor/src/overview.rs`. The mode arranges
each output's active-workspace windows into a centered grid inside the work
area, saves and restores plain, tiled, maximized and fullscreen arrangements,
focuses a clicked window and closes on Escape or a second toggle. A private
Xvfb/Winit D-Bus smoke with two GTK Wayland windows opened and closed the mode
and the compositor logged both transitions; the grid layout has unit tests.
Scaled thumbnails, animations, drag reorganization and native qualification
remain open.

The installed nested Winit backend never emits gesture events, so physical
M-series trackpad qualification, user-configurable bindings and where the
overview lands on the keyboard-accessible path remain open. Gala is still the
active session and no package was installed from this batch.

## CodexBar: Grok Build, upstream v0.78.0 and native CI — 2026-10-19

Done on `claude/codexbar-grok-production`: Grok Build card and local tokens; upstream pin v0.78.0
(restores Grok CLI billing); two use-after-free strings in the panel fixed with a generated-C guard;
one shared helper list for installers/deploy/image; native module and Xvfb probes in CI.
Follow-ups: live Grok usage check on the owner's account after install; first CI run of the
`codexbar-wingpanel` job on `ubuntu-26.04-arm`; incremental transcript offsets and `Indicator.vala`
card extraction remain from the [performance audit](CODEXBAR-PERFORMANCE-AUDIT-2026-10-18.md#next-measured-work).

## Release stages: F5 parity first, support assistants after — 2026-10-18

Owner's order:

1. **Stage 1 (gates v0.0.1):** F5 speech-to-text with the ease of macOS dictation
   ([#196](https://github.com/techmore/ElementaryOS_MSeries/issues/196)), plus the
   native elementary OS / Granite app audit
   ([#242](https://github.com/techmore/ElementaryOS_MSeries/issues/242)). Open
   gate: physical F5 in ChatGPT still fails (see the v0.0.1 F5 entry below).
2. **Stage 2:** support assistants on the shared Pantheon MCP broker, starting
   with troubleshooting ([#203](https://github.com/techmore/ElementaryOS_MSeries/issues/203),
   draft PR #185, disabled). Speech and Share eyes become clients of that broker.

v0.0.1 is cut (`dev` → `main`, see `mseries/BRANCHING.md`) only when stage 1 passes.

## v0.0.1 English F5 candidate; ChatGPT input correction staged — 2026-10-18

The owner narrowed v0.0.1 to English F5 speech to text on the existing M1 Pro
32 GB desktop; factory ISO, voice replies and diagnosis remain separate.
The fresh physical F5 check in ChatGPT FAILED: the key reached the listener,
but focused-field metadata was unavailable and it refused before microphone
capture. This is retained app-input failure evidence, not model WER. The earlier
seven installed routes and completed CPU/MLX comparisons are unchanged.

A reviewed per-user lowercase `chatgpt.desktop` override is now staged through
`dictation-launch.py --chromium`, enabling renderer accessibility and the IBus
environment at next full app launch. Seventeen launcher contracts pass, including
independent GLib quoting/spacing, URL/action preservation, owner-edit refusal and
private rollback. Desktop resolution selects that override. ChatGPT, listener,
input bridge and everyday4B were not restarted. No microphone/model was used.
A later owner retry also failed; read-only process metadata still shows the
original ChatGPT process without the new flags/environment. The fix has not
activated. Fully Quit, reopen from Applications, verify new process flags, then
physical F5 in the chat composer is the remaining acceptance gate. Preserve password/active-field guards.
The owner permits OS-level dictation integration; it is not a reason to type into
an unknown field. Native compositor input/broker work remains future development.

RC2 archive `d5c0e9b2…` is built from exact source `13a8b847ef3c754cbe37fe68686463bb2ec9f269`.
All 25 extracted-package/host checks passed. That exact head passed all seven CI
jobs in run `39157224321`. The source-only STT payload is now installed: all 16
runtime hashes and managers match, the transcript-only launcher is active for
its next invocation, strict CPU/IBus is ready, all seven debug overrides are
absent, native input preferences and everyday4B PID are preserved. One post-install
sample had 13,683,703,808 bytes available, maximum 2,489 RPM / 42.331 C. This was
static/readiness verification without microphone/model inference. It is not
physical F5 acceptance in ChatGPT. RC1's terminal-error idle refusal was fixed
without changing its retained receipt or any live status to obtain a pass.

Release worktree: `ElementaryOS_MSeries-f5-v001`, branch `release/f5-v0.0.1`.
Source-only deterministic Git-blob packaging, strict read-only preflight,
versioned rollback and a transcript-only UI are prepared. Native/ANE/MLX assets
stay available on the host but are not bundled or requalified. See
[release candidate instructions](releases/v0.0.1/README.md) and its sanitized
[receipts](releases/v0.0.1/receipts/). No v0.0.1 tag/release has been published.
Advanced diagnostic work is isolated on `feat/quiet-diagnostic-agent`, disabled
and not qualified; never add it to the STT artifact or use everyday4B for repairs.
The existing six-hour developer watcher continues; do not duplicate it or rerun
finished ASR benchmarks. Next: verify ChatGPT actually restarts with the staged flags, record the owner's
post-relaunch F5 result, then publish v0.0.1 only when that result passes. Preserve all owner main changes; one Git writer.

### Screenshot retention correction — 2026-10-21 (#227)

The shelf now always retains saved originals: non-cancelled drag completion is no
longer treated as proof that the target read/attached an image. Cards allow retry;
Copy/Show remain available. Replacement during an active drag defers cleanup,
and unique stage directories avoid same-name races. Only transient copies/portal
exports expire, two minutes after closing a card that offered a drag. Seven private
D-Bus/Xvfb GTK regressions pass; no live account, panel or desktop state changed.
See `screenshot-shelf/README.md`. Actual Signal compose-preview/content and display
boundary acceptance plus native Signal UI work remain open; do not close #227
from source tests alone.

## Signal Granite palette completeness — 2026-10-18

PR #222's Granite path now maps Signal brand/logo blue `#3b45fd` as well as the
UI color family. Three focused tests cover every system accent, fixed-width
asset replacement including uppercase logo colors, and custom-color fallback;
the validation workflow runs them. This fixes the reviewed regression without
claiming the broader native app or screenshot drag work in issue #227. No local
Signal installation, account migration or application restart was performed.

## Diagnostic entry armed once; no reboot — 2026-10-18

Owner explicitly authorized arming `elementary-aurora20-enh1-diagnostic` for one
boot, without rebooting. Verified image hashes and GRUB syntax first; then
`grub-reboot` set exactly that next_entry. Host still runs `.20`. GRUB clears
next_entry before launching the selected kernel; subsequent normal boots retain
`mseries-full-height` on `.20`. [Arming receipt](aurora/hardware-tests/2026-10-18-j314s-enh1-diagnostic-armed.json).
Watch the last initcall and mseries-boot stage markers; capture the last screen
if the trial stalls. Recovery: power off if unresponsive, then explicitly select
“elementary OS (M-series full-height desktop)” in the five-second GRUB menu.
No candidate boot result or fix is claimed yet. Do not reboot on the owner's behalf.

## Diagnostic candidate staged, no trial armed — 2026-10-18

PR #229 merged as `387d1ec`. The diagnostic image regenerated from merged source
matches `b7c6a3e74e1c90d4d5925551cdfa44d41e38f1e0f83d456c4a5eb1bea9dd8c35`
and is staged separately at
`/boot/initrd.img-7.1.12-elementary-aurora20-enh1-diagnostic`. A non-default manual
GRUB entry `elementary-aurora20-enh1-diagnostic` uses the existing candidate kernel
with initcall/debug logging arguments. GRUB syntax passes. The complete grubenv
bytes are unchanged and next_entry remains empty. Original candidate, working
.20 image/initramfs, shared boot.bin and generated grub.cfg hashes are unchanged.
[Staging receipt](aurora/hardware-tests/2026-10-18-j314s-enh1-diagnostic-staging.json)
records exact hashes and the private rollback directory. No reboot, trial arming
or hardware qualification. The owner must explicitly authorize the later test;
the cause of the original hang remains unknown.

## Candidate kernel boot hang: offline audit — 2026-10-18

Owner reports kernel messages followed by a hang before completing candidate
boot. Current host is back on `.20`; no retained candidate journal/pstore cause.
[Review](aurora/hardware-tests/2026-10-18-j314s-enh1-boot-hang.md) records unchanged
staged hashes, exact preserved unlock userspace, 93 matching candidate modules
and valid archive dependency references. No causal driver fault was established.
Added a read-only archive audit and a separate offline diagnostic initramfs
preparer with stage markers and preserved hook failure status. Real candidate
archive audit and generated shell syntax pass; five new regression tests pass.
No kernel/bootloader/module installation, boot selection change or reboot.
Next: review diagnostics before any separately authorized hardware trial; failed
candidate remains unqualified. The login-time capture cannot diagnose pre-login
hangs and QEMU without the required console driver was inconclusive.

## Native Share Eyes freshness follow-up — 2026-10-21

Source guard and synthetic regressions reject future/zero/missing launcher
heartbeats; 15-second freshness, clearing and recovery remain verified. Native
app/probe builds and private light/dark off-state renders pass. Not installed or
loaded. [Upstream/compatibility receipt](SHARE-EYES-FRESHNESS-2026-10-21.md) records
unchanged Torrential upstream and successful Signal module build; real tray,
sharing/device and next-load acceptance remain open.

## Screen-share real dock qualification — 2026-10-18

PR #225 was exercised with its real share server and GTK app on a private Gala
Wayland desktop with the actual patched elementary dock. The dock build had only
a read-only launcher observer to report widget state and render its icon to PNG.
The running launcher appeared; a pending viewer produced visible badge text 1
with opacity 1; admission cleared it; stop plus link revocation exited the app.
The original immediate present/minimize sequence left the window visible on
Wayland. Deferring initial minimize until the compositor has processed mapping
fixes that case; explicit activation cancels a pending initial minimize. Private
Gala now reports the window hidden at startup. Actual dock Super+1 activation
restores/focuses it, and Alt+F4 returns it to the dock. No owner desktop restart,
real screen capture or production server change was performed. This qualifies
the private Wayland dock path; factory boot and production Internet/LAN routing
remain separate acceptance work.

## PR #159 merge validation — 2026-10-18

Merged current main (including calendar PR #211) into the startup repair branch,
retaining both the startup report and all newer handoff/roadmap entries. On this
composed tree: 12 display-space Python tests, native notch/crowding allocation,
private actual-Gala startup test (old timeout reproduced, repaired timeout absent,
finite pre-surface sizing and 20 clock transitions), and six image-wiring tests
pass. New shell scripts pass ShellCheck; installer shell syntax passes. Non-patch
changes pass whitespace checks; unified patch context lines retain their required
leading spaces. No desktop installation or panel restart was performed in this
merge review. Fresh-login timing and owner visual acceptance remain pending.

## Aurora .20 top bar and startup repair — 2026-10-18

[Installed repair and tests](display-space/STARTUP-FIX-2026-10-18.md): Wingpanel
now requests a finite monitor width before its first surface/monitor event;
empty bars and clock reparenting no longer emit the tested GTK criticals. Migrated
stale cropped saved modes to full-height modes, preserving desk VRR and external
preferences. The deliberately disabled dock no longer counts toward Gala's panel
readiness. A nonfatal, board-guarded pre-start helper keeps stale modes from loading.
The patched panel is running. Native tests reproduce/remove the five-second
panel timeout and pass initial sizing plus 20 clock transitions; 12 Python tests
and existing native allocation checks pass. Fresh-login timing and owner visual
confirmation remain pending. Kernel, bootloader and dock-disabled state preserved.

## CodexBar inclusive15% quota display — 2026-10-18

Owner clarified that Claude must reveal the bold red written percentage at15%
as well as below it. The shared dot formatter now uses remaining<=15, preserving
consistent behavior across providers and both account rows.15.1% remains dot-only.
Dropdown quota bars and their percentage labels now share the dots' visual
thresholds: green >70%, yellow25–70%, red<25%. The underlying ETA/alert warning
thresholds remain separate. Native probes assert actual bar CSS matches remaining
quota in literal and dot modes. Hover/reset behavior is unchanged.
Boundary regression covers15%,15.1%,14%,10%,0% and missing values. Routine deploy
stages the native update for next login; no additional panel reload was requested.


## Claude pre-switch handoffs and reviewed GitHub backups — 2026-10-18

Added automatic handoffs for the most recently focused active local Code
conversation on cross-account desktop Switch (and first-time app sign-in setup).
After the app flushes/exits but before either login changes, the helper saves a
private brief from bounded recent visible transcript text and workspace Git status.
Thinking/signature/tool blocks are excluded. A fresh, tool-free Claude Code print
call uses the departing CLI account only when its identity matches the desktop;
otherwise, or on quota/network/timeout failure, a labeled emergency excerpt brief
is saved. The original conversation/transcript stays intact. The destination gets
a separate top-of-list Handoff conversation with a new transcript ID containing
only the plain-text brief, workspace bindings, and an original-conversation pointer.
No prompt starts work automatically and no thinking is claimed to cross organizations.
Same-account restarts do not spend tokens on another summary.

Private 0600 brief/receipt files live under codexbar-claude-app/handoffs, including
an immediately recoverable latest pointer before auth changes. Summary generation
is bounded to45 seconds,64K visible input characters and2400 output tokens; briefs
are lossy and explicitly say earlier details may be omitted. Source auth is never
copied into artifacts. The helper has no ambient polling or new service/database.

Owner chose each workspace's existing GitHub origin with reviewed public-safe
summaries. Publishing is deliberately separate from Switch: a native editable
review window requires an explicit Publish reviewed handoff action and writes a
new codex/handoff-* branch plus draft PR. No owner working-tree/index/main changes.
Emergency raw excerpts never prefill the public draft. Credential-pattern screening
is an additional check, not a substitute for owner review. Retrying publication can
reuse the same branch/PR; offline/failed publication retains the local handoff.
The success dialog offers Review GitHub handoff; the standalone command is
python3 ~/.local/lib/codexbar-cli/codexbar-claude.py handoff-review.

Verified: Claude Code2.1.299 live synthetic summarization with OAuth, safe mode,
no tools/hooks/MCP/session persistence; a separate live synthetic resume recalled
the task from the handoff-only seed. Owner conversations/accounts were not changed
for these tests. Review UI rendered under Xvfb; simulated publication remained
idle until the explicit click and received only edited review text.16 handoff tests,
41 switcher tests,15 history tests and deployment regression pass; all15 native
targets and full port check pass. Upstream CodexBar remains v0.77.0. Actual GitHub
publication awaits owner review by design; a live owner account switch with this
new handoff feature remains unverified. Native review-button changes install for
next login; helper changes apply on the next Switch. No panel reload is requested.


## Claude account switch and Code context live verification — 2026-10-18

Owner authorized switching from saved account1 to account2. The installed helper
matches main's explicit-desktop-switch fix. Both saved app sessions and history
preflights passed. The live combined switch stopped old main process72180 and
reopened Claude as524238; CLI and desktop identity hints matched the requested
target. Owner independently confirmed the correct main-UI account.

The operation exported/imported34 local Code conversations, with zero unavailable.
All 34 destination records, transcripts and workspace directories exist; session,
CLI transcript, cwd/originCwd, worktree and branch bindings match the source.
Claude's own post-start logs loaded13 active records from the exact target index
(nine imported plus four existing) and25 deferred archived records. Initial
existingSessions=0 is logged before disk loading and is not a rejection signal.
After clarification that the concern was the Code tab, owner confirmed the context
is working. Separate CSP conversations are not merged with imported conversations.

A read-only delegated loader review found no missing required schema fields or
hidden-record flag defect. Regular Chat/Projects and Cowork remain outside this
local Code import. An uncommitted optional automatic-focus experiment was removed:
its launch did not yield reliable focus confirmation. No speculative navigation
behavior is shipped. Production Claude helper40 and history15 tests pass.

No credential values or raw conversations were printed or added to the repository.
Wingpanel522634, Gala2678 and CodexBar daemon44641 remained running and healthy;
no panel reload was needed for this live Claude verification. Account2 remains
selected at the owner's request. The quiet crash watch continues.


## CodexBar compact rows grouped by account — 2026-10-18

Owner corrected the compact layout: the top row must contain multiple active
account values, rather than only 7D. In dot mode the active 5H and 7D indicators
now share the top row beside the provider mark; saved-account windows occupy the
bottom row. Token visibility still follows its independent dropdown preference.
Reset times stay hover-only. The same rule applies to all three providers, and
single-account providers do not add an empty bottom row. Literal mode is unchanged.

Native assertions check 5H/7D share a parent and alternate values appear below,
in addition to existing percentages/hover/height checks. All 15 native targets passed the row correction; the light fixture was visually
inspected before pushing. Owner then changed the numeric threshold: below 15%
the written percentage is shown in bold red; 15% and above remains dot-only.
Dot colors retain >70 green, 25–70 yellow, <25 red. Boundary tests cover 14/15. Owner's requested reload activated hover-only resets
as panel PID513013 with Gala2678 and daemon44641 unchanged; the layout correction
requires an additional reload under the same active request after deployment.
No provider app switching or unrelated changes are part of this correction.


## Claude desktop Switch no-op investigation and fix — 2026-10-18

Owner clarified that confirming Switch never closes/reopens the main Claude app.
A delegated investigation found the Indicator passes --desktop correctly and
installed process matching points at the running main app. Saved desktop bundles
have distinct non-expired session cookies; only sanitized identity/presence metadata
was inspected, with no credential values printed or live account changes.

Reproduced a concrete pre-stop no-op: app_switch returned early when config and
capture UUIDs matched the target, calling only the CLI switch. Those UUIDs derive
from lastKnownAccountUuid, a persisted hint rather than authenticated UI identity.
Removed that shortcut. An explicit desktop switch now validates the target, stops
the app, restores the pre-capture saved target, switches CLI if requested, and
relaunches even when local hints match. Existing rollback and history checks stay.
Regression verifies both app-only and combined flows restore the actual saved
cookie fixture and invoke stop/restore/(CLI)/launch. All 40 Claude helper tests and
15 history tests pass. No live Claude shutdown, switch, or session write was used
for investigation/testing. This faulty path is reproduced in isolation; attribution
to the owner's exact click and authenticated main-UI success remain unverified.
Next: owner retries Switch and confirms the main UI identity; do not infer that
identity from lastKnownAccountUuid or process existence alone.

Helper takes effect on the next Switch after routine deployment, without any
panel reload. Dot-mode hover-only reset code is installed but loads next login.
Quiet Wingpanel/Gala watch remains healthy (panel491179, Gala2678, daemon44641).


## CodexBar dot mode: reset details on hover — 2026-10-18

Dot mode now omits bar reset countdowns for active five-hour/weekly quotas and
alternate-account windows. Active-dot tooltips include the measured percentage
and reset countdown (or explicit unknown/due-now state); alternate hover retains
all window percentages and reset times. Literal mode and dropdown details keep
their existing reset preference. No polling changes or new preferences.

All 15 native targets pass, including no visible reset countdowns/arrows in dot
mode, reset details on active hover, critical numeric values and <=32px height.
Light compact rendering inspected: the same fixture's minimum width drops from
about 634px with countdowns to 368px without them. This is a fixture measurement,
not a promise for every account/provider combination. Upstream remains v0.77.0.
Routine deployment installs native changes for next login; no new panel reload
is requested by this batch. The existing quiet Wingpanel/Gala watch continues.


## CodexBar second-row dots — 2026-10-18

Owner requested matching visual dots for alternate accounts on the second row.
The bar now uses the same remaining-quota thresholds and below-10 numeric rule
for every saved-account window. Hover retains all account percentages and reset
countdowns; popup account rows remain literal. All 15 native targets pass, with
new assertions for alternate weekly dots and visible 5%/0% critical balances.
Dark rendering inspected. Push to main and deploy with one owner-requested reload
to activate this follow-up; the existing read-only stability watch continues.

## CodexBar account caching and compact display choices — 2026-10-18

OpenCode saved-account plans now cache for one hour and inactive-account quotas for
five minutes, with per-endpoint locks, reset-boundary expiry, retry backoff and
last-good stale results. Inventory is still read live from the read-only credential
DB; active quota stays owned by upstream. Opaque account/workspace/sign-in hashes
scope private 0600 JSON entries; credentials and raw provider replies are not saved.
Refresh explicitly bypasses both caches, including a click during an in-flight read.

Native Settings > Display adds Quota style (Literal percentages / Visual status
dots) and Token counts (Menu bar and dropdown / Dropdown only). Active five-hour
and weekly dots use remaining quota: green >70%, yellow 25–70%, red <25%; numbers
appear below 10%, and hover always reports the measured percentage. Literal mode
remains the default; dropdown quota details stay literal in either mode. Alternate account summaries use the same dots and retain all values on hover. Hidden bar tokens remain in all three
provider dropdowns. Logos shrink from 14 to 13 px. Weekly quota/reset stays on the
top row for Codex and Claude even when tokens are hidden.

Validation: all 15 native targets pass, including dense-dot boundary checks,
preference persistence, token visibility, hover text and <=32 px two-row rendering;
31 OpenCode helper tests cover TTLs, force, backoff, reset crossing, concurrent
misses, isolation/removal and cache sanitation. Light Settings and dark compact
renders inspected. Upstream remains v0.77.0. Owner requested main push and local
activation; deploy with one explicit reload after pushing. Prior panel PID432982,
Gala launcher PID2678 and daemon PID44641 were healthy in the read-only watch.
Commit 390f63f was pushed directly to main at the owner's request. Deployment
passed all 15 native targets and reloaded Wingpanel once: PID432982 → PID477816.
The short missing/recovered watch transition corresponds to that authorized reload,
not a crash. Gala PID2678 and CodexBar daemon PID44641 stayed running. Enabled
compactQuota=true and showTokens=false locally, preserving all other preferences.
Initial post-reload watch is healthy; the known empty-FlowBox startup warning
persists. The existing quiet watch continues; extended soak remains ongoing.


## CodexBar weekly quota beside top-row tokens — 2026-10-18

Owner clarified the top row must contain tokens AND the active seven-day percentage
and reset countdown for both ChatGPT/Codex and Claude. Added those weekly values
beside the token total; five-hour quota and alternate accounts stay below. Existing
percentage/reset preferences and missing-data behavior apply. The bar digest includes
weekly changes; the native probe verifies token/weekly percentage/reset share a row.
All 15 native targets pass; two-row height remains <=32 px. No polling changes.

The prior owner-requested single reload activated the previous build as PID 408824,
with daemon PID 44641 preserved. Both survived 120 seconds without a new coredump
or popup/accessibility errors. The known empty-FlowBox startup warning remains.
This correction is staged by routine deployment; no additional reload is issued.

## CodexBar: token totals lead ChatGPT/Codex and Claude — 2026-10-18

Moved those providers' seven-day token counts to the top row beside their marks.
Active quota/reset details and any alternate-account summaries share the lower row;
OpenCode retains its quota-first layout. Missing totals retain the existing fallback,
and display preferences/stale coloring remain respected. No helper or polling changes.
All 15 native targets pass; the token probe now asserts actual vertical label positions
for all three providers and the <=32 px two-row height. Light/dark and hidden-account
renders checked. Routine deployment stages this native layout for next login without
restarting Wingpanel; the quiet crash/launcher watch remains active.

## CodexBar performance/modularity audit and quiet stability watch — 2026-10-18

[Audit, evidence and remaining work](CODEXBAR-PERFORMANCE-AUDIT-2026-10-18.md).
Shared read-only OpenCode history now filters the 30-day window before JSON decoding
and streams period aggregation; no lifetime `fetchall`/record list. Synthetic unindexed
20,000-old/100-recent-row comparison: equal totals, 371.25 → 17.56 ms median under
tracemalloc, 46.96 → 0.01 MiB peak Python allocation. This is not a whole-panel benchmark.
Native `HelperProcess` centralizes bounded asynchronous read helpers (5s snapshot,
30s local, 120s account deadline, 4 MiB stdout); login/switch actions are excluded.
Helper completion repaints cached data without extra snapshot IPC; session rendering
uses already validated data. Common native source lists prevent probe/module drift.
Backoff exponent arithmetic is bounded; effective retry policy/cadence is unchanged.
Fifteen native targets, eight performance/watch regressions, helper/deployment and
six image-wiring tests pass; full v0.77.0 live port/schema check passes.

Installed `codexbar-wingpanel-watch.py`; this chat's “Watch Wingpanel stability”
heartbeat runs every five minutes, quiet while unchanged. It observes the panel and
Gala launcher, process identities/metrics and bounded categorized journal/core metadata;
no raw core, environment, journal text or credentials are persisted, and it cannot
restart the desktop. PID changes alone remain unclassified. No new core since the
prior popup fix. Panel PID 335310 / Gala PID 2678 stayed healthy through 80.2 seconds,
RSS 192,928 KiB, FDs 50; its earlier 14:23:25 restart has no crash attribution.
Routine deployment installs Python improvements for their next invocation and stages
the native performance changes for next login; no reload issued for this audit.
Next: normal-use monitoring, then scoped account caching and large-transcript benchmarks.

## CodexBar labels and confirmed popup lifetime defect — 2026-10-18

Removed “local” from the seven-day panel/card labels and moved counting scope into
Settings > About, using the native GTK About dialog. No polling or accounting changes.
Saved-core analysis found GTK flushing a destroyed popup surface (zero references,
NULL display). A pinned Wingpanel production-class fixture reproduces the matching
finalization/accessibility failure when an open indicator is removed before a switch
or close. The new lifetime patch keeps the previous anchor alive until detachment;
all four switch/close × animations on/off regression cases pass. The original fails.
The full patched Wingpanel build, 13 native CodexBar targets and v0.77.0 live port/schema
check pass. Existing full-height/notch and clock-right patches remain applied.
See [investigation and reproduction](CODEXBAR-CRASH-2026-10-18.md), including the
fixture setup limitation and why the exact original indicator remains unidentified.
Activated with one recovery `deploy-codexbar.sh --restart`; the patched core and
module inodes were verified loaded in Wingpanel PID 319737 throughout 63.4 seconds.
Daemon PID 44641 was preserved. No new coredump or popup/accessibility warnings;
one initial empty-FlowBox warning is recorded separately in the investigation.
Sampled RSS 194.72–199.19 MiB, descriptors 52–68, average CPU 1.21% of one core.
This bounded observation does not establish long-run stability. The panel and About
changes are active. Next: normal-use observation; do not reload again for routine deploys.

## Orchard soak closed with existing evidence — 2026-10-18

Final report: `docs/orchard-soak.html`; evidence and raw samples under
`mseries/orchard-incus/audit/2026-10-18-soak/`. The installed Python manager
(runtime hashes match merged `9747eb0`) ran on Wayland/Vulkan/blueberry for
99.36 minutes, seven cycles 15 minutes apart. All 70 developer operation groups
passed and owned guests were removed; the window closed before cycle eight.
This is **not** a completed two-hour qualification. The separate ordinary
window observer ended after 26 minutes and is not a full-duration control.

Using 87 minutes of settled inactive idle intervals (discard first 60 seconds
of each idle and last ten seconds before closure), app CPU averaged 0.1704%
of one core; reaped CLI children 0.0513% separately. Incus/VM/compositor costs
are excluded. Per-cycle idle CPU stayed 0.162–0.184%. Settled RSS medians rose
186.25 → 190.14 MiB (+3.89); private 69.22 → 74.77 (+5.55); PSS +0.33 MiB.
Output buffers returned to zero every cycle; rows/cards/histories stayed two,
read/timer slots two; GC-tracked objects fell 30,682 → 29,881. FD baseline moved
47 → 49, then 49–51 for the last three cycles. Small memory/descriptor growth
is observed, not attributed to a proven leak or dismissed as cache growth.

Three complete observed navigation probes: 18 actions each, p95 28.34/30.67/
30.77 ms; highest action delay 68.11 ms. A six-action partial probe retained
a 2,774 ms frame latency / 2,766 ms feedback gap. Three probes had unavailable
presentation feedback and failed in the old empty-median calculation. Causes
of sparse feedback, the large outlier and window closure remain unestablished;
these are programmatic GTK actions, not physical input-to-photon measurements.

Merged runner fixes explicitly classify absent/partial feedback, save each
probe before reporting failure, require action coverage/cycle count/duration
for a pass, and bound retries for transient Incus update-lock cleanup failures
with owned-name/creation-token checks on every retry. Scheduling and per-cycle
resource/frame receipts from the original soak extension are included. Removed
the proposed focus-raising option. The application runtime is unchanged.

Before the stop request: 123 Python tests, 117 passed and six opt-in tests
skipped, including six new frame-feedback cases. Final cleanup retry and
qualification bookkeeping are reviewed only; no further tests/CI, app launches
or desktop reloads are performed under the owner's explicit instruction.
The 4.5-second follow-up was cancelled; its busy-lock cleanup initially failed,
then the stop cleanup removed its sole owned fixture. All audit processes and
scheduled checks remain stopped. Next work requires a new owner request; do
not restart soak testing, raise windows or reload the panel automatically.


## Screenshot login repair — 2026-10-18

Fixed invalid `%h` Exec paths preventing screenshot shelf and Markup startup; installed and validated
absolute paths. Synthetic screenshot triggers thumbnail and four-second expiry. Rebuilt private Gala
from main to actually install Space/highlight code. Next login loads it; highlight, shutter playback
and real drag-out still await live verification. Recovery: [shelf README](screenshot-shelf/README.md).

## English F5 deployed; reuse canonical evidence — 2026-10-18

[Acceptance/deployment record](dictation/F5-ENGLISH-ACCEPTANCE.md) and
[canonical qualification ledger](dictation/QUALIFICATION-INDEX.md) supersede older
next-step lists. PR155 merged at5c26ff6 and the reviewed English payload is active:
CPU Nemotron4threads, stable words during speech, strict IBus, preserved toggle
and input settings. Native ANE/Parakeet MLX remain selectable; residency is bounded
and pressure-sensitive. Resident sustained MLX did not catch up to live audio.

All retained model/app/voice cohorts are terminal. Seven installed routes passed:
one GTK4 public-file ASR, GTK3/Qt6/Brave fixtures, and Code/Newelle/Tasks lease/cancel
fixtures (positive ASR remains in earlier pinned cohorts). Three missing-argument
setup failures remain; only unstarted fixtures resumed. Samples retained10.48GiB
at≤2530RPM/49.01C; post-fixture readiness/preservation passed. Never repeat completed
trials for scores, a new checkout or missing telemetry. Receipts/source identities
are indexed; future work begins there. Final docs publication is verified after
its merge in its PR body/task output.

Separate gaps: fresh human microphone/F5 acceptance, native Calendar GUI/reminders,
authenticated Gmail, natural/full-duplex voice, indefinite soak, power/battery and
factory boot. Permanent developer tracking stays on the existing six-hour workflow.

## CodexBar deployment follow-up: avoid unchanged icon invalidation — 2026-10-18

The local-token change was activated with one requested reload and passed its first 61-second
observation. Later routine post-push deployments produced GTK popover/accessibility warnings at
14:02:56 and 14:03:08, exactly when identical provider marks were reinstalled and the global icon cache
refreshed. Wingpanel PID 233125 then SIGSEGVed in libgtk-4 at 14:03:09 and auto-recovered as 248867.
This is a confirmed crash, not an intentional second reload. The stack does not prove which widget
owned the bad popover, so the relationship to icon invalidation remains an inference.
Deploy now byte-compares provider icons and refreshes the global icon cache only when a mark changes.
This removes unnecessary live icon-theme invalidation during code/docs-only deploys. Stubbed deployment
tests verify no icon/cache writes for identical marks, a single cache refresh for changed marks, and
unchanged explicit-only panel reload behavior. Native token code is unchanged; no second intentional
reload is needed. Quiet-path verification: all 13 native targets passed; no icon-cache command was invoked for
unchanged SVGs. Recovered Wingpanel PID 248867 and daemon PID 44641 remained unchanged during
61.1 seconds of observation, with no new panel journal messages. Sampled median CPU
0.39%, RSS 193.55–248.36 MiB, descriptors 52–106;
this is a short survival check, not proof of leak freedom or a resolved GTK root cause. The installed
sessions helper confirms non-negative seven-day totals for all three applications. Counts remain active.
No additional intentional menu-bar reload was issued.

## Seven-day local tokens for all three providers — 2026-10-18

Added `7d local` processed-token totals for Codex, Claude Code and OpenCode in the two-row panel.
Counts sit beside alternate-account summaries when present; the tooltip explains machine-local scope,
all local accounts/providers, cache inclusion and separation from account quota. All three now use the
sessions helper rather than mixing OpenCode Go-only cost data with whole-application activity.
Codex indexes active/archived JSONL token events, ignores repeated cumulative counters, deduplicates
copied history by usage-event fingerprint, and uses last-call usage (or differences after a baseline),
never a recent thread's lifetime sum. Claude now includes cache reads; its v2 cache invalidates old
excluded-cache answers. Shared `codexbar_tokens.py` accounts for provider-specific disjoint fields:
Codex authoritative total/input+output without adding cached/reasoning subsets again; Claude's four
input/output/cache categories; OpenCode authoritative total or disjoint components. Both OpenCode
readers share that function. Installers, deploy, image payload and deployment fixture ship the module.

No new network requests or polling cadence changes. Only changed transcript files are reparsed;
private caches store usage metadata, not transcript messages. A real-data first read took 1.608s,
then 0.188s with existing caches (one active transcript changed during the run). Thirteen native Meson
targets pass, including a real three-provider panel assertion and <=32 px height check; helper tests
cover identical processed totals, duplicate/archive events, resets, malformed data, cache reuse and
append invalidation. Full port check validates upstream v0.77.0 and live snapshot schema.
Owner-authorized activation completed with exactly one `deploy-codexbar.sh --restart`.
Confirmed installed module inode 320944 was loaded; Wingpanel PID 233125 stayed unchanged
for 61.0 seconds, CodexBar daemon PID 44641 preserved. No new panel journal messages or
coredumps since activation, sampled CPU median 0.30%, RSS 165.33–169.2 MiB,
file descriptors fixed at 49. Both native typography and local token changes are active. No real
account switch performed; long-run behavior and owner visual confirmation remain outside this smoke check.


## RepoBar account cache isolation — 2026-10-21

Follow-up to #414: follow-CLI mode resolves and pins the active stored CLI account
for each helper process, including worker requests. Snapshot and endpoint caches
require the resolved host/login; inherited token overrides cannot select another
identity. Unknown/signed-out accounts fail closed; validated same-account stale
snapshots remain available. The indicator no longer reads raw disk snapshots,
discards responses spanning settings changes and clears account-derived state on
terminal helper errors. No live panel restart or deployment.

Checks: 18 fake-CLI regressions; native indicator/module/settings build; two private
D-Bus/Xvfb account probes (late old-account response and prior account + helper
failure); light/dark healthy/offline renders; strict size lint. CI now exercises
the native probes. Actual second-account login remains owner acceptance. #414 was
merged independently before this follow-up was published; this patch is separate.

## RepoBar UX pass 2 — 2026-10-18

20-repo scrolling dashboard with Show all, native RepoBar Settings window, keyboard navigation and shortcuts, undo
toasts, remembered tab. Next: confirm on the live panel after a reload.

## RepoBar native UI pass — 2026-10-18

RepoBar's popover now matches CodexBar (switcher, status-dot cards, pills, details chips, icon dock, state pages);
headless probe + `deploy-repobar.sh` added. Next: confirm on the live panel after a panel reload.

## RepoBar port in progress — 2026-10-18

The optional elementary OS port now has a native GTK/Wingpanel dashboard with
search, dashboard/all/pinned/issue/PR/attention/local views, pin/hide controls,
CI, release and recent activity summaries, API quota status, a CLI, private
caches, and bounded local checkout scanning. Repository cards include nested,
lazy-loaded detail sections for issues, pull requests, CI, releases, activity,
commits, branches, and tags. Search includes repository topics. Local sync
requires explicit `--yes`, a clean attached branch, and fast-forward-only. The
installer remains optional and uses the existing GitHub CLI login. The dashboard
was installed and activated in the live Pantheon session on 2026-10-18; the
module loaded and the indicator toggle opened. An authenticated refresh returned
85 repositories. The live query bug was fixed by using valid connection
arguments and smaller pages. PR #175 is merged and active in the current desktop
session; the new module was loaded after one Wingpanel restart, and the installed
helper returned data from all eight detail categories. The panel uses a bundled
GitHub symbolic mark; GTK resolves it from the hicolor theme with current-theme
tinting. UI parity follow-ups include
traffic/cloner views, a heatmap visualization, multi-account controls, and
launch-at-login settings. The Wingpanel styling now matches CodexBar's compact
elementary OS typography, card surfaces, and rounded action dock. Repository
cards also show default-branch commit counts over rolling 1-hour, 24-hour, and
30-day windows from the cached snapshot. The helper and module build/install
completed, and a live refresh returned counts for all 85 repositories. The
updated module is installed but no panel reload was performed, so its revised
appearance and counts will load at the next login or later reload. See
`mseries/REPOBAR-PORT.md`.

## Consistent CodexBar panel typography — 2026-10-18

Owner approved the compact OpenCode appearance and requested the same text sizes for Codex/Claude.
Promoted the OpenCode sizes into shared panel styles: primary values 7.5 pt, reset countdowns 7 pt,
secondary rows 6.75 pt. Removed provider-specific font overrides; popover text is unchanged.
Verified native light/dark render probes with all three providers, including alternate accounts;
the routine deploy also builds and runs all 12 native targets. Upstream stays v0.77.0.
Installed/staged without restarting Wingpanel; native appearance loads at next login or an explicit reload.

## Compact two-row OpenCode panel — 2026-10-18

Owner requested denser OpenCode information in the desktop bar. The active OpenCode quota/reset
uses 7.5/7 pt text and 2 px spacing; its second row uses 6.75 pt text. With one saved account,
move the machine-wide seven-day token count below the quota instead of appending it to the top row.
With alternate accounts, retain their quota row and keep local tokens in the full tooltip/popover.
The token count participates in the panel digest so cached local updates refresh the lower row.
Existing percentage/reset/account visibility preferences remain respected; no polling changes.
Verified: native build, all 12 Meson targets, isolated light/dark render probes for single/alternate
OpenCode accounts. Upstream remains v0.77.0. Deploy stages the module without restarting Wingpanel;
this appearance change loads at next login or an explicitly requested reload. Live appearance pending.

## CodexBar fixes activated and observed live — 2026-10-18

Owner explicitly requested one menu-bar reload. Ran `bash mseries/deploy-codexbar.sh --restart`
from the reviewed audit sources; all 12 native targets passed before installation. Our one reload
activated the defensive JSON fixes and preserved CodexBar daemon PID 44641. `/proc/<pid>/maps`
matched the installed `libcodexbar.so` inode (320683), rather than the previous deleted mapping.
Two subsequent observation windows were interrupted by separate Bluetooth control installation/reload
work; no Wingpanel coredump was recorded. No additional reload was issued by this task.

Final uninterrupted live window: 182.7 seconds, Wingpanel PID 125428 unchanged,
daemon PID 44641 unchanged, loaded module checked throughout. RSS 166.53–170.89 MiB,
median sampled CPU 0.39%, file descriptors fixed at 49. No new journal messages for this
panel during the window and no Wingpanel coredumps since activation. Read-only live snapshot:
schema 1, two providers/four quota windows, not stale or busy, zero provider errors. All PR #164
CI checks passed. This verifies activation and short-run polling survival; long-run behavior and
owner interaction with the live popover/account switches remain unverified. No real account changed.

## CodexBar defensive data audit — 2026-10-18

Audited the native indicator's delayed callbacks, async parameter ownership, JSON ingress/rendering,
widget/JSON references, helper process targeting and polling guards. Generated C confirms the remaining
string captures and post-yield dialog titles are copied; no additional dangling-array use was found.
The concrete unsafe boundary was nested helper/snapshot data: null session/account/window elements and
wrong scalar types reached native renderers. Added shared `JsonBoundary` validation at every external
JSON ingress and checked optional getters in the indicator, presentation and quota code. Rejects wrong
collection elements/types, excessive depth (>24) and traversal (>20,000 nodes), while preserving nullable
optional fields and unknown keys. No extra polling. Claude Switch now also requires a successful helper
exit, rather than trusting an `ok:true` reply from a failed process.

Verified: old indicator aborts under fatal-critical ingestion probe (`build_session: session != NULL`);
new code rejects seven malformed snapshot replies, tolerates malformed helper collections, and recovers
on valid data with no GLib criticals. Five Switch interactions include Claude `ok:true` plus exit 1.
Twelve native Meson targets and `bash mseries/check-codexbar-port.sh` pass. Upstream pin stays v0.77.0.
Routine deploy stages the native module without reloading Wingpanel; changes load at next login.
No real sign-in or account switch exercised. Follow-up: owner smoke-test after next login; native code
still shares Wingpanel's process, so regression tests reduce risk rather than providing crash isolation.

## Historical English streaming benchmark checkpoint — 2026-10-18

[Completed benchmark and upstream audit](dictation/REALTIME-ENGLISH.md): Nemotron160
CPU first draft0.851s median, MLX Vulkan1.452s, native ANE2.97s warm committed
words (different policies). All final words match on the principal clean clip;
Moonshine errors and the original unsupported Nemotron GGUF remain retained.
Three extra speakers passed the small Nemotron/Unified comparison. Real private
GTK4 English-only words/grammar workflow passed. No new mic or owner windows.
At this checkpoint F5 integration/lifecycle were still pending. They are now
merged/deployed and qualified as recorded at the top of this roadmap and in the
canonical ledger. Fresh human microphone acceptance remains separate; do not
repeat the completed benchmark or treat this historical list as next work.

## CodexBar Switch crash and disruptive deployment — 2026-10-18

Confirmed real Wingpanel SIGSEGV at 12:59:20 in `switch_codex_account_co` from `libcodexbar.so`.
Reproduced with the current indicator in an isolated Xvfb Switch interaction: confirmation captured a borrowed
argument array after its originating row callback had freed it. Replaced the array with an owned scalar account ID
through confirmation and async execution. Invalid JSON helper replies are now rejected without object dereferences.
The same interaction now passes for success, null, array and invalid replies, preserving the exact chosen account.

Separately, our deploys intentionally restarted the whole panel at 13:21:50 and 13:22:21; later reloads coincide with
other indicator installs. Routine `deploy-codexbar.sh` now installs without restarting Wingpanel or CodexBar;
`--restart` explicitly reloads Wingpanel and never quits a running CodexBar daemon. Helper updates take effect on
next invocation; native module changes wait for login or that explicit reload. Working agreement updated accordingly.
Verified: reproducer SIGSEGV before fix; four successful headless interaction cases after fix; stubbed deployment
checks default/--no-restart/--restart and invalid options without signaling real processes. All nine Meson targets
pass, including four registered Switch interaction cases. Applied one controlled reload to activate the crash fix;
the existing CodexBar daemon PID 44641 was preserved. No Claude/ChatGPT account was changed in testing.


## Claude Code history across desktop account switches — 2026-10-18

Root cause: transcripts persist in `~/.claude/projects`, but the desktop Code sidebar is account/organization scoped.
New `codexbar_claude_history.py` privately exports the departing local Code history after the app exits, then adds
only missing resume entries under the selected account/org before launch. IDs and workspace paths are preserved;
existing records/transcripts are never overwritten. Backups include checksummed transcript bytes, reused by content.
No regular Chat-tab/Cowork/cloud history import and no automatic message sending. The confirmation explains local
Code context carry-over, and the result reports added/existing/unavailable counts. All installers/deploy and the
image payload ship the module (payload also now includes the already-required cache/sessions helpers).
[Evidence, storage, recovery and limitations](CODEXBAR-CLAUDE-HISTORY.md). Upstream remains v0.77.0.
Verified: isolated history tests and Claude lifecycle tests; staged rehearsal of 38 real local records copied 34,
then zero duplicates, then four back while retaining 34 existing; no live profile changes. Live desktop switch and
opening a transferred conversation remain unverified. Next: owner switches once and resumes a prior Code workspace.

## Orchard panel: icon and running-instance count — 2026-10-18

Removed the CPU/memory circles from the native Vala Wingpanel companion.
The panel display now contains exactly the Orchard tree icon and running-instance
badge (including zero; a dash still means Incus is unavailable). CPU/memory
captions and bounded graphs remain available in the popover. Removed the unused
ring widget and its periodic `/proc/meminfo` read. Updated the source-pinned
parity ledger to describe this owner-requested adaptation.

Verification: native ARM64 build and all five Meson suites pass; the panel
fixture also passes explicitly on Wayland through counts 2 → 0 → 0 → — → 1,
asserting no third display widget throughout. Installed only `liborchard-incus.so`
atomically and reloaded Wingpanel. The live accessibility tree contains one
image and one label (`2`), matching the two running Incus guests; the loaded
module's SHA256 matches the tested build. Manager windows/guests were not changed.
Evidence: `mseries/orchard-incus-native/audit/2026-10-18-panel-icon-count.json`.
This panel check is separate from the Python manager's unfinished multi-hour soak.


## Dock hotplug/startup findings and obsolete module cleanup — 2026-10-18

[Follow-up report](aurora/hardware-tests/2026-10-18-j314s-hotplug-and-module-cleanup.md)
records the owner's audio-after-replug, initially stretched top bar and startup
delay reports on running Aurora `.20`. Logs show a rejected saved 3024x1890 mode
against current 3024x1964 full-height modes, a panel startup timeout, USB/Thunderbolt
hotplug faults and missing dock Ethernet firmware. Audio causality remains unverified.
Archived and content-verified 5,771 files before removing orphan `.19` and two
Fairydust module trees; kept running `.20`, installed `.20-enh1` and stock Asahi.
GRUB syntax checks pass; no boot, display or audio configuration changes. Earlier
scoped visual/VRR results stand; symptoms and sustained stability remain open.
Next: capture active/saved display profiles, identify the late panel, and collect
before/after hotplug audio and kernel state. Cleanup is not a symptom fix.

## Native CodexBar display preferences — 2026-10-18

Settings (gear in the popover) > Display > Wingpanel now has switches for quota percentages, time until reset,
other accounts in the bar and account hints. Percentages/countdowns affect bar and quota text; progress bars,
tooltips and accessible quota descriptions retain the data. Both off gives provider icons in the bar.
Preferences save immediately in `~/.config/codexbar/wingpanel.json`, separate from upstream's config; the panel
watches for changes and re-renders cached data without extra snapshot/provider requests. Defaults preserve the
existing display. Upstream pin remains v0.77.0; no upstream files replaced.
Verified: five Vala test targets; light/dark headless Settings and panel renders; live atomic-replacement test
(`ninja -C BUILD test-live-preferences && bash mseries/codexbar-wingpanel/probe/run-live-preferences.sh BUILD`)
updates the bar off/on without additional snapshot requests. Not yet owner-tested on the real desktop.


## CodexBar Switch targets the provider app — 2026-10-18

ChatGPT Switch now confirms the selected account before changes, closes only the owner's ChatGPT executable,
saves its final login, installs the selected saved login under the account lock, and relaunches ChatGPT.
A close failure leaves the login untouched; a launch failure reports that the login changed and asks for a manual open.
Claude's installed-app Switch now switches both the app and CLI, or offers first-time app sign-in setup.
The switching paths do not quit CodexBar. Deployment still restarts Wingpanel/CodexBar to load the new code.
Verified: isolated account lifecycle tests, Claude and cache suites, native panel build and four Vala tests.
Unverified: live desktop account switch; apps were not closed during testing. OpenCode switching still uses its
existing CLI credential selection; desktop account synchronization is not established by this change.


## Screenshots: Space window mode and 4 s shelf — 2026-10-18

Command+Shift+4 drags an area; Space switches to window mode (blue highlight, click captures, shutter sound);
the fixed 280x180 thumbnail floats bottom-right for 4 s. Code is on main (`patches/gala-screenshot-window-pick.patch`,
`screenshot-shelf/`, details in [screenshot-shelf/README.md](screenshot-shelf/README.md)). **Next:** owner re-logs in
so the patched Gala loads, then confirms highlight, sound and thumbnail; not yet seen working live.

## Week/Day time-grid views — 2026-10-18

Published and deployed native hourly/half-hour slots, all-day bands, overlap
lanes, midnight clipping, bounded scrolling and readable block detail popovers.
Upcoming/Month lists and main's task quick-add/checkbox completion are retained.
Fixed UTC day filtering, explicit DURATION handling and untitled-event logging;
month navigation now avoids stale carousel callbacks. Native Calendar launch
appears only when its client is available; event views remain read-only.

All 21 combined integration groups pass in light/dark and against the installed
library; six image-wiring tests and focused shell/whitespace checks pass. Native
ARM64 build, synthetic rendered previews and reloaded Wingpanel mapping verified.
Next: owner acceptance on real calendars and physical touch/scale, with remote
sync and factory boot qualification still separate.
[Time-grid behavior and tests](calendar/README.md#month-week-and-day-views).

## Factory YouTube ISO: installed VM pass — 2026-10-18

The new ISO from `5c0c60e` built successfully in run `39128555434`, passed its
independent checksum, installed to a blank virtual disk and booted without the
ISO. Bundled Brave, its runtime libraries, the system YouTube logo and the running
dock application identity passed. Anonymous video/audio decoding advanced at
480p and selected 1080p with an empty browser profile; the guest screenshot shows
the playing movie and YouTube dock logo. [Measurements and exact artifact](video-decode/receipts/factory-2026-10-18/README.md).
Apple physical boot, V4L2 decoding and DRM remain separate hardware gates.

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

**Verse of the Day + tab (2026-10-18).** A third **+** tab beside Events/Tasks
shows a daily World English Bible verse (400-verse public-domain list, seeded
per-year shuffle, no repeats within a year) with SermonAudio, YouTube sermon and
Bible Gateway links, laid out with Granite/Wingpanel widgets. 22/22 private
fixture groups pass in light and dark; the patch applies to the pin and rebuilds
byte-identically. See [calendar/README.md](calendar/README.md#verse-of-the-day--tab).

**Bible tab production readiness (2026-10-19).** The calendar panel (agenda,
Tasks, Bible tab with daily verse and Titus study) is now a third pilot package,
`mseries-wingpanel-datetime`. It is version-gated to datetime 2.4.2, diverts
the stock plugin so daily upgrades can't overwrite it, and ships the accounts
launcher. CI builds it, checks the bundled data and runs the private-EDS suite
against the packaged library. The arrow buttons got accessible names.
The owner's desktop now runs the package (0mseries2). CI proves for all three
pilot packages that a stock upgrade can't overwrite ours and that removal
restores the stock plugin (2026-10-20). Remaining: apt publishing (signing key,
#52).


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
| Network indicator speed, connected-only Wi-Fi list, and usage views | Connected Ethernet now uses a socket glyph at 59.19424171875000% size, including the VPN lock variant (October 18). Panel rates below 1 MB/s now display `<1 MB/s`; Hover over the icon/readout to reveal measured values (Command optional; built and installed October 18; GTK interaction check passed, live visual check pending). Installed on the M1 Pro; user `netusage` service is active. Manual post-install includes the panel module and user logger. Overlay now includes the matching panel package for version-gated plugin compilation, then preserves the plugin. | Rebuild the image and verify the plugin loads against the final panel; check joined-network collapse, chevron expansion, and menu rendering. |
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
| Emporia elementary desktop client | Installed and live (2026-10-18) on the authenticated HTTPS origin with this device's enrolled credentials; no local poller. The Wingpanel Temperatures view has an overview, warnings and a sortable sensor list with trends and sparklines; the 3D house hues each room by temperature. SER8 collector on 2.3.64 with a verified rollback backup (see handoff). | Owner check of hover and click in the live popover; later collector releases use the same backup-and-switch process. |

## Open problems

Owner boot policy: use the installed Fairydust USB4 kernel by default and retain
stock Asahi for recovery. Apply with
`sudo bash mseries/fairydust/usb4/set-default-kernel.sh --apply`; the stock boot
on October 14 did not enumerate the dock's mouse or Ethernet.

| Problem | Why | Next step |
|---|---|---|
| **Built-in display dims unexpectedly** (owner-reported urgent bug, 2026-10-14) | The user installer disables ambient screen adjustment and idle dimming, and the image enhancement layer supplies the same defaults to new sessions. Manual brightness, blanking, and suspend remain available. | Apply the brightness stage, then confirm on AC/battery and through suspend/resume. If brightness still changes, capture the backlight value and related power-service logs. Cause remains unconfirmed. |
| Homeboard elementary Tasks sync bridge | Production bridge (`techmore/homeboard`, pinned in `mseries/install-homeboard-sync.sh`) installed and running in the background on this desktop (2026-10-19): auto-restart, D-Bus activation, upgrade/uninstall, back-off, keyring timeout, journal logs. Calendar agenda tests run in CI. Status: signed out. | Owner chooses **Sign In…** in the calendar's Tasks tab and completes Google sign-in; then confirm a round trip (tick in the dropdown → Homeboard within seconds, and a Homeboard edit back within a minute). |
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
0. **Lid open shows the login screen, with Touch ID.** Today the login needs a power-button press after resume (bug tracked in `BUG-FIX-ROADMAP.md`). First fix the wake path; then investigate fingerprint login. Aurora's `apple_sep` driver now attaches on this Mac and an enrolment completes in the enclave, but the xART guard blocks matching until the owner decides about `xart_guard=0` (see `aurora-sep/XART-GUARD.md`); the Settings page is installed.

1. **Dock video via m1n1 hypervisor trace.** Needs a second computer (below). Result would also help every Asahi user.
2. ~~**Panel toggle for the battery charge limit**~~ Done 2026-10-13: a switch in the gear menu (`quick-settings/ChargeLimit.vala`, polkit action in `power/`). Pending your click-through: check `charge-limit-toggle`.
2a. **Bluetooth in Quick Settings:** the far-right gear menu now includes a radio switch, saved-device Connect/Disconnect controls and pairing-settings link; the duplicate standalone Bluetooth bar icon is hidden while background services and the greeter remain. Full plugin build and private BlueZ integration test pass; installed and activated with the owner-approved Wingpanel reload; live interaction remains for the owner.

2b. **Sound Output switcher and AirPlay destinations** Built 2026-10-16, merged 2026-10-18: a Mac-style output list in the gear menu (`quick-settings/AudioOutput*.vala`) with a dot per AirPlay receiver (`quick-settings/AirPlayOutputs.vala`, `airplay/`). Discovery through `install-airplay-discovery.sh`, the helper through `install-airplay-outputs.sh`. Headless tests pass; audible AirPlay and the live panel are not verified.
3. ~~**Docked lid mode**~~ Done 2026-10-13: `install-docked-lid.sh` (user service). Real lid close pending: check `docked-lid-works`.
4. ~~**Linux VMs with KVM**~~ Guide written 2026-10-13: [`KVM-VMS.md`](KVM-VMS.md) (boot verified headless; graphics, networking address and benchmark overhead not yet measured). Scripted end to end 2026-10-16: [`vms/mseries-vm`](vms/README.md) creates, fetches media for and runs the guests (elementary OS, Windows 11 ARM64, Omarchy 4), with a 71-check hermetic suite in CI.
5. **Publish benchmark history** for every kernel/Mesa update, plot trends.
6. **Install media / transform script** for other M1/M2 Macs (see `TRANSFORM-DESIGN.md`).
7. **Tether continuity add-on**: pinned, removable ARM64 package installer and optional Brave integration are implemented (merged to main 2026-10-14); iPhone/Brave qualification remains. Current BlueZ 5.85 is below Tether's 5.86 minimum for Messages. See [`TETHER-CONTINUITY.md`](TETHER-CONTINUITY.md).
8. **Native battery time-to-full:** battery menu also has a persistent Show Watts in Menu Bar toggle (October 18); implemented as an optional patch and installer for elementary's Power indicator; built and installed on the M1 desktop. See [`BATTERY-ETA.md`](BATTERY-ETA.md).
9. **Torrential ARM64 native app port and optimization.** Native GTK/Granite
    package installed on the desktop; official Ubuntu torrent data transfer
    and full-ISO SHA-256 verified; RPC pause/resume checks passed. UI interaction,
    close/reopen state restoration, and measured optimization remain. Upstream source and packages stay local pending a
    license grant. See [`TORRENTIAL-PORT.md`](TORRENTIAL-PORT.md).
10. **Report upstream bugs** (Wingpanel crash: draft in `upstream/`). ~~PipeWire missing LV2 plugin in Ubuntu~~: not a bug. Ubuntu ships `libspa-filter-graph-plugin-lv2.so` in `libspa-0.2-modules-extra` (checked 2026-10-13, 1.6.2-1ubuntu1.2, the same version as the installed PipeWire). The notes saying Ubuntu omits it missed that package. Next step: install it instead of building the plugin in `install-pipewire-lv2.sh`, and add it to the factory image. Not yet tested with the Asahi audio chain.

Not realistic here: macOS 27 guests (`MACOS-VM.md`). M4 Mac mini is a separate
research port: Gravity Linux publishes a developer alpha reporting HDMI/DCP and
GPU support. Its matched kernel/Mesa/bootloader stack is pinned in
`m4-mini/research.json`; elementary integration and this owner’s J773g dual boot
remain unqualified. See `m4-mini/GRAVITY-INTEGRATION.md`.

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

- Phosphene feasibility (October 19): reviewed v4.19.5 / `287a964` for the 32 GB M1 Pro and elementary OS Vulkan MLX stack. Linux Apple Silicon is community/best-effort, but the checked installer still gates on Darwin/ARM64; MLX video operations are not qualified on our Vulkan fork. Advanced modes need 48 GB and compact-Q8 Hailuo is listed at 36 GB+, so a port is not a priority. No install or render test. [Assessment](local-ai/PHOSPHENE-FEASIBILITY-2026-10-19.md).
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
- Deployment follow-through (October18): qualified lazy CPU speech/IBus and Dictation launcher installed after idle/quiet/pref checks. Fresh listener32.67MiB before SDK load; not after-use memory. Owner reports physical F5 speech appears in Original transcript: native-app human pass, earlier popup failure retained. New installed focus-retry regression failed then passed after fix; receipts retain both and installed-source checks.46 contracts pass. Real spoken content/private backups excluded. Continuous translated previews and final grammar-after-release remain the next work; current translation is post-utterance.


## Optional Apple Passwords experiment — 2026-10-18

Added `install-icloud-passwords.sh --experimental`, a per-user opt-in installer
and three application launchers. Default first-boot behavior stays disabled;
`enhance.sh` ships the installer/public key only. Pinned upstream client
916ef17a5a14965f353d556a53ca3eedc1439113 and ARM64 anisette image digest;
rootless user service binds localhost and persists its identity volume.
Brave receives a stable Chromium MV3 extension manifest and native-host registration.
Keyring failure is fatal instead of falling back to a disk master key.

Locally installed and reinstallation checked; helper HTTP/JSON and isolated
empty-vault native ping pass. Keyring is unlocked and listener is loopback-only.
92 upstream tests + 11 subtests, three integration contracts, shell syntax and
shellcheck pass. No Apple account credentials entered or real vault inspected.
Owner must load the extension once in Brave, then sign in directly via the
Set Up Apple Passwords launcher. Account recovery, actual sync/autofill, ADP,
reboot and factory-image behavior remain unverified. See
[setup, limitations, disable steps and source pins](icloud-passwords/README.md).


### Apple Passwords native GTK/Granite onboarding and -80045 follow-up

Owner requested a native elementary GUI after GSA init returned -80045. Added
GTK4/Granite7 sign-in, private pipe worker, 2FA/device selection, unchecked explicit
recovery consent, search/reveal, Sync Now and local sign-out. The UI blocks closing
or cancellation while an irreversible recovery request is in flight. Password
retention is opt-in; credentials never enter process argv/environment or logs.
Installed a single native Applications entry, retired the terminal setup/sync entries
and opened the GUI locally. Default feature opt-in boundary remains unchanged.

Applied the reported endpoint-specific identity workaround from Dadoum/anisette-v3-server#61
without resetting the client/helper identity. Enforced TLS verification across GSA,
iCloud and web auth, with fingerprint-pinned Apple PKI roots in an app-scoped CA
bundle; system trust unchanged. Verified GSA/setup/idmsa TLS using credential-free
GETs. Added safe GSA transport/non-plist errors.

Validation: ten GUI/IPC/keyring/CA-pin tests, four mocked endpoint/TLS/consent tests,
129 upstream tests + 11 subtests; the one obsolete Mac-escrow-header assertion is
superseded by the port endpoint test. Installer repeat, shell syntax and compilation
pass. First owner attempt never reached passcode recovery. No agent login attempted;
actual compatibility fix, account recovery, sync/autofill and factory boot remain
unverified pending owner testing in the native app. Details: icloud-passwords/README.md.


### Approval/code waiting fix — 2026-10-18

Owner reports phone approval arrives but Linux fails before code entry. The native
worker now offers the code dialog before waiting on the trusted-device notification
HTTP response. Code entry waits on the private input pipe without a user-entry timeout;
there is only one code dialog and one notification request. A notification read timeout
continues to normal code validation without resending; TLS, connection and explicit
HTTP errors remain fatal. Errors now retain a safe stage label. No recovery behavior
or retry budget changed. This addresses a demonstrated timeout path, not a proven
root cause of the owner’s current failure.

Three mocked tests cover prompt-before-response, one-request read-timeout handoff,
and fatal TLS failure. Six native GUI/IPC tests pass. Installed the updated worker
and notification patch for the next owner-initiated sign-in. Live authentication
and sync remain unverified; no credentials or codes were entered by the agent.


### Native Apple Passwords UX refinement — 2026-10-18

Added persistent mnemonic account/password labels, clearer optional password-storage
copy, sign-in step guidance, and contextual Verify Code / Use This Device / Unlock
Keychain actions. Verification codes are visible for proofreading, accept pasted
spacing, and require exactly six ASCII digits before submission. Waiting for the
owner pauses the spinner and explicitly says the app is waiting; notification
progress cannot overwrite that state. Recovery consent remains unchecked by default.

Added sorted password results, empty/no-match guidance, labeled username/password
details, distinct error styling, and contextual Complete Setup. Sync is hidden
until keychain setup is complete; sign-in fields disable during an operation.
Helper startup moved into the background worker so the GTK thread stays responsive.
Eight GUI/IPC tests and three mocked approval-handoff tests pass. Installed updated
app/worker bytes locally without restarting an active session; reopen the app for
new layout code. Authentication/sync success is still unqualified.

## PR #234 cleanup qualification — 2026-10-18

Merged current main and retained the parallel radio-test report. Radio install now
aborts on failed copies and refuses existing helper/policy paths instead of
overwriting their ownership manifest; uninstall without our manifest leaves
services alone. Three sandboxed installer tests pass. The userspace radio suite
passes 168 tests (8 explicit skips for absent DKMS/Arch packaging or prerequisites);
the plugin suite passes 318 tests (30 explicit optional-core/platform skips), and
the native widget passes all eight stub checks, with portal access disabled so
temporary test homes clean up reliably. The libarchive-c 5.1 archive-name fixture
was corrected using in-memory archive entries; receiver code is unchanged. CI now
checks both vendored userspace suites. These are source/UI qualifications, not
a completed phone transfer. The other session's steps 0–4 remain scoped evidence;
the subsequent parallel report records one iPhone receive pass. Send and real-panel
acceptance remain pending; AWDL stop leaves elevated Wi-Fi latency. Retargeted the
obsolete stacked base to main and retained the merged Calendar/Homeboard changes.
No radio activation, panel reload or reboot was
performed during this cleanup review. The diagnostic boot selection is untouched.


## CodexBar QuickSwitch width — 2026-10-20
- Compact popover layout merged to `dev` via PR #315: 240 px minimum width, bounded dynamic labels, status and action dock on separate rows.
- Verified 11/11 headless render fixtures at a 280 px target (268 px captured content), 17/17 Meson test groups, and the live Wingpanel mapping the installed module. See `OS9-HANDOFF.md` for the deployment detail.
- Audit (2026-10-19): AUDIT-DEEPER Aurora unified 7.2.10 (DCP/CIO/PMP vs carried patches) and elementary kmscon default (#917) at the next elementary sync. See mseries/upstream-audits/daily/2026-10-19.md.

## Session reconciliation — 2026-10-20

Merged #290, #301–303, #305, and #307 to `dev`; reviewed integration notes, CI results, and parked branch/worktree dispositions are recorded in [OS9-HANDOFF.md](OS9-HANDOFF.md). Shelf-native drag behavior, older video-playback helpers, power-tuning A/B measurements, and the dirty appearance-mode worktree remain open and preserved. No unmerged worktree or local draft was deleted.

### Experimental iPhone onboarding and macOS guest preparation (2026-10-20)

`codex/messaging-macos-lab`: native Connect iPhone wizard, optional BlueFerry
integration and personal Bubbles build prepared. iPhone 14 Pro/iOS 27.0.1 MAP
permissions remain blocked; do not advertise working messaging yet. Machine Lab
has read-only VMApple readiness checks and current pinned Linux/KVM research;
M1 Pro boot, iMessage activation and dock-triggered full state save/restore are
not qualified. See `phone-setup/README.md` and
`machine-lab/experiments/vmapple/README.md`.

## One-visit Mac activation kit — 2026-10-20

Experimental messaging branch now includes a public downloadable Mac checklist
and pinned helper downloader at `phone-setup/macos-visit/`. Messaging requires
the genuine native hardware export and private transfer back to Linux. Optional
Machine Lab guest collection is documented for the same visit, with storage and
compatibility limits explicit. Shell checks pass; macOS execution and Bubbles
activation still require the owner. No claim that future VM work will never need
another macOS visit.

Single collector now includes the Machine Lab guest instead of leaving it as a
manual optional path: pinned downloads, genuine hardware export, native guest
startup, portable identity/storage configuration and re-read external hashes.
A completion receipt means files collected and transferred, not a qualified
Linux macOS boot. Next owner action: run it in native macOS with AC power and
an external exFAT drive; bring the verified private bundle back to Linux.

No-external-drive path: collector accepts an existing internal exFAT shared
partition. Creating one remains a separate capacity/backup/resize decision on
macOS; the collector performs no partition operations. Merely leaving the bundle
in macOS Downloads is not accessible from this Linux installation.

Native messaging redo: prior failed audio workaround rolled back; installed
Connect iPhone gains bounded Retry Connection without unpairing and stable
blocked/service/disconnected states. MAP transport and CONNECT probes all still
receive iPhone Forbidden. Text delivery remains the blocker, not solved by UI
checks or contact sync. No further VM/partition work is part of this retry.

Upstream protocol audit retained in `phone-setup/UPSTREAM-REVIEW.md`: installed
BlueFerry is current, but BlueZ 5.85 cannot provide the supported modern ANCS
bearer methods. Experimental advertisement/OBEX overrides were reverted after
failing to establish MAP. Stage a reversible BlueZ 5.87 trial before another
full-mode pairing; do not present that prerequisite as a guaranteed permission fix.
## Taskbar reboot/update persistence audit — 2026-10-20

Verified installed session dependency, private wrapper/executable path, persistent
taskbar-mode/pins, enabled unscheduled Work Mode login service/timer, and official
user-local icon/launcher files. No reboot or live dock changes were issued. Fixed
two update gaps: legacy dock_profile.py now preserves taskbar visibility/size/pins
using the private schema; factory payload now carries the complete taskbar/shared
CodexBar sources, tests, and official Teams/Outlook installer paths. Three isolated
regression tests exercise the real payload and profile apply/revert paths.

## Windows taskbar + CodexBar persistence — 2026-10-20

The canonical dock installer now applies the complete Windows taskbar stack and
CodexBar integration through `mseries/dock-taskbar/prepare-source.sh`. Source guards
reject a missing TaskbarRow, StartMenu, schema or CodexBar item. The taskbar button
sits left of Wi-Fi with a separate divider/gap; hover opens the shared native quota
menu without a keyboard grab, click pins it, leave closes after a crossing grace.
Owner requested larger popup text: 25% larger, 320-pixel body and 420-pixel
scroll viewport; the change is scoped to the taskbar popup.
The newer native Start menu and scoped Windows 11 CSS are included in the patch.
Teams' official icon and Outlook's transparent official SVG/launcher metadata are
retained. No icon asset is redistributed; existing local pins are unchanged.

A clean-build/linked-type/GTK hover regression check is wired into CodexBar CI;
`install-dock-drawers.sh --build-only` also runs the isolated hover probe before
any install. Tests use fake HOME/backend and cannot restart the desktop. See
`mseries/dock-taskbar/README.md`. Persistence work does not install/restart the dock;
the earlier complete Windows taskbar/CodexBar local deployment stays in place.
Do not deploy an app-tracking-only dock build lacking this full stack.

## Work Mode integration reconciled — 2026-10-20

#329 now preserves current gesture/cursor and floating-window clearance behavior
alongside taskbar modes, and selects the size-system token appropriate to the dock.
Nine Work Mode tests, 41 compositor tests, strict Clippy, native dock/settings builds
and private window/focus/typing checks pass. #337's status-note conflicts are
reconciled and 14 offline Teams/Outlook tests pass. No live desktop deployment.
See OS9-HANDOFF.md for receipts. Next: updated-head CI before merging, then the
remaining native taskbar/network and Teams/Outlook qualification checks.

## Teams/Outlook running markers and larger CodexBar popup — 2026-10-20

App tracking is now applied after the full canonical taskbar stack, with SHA-256
protection of Taskbar/StartMenu/CodexBar/shared sources and linked-type checks.
Brave StartupWMClass identities resolve to the existing official-icon launchers.
Markers synchronize for already-open apps at startup; open apps are gray, focused
apps blue, and closed pins unmarked. The owner requested another 25% font increase:
CodexBar uses 1.5625em, 400-pixel minimum body and 480-pixel scrolling viewport.

Clean native build, schemas, actual GTK Launcher startup/focus/close/reopen probe,
three resolver/AppSystem tests including both Teams/Outlook lifecycle and pin
retention, existing hover/focus/leave/pin probe, shell checks and light/dark fixture
inspection pass locally. Live read-only matching resolves both open Brave apps.
Source work reuses PR #339 and supersedes its draft; no partial dock deployment.
See mseries/DOCK-APP-TRACKING.md for boundaries and reproduction commands.

## Darker running-app markers — 2026-10-20

Owner requested darker gray running dots/pills. The complete taskbar now uses
65% black in light mode and 35% white in dark mode (previously 45% / 55%).
Focused blue markers, geometry, Start menu, CodexBar and app icons are unchanged.
Full canonical native build/schema, actual Launcher startup/focus/close/reopen
and CodexBar hover/focus/leave/pin probes, and resolver lifecycle tests pass.
All 46 production Vala files match #342 byte-for-byte; the stylesheet differs
only in these two marker colors.

- 2026-10-20: corrected taskbar running-marker specificity/opacity and applied 80% black light-mode markers; native build/schema and three lifecycle checks passed; privately deployed.

- 2026-10-20: owner requested a further marker darkening pass; solid black light-mode markers rebuilt and loaded in the active taskbar.

- 2026-10-20: final owner-tuned running markers use #444444 in both modes, matching the silver taskbar; rebuilt and loaded.

- 2026-10-20: owner requested slightly lighter markers; #555555 rebuilt and loaded in both taskbar modes.

- 2026-10-20: owner-tuned running markers lightened slightly to #606060 in both modes; rebuilt and loaded.

- 2026-10-21: audited eleven customized Pantheon shell ports against upstream; retained integration gates for Gala/Wingpanel/Dock/Files and unified desktop Quick Settings source preparation with factory/package builds. Native core/extras builds, source parity, routing tests and private Bluetooth probe passed; no live deployment. See `upstream-audits/pantheon-shell-2026-10-21.md`.

### 2026-10-21 upstream pass: native Messages

Prepared sender-ID read-only snapshot compatibility and accurate direct-sender
reply guidance; see `phone-setup/UPSTREAM-REVIEW.md` and newest OS9 handoff.
Next: qualify the current BlueFerry backend separately on the BlueZ 5.85
compatibility path before any service upgrade or hardware acceptance claim.

### 2026-10-21 Machine Lab CI fixture reliability

Confirmed and fixed fake-QMP child reaping/output-EOF race; regression tests use
only owned synthetic peers. No application behavior or VM acceptance change.
See `upstream-audits/housekeeping/2026-10-21-machine-lab-qmp-teardown.md`.

## M4 Mac mini preparation — 2026-10-21

See `m4-mini/README.md` and its pinned public source profile. Initial J773g DT
support exists; experimental J713 GPU/NVMe work does not qualify mini HDMI or
standalone boot. Source capture is available; board port, builds and hardware
acceptance remain open. Existing release pins are unchanged.

M4 initial DT compilation now passes from the pinned source capture; loader
fixups and physical boot remain unverified. See m4-mini/receipts for the retained
AIC unit-address warning and artifact digest.

M4 audit correction: Gravity Linux publishes a developer alpha with reported
J773g HDMI/DCP and GPU. The earlier Asahi-only unsupported summary was incomplete.
Its full stack is now pinned in m4-mini/research.json and its board DT compiles;
see m4-mini/GRAVITY-INTEGRATION.md for elementary integration gaps and alpha limits.
