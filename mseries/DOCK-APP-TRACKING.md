# Windows taskbar running indicators

The canonical `dock-taskbar/prepare-source.sh` applies app tracking **after** the
complete Windows taskbar, Start menu and CodexBar stack. SHA-256 comparisons reject
a tracking patch that changes Taskbar.vala, StartMenu.vala, TaskbarCodexBar.vala or
the shared CodexBar sources. The linked application must contain all customization
types and AppResolver before installation. Build/test commands never reload the
live desktop.

The compositor supplies window IDs, not always desktop filenames. AppResolver
matches installed desktop IDs (with/without suffix), StartupWMClass, then unique
executable basenames. Thus Brave Teams/Outlook windows group under the pinned
launchers with their existing official icons. Ambiguous executable aliases do
not pick an arbitrary launcher. Unknown apps get temporary unpinnable entries;
the placeholder executable is `/usr/bin/false`, never a window-supplied command.
Window actions retain the original compositor identity and UID.

Markers are real GTK boxes. Open apps show a gray pill; only a window with
`has-focus` makes its launcher blue. Closed pinned apps have no marker. The
revealer is explicitly synchronized at initialization, fixing already-open apps
whose state was known before notify handlers connected. Focus changes also
refresh the marker even if the window count is unchanged.

This reuses the resolver and controlled-service tests drafted in PR #339 and
completes them with the initial-marker fix, actual-focus styling and Outlook
lifecycle coverage. The combined PR supersedes the draft; do not install the
earlier tracking-only builds.

CodexBar text is now 1.5625em: another 25% above the previous 1.25em. Its body
minimum is 400 logical pixels and its scroll area is capped at 480. The grouped
button, hover/focus behavior and divider remain unchanged. Teams/Outlook assets,
launcher files and ordered pins are not rewritten by the dock installer.

## Validation

```sh
bash mseries/dock-taskbar/test-build.sh
bash mseries/install-dock-drawers.sh --build-only
```

CI's clean pinned-upstream build links the full taskbar and checks component types.
The actual Launcher GTK probe covers initially-open apps, focus-only changes,
closing and reopening. Three actual resolver/AppSystem tests cover identities,
unknown/ambiguous windows, multiwindow grouping, Teams and Outlook lifecycle, and
pin retention. The existing real GTK CodexBar hover/focus/leave/pin tests run too.
Local light/dark native fixture renders were inspected: Teams focused blue,
Outlook open gray, closed AppCenter unmarked, and the larger quota popup fits.
A read-only check against the live compositor resolved both actual open Brave
windows to their expected installed Teams/Outlook desktop entries. This is not a
claim of owner visual acceptance on native Wayland.

## PR #339 review rebased on #342 — 2026-10-20

PR #342 superseded the draft's original integration during this review. This
follow-up preserves its initial-marker synchronization and gray-open/blue-focused
state, larger quota popup and canonical tracking preparation. The earlier review's
all-gray CSS candidate was not carried forward over this newer implementation.
The obsolete explicit build-only alias no longer applies the tracking patch twice.

Remaining fixes: reject ambiguous StartupWMClass/case-folded ID matches while
preserving exact case-sensitive IDs; focus a window rather than requesting a
partial exact-ID overview when aliases share a launcher; hide the inapplicable
Uninstall/View in AppCenter actions on generic transient placeholders.
Five production resolver/AppSystem/activation-selection regressions, eight wrapper
tests, full canonical build/schema/preservation, actual GTK marker-state and
hover/focus/leave/pin probes pass. The combined private nested taskbar also passes
X11/Wayland snapping, restore, clearance, focus and typing. The optional
`MSERIES_SMOKE_TASKBAR=1` path in `window-recovery/test-nested.py` uses fake HOME,
backend and settings and requires an explicit candidate binary.

Receipt and reviewed screenshot: `dock-tests/receipts/review-339-2026-10-20/`.
The screenshot retains fixture fallback icons and is not complete representative
real-app/light-dark/physical-input acceptance. No live install/restart occurred.
Keep #339 draft: the recorded recovery-confirmation and representative acceptance
gates remain unproven, and the coordinated live-deployment gate cannot be
completed under the owner's explicit no-deploy instruction. Do not treat #342's
merge as authorization to deploy this follow-up.
