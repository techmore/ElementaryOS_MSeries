# J314S wip3: first dock plug lands on a silent dcpext1 — 2026-10-22

Diagnosis by Claude Code on the owner's J314S (MacBook Pro 14-inch, M1 Pro), running the trial kernel
`7.2.11-elementary-aurora72-wip3` (up since 2026-10-21 16:42 EDT; `apple_sep.xart_guard=0`), with the Dell WD22TB4.
Owner report: the dock's monitor did not come on. The diagnosis changed nothing on the host. Times are EDT on 2026-10-22.

## Result

The dock's Thunderbolt link, USB hubs, Ethernet and HID all came up. The DisplayPort side did not, and could not be
recovered by replugging into the same port. It worked at once on a different port. The fix drafted for it
(`unified72/patches/0002-...`) is **build-only and unproven**: nothing here was compiled into a kernel or booted.

## Timeline

| Time | Event |
| --- | --- |
| 07:04:23 | `mseries-power` runs (AC arrived); `38bc` (panel) power-cycles; `289c00000` logs `dcp_dptx_disconnect(port=0)` and `connected:0`. |
| 07:04:27.95 | Dock `thunderbolt 0-1` authorised. `28cc00000` (dcpext1): `allocated Type-C DPTX PHY 0`, `display routed to Thunderbolt DP tunnel dpin0`. |
| 07:04:29–07:04:39 | Six attempts (the first plus five retries), two seconds apart (1 s timeout, 1 s delay): `AppleDCPDPTXRemotePort (chan:1) command type 0xc0 ... timed out after 1000 ms`, `service call group 0 cmd 12 failed ... -110`, `dcp_dptx_connect: failed to validate DPTX target 0:0: -110`. Then `Type-C DPTX reconnect failed after 5 retries: -110`. |
| 07:04:40–41 | `dcp_hotplug() connected:0`; teardown: `group 8 cmd 8 failed ... -110`, `dpin0: display teardown failed: -110`. |
| 07:10:40–50 | Owner unplugs and replugs the **same** port. Dock re-enumerates on Thunderbolt. |
| 07:10:51–52 | `28cc00000` again; a `group 8 cmd 8` call times out; `dpin0: DP tunnel setup failed: -110`. 07:11:03 `0:5 <-> 1:14 (DP): not active, tearing down`. |
| 07:12:21–27 | Owner moves the dock to **another** port. `289c00000` (dcpext0): `allocated Type-C DPTX PHY 1`, `DCPDP13Service` appears in 26 ms, `connected:1`, 1920x1080@60, `card2-DP-2 connected`. |

## What the evidence supports

1. **dcpext1's DPTX RemotePort service stopped answering.** `validate` (cmd 12) timed out on all six attempts; the later
   release (cmd 8, group 8) timed out too, in the same state and on the next plug. Nothing on `289c00000` timed out.
2. **The failed port stays pinned.** In `dcp_tb_release_locked()` (drivers/gpu/drm/apple/dcp-fabric.c at the pinned
   source), a failing `dcp_dptx_disconnect_oob()` returns before the route is freed; the comment there says the
   route "stays owned for the next request to release". A timeout is not a refusal, and the next request
   (07:10:51) hit the same timeout in that same release. That matches `DP tunnel setup failed: -110` appearing
   one second after `group 8 cmd 8 failed`. The port that was moved to was a different `apple_dcp_typec_port`, so
   it did not inherit the stuck ownership.
3. **The kernel does not look at the other display controller.** After the failed validates nothing tried
   `289c00000` for that plug.
