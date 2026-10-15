# Watchlist: people and projects we follow

Added 2026-10-14. Machine-readable list: `mseries/local-ai/people-watch.json`.
Checker: `mseries/local-ai/people-watch.py` (read-only, polls GitHub every 6 h; set
`GITHUB_TOKEN` for a higher rate limit). It is a `mseries-verify` check named
`upstream-people-watch`; it passes when any project pushed or released since the last
acknowledgement. Read the list with `python3 ~/.local/share/mseries-verify/people-watch.py --list`,
then accept it with `--ack`. Kernel and Touch ID signals stay in `upstream-watch.py` and
`touchid-watch.py`.

Source: Omarchy's [Introducing Omarchy M](https://omarchy.us/news/2026/09/introducing-omarchy-m/)
(2026-09-11). People without a stated GitHub account (Scott Jones, Dj, Miguel Cruz, Liam,
Eryk Wieliczko, Randy, Shawn Yeager, Jon Kinney) are not watched yet; add them to the JSON
once their repositories are confirmed. Do not guess handles.

| Project | Who | Why it matters here |
| --- | --- | --- |
| maralcbr/omarchy-mx-mac | Marcelo Alcantara | Native Mac installer; **feature-frozen** (security/boot fixes only) |
| aurora-silicon/linux | Aurora kernel | Kernel lane its image pins; qualified on the 14" M1 Pro |
| omacom/omarchy-mac-installer | Omarchy M | Where installer work now continues |
| omacom/omarchy-mac | Naeem Malik, Scott Jones | M1/M2 Omarchy for a year |
| omacom/omarchy-mac-pkgs | Omarchy M | Package source we port from (audited at 222f7a8) |
| omacom/try-omarchy | Eduardo Martinez | Omarchy as a native Mac app |
| riverscn/omarchy-pkgs-aarch64 | Shun Li | aarch64 packages and images |
| subedijaidip/dp-altmode-t8112 | Jaidip Subedi | USB-C external displays on M2 Air; our dock video gap |
| joshuaswarren/mlx-omarchy | Joshua Warren | MLX over Vulkan; local AI |
| RyanTheTide (user) | Ryan Murray | Kernel foundations, macOS tracing |
| zackb/tether | zackb | iPhone continuity (we pin v0.2.37; v0.2.38 exists as of 2026-10-14) |
| erikwb/BlueFerry | erikwb | iPhone texts and codes |
| OpenBubbles/openbubbles-app | OpenBubbles | iMessage candidate (SSPL core, never bundle) |
| cameroncooper/keychain, Sank6/iCloud-Keychain-for-Linux | | iCloud Keychain clients |
| BlueBubblesApp/bluebubbles-app, bluebubbles-server | BlueBubbles | iMessage through a real Mac; Apache-2.0; 1,386 / 1,108 stars; pushed 2026-10-14 / 10-13 |
| OpenBubbles/rustpush | OpenBubbles | iMessage core; license NOASSERTION (SSPL per our notes); never bundle |
| chrispouliot/bubbles, tannerkrewson/LiteBubbles | | rustpush GUI clients; 0 stars, license not declared, very new |
| bendews/apw | bendews | Apple Passwords CLI; GPL-3.0; 257 stars; last push 2026-08-24 |
| dragosol/icloud-keychain-linux | dragosol | Read-only Keychain viewer; no license, so personal use only |
| alex-mextner/passwords-app, deej1721/icloud-passwords-linux | | Two-way sync (MIT, created 2026-10-10) / Windows-helper-in-VM bridge (MIT) |

Their claims are leads, not evidence: Omarchy's post says Touch ID works and that M1/M2
is the first release target, but its own status page still lists Touch ID as not in the
first release. Verify before relying on any of it. Respect each project's license; do not
import sponsor-only or SSPL code into the image (see `AGENTS.md`).

## Lead: omarchy-mx-mac (read 2026-10-14, nothing installed or downloaded)

[maralcbr/omarchy-mx-mac](https://github.com/maralcbr/omarchy-mx-mac) (MIT, 420 stars, latest release v4.0.4-mac.1) is
Omarchy on Arch Linux ARM + Asahi, with a signed, notarized macOS installer. Points that matter here:

- **Frozen.** Its README says new Apple Silicon work goes to `omacom/omarchy-mac` (branch
  `quattro-upstream`, last commit 2026-10-04) and installers to `omacom/omarchy-mac-installer`
  (active today). Both are now watched (the first via `omarchy-mac`).
- **Aurora kernel.** New installs use `aurora-silicon/linux` (default branch `aurora-stable`, working branch
  `aurora-wip`), pinned to a commit it says is qualified on the **14-inch M1 Pro** (our model) and 16-inch M2 Max.
  Aurora is a candidate second kernel lane next to Asahi fairydust for our dock/USB4, suspend and video gaps.
  Its license shows as NOASSERTION on GitHub (a Linux tree, so GPL-2.0 expected; confirm before packaging).
  Evaluate in the edge lane or a VM only; the Mac's kernel and bootloader are not changed without the owner.
- **Relevant work to read:** LUKS2 key and token hardening (Sept 25 commits) against our unverified
  `elementary-mac-setup` encryption flow; the "s2idle sleep-drain programme" tickets against our suspend and
  battery checks; its 22-model admission list and VM-acceptance method for our factory image qualification.
- Different base (Arch Linux ARM, Hyprland), so copy ideas and tests, not packages (see the porting boundary
  in `ROADMAP.md`).

## GitHub upstream monitoring — 2026-10-14

`Watch public upstreams` runs every six hours and on demand. It combines
`local-ai/people-watch.json` subscriptions with the explicit branches in
`upstreams/omarchy-m.json`, and maintains one issue with pending revisions,
release changes and fetch failures. Closing the issue acknowledges observations;
new changes reopen it. Failed fetches preserve the last successful observation
and fail the Action. No upstream code is automatically merged or deployed.
The native macOS installer remains reference-only, per the owner decision.

Activated on main: [upstream dashboard #51](https://github.com/techmore/ElementaryOS_MSeries/issues/51).
First Action run 38640456586 completed successfully. The duplicate Codex
heartbeat `follow-omarchy-m-sources` is PAUSED. Review covered initial audited
revision comparison, missing user sources, and trusted dashboard authors.
No new automated tests were run for this watcher.

## Owner-reported, unverified (2026-10-15)

The owner says Michael Dell is a sponsor of Omarchy MX / Omacom and the Asahi work. Not checked against a public source; do not repeat it as fact until one is found. Context: this project is reverse-engineering the Dell WD22TB4 dock for Asahi Linux, so the dock's DisplayPort tunnel retries on the `dptunnel` kernel are expected research behaviour, not a bug to remove.
