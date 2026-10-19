# CodexBar custom port: what we add and how to repeat it on an upstream bump

We run upstream [steipete/CodexBar](https://github.com/steipete/CodexBar) (Linux ARM64 CLI + Qt desktop,
pinned in `mseries/install-codexbar.sh`) and add an elementary OS layer. **Never replace our files with stock
ones.** Upgrade by re-pinning, re-installing upstream, and re-verifying each item below.

## What is ours (all in `mseries/`)

| Piece | File(s) | Depends on upstream |
|---|---|---|
| Wingpanel indicator (native popover: dense cards, company marks, account line, bottom bar with freshness, dock and refresh) | `codexbar-wingpanel/` (`Indicator.vala`, `JsonBoundary.vala`, `Presentation.vala`, `QuotaEta.vala`, `icons/`) | `codexbar-linux --snapshot` JSON (schemaVersion 1: `entries[].windows[]`, `spending`, `stale`, `busy`) and the `--refresh/--usage/--spending/--settings/--quick-view` actions |
| Native Settings window (replaces upstream's Qt one; Fusion is hard-coded there so it can't be themed). Same `linux.json` keys, applied live through `codexbar-linux --configure`; opened by the panel's Settings button (`~/.local/bin/codexbar-settings`) | `codexbar-wingpanel/settings/` (`SettingsModel.vala` with tests, `SettingsApp.vala`), `probe/run-settings-probe.sh` | `linux.json` keys and validation in `DesktopController.cpp` (`validate`/`loadSettings`), `--configure`, `--autostart`, `codexbar config providers/enable` |
| Wrapper that follows the active OpenCode v2 OAuth account, with a legacy Go key fallback (read-only `credential` table; never copies/refreshes it) | `codexbar-opencode-wrapper.py` → `~/.local/bin/codexbar` | `codexbar-upstream` CLI path under `~/.local/lib/codexbar-cli/` |
| Shared helper cache and locks (polling limits: per-answer TTL, exponential backoff on failure, last-good data kept, private `0600` files under `~/.cache/codexbar-mseries`; one `flock` around Codex sign-in writes) | `codexbar_cache.py` | none |
| Sessions helper (incremental transcript index: only changed files are parsed) | `codexbar-sessions.py`, `codexbar_tokens.py` | none (reads local data) |
| OpenCode local usage, account plans and switching | `codexbar-opencode-local.py` | reads `opencode.db` read-only; activates via `opencode auth switch opencode <credential-id>` |
| Codex multi-account switcher (upstream's is macOS-only) | `codexbar-accounts.py` | upstream `codexbar usage --provider codex` honoring `CODEX_HOME` |
| OpenCode Go sign-in (upstream imports opencode.ai cookies only on macOS): native WebKit window, saves the `auth`/`__Host-console_session` session as `providers[opencodego].cookieSource=manual` + `cookieHeader`; the panel's OpenCode **+** runs it | `codexbar-opencode-login.py` | config path resolution (`CodexBarConfigStore.defaultURL`), `OpenCodeWebCookieSupport` cookie names, `usage --source web` |
| Claude CLI accounts via claude-swap, plus native Claude desktop sessions. CLI only keeps the app login separate; Switch both validates the target session, quits the native app, saves its final encrypted session, merges the target login without changing preferences, switches the CLI, and relaunches the app. Set up app preserves the previous session and locally clears the login for one-time sign-in without sending a logout request. Save app login and automatic list capture remember it. | `codexbar-claude.py`, venv `~/.local/share/claude-swap-venv`, `cswap` | claude-swap `list/status/switch --json`, `schemaVersion` 1, `to.email`, `reason: already-active`, `configs/.claude-config-*.json`; installed Claude `config.json` keys `lastKnownAccountUuid`, `oauth:tokenCache`, `oauth:tokenCacheV2`, SQLite `Cookies` (or `Network/Cookies`), `gtk-launch com.anthropic.Claude` |
| Claude local Code context carry-over | `codexbar_claude_history.py`, [design/evidence](CODEXBAR-CLAUDE-HISTORY.md) | installed Claude desktop account/org Code index and local `.claude/projects` transcripts; private exports and create-only imports after app exit |
| Installers / deploy / CI | `install-codexbar.sh`, `install-codexbar-wingpanel.sh`, `deploy-codexbar.sh`, `check-codexbar-port.sh`, `.github/workflows/validate-mseries.yml`, `enhance.sh` payload list | version pin `version=vX.Y.Z` |

## Upgrade checklist

1. Read the upstream release notes between our pin and the new tag (`gh release list -R steipete/CodexBar`).
2. Bump `version=` in `install-codexbar.sh`. Download both tarballs to a scratch dir and verify `sha256`.
3. Run `bash mseries/check-codexbar-port.sh` against the new CLI (set `CODEXBAR_CLI=<scratch>/codexbar`). It checks the
   pieces we depend on and prints what still needs a human look.
4. Install: `bash mseries/install-codexbar.sh --skip-system-deps`, then `bash mseries/deploy-codexbar.sh` (stages
   the native module for next login and preserves the running panel/daemon).
4b. On an upstream bump diff `Integrations/Linux/DesktopController.cpp` (settings defaults and `validate`) and `qml/SettingsWindow.qml` between the old and new tags; add any new setting to `SettingsModel.vala` and the window, and drop removed ones.
5. Re-run `bash mseries/check-codexbar-port.sh` (no env) against the live app: it now also compares the running
   app's `--snapshot` against the panel's fixture schema.
6. If upstream changed the snapshot schema, update `Indicator.vala` and `probe/fixtures/` first, rebuild, run the
   headless probe (`probe/run-probe.sh`), and only then push.
7. If upstream starts reporting a provider we draw ourselves (a `claude` entry), our card steps aside; check for double cards.
8. Record the pin, what was re-verified and what was not in `OS9-HANDOFF.md`; push; run `deploy-codexbar.sh`.

## Do not lose

- Our helpers are installed from this repo by the installers and the deploy script; the installer does not delete user config.
- `~/.local/bin/codexbar` is the wrapper, not upstream's binary (upstream's CLI is `codexbar-upstream`).
- Account stores: `~/.local/share/codexbar-mseries/codex-accounts` (private, 0600) and claude-swap's own store. Never commit these.

