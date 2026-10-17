# USB4 DisplayPort tunneling on M1 Pro (dock video) — reverse-engineering map

Status: **experiment 1 installed and tested on hardware — the tunnel activates, the
sink never answers; experiment 2 built and installed; runbook ready. Offline
source/upstream analysis added 2026-10-15 (section 6): `dprx_bypass` can bring the
fabric up but cannot produce video, and the missing piece is upstream's "DP IN
PHY".** (2026-10-15).

This branch now carries the experiment-2 **implementation** as well as the docs:
`0002-experimental-dp-tunnel.patch` (sha256 `c962eff0…`) matches the pin in
`debian/build.sh`, so a build from here reproduces the installed
`7.1.13-elementary-fairydust-usb4-dptunnel` kernel. `re/usb4-exp2` remains the
upstream/ownership branch; the two no longer need syncing by hand.
Next hardware session: [`EXP2-RUNBOOK.md`](EXP2-RUNBOOK.md).
Scope: make the Dell WD22TB4's HDMI/DP outputs work, i.e. tunnel DisplayPort
from the display controller (`DCP`) through the USB4 host router (`ACIO`) to the
dock. This is the "Monitor through the dock" open problem in
[`../../ROADMAP.md`](../../ROADMAP.md).

The everyday non-dock paths (built-in HDMI, direct USB-C adapter) are covered in
[`DOCK-VIDEO-DECISION.md`](DOCK-VIDEO-DECISION.md); this document is the
"gain of function" path the owner asked to pursue.

## 1. The signal path

```
                     +-------------------------------+
  +-----------+      |  ACIO / Host router           |
  | Display   |      |  +----------+   +----------+  |
  | Controller|      |  | DP IN 0  |   | DP OUT   |  |      +--------+
  | (DCP)     |      |  +----------+   | adapter  |--+----->| Dock   |
  |  dcpext0  |      |       ^         +----------+  | USB4 | DP/HDMI|
  |  dcpext1  |      |       |  USB4 tunnel          |      +--------+
  +-----+-----+      +-------|-----------------------+
        |                    |
        v                    |
  +-----+----------------+   |
  | Display crossbar     |---+      feeds DP IN adapters (dpin0 / dpin1)
  | (per ATC PHY)        |
  +-----+----------------+
        |
        v
   +----+------+   +-----------+   +-----------+
   | ATC PHY   |   | Type-C    |   | Type-C    |   (DP Alt Mode: upstream
   | (DP PHY)  |-->| PHY lanes |-->| port      |    "fairydust" already does this)
   +-----------+   +-----------+   +-----------+
```

Four hardware blocks are involved, all with Linux drivers present in our tree:

| Block | Driver | What it does today |
|---|---|---|
| DCP / DPTX endpoint | `drivers/gpu/drm/apple/{dcp.c,dptxep.c,dptxep.h}` | Drives a DP link on a *remote port* (core/atc/die) |
| Display crossbar | `drivers/mux/apple-display-crossbar.c` | Routes a `dispext<n>,<pipe>` stream to `dpphy`, `dpin0` or `dpin1` |
| ACIO / host router | `drivers/thunderbolt/apple.c`, generic `tb` core | USB4 link + tunnels; **DP tunnels deliberately disabled** |
| Type-C PHY | `drivers/phy/apple/atc.c` | Alt-mode DP and USB3/USB4 lanes |

The crossbar is the pivot: **the same driver that already implements DP Alt Mode
already knows how to reach the USB4 DP IN adapters.** Each port's crossbar
exposes three outputs — `dpphy`, `dpin0`, `dpin1` — and enabling one does
`dpxbar_set32(OUT_PCLK1_EN, atc_bit)` + `dpxbar_set32(CROSSBAR_ATC_EN, atc_bit)`
with `atc_bit` = `ATC_DPPHY`/`ATC_DPIN0`/`ATC_DPIN1`. The two `dpin*` outputs are
the ACIO DP IN adapters (USB4 tunnel 0 and 1); only `dpphy` is used today.

## 2. Register / device-tree level facts

Crossbar (`drivers/mux/apple-display-crossbar.c`):

- A mux controller exposes three mux controls, index `0 = dpphy`, `1 = dpin0`,
  `2 = dpin1` (`enum { MUX_DPPHY = 0, MUX_DPIN0 = 1, MUX_DPIN1 = 2 }`).
- The *state* is the input stream: states `0..8` select `dispext(state >> 1)`,
  pipe `state & 1`; `MUX_IDLE_DISCONNECT` (`-2`) disconnects.
- Enabling an output sets `OUT_PCLK1_EN` and `CROSSBAR_ATC_EN` with
  `ATC_DPPHY` / `ATC_DPIN0` / `ATC_DPIN1`, which is exactly the route to the
  ACIO DP IN adapters for `dpin0` / `dpin1`.

DCP (`drivers/gpu/drm/apple/dcp.c`):

```c
/* dcpext1 has: apple,dptx-phy = <1>; mux-index = <2>; */
dptxport_connect(service, /*core=*/0, dcp->dptx_phy /*atc*/, dcp->dptx_die);
dptxport_request_display(service);
...
dptxport_set_hpd(service, true);   /* only when connector_type == DisplayPort */
```

So the DCP is told to drive "remote port" = ATC *n*; the crossbar decides whether
that lands on the Type-C DP PHY or on the ACIO DP IN adapter.

Each of the three host routers in the device tree lists its two DP IN adapters as
bare comments — there are no endpoints:

```
/* 5: DP0 */
/* 6: DP1 */
```

— the comments are there, the wiring is not.

The quirk that hides all of this
(`drivers/thunderbolt/quirks.c`):

> "Nothing drives the Apple host router's DP IN adapters yet (the DCP is only
> wired to the ATC PHYs), so every DP tunnel attempt dies after ~300 DPRX read
> timeouts. Skip them."

