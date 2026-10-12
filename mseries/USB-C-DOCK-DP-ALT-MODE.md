# USB-C docks & DisplayPort Alt Mode on M-series (why the Dell WD19S is dead)

Investigates why a USB-C dock's monitor and mouse do not work on the
elementary/mkosi Apple Silicon target, with a live capture from
`MacBookPro18,3` (J314s, M1 Pro, `apple,t6000`). Read with
`KERNEL-REPORT.md` and `PORT-MAP.md`.

## TL;DR

A USB-C dock that carries video (Dell WD19S and friends) needs **DisplayPort
Alt Mode** on the host Type-C port. Asahi Linux does not ship DP Alt Mode yet
(`DP Alt Mode: WIP` on the M1 feature-support table), and neither does
Thunderbolt/USB4 (`Thunderbolt: WIP`). So:

- **Monitor through the dock: impossible on this kernel.** Use the laptop's
  built-in HDMI port, or build the experimental `fairydust` kernel (below).
- **Dock USB (mouse): unreliable.** The dock's upstream Type-C link must come
  up before any downstream hub/mouse appears. On M1 Pro the Apple Type-C PHY
  (`phy-apple-atc`) has gaps that make this flaky.

This is a **kernel** limitation, not an elementary userspace bug. Nothing in
the image can fix it.

## Live evidence (M1 Pro, linux-asahi 7.1.13)

Device: `MacBookPro18,3` / `J314s` / `apple,t6000`. Dock: **Dell WD19S**
(regulatory model `K20A`, service tag `2SOLVS3`) — a *USB-C* dock whose video
outputs are DP Alt Mode, not Thunderbolt (the TB variant is the WD19TB).

1. **No DisplayPort connector exists.** `/sys/class/drm` exposes only
   `card2-eDP-1` (internal) and `card2-HDMI-A-1` (the 14"/16" chassis HDMI
   port). There is no `DP-1`, so any dock DP/HDMI output has nowhere to land:
   ```
   /sys/class/drm/card2-HDMI-A-1: disconnected
   /sys/class/drm/card2-eDP-1:    connected   (3024x1964 internal)
   ```

2. **USB4/Thunderbolt pipe handler is not implemented** (falls back, prints
   on every port bring-up):
   ```
   phy-apple-atc 703000000.phy: ATCPHY_PIPEHANDLER_STATE_USB4 not implemented; falling back to USB2
   ```

3. **The Type-C PHY can fail to come back after a disconnect** (M1 Pro):
   ```
   phy-apple-atc b03000000.phy: Pipehandler lock not acked.
   phy-apple-atc b03000000.phy: Failed to lock pipehandler
   ```
   When this fires, the port's xHCI bus is torn down and re-probed but the
   dock's hub never enumerates — no mouse.

4. **Plain USB3 over a Type-C port does work** when the link trains: an ASIX
   `AX88179A` gigabit NIC enumerated at 5000M (`lsusb -t`, `cdc_ncm`) on a
   port whose PHY trained cleanly. So ethernet over the dock's NIC can work
   even while video and the dock hub do not.

5. `/sys/class/typec/port*-partner/usb_mode` reports `usb2 usb4` for the dock
   but the kernel cannot act on the `usb4` half. (Reading it also trips a
   benign `sysfs_emit_at` WARN in the `typec` driver — informational, not the
   cause.)

Internal input (keyboard/trackpad) is unaffected — those are SPI, not the
dock. `/proc/bus/input/devices` shows only `Apple SPI Keyboard` /
`Apple SPI Trackpad` when the dock mouse is not enumerated.

## Port map on M1 Pro (three Type-C ports + HDMI)

| typec port | USB controller | PHY | role | notes |
|---|---|---|---|---|
| port0 | — | — | sink/device | charge-only / MagSafe-ish |
| port1 | `702280000.usb` | `703000000.phy` | host+device | USB4 fallback prints here |
| port2 | `b02280000.usb` | `b03000000.phy` | host+device | NIC enumerated here; PHY lock failure here |
| port3 | `f02280000.usb` | `f03000000.phy` | device-first | gadget/`udc` |

`fairydust` "blesses" exactly one port for DP output; try the dock in each
port to find the working one.

## Fix path A (today, zero risk): use the HDMI port

The 14"/16" MacBook Pro's physical HDMI port is supported on M1 Pro and
already exposed as `card2-HDMI-A-1`. Move the monitor cable from the dock to
the laptop HDMI port. For the mouse, plug it into a USB-C→USB-A adapter on a
port whose PHY has trained (watch `dmesg` for the pipehandler errors), or use
a Bluetooth mouse. Networking over the dock is fine when its NIC trains.

## Fix path B (real fix): the `fairydust` DP-Alt-Mode kernel

Asahi's `fairydust` branch wires up the four blocks DP-over-Type-C needs
(DCP, DPXBAR, ATCPHY, ACE) and exposes one USB-C port as a DP Alt Mode
output. It is *experimental* and "blesses" a single port; multiple USB-C
displays are not possible and hot-plug has quirks. Reported working on M1
Pro (this exact class of machine) by users — but treat as best-effort.

Sources / prior art:
- Asahi progress report (Linux 6.19, Feb 2026): `fairydust` landing + limits.
- Fedora Asahi guide + `bharambetejas/asahi-fairydust-display`.
- Void guide (`linux-asahi-fairydust`).

This host runs `linux-asahi` from Arch, so the Arch path is the one that fits
the elementary-grow transform: rebuild `linux-asahi` from the `fairydust`
branch using the `linux-asahi` PKGBUILD as a base.

Required kernel config (modules, not built-in):
```
CONFIG_TYPEC=m
CONFIG_TYPEC_DP_ALTMODE=m
CONFIG_TYPEC_NVIDIA_ALTMODE=m
CONFIG_TYPEC_TBT_ALTMODE=m
```

Helper: `mseries/fairydust/build-fairydust-kernel.sh` (run on the Arch/omarchy
side, not in the elementary subvolume). It is intentionally conservative:
it refuses to touch `/boot` unless `--install` is passed and prints the
exact `update-m1n1` + GRUB steps to review.

### WD19S caveat

The WD19S drives up to 3 monitors via DP **MST** (a single DP stream split
into multiple). `fairydust` exposes one DP sink; MST behaviour through the
dock is untested. Expect **one** monitor to work at most, and possibly only
on one specific Type-C port.

## Why not just "enable USB4"?

There is no knob. `ATCPHY_PIPEHANDLER_STATE_USB4 not implemented` is a missing
driver state machine in `phy-apple-atc`, not a config option. USB4 tunnelling
needs the same DPXBAR/ATCPHY/ACE work plus a USB4 router driver — it is
WIP upstream.

## What belongs in this repo

- `packages.arm64`: note the DP-alt-mode kernel config so a future
  Asahi-flavoured kernel build turns it on.
- This doc + a `PORT-MAP.md` row (dock video gate = kernel capability).
- Nothing userspace-side: do not add DisplayLink hacks as a workaround for a
  native-DP dock (DisplayLink is a different, CPU-rendered transport and a
  separate decision).
