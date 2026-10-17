# macOS baseline: the dock HDMI chain works, and macOS drives it from dcpext0

2026-10-17, Claude. Ordinary macOS visit, read-only. Collected with
`run-macos-baseline.sh` (pinned commit `6dad972`, all three tool SHA-256s
re-verified). No cable, boot, display or security setting was changed.
Raw `PRIVATE/` output stays on the owner's Mac
(`~/Documents/wd22tb4-capture-20261017T152413Z`); nothing below contains a
serial number, volume UUID or other device identifier.

## Platform

| Item | Value |
| --- | --- |
| Model | MacBookPro18,3 (j314s) |
| macOS | 27.0.1 (26A434) — not a documented m1n1 hypervisor target (13.5 / 14.8.3) |
| Dock | Dell WD22TB4, USB4 mode, 40 Gb/s, on Thunderbolt/USB4 **Bus 1** |
| Collector status | iodevicetree, ioservice, displays/TB/USB, volumes: OK. Kernelcache found but **not copied** (`kernelcache-paths.txt FAILED:1`). Kernel log query returned no lines. |

At capture time macOS listed only the built-in display. The registry event
logs below show why: the sink was driven earlier in the session and then
unplugged (HPD loss).

## Live ADT confirms the shipped DP-IN metadata

The live IODeviceTree matches what patches 0004–0006 already use:

| Node | Address | IRQ | Parent |
| --- | --- | --- | --- |
| `atc1-dpin0` | `0xb01e50000` (0x4000) | 1354 | `acio1`, transport-index 0 |
| `atc1-dpin1` | `0xb01e58000` (0x4000) | 1355 | `acio1`, transport-index 1 |
| `atc1-dpxbar` | `0xb0304c000` | — | — |
| `dcpext0` | `0x289c00000` | — | — |
| `dcpext1` | `0x28cc00000` | — | — |

No DT address or interrupt change is indicated.

## What macOS did (IORegistry `EventLog`s)

Times are `EventTime` ticks converted at the 24 MHz timebase; treat
sub-millisecond spacing as approximate.

`AppleATCDPINAdapterPort(atc1-dpin0)` (246 events) and
`AppleDCPDPTXRemotePortUFP` on **`dispext0:dcpdptx-port-epic:0`** (236 events)
record the whole sequence. No other DP-IN or UFP port saw activity.

| t (s after boot) | Event |
| --- | --- |
| 11.63 | DP-IN `TunnelUse=1`, `DisplayRequest` queued, `SinkActive=1` |
| 11.63 | UFP (dispext0 port 0) `DisplayRequest` |
| 11.63 | crossbar0 `ApplyState dfp: 0:ufp0,0-dfp1,1` (dispext0,0 ← atc1 dpin0) |
| 11.63 | DP-IN `TunnelUse=2` |
| 11.633 | DP-IN `TunnelActive=1`, then `Plug` |
| 11.633 | UFP `Activate=1` (≈9 µs after DP-IN active), `Plug` |
| 11.71 | Sink hints: max 4096×2160, 10 bpc, 248.832 MHz active / 297 MHz total pixel rate, not tiled |
| 11.72 | UFP `Downspread=0`, `LinkRate=30` (0x1e, HBR3 8.1 Gb/s) |
| 11.73 | DP-IN `TunnelActive=1` again (re-asserted after the link rate is set) |
| 11.73 | UFP `LaneCount=4` |
| 15.9 → 345.7 | `IRQ` every ≈6.7 s on both DP-IN and UFP, sink stays active |
| 507.0 | `Unplug` (sink HPD lost), hints invalidated |
| 507.2 | lane count/link rate 0, tunnel inactive, `DisplayRelease`, crossbar cleared |

Plug to configured link took about **90 ms**.

## Conclusions

1. **The physical chain works.** Mac USB4 → WD22TB4 → dock HDMI → this
   monitor trains a 4-lane HBR3 link on macOS. The monitor is not the wall;
   H1 ("firmware blocked on a dead/odd sink path") is now unlikely as stated.
