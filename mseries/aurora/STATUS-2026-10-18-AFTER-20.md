# Aurora status after `.20` — 2026-10-18 09:50 UTC (Claude Code, read-only)

## Later host observation — 2026-10-18

The snapshot below is historical. The [earlier visual/VRR report](hardware-tests/2026-10-18-j314s-vrr-and-boot-archive.md)
records an owner-confirmed working dock. The [later hotplug/cleanup report](hardware-tests/2026-10-18-j314s-hotplug-and-module-cleanup.md)
records startup/display-mode and dock faults, unverified audio-after-replug, and
verified removal of orphan module trees. These observations do not invalidate the
scoped visual pass or establish sustained stability. No new upstream audit here.

Source: `gh` against `omacom/linux-aurora` at 2026-10-18T09:50Z.

## Later owner confirmation and VRR observation

The owner subsequently confirmed the dock works and both displays look normal
with builtin VRR selected. [Scoped receipt](hardware-tests/2026-10-18-j314s-vrr-and-boot-archive.md)
records external fixed 1080p/60, unchanged layout, and brief builtin kernel VRR
activation (3/25 samples). This updates the visible-picture uncertainty below;
the physical dock port was not independently verified, and long-run stability,
suspend/resume and sustained VRR are still open. No upstream release statement
or original freeze is changed by this host observation.

## What changed since `.20`
- **No new release.** `aurora-2026.10.17.20` (2026-10-17 19:20Z) is still latest; default-branch HEAD is
  `5d570a78a` (the `.20` merge, #137). Zero commits on it since.
- 52 branches. Only new push: `fix/t8140-j700-internal-display-dart` (Neo; PR #140 closed). Not J314S.
- **Draft PR #139** (updated 09:40Z, head `ffa615e26`): one kernel on Asahi `asahi-wip` v7.2.10 carrying
  `integration/aurora` + `aurora-wip`. Author states hardware qualification is still in progress and that
  updates are fast-forward pushes. Hardware results are the MacBook Neo (J700) and "M1 Pro (J316s)" on 7.2.10
  *without* the unified carries; "Still to land": Touch ID ready reporting and dtbs_check bindings. Its J316S
  battery results are not this J314S machine, and nothing in it is a release.
- Issues touching our questions: #130 (J316S direct USB-C display: DCP crashes after display power-back-on,
  idle lock or s2idle, open), #121 (J516S s2idle external-display veto), #85 (BT hang after long s2idle),
  #132 (M2 Max via dock: no 4K above 60 Hz). None says SEP hang fixed.

## Does anything fix the four items?
| Item | Answer |
|---|---|
| SEP / Touch ID probe crash | **Unproven.** #139 carries "Touch ID sensor attach: serial and nonce read before registration, attempts spaced and bounded with one late retry" and the T8112 SEP DART/xART guard. That targets sensor attach, which fits our probe crash, but it is a draft on 7.2.10, M2/Neo-tested. No J314S result. |
| Power management | `.20` already has the J314S PMP/PMGR/idle-governor files (identical in #139 per the energy-port plan). Nothing newer. No J314S energy numbers exist upstream. |
| Thunderbolt/USB4 | Already in `.20` (#124 s2idle port power-off is opt-in). |
| Dock HDMI (G3) | See next section: on `.20` it already appears to work on this machine. |

## This machine on `.20` right now (the important result)
Uptime 1 h 15 min on `7.1.12-2-20261017.20-sep-ARCH` with the matched `boot.bin` (installed 04:32), SEP driver
loaded (`/dev/sep-bio`, "SEP platform profile T6000/J316s", xART writes enabled), no crash, no fprintd or Touch ID
probe run this boot. Docked on the WD22TB4 (bolt: authorized, USB4 2x20 Gb/s; hub/Ethernet present).
- DCP logs on the dock connect: `SET_LINK_RATE 0x1e`, `set_active_lane_count ... SET_ACTIVE_LANE_COUNT 4`
  (a "unexpected lane count:4 phy:0" warning), `dcp_dptx_connect_session(port=0) ... tunnel=1 route=borrowed`.
- `card2-DP-2`: `connected`, `enabled`, dpms On, 256-byte EDID read (INS `NS65DF710NA21`, "Ines GmbH 65\""),
  modes up to 3840x2160; Gala lists it as a logical monitor at x=1512 scale 1.
- That meets **G3 (link rate + lanes) and G4 (EDID, connector with modes)**, and Gala has the output enabled.
  **G5 (a visible picture) and the physical port are not confirmed by me**: it is the owner's screen, I did not
  look at it, and a 65" Insignia TV is very likely, but not proven, plugged into the dock's HDMI rather than DP.
- Later in the same boot the sink re-trained repeatedly (04:51: `SET_LINK_RATE 0x0`, `INACTIVE_SINK_DETECTED`,
  disconnect/reconnect cycles every ~10-15 s) before settling; hotplug timeline needs a stability check.

## Not verified / next
1. Owner confirms the TV shows the desktop and which dock port it uses; then record G5.
2. Stability: leave docked for a long idle plus lock/DPMS and s2idle cycles, journal the retrains.
3. Touch ID: do not probe until the matched DT plus a deliberate single probe is approved (owner + DeepSeek).
4. Do not boot `.20` alternatives or 7.2.10 until a CI-built, rollback-ready candidate exists (existing rule).
