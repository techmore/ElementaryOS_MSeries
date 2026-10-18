# Debug boot result: the DCP firmware goes silent after ACTIVATE and never answers `set_hpd` (2026-10-16)

Author: OpenCode. This is the *result* of the instrumented boot that
[`2026-10-16-dpin-dbgboot-instrumentation.md`](2026-10-16-dpin-dbgboot-instrumentation.md)
prepared and armed. Read [STATE-OF-PLAY](../STATE-OF-PLAY.md) first.

**Status: measured, live, reproduced.** One controlled one-shot boot ran the
`DPINDBG`-instrumented `appledrm.ko`. No new functional change was made; the
instrumentation is `dev_info` only. The dock and cables were not moved.

## Verification that the instrumented boot actually ran

- Kernel `7.1.13-elementary-fairydust-usb4-dptunnel`; cmdline exactly
  `thunderbolt.allow_dp_tunnel=1 thunderbolt.dprx_bypass=1 thunderbolt.dprx_timeout=15000`.
- Live `appledrm` build-id `cdca5ea2cc7a5939df332619daa389e915260a5c` **equals**
  the instrumented ko's build-id
  (`/home/sdolbec/dptunnel-logs/dpin-dbgboot-20261016-210203/appledrm-diag.ko`).
  So the `DPINDBG` lines below come from the intended module.

## The tunnel-path trace, decoded

`apcall idx` names are from `dptxep.h:enum dptx_apcall`. All lines are
`apple-dcp 28cc00000.dcp` (the tunnel connector, `dp_tunnel=1`), boot clock:

```
61.923979  connect_source phy ret=-67 initialized=1 powered=0   # 1st phy_power_on: -ENOLINK, DP-IN HPD low
61.975445  connect_source phy ret=0  initialized=1 powered=1    # retry ~52 ms later: DP-IN HPD high -> powered
61.976169  AppleDCPDPTX.cpp:355: [AFK]powering nub 0x864bc8     # firmware powers its DPTX endpoint
61.976420  apcall idx=18   GET_SUPPORTS_HPD
61.976601  apcall idx=10   GET_MAX_LANE_COUNT
61.976831  apcall idx=0    ACTIVATE
61.976836  tunnel_reply ret=0 powered=1 rate=0 lanes=4 link_error=0
61.977061  request_display ret=0
61.977079  hpd_work: hpd=1                                      # connect_source scheduled it; DP-IN HPD is high
63.027307  set_hpd hpd=1 afk_ret=-110                           # <-- firmware never answered (1 s AFK timeout)
63.027329  connect_source: waited=949 ret=-110 powered=1 rate=0 lanes=4 link_error=-110
65.076283  set_hpd hpd=0 afk_ret=-110                           # teardown
66.982873  apcall idx=22   DEVICE_NOT_RESPONDING      -> reply -67
66.983190  apcall idx=24   DEVICE_NOT_STARTED         -> reply -67
66.983656  apcall idx=1    DEACTIVATE                -> reply -108
66.984087  apcall idx=20   INACTIVE_SINK_DETECTED    -> reply -67
66.984431  apcall idx=20   INACTIVE_SINK_DETECTED    -> reply -67
66.984654  set_hpd hpd=0 resp=0
```

### What this corrects

The earlier second-boot record attributed `DP source preparation failed: -110`
to the **2 s `DPTX_CONNECT_TIMEOUT`** (`dcp.c:436`, `waited=0`). That was wrong.
The trace shows `waited=949` — a **non-zero** return, i.e. `linkcfg_completion`
*was* signalled — and `link_error=-110`, which is written **only** by
`dptxport_hpd_work()` when our outgoing `dptxport_set_hpd()` returns an error
(`dptxep.c`, `hpd_work`). So the fatal `-110` is:

> our `set_hpd(hpd=1)` AFK service call (group 8 / command 8) to the DCP
> firmware timed out after 1 s (`afk.c` waits `MSEC_PER_SEC`), and
> `hpd_work` promoted that into `link_error`, which woke `connect_source` and
> tore the tunnel down.

