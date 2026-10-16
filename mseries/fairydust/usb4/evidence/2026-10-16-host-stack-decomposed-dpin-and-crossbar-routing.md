# The host-side stack is decomposed: only the DP-IN adapter (and its routing) is missing

**Date:** 2026-10-16
**Status:** verified against **this machine's kernel source** and the **running
kernel's config/devicetree**. No hardware test is reported here.
**Audience:** all agents. Read `STATE-OF-PLAY.md` first.

This note replaces the vague "nothing on Linux enables the ACIO DP-IN adapter"
with a layer-by-layer statement of what exists and what does not. It exists so
that nobody re-derives it, and so that the next step is driver work, not more RE.

## Bottom line

Five layers are needed to get a host DP stream into a USB4 tunnel. **Three are
already implemented in this kernel.** The missing one is the DP-IN adapter
(`atc-dpin`), and the routing that feeds it.

| Layer | Apple's class | Linux state on this machine |
|---|---|---|
| ATC-PHY "ACIO PHY": lane mode, crossbar protocol, `CFG0` | `AppleT8103TypeCPhy::configureACIOPhyLaneMode` / `configureDPTunnelMode` | **implemented** — `drivers/phy/apple/atc.c`, `regs.core` |
| Display crossbar (`ATC DPXBAR`) | `AppleT602XATCDPXBAR` | **implemented** — `drivers/mux/apple-display-crossbar.c`, `CONFIG_MUX_APPLE_DPXBAR=m`, driver registered; **but its DT node is `status = "disabled"`** |
| DPTX source / endpoint | `AppleDPTX` / iomfb | **implemented** — `drivers/gpu/drm/apple/dptxep.c`; live connector `card2-DP-1` |
| **DP-IN adapter (`atc-dpin`)** | `AppleATCDPINAdapterPort` | **ABSENT** — no driver, no DT node, no compatible anywhere in the tree |
| ACIO `startUsingTunnel()` / `stopUsingTunnel()` | CIO service | **not obtainable** — see `2026-10-16-re-foothold-for-remaining-subsequences.md` |

The DPTX endpoint currently routes through the **Type-C alt-mode mux**
(`dcp->typec_mux`, `dptxep.c:495`) — i.e. the alt-mode path. The *display
crossbar* mux (`dpphy` / `dpin0` / `dpin1`) is a **different** mux and has no
consumer in the tree today.

## Proof that Apple's `[obj+0x160]` is the atcphy "core" block

`AppleT8103TypeCPhy::configureACIOPhyLaneMode` and
`AppleT8103TypeCPhy::configureDPTunnelMode` both read/write the register block
reached through the object member at `+0x160`. The two offsets they touch are
exactly two register names that Linux's own driver already has, in
`atcphy->regs.core` (the `core` region = `0xb03000000`, size `0x4c000`):

```c
/* drivers/phy/apple/atc.c */
#define ACIOPHY_CFG0              0x08
#define ACIOPHY_CFG0_COMMON_BIG        BIT(0)
#define ACIOPHY_CFG0_COMMON_SMALL      BIT(2)
#define ACIOPHY_CFG0_COMMON_SMALL_OV   BIT(3)
...
#define ACIOPHY_LANE_MODE_T8103   0x48
#define ACIOPHY_LANE_MODE_RX0     GENMASK(2, 0)
#define ACIOPHY_LANE_MODE_TX0     GENMASK(5, 3)
#define ACIOPHY_LANE_MODE_RX1     GENMASK(8, 6)
#define ACIOPHY_LANE_MODE_TX1     GENMASK(11, 9)
enum atcphy_lane_mode { ACIOPHY_LANE_MODE_USB4 = 0, USB3 = 1, DP = 2, OFF = 3 };
#define ACIOPHY_CROSSBAR_T8103    0x4c
```

Observed in the disassembly (addresses from the foothold note):

* `configureACIOPhyLaneMode(lane_sel, mode)` — writes a **3-bit mode field per
  lane at `core + 0x48`**: `bfxil reg, mode, #0, #3` (bits `[2:0]`) in one pass
  and `bfi reg, saved, #3, #3` (bits `[5:3]`) in the other; arg1 bit 0 selects the
  pass. This is exactly `ACIOPHY_LANE_MODE_RX0/TX0`.
* `configureDPTunnelMode(u64, idx)` — writes `core + 0x08` (`ACIOPHY_CFG0`):
  `orr #4` (`COMMON_SMALL`), then `orr #8` (`COMMON_SMALL_OV`), then, after an
  intervening call, `orr #1` (`COMMON_BIG`) — the same "big/small PMA" override
  programming Linux's own lane-power code does (`atc.c` ~1914-1951).

