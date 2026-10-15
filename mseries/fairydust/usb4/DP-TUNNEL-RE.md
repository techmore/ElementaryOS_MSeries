# USB4 DisplayPort tunneling on M1 Pro (dock video) — reverse-engineering map

Status: **experiment 1 ready to build** (2026-10-15).
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
already knows how to reach the USB4 DP IN adapters.** Its header comment says so:

> "the display crossbar used to route display controller streams to the three
> different modes (DP AltMode, USB4 Tunnel #0/#1) of the Type-C ports."

## 2. Register / device-tree level facts

Crossbar (`drivers/mux/apple-display-crossbar.c`):

- A mux controller exposes three mux controls, index
  `0 = dpphy`, `1 = dpin0`, `2 = dpin1`.
- The *state* written to a control is the input stream:
  `dispext(state >> 1)`, `pipe(state & 1)`; `state = 9` is disconnected.
- `dpin0`/`dpin1` set `ATC_DPIN0`/`ATC_DPIN1` in `CROSSBAR_ATC_EN` and
  `OUT_PCLK1_EN`, which is exactly the route to the ACIO DP IN adapters.

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

Host router DP IN adapters exist in the device tree but are unwired
(`arch/arm64/boot/dts/apple/t600x-j314-j316.dtsi`, added by
`0001-usb4-thunderbolt-apple-m1pro-on-fairydust.patch`):

```
/* 5: DP0 */
/* 6: DP1 */
```

— the comments are there, the endpoints are not.

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
2. **Protocol glue (needs RE):** *something* must tell the DCP to start driving
   the DP IN adapter, and the DP sink's HPD/AUX must reach the DCP. Today the
   DCP is triggered by (a) the Type-C alt-mode bridge
   (`apple_connector_oob_hotplug -> dcp_dptx_connect_oob`) for alt mode, or
   (b) the DP2HDMI HPD GPIO for the HDMI dcpext. Neither exists for a tunnelled
   DP link, so the DCP sits idle and the thunderbolt core's DPRX read times out.

   For USB4 the DPRX capabilities are read from the DP IN adapter *before* the
   tunnel is extended, so the sequence in macOS is almost certainly
   "start the DCP on the DP IN adapter → read DPRX → extend tunnel". The exact
   apcall/sequence (and whether `dptxport_connect()` takes a different remote
   port, or a new "tunnel" parameter, for a tunnelled endpoint) is the part that
   needs a macOS trace.

## 5. Experiment 1 — `0002-experimental-dp-tunnel.patch`

Applies on top of `0001-usb4-thunderbolt-apple-m1pro-on-fairydust.patch`.
Off by default; the normal build is unchanged.

Changes:

1. `arch/arm64/boot/dts/apple/t6000-j314s.dts` — define `ENABLE_DCPEXT_TYPEC`
   (so `dcpext1` exists at all) and `ENABLE_DCPEXT_TB_TUNNEL`.
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

### Install (from the CI artifact)

The experimental kernel installs *side by side* with the working one, as its own
GRUB entry, and the device-tree change is applied by swapping just the `j314s`
DTB inside the existing boot image:

```
A=<artifact-dir>
KERNEL_SUFFIX=fairydust-usb4-dptunnel \
KERNEL_ENTRY_ID=elementary-usb4-dptunnel \
KERNEL_EXTRA_CMDLINE=thunderbolt.allow_dp_tunnel=1 \
  sudo bash mseries/fairydust/usb4/install-ci-kernel.sh "$A" --swap-dtb          # dry run
# ... repeat with --apply to actually install
```

`--with-ci-bootbin` replaces the whole boot image instead of swapping one DTB.
Then reboot and pick the `fairydust-usb4-dptunnel test` entry; the default entry
is untouched. The command-line parameter is belt-and-braces — the module
parameter can also be flipped at runtime with
`modprobe thunderbolt allow_dp_tunnel=1`.

### Test

Boot the experimental kernel with `thunderbolt.allow_dp_tunnel=1` (or
`modprobe thunderbolt allow_dp_tunnel=1`), then:

```
sudo bash mseries/fairydust/usb4/test-dp-tunnel.sh
# if the DCP did not start by itself:
echo 1 | sudo tee /sys/kernel/debug/dri/*/*DP-1/force_link
sudo bash mseries/fairydust/usb4/test-dp-tunnel.sh
```

### How to read the result

- **Success signal:** in `dmesg`, the DPRX read now completes (no repeated
  `DPRX read timeout`), and `tb` logs a DP tunnel or a bandwidth allocation.
  That proves the crossbar → ACIO DP IN route works and the remaining problem is
  purely "who triggers the DCP".
- **Failure signal:** `DPRX read timeout` still floods. Then either the crossbar
  route is wrong (try `dpin1`, `<&atcphy1_xbar 2>`), the DCP did not actually
  start (check `dcp_dptx_connect` lines and the crossbar
  `Switched dpin0 to dispext1,0` line), or the ACIO DP IN adapter needs
  explicit enablement.
- **Danger signal:** loss of the USB4 link / dock USB devices when the DCP
  drives. That would mean the DCP's `typec_mux_set()` in `dcp_platform_probe()`
  is stealing `atcphy1` from the ACIO. Mitigation: drop `mux-index`/
  `typec_mux_set()` for tunnelled connectors.

## 6. Next experiments

2. Try `dpin1` (`<&atcphy1_xbar 2>`) and both. Confirm from the crossbar and
   ACIO state which DP IN adapter index the tunnel is expected to use.
3. Wire the ACIO DP IN endpoints (`port@5`/`port@6`, "DP0"/"DP1") in the device
   tree so the thunderbolt core can associate a DP IN adapter with a source, and
   see what the core does with it.
4. Replace the debugfs hammer with the real trigger: on sink HPD / DP bandwidth
   request, call `dcp_dptx_connect()` for the DP IN adapter that the tunnel will
   use, then let the core read DPRX.
5. Only then: the DCP firmware protocol for a *tunnelled* DPTX endpoint, guided
   by a macOS trace.

## 7. The sanctioned RE method (for step 5)

Per [`README.md`](README.md) and [`RECOVERY.md`](RECOVERY.md), the missing
protocol details must come from a trace of macOS driving the same dock, captured
from a second computer with the m1n1 hypervisor:

- `m1n1-build/m1n1/proxyclient/` (`hv`, `experiments`, `tools`) on the second
  machine; `pyserial` and `construct` are required.
- Boot macOS on the Mac with the dock attached, capture MMIO/AFK traffic for the
  DCP DPTX endpoint and the ACIO DP IN adapter, and diff against the Linux boot.
- Targets: the AFK call that starts a tunnelled DPTX endpoint, the remote-port
  encoding, AUX routing, and HPD direction.

This cannot be done from this machine alone (one computer, no second host
attached); it is the one genuinely blocking dependency.

## 8. References

- Crossbar: `drivers/mux/apple-display-crossbar.c` (Sven Peter).
- DCP DPTX endpoint: `drivers/gpu/drm/apple/dptxep.c`, `dptxep.h`.
- Host router: `drivers/thunderbolt/apple.c` (block diagram in the header).
- Upstream state: `fairydust` HEAD `ce9f2eba72c061a50b2d790450e90af3439d8c24`
  (2026-09-08, = our build baseline). DP Alt Mode is "WIP"; Thunderbolt is
  "WIP" with no DP tunneling. Asahi feature table, M1 Pro/Max/Ultra.
