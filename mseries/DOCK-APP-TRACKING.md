# Windows taskbar running indicators

The canonical `dock-taskbar/prepare-source.sh` applies app tracking **after** the
complete Windows taskbar, Start menu, AirDrop controls and CodexBar stack. SHA-256
comparisons reject a tracking patch that changes Taskbar.vala, StartMenu.vala,
TaskbarCodexBar.vala, TaskbarAirDrop.vala, AirDropPanel.vala or the shared CodexBar
sources. The linked application must contain all customization types and AppResolver
before installation. Build/test commands never reload the live desktop.

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

### Supersession confirmed

The recovery coordinator closed #339 as superseded at 12:05:17 and reported the
#342 coordinated deployment complete. The original tracking integration is already
in dev. This review's extra hardening is retained in a separate draft follow-up,
not an attempted merge/redeployment of #339. The follow-up's representative native
acceptance remains unqualified; no deployment or Wingpanel restart was performed.

## PR #343 source-merge qualification — 2026-10-20

Completed the remaining visual/input checks without deploying: the new
`dock-tests/test-launcher-qualification.vala` links the actual production App,
Launcher, Window and resolver classes. Its Python runner uses private Xvfb,
HOME/settings, a recording compositor, read-only AppCenter and portal stubs,
and real XTEST pointer/keyboard events. It tests the changed controls in light
and dark themes, with complete original fixture artwork and actual Brave-style
Teams/Outlook identity patterns. No browser account or live window is operated.

Real clicks verify mixed-ID focus fallback, complete homogeneous-ID group
activation and transient-window focus. Actual secondary-click menus retain
installed-launcher pinning and omit invalid transient management actions; Escape
dismissal and subsequent typing pass. Pointer hover preserves keyboard focus.
Both screenshots were inspected: open gray/focused blue/multiwindow markers and
closed-pin absence match the canonical design, with complete icons.

The canonical clean taskbar build now compiles/runs this qualification alongside
the existing actual marker-state, hover and resolver checks, so CI repeats it.
Reproduction: `MSERIES_QUALIFICATION_OUT=/absolute/output bash
mseries/dock-taskbar/test-build.sh`. Evidence: `dock-tests/receipts/qualification-343-2026-10-20/`.

This completes the source-merge visual/input gate requested by the owner. Earlier
receipt references to live qualification remain historical deployment boundaries,
not a claim that this run tested native M-series hardware. Physical Wayland
placement/performance and authenticated browser behavior remain separate
post-deployment acceptance. The explicit no-deploy/no-Wingpanel-restart instruction
was honored; source merge does not install these changes. Merge still requires
all updated-head GitHub checks to pass.
