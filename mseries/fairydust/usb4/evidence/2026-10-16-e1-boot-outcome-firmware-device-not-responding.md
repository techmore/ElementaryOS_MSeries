# E1 boot result — `set_hpd` is cleared as the wall; the firmware reports the tunnelled sink "device not responding" (2026-10-16)

Author: OpenCode. This is the *result* of the E1 boot that
[`2026-10-16-e1-nonfatal-tunnel-hpd-boot.md`](2026-10-16-e1-nonfatal-tunnel-hpd-boot.md)
prepared and armed. Read [STATE-OF-PLAY](../STATE-OF-PLAY.md) first.

**Status: measured, live, one controlled one-shot boot.** Only `appledrm.ko`
changed (patch `0013`). The owner performed the reboot; the dock and cables were
not moved.

## Verification that the E1 build actually ran

- Kernel `7.1.13-elementary-fairydust-usb4-dptunnel`; cmdline exactly
  `thunderbolt.allow_dp_tunnel=1 thunderbolt.dprx_bypass=1 thunderbolt.dprx_timeout=15000`
  (`dprx_bypass` → `Y`, `dprx_timeout` → `15000` at runtime).
- Live `appledrm` build-id `90eec845166a52f688cbd1675187d73fcf8bbb1b` **equals**
  the E1 ko's build-id
  (`/home/sdolbec/dptunnel-logs/dpin-e1boot-20261016-214205/appledrm-e1.ko`,
  sha256 `882c44457e853d543df50c635cdfbb37fe8cb6d145236ab10f612d9c4bdac67c`).
  The `DPINDBG` and `E1 … ignored (tunnel)` lines below therefore come from the
  intended module, not the previous diagnostic build.
- Installed controlled initramfs sha256
  `46116374311cd18cb265c751f436dc751297c0203d7bb605b685cb5527778cb2` = the
  documented E1 image. `grub-editenv list` → `next_entry=` (one-shot consumed);
  the default entry is untouched.

## The tunnel-path trace, decoded

All lines are `apple-dcp 28cc00000.dcp` (index 2, `dptx target phy: 1`,
`tunnel: 1`); boot clock in seconds:

```
 0.074034  platform 28cc00000.dcp: Adding to iommu group 7
 9.277695  RTKit: Initializing (protocol version 12)
11.436884  AFK[ep:2a]: new service AppleDCPDPTXRemotePort on channel 1
12.880559  DPINDBG connect_source phy ret=-67 initialized=1 powered=0   # 1st phy_power_on: -ENOLINK
12.933316  DPINDBG connect_source phy ret=0  initialized=1 powered=1    # retry 53 ms later: powered
12.934293  DPINDBG apcall idx=18   GET_SUPPORTS_HPD
12.934513  DPINDBG apcall idx=10   GET_MAX_LANE_COUNT
12.934744  DPINDBG apcall idx=0    ACTIVATE
12.934746  DPINDBG tunnel_reply ret=0 powered=1 rate=0 lanes=4 link_error=0
12.934933  DPINDBG request_display ret=0
12.934941  DPINDBG hpd_work: hpd=1
13.983787  DPINDBG set_hpd hpd=1 afk_ret=-110                          # firmware still does not answer
13.983792  DPINDBG hpd_work: E1 set_hpd(1) ret=-110 ignored (tunnel)   # E1 engaged: non-fatal
17.948828  DPINDBG apcall idx=22   DEVICE_NOT_RESPONDING               # <- firmware's own verdict
17.948868  DPINDBG connect_source: waited=2986 ret=-67 powered=1 rate=0 lanes=4 link_error=-67
17.948959  DPINDBG tunnel_reply ret=-67 powered=1 rate=0 lanes=4 link_error=-67
17.949374  DPINDBG apcall idx=24   DEVICE_NOT_STARTED                  # teardown
17.949381  DPINDBG tunnel_reply ret=-67 powered=1 rate=0 lanes=4 link_error=-67
17.949938  DPINDBG apcall idx=1    DEACTIVATE                          # teardown
17.951479  DPINDBG tunnel_reply ret=0 powered=0 rate=0 lanes=0 link_error=-67
17.951985  thunderbolt-apple-nhi b01f00000.nhi: DP source preparation failed: -67
17.952539  DPINDBG apcall idx=20   INACTIVE_SINK_DETECTED              # teardown
17.952547  DPINDBG tunnel_reply ret=-67 powered=0 rate=0 lanes=0 link_error=-67
17.952859  DPINDBG set_hpd hpd=0 resp=0
```

## What E1 changed, and what the `-67` actually is

E1's two edits did exactly what they promised:

1. `hpd_work` no longer writes `link_error`/completes `linkcfg_completion` in
   tunnel mode, so the `13.98 s` `set_hpd(1)` `-110` no longer ends the link.
2. the tunnel path waits `msecs_to_jiffies(8000)` on `linkcfg_completion`
   instead of the 2 s `DPTX_CONNECT_TIMEOUT`.

The `ret=-67` is therefore **not** the firmware returning an error and **not** a
timeout. It is *our* reply to the firmware's call 22. In `dptxport_call()`
(`dptxep.c`):

```c
if (service->ep->dcp->dp_tunnel &&
    (idx == DPTX_APCALL_DEVICE_NOT_RESPONDING ||
     idx == DPTX_APCALL_DEVICE_NOT_STARTED ||
     idx == DPTX_APCALL_INACTIVE_SINK_DETECTED))
        return dptxport_tunnel_reply(dptx, reply, reply_size, -ENOLINK);
```