## 3. Measured state on this machine (2026-10-15, j314s)

```
dock:      thunderbolt 0-1: Dell WD22TB4 Thunderbolt Dock
host router: thunderbolt-apple-acio b01ac0000.cio   -> usb4_1_acio -> atcphy1
             (b = die 1 block; atcphy1 = "USB-C Left Front")

dmesg:  apple-display-crossbar b0304c000.mux: Switched dpphy to dispext1,0
        apple-display-crossbar 130304c000.mux: Switched dpphy to dispext0,0
        apple-dcp 289c00000.dcp: typec_mux_set() returned: 0        # dcpext0/HDMI
        apple-dcp 28cc00000.dcp: fwnode_typec_mux_get() returned: 0  # dcpext1: no Type-C mux
```

- `b0304c000.mux` is `atcphy1_xbar`, the crossbar of the port the dock is on.
  It currently routes **`dispext1,0` → `dpphy`** — the DP PHY, not a USB4 tunnel.
- `dcpext1` (`dcp@28cc00000`, `apple,connector-type = "DP"`) is the external
  display controller for that port and is `status = "okay"`.
- `card2-DP-1` is `disconnected`: the DCP never starts a link because the
  Type-C alt-mode / DCP hot-plug trigger never fires for a USB4 dock.

Net: the port, the crossbar, the DCP and the USB4 link are all up; only the
routing (crossbar mux) and the "who drives the DP IN adapter, and when" glue are
missing.

## 4. The two missing links

1. **Config change (cheap, this patch):** point `dcpext1` at the crossbar's
   `dpin0` mux control instead of `dpphy`, and stop suppressing DP tunnels.
   One cell in the device tree plus a module parameter.
2. **Protocol glue (needs RE):** *something* must make the DCP drive its stream
   into the ACIO. For USB4 the DPRX capabilities are read from the DP IN adapter
   *before* the tunnel is extended, so the macOS sequence is almost certainly
   "start the DCP on the DP IN adapter → read DPRX → extend tunnel". The exact
   apcall/sequence (and whether `dptxport_connect()` takes a different remote
   port, or a new "tunnel" parameter, for a tunnelled endpoint) is the part that
   needs a macOS trace.

### What the DCP side actually looks like (source facts, 2026-10-15)

Reading `drivers/gpu/drm/apple/dptxep.c`, `dcp.c` and `drivers/phy/apple/atc.c`
answers more than expected — and changes experiment 2:

- The DCP's external stream is `dispextN` and the crossbar routes it to one of
  `dpphy` / `dpin0` / `dpin1`. **The ATC PHY is not in the DP path for a
  tunnel:** `dpphy` is the ATC-lane output, while `dpin0`/`dpin1` are the ACIO's
  DP IN adapters. So `dpin0` is the whole display-side change; the DP stream is
  encapsulated by the ACIO from there.
- `dcp_dptx_connect()` (run at probe for externals, and from
  `apple_connector_oob_hotplug`) does
  `dptxport_connect(service, core = 0, atc = dptx_phy, die = dptx_die)`, then
  `dptxport_request_display()`, then `dptxport_set_hpd(true)` for a DP
  connector. For `dcpext1` that is core 0, atc 1, die 0, `CONNECTED`. The
  remote-port encoding is `CORE = bits 3:0`, `ATC = bits 7:4`, `DIE = bits 11:8`,
  `CONNECTED = bit 15` (`dptxep.h`), so a *tunnelled* endpoint may use a
  different `atc`/`die` — one of the things the trace must settle.
- **Hazard:** `dptx->atcphy = dcp->phy` (the `dp-phy`, here `atcphy1`), and
  `dptxport_call_set_link_rate()` / `set_active_lane_count()` call
  `phy_configure(atcphy1, ...)` → `atcphy_dpphy_configure()` →
  `atcphy_dp_configure()` (DP PLL/lane registers). For the dock, `atcphy1` must
  stay in `APPLE_ATCPHY_MODE_USB4`, so reconfiguring it for DP is at best noise
  and at worst fatal to the USB4 link. macOS must point a tunnelled endpoint
  somewhere else — hence the new experiment 2.
- `dptx->phy_ops.dp.set_lanes = (dcp->dptx_phy > 3)`: an `apple,dptx-phy` above
  3 marks a standalone dptx/lpdptx PHY instead of one behind the ATC PHY.
  `dcpext1` uses 1, `dcpext0`/HDMI uses 3.
- The ATC PHY's DP-vs-USB4 mode comes from its **Type-C mux** (the typec mux set
  path calls `atcphy_configure(target_mode)`). `dcpext1` has no Type-C-mux
  fwnode, so `dcp->typec_mux == NULL` and the dock is what puts `atcphy1` into
  `USB4` mode — which is why there are no DP lanes to "take".

## 5. Experiment 1 — `0002-experimental-dp-tunnel.patch`

Applies on top of `0001-usb4-thunderbolt-apple-m1pro-on-fairydust.patch`.
Off by default; the normal build is unchanged.

Changes:

1. `arch/arm64/boot/dts/apple/t6000-j314s.dts` — define
   `ENABLE_DCPEXT_TB_TUNNEL` (`dcpext1` itself is already enabled for the
   J314/J316 family by `t600x-j314-j316.dtsi`).
2. `arch/arm64/boot/dts/apple/t600x-j314-j316.dtsi` — under
   `ENABLE_DCPEXT_TB_TUNNEL`, `dcpext1` gets `mux-controls = <&atcphy1_xbar 1>`
   (dpin0) instead of `<&atcphy1_xbar 0>` (dpphy).
3. `drivers/thunderbolt/quirks.c` — new module parameter
   `allow_dp_tunnel` (boot: `thunderbolt.allow_dp_tunnel=1`); when set, the
   Apple host routers keep DP tunneling enabled instead of `QUIRK_NO_DP_TUNNEL`.
