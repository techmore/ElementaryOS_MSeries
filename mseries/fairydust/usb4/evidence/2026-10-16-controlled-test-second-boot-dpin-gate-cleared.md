# Second controlled-test boot — DP-IN activation gate cleared; new wall is the DCP link-config timeout

Date: 2026-10-16 20:50 (wall clock). Author: OpenCode (log analysis / build
verification lane). This record reviews the *actual* modules, parameters, source
timing and external-connector evidence of the re-staged controlled boot — the
task assigned in `REVIEW-2026-10-16-GAPS.md` ("DeepSeek's next task ... not
rebuild or rediscover the dock").

## What booted (verified, not assumed)

- Kernel `7.1.13-elementary-fairydust-usb4-dptunnel`, booted 20:50:18.
- cmdline offset `thunderbolt.allow_dp_tunnel=1 thunderbolt.dprx_bypass=1
  thunderbolt.dprx_timeout=15000` — matches GRUB id `elementary-usb4-dpin-controlled`
  only. The bypass safeguard was armed on the boot itself.
- The five rebuilt modules loaded in memory are the **staged 0011 build**, checked
  by in-memory `.note.gnu.build-id` (`/sys/module/<m>/notes/...`) against the
  modules inside `initramfs-linux-asahi-fairydust-usb4-dpin-controlled.img`:

  | module | in-memory build-id | staged initramfs build-id | verdict |
  | --- | --- | --- | --- |
  | thunderbolt | `9d2790d698444e92eb5130c4c92d3a54d3815517` | same | MATCH |
  | thunderbolt_apple | `956053beadfe6f23ad00e6a85bdc06d29b426837` | same | MATCH |
  | appledrm | `a7fa19bc18a077a5a3536c8d7338e0ccccb8c631` | same | MATCH |
  | phy_apple_dpin | `f1e65d6c820be2c12b487a5a2accbb918add4626` | same | MATCH |
  | phy_apple_atc | `2e3eed73916dbbff6bedb7b73f6387478f2eb441` | same | MATCH |

  Note: the `/lib/modules/.../kernel/...` copies are **stale and were not loaded**
  — e.g. the root-tree `thunderbolt_apple.ko` (build-id `f0e615ab…`) does not even
  contain the string `DP source preparation failed`. Do not read `/lib/modules`
  copies to reason about a controlled-test run.

## Sequence observed

- 20:50:34 `apple-display-crossbar b0304c000.mux: Switched dpin0 to dispext1,0`.
  The crossbar mux is live on this DTB and routed the DP-IN block to external
  display controller 1 — this did not happen in the earlier (pre-DTB) runs.
- 20:50:36 appledrm initialises (`[drm] Initialized apple 1.0.0 ... minor 2`).
  Desktop came up; gala running (2 logind sessions). The earlier gala/appledrm
  registation race did **not** abort the session this boot.
- 20:50:37 USB4 link up, `thunderbolt 0-1: Dell WD22TB4 Thunderbolt Dock`,
  retimer found.
- 20:50:38 DP tunnel `0:5 <-> 1:14` path programmed (ACIO TX/RX config-space
  messages for ports 13–16); DCP `28cc00000.dcp` (index 2, tunnel 1)
  `[AFK]powering nub`. The automatic bridge ran with no `force_link`.
- 20:50:40 `thunderbolt-apple-nhi b01f00000.nhi: DP source preparation failed: -110`.
- 20:50:40 `0:5 <-> 1:14 (DP): not active, tearing down` (tunnel torn down).
- 20:50:42 `DP source stop failed: -110`.

## The measured advance: the DP-IN activation gate cleared

Compared with the first controlled boot (`-67`/`-ENOLINK` at `phy poweron failed`):

- `phy poweron failed` occurrences this boot: **0**.
- `DP-IN activation failed:` info lines (added by 0011 for the polling handshake):
  **0**.
- `DP source preparation failed`: 1.

`dpin_power_on()` only returns 0 when `apple_dpin_set_inactive(io, 0)` sees the
INACTIVE-ACK bit reach 0, and that poll returns `-ENOLINK` if HPD level (bit 2 of
`0x00`) is low while waiting. No failure log + no `phy power-on` error therefore
means the **DP-IN activation handshake succeeded and DP-IN HPD was high** when it
ran. The previously-single blocker (activation aborted at once because HPD was low
~4 s after bring-up) did not recur: the re-staged modules + later activation time
let HPD propagate first.

## The new wall: DCP firmware link-config completion never fires

> **Correction (2026-10-16, after the `DPINDBG` debug boot).** The attribution
> below is wrong about the *mechanism*. The debug boot measured
> `waited=949 ret=-110 … link_error=-110`: the completion **did** fire, and the
> `-110` was our own `set_hpd(hpd=1)` AFK call timing out after 1 s. The
> conclusion that the DCP never sent `set_active_lane_count`/`SET_LINK_RATE`
> still stands. See
> [2026-10-16-dbgboot-dcp-silent-never-configures-link.md](2026-10-16-dbgboot-dcp-silent-never-configures-link.md).

`-110` is `-ETIMEDOUT`, and the only `-110` a DCP DP-source start can return is
`dcp.c:436`:

```
waited = wait_for_completion_timeout(&dptx->linkcfg_completion, DPTX_CONNECT_TIMEOUT);
ret = waited ? READ_ONCE(dptx->link_error) : -ETIMEDOUT;   /* DPTX_CONNECT_TIMEOUT = 2000 ms */
```

Timing corroborates it: tunnel path programmed 20:50:38 → failure 20:50:40 = ~2 s
= `DPTX_CONNECT_TIMEOUT`, not the worker's 5 s `-ENOLINK` deadline. So the code
path reached this point, which it can only do **after `phy_init` and
`phy_power_on` both succeeded** (`dcp.c:399–410`), i.e. after the DP-IN gate above.
The completion is set only when the DCP firmware sends the `set_active_lane_count`
tunnel request with `lane_count > 0` (`dptxep.c:518`; `dptxport_tunnel_reply`,
`dptxep.c:281`). It never arrived within 2 s → the DCP firmware never started DP
link configuration toward the sink.

Plain-language: the host side is now powering and routing the DP-IN path and is
waiting for the DCP to configure the actual DP link; the DCP does not. That is one
layer up from where the first controlled boot died, and it is the same
sink-facing DP-link/AUX question that DPRX addresses (bypass=1 marks the tunnel
active without a real sink handshake, so the DCP may have no sink to train).

## External-connector evidence

- DRM: `card2-DP-1 disconnected`, `card2-HDMI-A-1 disconnected`,
  `card2-eDP-1 connected`. No EDID, no modes on either external connector.
- Thunderbolt debugfs config space re-read live:
  `0-0 port5/6 = 0x0e0101` (DP_IN), `0-1 port13/14 = 0x0e0102` (DP_OUT); word
  `0x0004` on `1:14` differs from `1:13` by bit 30 — monitor HPD still present on
  the `1:14` adapter. (H1 remains a *presence* result only.)
- **No picture.** M1–M4 remain unmet.

## Next questions (recorded, not yet run)

1. Does `dptxport_hpd_work` actually call `dptxport_set_hpd(dcp service, 1)` this
   boot? HPD was high on the DP-IN side, so the DCP should have been told to
   start. Log the call and the AFK reply.
2. Why does the DCP firmware omit the `set_active_lane_count` request? Prime
   suspect: the DCP needs the sink's DPCD/EDID (real AUX), which `dprx_bypass=1`
   hides. Qualifying this needs a bypass-off run — the hazard path in
   `DP-TUNNEL-RE.md` §9; owner-gated.
3. The 2 s `DPTX_CONNECT_TIMEOUT` vs the 5 s source deadline (`N4`): the source
   worker's deadline cannot help when the inner timeout is the one that fires.

## Constraints respected

No module/boot payload installed, no reboot triggered, no cable or dock move, no
bypass change, no unbind, no `/dev/mem` read. Read-only inspection and the
already-booted controlled entry.
