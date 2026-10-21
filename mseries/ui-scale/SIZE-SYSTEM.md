# M-Series size system

Issue: [#332](https://github.com/techmore/ElementaryOS_MSeries/issues/332). Source of truth:
[`size-system.json`](size-system.json).

One text-size ladder drives every surface. Quick Settings (`mseries/quick-settings/TextScale.vala`)
steps along it, and `mseries-ui-scale --watch` keeps the dock in step with it in native mode
and Work Mode. Display scale, refresh rate and brightness are never touched.

| Step | Text | Dock native | Work floating | Work taskbar |
| --- | --- | --- | --- | --- |
| Compact | 0.85 | 40 | 32 | 40 |
| Small | 0.92 | 44 | 36 | 44 |
| Default | 1.00 | 48 | 40 | 48 |
| Large | 1.10 | 52 | 44 | 52 |
| Larger | 1.25 | 60 | 48 | 60 |
| Largest | 1.50 | 72 | 56 | 72 |

Font policy: UI Inter 9, document Open Sans 10, monospace Roboto Mono 10, titlebar Inter Bold 9
(applied by `--set`).

## Rules for app authors
- Size text with the Granite ramp only: `title-1` (24pt), `title-2` (18pt), `title-3` (11pt),
  `title-4`/`Granite.HeaderLabel` (bold body), body, `dim-label`, `small-label` (0.85rem), `numeric`.
- If you need a custom size, use `em`/`rem`, and never go below 0.8em. Don't use absolute `pt`
  sizes, and never use `px` for fonts: `px` ignores the text-size setting.
- Don't hard-code dock sizes. Read `mseries-ui-scale --dock-size native|work|work-taskbar`
  (exit 3 means the size system isn't adopted: keep your previous behaviour).

## Dock writers read the tokens (phase 2)
The scripts that used to hard-code a dock icon size now ask the size system, and keep their old
literal as the fallback when it is absent or not adopted (`--dock-size` exits 3). At the default
step the token equals the old literal, so nothing changes until the text size does:

| Script | Token | Default step | Old literal |
| --- | --- | --- | --- |
| `dock-policy/enable-permanent.sh` | `native` | 48 | 48 |
| `dock-trial/dock-trial.py` (`--visible`) | `native` | 48 | 48 |
| `display-space/dock_profile.py` (compact floating profile) | `work` | 40 | 40 |
| `work-mode/mseries-work-mode` | `work` / `work-taskbar` | 40 / 48 | 40 / 48 |

`dock_profile.py` uses the `work` token because the compact floating dock is the 40 px size,
not the 48 px native dock. `mseries/ui-scale/test_dock_consumers.py` runs each script against a
stand-in `mseries-ui-scale` (absent, unmanaged, garbage output, and several steps) and compares the
result with the old literal, so default-scale behaviour is proven identical.

Still open in phase 2: the taskbar's compiled-in 48 px icon size (`TASKBAR_ICON_SIZE` in
`patches/dock-taskbar.patch`) and the fixed 1.30 Wingpanel content scale
(`patches/wingpanel-content-scale.patch`). Both need a dock or panel rebuild and a visual check.

## `check-ui-sizes.sh`
`mseries/ui-scale/check-ui-sizes.sh` scans the size-bearing sources (dock profile, policy and
trial scripts, Work Mode, the taskbar sources and patches, the CodexBar and RepoBar indicators,
the Wingpanel content-scale patch) and fails on hard-coded sizes, in four rules:

| Rule | Finds | Use instead |
| --- | --- | --- |
| `font-abs` | `font-size` in `pt`/`px` | Granite ramp class, or `em`/`rem` |
| `dock-size` | dock `icon-size` literals | `mseries-ui-scale --dock-size MODE` |
| `icon-px` | `pixel_size`, `-gtk-icon-size: Npx` | a size derived from the ladder |
| `panel-scale` | fixed `CONTENT_SCALE` | a value derived from the ladder |

Patches are scanned on their added lines only. Existing sizes are listed in
`ui-size-allowlist.json` as `(file, rule, matched text)` groups with a maximum count and a required
reason, so line moves don't matter but a new size, or one more of an old size, fails. Migrating a
size means deleting it and trimming its entry; `--strict` (used in CI) also fails when an entry
is larger than what the sources contain, so the list can only shrink. `--list` prints everything the
scanner finds. The RepoBar taskbar readout (18pt) is allowlisted on purpose: the owner chose it.
Phase 3 turns the allowlist down to zero font entries. Tests: `test_check_ui_sizes.py`.

## Adoption
Installing changes nothing on the desktop. The size system is adopted the first time the
text size changes, from Quick Settings or with `mseries-ui-scale --set STEP`. From then on,
the dock follows the ladder. `mseries-ui-scale --unmanage` stops it.

The rest of phase 2 (taskbar icon size and Wingpanel scale from the ladder), phase 3 (app type-ramp
migration) and phase 4 (Qt/Electron) are tracked in #332.