4. `drivers/gpu/drm/apple/connector.c` — new write-only debugfs attribute
   `force_link` per connector, which calls `dcp_dptx_connect_oob()` /
   `dcp_dptx_disconnect_oob()`. This is the manual stand-in for the missing
   trigger: it makes the DCP drive `dcpext1` into the DP IN adapter so we can
   observe whether DPRX answers.

### Build

```
FAIRYDUST_DP_TUNNEL=1 FAIRYDUST_WORKDIR=... FAIRYDUST_SOURCE_ARCHIVE=... \
  bash mseries/fairydust/debian/build.sh --build
```

or the `.github/workflows/daily-9.0.yml` dispatch with `fairydust_tunnel = true`.
The experimental kernel uses release `7.1.13-elementary-fairydust-usb4-dptunnel`
so it cannot be confused with the working `...-usb4` kernel.

### Built artifact (2026-10-15, CI run 38776005043)

The run for branch `docs/dock-video-decision`, source commit
`083f3a19ef63de52f8ad8f4ae81c1607c4b3c2aa`, produced the package; it checks out
statically without root:

- `linux-image-7.1.13-elementary-fairydust-usb4-dptunnel_7.1.13+elementary.usb4-dp1_arm64.deb`
  with a clean `SHA256SUMS`; release string
  `7.1.13-elementary-fairydust-usb4-dptunnel` (so `uname -r` distinguishes it).
- The DTB ships at `usr/lib/linux-image-<release>/apple/t6000-j314s.dtb`, i.e.
  exactly the path `install-ci-kernel.sh --swap-dtb` uses.
- **The device-tree change is in the compiled DTB.** `dcp@28cc00000` (dcpext1)
  has `mux-controls = (phandle 153, 1)` — index 1 is `dpin0` — where the working
  boot.bin has `(phandle 153, 0)`, `dpphy`. `mux-index` is still 2, and the HDMI
  node `dcp@289c00000` is unchanged at `(146, 0)`.
- **The code changes are in the modules.** `appledrm.ko` exports the `force_link`
  debugfs attribute, and `modinfo -p thunderbolt.ko` lists
  `allow_dp_tunnel:leave DP tunneling enabled on Apple host routers
  (experimental) (bool)`.

The ISO job in the same run fails ("Build experimental arm64 image", unrelated
to the kernel); only the `fairydust-kernel-packages-*` artifact is used here.

### Install (from the CI artifact)

The experimental kernel installs *side by side* with the working one, as its own
GRUB entry, and the device-tree change is applied by swapping just the `j314s`
DTB inside the existing boot image:

```
A=<artifact-dir>          # may be the download dir or the artifact dir inside it
sudo bash mseries/fairydust/usb4/install-ci-kernel.sh "$A" --swap-dtb \
     --suffix fairydust-usb4-dptunnel \
     --entry-id elementary-usb4-dptunnel \
     --cmdline thunderbolt.allow_dp_tunnel=1            # dry run
# ... repeat with --apply to actually install
```

Use the flags rather than the `KERNEL_*` environment variables: `VAR=... sudo
cmd` is stripped by sudo's `env_reset`, so the variables would silently fall back
to the default variant (which then collides with the working kernel and aborts).
`gh run download -D dir` nests the files under `dir/<artifact-name>/`; the script
accepts either layout.

`--with-ci-bootbin` replaces the whole boot image instead of swapping one DTB.
Then reboot and pick the `fairydust-usb4-dptunnel test` entry. The command-line
parameter is belt-and-braces — the module parameter can also be flipped at
runtime with `modprobe thunderbolt allow_dp_tunnel=1`.

The GRUB entry is separate from the working one, but **the device tree is not**.
There is no `devicetree` line in any `grub.cfg`/`custom.cfg` entry on this
machine and no DTB under `/boot`, so the tree always comes from the one shared
`/boot/m1n1/boot.bin`, which m1n1/u-boot consume *before* GRUB runs. Swapping the
DTB therefore changes the tree for every entry, including the working one. This
is acceptable here because the delta is a single property (measured, see below)
and the routed path is already exercised on the current kernel — the boot log
already shows `Switched dpphy to dispext1,0` — so the working entry would boot
with `dispext1 -> dpin0` instead of `dispext1 -> dpphy`. `--apply` copies the
original image to `/root/usb4-backup-<stamp>/boot.bin` and
`/boot/m1n1/boot.bin.KNOWN-GOOD-pre-usb4-<stamp>` first;
`cp /boot/m1n1/boot.bin.KNOWN-GOOD-pre-usb4-<stamp> /boot/m1n1/boot.bin` while
running either kernel restores it. If the tree itself ever prevented Linux from
booting, the restore has to be done from macOS (the ESP is readable there) — see
`RECOVERY.md`.

The delta was measured by parsing the live tree out of `boot.bin` and the
experimental DTB from the `.deb` (`/soc/dcp@28cc00000/mux-controls`, phandle 153
= `mux@b0304c000` = `atcphy1_xbar`):

```
live: 00 00 00 99 00 00 00 00     # arg 0 = dpphy
exp : 00 00 00 99 00 00 00 01     # arg 1 = dpin0
```

Both are 93189 bytes with identical structure/strings offsets and the same 578
nodes, and that is the *only* property that differs, so the splice cannot shift
anything and nothing else about the tree changes.

