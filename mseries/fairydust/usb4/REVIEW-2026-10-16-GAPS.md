# Offline review of the DP-IN / DPRX analysis — gap ledger

2026-10-16, Claude. Read-only review of `DP-TUNNEL-RE.md` §4-7 against the
pinned tree (fairydust `ce9f2eba` + `0002`) and the newer audit/REA/ordering
notes. No hardware, kernel, boot image or cable was touched. This file is a
ledger: **each gap has one owner and one status, so nobody re-derives it.**
Hardware truth lives in [STATE-OF-PLAY](STATE-OF-PLAY.md); do not duplicate it here.

## Corrections to existing text (docs only)

| # | Where | Issue | Status |
|---|---|---|---|
| C1 | `DP-TUNNEL-RE.md` §6.1 | Says bypass takes the BW-allocation branch and reads `DP_LOCAL_CAP`. In the tree `tb_dp_bandwidth_mode_consumed_bandwidth()` returns `-EOPNOTSUPP` unless BW mode is enabled and `tunnel->bw_mode` is set, so the likelier path is the fall-through `tb_dp_read_cap(DP_COMMON_CAP)`. Conclusion unchanged (stale caps, no video); mechanism needs a hardware-free confirm. | open |
| C2 | `DP-TUNNEL-RE.md` §6.4 | "Crossbar is not the missing piece" leans on experiment 1 reaching path activation. `tb_path_activate()` only writes config space (see `DPIN-AUX-AUDIT.md` §2), so that evidence is weak; the macOS crossbar trace match is the real support. | open |
| C3 | `DP-TUNNEL-RE.md` §6-7 | `tunnel.c` line numbers refer to the unpatched pin; the patched tree is ~11 lines later (`tb_dp_wait_dprx` 1063 -> 1074). Cite function names. | open |
| C4 | `DP-TUNNEL-RE.md` §7 | Items 1, 3, 4 (crossbar A/B, `dpin1`, ACIO DP-IN DT wiring) are superseded by the DP-IN ADT/REA findings (`0xb01e50000`/`0xb01e58000`, patches 0004-0006). Priority note already added on the branch. | covered by branch |
| C5 | local `~/ElementaryOS_MSeries` | Untracked copy of `DP-TUNNEL-RE.md` is the pre-audit version. Use the `docs/dock-video-decision` copy. | note |

## Open engineering gaps (all offline-addressable unless noted)

| # | Gap | Next step | Owner |
|---|---|---|---|
| G1 | **bridge implemented, reviewed (B1-B8)**; (design sketch: [DPIN-ROUTER-HOOK-DESIGN.md](DPIN-ROUTER-HOOK-DESIGN.md)) No router-side DP-IN hook: 0004-0006 touch nothing under `drivers/thunderbolt/`. Placement is settled by `evidence/2026-10-16-router-vs-dcp-activation-ordering.md` (`tb_dp_activate()`, after `tb_dp_port_enable(src)`, before `tb_dp_dprx_start()`, mirrored in the inactive branch). | Reference design incl. provider lookup (a/b/c in that note). Kernel feature set is DeepSeek's: post as a comment, no tree change. | DeepSeek |
| G2 | Host DP-IN adapter is refcounted by Apple (`incrementTunnelUse`/`decrementTunnelUse`); Linux has no equivalent, so activate-per-tunnel could double-activate when two tunnels share an adapter. | Decide refcount shape before wiring G1. | DeepSeek |
| G3 | (plan: [DPRX-TEARDOWN-BACKPORT-PLAN.md](DPRX-TEARDOWN-BACKPORT-PLAN.md)) Sven Peter's DP-teardown series (6 patches applied to `thunderbolt.git/fixes`) is not in our tree and must be rebased on top of `0002` (same functions as `dprx_bypass`). Not needed for the next experiment; needed before leaving bypass-based testing. | Backport plan only. | DeepSeek |
| G4 | The register *sequence* around DP-IN (power/clock/reset ordering, ACIO `startUsingTunnel()`) is unmeasured; static REA gives offsets, not order. | Live hypervisor trace needs a second Mac plus a reboot (owner-gated). Neo link exists; follow `MACOS-CUTOVER-CHECKLIST.md`. | owner + Codex |
| G5 | Real-sink question: bypass-off DPRX/DPCD answer from the dock HDMI sink. Watchdog data cannot qualify it (bypass epoch/adapter not correlated). | Needs bypass-off run; hazard in `DP-TUNNEL-RE.md` §9. Owner-gated. | owner |

## Bridge implementation review (DeepSeek, read-only) — recorded 2026-10-16

An uncommitted ~606-line Thunderbolt-to-DCP "DP source" bridge exists in the
isolated tree `~/Documents/Codex/2026-10-16/hey-x20/work/dpin-implementation/source`
(HEAD `aa02910`; the review cites baseline `af5c00e`, so re-check line anchors).
It implements the hook shape from [DPIN-ROUTER-HOOK-DESIGN.md](DPIN-ROUTER-HOOK-DESIGN.md)
(G1/G2): source request after both adapters are enabled, DPRX gated on source
status, blocking DCP work on an ordered workqueue outside `tb->lock`. The reviewer
judged the five ordering claims to hold. Hardware untested, not in CI, not committed.

Concerns, in the reviewer's order. "Spot-checked" means I confirmed the cited code
exists; I did not re-derive the rest.