4. **The same failure is not new in wip3's source.** `dcp.c`, `dptxep.c`, `dcp-fabric.c` and `dcp-fabric-core.c` are
   unchanged between the wip2 pin (`644133b7`) and the wip3 pin (`bd526b3c`) (the first three fetched at both
   refs and compared by size and by the GitHub compare file list; `dcp.c` by the compare list only); only `apple_drv.c`,
   `iomfb_plane.h`, `iomfb_template.c`, `plane.c` and `plane.h` differ in `drivers/gpu/drm/apple/` (GitHub compare).
   So this is not a wip3 regression in the code that decides routing or talks to the DPTX service. (It remains
   possible that something outside those files changed the firmware's behaviour; not shown.)
5. **Earlier boots never hit it.** In boots −4 to −7 (wip2 and `.20-enh1`) every dock plug logged either an answer
   within ~80 ms from `28cc00000` (a cold-boot plug, after which `289c00000` took over the picture) or went straight
   to `289c00000`. No `failed to validate DPTX target` line exists in the kernel journal of boots −1 to −7. This boot
   (wip3) had no earlier dock plug; the three wip3 boots before it ran for under an hour each and none logged a dock.

## Related

`dcpext1` is `28cc00000` (the tunnel connector, no Type-C mux in the device tree); `dcpext0` is `289c00000`
(the built-in HDMI). An earlier, different failure of the same DCP is recorded in
[`fairydust/usb4/evidence/2026-10-16-dbgboot-dcp-silent-never-configures-link.md`](../../fairydust/usb4/evidence/2026-10-16-dbgboot-dcp-silent-never-configures-link.md)
(older kernel: firmware silent after ACTIVATE, never answering `set_hpd`). Not shown to be the same cause.

## What is not shown

- **Why `28cc00000` was chosen at 07:04:27.** The candidate scorer prefers the lowest CRTC index among available
  pipelines (`dcp_fabric_tunnel_candidate()`), which would be `289c00000`. Both `dcp_fabric_available()` (owned,
  fixed output busy, HDMI presence not settled) and the planner (`keep_order`, another port wanting that pipeline) can
  exclude it. `289c00000` logged a disconnect at 07:04:23, four seconds earlier. No verbose logging was on, so the
  reason is not in the journal.
- **Why the service went silent.** Candidates: long idle since boot (14 h) of an external DCP; the 07:04:23 power
  event; a firmware state left by the previous trial boots. None is tested. A reboot is expected to clear it, since
  a fresh `28cc00000` answered on every earlier boot — not verified on this boot.
- **Whether this repeats.** One occurrence.

## Workaround for the running kernel

Move the dock to another USB-C port. If the port stays dark on the same port after replug, that port is pinned until
reboot (finding 2). Reboot also clears it.

## The draft patch

`unified72/patches/0002-drm-apple-free-dp-tunnel-route-from-silent-dcpext.patch`, series revision 5, candidate
`7.2.11-elementary-aurora72-wip4`:

- A DPTX call that times out marks that DCP's pipeline unresponsive for 300 s (cleared on the next connect that
  gets an answer). New `dptx_holdoff` fields on `struct apple_dcp`; `unresponsive` on `struct dcp_fabric_pipeline`.
- `dcp_fabric_available()` is false for an unresponsive pipeline and `dcp_fabric_plan()` does not plan onto one,
  unless a tunnel already holds it. With no other pipeline free the request returns `-EBUSY`; the Thunderbolt side
  already treats that as "no display pipeline free; waiting for one" and retries every 2 s
  (`apple_dpin_m1`, `capacity_retry`), so a retry lands on `289c00000` when it is free.
- `dcp_tb_release_locked()` completes a release whose firmware call timed out: it drops the DCP's connected view
  (`dcp_dptx_abandon()`) and goes on to free the crossbar route, instead of keeping the route owned.

### What it fixes and what it does not

- Fixes: a port pinned to a dead pipeline until reboot (finding 2), and the next plug choosing the dead pipeline
  again while it is held off.
- Does **not** move the dock to `289c00000` within the plug that already attached to the silent pipeline (the
  07:04 case): the tunnel is attached before the validate runs, and the Thunderbolt driver only re-requests
  on a new tunnel event. The expected result there is a dark monitor, then a working one after one replug,
  instead of a port dark until reboot. Closing that gap needs the DCP to ask the Thunderbolt side for a new request
  (not designed here).
- Does not explain or prevent the silence itself.

### Checked here

- The patch applies (`git apply --check`) on the exact pinned files with 0001 applied. The six file blobs were read
  from GitHub at `bd526b3c`; no archive was downloaded and no full tree was built.
- The pure routing change (`dcp_fabric_available()`, `dcp_fabric_tunnel_candidate()`, `dcp_fabric_plan()`) was
  compiled from the real `dcp-fabric-core.c` against stub headers and run in userspace. The scenario passes, and
  four checks fail when the availability change is removed. The same scenario is added as the KUnit case
  `fabric_unresponsive_pipeline_test`; KUnit itself was not run.
- `dcp.c` and `dcp-fabric.c` edits were not compiled. The `aurora-enhancements` workflow builds `unified72` on this PR.

### Acceptance before anyone arms it

Native build and KUnit pass in CI; stage unarmed beside wip3 (owner decision); then on the J314S: dock plug on each port
from a fresh boot, a plug after hours idle, and a deliberate replug on the port that failed. Look for
`DPTX service not answering`, `no display pipeline free; waiting for one` and `a display pipeline came free`. Keep
`.20` as the default and the wip3 rollback in `unified72/BOOT-TRIAL.md`.

## Side observation: audio blips on plug and unplug

Each dock plug or unplug flips AC/battery; `mseries-power` then reapplies the CPU profile (07:12:20–23: power-saver
2208 MHz caps, then balanced 3036 MHz, three runs in 3 s) and the panel DCP power-cycles. The only logged glitch is one
`snd_pcm_avail after recover: Broken pipe` on `hw:AppleJ314,1p` at 07:04:23. The dock exposes no audio device to
PipeWire. Cause not established.
