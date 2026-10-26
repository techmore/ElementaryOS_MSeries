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

## Deployment and live state

Installed dock SHA-256:
`e0c6110b65427a9c83651d1f635a84281967dd2b45f730b5a8254ed853b6c3ee`.
Reloaded only `pantheon-dock.service` for the confirmed duplication defect;
`KillMode=process` preserves launched apps. Loaded native dock PID 196102.
Wingpanel PID stayed 53749; it was not restarted.

Private pre-repair pins retained at
`~/.local/state/mseries/dock-duplicates-2026-10-26-before.json` (0600).
Startup normalized 22 pins to 11 unique entries. Live
`mseries-desktop-mode elementary` then `mseries-desktop-mode windows` returned
`Off`/taskbar false then `Active`/taskbar true. Final pins exactly match the
first occurrence of each original ID, in order. Owner's active Windows mode
restored after the check.

Limits: Exit menu click itself and owner visual acceptance remain unverified;
the loaded action's helper path and mode state were exercised. No new screenshot
review is claimed. Two pre-existing startup criticals (`g_list_store_remove`,
`g_object_ref`) also appeared after reload and remain untraced; this batch does
not claim to fix them or close #593. No panel, kernel, bootloader or audio change.
