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
| maralcbr/omarchy-mx-mac | Marcelo Alcantara | Native Mac installer; cut the build that lit up USB-C monitors |
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

Their claims are leads, not evidence: Omarchy's post says Touch ID works and that M1/M2
is the first release target, but its own status page still lists Touch ID as not in the
first release. Verify before relying on any of it. Respect each project's license; do not
import sponsor-only or SSPL code into the image (see `AGENTS.md`).
