# Router vs DCP activation ordering — the DP-IN hook must be on the tunnel path

**Date:** 2026-10-16
**Status:** offline source analysis of the pinned tree. No hardware, no reboot,
no cable move. This answers item 2 of `DPIN-IMPLEMENTATION.md`.
**Audience:** the author of 0004-0006 and the next agent.

## The question

The draft enables DP-IN from DCP's ACTIVATE callback, while the USB4 router waits
for DPRX during tunnel activation. Is an earlier hook required?

**Yes.** The DP-IN activation hook belongs on the **Thunderbolt tunnel
activation path**, not on DCP ACTIVATE.

## Why — four structural facts from the pinned source

**1. 0005 contains no router integration at all.** Every hunk in
`0005-experimental-dpin-handshake-tunnel-clocks.patch` touches only
`drivers/gpu/drm/apple/{dcp.c,dptxep.c,dptxep.h}` and `drivers/phy/apple/*`.
Nothing under `drivers/thunderbolt/` is modified by 0004-0006.

**2. The router's DPRX wait runs inside tunnel activation, before any DCP
involvement.** `tb_dp_activate()` (`tunnel.c:1163`) programs the hops, enables
both DP adapters, and finally calls `tb_dp_dprx_start()` (`tunnel.c:1133`):

* with a tunnel callback, `tb_dp_dprx_start()` returns `-EINPROGRESS` and re-arms
  `tb_dp_dprx_work` every `TB_DPRX_POLL_DELAY` (50 ms) until `dprx_timeout`
  (`tunnel.c:1115-1121`);
* the tunnel is only marked active by `tb_tunnel_set_active(tunnel, true)`
  (`tunnel.c:1123`) when the wait returns 0 — or via `dprx_bypass`.

So the DP-IN enable can never be observed by that wait if DCP is what drives it.

**3. A DCP ACTIVATE is itself downstream of HPD and EDID.** DCP ACTIVATE runs
when the DRM pipeline is enabled for a connector. For a real tunnelled sink that
needs the connector reported connected with a valid mode — i.e. HPD plus EDID —
both of which are downstream of the DP-IN adapter being enabled.

This is **not an unavoidable synchronous deadlock**: in this setup DCP can also
be started by the existing debugfs force-link / OOB-hotplug path, which can
overlap the DPRX window. But that start is manual, so there is **no automatic
start bridge** in 0005. `DPIN-IMPLEMENTATION.md` reaches the same conclusion
("a candidate future notification boundary is after both DP adapters are
enabled, before DPRX work starts"); that file is the normative one.

**4. HPD cannot be the trigger, because HPD is read *during* activation.** Per
the superseding protocol in `DPIN-IMPLEMENTATION.md`, activation clears the
inactive request at `+0x0c`, polls the ACK at `+0x10`, and reads HPD at `+0x00`
*while the ACK is pending*. The activation procedure therefore cannot be gated on
the HPD which it exists to observe. (This is the same chicken-and-egg that makes
"HPD queues a real HPD-level read" a notification path, not an activation
trigger.)

## The hook that matches Apple's own design

Apple's `AppleATCDPINAdapterPort` is an `IOTBTTunnelClientInterface` client: it
activates on **tunnel state change** and deactivates on teardown, and
`incrementTunnelUse()`/`decrementTunnelUse()` pair with tunnel use. The Linux
analogue is exactly `tb_dp_activate(tunnel, active)`:

* activate DP-IN **after** `tb_dp_port_enable(tunnel->src_port, true)` and
  **before** `tb_dp_dprx_start(tunnel)` (`tunnel.c:1190-1201`);
* deactivate it in the inactive branch next to `tb_dp_dprx_stop()`
  (`tunnel.c:1183-1188`), so teardown is symmetric;
* do it only for a DP tunnel whose **src_port is a USB4 host DP-IN adapter**, not
  for DP-OUT.

The provider reachability does not exist in 0005 today. Options, least to most
invasive:

* (a) the dpin PHY registers a callback that `tb_dp_activate()` invokes, looked
  up from the tunnel's `src_port` fwnode;
* (b) the dpin driver registers as a `tb` tunnel client;
* (c) a direct phandle lookup from the src_port DT node.

## Ownership / lifetime — still open, do not guess

`incrementTunnelUse`/`decrementTunnelUse` imply the host DP-IN adapter is
**refcounted** across tunnel use, and two tunnels could share one adapter. Linux
has no equivalent refcount, so a naive activate-on-every-tunnel would
double-activate. Resolve the refcount shape before wiring the hook.

## What this does NOT claim

* **Not proven:** that enabling DP-IN makes DPRX complete. The ACIO's opaque
  `startUsingTunnel()` is still unaccounted for and may be required as well.
* **Not the mechanism:** "the display path waits on tunnel-active". It does not:
  `tb_dp_tunnel_active()` (`tb.c:1926`) does bandwidth bookkeeping only
  (`TB_TUNNEL_ACTIVATED` has no DRM listener). The gate is the HPD/EDID one in
  fact 3 above — state it that way.
* No ordering fix here has been built or tested.

## Reproduction

```sh
L=<pinned tree>
grep -n 'tb_dp_activate\|tb_dp_dprx_start\|tb_dp_dprx_work' $L/drivers/thunderbolt/tunnel.c
sed -n '1133,1201p' $L/drivers/thunderbolt/tunnel.c
sed -n '1926,1960p' $L/drivers/thunderbolt/tb.c
grep -n '^+++ ' 0005-experimental-dpin-handshake-tunnel-clocks.patch
```