2. **macOS uses `dcpext0`, port 0.** It routed `atc1-dpin0` to
   `dispext0,0`. Every Linux run so far used `dcpext1` (`dispext1,0`), via
   patch 0009 `apple,dp-source = <&dcpext1>`. On Linux, `dcpext0` is
   permanently assigned to the built-in HDMI port; macOS allocates
   controllers dynamically and gave `dcpext0` to the tunnel because the HDMI
   port was idle. So this does not prove `dcpext1` cannot work, but
   `dcpext0` port 0 is the only proven combination. The DPTX port (0)
   already matches Linux.
3. **Timing is not the problem.** Linux's 2 s `DPTX_CONNECT_TIMEOUT` is
   ~20× the observed link-configuration time.
4. **Ordering matches the Linux bridge.** DP-IN goes active before the DCP
   port's `Activate`, as patches 0008/0011 do. New detail: macOS re-asserts
   DP-IN `TunnelActive` after setting the link rate and before the lane count,
   consistent with the link-rate-dependent tunnel clock path in
   `REA-DPIN-FINDINGS.md`.

## Next experiment: E4 (staged as patch 0015, not built, not booted)

`0015-experimental-j314s-dcpext0-tunnel.patch` adds
`ENABLE_DCPEXT0_TB_TUNNEL` (defined in `t6000-j314s.dts`): `dcpext0` takes the
tunnel role (ATC1 crossbar "dpin0" control, mux state 0, `dptx-phy = <1>`,
same `apple,dp-tunnel-phy = <&dpin1_0>`, HDMI GPIOs and the HDMI DP-out
endpoint removed, dpaudio1 link kept); `dcpext1` returns to stock DP-altmode
wiring; the NHI points at `dcpext0`. Built-in HDMI has no display controller
under E4 (already out of scope per `HDMI-FASTEST-PATH.md`).

Offline validation: applies cleanly after 0001–0014. `t6000-j314s` compiles
with stock **dtc 1.6.1** with and without the define (Asahi float-literal
cells integer-ized for the check only); the only added warning is the
`graph_child_address` one `dcpext1` already has. In the E4 DTB (`fdtget`):
`dcpext0` `mux-controls` → `mux@b0304c000` cell 1, `mux-index` 0,
`apple,dptx-phy` 1, `apple,dp-tunnel-phy` → `phy@e50000`, `ports` keeps only
`port@0` (dpaudio1); `dcpext1` → same crossbar cell 0, mux-index 2, no tunnel
properties; NHI `apple,dp-source` → `dcp@289c00000`. An earlier draft that
deleted the whole `ports` node broke the `dpaudio1` graph and was fixed.
Not in CI, not installed, not booted.

Gates before an E4 boot (owner decision):

- Build the boot.bin DT with 0015 and keep the module set from E3; the
  bridge code does not depend on which DCP is the source.
- `dcpext0` is `status = "disabled"` in the DT and enabled by the loader.
  Current m1n1 (`56b77ba`, `kboot.c` `dt_carveout_reserved_regions` →
  `dt_add_reserved_regions`) sets `status = "okay"` on every `dcpextN` whose
  alias exists on t600x, independent of HDMI. Confirm on the installed m1n1
  revision: E4's log must show `289c00000.dcp` probing.
- Keep bypass armed (`dprx_bypass=1`, `dprx_timeout=15000`) for the first
  E4 boot. **E2 (`next_entry=elementary-usb4-dpin-nobypass`) is still armed
  and still targets `dcpext1`;** clear it first if E4 should go first.
- Expect in the log: `Switched dpin0 to dispext0,0` and
  `289c00000.dcp: DCP index:… dptx target phy: 1 … tunnel: 1`. Success is the
  firmware sending `set_active_lane_count`/link-rate calls, then EDID.

## Gaps left by this capture

- Kernelcache not copied (the run printed one candidate; the copy step
  reported failure). Only needed for a future hypervisor trace.
- `log show` returned nothing for the DCP/DPTX/HPD predicate; the
  IORegistry event logs carry the sequence instead.
- `observations.txt` not filled in (physical Mac port, dock HDMI socket,
  monitor model, whether a picture was seen before the unplug at ~8.5 min).
