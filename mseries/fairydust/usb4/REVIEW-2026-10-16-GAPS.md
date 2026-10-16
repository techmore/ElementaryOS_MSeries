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

## Pre-reboot gate: findings from inspecting the prepared bundle (Claude, read-only)

Inspected `~/Documents/Codex/2026-10-16/hey-x20/work/dpin-implementation/`
(`source/`, `deployment/`) and the live `/boot`. Nothing installed, loaded or
edited. Bundle claims about validation were not re-run.

| Item | Result |
|---|---|
| **B2** PHY load order | **Largely refuted, downgrade.** `appledrm.ko` declares `depends: phy-apple-dpin`, which depends on `phy-apple-atc`, and `phy-apple-dpin` has the `of:...apple,t6000-dpin` alias, so loading `appledrm` loads the PHY first. Separately `phy_get()` returns `-EPROBE_DEFER` when a `phys` phandle's provider is not registered (`phy-core.c:641`), and `devm_phy_optional_get` only maps `-ENODEV` to NULL. The review's "NULL forever, no deferral" does not hold when the DT has `phys`. Remaining check: all five `.ko` (including `phy-apple-dpin`) must be installed under `/usr/lib/modules/<kv>/`, `depmod` run, and the initramfs must carry them. |
| **B1** probe-fail | **Still open in the code** (`apple.c:685-728,763-765`: deep-validation failure returns `-EINVAL` and fails the NHI probe). Mitigation is pairing: the prepared `boot-dpin.bin` DT diff is exactly the three intended properties plus two `phy@e50000/e58000` nodes, and the modules ship with it. Residual risk: `boot.bin` loads for **every** GRUB entry, so a DT/module mismatch on any entry loses USB4 on that entry. |
| **NEW N1 (blocker for the stated plan)** | The `elementary-usb4-dptunnel` GRUB entry in `/boot/grub/custom.cfg` has `thunderbolt.allow_dp_tunnel=1 thunderbolt.dprx_timeout=3600000` and **no `thunderbolt.dprx_bypass=1`**. The live `Y` is a runtime write and resets on reboot (`DP-TUNNEL-RE.md`: "bypass resets on module reload/boot"). So the "first boot keeps the bypass safeguard" plan does not hold as configured: with the dock attached at boot, DPRX runs **unbypassed with a 1-hour timeout** until someone writes sysfs after login. That is the retry storm (1,684+ lines) and the section 9 unplug-wedge window. `dprx_timeout` is `0444`, so it can only be set on the command line. Fix: a separate new GRUB entry (leave the current one as fallback) with `thunderbolt.dprx_bypass=1 thunderbolt.dprx_timeout=15000`. Editing GRUB is the owner's call. |
| **NEW N2** | `RECOVERY.md` (and its ESP copy text) tell the owner to copy `boot.bin.KNOWN-GOOD-usb4-test` / `-fairydust-original`. Those files are **not present** in `/boot/m1n1/`. Existing known-good images: `...-pre-dtb-20261014-141046`, `...-pre-m1n1-20261014-142142`, `...-pre-usb4-20261014-135219`, `...-pre-usb4-20261015-140455`, `...-pre-usb4-20261015-152345`. No `RECOVERY.txt` is listed in `/boot/m1n1/` either. The recovery steps need a corrected file name before a boot.bin change. |
| **N3** | `deployment/` has the five modules and `boot-dpin.bin`, but no repacked initramfs and no install script yet (`repack-dpin-initramfs.py` exists). Not ready to apply; the order (modules + `depmod`, initramfs, `boot.bin`, GRUB entry) should be written down and the old `appledrm.ko` in the current initramfs is known to have been stale once. |
| **B3/B4** | Unchanged by this inspection; still open. |

### Suggested one-boot batch (owner decides each step)

1. Fix `RECOVERY.md`/ESP note to name a file that exists; keep the 20261015-152345 image as the rollback target.
2. New GRUB entry with `dprx_bypass=1` and `dprx_timeout=15000` (N1); do not alter the current entry.
3. Install modules + `depmod`, repack initramfs, then `boot.bin`; verify with `modinfo`/`lsinitramfs` before rebooting.
4. First boot: expect "DP source ready ... before DPRX" and no timeout storm; a bypassed DPRX line is not progress.

### Follow-up spot-checks of B3/B4 (Claude, read-only, same tree)

