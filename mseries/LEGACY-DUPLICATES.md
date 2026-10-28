# Legacy duplicates (marked, not removed)

Status 2026-10-27. The owner asked to mark duplicate apps and keep the primaries until the system is
stable; legacy code and apps get removed only after that. **Nothing here was deleted, hidden, uninstalled,
archived or moved.** Frozen copies of SDK-owned apps are already marked by
[REPO-OWNERSHIP.md](REPO-OWNERSHIP.md) and [ci/frozen-paths.txt](ci/frozen-paths.txt) (`FROZEN.md` in each
directory); this file references them and does not repeat that work.

Evidence used: what is installed and running on the M1 Pro (`~/.local/bin`, `~/.local/share/applications`,
user units, `ps`), the dock pins (`gsettings get io.elementary.dock launchers`), newest commits, and the
current docs. Where the evidence does not settle it, the row says **undecided** for the owner.

Markers used:

- Repo directory: a `LEGACY.md` banner naming the primary (not added inside frozen paths).
- Installed user launcher: ` (Legacy)` appended to `Name=`; backup of the original kept outside the repo.
- System launchers under `/usr/share/applications` were not edited; they are listed for the owner.

## Groups

| Group | Primary | Legacy duplicates | Evidence | After stabilization |
| --- | --- | --- | --- | --- |
| Claude / T3 client | `rust/claude-pantheon-rs` (SDK repo), launcher `io.github.techmore.ClaudePantheonRs.desktop` "T3" | `mseries/claude-pantheon-native` (Vala/C, `LEGACY.md` added); `com.t3tools.T3Code.desktop` "T3 Code (Beta)" (Electron, Exec points at a missing `/tmp/opencode/...` path; launcher renamed) | Rust T3 pinned in dock, binary rebuilt 2026-10-27; Vala twin not installed, last commit 2026-10-22 | Remove Vala dir and the T3 Code launcher |
| T3 hand-written vs SDK-rendered | **undecided** | `claude-pantheon-sdk` / "T3 Monitor (SDK)" (`rust/claude-pantheon-rs/sdk/t3.msdk`, hidden launcher) | Owner direction: the SDK should build all apps; today the SDK monitor is read-only and the hand-written app is the daily one | Owner picks |
| Claude desktop vs T3 | **undecided** | `com.anthropic.Claude.desktop` (Electron, running and pinned) | T3 was started to replace the Electron client, but both are pinned and in use | Owner picks |
| Messages | **undecided** (deferred by owner) | Python `io.elementary.mseries.Messages` (`mseries/phone-setup/messages.py`, frozen, pinned); Rust `io.elementary.mseries.MessagesRust` "Messages (Rust Preview)" (`rust/mseries-messages`, frozen); `io.elementary.mseries.Conversations` "Messages & Signal" (tab launcher the owner rejected) | [MESSAGING-STATUS.md](MESSAGING-STATUS.md): do not promote the preview or replace the default client without an owner request. Rust is newer; Python is the pinned one | Owner picks; no launcher renamed |
| Signal official client | `signal-desktop.desktop` "Signal Beta" (`~/.local/libexec/mseries-signal-launcher`, accent-synced beta bundle) | `signal-desktop-beta.desktop` (identical, hidden; renamed); `org.signal.Signal.desktop` (Flatpak 8.32 stable, hidden; renamed) | Only `signal-desktop.desktop` is visible; all three beta entries run the same launcher | Remove the duplicate entries and the Flatpak |
| Signal "signal beta.desktop" | keep for now | `signal beta.desktop` (third identical entry, hidden) | Its file name equals the window class `signal beta`, so the dock probably uses it to label the running window; renaming it would show "(Legacy)" on the live app | Owner decides whether to keep it as the window-match entry or fix `StartupWMClass` |
| Signal native vs official | **undecided** | Signal Pantheon (`io.github.sdolbec.SignalPantheonClient`, pinned, signal-cli running) vs official Signal Beta vs Rust Messages Signal channel | MESSAGING-STATUS: Signal Pantheon integration incomplete and deferred | Owner picks |
| Dictation | `mseries-stream-dictate.service` (transcribe.cpp + Parakeet, `mseries/dictation/stream-dictate.py`) | Voxtype (`/usr/local/bin/voxtype`, `voxtype.service`, `install-dictation.sh`, `dictation/config.toml`) | stream-dictate enabled and running; `voxtype.service` disabled and inactive; [dictation/README.md](dictation/README.md) calls Voxtype the fallback. Shared directory, so no banner | Remove Voxtype and its installer |
| Smart Reply | `rust/mseries-reply` (`mseries-reply input-service` running) | First Python bridge: already replaced in place | [SMART-REPLY-DESIGN.md](SMART-REPLY-DESIGN.md) "Rust replaces the Python bridge"; `mseries/smart-reply` now holds the Rust unit only | Nothing left to mark |
| Orchard / Machine Lab | `mseries/orchard` (installed, pinned) | `mseries/orchard-incus` (Python, `LEGACY.md` added); `mseries/machine-lab` and `mseries/orchard-incus-native` (already "has moved" stubs) | Merged 2026-10-21 per [orchard/README.md](orchard/README.md) | Remove all three dirs |
| Assistants | **undecided** (another session owns `mseries-assistant`) | "Desktop Assistant" and "Personal Assistant" run the same code path and profile; "Hermes Assistant (Experimental)" (separate Hermes agent); Newelle (Flatpak `io.github.qwersyk.Newelle`) | `~/.local/bin/mseries-assistant`: `desktop` and `personal` take the same branch | Owner picks after that session lands |
| Discord | **undecided** | `discord.desktop` (Vesktop, native arm64) vs `discord-official.desktop` (official x86 under muvm) | Both installed, neither pinned | Owner picks |
| Disk Space / Updates / Power / granite-smoke | SDK repo (`techmore/mseries-sdk-apps`) | Already removed from this repo by PR #646 | [REPO-OWNERSHIP.md](REPO-OWNERSHIP.md) "Removed from this repo" | Done |
| Torrential | `rust/torrential` (SDK repo, new id `org.techmore.mseries.Torrential`) | `mseries/torrential-native` packaging (old id `com.github.davidmhewitt.torrential`) | REPO-OWNERSHIP: "confirm what native/port material is still needed" | **undecided**; no banner |
| Restore Application Windows | `/usr/share/applications/mseries-restore-windows.desktop` | `~/.local/share/applications/mseries-restore-windows.desktop` (byte-identical shadow) | Same desktop id, so the user copy hides the system one; renaming it would label the only visible entry "(Legacy)" | Delete the user copy (not renamed) |
| Frozen SDK copies | `techmore/mseries-sdk-apps` | Every path in [ci/frozen-paths.txt](ci/frozen-paths.txt) | `FROZEN.md` in each; CI guard | Retire per [REPOSITORY-TOPOLOGY.md](REPOSITORY-TOPOLOGY.md) step 6 |

