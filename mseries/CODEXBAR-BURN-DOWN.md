# Use-it-before-you-lose-it: suggested work for expiring quota (design, opt-in)

Status: **proposed, not implemented.** Off by default. Nothing here sends a prompt on its own.

## Problem

Subscription quota is use-it-or-lose-it. A weekly window that resets in two hours with 70% left, or a
model-scoped cap (Fable) that is barely touched, is value the owner paid for and will not get back. CodexBar
already knows the numbers (`remaining`, `resetsAt`, upstream `pace`, scoped windows). It does not help turn
spare quota into useful work.

## Behavior

When enabled, CodexBar notices **spare quota that is about to expire** and offers a short list of worthwhile
tasks sized to burn it. The owner picks; CodexBar never starts work unprompted.

1. **Detect.** A window is *burnable* when all hold:
   - `remaining >= minRemainingPct` (default 40) and `resetsAt` is within `withinHours` (default 24 for weekly
     windows, 1 for 5-hour windows);
   - upstream pace says it will not be used up (`willLastToReset` true) so the spare is real;
   - the account is the active one, and the window is not scoped to a model the owner does not use.
2. **Reserve.** Never plan to spend the last `reservePct` (default 15) of any window, and never touch the 5-hour
   window when the weekly window is below its own reserve. The 5-hour window refills, so it is only burned when
   it will reset before the owner next works (quiet hours).
3. **Suggest.** Build 3–5 ranked suggestions from local, already-readable context only (see below), each with an
   estimated token cost, the model it needs (Sonnet, Fable, Codex…) and the window it draws from.
4. **Offer.** A quiet line on the provider card ("Fable: 55% left, resets in 6h · 3 ideas"). Clicking opens a
   list. Each item has **Copy prompt** and **Open in terminal** (`claude`/`codex` in the project directory).
   Optional notification once per window, at most one per day.
5. **Record.** Dismissed ideas are not repeated for that reset cycle.

Fable and other model-scoped windows are matched to ideas that actually need that model (long-context
review, large refactors, design docs); Sonnet-only spare goes to routine work (tests, docs, cleanup).

## What makes a suggestion "valuable"

Ranked by, in order: unfinished work the owner already started, then cheap-to-verify wins, then exploration.

- Repos with uncommitted changes or stale branches (`git status`, last commit age) → "finish/review this".
- Open TODO/FIXME clusters and failing or missing tests → "add tests for X", "fix the failing suite".
- Recent Claude Code / Codex session endings that stopped mid-task (`codexbar-sessions.py`,
  `codexbar_claude_history.py` handoff summaries) → "resume with the saved summary".
- Docs, audits and dependency/security reviews that have not run in N days (`mseries/upstream-audits/`).
- Fallback: a user-maintained backlog file (`~/.config/codexbar/burn-backlog.md`), one task per line.

A suggestion carries: title, project path, a ready-to-paste prompt, expected tokens (from the owner's own
history for similar tasks), model, and *why now* ("resets in 5h").

## Settings (`wingpanel.json`, all optional)

| Key | Default | Meaning |
|---|---|---|
| `burnSuggestions` | `false` | Master switch. Also a toggle in Settings → Panel. |
| `burnMinRemainingPct` | `40` | Spare needed before suggesting. |
| `burnWithinHours` | `24` | How close to reset a weekly window must be. |
| `burnReservePct` | `15` | Never plan to spend below this. |
| `burnNotify` | `false` | One notification per window, max one per day. |
| `burnProviders` | `["claude","codex"]` | Which providers participate. |
| `burnQuietHours` | `22:00–07:00` | When 5-hour windows may be counted as spare. |

## Guardrails (non-negotiable)

- **Opt-in and manual.** No auto-run in v1. A future "run unattended" mode would need its own switch, a hard
  token ceiling per run, and a visible kill switch; it is out of scope here.
- **Local context only.** Suggestions read git metadata, session summaries and the backlog file already on the
  machine. File contents, secrets and transcripts are never sent anywhere by CodexBar itself, and the prompt is
  shown to the owner before it is copied or launched.
- **Never spend what hurts.** Reserve rules above; unknown, stale or expired windows produce no suggestion
  (same rule as `account_headroom`).
- **Honest numbers.** Costs are estimates labelled as such; subscription quota is not dollars.
- **Quiet.** One line, no badges, no repeated nags; disappears when the window drops below threshold.

## Implementation sketch

- `codexbar_burn.py`: pure functions `burnable_windows(snapshot, prefs, now)` and `rank(ideas)`, with an
  `ideas()` collector over git, session history and the backlog. Cached in `codexbar_cache` (60 s TTL).
- `codexbar-burn.py` helper (JSON on stdout, like `codexbar-sessions.py`), called when the popover opens and
  only when `burnSuggestions` is true, so the default path costs nothing.
- `Indicator.vala`: one subtle line and a popover list reading the helper's JSON via `JsonBoundary`.
- Tests: `test-codexbar-burn.py` (threshold, reserve, scoped-window matching, stale/expired exclusion,
  dismissal, no secrets in output); a probe fixture for the card line.

## Open questions

- Should 5-hour windows ever be suggested outside quiet hours? (Proposed: no.)
- How to estimate tokens per idea: owner history medians vs. a fixed small/medium/large scale?
- Does Codex expose enough pace data to treat it the same as Claude, or only percent and reset?
