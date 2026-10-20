# Toolkit and screen map

Inspected 2026-10-20 at ElementaryOS_MSeries revision
`ed0d31ab28431b5ecb8549a274ac9d1892bc63a4` (`origin/dev`). Paths are repository-relative.
Recheck them in the active branch before copying patterns.

## Build evidence and screen families

| Surface | Evidence and useful starting points | Patterns to reuse or assess |
| --- | --- | --- |
| CodexBar settings | `mseries/codexbar-wingpanel/meson.build`; `settings/SettingsApp.vala`; `settings/SettingsModel.vala`; `PanelPreferences.vala` within that directory | Vala, Granite 7 >= 7.7; `Gtk.ApplicationWindow`, HeaderBar + StackSwitcher, scrollable pages, `Granite.HeaderLabel`, grouped rows with trailing controls; live configuration and visible apply errors |
| CodexBar panel | `mseries/codexbar-wingpanel/Indicator.vala`, `Presentation.vala`, `JsonBoundary.vala`, `HelperProcess.vala`, `AccountDialog.vala` | Wingpanel 9; compact snapshot-driven panel and popover, asynchronous bounded helper calls, separate presentation/model boundary, account actions |
| Quick Settings | `mseries/quick-settings/Controls.vala`, `Bluetooth.vala`, `AirDropPanel.vala`, `AirPlayOutputs.vala`, `AudioOutput.vala`; `prepare-source.sh` | Existing indicator integration; inspect source preparation and host dependency versions before modifying; preserve backend interfaces and device-state distinctions |
| Orchard native manager | `mseries/orchard-incus-native/meson.build`, `src/MainWindow.vala`, `InstanceDetails.vala`, `ResourceBrowser.vala`, `Dashboard.vala`, `Application.vala` under `src/` | Explicit GTK 4 + Granite 7, libsoup 3, libsecret; ListStore/ListView, search/filter/sort, pending operations, Granite.Toast; optional Wingpanel 9 module |
| Machine Lab | `mseries/machine-lab/meson.build`, `src/main.vala`, `src/page.vala`, `src/viewer.vala`, `data/style.css` | GTK >= 4.12 + Granite 7; machine sidebar/detail pages, empty welcome, machine states, themed cards; follows Granite color preference changes |
| Battery | `mseries/battery/mseries-battery-app.py`, `battery_core.py` | Python GI GTK 4 + Granite 7; section/card helpers, `Granite.Placeholder`, history and estimates. Keep measurements and estimates distinguishable |
| Apple Passwords | `mseries/icloud-passwords/app.py`, `worker.py`, `test_gui.py` | Python GI GTK 4 + Granite 7; HeaderBar, sign-in/verification/unlock flow, search/list/detail, busy/cancel/re-authentication controls, explicit experimental status |
| Work Mode | `mseries/work-mode/meson.build`, `Plug.vala`, `io.elementary.mseries.work-mode.gschema.xml` | GTK 4 + Granite 7 + libadwaita + Switchboard 3; PreferencesPage/Group, SwitchRow/ActionRow/EntryRow, GSettings bindings, native image chooser; initialize plug fields after GObject base construction |
| Troubleshooter | `mseries/netspeed/troubleshooter/mseries-troubleshooter-ui` | Python GI GTK 4 with optional Granite fallback; question entry, welcome suggestions, readable report with verdict and evidence |

## Concrete local anchors

In CodexBar `settings/SettingsApp.vala`, inspect `page`, `section`, `row`,
`add_row`, `icon_button`, `changed`, and `apply_pending`. Rows associate controls
with accessible labels, subtitles wrap, and configuration writes are debounced.
These are private per-app helpers, not a shared public component API.

CodexBar's current quick-switch menu starts with a 240-logical-pixel width request
and wraps/ellipsizes dynamic labels. GTK width requests are minimums; inspect
child natural sizes when a long account name widens a popover. Do not apply that
width to unrelated dialogs or full settings windows.

Machine Lab's CSS scopes styles with `ml-`; CodexBar uses `cb-` or
`mseries-codexbar` selectors. Machine Lab mixes theme-derived colors with explicit
status and machine palette values. Assess contrast and meaning before reuse.

## Retained screenshots actually inspected

- `mseries/netspeed/docs/screenshots/troubleshooter-empty-light.png`: 640 × 470,
  native header search, centered welcome with title, short explanation, and three
  icon/title/subtitle suggestions.
- `mseries/netspeed/docs/screenshots/troubleshooter-report.png`: 640 × 470, dark
  report with a verdict, attention/ignore groups, and readable task-focused text.

These are historical visual references, not evidence that current code or
hardware was visually qualified. Other screen families were inspected in source;
new screenshots should be captured when changing those screens.