## Old app ids (pending, not yet duplicates)

SDK PR #41 ([docs/APP-ID-MIGRATION-2026-10-27.md](https://github.com/techmore/mseries-sdk-apps/blob/main/docs/APP-ID-MIGRATION-2026-10-27.md))
moves the Rust apps to `org.techmore.mseries.*`. The new packages are **not installed yet**, so the old
launchers are still the only working ones and were not renamed. After the new packages install, these become
legacy: `io.github.techmore.ClaudePantheon{Rs,Sdk}`, `org.elementary.mseries.ImageStudio`,
`io.elementary.mseries.{Conversations,MessagesRust}`, `io.github.sdolbec.SignalHistoryImport` (and dock pins
need the swap in that doc).

## Installed launchers renamed (user level)

Backups: `~/.config/Claude/side-session-notes/local_ade438ad-48f1-41af-89b1-8329dfaedd51/legacy-desktop-backup/`.

| File in `~/.local/share/applications` | New `Name=` |
| --- | --- |
| `signal-desktop-beta.desktop` | Signal Beta (Legacy) |
| `org.signal.Signal.desktop` | Signal (Legacy) |
| `com.t3tools.T3Code.desktop` | T3 Code (Beta) (Legacy) |

To undo: copy the backup over the file and run `update-desktop-database ~/.local/share/applications`.

## System launchers for the owner (not edited)

| `/usr/share/applications` entry | Note |
| --- | --- |
| `io.github.techmore.ClaudePantheonRs.desktop` "T3-R Pantheon" | Shadowed by the user copy "T3"; old app id |
| `mseries-restore-windows.desktop` | Shadowed by an identical user copy |
| `org.mseries.Battery.desktop`, `org.techmore.EnergyMonitor.desktop`, `mseries-power-report.desktop`, `org.gnome.PowerStats.desktop` | Four battery/power views; **undecided** which is primary |

## Other installed leftovers (listed, untouched)

`~/.local/bin`: `claude-pantheon-rs.bak-20261027`, `claude-pantheon-sdk.bak-20261027`,
`mseries-messages-rs.bak-20261027`, `mseries-assistant.before-mseries`. `~/.config/systemd/user`:
`mseries-ai-{coder,compact,everyday,personal}.service.before-mseries`, `voxtype.service` (disabled).
`~/.local/libexec`: `mseries-brightness.bak-20261016`, `mseries-screenshot-shelf.pre-retention-fix-20261022`.

## Duplicates inside `techmore/mseries-sdk-apps` (not edited)

| Group | Copies | Note |
| --- | --- | --- |
| T3 | `rust/claude-pantheon-rs` app vs `rust/claude-pantheon-rs/sdk/t3.msdk` (`claude-pantheon-sdk`) | Same undecided row as above |
| Messages | `rust/mseries-messages` (two desktop entries: Messages, MessagesPreview) vs Python `mseries/phone-setup/messages.py` | Migration doc: "Retiring either is the owner's decision" |
| Signal | `mseries/signal-pantheon` (Vala + signal-cli) vs Signal channel in `rust/mseries-messages` | Deferred per MESSAGING-STATUS |
| Disk Space | `rust/mseries-diskspace` app vs `rust/msdk/examples/disk-space.ui.json` | Example, not a shipped app; no action |
| Compositor protocol | `rust/pantheon-compositor/protocol/pantheon-desktop-shell-v1.xml` only | Vendored XML with a drift check against this repo; intentional, no action |
| `granite-smoke` | `rust/granite-smoke` | Removed here; smoke-only crate in the SDK repo |
