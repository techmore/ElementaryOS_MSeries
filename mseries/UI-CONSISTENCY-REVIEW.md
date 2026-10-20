# M-Series UI consistency review — 2026-10-20

Reviewed using `elementaryos-mseries-ui-specialist` against `dev` revision
`31a926b2f584ae7add46747bdc0d49e7ef056d18`.
Branch: `codex/ui-consistency-review`.

## Review scope and priorities

Source review covered Orchard main navigation and instance controls, Battery,
Apple Passwords, Machine Lab theme/style conventions, CodexBar settings and
popover conventions, Quick Settings shared controls, the Work Mode plug, and
Troubleshooter's existing screen references. This is a focused first pass, not
an exhaustive audit of every dialog or interaction in the repository.

| Priority | Finding and user impact | Resolution |
| --- | --- | --- |
| P2 | Orchard puts ten action icons into its header, with four filters and six bulk controls in fixed horizontal rows. The old header measures at least 761 logical pixels wide, preventing a 720-pixel window. Long instance names also compete with row actions. | Keep New and Refresh visible; move eight secondary destinations to a labeled native action menu. Place search above wrapping filter controls and let bulk actions wrap. Ellipsize names with full-name tooltips and wrap metadata. Add accessible labels to changed icon controls, filters and selection controls. |
| P2 | Apple Passwords gives its complete login form directly to a homogeneous stack without a scroll container. Requesting a 420-pixel-high window produces a 574-pixel window; larger text makes constrained-height use worse. | Scroll the login page vertically, size stack pages independently, and reduce the form's minimum width from 420 to 360. Preserve the existing sign-in/verification flow and mnemonic labels. |
| P2 | Orchard and Battery do not subscribe to Granite's desktop color-scheme preference, unlike Machine Lab and Apple Passwords. Their appearance can remain inconsistent with the selected desktop mode. | Initialize GTK's dark preference from Granite at startup and update it on preference notifications, using each app's existing language/toolkit. Battery's report/preferences icons also receive explicit accessible names. |

## Validation and evidence

- Orchard: `meson setup work/orchard-build mseries/orchard-incus-native -Dwingpanel=disabled`,
  component compilation, then private-Xvfb/private-D-Bus `meson test` passed all
  four targets: incus-client, model-client, native-windows and restart-config.
  Existing compiler warnings remain; compilation succeeds.
- The UI smoke now presents a 720 × 640 window with a long fixture name, checks
  minimum/allocated width, and activates the seven secondary-window actions,
  checking that each opens the expected window type/title. The eighth menu action
  selects Dashboard. Fake Incus, temporary configuration/state and a private
  display keep these checks separate from the live desktop.
- A disposable copy of the original Orchard main window with the geometry test
  fails at minimum width 761 versus the required 720. The updated window's header
  minimum is 289, and the complete instance view renders at 720 with wrapping
  bulk controls and visible row actions.
- Orchard renders at 720 × 640 in both light and dark elementary themes were
  captured and visually inspected. The probe supports `ORCHARD_UI_CAPTURE` for
  screenshots after the next layout/frame.
- Apple Passwords: all nine `test_gui.py` tests passed under private Xvfb/D-Bus,
  including a 540 × 420 window with Sans 14 text, a scrollable login page,
  reachable Sign In focus, and existing sign-in/verification/cancellation checks.
  The same short-window regression test against the original app fails because
  it allocates 574 pixels of height. Light/dark 540 × 420 login renders were
  visually inspected with the sign-in region scrolled into view.
- Battery: all 26 `test_battery*.py` tests passed. The new GTK test verifies the
  initial dark preference and subsequent preference notifications in both
  directions using mocked desktop preference reads. Light/dark 980 × 680 empty
  history screens were rendered with isolated data/config and inspected.
- `git diff --check` passed. Screenshot probes use fixtures/empty data, never
  Apple credentials or a live Incus daemon. Orchard's color-preference hookup
  is compiled and follows Machine Lab's existing pattern; live desktop switching
  was not hardware-tested. Programmatic focus/action checks are not a complete
  keyboard or screen-reader qualification.

## Remaining review items

- CodexBar settings and Troubleshooter do not have an explicit Granite
  color-preference subscription in the inspected frontend source. Determine
  their actual startup/theme behavior with dedicated fixtures before changing
  them; an absent subscription alone does not prove a visible failure.
- Machine Lab includes hardcoded status colors and a continuously pulsing running
  indicator. Review contrast and animation-preference behavior in a dedicated
  visual pass before replacing intentional machine identity colors.
- Orchard's secondary dialogs still have dense headers/forms; this batch fixes
  main-window navigation and controls. Smaller widths than 720, very large text,
  RTL and actual translated strings need a further layout pass.
- Battery still rebuilds its pages when refreshing. Preserving focus and scroll
  across refreshes deserves a separate behavioral fix and fixture coverage.
- Several frontends lack complete gettext integration. This batch does not
  claim localization completeness or introduce a cross-app translation system.

## Runtime status

PR #321 merged into `dev` as `9cb1c70` and the three updated apps were installed
on 2026-10-20 at the owner's request. Installed-file comparisons and private-display
startup/scroll/theme checks passed; see
`mseries/receipts/ui-consistency-install-2026-10-20.json`. Reopen the apps to load
the changes. No live app, panel or daemon was restarted, and no wallpaper, account,
VM or hardware settings were changed. No CodexBar runtime files were modified.