So the PHY-side effects of Apple's enable sequence are **already implemented in
Linux**. This is why the PHY was never the wall.

### Unresolved detail (do not guess)

`configureDPTunnelMode` / `unconfigureDPTunnelMode` also maintain a **3-entry,
index-keyed table at object offsets `0x3a8`, `0x3b0`, `0x3b8`** (index 0..2):
`configure` is a no-op if the entry already equals the incoming `u64`, and
`unconfigure(idx)` returns immediately if the entry is zero, else clears it. The
semantics of those three entries are **not** established — do not assert that
they are lane configs, PMA values or DART domains. (In the same functions the
`u64` is also used as a target of a virtual call, which is why the note does not
call it "a physical address".)

## How a `dpin` driver would get instantiated

`drivers/thunderbolt/apple.c:795` calls:

```c
ret = of_platform_populate(acio->np, NULL, NULL, acio->dev);
```

so **every child node of the ACIO node becomes a platform device**. Apple's ADT
places `dpin0`/`dpin1` under `acio1` (with `atc-phy1` + `atc1-dpxbar` as the
other parents), so:

* adding `dpin@b01e50000` and `dpin@b01e58000` as children of `cio@b01ac0000`
  (and the die-1 twin) is enough for a matching driver to bind;
* no kernel-driver change is needed just to get the device created.

Recovered addresses (unchanged, from the ADT, cross-checked earlier):
`dpin0 = 0xb01e50000`, `dpin1 = 0xb01e58000`, size `0x4000`, IRQ 1354/1355.

**For the register protocol, use `DPIN-IMPLEMENTATION.md` — it supersedes the
earlier mapping.** The earlier "`0x04` is a handshake / setting `0x0c` bit 0
activates" reading is **wrong**: `0x0c` bit 0 is an *inactive request* that is
**cleared** to activate, with its ACK at `0x10`. Do not re-derive the protocol
from the older evidence note.

## DT changes are cheap — the DTB is embedded in `/boot/m1n1/boot.bin`

This is a process unlock and it also explains the `KNOWN-GOOD-pre-dtb-*`
backups:

* `/boot/m1n1/boot.bin` is 9,037,538 bytes and contains **111** FDT images
  (magic `0xd00dfeed`); it contains `apple,t6000-atcphy` and
  `apple,t6000-display-crossbar` and does **not** contain `atc-dpin`.
* GRUB does not load a DTB (`/boot/grub/custom.cfg` has no `devicetree` line), so
  the running DT comes from the bootloader image, not from the kernel package.
* The repo already ships the packer:
  `mseries/fairydust/debian/assemble-m1n1-bootbin.py`.

Therefore **a DT-only experiment is a boot.bin repack + reboot, not a 1-3 h
kernel build** — but it *is* a reboot, so batch DT work rather than iterating.

## Concrete next steps

**Current owner constraint: no kernel/module/DTB installation, no reboot, no
cable move.** Everything below that needs hardware is therefore a *proposal*, not
an authorised action.

1. **[no hardware]** Repack `boot.bin` with the two `atc-dpin` child nodes under
   each ACIO and with `atcphy1_xbar` (`mux@b0304c000`) changed from
   `status = "disabled"` to `"okay"`. Verify by diffing the embedded FDTs
   (`d00dfeed` scan + `fdtdump`) before any reboot. **Requires owner
   authorisation and a reboot.**
   Note: `0004`-`0006` already add the DP-IN binding and ACIO1 nodes; this step
   is about the *deployment vehicle* (boot.bin), not about re-authoring them.
2. **[no hardware]** Routing: the DPTX endpoint currently selects only the
   **alt-mode** mux (`dcp->typec_mux`). Getting the stream into a tunnel needs
   the *display crossbar* route (`dpphy`/`dpin0`/`dpin1`) instead — see the
   ordering analysis in
   `evidence/2026-10-16-router-vs-dcp-activation-ordering.md`.
3. **[hardware, needs authorisation]** Reboot once with the new boot.bin, dock
   attached, `dprx_bypass` armed, and read back the dpin + crossbar registers
   *before* writing.

## Do not re-derive

* `tunnel.c` / `tb.c` already do everything the host router side needs; the
  DP-OUT/HPD selection bug is fixed (`0003-dp-out-prefer-adapter-with-hpd.patch`).
* The atcphy "core" block is `regs.core`; offsets `0x08` and `0x48` are
  `ACIOPHY_CFG0` and `ACIOPHY_LANE_MODE_T8103`.
* `startUsingTunnel` is not in `kernelcache.release.mac13j` and not in
  `AppleConvergedPCI`.
* `dpin0`/`dpin1` never appear in `/sys/bus/thunderbolt/devices`; the dock's DP
  adapters are visible only in debugfs.
