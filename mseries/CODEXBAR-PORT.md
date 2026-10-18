# CodexBar custom port: what we add and how to repeat it on an upstream bump

We run upstream [steipete/CodexBar](https://github.com/steipete/CodexBar) (Linux ARM64 CLI + Qt desktop,
pinned in `mseries/install-codexbar.sh`) and add an elementary OS layer. **Never replace our files with stock
ones.** Upgrade by re-pinning, re-installing upstream, and re-verifying each item below.

## What is ours (all in `mseries/`)

| Piece | File(s) | Depends on upstream |
|---|---|---|
| Wingpanel indicator (native popover: dense cards, company marks, account line, bottom bar with freshness, dock and refresh) | `codexbar-wingpanel/` (`Indicator.vala`, `Presentation.vala`, `QuotaEta.vala`, `icons/`) | `codexbar-linux --snapshot` JSON (schemaVersion 1: `entries[].windows[]`, `spending`, `stale`, `busy`) and the `--refresh/--usage/--spending/--settings/--quick-view` actions |
| Native Settings window (replaces upstream's Qt one; Fusion is hard-coded there so it can't be themed). Same `linux.json` keys, applied live through `codexbar-linux --configure`; opened by the panel's Settings button (`~/.local/bin/codexbar-settings`) | `codexbar-wingpanel/settings/` (`SettingsModel.vala` with tests, `SettingsApp.vala`), `probe/run-settings-probe.sh` | `linux.json` keys and validation in `DesktopController.cpp` (`validate`/`loadSettings`), `--configure`, `--autostart`, `codexbar config providers/enable` |
| Wrapper that passes an explicit OpenCode Go key, or the active unexpired OpenCode v2 OAuth access token (read-only `credential` table; never copies/refreshes it) | `codexbar-opencode-wrapper.py` → `~/.local/bin/codexbar` | `codexbar-upstream` CLI path under `~/.local/lib/codexbar-cli/` |
| Sessions helper | `codexbar-sessions.py` | none (reads local data) |
| OpenCode local usage + account email | `codexbar-opencode-local.py` | none (reads `opencode.db` read-only) |
| Codex multi-account switcher (upstream's is macOS-only) | `codexbar-accounts.py` | upstream `codexbar usage --provider codex` honoring `CODEX_HOME` |
| OpenCode Go sign-in (upstream imports opencode.ai cookies only on macOS): native WebKit window, saves the `auth`/`__Host-console_session` session as `providers[opencodego].cookieSource=manual` + `cookieHeader`; the panel's OpenCode **+** runs it | `codexbar-opencode-login.py` | config path resolution (`CodexBarConfigStore.defaultURL`), `OpenCodeWebCookieSupport` cookie names, `usage --source web` |
| Claude CLI accounts via claude-swap, plus native Claude desktop sessions. CLI only keeps the app login separate; Switch both validates the target session, quits the native app, saves its final encrypted session, merges the target login without changing preferences, switches the CLI, and relaunches the app. Set up app preserves the previous session and locally clears the login for one-time sign-in without sending a logout request. Save app login and automatic list capture remember it. | `codexbar-claude.py`, venv `~/.local/share/claude-swap-venv`, `cswap` | claude-swap `list/status/switch --json`, `schemaVersion` 1, `to.email`, `reason: already-active`, `configs/.claude-config-*.json`; installed Claude `config.json` keys `lastKnownAccountUuid`, `oauth:tokenCache`, `oauth:tokenCacheV2`, SQLite `Cookies` (or `Network/Cookies`), `gtk-launch com.anthropic.Claude` |
| Installers / deploy / CI | `install-codexbar.sh`, `install-codexbar-wingpanel.sh`, `deploy-codexbar.sh`, `check-codexbar-port.sh`, `.github/workflows/validate-mseries.yml`, `enhance.sh` payload list | version pin `version=vX.Y.Z` |

## Upgrade checklist

1. Read the upstream release notes between our pin and the new tag (`gh release list -R steipete/CodexBar`).
2. Bump `version=` in `install-codexbar.sh`. Download both tarballs to a scratch dir and verify `sha256`.
3. Run `bash mseries/check-codexbar-port.sh` against the new CLI (set `CODEXBAR_CLI=<scratch>/codexbar`). It checks the
   pieces we depend on and prints what still needs a human look.
4. Install: `bash mseries/install-codexbar.sh --skip-system-deps`, then `bash mseries/deploy-codexbar.sh` (restarts
   Wingpanel and the app).
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
