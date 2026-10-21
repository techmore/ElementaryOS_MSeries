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

The compiled taskbar now follows `icon-size` while the size system is managed.
The CLI atomically publishes a private generated adoption marker before emitting
any dock setting change: `$XDG_STATE_HOME/mseries/ui-scale-policy.ini` (default:
`~/.local/state/mseries/ui-scale-policy.ini`). The format is `[SizeSystem]` with
`version=1` and boolean `managed`; missing, malformed, unsupported-version or
unmanaged markers preserve the legacy 48 px taskbar. Native mode still reads
`icon-size` regardless of adoption. The JSON remains the only dock-token source.
`--unmanage` publishes false, leaving stored settings untouched. A shared native
policy monitor observes atomic replacement, deletion and malformed-policy changes;
it refreshes existing launcher icon caches, group layout and separator heights
without requiring the stored icon size to change. The directory monitor is registered
before its initial read so first adoption cannot fall between reading and watching. The marker is a generated
implementation detail, not a user preference. Unique temporary files avoid
concurrent CLI/watcher writers colliding.

Quick Settings adoption now applies the documented font policy as well as dock
sizes. Reconciliation publishes adoption before synchronous icon-size consumers
run; a pending text-change adoption is retained through overlapping mode changes.

Still open in phase 2: Wingpanel's fixed 1.30 content scale. A private experiment
using a text-dependent transform and inherited-font compensation did not cover
absolute/rem typography in upstream indicators. Applying that transform could
scale those fonts twice. The experiment is not shipped; a panel sizing design
must cover all upstream font classes before acceptance.

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
scanner finds. The RepoBar taskbar readout is half the dock icon size in points (48 px icons give 24pt, 72 px give 36pt), computed in
`TaskbarRepoBar.vala` from the same token the dock uses, so it follows the mode and text step together. RepoBar/CodexBar,
legacy Orchard and Start-menu fonts now use relative units. The lint inventory
also covers Machine Lab, Battery, Screenshot Shelf, native Orchard and OpenCode
login; their existing relative fonts remain intact. Glyph geometry exceptions
remain separate from font migration. Tests: `test_check_ui_sizes.py`.

## Adoption
Installing changes nothing on the desktop. The size system is adopted the first time the
text size changes, from Quick Settings or with `mseries-ui-scale --set STEP`. From then on,
the dock follows the ladder. `mseries-ui-scale --unmanage` stops it.

## Validation and remaining acceptance

The native taskbar-policy fixture compiles the exact production methods from the
patch and checks every dock token plus unmanaged/malformed/version fallbacks on
isolated settings. The complete prepared native dock fixture also creates actual
Launcher/ItemGroup/ItemManager widgets, keeps `icon-size=40` unchanged, then checks
adoption, unmanage, malformed and deleted policy transitions update cached icons,
group geometry and separator height. Its service activation is disabled and runtime,
D-Bus, settings and display are private. A separate private portal process supplies
precise `Read`/`ReadOne` variant layering and typed appearance settings. Read-only
Switcheroo properties use the private logical system bus; no AccountsService is
registered, so accidental Granite fallback still fails under fatal criticals.
The outer full-suite and nested launcher buses disable service activation too.
The cached-widget fixture compiles actual prepared dock/custom schemas plus a
clearly labelled, pinned Gala consumed-key subset. Its complete four-schema
inventory and exact workspace-key default are asserted. All native fixture
runtimes set private `XDG_DATA_DIRS` and `GSETTINGS_SCHEMA_DIR`; no host schema root
can satisfy a missing dependency. Compiler metadata paths remain unchanged. The complete prepared source builds without
installation. Constructing the real manager with fatal criticals also exposed an
upstream pre-construction callback capture in `BackgroundItem`; its map callback
is now static with identical icon ownership and results.
RepoBar/CodexBar fixture scripts now retain `GDK_SCALE=1|2` through `env -i`, assert
the actual window scale, and save scale/dimension metadata. Scale2 names have a
suffix. PNG snapshots use logical widget coordinates; identical PNG dimensions
do not establish physical multi-monitor acceptance.

The rebuilt taskbar/module must load at next login before owner-session visual
acceptance. Check internal125%/dock100%, native/floating/taskbar and light/dark.
Routine CodexBar staging preserves the running panel and daemon; no live process
restart or monitor/refresh/brightness change is part of these checks.

Wingpanel sizing, physical visual acceptance and Qt/Electron phase4 keep #332 open.
Do not apply blanket `--force-device-scale-factor` or `QT_SCALE_FACTOR` overrides:
these can replace/compound compositor monitor scaling. Each app needs a measured
font-only integration under its actual Wayland/Xwayland backend with isolated
profiles and preserved user preferences. Unsupported apps retain toolkit defaults.