Quota and account cards, like the top-panel readout, always order Codex first, Claude second, OpenCode Go third.

## Polling and cache

Who polls what, so a new feature does not quietly add requests:

| Source | Runs | Limit |
|---|---|---|
| `codexbar-linux --snapshot` (local IPC, upstream owns provider fetching) | panel timer | 5 s while the popover is open or a refresh runs, 30 s otherwise |
| `codexbar-accounts.py usage` (saved Codex accounts; the active one comes from the snapshot) | popover open | cached 15 min per account, parallel, `--force` from the Refresh button |
| `codexbar-claude.py list` | popover open | cached 2 min, cleared by any other Claude command |
| `codexbar-sessions.py`, `codexbar-opencode-local.py` | popover open | local reads; transcripts are re-parsed only when their size or mtime changed |
| Everything above with the popover closed | background tick | every 15 min |

`codexbar_cache.py` owns the on-disk cache (`~/.cache/codexbar-mseries`, `0700`/`0600`), the failure backoff (60 s doubling
to 1 h, last good answer kept and flagged `stale`) and the `flock` helper. `python3 ~/.local/lib/codexbar-cli/codexbar_cache.py status`
prints how old each cached answer is and what is failing. Credential writes (Switch, Save, Add) share one lock in
`codexbar-accounts.py`; never run the Codex CLI against the live `~/.codex` from a poller, because a token refresh can
rewrite `auth.json` while a switch is replacing it.

## Native Claude app accounts