`dptxport_tunnel_reply(..., -ENOLINK)` writes `link_error = -67` and completes
`linkcfg_completion`. So the firmware told us `DEVICE_NOT_RESPONDING`, our
handler mapped it to `-ENOLINK`, and that woke `connect_source` with `-67`.

The wait arithmetic confirms the timing. `wait_for_completion_timeout()` returns
**remaining** jiffies, and `CONFIG_HZ=1000`:

```
8000 jiffies (8 s window) - 2986 returned = 5014 jiffies = 5.014 s elapsed
12.934941 (request_display) + 5.014 s = 17.949 s  == the apcall idx=22 line
```

So the completion was signalled by the firmware's call 22 ~5 s after
`request_display` — several seconds past the old 1 s `set_hpd` failure and short
of the 8 s window. E1 removed the HPD explanation; the firmware then, on its own,
reported the sink.

## The measured outcome

- **The DP-IN activation gate cleared again**: `phy ret=-67` then `ret=0
  powered=1`, no change from the second controlled boot.
- **`set_hpd` is not the wall**: the tunnel survived the `-110` for a full 5 s
  and was ended by the firmware's own call, not by that failure.
- **The firmware still never configured the link**: no
  `idx=7,13,15,5,12,9,6`, `rate` stays `0`, and the tunnel DCP's RTKit syslog
  count is **13** for the whole boot — identical to the debug boot, and still
  only boot-up lines plus one `AppleDCPDPTX.cpp:355: [AFK]powering nub`. It never
  emitted AUX/EDID/link-training/clock lines (vs 360 on the working built-in HDMI
  path).
- **The firmware's last substantive word was `DEVICE_NOT_RESPONDING` (22)**,
  followed by the teardown calls 24/1/20.

## Interpretation (ranked, still hypotheses)

- **H1 — the firmware is blocked before its DP TX state machine, on the
  sink-facing path. Strongly supported now.** This is H1 minus the HPD-delivery
  explanation that E1 was built to remove: the firmware had a real 8 s window,
  our HPD failure was made harmless, and it still produced no link-config
  sequence. Caveat kept from the debug boot: calls 22/24/20 also occur on the
  working path's *teardown*, so their presence is not by itself the diagnosis —
  the diagnosis is the sustained firmware silence and the missing link-config
  sequence.
- **H2 — `set_hpd` (group 8 / command 8) is the wrong or unsupported command for
  the tunnelled endpoint. Not excluded.** The firmware still never answered
  `set_hpd(1)` this boot, while it answered `set_hpd(0)` at teardown (`resp=0`).
  E1 deliberately kept sending it; do not invent a replacement without evidence.
- Net: the frontier has moved off HPD delivery. The open question is the **sink /
  AUX path** — whether the monitor behind the dock's HDMI answers DPCD/AUX at all
  through the tunnel (which `dprx_bypass=1` hides from the host side).

## Milestones

| Gate | Result |
| --- | --- |
| M0 sink presence | **MET** (unchanged) |
| Correct tunnel target `0:5 <-> 1:14` | **MET** |
| Host DP-IN activation | **MET** (gate clears, `ACTIVATE` `ret=0`) |
| DCP DP link configured | **NOT MET** — now attributed to the sink-facing path, not HPD |
| Visible monitor wake | **NOT DEMONSTRATED** |

The owner confirms the monitor was on the dock's HDMI throughout this boot and
showed **no reaction** (no wake / no source search).

## External-connector evidence

`card2-DP-1 disconnected`, `card2-HDMI-A-1 disconnected`, `card2-eDP-1 connected`.
No EDID, no modes on either external connector. **No picture.**

## Deployment state after this boot

- The one-shot entry `elementary-usb4-dpin-controlled` was consumed;
  `next_entry` is empty and the default entry is unchanged.
- The **E1** initramfs is still installed on that entry (`46116374…`). Rollback
  to the pristine controlled image:
  `sudo install -m0644 /home/sdolbec/dptunnel-logs/dpin-dbgboot-20261016-210203/initramfs-controlled-original.img /boot/initramfs-linux-asahi-fairydust-usb4-dpin-controlled.img`
  then `sudo grub-editenv /boot/grub/grubenv unset next_entry`.

## Next experiments (owner-gated; each needs one reboot)

- **E3 — instrumentation before another functional change (cheapest).** Log the
  DP-IN HPD notifier separately (it never fired this boot) and the host DP-IN
  adapter's DPCD/AUX status at the moment of failure, to distinguish "no sink"
  from "no AUX". Also worth logging the `set_hpd` reply path.
- **E2 — unbypassed DPRX qualification (`dprx_bypass=0`).** Decisive on whether
  the firmware can reach the sink when the host performs the real DPRX read. This
  is the documented hazard (`DP-TUNNEL-RE.md` §9); arm the bypass before touching
  any cable.
- **macOS m1n1-hypervisor MMIO trace** of the tunnelled-DPTX protocol
  (`MACOS-TRACE-RUNBOOK.md`) — the genuine last-step blocker if E2/E3 do not
  resolve the sink question.

## Constraints respected

This record is read-only inspection of the boot the owner performed. No module or
boot payload was installed, no reboot was triggered by this session, and there
was no cable/dock move, bypass change, or driver unbind.
