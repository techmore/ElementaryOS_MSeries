# Panel and Orchard visual consistency review — 2026-10-20

Source baseline: `9cb1c70` on `dev`. Branch: `codex/panel-ui-polish`.
Applied `elementaryos-mseries-ui-specialist`; owner chose visual polish of
Orchard's app and dropdown before additional management features.

## Changes

| Surface | Problem | Fix |
| --- | --- | --- |
| CodexBar dropdown | Fixed 7–8 pt text, tight cards and horizontally competing account/quota/action fields make the compact view difficult to scan. | Theme-relative text sizes, padded rounded cards, full-width quota bars below their labels, and separate identity/switch and quota lines. Compact width checks still pass. Existing quota semantics, provider order, hints and account actions remain intact. |
| CodexBar settings | Unlike neighboring native apps, the frontend does not initialize or follow Granite's dark preference. | Use the existing native system-preference pattern at startup and on changes. |
| Quick Settings | The volume, display and keyboard sliders rely on icons/tooltips to identify them. Similar sliders have little visible hierarchy. | Visible labels with aligned percentages above each control; retain their existing icon actions, accessibility labels, coalesced writes and backend behavior. Slightly softer, more spacious grouped cards. |
| Orchard dropdown | Metrics, graphs, status and actions read as a flat list. Empty graph areas and a short scroll allocation leave poor proportions or clipped rows. Refreshes recreate identical rows, disturbing focus. | Paired metric cards, explicit instance section, stacked name/status rows, accessible action names, full-name tooltips, bounded scroll height, useful empty/unavailable copy and a clear Open Orchard footer. Hide graphs without valid running measurements. Preserve unchanged rows on refresh. |
| Orchard app | Always-visible bulk controls clutter the instance view; the dashboard is a long stack of ungrouped values/graphs. | Show bulk controls after selection, a labeled New Instance primary action, cleaner list/sidebar structure, responsive CPU/memory/network/storage cards, and an activity heading. Sparklines follow the theme accent. Existing management functions remain available. |
| Battery dropdown | One giant clickable report mixes summary, history, CPU users, profiles, events and suggestions. Truncated dense text competes with the headline. | A prominent remaining-time summary and graph, grouped statistic tiles, a bounded Recent activity disclosure and an explicit Open Battery button. All activity sections remain reachable. Cache unchanged summaries and stop refreshing while unmapped. Stock device fallback and existing power controls are retained. |

## Validation

- CodexBar builds and all 17 Meson tests pass. Existing compact-width assertions
  pass with the larger text across Quota, Sessions and Spend. Light fixtures
  include healthy, empty and provider-error; dark fixtures include healthy,
  stale and exhausted. The custom-port check passes, including the live snapshot
  schema. Upstream version remains `v0.78.0`.
- Native Orchard builds with Wingpanel enabled and all five suites pass.
  The indicator fixture covers seven transitions: populated, identical refresh,
  empty, all stopped, error, empty recovery and populated recovery. The identical
  refresh checks that existing row widgets are preserved. Window tests check
  selection/clear behavior and the previously covered menu destinations.
- Quick Settings and Power modules both compile from the existing pinned
  upstream sources with the project's patch sequence. No pin or backend was
  changed. Bluetooth's private BlueZ checks pass for connect/disconnect,
  failure recovery and power off/on.
- New `mseries/panel-ui-probes/run-probes.py` renders the actual shared slider
  implementation with fake write backends and the actual HistoryCard extracted
  from the patch. It checks that two rapid slider changes produce one latest-value
  write and that Battery details start collapsed and can expand. Fixtures use
  private Xvfb, D-Bus and temporary HOME/config/cache/data; no hardware or accounts
  are operated. Both themes pass. Quick Settings previews show the shared controls,
  not a claim that every service-backed section was exercised.
- The shared-control preview initializes GTK only; it does not need Granite
  desktop-settings initialization or AccountsService on a headless runner. Native
  Orchard fixture windows use the same approach, verified against a private bus
  with no AccountsService; the production app keeps its desktop integration.
- CI now runs these shared-control/summary probes in both themes and builds/tests
  the native Orchard module (the earlier Orchard job only covered its Python port).
- Light/dark screenshots of the changed widgets, Orchard's dashboard and indicator
  states were captured and inspected. `git diff --check` and workflow YAML parsing
  pass. Compiler/deprecation and private-portal warnings remain; no new build error
  or GTK critical was observed.

## Runtime and limits

No live panel reload is part of this work. CodexBar's required deployment stages
its module for next login while preserving Wingpanel and the daemon. This deploy
passed all 17 tests and retained both PID lists; see
`receipts/panel-ui-codexbar-stage-2026-10-20.json`. Quick Settings, Power and Orchard changes
remain built artifacts on this branch until installed. The owner's existing
Battery and Orchard apps remain available throughout the review.

This is visual polish, not a new Orchard feature set. Full screen-reader testing,
large-scale translated/RTL layouts, live radio/output changes and hardware battery
behavior remain outside these private render checks. Account and VM lifecycle
flows keep their existing confirmation and backend boundaries.
