# The DPRX timeout is (at least partly) a DP OUT **selection** bug

**Date:** 2026-10-16
**Confidence:** high — read from live hardware registers, and the code path is
identified. Not yet tested by rebuild.
**Impact:** if correct, this produces the `DPRX read timeout` **without the
Apple DP-IN block being involved at all**, and the fix is a few lines.

## Evidence: which dock adapter has the monitor

Read the same register the kernel uses — `ADP_DP_CS_2` (`cap_adap + 0x02`,
`ADP_DP_CS_2_HPD = BIT(6)`) — via
`/sys/kernel/debug/thunderbolt/<router>/port<n>/regs`:

```
dock 0-1 port13  ADP_DP_CS_2 = 0x000fff00   HPD = 0   <- empty socket
dock 0-1 port14  ADP_DP_CS_2 = 0x000a0040   HPD = 1   <- the monitor
```

Exactly one dock DP OUT adapter reports hot-plug, and the monitor is the only
display on the dock. So **`1:14` is the monitor** (the HDMI socket) and `1:13`
is a socket with nothing plugged in.

## The bug

`tb_find_dp_out()` (`drivers/thunderbolt/tb.c:1864`) walks `tcm->dp_resources`
and returns the **first** DP OUT that is not in use and is on a different
router:

```c
list_for_each_entry(port, &tcm->dp_resources, list) {
        if (!tb_port_is_dpout(port))
                continue;
        if (tb_port_is_enabled(port)) { ... continue; }
        if (in->sw == port->sw) { ... continue; }
        tb_port_dbg(port, "DP OUT available\n");
        ...
}
```

**It never consults HPD.** With two candidate adapters on the dock, the pairing
is arbitrary list order. Every DP tunnel we have ever observed on this machine
was:

```
0:5 <-> 1:13      host dpin0 -> dock's EMPTY socket
```

So the DPRX/AUX read is issued through an adapter with nothing behind it, and
of course it returns nothing: `DPRX read timeout` x N -> `RESULT=SILENT`. That
is our exact symptom, and it needs no Apple-specific explanation.

Note the contrast: `tb_scan_port()` (`tb.c:1300`) **does** check HPD
(`tb_port_is_dpout(port) && tb_dp_port_hpd_is_active(port) == 1`) to queue a
hotplug — so the hotplug is raised for `1:14`, but the subsequent allocation
still picks `1:13`. The information is available and then discarded.

## Why upstream never noticed

Upstream's `quirk_no_dp_tunnel` comment says every Apple DP tunnel attempt dies
after ~300 DPRX timeouts. That is consistent with this: on a dock with a single
DP OUT adapter, or with the monitor on the adapter that happens to be picked,
it would work; on a dock that exposes two, the arbitrary pick fails. Upstream
disabled the whole path on Apple routers rather than diagnosing it.

## Proposed fix (small, testable)

Prefer a DP OUT adapter with HPD asserted in `tb_find_dp_out()`; fall back to
the existing behaviour if none has HPD. Sketch:

```c
static struct tb_port *tb_find_dp_out(struct tb *tb, struct tb_port *in)
{
        struct tb_port *port, *fallback = NULL;

        list_for_each_entry(port, &tcm->dp_resources, list) {
                ...existing filters...
                if (tb_dp_port_hpd_is_active(port) == 1)
                        return port;          /* the monitor is here */
                if (!fallback)
                        fallback = port;
        }
        return fallback;
}
```

Rebuild -> one-shot boot -> dock attached, monitor on HDMI -> expect a tunnel
`0:x <-> 1:14` and, at minimum, a real DPRX completion instead of a timeout.

## What this does and does not prove

* If DPRX completes: **M1 is met** — the host provably feeds the tunnel. That is
  a first, and it is independent of all the DP-IN/ACIO work.
* It does **not** by itself produce a picture. The DCP still has to be routed
  into the tunnel via the DP-IN path (`evidence/2026-10-16-dpin-adapter-enable-protocol-recovered.md`).
  But it removes a confound from every future measurement.

## Do not re-derive

* The dock's DP adapters are **always** present — read them in debugfs, never in
  `/sys/bus/thunderbolt/devices` (there are no sysfs devices for unallocated
  adapters; day 9's "zero DP adapters" was that mistake).
* `ADP_DP_CS_2` bit 6 = HPD, `cap_adap + 0x02`. `cap_adap` is the capability
  with id `0x04` in the port config space (dock adapters: `0x0039`; host
  adapters: `0x0009`).
