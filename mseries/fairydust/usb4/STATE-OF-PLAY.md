# WD22TB4 dock video — state of play (read first)

Updated 2026-10-16. This is the cumulative frontier ledger. Preserve measured
advances and do not re-run discovery without a new reason.

## First live boot of the bridge — outcome (2026-10-16)

The controlled one-shot boot ran (11:45:04–11:47:13, dptunnel kernel, exactly
`allow_dp_tunnel=1 dprx_bypass=1 dprx_timeout=15000`; all five rebuilt modules
loaded). The bridge engaged automatically on the real dock tunnel
(`0:5 <-> 1:14`): `apple_dp_source_work` → `apple_dcp_dp_source_start` →
`dcp_dptx_connect_source` → `phy_init` → `dpin_init`. Live results:

- First attempt: `phy poweron failed --> -67` (`-ENOLINK` from the DP-IN
  activation gate; DP-IN HPD level was low at activation, ~4 s after bring-up)
  → `DP source preparation failed: -67` → tunnel torn down. `-ENOLINK` is final
  to the worker (only `-EAGAIN`/`-EPROBE_DEFER`/`-EINPROGRESS` retry to the 5 s
  deadline), so no retry happened.
- Second attempt (after the USB4 link dropped and re-initialized at
  11:46:27–30): kernel Oops in `dpin_init` — `pm_runtime_resume` called with a
  NULL device (`dpin->dev`); worker killed; tunnel torn down again at 11:46:48.
- A Gala/simpledrm boot race crashed the desktop before the collector could
  run. The `~/.cache/mseries-gala-failed` marker was removed on 2026-10-16
  (self-healing launcher); the race cause is recorded (appledrm registers
  after gala on the dptunnel entries) and the `lightdm-wait-for-drm.conf`
  drop-in is installed (effective next boot, unverified).

No picture; M1–M4 remain unmet. Full record:
[evidence/2026-10-16-controlled-test-first-boot-outcome.md](evidence/2026-10-16-controlled-test-first-boot-outcome.md).
Next: re-run the controlled boot with the collector (R1/R2 fixes staged at
revision `46bb8b6`; boot owner-gated). The session-race cause is recorded and
the drop-in takes effect at the next boot.

## First-boot failures fixed and re-staged — 2026-10-16

