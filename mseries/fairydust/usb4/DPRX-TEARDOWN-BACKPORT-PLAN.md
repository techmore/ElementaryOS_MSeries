# Plan: backport Sven Peter's DP-teardown series (ledger G3)

2026-10-16, Claude. **Plan only.** Built from patch *titles* in
`DP-TUNNEL-RE.md` §6.3 and the pinned tree (`ce9f2eba` + `0002`). The upstream
diffs were not re-read here; step 0 is to fetch them. Kernel work is DeepSeek's.

Series: "thunderbolt: Fix DP tunnel teardown while an async DPRX read is
running" (v3, six patches in `thunderbolt.git/fixes`, one deferred).

## Why it matters here

`DP-TUNNEL-RE.md` §9: unplugging with a DPRX read in flight wedges the Type-C
port, and the read can never finish on this hardware yet. Every unbypassed
sink test (ledger G5) runs into this. `dprx_bypass` is a workaround that only
helps if it is armed before the unplug.

## What the pinned tree still has (verified by reading it)

| Upstream patch (title) | State in our tree |
|---|---|
| 1 Hold a router reference per allocated HopID | `tb_port_alloc_in_hopid()`/`release` (`switch.c:808/832`) take no switch reference. |
| 2 Make the DP tunnel activation callback mandatory | `tb_dp_dprx_start()` branches on `tunnel->callback` (`tunnel.c:1143`); `tb_dp_dprx_work()` null-checks it (`:1128`). |
| 3 Fix domain reference leak when DPRX read is canceled | `tb_dp_dprx_stop()` does `cancel_delayed_work()` and drops the tunnel ref only if it was pending (`:1155-1161`). |
| 4 Don't access a tunnel after its DPRX read was canceled | `tb_dp_dprx_work()` reads `dprx_canceled` without the lock held at the check (`:1112`), then touches the tunnel. |
| 5 Mark discovered tunnels as active | Discovery path `tb_tunnel_discover_dp()` (`tb.c:389`) separate from `tb_dp_activate()`. |
| 6 Tear down inactive DP tunnels when the domain is stopped | `tb_stop()` (`tb.c:2966`) deactivates DMA tunnels only; others are just `tb_tunnel_put()` (`:2982-2984`). |
| 7 (deferred) Drop the callback data | optional. |

## Interaction with our patches (the reason to do this deliberately)

- **`0002` inserts `dprx_bypass` into `tb_dp_wait_dprx`**, which upstream patches
  3-4 rewrite. Rebase the series on top of `0002`, keep the bypass early-return as
  the first statement, and re-run the check that bypass still marks the tunnel
  active (`tb_dp_dprx_work` else-branch).
- **The DP-IN hook (`DPIN-ROUTER-HOOK-DESIGN.md`) needs patch 6.** Today
  `tb_stop()` never deactivates a DP tunnel, so a `tunnel_stop()` placed next to
  `tb_dp_dprx_stop()` would not run on shutdown and DP-IN would stay active.
  Land patch 6 first, then the hook.
- Patch 5 (discovered tunnels active) overlaps the hook's discovery call; do them
  as one coherent change, not two.

## Steps

0. Fetch the exact patches from `thunderbolt.git/fixes` (v3 message ids) and
   record their SHA-1s here. Do not rely on this table's paraphrase.
1. In a scratch copy of the pinned tree: apply 0001, 0002, 0003, then try the
   series; list rejects per file (`switch.c`, `tb.c`, `test.c`, `tunnel.c`, `tunnel.h`).
2. Resolve `tunnel.c` rejects around `tb_dp_wait_dprx`/`tb_dp_dprx_work`/`tb_stop`
   keeping the bypass and the bounded-timeout behaviour from `0002`.
3. Build `drivers/thunderbolt` module-only (no install) and run the in-tree
   KUnit `test.c` for thunderbolt if the config enables it.
4. Compare `dprx_bypass=1` behaviour before/after on paper: no retry storm,
   tunnel marked active at once, deactivation cancels work and drops exactly one ref.
5. Only then offer it to the owner as a candidate for a bounded bypass-off run.

## Out of scope / not claimed

Nothing here is applied, built or booted. No claim that the series fixes the
wedged-port hazard on Apple hardware; it addresses the upstream-described race.