- **B3 confirmed:** `apple_nhi_dp_source_get()` returns `-EOPNOTSUPP` when
  `port != source->port || !async` (`apple.c:613-614`), and `tb_dp_activate()`
  now propagates a negative return. A tunnel on host DP-IN port 6 would fail
  activation instead of timing out. The dock's current pairing is `0:5 <-> 1:14`
  (port 5, the mapped one), so today's dock is unaffected; other docks or a port
  swap would be.
- **B4 confirmed:** the status is read in `tb_dp_dprx_work` (new `source_failed`
  pre-read) and again in the gate before the bypass check in `tb_dp_wait_dprx`.
- **New N4 (timing):** `apple_nhi_dp_source_get()` sets a **5 s** source deadline
  (`apple.c:622`), shorter than the 12 s default DPRX window. If DCP start takes
  longer than 5 s the source is marked failed and the tunnel fails fast, even with
  bypass armed. Fine as a design if intended; the first boot log should show which
  limit was hit, and it is a candidate cause of a "failed" first run that is not a
  hardware wall.
- The ordering itself (adapters enabled, then source requested, status gate before
  bypass, discovered tunnels adopted via `tb_tunnel_start_dp_source`) reads as
  described.

## Brief for DeepSeek's next pass (kernel/bridge lane)

Start here: [STATE-OF-PLAY](STATE-OF-PLAY.md) -> this ledger -> [POST-REBOOT-CHECKLIST](POST-REBOOT-CHECKLIST.md).
Bridge source is now checkpointed in the repo as patches 0007-0009 with the handoff
[DCP-SOURCE-BRIDGE.md](DCP-SOURCE-BRIDGE.md) (Codex checkpoint `1985a0c`; the working tree is
`~/Documents/Codex/2026-10-16/hey-x20/work/dpin-implementation/source`). Codex holds the
Git write; send results as a comment on PR #53 or ledger edits, not patches to its tree.
STATE-OF-PLAY says the batch is paused at that checkpoint at the owner's request, and
flags default/fallback-kernel compatibility of the global DT (a DP-IN PHY those kernels
may not provide) as the pre-deployment question: that is B1's residual risk, so item 3
below comes first if the owner resumes.
Do not repeat: port guessing, `/dev/mem` ADT reads, ACIO unbind/bind, crossbar-only
writes, extra `force_link` probes. Constraints: bypass armed on any run that touches
the dock; no change to the owner's default boot entry.

Ordered work, smallest first, each with its done-criterion:

1. **B4** read the source status once per worker iteration and pass it to the gate;
   extend `tools/testing/apple-dpin/test-bridge.py` to extract `tb_dp_dprx_work` and
   cover fail-fast on source error versus retry on `-EINPROGRESS/-EAGAIN/-ETIMEDOUT`.
2. **B3** decide unmapped-port behaviour (return 0 like "no source", keep
   `-EOPNOTSUPP` only for the truly unsupported combination) and test it.
3. **B1** degrade deep DT validation failures to `dev_warn` + source disabled; keep
   `-EINVAL` only for the `apple,dp-source`/`apple,dp-in-port` pair violation. Add the
   port<->transport-index relation (**B7**) while there.
4. **B5** downgrade the expected `-EBUSY` on stop during DCP unbind from `dev_err`.
5. **N4** confirm the 5 s source deadline is intended versus the 12 s DPRX window;
   if kept, make the log say which limit fired.
6. **N3** a reviewed install script and repacked initramfs in `deployment/` (apply
   order in POST-REBOOT-CHECKLIST section C), plus a `lsinitramfs` check of the five modules.
7. **G3 step 0** fetch Sven Peter's v3 series from `thunderbolt.git/fixes`, record
   SHA-1s in `DPRX-TEARDOWN-BACKPORT-PLAN.md`; patch 6 (stop-time DP teardown) must
   precede any hook that relies on `tunnel_stop()` at shutdown.

Report back by appending to this ledger (status column) and the PR #53 thread.

## Status update after Codex checkpoint (patches 0007-0009) — Claude, 2026-10-16

Codex's handoff (`DCP-SOURCE-BRIDGE.md`) says B1-B8 are addressed in the checkpoint.
I spot-checked the committed `0008` patch and found: B1 `dev_warn("DP source disabled ...
retaining USB4 data support")` replaces the probe failure; B2 `devm_phy_get` (mandatory)
when `apple,dp-tunnel` is set, else optional; B7 the `apple,transport-index` check with
`index > 1`; B3 test asserts `-EOPNOTSUPP` for the non-async case. B4/B5/B8 I did not
re-verify. Treat B1, B2, B7 as **fixed (spot-checked)** and the rest as **fixed per Codex,
unverified by me**; runtime qualification is still outstanding.