The first boot's `-67` gate did **not** recur: the `-ENOLINK` retry (patch 0011)
now powers the DP-IN PHY on the second attempt. `phy poweron failed` = 0.

### The firmware answered `set_hpd(0)` but not `set_hpd(1)`

One asymmetry worth keeping: at teardown the firmware **did** reply to
`set_hpd(hpd=0)` — `[66.984654] … DPINDBG set_hpd hpd=0 resp=0` — within the AFK
window, whereas it never replied to `set_hpd(hpd=1)` during the connect. So the
firmware implements group 8 / command 8; it just did not service the *assert*
within 1 s. That is consistent with it blocking while it tries to bring the sink
up. Note also that our reply check (`resp.unk != 1` → `-EINVAL`) rejects
`resp=0`, which may be the correct answer for a *deassert*; that check is not
changed here, only recorded.

### The firmware's own voice is silent

RTKit syslog lines emitted this boot:

| DCP | role | syslog lines |
|---|---|---|
| `28cc00000` | tunnel connector (`dcpext1`, `dp_tunnel=1`) | **13** (all at 10.35 s boot-up, plus **one** at 61.976 s) |
| `289c00000` | built-in HDMI (`dcpext0`, `dp_tunnel=0`) | **360** |
| `38bc00000` | internal eDP | 31 |

The single tunnel-path line is `AppleDCPDPTX.cpp:355: [AFK]powering nub`.
After ACTIVATE the firmware logs **nothing** — no AUX, no EDID, no
"Beginning %s phase of link training", no clock/mode-set messages. It stopped
before its DP TX state machine began.

## New asset: the working-path reference trace

While this session was open, a monitor was connected to the **built-in HDMI**
(`289c00000`, `dp_tunnel=0`) at 246 s. That path is fully working and gave us,
for the first time, the firmware's complete link-config sequence on this
machine. This is the exact success template the tunnel path is missing:

```
246.715595  apcall idx=18   GET_SUPPORTS_HPD
246.715842  apcall idx=10   GET_MAX_LANE_COUNT
246.716150  apcall idx=0    ACTIVATE
246.716403  request_display ret=0
            ... ~0.7 s firmware-side gap ...
247.421407  apcall idx=21   SET_TILED_DISPLAY_HINTS (acked unhandled on non-tunnel)
247.422965  apcall idx=7    GET_MAX_LINK_RATE
247.423151  apcall idx=13   GET_SUPPORTS_DOWN_SPREAD
247.423331  apcall idx=7    GET_MAX_LINK_RATE
247.423903  apcall idx=15   SET_DOWN_SPREAD
247.424422  apcall idx=5    WILL_CHANGE_LINKG_CONFIG
247.424622  apcall idx=12   SET_ACTIVE_LANE_COUNT   lanes=0
247.424863  apcall idx=9    SET_LINK_RATE
247.425886  apcall idx=6    DID_CHANGE_LINK_CONFIG
247.437803  apcall idx=13   GET_SUPPORTS_DOWN_SPREAD
247.438608  apcall idx=12   SET_ACTIVE_LANE_COUNT   lanes=4
247.438666  connect_source: waited=1277 ret=0 powered=0 rate=20 lanes=4 link_error=0
247.969...  mode_set_gated: 3840x2160@30 Hz   (then 1920x1080@60)
```

Three facts from the reference matter for the tunnel work:

> This same working-path reference was also captured independently by Claude in
> [`DCP-REFERENCE-BUILTIN-HDMI-20261016.txt`](../DCP-REFERENCE-BUILTIN-HDMI-20261016.txt)
> (a different boot, plain `dmesg` without `DPINDBG`). The two are consistent.
> This document adds the `apcall idx` decoding and the tunnel-path contrast.

1. **The firmware is the DP master.** It runs AUX/EDID/link training itself and
   then *reports* the trained result back as `SET_LINK_RATE` (9) and
   `SET_ACTIVE_LANE_COUNT` (12). `linkcfg_completion` is completed by those, not
   by anything the host initiates. `rate=20` = `LINK_RATE_HBR2` (5.4 Gbps).
