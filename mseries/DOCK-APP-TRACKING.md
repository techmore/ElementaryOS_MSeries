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