N3 (install script): a reviewed draft now exists, [`install-dpin-batch.sh`](install-dpin-batch.sh).
Dry-run by default; it verified the current (unfrozen) bundle's SHA-256s and vermagic and
printed the plan and GRUB entry without writing anything. It has **not** been run with
`--apply`. Known side effect, documented in the script header: the shared module tree means
the existing `elementary-usb4-dptunnel` entry loses USB4 after install (use the new entry or
roll back). Remaining before use: Codex freezes the bundle so the manifests are final.

## Controlled-test first boot (11:45) — result recorded 2026-10-16

Full analysis: [evidence/2026-10-16-controlled-test-first-boot.md](evidence/2026-10-16-controlled-test-first-boot.md).
Summary: bridge and DT mapping probe correctly; DP-IN activation failed immediately with
`-ENOLINK` (`phy poweron failed --> -67`) because `apple_dpin_set_inactive()` aborts on HPD
low in its first poll, before the ACK can change (probable cause, from code plus one log
line); a second, separate NULL-deref occurred when the DCP kept a stale `dpin` PHY after the
ACIO re-probed. DPRX was never reached, so this says nothing about the sink. New items:

| # | Item | Owner |
|---|---|---|
| R1 | Instrument the DP-IN registers on failure, then make activation wait for the ACK instead of aborting on first-poll HPD low (update the offline test that asserts the immediate abort) | Codex/DeepSeek |
| R2 | Stale-PHY guard: per-start lookup or bound-provider check so a start after ACIO re-probe fails with `-ENODEV` and never oopses | Codex/DeepSeek |
| R3 | `STATE-OF-PLAY.md` still says no reboot has happened; the first boot did | **Fixed** in the outcome record commit (STATE-OF-PLAY updated) |

## Tooling

| # | Defect | Status |
|---|---|---|
| T1 | `test-dp-tunnel.sh` counted every `connected` DRM connector, including eDP, so "paths activated" could print display success. | **fixed** in this batch: counts only `card*-DP-*` / `card*-HDMI-*`. On the live machine the old count included eDP (1), the new count is 0 (both external connectors disconnected). |
| T2 | Stock `trace_dptx.py` omits `atcN-dpin*`/`atcN-dpxbar`. | `trace-dpin.py` covers it; synthetic tests only. |

## Do not repeat

Already closed elsewhere (see STATE-OF-PLAY "Do not repeat"): port guessing,
`/dev/mem` ADT reads, ACIO unbind/bind recovery, crossbar-only writes, further
`force_link` probes to manufacture evidence.

## Codex source checkpoint disposition — 2026-10-16

The owner requested stopping. Patches 0007–0009 and DCP-SOURCE-BRIDGE.md now
record the implementation against B1–B8: graceful optional bridge disable,
mandatory tunneled PHY, unmapped-port no-op, one readiness read, retained
cleanup ownership, serialized unbind, T6000 mapping validation, locked
cancellation and HopID router references. Final changed modules compile and
27 bridge production-function groups pass. These are source dispositions,
not hardware closure or a complete upstream teardown-series qualification.

Next resolve global-DT compatibility/rollback for default and fallback
kernels before any deployment. No new modules/boot payload/initramfs were
installed, and no reboot or cable change occurred in this batch.

## DeepSeek current handoff — controlled test, 2026-10-16

Resumed directly at fallback compatibility. Patch 0010 preserves ordinary
DCP phys and uses a managed vendor-reference getter (11 fault/refcount groups,
independently reviewed). Frozen source c6fd906 rebuilt from cleaned module
outputs; all five version/layout/export checks pass. The final real initramfs
was inspected for all five hashes, preload-before-coldplug and absence of
Thunderbolt parameter overrides. Separate entry: bypass1/timeout15000. N1/N3
preparation gaps addressed by the isolated initramfs, hash-guarded installer and
rollback. Root modules/default/original images are preserved, superseding the
root-module-replacing shell draft. Five-second source deadline remains N4.

No hardware test has run. Next: one-shot controlled boot, confirm actual loaded
module build IDs and parameters, capture PHY/source errors and external EDID/modes.
No unbind/reload/cable exercises or repeated binary/port discovery. See
CONTROLLED-TEST.md and evidence/2026-10-16-controlled-test-preflight.json.

Deployment completion: the reviewed three-target plan is now staged and verified.
Exact original boot/config/grubenv backups verified; root modules and original
image/kernel unchanged. No reboot armed/performed. DeepSeek's next task is to
review the controlled boot's actual module IDs/parameters/source timing and
external connector evidence, not rebuild or rediscover the dock.