Verified non-root on this machine (`swap-dtb.py` against the live
`/boot/m1n1/boot.bin`): the DTB run is found (110 trees, offsets 3932160 to
8725127), exactly one tree matches `apple,j314s` (#25, 93189 bytes), and an
identity swap reproduces the input byte for byte
(`sha256 5cbc5f30019209072d32fdd2d53122a81348129f6ab4c58959b5a2fdf8539d55`). The
script re-parses its own output and asserts the gzip U-Boot tail is unchanged.
Because it splices the tree in place, later trees and the tail shift by the size
delta; that is fine because the consumers scan the magic/size headers rather
than using absolute offsets.

`install-ci-kernel.sh` requires root (it writes to the ESP, `depmod`, a chroot
`mkinitcpio` and GRUB), and `sudo` on this machine asks for a password, so the
dry run and the `--apply` both have to be launched from a real terminal.

**Applied on this machine 2026-10-15 (not yet booted).** Log:
`/tmp/opencode/logs/install-apply-20261015-140455.log`. `swap-dtb.py` reported
`110 DTBs from offset 3932160 to 8725127; replacing #25 (93189 -> 93189 bytes)`
and `5cbc5f30…` → `4f793ffa…`. Independent re-check after the fact: byte-diffing
the installed `boot.bin` against the backup shows **exactly one differing byte**
(offset 4478434) inside the DTB run; the installed `j314s` tree reads
`mux-controls = 00 00 00 99 00 00 00 01` (arg 1, `dpin0`) with `mux-index` still
2, the HDMI node still arg 0, the experimental DTB bytes present once and the
original zero times. The backup still hashes to the original `5cbc5f30…`, so the
rollback is exact. ESP went 229 MB → 184 MB free. `mkinitcpio` warned about
`xhci_pci`/`dockchannel_hid` firmware, the aarch64 microcode hook, and a missing
`drm_privacy_screen_register` symbol — same warnings the working kernel's
initramfs build produces, and the image was generated successfully.

### Test

Boot the experimental kernel with `thunderbolt.allow_dp_tunnel=1` (or
`modprobe thunderbolt allow_dp_tunnel=1`), then:

```
# 0. confirm the experimental device tree is actually the one that booted:
#    arg 1 = dpin0; arg 0 would mean the original tree (experiment not armed)
xxd -p /proc/device-tree/soc/dcp@28cc00000/mux-controls      # expect ...00000099 00000001

sudo bash mseries/fairydust/usb4/test-dp-tunnel.sh
# if the DCP did not start by itself:
echo 1 | sudo tee /sys/kernel/debug/dri/*/*DP-1/force_link
sudo bash mseries/fairydust/usb4/test-dp-tunnel.sh
```

The step-0 read is the one check that separates "the route is wrong" from "the
experiment never ran": `/proc/device-tree` is the tree the kernel was handed, so
it says which DTB m1n1 actually served.

### How to read the result

- **Success signal:** in `dmesg`, the DPRX read now completes (no repeated
  `DPRX read timeout`), and `tb` logs a DP tunnel or a bandwidth allocation.
  That proves the crossbar → ACIO DP IN route works and the remaining problem is
  purely "who triggers the DCP".
- **Failure signal:** `DPRX read timeout` still floods. Then either the crossbar
  route is wrong (try `dpin1`, `<&atcphy1_xbar 2>`), the DCP did not actually
  start (check `dcp_dptx_connect` lines and the crossbar
  `Switched dpin0 to dispext1,0` line), or the ACIO DP IN adapter needs
  explicit enablement. The `thunderbolt.dprx_timeout` parameter (ms, `-1` waits
  forever) makes a single attempt easier to watch in `dmesg`.
- **Danger signal:** loss of the USB4 link / dock USB devices when the DCP
  drives. `dcpext1` has no Type-C-mux fwnode (`fwnode_typec_mux_get() returned:
  0`), so its `typec_mux_set()` is never called and it cannot reconfigure
  `atcphy1` itself — if the link still drops, the ACIO and the DP IN adapter are
  fighting over the PHY and this approach needs rethinking.

### Result: experiment 1 on hardware — 2026-10-15 (boot 14:13-15:32)

The kernel booted (`7.1.13-elementary-fairydust-usb4-dptunnel`), the tree was
armed (`mux-controls` = arg 1) and the crossbar took the new route
(`apple-display-crossbar b0304c000.mux: Switched dpin0 to dispext1,0`), with
`thunderbolt.allow_dp_tunnel=1` on the command line. **It still did not produce
video**, but the failure moved one step deeper: from "the tunnel is never
attempted" to "the tunnel comes up and the sink cannot be read".

With the dock attached and a display hotplugging on the dock's DP OUT, the
connection manager did everything short of video:

```
0:5: DP IN available
1:13: DP OUT available
0: allocated DP resource for port 5
available bandwidth for new DP tunnel 22500/22500 Mb/s
0:5 <-> 1:13 (DP): bandwidth allocation mode enabled
0:5 <-> 1:13 (DP): estimated bandwidth 22500 Mb/s
activating Video path from 0:5 to 1:13
Video path activation complete
activating AUX TX path from 0:5 to 1:13
AUX TX path activation complete
activating AUX RX path from 1:13 to 0:5
AUX RX path activation complete
0:5 <-> 1:13 (DP): DPRX read timeout      (x21479 on 1:13, x4054 on 1:14)
```

The host DP IN adapter `0:5` and a dock DP OUT adapter pair up, bandwidth is
allocated in allocation mode, and all three fabric paths activate — four times
over the session. **Nothing ever gets past the DPRX read**: no DPCD data, no link
rate, no training, no video. `force_link` was never exercised (no debugfs writes
in the log). Across the whole persistent journal this is the only boot that ever
reached path activation (`DPRX=25533 path_activations=4`); every other boot shows
0 and 0. So the experiment confirmed the device-tree change on real hardware and
advanced the failure to the sink's DPCD over AUX, but did not restore video.

Caveat, and why the next step is an A/B: the tunnel-side steps above do not
involve the display crossbar at all — allocation and path activation are
host-router <-> dock-router. What the crossbar change buys is the DCP's video
route into `dpin0`. Because the tree is global (see above), no boot has yet run
`allow_dp_tunnel=1` with the *original* `dpphy` route, so we cannot yet claim the
crossbar change was operative. Restoring the backup `boot.bin` and rebooting the
same kernel settles that in one reboot, and is now the cheapest experiment here.

Also observed: the test boot itself carried no `dprx_timeout` (only
`allow_dp_tunnel=1`), so those 25533 lines came from the module default, and the
storm ran continuously from 14:23:00 until the dock was unplugged at 14:55:47.
That unplug is what wedged the Type-C port — see section 9: unplugging while a
DPRX read is in flight deadlocks `apple_nhi_remove` against the `tps6598x` mutex,
and only a reboot clears it. The
GRUB entry has since been changed to `thunderbolt.dprx_timeout=3600000`; prefer a
short bound, and disarm at runtime with `dprx_bypass=1` before touching the cable.

And in the next boot (boot `-1`, 15:34) the suspend attempt ends at
`PM: suspend entry (s2idle)` with nothing after it and the machine had to be
power-cycled. Suspend with the USB4 dock attached stays unsafe, as `CUTOVER.md`
already warns.

### Clue: the DCP firmware does its own sink detection — measured 2026-10-15 16:06

Seventeen minutes into an idle boot **with no dock attached**, the DCP on the
tunnelled connector said this twice:

```
apple-dcp 28cc00000.dcp: DPTXPort: acking unhandled call 20
apple-dcp 28cc00000.dcp: dcp_dptx_disconnect(port=0)
```

`dptxep.c` ACKs DPTXPort calls it does not implement ("just try to ACK and hope
for the best..."), and call 20 is `DPTX_APCALL_INACTIVE_SINK_DETECTED`
(`dptxep.h`). Two consequences:

* The **firmware** owns sink detection on the tunnelled path, and it starts
  probing on its own — no driver `dcp_dptx_connect` was logged in that boot. The
  router's `DP_COMMON_CAP_DPRX_DONE` bit is therefore almost certainly set by the
  firmware *after* it reads the sink, which is exactly why experiment 1 saw a
  live tunnel and then nothing: DPRX_DONE never came because the firmware found
  no active sink. `dprx_bypass` can bring the fabric up but cannot make the
  firmware see a sink it cannot reach.
* Call numbers are now worth watching in any session (`dptxep.h`): 5/6 will/did
  change link config, 7-9 link rate, 10-12 lanes, 18 HPD support, 19 force
  hotplug detect, 20 `INACTIVE_SINK_DETECTED`, 21 tiled hints, 22-24 device not
  responding / busy / not started. Calls 5/6/7/9 appearing would mean the
  firmware is driving the link — a much better success signal than a clean log.
  `test-dp-tunnel.sh` now prints a call census.

## 6. What the source and upstream say — offline analysis, 2026-10-15

Written while the dock was unavailable, by reading the pinned tree
(`ce9f2eba`, fairydust on 7.1) and the public Asahi/LKML record. No hardware was
touched. This is the interpretation the next hardware session should carry.

### 6.1 Who sets `DPRX_DONE`, and what `dprx_bypass` actually buys

`tb_dp_wait_dprx()` (`tunnel.c:1063`) polls the **host router's own DP IN
adapter** — `tunnel->src_port`, our `0:5` — for bit 31 of `DP_COMMON_CAP`
(`DP_COMMON_CAP_DPRX_DONE`). The kernel does not do the AUX exchange: the router
hardware does, and it sets the bit (and fills `DP_LOCAL_CAP` / `DP_REMOTE_CAP`)
once its read of the downstream sink completes. The DP IN adapter is armed at the
end of `tb_dp_activate()` by `tb_dp_port_enable(in, true)`
(`switch.c:1535`), which sets `ADP_DP_CS_0_VE | ADP_DP_CS_0_AE` (Video Enable +
AUX Enable) — that is the trigger for the state machine.

Experiment 2's `dprx_bypass=1` makes `tb_dp_wait_dprx()` return 0 immediately.
Consequences, exactly:

- the retry storm stops (the collector's `DPRX read timeout` counter freezes);
- `tb_dp_dprx_work()` marks the tunnel active at once;
- the activation callback `tb_dp_tunnel_active()` (`tb.c:1907`) then reads the
  consumed bandwidth; because the wait now returns 0 it takes the
  bandwidth-allocation-mode branch (`tb_dp_bandwidth_mode_consumed_bandwidth()`),
  which reads `DP_LOCAL_CAP`.

And here is the limit: the comment at `tunnel.c:1203` states that `DP_LOCAL_CAP`
"gets updated to the lowest AUX read parameter values". If the AUX read never
happened, that register still holds its reset/default value — not the sink's real
caps. **Therefore `dprx_bypass` can bring the fabric up but cannot produce video.
It is a fabric probe, not a fix.** Treat "tunnel active + no picture" under bypass
as the expected, informative outcome, not a regression.

Upstream says the same thing in its own words: `tb_dp_tunnel_active()`'s failure
branch warns that DPRX negotiation most likely did not complete "because there is
no graphics driver loaded or **not all DP cables where connected to the discrete
router**" (`tb.c:1949`). That is a sink/cable-side symptom, which is why tomorrow
is as much a sink question as a host question.

### 6.2 Upstream status: nothing newer to import, and the pieces named

- Asahi's own documentation states the hardware *can* do it: `dcp`/`dcpext`
  "USB-C ports: DP altmode, or USB4 tunneling with 2 controllers max per port."
  The controller support is the gap, not the silicon.
- The author of the Apple drivers, Sven Peter, on why DP tunnels do not work on
  Apple yet (LKML, 2026-08-18, `Re: [PATCH 1/5] thunderbolt: Fix tunnel reference
  leak...`):

  > the only reason DP tunnels don't work yet is because they need **two separate
  > MMIO blocks** (what macOS calls **"DP IN PHY"** and **"display crossbar"**) and
  > possibly also the **display co-processor** to be up. Once that's done they
  > should come up normally.

  Mapping onto this document: *display crossbar* = `apple-display-crossbar`
  (experiment 1); *display co-processor* = the DCP (experiment 2); **"DP IN PHY"
  is a third block we have not identified or programmed.**
- The Asahi `tbt-reset-wip` branch is the bring-up work: "only XDomain works
  since pcie, dp and usb3 tunnels need more bringup work, and not all cables work
  because I'm not forwarding the information like Apple's NHI expects them just
  yet." So there is no finished upstream DP-tunnel implementation to adopt; the
  most up-to-date method *is* mimicking macOS (section 8).
- Phoronix, 2026-08-31, on the 19-patch USB4/Thunderbolt series for M1/M2/M3:
  "Right now only XDomain connections and USB3-via-USB4 tunnels are supported.
  Both PCIe and DisplayPort tunnels will come later since those require
  additional work and reverse engineering that is not done yet."
- The DRM core does now ship DP-tunnel helpers (`DRM_DISPLAY_DP_TUNNEL`,
  `drivers/gpu/drm/display/drm_dp_tunnel.c`, Imre Deak) — but they are written for
  i915/discrete-GPU BWA, and the Apple DCP does not use them. They are useful as a
  *description* of the DP-tunnel register model (tunneling OUI, DP IN adapter
  info, BW granularity, allocated/estimated BW, DPTX bandwidth-allocation mode).

### 6.3 Our unplug hazard is a known upstream bug, with a fix we predate

`DP-TUNNEL-RE.md` section 9 records that unplugging the dock with a DPRX read in
flight wedges the Type-C port. That is not our bug:

> On the Apple NHI unplugging the cable runs into just that reliably because the
> read can never finish right now and because the unplug powers down the entire
> USB4 complex and removes the NHI device.

It is the motivation for Sven's series **"thunderbolt: Fix DP tunnel teardown
while an async DPRX read is running"** (v1 2026-08-17, v2 08-23, v3 08-29; six of
seven patches applied to `thunderbolt.git/fixes`). It makes `tb_stop` tear down
inactive DP tunnels, holds a router reference per HopID, and cancels the DPRX work
before the tunnel can outlive the switch.

**Our build predates it** (verified against this tree): `tb_dp_dprx_start()` still
takes its tunnel reference unconditionally *before* the callback check
(`tunnel.c:1123`) and `tb_stop` does not deactivate DP tunnels.

Concrete backport notes (v3, 7 patches, base-commit `8d3ae592…`; patches 1–6 were
applied to `thunderbolt.git/fixes`, patch 7 is a deferred cleanup):

1. `thunderbolt: Hold a router reference for each allocated HopID`
2. `thunderbolt: Make the DP tunnel activation callback mandatory`
3. `thunderbolt: Fix domain reference leak when DPRX read is canceled`
4. `thunderbolt: Don't access a DP tunnel after its DPRX read was canceled`
5. `thunderbolt: Mark discovered tunnels as active`
6. `thunderbolt: Tear down inactive DP tunnels when the domain is stopped`
7. `thunderbolt: Drop the DP tunnel activation callback data` (deferred)

It touches `switch.c`, `tb.c`, `test.c`, `tunnel.c`, `tunnel.h` — and it rewrites
`tb_dp_wait_dprx` / `tb_dp_dprx_work` and `tb_stop`, **exactly where experiment 2
inserts `dprx_bypass`**. A backport therefore has to be rebased *on top of*
`0002-experimental-dp-tunnel.patch`, not applied beside it. It is not needed to
run experiment 2 — the bypass plus a bounded timeout already close the hazard — so
this is a deliberate later step, not a test-day change.

### 6.4 The macOS crossbar trace already exists — and it matches experiment 1

The crossbar MMIO reference we planned to capture from macOS is already in the
Asahi record, captured by Janne Grunau's `DisplayCrossbarTracer`:

- `gist.github.com/jannau/b9d6826fa649b712463c10f7651dd01d` — *m1 Max → HP G4
  Thunderbolt dock → TB3 display + DP display*
- `gist.github.com/jannau/80a8330219920295d534b76c2b4cabec` — *M1 Max, 4 external
  displays: atc1 DP-alt, atc2 TB dock + TB + HDMI, atc3 built-in HDMI*

For the dock port (`atc2-dpxbar`), macOS writes, in order:
`CROSSBAR_MUX_CTRL = 0x2000` then `0x2002` → `DPIN0_SELECT0` / `DPIN0_SELECT1 =
0x2 = DISPEXT_1_0`; `UNK_TUNABLE = 0x5 (T6000)`; a `FIFO_WR/RD_N_CLK_EN` clock
dance; `OUT_N_CLK_EN`; `OUT_UNK_EN = 0x1 (DPIN0)`; `FIFO_WR_DPTX_CLK_EN`;
`FIFO_RD_PCLK1_EN`; `OUT_PCLK1_EN = 0x1`; `CROSSBAR_ATC_EN = 0x1 (DPIN0)`;
`CROSSBAR_DISPEXT_EN = 0x4 (DISPEXT_1_0)`.

Two conclusions:

1. **macOS routes `dispext1,0` to `DPIN0`** — literally experiment 1's
   `&atcphy1_xbar 1` (mux state 2). The crossbar choice was right.
2. Our `apple_dpxbar_set()` (`apple-display-crossbar.c:224`, MUX_DPIN0) writes the
   same register set, and the driver writes the T6000 `UNK_TUNABLE = 5` at probe
   (`apple_dpxbar_hw_t6000.tunable = 5`). So the crossbar half is
   upstream-equivalent — it is **not** the missing piece, which is consistent with
   experiment 1 reaching path activation.

### 6.5 The open lead: the "DP IN PHY"

There is no `dp-in-phy` node or driver in our tree. The crossbar is a single
16 KiB `mux@…304c000`; the host router and NHI live inside the ACIO
(`cio@b01ac0000`, with `nhi@f00000` as a child); and the DP IN adapters are
reached *only* through router config space via `tb_dp_port_enable()` and friends.
So whatever macOS programs as a second "DP IN PHY" block is, by our model,
unaccounted for — and it is the best explanation for a host router whose DPRX
state machine never reports a sink even though the crossbar, the DCP and the
tunnel fabric are all up.

Next finding target (still needs the macOS trace / ioreg or a device-tree dump
under m1n1): identify that block, its MMIO range, and its bring-up sequence. That
is a sharper question than "who triggers the DCP", because experiment 1 already
showed the firmware does its own sink detection (section 5, call 20).

## 7. Next experiments

1. **A/B the crossbar route, and exercise `force_link`** (cheapest — do this
   first). The hardware run above leaves one ambiguity: no boot has yet combined
   `allow_dp_tunnel=1` with the *original* `dpphy` route. Restore
   `/boot/m1n1/boot.bin.KNOWN-GOOD-pre-usb4-20261015-140455`, keep the same kernel
   and parameter, and reboot. An identical signature (`Video path activation
   complete` then `DPRX read timeout`) means the crossbar route is not the blocker
   and everything left is the DPRX/AUX read — a thunderbolt-side question with no
   display-tree component. In both configurations also try the `force_link` write,
   which has never been exercised, since the DP IN adapter's AUX may only be
   routable once the DCP is actually driving.
2. **Unbind the tunnelled connector's DPTX endpoint from the ATC DP PHY.**
   *Implemented* — this branch's `0002-experimental-dp-tunnel.patch`
   (`apple,dp-tunnel`, NULL `atcphy`, 4-lane default), installed as the
   `…-dptunnel` kernel. The open question is only whether it changes the DCP's
   behaviour at all. While
   `dptx->atcphy` is `atcphy1`, every link-rate change makes the DCP poke
   `atcphy_dp_configure(atcphy1)` although that PHY must stay in USB4 mode.

   The framework paths are already NULL-safe — `phy_validate(NULL, ...)` returns
   `-EINVAL`, `phy_configure(NULL, ...)` returns `-EINVAL`, and
   `phy_set_mode_ext(NULL, ...)` returns `0` — and `set_link_rate()` /
   `set_active_lane_count()` are already guarded by `if (dptx->atcphy)`. So the
   change is small:

   1. DT: mark the tunnelled connector (`apple,dp-tunnel;`, or reuse
      `ENABLE_DCPEXT_TB_TUNNEL`).
   2. `dcp_dptx_connect()`: skip `dptxport[port].atcphy = dcp->phy` for such a
      connector so it stays NULL (the array comes from `kzalloc`).
   3. `dptxport_call_get_max_lane_count()`: when `!dptx->atcphy`, take the
      existing "default to 4 lanes" branch instead of the `-EINVAL` error path
      that currently reports 0 lanes.

   `dcp->phy` itself must stay present, because `dcp_dptx_connect()` refuses to
   run without it (`missing phy` / `-ENODEV`).
3. Try `dpin1` (`<&atcphy1_xbar 2>`) and both. Confirm from the crossbar and
   ACIO state which DP IN adapter index the tunnel is expected to use.
4. Wire the ACIO DP IN endpoints (`port@5`/`port@6`, "DP0"/"DP1") in the device
   tree so the thunderbolt core can associate a DP IN adapter with a source, and
   see what the core does with it.
5. Replace the debugfs hammer with the real trigger: on sink HPD / DP bandwidth
   request, call `dcp_dptx_connect()` for the DP IN adapter that the tunnel will
   use, then let the core read DPRX.
6. Only then: the DCP firmware protocol for a *tunnelled* DPTX endpoint, guided
   by a macOS trace.

## 8. The sanctioned RE method

Per [`README.md`](README.md) and [`RECOVERY.md`](RECOVERY.md), and per the
ice3186/linux prototype, the last unknown — how the DCP starts a *tunnelled*
DPTX endpoint, and the DPIN0/DPIN1 crossbar programming — must come from a trace
of macOS driving the same dock, captured from a second computer with the m1n1
hypervisor.

The tooling already exists, and its dependencies are now vendored off-system
(no `pip`, no `apt`, no `sudo`):

```
bash mseries/fairydust/usb4/m1n1-trace-deps.sh
```

That fetches the two pure-Python wheels `proxyclient` needs
(`construct==2.10.70`, `pyserial==3.5`) into
`~/.local/share/m1n1-proxyclient/site` and prints the `PYTHONPATH`. From the
**second** computer, with the Mac booted into m1n1 and the WD22TB4 + monitor
attached:

```
export PYTHONPATH=~/.local/share/m1n1-proxyclient/site:<m1n1>/proxyclient
python3 <m1n1>/proxyclient/tools/run_guest.py \
  -m <m1n1>/proxyclient/hv/trace_dcp.py  <m1n1>.macho   # DCP / AFK / ASC traffic
python3 <m1n1>/proxyclient/tools/run_guest.py \
  -m <m1n1>/proxyclient/hv/trace_dptx.py <m1n1>.macho   # DPTX PHY MMIO
```

`proxyclient/hv/` already ships DCP- and DPTX-specific tracers (`trace_dcp.py`
is a full AFK/ASC endpoint tracer built on `m1n1.fw.dcp.ipc`). Targets: the
sequence the DCP uses when the dock's DP sink appears, the remote-port encoding
for a tunnelled endpoint, AUX routing, HPD direction, and the
`CROSSBAR_ATC_EN` / `CROSSBAR_MUX_CTRL` writes that select `dpin0`/`dpin1`.

This cannot be done from this machine alone (one computer, no second host
attached); it is the one genuinely blocking dependency.

## 9. Hazard: unplugging the dock with a DPRX read in flight

**Measured 2026-10-15.** During experiment 1 the dock was unplugged at 14:55:47
while the host router's DPRX read was still running (`dprx_timeout=-1`/module
default, so the read never stopped). The Type-C port wedged: `apple_nhi_remove`
deadlocked against the `tps6598x` (CD321x) mutex, and the port stayed dead — no
hotplug, no USB, no charging — until a hard power-cycle. Nothing at runtime
clears it.

What happens, in stock code (experiments 1 and 2 do not touch this path):

    cd321x_update_work [tps6598x_core]        # cable removal, holds the tps6598x mutex
      -> cd321x_deactivate_altmodes -> typec_altmode_update_active
      -> apple_cio_altmode_notify -> apple_cio_set_cable_info(0)
      -> apple_cio_stop -> of_platform_depopulate        # removes the NHI device
      -> apple_nhi_remove -> tb_domain_remove
           -> wait_for_completion(&anhi->nhi.domain_released)   # never completes

`domain_released` is completed in `tb_domain_release()` (`domain.c`) when the tb
domain's last reference drops. `tb_domain_remove()` calls `tb->cm_ops->stop()`
(= `tb_stop()`), which drops DP-tunnel references **without deactivating the
tunnels**, so nothing cancels the `dprx_work` still waiting for DPRX; the tunnel
outlives `tb_switch_remove` and its references keep the domain alive. The waiting
kworker holds the `tps6598x` mutex the whole time, so the Type-C IRQ thread and
every later module unload block on it too. No userspace recovery exists — no
process holds an fd on the tb char device; the reference is kernel-side.

Upstream describes it in exactly these terms: *"This can be triggered by
unbinding the driver while a DP tunnel is still waiting for the DPRX capabilities
read to finish. On the Apple NHI unplugging the cable runs into just that
reliably because the read can never finish right now and because the unplug
powers down the entire USB4 complex and removes the NHI device."* (linux-kernel,
"thunderbolt: Hold a router reference for each path", v2 1/7, 2026-08-24). The
same thread explains why a full ACIO teardown per cable is unavoidable: the
cable-info VSE register "appears to be effectively write-once after each boot of
the co-processor", and writing a second connection's value crashes it ("assert
4357 violated").

