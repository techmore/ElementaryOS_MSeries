---
name: elementaryos-mseries-ui-specialist
description: Build, edit, and review consistent native UI in the ElementaryOS_MSeries project using its GTK 4, Granite 7, Wingpanel, and Switchboard patterns. Use for project screens, settings, indicators, interaction states, and UI consistency reviews.
---

# M-Series UI Specialist

Create a coherent elementary OS experience across the project's apps, settings,
and menu bar. The owner values Apple's design standards: use their attention to
clarity, hierarchy, feedback, consistency, and craftsmanship as a quality bar,
expressed through the native elementary OS toolkit.

## Start from the actual surface

Locate the active ElementaryOS_MSeries checkout; read its `AGENTS.md` and current
`mseries/OS9-HANDOFF.md`. Resolve all `mseries/...` paths below against that
checkout, not this skill's installation directory. If no checkout is available,
request its location before making project-specific edits.

Read [toolkit-and-screens.md](references/toolkit-and-screens.md) for the relevant
screen family, then inspect its current code and build dependencies. The listed
revision is an inspection baseline, not a substitute for the active branch.

Read [ui-conventions.md](references/ui-conventions.md) when designing or reviewing
layouts, controls, asynchronous states, text, or accessibility.

Read [sources-and-apple-guidance.md](references/sources-and-apple-guidance.md) for
source attribution, the original **swiftui-specialist** skill, Apple HIG, and how
to translate those references without importing SwiftUI-specific rules.

## Working approach

- Choose the closest existing screen family and name the components or helpers
  being reused. Existing helpers are mostly local to individual apps; inspect
  their ownership and dependencies before extracting a shared implementation.
- Match the surface's toolkit and host conventions. GTK 4 + Granite 7 is the
  common baseline; Work Mode already uses libadwaita inside Switchboard. Preserve
  intentional exceptions and user-requested product direction.
- Distinguish observed conventions from new recommendations. Existing hardcoded
  colors, small text, crowded headers, or missing translations are review targets,
  not an approved design system merely because they appear in source.
- Keep UI state backed by its existing model/service. Preserve account, selection,
  focus, and scroll position through updates; handle pending, stale, unavailable,
  empty, and failed states without presenting unknown data as zero or success.
- Make the requested change at its natural scope. A consistency fix does not
  require a toolkit migration, global theme rewrite, or new shared library.

## Validate the changed experience

Read [review-and-validation.md](references/review-and-validation.md) and choose
checks for the changed surface. Review layout in light/dark modes, long text and
small windows, plus keyboard and accessible names for changed controls. Use
existing isolated fixture probes where available.

Report concrete findings and checks, distinguishing source inspection, successful
builds, screenshot review, interaction tests, and live hardware verification.
Preserve the owner's panel stability and the repository's deployment rules.
