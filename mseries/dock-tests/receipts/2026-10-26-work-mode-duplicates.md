# Work Mode / duplicate dock launcher repair — 2026-10-26

Scope: the owner's duplicate application icons, with Windows Work Mode meaning
the Windows-style desktop/taskbar. Broad GUI acceptance in #593 remains open.
Base: `origin/dev` `659e17ba`; initial exit-action commit `8d0827d5`.
Dock source remains elementary/dock 8.3.3 at
`8b45a68a122947ad3a6427bf6e159ec2acf04ad0` (GPL-3.0).

## Defects and reproduction

- Live pin list: 22 entries, 11 unique IDs, repeated in the same order.
  `ItemManager.map` calls singleton `AppSystem.load` on remap. Repeated loads
  append duplicate Apps while replacing hash entries, leaving orphan launchers.
- New regression with two desktop IDs repeated twice fails without
  `dock-unique-launchers.patch`: expected 2 model objects, observed 4 (exit 134).
- Exit-action taskbar patch fails downstream power patch application; once that
  is corrected, its stale 512-line new-file count drops seven lines and fails
  Vala compilation (`expected }`). Correct count: 519.
- GSettings-only exit waits for timer application. Use installed
  `mseries-desktop-mode elementary` to turn off and apply immediately.

## Changes and checks

`dock-unique-launchers.patch` makes initialization single-shot, uses owned hash
keys, reuses an existing App by desktop ID and suppresses partial pin saves
during loading. First load normalizes duplicates in first-occurrence order.
No desktop entries or icons are rewritten; both layouts share this model.

Commands run successfully on this Linux ARM64 desktop:

- `bash mseries/dock-tests/test-running-apps.sh`: five tests, production
  AppSystem/resolver with controlled Window/App services. Duplicate startup,
  repeated load, pin reuse, window grouping, close and reopen covered.
- `python3 mseries/work-mode/test_work_mode.py`: 13 isolated helper tests.
- `bash mseries/dock-taskbar/test-build.sh`: full pinned-source build, strict
  schemas, production size-policy/marker tests, light/dark pointer activation,
  context menus, Escape, typing and hover checks. Private buses/Xvfb.
- `bash mseries/install-dock-drawers.sh`: final source installed privately.
- `git diff --check`: pass.

## Wayland transition failure and repair

The first live Windows -> elementary transition disconnected the customized
dock and triggered the launcher's stock-dock fallback. The owner's follow-up
reported that open windows disappeared. The earlier pin/settings-only round trip
was insufficient runtime evidence and is superseded by this qualification.

Retained protocol observation before the final fix:
`xdg_surface.set_window_geometry(1221, 0, -1397, -2)` followed by error 5:
width and height of window geometry must be greater than zero. The initial
clamping attempt still used the OLD surface allocation while GTK committed the
NEW layout. `dock-mode-geometry.patch` now measures the new layout and sets its
size and shadow together in the same compute-size handler.

Added read-only `io.elementary.dock.items.ListRunningApps` diagnostics; no
window titles or content are returned. New `test-wayland-transition.py` runs the
actual dock and installed nested Pantheon compositor on Xvfb with private
HOME, settings, runtime and non-activating buses. It launches a fixture window,
checks its running identity, performs four floating/taskbar transitions in the
same dock process, checks the identity after each, then closes the app and
checks removal. PASS. This adds Wayland protocol coverage absent from the X11
launcher fixtures. The installed nested compositor is qualification tooling;
this does not establish a source-matched native compositor hardware release.

Command (compiled production schemas required):

```sh
python3 mseries/dock-tests/test-wayland-transition.py BINARY SCHEMA_DIR NEW_OUTPUT_DIR
```

## Final deployment and live state

Installed/loaded dock SHA-256:
`d43fd2536b0cff3a0cc4e621ce29c822378e77a6266f9540e766cce25e833893`.
Final incremental build/install used the retained prepared tree at
`/tmp/mseries-dock-recovery`, followed by `systemctl --user restart pantheon-dock.service`.
Loaded native dock PID 215953 reports nine running applications through
`ListRunningApps`; saved pins are 11 entries / 11 unique IDs. The fallback
marker is absent. The owner-requested Windows Work Mode remains active; no
more live mode switching was performed after the owner reported disruption.

Private pre-repair pins retained at
`~/.local/state/mseries/dock-duplicates-2026-10-26-before.json` (0600).
The original first-occurrence pin order is preserved. Only the dock was
restarted by this task, with `KillMode=process` preserving launched apps.
No Wingpanel restart was performed by this task (observed final panel PID
197327; earlier concurrent work changed it from 53749).

Limits: Exit menu click itself and owner visual acceptance remain unverified;
its helper path and the isolated Wayland transition were exercised. No new
screenshot review is claimed. Pre-existing startup `g_list_store_remove` and
`g_object_ref` criticals remain untraced; this batch does not claim to fix them
or close broader #593. No kernel, bootloader or audio change. Uncommitted Work
Mode Settings control changes in the shared checkout were preserved separately.
