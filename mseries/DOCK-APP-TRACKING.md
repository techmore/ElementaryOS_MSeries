# Draft: taskbar-compatible app tracking and running pills

**Source-only. Not installed. Do not deploy while desktop recovery is pending.**
This draft leaves the owner’s Windows taskbar binary and private schema untouched. This
patch is not applied by the default installer. Explicit build-only qualification
is available with `bash mseries/install-dock-drawers.sh --build-running-apps-only`.
That mode requires the complete Taskbar.vala and taskbar-mode schema, verifies
Taskbar.vala stays byte-identical, builds, and exits before installation.

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

The source-only combined build applies the existing drawers, workspace/startup,
and **complete Windows taskbar patch**, then this app-tracking patch, all on
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