R1/R2 are implemented in source revision `46bb8b6` (public patch 0011):
`apple_dp_source_work` retries `-ENOLINK` every 50 ms until the existing 5 s
deadline (Apple's abort semantics kept), `dpin_power_on` logs
INACTIVE/ACK/HPD/IRQ registers once per state change on failure, and every
dpin op plus the DCP connect path fail with `-ENODEV` on a stale PHY instead
of oopsing. Five modules rebuilt; all offline suites pass (28 bridge groups
including the new `-ENOLINK` retry group); checkpatch clean; the refreshed
bundle re-validated (the only new undefined symbol versus the booted bundle
is `_dev_info`, referenced by the target tree's own `appledrm.ko`).

The controlled-test payload was re-staged and re-installed with the reviewed
tooling (rollback → stage → verify → plan → apply): new image `486be1d9…`
(verified offline: five module hashes, preload order, unique test
parameters), same append-only `custom.cfg` (`9eadf091…`) and fallback-safe
`boot.bin` (`6702f2c7…`). Fresh rollback set
`/home/sdolbec/dptunnel-logs/rollback-46bb8b6`; the c6fd906 rollback set is
superseded. `next_entry` stays empty; no boot armed or performed. Record:
[evidence/2026-10-16-r1-r2-fix-and-restage.md](evidence/2026-10-16-r1-r2-fix-and-restage.md).

## Controlled-test preparation resumed — 2026-10-16

The owner resumed at fallback compatibility, with no repeated discovery.
Patch 0010 preserves DCP's original phys and every existing PHY dependency;
only the new driver consumes apple,dp-tunnel-phy through a managed getter.
Independent source review and 11 lookup fault/refcount groups pass. Static
fallback compatibility is addressed; fallback boot/runtime remains untested.

The frozen source c6fd906 was clean-rebuilt for all five modules, followed by
version/layout/export checks and actual staged-image verification. The new
initramfs alone carries the new modules and metadata; root modules, original
initramfs, kernel/default and existing GRUB entries remain untouched. The
separate entry uses bypass=1 and timeout=15000. Exact artifacts, hash-guarded
installer, rollback and collector: [CONTROLLED-TEST.md](CONTROLLED-TEST.md).
The earlier root-module-replacing installer is superseded for this test.
No reboot, module reload/unbind, cable move or hardware success is claimed.
**Deployment status: STAGED AND VERIFIED.** The new initramfs, append-only
custom.cfg and fallback-compatible boot.bin are installed and hash-checked.
Original boot/config/grubenv backups were verified at
`/home/sdolbec/dptunnel-logs/rollback-c6fd906` (superseded by
`rollback-46bb8b6`, see the re-stage section above). Root modules, original initramfs,
kernel/default and grubenv are unchanged. No reboot is armed (`next_entry` empty)
or performed; running modules remain unchanged. That one-shot boot ran on 2026-10-16 (outcome in the first section above);
the collector was not run (desktop race).

## Current result

**No monitor picture through the dock. No unbypassed DPRX completion or EDID
has been demonstrated.** A separate live test fixed selection of the dock's
HDMI-facing DP OUT adapter. The new DP-IN handshake/tunnel-clock series was installed and ran live once
(2026-10-16): the bridge engaged on the real dock tunnel and failed in the
DP-IN activation gate (`-ENOLINK`) plus a `dpin_init` Oops on the retry — see
the first section above.

Current authorization: the owner now permits installation, reboot and cable
changes when needed, but wants them batched. This supersedes earlier bans.
The current bridge batch is stopped at a saved source checkpoint at the owner's
request; no new driver or boot payload has been installed/loaded. Preserve the current cable layout
unless a concrete test requires a change. Codex owns Git writes for this
batch; scoped DeepSeek review was requested but transport failed.
Keep the dock on M1 Pro left-front, HDMI on the Amazon Basics monitor and
Neo connected separately. Preserve the occupied Neo firmware connection.
Primary chat must not block on SSH; delegate remote work with hard timeouts.
Active progress updates are requested every 30 seconds.

An automatic NHI-to-DCP source bridge is now implemented in the isolated
source. Its 27 production-logic test groups and final changed-module builds pass.
Patches 0007–0009 and [the handoff](DCP-SOURCE-BRIDGE.md) save that checkpoint.
Before deployment, resolve compatibility/rollback for default and fallback
kernels: the candidate global DT introduces a DP-IN PHY they may not provide.
One single-boot test has occurred (2026-10-16); see the first section above.
Hardware M1/M2/M3 below remain unproven. A discovered BTF-module layout hazard
in the earlier module-only recipe is recorded at the top of OS9-HANDOFF;
retain module layout even when BTF data generation is skipped.

## Milestones — observable evidence, not analysis

| Gate | Required evidence | Recorded result |
| --- | --- | --- |
| M0: downstream sink presence | dock DP OUT reports HPD | **MET**: `1:14` HPD=1, `1:13` HPD=0 in the recorded live test |
| Correct tunnel target | host DP IN paired with HPD adapter | **MET** after independent 0003: `0:5 <-> 1:14` |
| Visible monitor wake | monitor visibly leaves standby/searches for source in response to a recorded action | **NOT DEMONSTRATED** |
| M1: host feeds the tunnel | real DPRX completion with bypass OFF, no timeout | **NOT MET**: timeouts remain on `0:5 <-> 1:14` |
| M2: display detected | DRM connected, EDID/valid mode, no firmware link failure | **NOT MET** |
| M3: picture through dock | visible output from dock HDMI with matching mode | **NOT MET** |
| M4: repeatability | repeated success across qualified lifecycle transitions | **NOT MET** |

The earlier ledger saying "before M0" or "zero sinks" was based on looking
for adapter sysfs devices that do not exist. Dock HPD proves sink presence;
it does **not** prove the entire monitor/cable/dock video chain can display
pixels. The earlier "H1 closed" claim is therefore limited to presence.
Likewise, "the only wall" / "SOLVED" overstated what static analysis and a
DPRX timeout establish. DP-IN/clock/lifecycle integration is the leading
missing host path; further failures have not been excluded.

## Live advances that must be preserved

[Recorded HPD adapter-selection test](evidence/2026-10-16-hpd-fix-tested-module-only-rebuild.md)
reports that `0003-dp-out-prefer-adapter-with-hpd.patch` was built and loaded
in the earlier live session. It changed `0:5 <-> 1:13` to `0:5 <-> 1:14`.
DPRX still timed out with video/audio enable and AUX/video HopIDs programmed
at both ends. Keep this fix; do not reopen the socket selection question.
This live report is separate from the present offline DP-IN implementation.

Adapter map, read from Thunderbolt debugfs config space:

```
HOST 0-0 port5 = 0x0e0101 DP_HDMI_IN  -> dpin0
HOST 0-0 port6 = 0x0e0101 DP_HDMI_IN  -> dpin1
DOCK 0-1 port13 = 0x0e0102 DP_HDMI_OUT -> HPD=0 in the test
DOCK 0-1 port14 = 0x0e0102 DP_HDMI_OUT -> HPD=1, HDMI monitor in the test
```

Both DP OUT adapters exist regardless of sink presence; they are not sysfs
devices. USB data/Ethernet enumeration and tunnel activation do not establish
monitor AUX/DPCD communication. A bypassed "DPRX capabilities read completed"
message does not establish a sink response.

## Concrete new source — offline only

[DPIN-IMPLEMENTATION.md](DPIN-IMPLEMENTATION.md) is the review/build/DeepSeek
handoff for additional patches **0004, 0005, 0006**. They implement a separate
DP-IN generic PHY, resource/IRQ wiring, inactive/ACK handshake, HPD deferred
notifications, shared ATC tunnel clocks and DCP callback/error handling.
Stable PKGBUILD/config have not been changed to auto-deploy them.

Actual base: fairydust `ce9f2eba72c061a50b2d790450e90af3439d8c24` plus
`0001-usb4-thunderbolt-apple-m1pro-on-fairydust.patch` and
`0002-experimental-dp-tunnel.patch`. Preserve independent `0003`.

Validated: 29 production-logic groups, 2 compiled-board checks, complete
Apple DRM/PHY relocatable objects, target/control DTBs, binding documents,
DP-IN-filtered DTB schema and clean patch application. **Not** final MODPOST,
production Rust/BTF configuration, hardware concurrency, DP-IN ACK, PLL lock,
DPRX, EDID, picture or suspend. No new module/DTB/kernel was installed here.

## Correct recovered protocol (supersedes early register guesses)

Matching macOS 13.5/22G74 `mac13j` kernelcache, T600x DCP firmware and shipped
j314sap ADT were selectively obtained from the official Apple restore.
They are available privately; no macOS reboot is needed to fetch them.
[REA findings](REA-DPIN-FINDINGS.md) contain hashes, original-byte/dispatch
checks and the separate [Ghidra cross-check](evidence/2026-10-16-ghidra-dpin-crosscheck.md).

DP-IN0 `0xb01e50000`, DP-IN1 `0xb01e58000`, each `0x4000`, shipped IRQ values
1354/1355, parent ACIO1/ATC1. This is shipped-board metadata, not a live ADT.

| Byte offset | Derived function |
| --- | --- |
| `0x00` | HPD level bit 2, latched plug/unplug bits 0/1 |
| `0x04` | IRQ status; captured-value acknowledgment |
| `0x08` | IRQ enables; OR 3 enables the two HPD sources |
| `0x0c` | inactive request bit 0; **clear to activate** |
| `0x10` | inactive ACK bit 0; wait for requested state |

Activation has a one-second bound and observes HPD while ACK is pending.
Deactivation waits with HPD low too. IRQ capture is status/HPD/status until
stable. The earlier report calling `0x04` a handshake and setting `0x0c`
activation is superseded. Crossbar MMIO is a different block.

T6000 `initDPTunnel` is a no-op; link-rate dispatch reaches inherited T8103
clock configuration. Both DP-IN ports share a fixed AUSPLL descriptor and
have separate PCLK enable/select fields. This is separate from physical
DP-altmode AUX/lane setup and existing USB4 CIO PLL/common power. DP-IN
connection attributes are `0x101` (role 1 + HPD support), not physical-DP
attributes. Do not guess a different DCP core based on a PHY transport index.

## Next frontier task — do not restart discovery

The outstanding integration question is **ordering**: this draft activates
DP-IN on DCP's ACTIVATE callback, while the USB4 router waits for DPRX during
tunnel activation. Establish whether an earlier router hook is required;
do not assume the dependency is resolved or blindly bypass it. Compare
opaque ACIO tunnel-use ownership with Linux's existing routing/lifetime.
The pinned source confirms DPRX activation is asynchronous (`-EINPROGRESS`,
25ms polls / 50ms delays, default 12s deadline), and contains no automatic
Thunderbolt-to-DCP start bridge. See the implementation handoff's exact
function chain. Starting DCP only after DPRX success would be too late if
DPRX needs DCP; this is not proof of an unavoidable synchronous deadlock.
Keep manual force-link as the current experiment entry, not an automatic
connect triggered solely by HPD. No new live action is authorized here. **Update 2026-10-16:** the ordered
one-shot boot has now run (outcome above): with bypass armed, the router-side
hook does fire and the bridge runs automatically on tunnel activation; the
remaining live blockers are the DP-IN activation `-ENOLINK` gate and the
`dpin_init` Oops. Bypass-off DPRX ordering remains to be qualified after those
fixes.

Next: review the published series and resolve that call order using the
already acquired source/binaries, complete normal-config/MODPOST coverage,
then prepare one bounded hardware experiment for later owner authorization.
The evidence ladder is DP-IN ACK/clock lock -> real DPRX -> EDID/modes ->
picture. A monitor wake is useful evidence but not a completed display link.
Record tested patch revision and exact failure at each step.

Do not repeat port guessing, dock moves, macOS flips, kernelcache discovery,
physical AUX enable or crossbar-only writes. The Neo has no Thunderbolt
controller in the recorded inventory; its display-capable USB port supplies
a DP-altmode reference, not the M1 USB4 tunnel protocol.

## Operational guards retained from previous sessions

- A live DPRX wait can wedge the port. Do not disable bypass, unload drivers,
  unbind ACIO or unplug anything as part of this offline work.
- Bypass resets on module reload/boot; old snapshots do not prove its current
  value. Existing earlier report records bypass Y, not a new current read.
- NHI loss was not recovered by ACIO unbind/bind. Do not repeat that recovery
  experiment; current reboot prohibition takes precedence.
- `/dev/mem` ADT reads failed EPERM under STRICT_DEVMEM. Do not retry them.
- Read actual runtime/build logs before claiming a new hardware result.
- Work in `wt-dockvideo`; preserve other agents' work and use one Git writer.

## Evidence index

- [First controlled-test boot outcome](evidence/2026-10-16-controlled-test-first-boot-outcome.md)
- [Current implementation / DeepSeek next task](DPIN-IMPLEMENTATION.md)
- [Offline validation record](evidence/2026-10-16-dpin-offline-validation.json)
- [REA derived findings](REA-DPIN-FINDINGS.md)
- [Ghidra corroboration](evidence/2026-10-16-ghidra-dpin-crosscheck.md)
- [Earlier HPD fix live result](evidence/2026-10-16-hpd-fix-tested-module-only-rebuild.md)
- [Earlier address-level RE foothold](evidence/2026-10-16-re-foothold-for-remaining-subsequences.md)
- [Host stack decomposed: only DP-IN + routing missing](evidence/2026-10-16-host-stack-decomposed-dpin-and-crossbar-routing.md)
- [Router vs DCP activation ordering (answers handoff item 2)](evidence/2026-10-16-router-vs-dcp-activation-ordering.md)
- [Original audit](DPIN-AUX-AUDIT.md), [routing RE](DP-TUNNEL-RE.md)
- [Gap ledger from the 2026-10-16 offline review (owners, status)](REVIEW-2026-10-16-GAPS.md)
- [Router-side DP-IN hook and refcount design sketch (ledger G1/G2)](DPIN-ROUTER-HOOK-DESIGN.md)
- [DPRX teardown series backport plan (ledger G3)](DPRX-TEARDOWN-BACKPORT-PLAN.md)
- [Batched reboot: pre-flight, GRUB entry, post-reboot checks](POST-REBOOT-CHECKLIST.md)
- [HDMI: what works today, decision frame and plan (read this first for priorities)](HDMI-FASTEST-PATH.md)
- [Controlled test, first hardware boot: DP-IN activation aborted at once; stale-PHY oops](evidence/2026-10-16-controlled-test-first-boot.md)
- [Pantheon fails to start on the dptunnel entries: gala aborts in mutter KMS modeset after a DRM hotplug](evidence/2026-10-16-pantheon-session-crash-on-dptunnel-entries.md)

Keep raw Apple binaries, decompiler output and raw machine captures private.
