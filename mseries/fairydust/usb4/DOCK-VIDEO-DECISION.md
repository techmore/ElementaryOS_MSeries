# Dock / external-monitor video on the M1 Pro — decision and methods

Date: 2026-10-15. Machine: `MacBookPro18,3` (`apple,j314s`, M1 Pro, 14-inch),
elementary OS 9 on kernel `7.1.13-elementary-fairydust-usb4`.

This records the decision for the long-standing open problem
**"Monitor through the dock"** in [`../../ROADMAP.md`](../../ROADMAP.md), with
the upstream state checked on 2026-10-15.

## TL;DR

> **Update 2026-10-15 (later):** the owner directed the RE path, so the dock is
> now the target after all. The everyday alternatives below are still valid, but
> the active work is experiment 1 in
> [`DP-TUNNEL-RE.md`](DP-TUNNEL-RE.md) ("route the controller into the ACIO DP IN
> adapter and let the tunnel allocate"). This page stays as the record of the
> non-dock fallbacks.

There are three different things people call "the monitor", and only two of them
are reachable today:

| Path | Status | Cost |
|---|---|---|
| **A. Mac's built-in HDMI port** | **Works** (supported) | Plug in an HDMI cable |
| **B. USB-C DP Alt Mode** (direct adapter) | WIP, works in practice | Buy a USB-C→HDMI/DP adapter |
| **C. Dock video** (HDMI *or* DP on the WD22TB4) | **Not possible** | Multi-week upstream RE |

**Decision: target A (built-in HDMI) as the everyday path, keep B as the
"DP" alternative. Do not spend effort on C** — HDMI-out-of-the-dock and
DP-out-of-the-dock are the *same* problem (USB4 DisplayPort tunnelling), not two
problems, and that tunnelling is unimplemented upstream.

## Evidence (checked 2026-10-15)

**Asahi feature table, M1 Pro/Max/Ultra** (<https://asahilinux.org/docs/platform/feature-support/m1/>):

- `HDMI Out: linux-asahi (13.5 FW only)` — the 14/16-inch M1 Pro's own HDMI port
  is a **supported** external display.
- `DP Alt Mode: WIP`, `Thunderbolt: WIP`.

**Local hardware confirms the 13.5 firmware** (`bash mseries/check-display-paths.sh`):

```
DCP firmware-compat   13.5        (/proc/device-tree/soc/dcp@289c00000)
card2-eDP-1           connected   (internal)
card2-HDMI-A-1        disconnected
card2-DP-1            disconnected
mux_apple_display_crossbar   loaded
```

**Our kernel is the current upstream fairydust tip.** The `fairydust` branch
HEAD is `ce9f2eba72c061a50b2d790450e90af3439d8c24` (2026-09-08) — the exact
revision this repo pins (`mseries/fairydust/usb4/PKGBUILD`). No newer DP/USB4
work has landed, so there is nothing to rebuild for.

**Upstream says a Thunderbolt dock will not carry video with fairydust.** Asahi
developer chaos_princess, 2026-08-26:

> "tb hubs will not work with fairydust, as it is configured to output to dp phy,
> not to tb interface. But if you want two displays on two ports - doable with a
> device tree patch by copying the dcpext config for another one."

**A direct USB-C adapter does work.** AsahiLinux/linux issue #579 reports an
`Apple USB-C Digital AV Multiport Adapter` (`05ac:1463`) coming up as `DP-1` and
driving 4096x2160@60 on the front-left port — while a Studio Display (Thunderbolt)
fails with `could not allocate DP tunnel`.

**Why C needs RE, not a setting.** Sven Peter's USB4 series (2026-08-30, the base
of our USB4 port) supports only XDomain and USB3-via-USB4 tunnels; PCIe and
DisplayPort tunnelling "require additional work and reverse engineering that is
not done yet". On this machine the host DP-IN adapter (`0:5`) is never driven by
a DP source because the DCP external pipes are wired only to the ATC PHYs, and
`apple-dcp` has no tunnelled-DPTX mode (see [`README.md`](README.md) §"Dock
video"). Making it work needs the DCP firmware protocol for a tunnelled DPTX
endpoint, AUX-over-tunnel, DPXBAR→ACIO routing, and link training.

## Methods

### Path A — built-in HDMI (recommended)

1. Plug the monitor into the **HDMI port on the left side of the MacBook**
   (not the dock).
2. Confirm: `bash mseries/check-display-paths.sh` → `card2-HDMI-A-1  connected`.
3. If the panel stays dark, select the right input on the monitor, then
   `xrandr --output HDMI-A-1 --auto`.

### Path B — USB-C DisplayPort Alt Mode (the "DP" route)

- Use a **direct** USB-C→HDMI/DP adapter/cable. A Thunderbolt/USB4 dock will
  **not** work (it negotiates USB4, so the fairydust DP PHY path is bypassed).
- Use the **front-left** USB-C port (fairydust "blesses" one port per machine:
  `t600x` `j314/j316/j414/j416` → front-left).
- Only **one** USB-C display at a time. Hot-plug is quirky; a cold boot with the
  adapter attached is more reliable.
- Confirm: `card2-DP-1  connected`. If `typec_displayport` is needed,
  `modprobe typec_displayport`.
- Two external displays on two ports is a device-tree change (copy the `dcpext`
  config for a second port) — an open, tractable task, not done here.

### Path C — dock video (parked)

Not targeted. If it is ever attempted, the entry point is an m1n1-hypervisor
trace of macOS driving the dock from a second computer, then implementing the
DCP tunnelled-DPTX path (see [`README.md`](README.md) and
[`usb4/RECOVERY.md`](usb4/RECOVERY.md)). The `upstream-dp-watch` verify check
still watches for it.

## Verification helper

`mseries/check-display-paths.sh` (read-only) reports the DCP firmware, the
support modules, every DRM connector's state, and a one-line verdict per path.
Run it after plugging a cable in.