Rules that follow, in order of preference:

1. **Never unplug the dock while a DPRX read is in flight.** Arm
   `dprx_bypass=1` *before* attaching the dock (runbook section 1.2): with the
   bypass the read returns instantly, which removes the window.
2. If the bypass is not armed, bound the read instead of leaving it open:
   `thunderbolt.dprx_timeout=<a few seconds>`, not `-1`/an hour. The entry
   currently carries `3600000` ms; a short value is safer.
3. Do not suspend with the USB4 dock attached (the next boot hung at
   `PM: suspend entry (s2idle)` and needed a power-cycle; `CUTOVER.md` warns of
   the same).
4. Recovery when it does wedge: **reboot**. `sudo reboot` works — neither
   `tps6598x` nor the Apple thunderbolt driver registers a `.shutdown` callback,
   so the stuck mutex does not block `device_shutdown()`.

This is a known upstream bug with a fix we predate — see section 6.3; backporting
Sven Peter's "Fix DP tunnel teardown while an async DPRX read is running" series
is the principled fix rather than relying on the bypass.

## 10. References

- Crossbar: `drivers/mux/apple-display-crossbar.c` (Sven Peter).
- DCP DPTX endpoint: `drivers/gpu/drm/apple/dptxep.c`, `dptxep.h`.
- Host router: `drivers/thunderbolt/apple.c` (block diagram in the header).
- DPRX / async activation: `drivers/thunderbolt/tunnel.c`
  (`tb_dp_wait_dprx`, `tb_dp_dprx_work`), `drivers/thunderbolt/tb.c`
  (`tb_dp_tunnel_active`), `drivers/thunderbolt/switch.c` (`tb_dp_port_enable`).