| # | Sev | Concern | Status |
|---|---|---|---|
| B1 | high | `apple_dp_source_init()` deep-validation failure returns `-EINVAL` and fails the whole NHI probe (`apple.c:763-765`): a half-consistent repacked DT would drop all USB4 (dock Ethernet, mouse). Degrade deep failures to warn + disabled; keep `-EINVAL` only for the NHI property-pair violation. Offline FDT diff before any reboot. | spot-checked, open |
| B2 | high | `devm_phy_optional_get(dev, "dp-phy")` (`dcp.c:1356`) with no deferral: if `appledrm` probes before the DP-IN PHY provider, `dcp->phy` stays NULL and every start is `-EINVAL`. Use non-optional get when `apple,dp-tunnel` is set, or add a softdep. `CONFIG_PHY_APPLE_DPIN` is only in `dpin-offline.config`, not production config. | spot-checked, open |
| B3 | med | `-EOPNOTSUPP` now fails activation for the unmapped host DP-IN port (6); previously it established then timed out/bypassed. Decide intent; likely return 0 for unmapped ports. | open |
| B4 | med | Worker reads source status twice per 50 ms iteration (pre-read, then inside `tb_dp_wait_dprx`). Read once. `test-bridge.py` does not extract `tb_dp_dprx_work`, so the fail-fast retry classification has no offline coverage. | open |
| B5 | low | `-EBUSY` from source stop on DCP unbind logs `dev_err` during normal unload; downgrade. | open |
| B6 | low | `comp_unbind` holds `dp_source_lock` across full teardown; no deadlock found, NHI stop may block for the DCP unbind duration. | accepted |
| B7 | low | Port<->transport-index relation not validated (port 5 + index 1 passes). Add or document. | open |
| B8 | info | Pre-existing: an executing DPRX worker cannot be cancelled and may log "not active, tearing down"; not a bridge failure. | note |

Batch-run conditions from the review (all owner-gated): kernel/modules and the
repacked `boot.bin` DT must go together (a mismatched pair is B1); first run
with bypass armed and a short `dprx_timeout` (not 3600000); then bypass off ->
DPRX -> EDID -> pixels. Errno hints: `-EAGAIN/-EPROBE_DEFER/-ETIMEDOUT` DCP not
ready, `-EINVAL/-ENODEV` phy NULL (B2), `-EBUSY` provider owned (B5).
Build wiring: production `build.sh` applies a fixed hash-pinned list (0001; 0002
only with `FAIRYDUST_DP_TUNNEL=1`), so 0004-0006 plus the bridge and DP-IN config
are not in CI yet.
Provenance notes: the 09:00 reboot was the missing session's, not the reviewer's;
the 24x AT-register timeouts are benign per-lane-init retries.

## Codex (ChatGPT) status report — recorded 2026-10-16

Reported by the owner as pasted Codex output; I did not inspect the bundle.
Treat as claims until the artifacts are checked.

- **Constraint change (as reported):** owner now allows a reboot or cable change
  when needed, batched to avoid repeated switching. `STATE-OF-PLAY.md` still says
  "no kernel installation, no M1 reboot, no cable moves"; it needs the owner's
  confirmation and an edit by whoever holds the Git write on that file.
- **Done (reported):** bridge implemented and offline-tested (14 new test groups,
  earlier 29 + 2 still pass); Thunderbolt/Apple DRM objects compile; DT validates
  after a quoting fix; HDMI-adapter fix (0003) added to the build tree; a
  domain-reference leak on cancelled DPRX work fixed; a boot-time-discovered
  tunnel now also starts DCP (my design point 3, hook must cover discovery).
- **Prepared (reported):** module-only build against the running kernel with the
  exact version string and the running kernel's BTF module layout (a mismatch the
  version string alone did not catch), plus a `boot.bin` whose DT differs only by
  two DP-IN nodes, the DCP PHY reference and the NHI-to-DCP mapping. Nothing
  installed or loaded yet. First boot keeps `dprx_bypass`; only real driver
  responses and display evidence count as progress.
- **DeepSeek's review of this bundle failed with a transport error in Codex's
  session**; the separate read-only DeepSeek review above (B1-B8) is the one on record.

### Gate before the batched reboot (cross-reference, not new analysis)

The pasted report does not say whether these were addressed; verify each is closed
or consciously accepted before the owner reboots:

1. **B1** (brick-USB4 on inconsistent DT): the DT and modules ship as a pair, which
   is right; confirm deep-validation failure degrades to a warning, or accept the
   risk with `/boot/m1n1/boot.bin.KNOWN-GOOD-*` and `RECOVERY.md` ready.
2. **B2** (PHY provider load order / `CONFIG_PHY_APPLE_DPIN` in the module set):
   a module-only bundle must actually contain `phy-apple-dpin` and load it before
   `appledrm`; otherwise every source start is `-EINVAL` and the run is wasted.
3. **B3/B4**: unmapped-port behaviour and double status read; B4's missing
   `tb_dp_dprx_work` coverage matters because bypass stays armed on the first run.
4. Short `dprx_timeout` (not 3600000) and bypass armed before any cable move
   (`DP-TUNNEL-RE.md` §9).
5. Confirm the initramfs contains the new modules (the stash notes say the old
   initramfs once carried stale `appledrm.ko`).

## Tooling

| # | Defect | Status |
|---|---|---|
| T1 | `test-dp-tunnel.sh` counted every `connected` DRM connector, including eDP, so "paths activated" could print display success. | **fixed** in this batch: counts only `card*-DP-*` / `card*-HDMI-*`. On the live machine the old count included eDP (1), the new count is 0 (both external connectors disconnected). |
| T2 | Stock `trace_dptx.py` omits `atcN-dpin*`/`atcN-dpxbar`. | `trace-dpin.py` covers it; synthetic tests only. |

## Do not repeat

Already closed elsewhere (see STATE-OF-PLAY "Do not repeat"): port guessing,
`/dev/mem` ADT reads, ACIO unbind/bind recovery, crossbar-only writes, further
`force_link` probes to manufacture evidence.
