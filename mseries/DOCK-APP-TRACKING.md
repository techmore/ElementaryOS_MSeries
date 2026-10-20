# Draft: taskbar-compatible app tracking and running pills

**Source-only. Not installed. Do not deploy while desktop recovery is pending.**
This draft leaves the owner’s Windows taskbar binary and private schema untouched. This
patch is not applied by the default installer. Explicit build-only qualification
is available with `bash mseries/install-dock-drawers.sh --build-running-apps-only`.
That mode first uses the canonical `dock-taskbar/prepare-source.sh` path from
PR #341. It verifies Taskbar.vala, StartMenu.vala, TaskbarCodexBar.vala and all
shared CodexBar Vala sources stay byte-identical, builds, runs the real GTK hover/
focus probe, and exits before installation.

## Problem and proposed fix

The compositor reports window identities such as `io.elementary.appcenter`,
`Chatgpt`, and `brave-teams.microsoft.com__v2_-Default`. The dock treated these as
literal desktop filenames and silently skipped windows without an exact match.

`dock-running-apps.patch` resolves installed IDs with/without `.desktop`,
case-insensitive IDs, StartupWMClass, then unambiguous executable basenames.
The cache follows desktop-catalog changes. It preserves the raw identity for
window actions and groups each resolved application's real windows under its
installed launcher. Teams/Outlook matching relies on the launcher metadata from
the transparent-icon PR. Applications without installed desktop entries get
safe generic transient runtime items, which disappear when their windows close.
Their placeholder executable is `/usr/bin/false`; window identities are escaped
KeyFile strings, never commands. Generic items cannot be pinned through the menu.

Running markers are muted theme-derived gray pills, 10×3 logical pixels for one
window and 14×3 for multiple windows. Inactive-workspace markers are dimmer.
Closed pinned apps have no marker. Background processes without managed windows
are not presented as opened apps.

## Customization boundary and recovery

An earlier deployment incorrectly built only the Pantheon dock, omitting the
owner's Taskbar.vala customization. The recovery chat restored the retained
Windows-taskbar executable during recovery (SHA256
`960642d81bd83c4ec06be02c6a37ffa6967a874ddd42e4011827bc696002541f`) and schema.
Official Teams/Outlook icons, launchers and pins were preserved. The recovery chat subsequently owns all live taskbar deployments, including
the owner’s newer StartMenu and CodexBar changes. Do not restore an older binary
or repeat the incompatible deployment. No further live dock changes are authorized by this draft.

The source-only combined build uses the canonical helper to apply drawers,
workspace/startup, complete Windows taskbar and taskbar-CodexBar patches, and
copy the shared native CodexBar sources. Only then is this tracking patch applied, on
upstream elementary/dock `8b45a68a122947ad3a6427bf6e159ec2acf04ad0`. The complete committed Taskbar.vala baseline is unchanged by this patch.
A second isolated build also combines the patch with the recovery chat’s full
current Taskbar, StartMenu and TaskbarCodexBar sources. All three files remain
byte-identical after applying the patch and the combined native build passes.
The preservation receipt is `dock-tests/receipts/taskbar-source-preservation-2026-10-20.json`.
This is source/build validation only; it is not installed or live-qualified. The native combined build passes.
The original GPL headers are retained; the resolver is GPL-3.0-or-later.

## Verification

```sh
bash mseries/dock-tests/test-running-apps.sh
bash mseries/dock-tests/test-startup.sh
python3 mseries/dock-tests/test-launcher.py
bash mseries/install-dock-drawers.sh --build-running-apps-only
```

The canonical preparation path, build-only guard and GTK hover/focus probe
also pass at dev `689ffdf6aca2cbddf1f54637de22e45d0fb29d38`.

Three native tests compile the actual AppResolver and AppSystem against controlled
services and real private desktop entries. They cover normal/browser/unknown IDs,
ambiguous executable aliases, preserving pins, grouping multiple windows, and
open/close transitions. Eight existing wrapper regressions pass. Fourteen Teams/
Outlook offline tests passed separately. Private light/dark GTK probes measured
10×3 and 14×3 pill geometry without CSS errors. An earlier read-only live resolver
probe matched all seven then-current app identities, including Teams and Outlook.
These checks do not qualify the final combined taskbar visually or on live input.

Next gates: owner confirmation of desktop recovery; review the full customized
build and source provenance; isolated combined-taskbar UI/focus/typing checks;
then separately authorize a coordinated live deployment owned by the recovery
coordinator. Keep this PR draft
until those gates are met. Do not let the icon PR's automatic merge apply here.

## Review follow-up — 2026-10-20

Fixed nondeterministic StartupWMClass and case-folded ID collisions; exact
case-sensitive desktop IDs still win. Unknown/ambiguous aliases get transient
items. Mixed raw identities grouped under one launcher cannot use the compositor's
single exact-ID overview, so clicking focuses one window rather than showing an
incomplete group; per-window menu actions remain available. Transient items also
hide the inapplicable Uninstall action.

The full taskbar CSS overrode the original gray-pill patch with blue 18×4 markers.
Removed that competing block in the opt-in tracking patch, retaining neutral
10×3/14×3 pills. The fixed-silver taskbar gets a darker neutral marker for visible
contrast; its shared Vala sources are unchanged.

Five production native regressions and eight wrapper checks pass. The canonical
full build/schema and hover/focus/pin/leave probe pass. A private nested combined
taskbar test passes X11/Wayland snapping, restore, dock clearance, startup/repeated
activation focus and keyboard typing. Reproduce with a candidate staged only
under a private fixture prefix:

```sh
MSERIES_SMOKE_TASKBAR=1 MSERIES_SMOKE_DOCK=/private/fixture/bin/io.elementary.dock \
MSERIES_SMOKE_COMPOSITOR=/private/build/pantheon-compositor \
  dbus-run-session -- python3 mseries/window-recovery/test-nested.py
```

The optional taskbar path creates a fake HOME/backend and private settings.
`MSERIES_SMOKE_CAPTURE=/absolute/path.png` retains a fixture screenshot. Review
receipt and screenshot: `dock-tests/receipts/review-339-2026-10-20/`. The screenshot
shows the complete bar and neutral pills, but fixture fallback icons and the lack
of complete real-app/light-dark/physical-input acceptance remain explicit limits.

**Still draft; not merge-qualified.** Owner recovery confirmation and separately
authorized coordinated live deployment remain gates. The current instruction
prohibits deployment and Wingpanel restarts, so neither was performed and the
gates were not waived. CI success alone cannot promote this draft.