2. **`set_hpd` is not part of this path.** The HDMI connector is
   `connector_type != DisplayPort`, so `connect_source` never calls `set_hpd`
   (`dcp.c`); the firmware used its own DP2HDMI HPD IRQ. In tunnel mode our
   driver schedules `hpd_work` unconditionally (`dcp.c`, `if (dcp->dp_tunnel)
   schedule_work(&dptx->hpd_work)`), and that is exactly what timed out.
3. The `DEVICE_NOT_RESPONDING`/`DEVICE_NOT_STARTED`/`INACTIVE_SINK_DETECTED`
   calls (22/24/20) also appear on the working path's **teardown**, e.g. at
   331–332 s and 382–385 s. So on the tunnel path they are **teardown noise and
   not, by themselves, proof that the firmware found no sink.** Do not read them
   as the diagnosis.

## Interpretation (ranked, all still hypotheses)

Observed failure, stated exactly: *after ACTIVATE + `request_display`, the DCP
firmware neither begins link configuration nor answers our HPD notification, and
Linux turns the `set_hpd` timeout into a fatal link error.*

- **H1 — the firmware is blocked before its DP TX state machine.** Best supported:
  it emits zero link/AUX/mode logs (vs 360 on the identical firmware path that
  works), and it does not answer a command on a service that is otherwise live.
  Candidate blockers: sink/AUX reachability; a prerequisite the host has not
  supplied. `dprx_bypass=1` skips the host DPRX wait but not the hardware AUX
  read, so it can hide a failure without explaining it.
- **H2 — `set_hpd` (group 8 / command 8) is the wrong or unsupported command for
  the tunnelled endpoint.** It is only exercised for a *physical DisplayPort*
  connector and may never have been validated on this machine. If so, the
  firmware may actually be *waiting* for HPD and our delivery is malformed.
- **H3 — our own timeout is too aggressive / fatal.** The firmware took ~0.7 s
  from `request_display` to first link call on the working path, so 1 s is not
  obviously too short, but treating a `set_hpd` failure as a link error is a
  design choice, not a measured requirement.

H1 and H2 are distinguishable by a single experiment (below). H3 is not a wall
by itself.

## Proposed next experiments (owner-gated; each needs one reboot)

- **E1 (cheapest, safe) — make tunnel-mode HPD delivery non-fatal and observe.**
  Keep the `DPINDBG` logs; in the tunnel path, log a `set_hpd` failure and do
  **not** set `link_error`, so `connect_source` uses its full window. If the
  firmware then drives `idx=7,13,15,5,12,9,6`, H3/H2 is the story and the wall
  moves forward. If it stays silent for the whole window, H1 is confirmed.
- **E2 (decisive on H1) — unbypassed DPRX qualification** (`dprx_bypass=0`). This
  is the documented hazard (`DP-TUNNEL-RE.md` §9: never unplug with a DPRX read
  in flight). It directly tests whether the firmware can reach the sink when the
  host does the real DPRX read. Highest information, highest risk.
- **E3 — more instrumentation before another functional change:** log the DP-IN
  HPD notifier separately (it never fired this boot) and the host DP-IN adapter's
  DPCD/AUX status at the moment of failure, to distinguish "no sink" from "no
  AUX".

`set_hpd` should not be "fixed" by inventing a new AFK command without evidence
for H2; the group/command came from upstream Asahi code.

## Deployment state after this boot

- The one-shot GRUB entry `elementary-usb4-dpin-controlled` was consumed; the
  default entry is unchanged. `next_entry` is no longer needed for this test.
- The **instrumented** initramfs is still installed for that entry
  (`a6db46fa…`). Rollback to the un-instrumented controlled image:
  `sudo install -m0644 /home/sdolbec/dptunnel-logs/dpin-dbgboot-20261016-210203/initramfs-controlled-original.img /boot/initramfs-linux-asahi-fairydust-usb4-dpin-controlled.img`
  then `sudo grub-editenv /boot/grub/grubenv unset next_entry`.
- No picture, M1–M4 unmet, external DP/HDMI on `card2` disconnected, eDP only.
- Side observation, not part of the dock test: a monitor was attached to the
  built-in HDMI at 246 s and removed at 382 s during this session. It produced
  the reference trace above. It does not indicate dock progress.