Use **Switch → Set up app** once for a saved CLI account that says **app sign-in needed**. This restarts
Claude at its sign-in screen after saving the current app session locally. Sign in to the selected account
in the native app and choose **Save app login** in CodexBar. Use **Switch → Switch both** afterwards to
switch the native app and CLI together. Finish running Claude work before accepting the restart dialog.
If setup is cancelled, Switch both to the previous saved account restores it.

The same-machine store is `~/.local/share/codexbar-claude-app` (0700); each `<accountUuid>.json` (0600)
atomically bundles encrypted cookies (SQLite backup including WAL, normalized to a standalone database)
and only the three app identity/token-cache keys. Nothing is decrypted or returned in listing output.
The app is stopped before restoration; stale SQLite sidecars are removed, preferences are merged, and
failed restoration attempts roll back to the original session. A missing/corrupt target leaves the app
and CLI untouched. Setup recovery uses `pending-login.json`. Do not commit or sync this private store.
Sessions can expire or be revoked by the service; sign in again in that case. `desktopReady` means a
structurally valid snapshot exists, not a server-side authentication check. Keep the app storage format
and its Linux executable path under review on Claude desktop updates.

OpenCode's quota remains account-wide; the token count beside it is the seven-day history from this
machine across its local OpenCode Go accounts, labelled separately. OAuth credentials stay in OpenCode's
database; expired credentials are ignored (with a 60-second margin), and OpenCode handles refresh.

### Native sign-in persistence and process lifecycle

