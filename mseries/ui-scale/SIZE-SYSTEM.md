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

## Adoption
Installing changes nothing on the desktop. The size system is adopted the first time the
text size changes, from Quick Settings or with `mseries-ui-scale --set STEP`. From then on,
the dock follows the ladder. `mseries-ui-scale --unmanage` stops it.

Phases 2–4 (Wingpanel scale, the other dock writers, app type-ramp migration, Qt/Electron)
are tracked in #332.