- Upstream teardown fix (predates our base): Sven Peter, "thunderbolt: Fix DP
  tunnel teardown while an async DPRX read is running", v1 5-patch series
  2026-08-17 (later v3, 7 patches, 2026-08-29); six of seven applied to
  `thunderbolt.git/fixes`. Our base is pre-fix: `tb_dp_dprx_start()` still takes
  its reference unconditionally (`tunnel.c:1123`) and `tb_stop()` does not
  deactivate DP tunnels.
- "Two separate MMIO blocks … DP IN PHY … display crossbar": Sven Peter, LKML
  2026-08-18, `Re: [PATCH 1/5] thunderbolt: Fix tunnel reference leak…`
  (`spinics.net/lists/kernel/msg6385777.html`).
- Asahi USB4 bring-up WIP: `github.com/AsahiLinux/linux/commits/tbt-reset-wip/`
  (tip 2026-08-24; ACIO/NHI/quirks only, **no DP bring-up**), plus the 19-patch
  upstream series (Phoronix, 2026-08-31, "no PCIe or DisplayPort tunneling yet").
  Checked 2026-10-15: nothing newer to import.
- macOS crossbar MMIO traces: Janne Grunau gists
  `b9d6826fa649b712463c10f7651dd01d` (TB dock) and
  `80a8330219920295d534b76c2b4cabec` (4 displays).
- DRM DP-tunnel helpers (i915-side model): `drivers/gpu/drm/display/drm_dp_tunnel.c`.
- Upstream state: `fairydust` HEAD `ce9f2eba72c061a50b2d790450e90af3439d8c24`
  (2026-09-08, = our build baseline). DP Alt Mode is "WIP"; Thunderbolt is
  "WIP" with no DP tunneling. Asahi feature table, M1 Pro/Max/Ultra.
