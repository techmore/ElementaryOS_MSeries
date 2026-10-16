# HDMI: what works today, what the dock work is really buying, and a plan

2026-10-16, Claude. Plain-language status for the owner and the other agents.
Hardware facts stay in [STATE-OF-PLAY](STATE-OF-PLAY.md); this file is the decision frame.

## Where nine days of dock work stands

Milestones M0 (dock sink presence) and the correct DP OUT/DP IN pairing are met.
M1-M4 (real DPRX, EDID, picture, repeatability) are not. The dock's HDMI needs
USB4 DisplayPort tunnelling, which **no upstream Asahi branch has** (Sven Peter:
needs two undocumented MMIO blocks, "DP IN PHY" and the crossbar, plus the DCP).
The offline work (HPD fix, DP-IN handshake, DCP source bridge, REA of Apple's
kernelcache) is real progress, but it is still all untested on hardware, and I
cannot honestly estimate when a picture appears. It may take several more boots
and could still hit a wall (a silent sink, or the unidentified ACIO
`startUsingTunnel()` step).

## The gap in the record: nobody has tested the paths that should already work

`DOCK-VIDEO-DECISION.md` (2026-10-15) lists:

| Path | Status per Asahi's feature table | Tested on this Mac? |
|---|---|---|
| A. The Mac's **own HDMI port** (left side) | supported (13.5 firmware, confirmed locally) | **No record of a monitor ever being plugged in.** `check-display-paths.sh` shows `card2-HDMI-A-1 disconnected` |
| B. Direct USB-C -> HDMI/DP adapter, front-left port | works in practice (Asahi issue #579, 4096x2160@60) | No record |
| C. Dell dock video | not implemented upstream | the 9-day effort; no picture |

The WD22TB4 has a captive Thunderbolt cable, so the "non-Thunderbolt cable makes
the dock fall back to plain DP Alt Mode" idea (README, "not verified") does not
apply, and Linux cannot force the CD321x out of USB4.

## Plan: get a monitor working this week, keep the dock effort running in parallel

1. **Track 1, 5 minutes, no code (owner):** HDMI cable from the Amazon Basics
   monitor straight into the MacBook's HDMI port, then
   `bash mseries/check-display-paths.sh` (expect `card2-HDMI-A-1 connected`) and
   report the result in PR #53 or the handoff. If the panel stays dark, try the
   monitor's input select and `xrandr --output HDMI-A-1 --auto`. Do not unplug
   the dock for this: leave it attached and use the second port, or arm the bypass
   (`cat /sys/module/thunderbolt/parameters/dprx_bypass` must print `Y`) before
   touching any cable (`DP-TUNNEL-RE.md` section 9).
2. **Track 2 (owner decision, cheap):** a USB-C -> HDMI/DP adapter on the front-left
   port is a known-good fallback if Track 1 has a problem; the dock stays for
   USB, Ethernet and audio, which already work.
3. **Track 3 (agents):** dock video continues, but with a clear stop rule. One
   batched boot (POST-REBOOT-CHECKLIST) answers whether the bridge produces a real
   DPRX answer. If the bypass-off run shows no DPRX/EDID after that, stop and
   decide with the owner whether a second-computer macOS trace is worth more
   time, instead of more offline rounds.

## What counts as "HDMI support"

If the goal is a working external monitor on this Mac, Tracks 1/2 may already
deliver it today. If the goal is specifically to use the Dell dock's HDMI, that
is Track 3 and is research with an uncertain end. The owner should say which one
is the real requirement so effort is spent on the right one.
