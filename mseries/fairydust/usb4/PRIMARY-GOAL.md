# PRIMARY GOAL — dock HDMI picture on elementary OS (read before any dock-video work)

**Goal:** a picture on the monitor plugged into the **Dell WD22TB4's HDMI**
port, from **elementary OS** on this **MacBookPro18,3 (j314s, M1 Pro)**.

Everything in `mseries/fairydust/usb4/` serves this goal. Every patch,
experiment, boot and doc change must say which gate below it moves, or why it
is needed to move one. Work that moves no gate is not dock-video work.

## Gates (in order; qualify one payload and boot at a time)

The table retains best prior experiment evidence. It does not establish the current installed/armed state.

| Gate | Evidence in `dmesg` / userspace | Status 2026-10-17 |
|---|---|---|
| G0 USB4 link to the dock | `thunderbolt 0-1` at 40 Gb/s; dock USB/Ethernet work | **met** |
| G1 DP tunnel allocated | tunnel `0:5 <-> 1:14` set up | **met** (E1–E3) |
| G2 DCP firmware accepts the tunnelled sink | Positive progress on the mapped DCP; absence of an error alone is insufficient | **not met** on `dcpext1`; E4 tests `dcpext0` |
| **G3 Link trained (the current blocker)** | firmware sends link rate + lane count (`set_active_lane_count`, `SET_LINK_RATE`) | not met |
| G4 Sink identified | EDID read; an external connector shows `connected` with modes | not met |
| G5 Picture | the monitor shows the elementary desktop | not met |

macOS proves the hardware chain: same Mac, dock, cable and monitor train
4-lane HBR3 ~90 ms after HPD, routed through `dcpext0` port 0
([evidence](evidence/2026-10-17-macos-baseline-dcpext0.md)).

## Prior art — check it before more reverse engineering

**Aurora (`omacom/linux-aurora`, used by omarchy-mac) already drives
DisplayPort over USB4 on Apple Silicon Linux, including on a j314s.**
This project is not first; we should reuse, not re-derive.

- [linux-aurora#38](https://github.com/omacom/linux-aurora/issues/38), comment
  by @cb2206 (2026-10-12): **J314S, Aurora 2026.10.11.15, LG UltraFine 5K over
  Thunderbolt** — log shows `dpinN: active`, `DPTXPort: SET_LINK_RATE 0x14`,
  during display resume. The report explicitly records **zero**
  `DP tunnel up/down` events: the existing tunnels stayed allocated. This supports
  display resume on the same model, not this WD22TB4 dock or tunnel reallocation.
- [linux-aurora#132](https://github.com/omacom/linux-aurora/issues/132): M2 Max
  through a CalDigit TS5 Plus dock trains HBR3 ×4 and shows 4K 60 Hz.
- Aurora's j314s DT gives **both** `dcpext0` and `dcpext1` every Type-C port
  (`apple,typec-dptx-phys = <0 1 2>`) with dynamic routing (`dcp-fabric*.c` in
  `drivers/gpu/drm/apple/`, `atc-tunnel.h` in `drivers/phy/apple/`,
  `drivers/thunderbolt/apple.c`). Its 2026.10.15.19 notes say M1 Pro/Max
  USB-C ports need the boot loader to switch `dcpext0` on — consistent with E4.
- Active devs: @iconidentify (kernel/display/tunnel owner), @maralcbr
  (Thunderbolt s2idle, j314s PMP), @GehrmannSolutions (M3 external DP).
  Upstream lineage: `iconidentify/aurora-linux`.

**Fastest path to G5 is probably Aurora's kernel + its j314s DT (+ an m1n1
that enables `dcpext0`), not more patches on fairydust `ce9f2eba`.** The ESP
already has `vmlinuz-aurora-sep-20261015.19` and a GRUB entry
`elementary-aurora-sep`, but `boot.bin` still carries our (older) DT, so that
entry has never been tested with Aurora's display/tunnel wiring.

## Rules for every agent

1. Read this file, then [STATE-OF-PLAY](STATE-OF-PLAY.md), before dock work.
2. Before writing new RE code, check whether Aurora already solves it.
3. After any boot, record the highest gate reached in STATE-OF-PLAY.
4. Don't present a gate as met without the log line that proves it.
