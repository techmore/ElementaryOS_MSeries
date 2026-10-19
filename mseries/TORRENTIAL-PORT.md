# Torrential on M-series

The native Rust/GTK 4/Granite app is built and installed on the M1 OS 9
desktop. It runs with the system Transmission 4.1.1 backend and appears as
**Torrential** in the application menu. Flatpak is not required.

## Source and local fork

Upstream: <https://github.com/davidmhewitt/torrential>, `main` at
`3af2c2ab473d074bb95a63a3bb185d5809ee8d8a` (the unreleased rewrite).
Local fork: [private `techmore/torrential` repository](https://github.com/techmore/torrential),
branch `mseries-native`, commit `4082b079dab42a53c80a8ebbb6a11253ac716453`.
The working clone is `/home/admin/Documents/TorrentialFork`; its upstream remote
points to `davidmhewitt/torrential`.

The fork redirects unread daemon stdout, waits briefly for RPC readiness,
creates its config and Downloads directories, binds RPC to loopback, and
uses SIGTERM plus wait so the daemon can save state without a shutdown panic.
The direct `nix` dependency is retained for graceful termination.
Backend state is under `~/.config/torrential`; downloads use the XDG Downloads
folder. The packaging policy currently permits the standard `~/Downloads`
location; a customized XDG folder needs a matching AppArmor rule.

## Native package and runtime evidence — 2026-10-13

The local ARM64 package is
`/home/admin/Documents/TorrentialFork/build/native-package/elementary-torrential_0.1.0-1~mseries3_arm64.deb`.
The recipe in [`torrential-native/`](torrential-native/) installs the binary,
launcher, icon, schema, and a scoped AppArmor addition for the daemon's
Torrential configuration and Downloads folder. It accepts elementary's
`libgranite7` as well as Ubuntu's `libgranite-7-7` package name. Removing the
package removes its policy include while preserving other local rules.

The native release build passed on the AArch64 host with 16 KB pages, GTK
4.22.4 and Granite 7.8.1. The package installed successfully, its GSettings
schema became available, and the app launched in the active desktop session.
The daemon's default system service was disabled on this host so the app owns
its own child. The app and child remained running during the download check;
backend settings were written successfully. A visual screenshot and UI-button
interaction were not available from the command environment.

Added the official Ubuntu 26.04.1 Server AMD64 torrent through the app's local
backend RPC. Tracker announcement succeeded and an actual peer transfer
produced about 235 MiB downloaded at 13.5 MiB/s with 50 peers and verified
pieces without an error at a later check. The 2,927,861,760-byte ISO subsequently completed and matched Ubuntu's
published SHA-256 `cc8a95cde20f6ced61a322420de00f10cc3c90ced545daa46cb9c1a117f1d927`.
RPC pause/resume checks settled to the expected states. The completed test
torrent was paused and remains in the app queue under `~/Downloads`. UI button
interaction is still unqualified.
An initial Ubuntu ARM64 desktop torrent was rejected by its tracker and was
removed before this successful test.

Build commands use `CARGO_HOME=~/Documents/torrential-build-cache/cargo` and
`CARGO_TARGET_DIR=~/Documents/torrential-build-cache/target` with
`cargo build --release --locked`. The rebuilt package uses the same target
cache. The cache is approximately 1 GiB and may be reused for later builds.

## Distribution and next work

The audited upstream tree has no LICENSE/COPYING/NOTICE file or license grant.
The owner requested a private `techmore/torrential` repository for the fork
fixes; keep it private and keep built packages out of public distribution
until redistribution permission is clear. This public OS repository contains
only downstream packaging and status documentation. No one was contacted and
nothing was sent to the upstream project.

Keep Torrential optional and outside the factory image. Remaining work includes
UI add/pause/resume/remove qualification, close/reopen state restoration, file and magnet association support, custom
folder policy handling, and measured idle CPU/RSS/wakeup comparisons before
further optimization. Upstream's rewrite also documents incomplete features
in its README.

## UI polish and close fix — 2026-10-18

Fork `techmore/torrential`, `mseries-native`, merged PRs
[#2](https://github.com/techmore/torrential/pull/2) (UI polish) and
[#3](https://github.com/techmore/torrential/pull/3) (quit on window close);
head `6ab0de5`. Package `elementary-torrential_0.1.0-1~mseries3_arm64.deb`
built with `build-deb.sh` from that head and installed; `/usr/bin/torrential-relm4`
is byte-identical to the merged build.

- UI: scrollable list, segmented All/Downloading/Seeding/Paused filter, Ctrl+F
  search, richer rows (size, rates, ETA, ratio, checking, error, paused),
  status bar with totals, drag and drop of `.torrent`/magnet, Granite dark-style
  sync, completion toast or notification, Ctrl+O/L/F/comma/Q and Delete,
  symbolic magnet icon, validating magnet dialog, real download folder in
  Preferences. The Quit menu item previously did nothing (action unregistered).
- Bug found on the desktop: closing the window stopped the daemon but left the
  app spinning (CPU 60-90%), because hidden hide-on-close dialogs kept
  GtkApplication alive. Reproduced headless with the real daemon in a private
  netns, fixed by routing close-request through `quit()`, re-verified the same way.
- Verification method: private Broadway display, private netns/D-Bus/GSettings,
  mock Transmission RPC for populated states, real daemon for close/quit.
- Operational note: the packaged `transmission-daemon` system service must be
  disabled (`systemctl disable --now transmission-daemon.service`); with it
  running the app attaches to it, gets HTTP 401 and shows nothing. It was
  disabled by the owner on 2026-10-18.
- Still unverified: drag and drop, completion notification, Ctrl+comma
  preferences, system dark-mode switch, and a real-torrent transfer with the new
  UI. Magnet/.torrent file association (single-instance open handling) is not
  implemented.