A safeStorage OAuth cache alone is insufficient for the native chat surface. Snapshots require its
`sessionKey` cookie; **Save app login** waits up to 35 seconds for Electron to persist new cookies
([Electron Cookies API](https://www.electronjs.org/docs/latest/api/cookies)). A login is not labelled
app-ready until the complete cookie snapshot is on disk. Keep Claude open while that initial save runs.

On Linux Chromium may rewrite its command line into argv[0]. Stop detection uses the process parent
tree to signal only the main app, then waits for all app processes to exit. Restart uses detached
`gtk-launch` with closed standard streams and verifies the app process, avoiding inherited-output-pipe
hangs. The owner confirmed a real account-2 → account-1 native round trip retains the Gmail account's
chats without another sign-in after these fixes.

## Dense alternate-account quotas and adding Codex accounts

Alternate Claude and Codex accounts show separate **5H** and **7D** percentages with `↻` reset
countdowns. Saved distinct OpenCode OAuth accounts also show **30D** when supplied. Short-window
exhaustion is never hidden behind a healthy weekly/monthly balance. The main panel prioritizes the
five-hour window; a compact second line shows alternate accounts, numbered with identities in the
tooltip. Dropdown account rows keep the email and Switch action above their compact quota summary.
Countdowns update during normal polling without rebuilding the open dropdown. Refresh updates the
account helpers too. Providers expose quota percentages, not an absolute remaining-token balance.

`codexbar-opencode-local.py accounts` reads saved OpenCode credentials read-only and obtains quota
for distinct inactive accounts without activating them. Duplicate sessions for the same account and
workspace are collapsed, with the active record preferred. Tokens stay in process memory/environment;
output only contains account identities, quota windows, and actionable errors. The active account's
quota remains supplied by upstream's snapshot. Currently the two saved OpenCode login records on this
machine belong to the same account/workspace and appear once.

Codex **+** opens `AccountDialog.vala`, a Granite account sheet with a raised provider mark, clear title, theme-accented instruction rows and native response buttons, a browser sign-in action,
inline progress/result, retry and cancellation. `codexbar-accounts.py login` finds the CLI on PATH or
bundled with the desktop app, starts official `codex login` in a private temporary `CODEX_HOME` with
file credential storage, and saves the result into the account store. It never replaces the live
Codex auth file. Cancellation terminates the login child and removes temporary credentials. Initial
Claude **+** starts the existing browser sign-in helper directly, without a confirmation popup. OpenCode **+** launches the native API-key window directly, without an intermediate Continue confirmation; the helper/result flow remains intact. Codex waiting/success/retry states share the visual hierarchy, keyboard defaults and bounded selectable detail. The OpenCode API-key window also uses a Granite sheet with the same emblem, theme accents, framed sections and native Cancel/Connect buttons. Its masked entry, browser/passkey path, key validation/storage and built-in sign-in fallback remain available. A spinner accompanies validation and failed checks restore the editable field. Run `probe/render-opencode.py OUT.png [initial|busy|error]` under Xvfb with the elementary light/dark theme to preview it without authentication. Render with `CB_DIALOG=codex|claude|opencode|codex-wait|codex-success|codex-error` through `probe/run-probe.sh`; these modes never run real sign-in helpers.
Official login/storage reference: https://learn.chatgpt.com/docs/auth .

Secondary quota values use the same theme success/warning/error colours and thresholds as the usage
bars: over 25% green, 10–25% amber, at most 10% red. Each window is coloured independently; a red
5-hour value and a green weekly/monthly value can appear together. Reset times remain muted and are
not the sole indicator of quota state; labels and percentages remain explicit.

## Account recommendation and weekly-reset badges

A yellow **★** marks the service and account with the most usable reported quota. Services report
percentages rather than comparable absolute token budgets, so the score is the account’s lowest
remaining percentage across its reported windows. An empty five-hour window cannot win based on a
large weekly balance. All exact positive ties are marked; there is no star when every account is
exhausted or unknown. Stale accounts, unknown balances and windows awaiting a past reset are excluded.

A red **!** independently marks the service and account with the earliest upcoming **7-day** reset.
Monthly and five-hour resets are excluded. All exact reset-time ties are marked. It identifies the
next weekly reset even if that reset is still days away; its tooltip gives the account and local date.

Badges appear in provider headers, saved-account rows and the compact panel. A provider-level badge
can refer to a secondary account; the matching row carries the same marker and the tooltip names it.
Selection is recomputed from existing data during normal polls, with no additional API calls or
account switching. Changing winners or passing a reset time updates the markers without waiting for
new quota data.


### Account plan badges

Dropdown identities show compact reported-plan pills for active and saved accounts. Codex uses its
existing per-account plan claim; Claude reads only known subscription labels from its live/saved
Claude Code login metadata, returning no credential fields. OpenCode uses the upstream active plan
or per-account plan metadata when supplied. Missing or unreadable plans say **Plan unavailable**;
quota size and the active account's plan are never used to guess another account's subscription.
Known-plan tooltips say “Reported plan” because saved login metadata may be cached.

OpenCode OAuth accounts now obtain the current workspace product from the official Console's
`GET /console/api/go/status`, using that account's bearer token and `x-org-id`. Current Go/Go Plus
access is labeled from `product` and an unexpired `access.endsAt`; scheduled `renewalProduct` and
quota limits do not determine the badge. The verified helper product overrides upstream's generic
“Go” provider label. Missing/unreadable data remains unavailable (or uses existing reported metadata).
Requests allow only the official Console host, block redirects, limit response size and use an
eight-second timeout. No token refresh, login switch or credential/database write is performed.
[OpenCode Go plans](https://dev.opencode.ai/v2/docs/console/go/) describe the public level names.

`CB_HIDE_PANEL=1 CB_SCROLL=end probe/run-probe.sh ...` renders the dropdown at its normal width,
scrolled to the last provider, for checking secondary-account badges in light/dark themes.


### OpenCode account switching

Saved secondary OpenCode browser accounts have a **Switch** button. The helper validates the selected
credential belongs to the `opencode` integration, runs the official `opencode auth switch opencode ID`
through its normal service, and confirms the requested credential is the sole active selection. The
helper never edits SQLite directly or exposes CLI credential output. The native OpenCode service owns
activation notifications and OAuth refresh. Expired access with saved refresh credentials remains
switchable; unusable sign-ins have a disabled button and a sign-in hint. Workspace names distinguish
choices where available, and duplicate sessions for one account/workspace remain deduplicated.

CodexBar refreshes the account list, identity, plan and usage after switching, discarding older pending
helper responses. Identity and quota credentials follow the v2 active selection rather than legacy
`account_state`/`auth.json`. Legacy keys remain a fallback when no usable v2 selection exists; an
explicit `OPENCODE_API_KEY` environment override retains precedence. While OpenCode refreshes a selected
OAuth token, the wrapper keeps that identity rather than substituting a legacy account.

OpenCode **+** now offers **Sign in with browser** in the native Connect sheet, alongside API-key
setup and the built-in quota-only sign-in. It runs the official
`opencode auth login opencode --method device --answer server=https://opencode.ai/console`, opens
only the validated official device approval URL, and displays the approval code. Choose the other
browser account/workspace; an existing browser session may need signing out first. OpenCode owns
credential storage and makes the new account active. CodexBar verifies the active identity and that
all previous saved credential IDs remain, then refreshes dropdown accounts, plan and usage. Signing
into an already saved identity gives a retry message instead of claiming another account was added.
No credentials or raw CLI logs are shown. Cancel interrupts the pending native authorization; a
ten-minute timeout handles abandoned attempts. Repeated panel clicks cannot start parallel helpers.

`test-codexbar-opencode-login.py` covers new/duplicate identities, workspace choices, preservation,
URL validation, cancellation, failure privacy and read-only metadata. Run
`probe/render-opencode.py OUT.png browser` for the waiting sheet. OpenCode v2.0.32 produced the
expected approval URL in a live begin/cancel smoke test with saved IDs preserved; a real distinct
second-account authorization still requires owner browser approval. Account activation was checked with OpenCode v2.0.32,
including a live same-account saved-session round trip with the original selection restored.
[Official account commands](https://dev.opencode.ai/v2/docs/cli/commands/) document the activation API.

### Switch lifecycle

ChatGPT's panel Switch uses `codexbar-accounts.py switch <exact-id> --desktop`: confirms before editing,
closes only the current user's ChatGPT executable, saves the departing login, swaps auth under the state lock,
and reopens ChatGPT. Avoid signing out/revoking saved credentials, which would break fast switching.
Claude's installed-app Switch uses `switch <number> --desktop` after confirmation. CodexBar stays running during
both. Routine deployment stages the native module for next login; an explicit `--restart` reloads
Wingpanel while preserving the running CodexBar daemon.

### Wingpanel display preferences

Use the popover gear > **Display > Wingpanel**. Percentage and reset-time switches control quota text in the
bar and menu. Other-account rows and hints can be hidden in the panel bar separately. Tooltips and progress-bar
accessible names retain full quota information. Local options live in `~/.config/codexbar/wingpanel.json`, loaded
by `PanelPreferences.vala`, and are never sent to upstream `--configure`. A directory monitor handles atomic file
replacement and updates cached widgets immediately, without provider requests. Preferences default to enabled;
malformed files retain the last valid values and the Settings window reports save errors.

Build/run `test-live-preferences` via `probe/run-live-preferences.sh BUILD_DIR` to check live changes against
isolated backends. For render variants, pass `CB_DISPLAY_PREFS=/absolute/path/to/wingpanel.json` to `probe/run-probe.sh`.

### Claude conversation continuity

Claude desktop keeps its Code sidebar per account and organization, even though Code transcripts remain locally
available across logins. `codexbar-claude.py` now exports local Code context after exit, restores the selected app
login, imports only missing sidebar records into its selected organization, and then switches the CLI/reopens Claude.
Existing destination history is untouched. See [Claude Code history](CODEXBAR-CLAUDE-HISTORY.md) for backup locations,
the read-only `history-preview` command, the inspected Claude app revision, and the remaining real-switch check.

### Deploy without interrupting the menu bar

`bash mseries/deploy-codexbar.sh` installs helpers, settings and the native module without restarting Wingpanel or
quitting CodexBar. Helpers load on their next invocation; the module loads at next login. `--no-restart` remains an
alias for the safe default. Use `--restart` only for an intentional panel reload or recovery from a confirmed defect;
it reloads Wingpanel and leaves a running CodexBar daemon alone. Do not call a staged module “running” before reload.

`probe/run-switch-probe.sh BUILD_DIR [success|null|array|invalid]` exercises the actual Switch row, delayed confirmation
and async result with a fake backend in an isolated desktop. It reproduces the freed-argument-array crash before the
owned account-ID fix. Meson registers all four cases when Xvfb/DBus are installed, so ordinary deploy checks and
`check-codexbar-port.sh` run them before installing a build. `test-codexbar-deploy.py` checks that
routine deployment cannot signal the live panel or quit the daemon.

### Defensive JSON boundary

`JsonBoundary.vala` checks every external snapshot/helper JSON root and nested rendered collection before
native code reads it. Checked optional getters preserve defaults for absent/null fields. Validation rejects
wrong types/elements and caps traversal depth/work; unknown keys remain compatible. Five isolated Switch
interactions and the malformed-refresh/recovery probe are registered with Meson when Xvfb and D-Bus are
available. The ingestion probe treats GLib criticals as failures and reproduced a null-session assertion
on the previous code. Tests use private fake profiles and never signal real apps or change real accounts.
Claude Switch additionally requires helper exit success. No polling intervals changed.

### Compact OpenCode panel rows

All three providers share compact panel text (7.5 pt quota, 7 pt reset, 6.75 pt second row). With one
saved account and account quota available, its local seven-day token count occupies the lower row.
With alternate accounts, that row keeps their quotas instead; local usage remains in the tooltip and
popover. `probe/run-probe.sh BUILD OUT light opencode-compact connected` previews both cases.

### Seven-day local processed tokens

Every provider has a `7d` total sourced from `codexbar-sessions.py`. These are rolling local
coding-activity estimates across accounts/providers on this machine, not remaining plan tokens or
ordinary ChatGPT/claude.ai chat totals. Input, output and cache reads/writes are included. Codex
cached-input and reasoning-output breakdowns are already included in its totals; OpenCode's fallback
components are disjoint; Claude exposes cache categories separately. Shared `codexbar_tokens.py`
implements those rules and is required by both local helpers.

The Codex reader caches changed-file usage observations from `.codex/sessions` and `archived_sessions`,
with the existing 4,000-file/30-day scan bounds. Repeated cumulative observations and copied history
are deduplicated. A resumed counter without last-call usage establishes a baseline rather than
counting a whole lifetime as new use; missing history can undercount. Claude's `claude-transcripts-v2`
cache replaces the old cache-excluding definition. Caches remain private JSON under
`~/.cache/codexbar-mseries`; no credentials or message content are copied. Existing helper polling
remains 60 seconds while open (15-second freshness on opening) and 900 seconds while closed.
Cached session updates repaint the panel directly, without an extra upstream snapshot/refresh.
Totals share the second row with alternate accounts, respect percentage visibility, and remain
explained in Settings > About. Provider tooltips retain the concise totals. The local-token native probe checks all three and bar height.

Routine deployment leaves identical provider marks and the global icon cache untouched. Rebuild the
icon cache only when the SVG contents actually change, to avoid needless invalidation of the live panel.

### Wingpanel popup anchor lifetime

`install-wingpanel-codexbar-left.sh` applies `patches/wingpanel-popover-lifetime.patch`
to the pinned Wingpanel core in addition to the full-height/notch and clock-right patches.
It retains a removed menu anchor until its popup is detached on switch/close. This fixes
a reproduced use-after-finalization defect; see [crash evidence and tests](CODEXBAR-CRASH-2026-10-18.md).
The installer stages the binary without restarting the live panel. Run
`bash mseries/wingpanel-tests/run-popover-lifetime.sh` for the isolated four-case regression.

### Performance boundaries and the quiet panel watch

See [the 2026-10-18 audit](CODEXBAR-PERFORMANCE-AUDIT-2026-10-18.md) for measurements,
remaining modularity work and activation limits. Shared `codexbar_history.py` streams
OpenCode's displayed 30-day windows, with read-only queries and no new app DB indexes.
`HelperProcess.vala` bounds disposable native read helpers; account actions retain their
existing lifecycle. Helper completion repaints cached cards without extra snapshot IPC.
Install/deploy/image payloads must include both `codexbar_history.py` and the token module.

`python3 ~/.local/lib/codexbar-cli/codexbar-wingpanel-watch.py` reports panel/launcher
health and new categorized journal/core events using a private bounded checkpoint.
It never controls processes. The owner's five-minute chat heartbeat consumes that report
and stays quiet while unchanged. Retain the distinction between an unexplained PID
transition and a confirmed crash. The heartbeat requires the app/host to be available;
it is not a continuous availability guarantee.

### Token-first ChatGPT/Codex and Claude rows

When seven-day totals are available, ChatGPT/Codex and Claude show them beside the
provider mark on the top row. Active quota/reset details and alternate accounts share
the second row. OpenCode retains its quota-first order. The native token probe checks
vertical ordering and the two-row height; display preferences and missing-data fallbacks
remain supported. As with other native changes, routine deployment stages this layout
for next login without reloading a healthy panel.

ChatGPT/Codex and Claude's token-first heading also includes the active seven-day
percentage and its reset countdown. Five-hour and alternate-account details remain
on the lower row. The token probe asserts the weekly values share the token heading.

## Saved OpenCode account cache and display density

Saved-account console plans use a 3600-second cache and inactive quota uses 300
seconds, scoped to database/account/workspace/sign-in identity. Manual Refresh
bypasses both. Reset boundaries invalidate cached quota; failures back off and
retain sanitized last-good values with a stale marker. The active account uses
the upstream snapshot. Credential inventory stays live; no credentials or raw
provider responses are persisted. Shared private JSON cache/locks require no new
database or service.

Native Display settings persist `showTokens` (default true) and `compactQuota`
(default false) in Wingpanel's own preferences. Dropdown token counts remain
available when hidden from the bar. Compact active quota dots show remaining
balance (>70 green, 25–70 yellow, <25 red, percentage visible below 10); hover
reports the measured percentage. Popup quotas stay literal; alternate bar accounts use matching dots with full values on hover.
Menu bar marks use 13px; card marks retain their existing size.

In visual dot mode, reset countdowns are hover-only on both bar rows, regardless
of the literal-mode reset visibility preference. Active dot hover reports the
measured percentage and reset state; alternate-account hover retains every window.
The dropdown and literal mode still honor the existing reset preference.

Explicit Claude desktop switches always stop/restore/relaunch after target
validation, even when local account UUID hints match. Persisted identity hints
and process existence do not verify the account authenticated by the main UI.

Compact bar rows group by account: active 5H and 7D share the top row; alternate
account windows share the lower row. Token location remains independently set.

Numeric dot-mode percentages now appear below 15% in bold red (superseding the
earlier below-10 rule). The green/yellow/red dot thresholds are unchanged.

## Claude switch handoff extension

Ship codexbar_claude_handoff.py alongside the history helper in installers, deploy
and image payloads. Cross-account app Switch saves a private brief before auth
changes and registers a fresh handoff-only Code conversation. A45-second tool-free
Claude Code safe-mode call summarizes recent visible text; unavailable/mismatched
login or exhausted quota produces labeled emergency excerpts. Originals stay intact.
The native completion dialog offers a local GitHub review window. Only its explicit
Publish action sends edited text to the workspace origin in a separate branch/draft
PR. Emergency excerpts never automatically become public. No extra polling/service.
See CODEXBAR-CLAUDE-HISTORY.md for qualifications and limits.

Dot-mode numeric visibility is inclusive: remaining<=15% displays the written
percentage in bold red; values above15% stay dot-only. This supersedes earlier
below-15 wording and applies consistently to all provider/account rows.

Dropdown quota bars and percentage labels use the same visual thresholds as the
menu dots: green >70%, yellow25–70%, red<25%. The shared visual formatter is
separate from ETA/alert warning thresholds.
