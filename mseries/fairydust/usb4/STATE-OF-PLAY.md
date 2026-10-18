# WD22TB4 dock video — state of play (read first)

> **PRIMARY GOAL:** a picture on the WD22TB4 dock's HDMI from elementary OS on this j314s.
> Current blocker is **G3**: the DCP firmware must set link rate + lane count, then read EDID.
> Aurora has j314s Thunderbolt-display prior art; check it before more RE. This dock HDMI path remains unqualified.
> Gates, prior art and rules: [PRIMARY-GOAL.md](PRIMARY-GOAL.md).

Reviewed 2026-10-17; historical hardware records follow. No new boot was performed by the code audit. This is the cumulative frontier ledger. Preserve measured
advances and do not re-run discovery without a new reason.

## Aurora upstream port — offline candidate, 2026-10-17

The owner requested the upstream port. `mseries/aurora/` now packages the
unchanged Aurora `.20` kernel and stages its matching m1n1 + full J314S DTB
from an explicit boot.bin copy. The new `elementary-aurora20` entry preserves
.19/Fairydust entries; neither installer nor staging tool deploys boot.bin or
arms a boot. Guide: [Aurora port](../../aurora/README.md). Package/DT checks and
regressions pass locally; **no new hardware result**, so G2–G5 are unchanged.
The last E4 installation record below remains the last retained hardware state.
Fallback compatibility of the global DT/m1n1 change is still unqualified.

## Latest recorded hardware state — 2026-10-17 (E4 armed; boot outcome not recorded)

The following is the last retained installation record, not a fresh read of the machine.
Read [the code-audit validation and limits](DOCK-CODE-REVIEW.md) before collecting another run.
E4 disables built-in HDMI and is not covered by the older fallback-preserving installer contract.

**The E4 record reports it installed and armed at capture time.** `boot.bin` now carries the
patch-0015 j314s tree (dcpext0 drives the tunnel) plus today's Touch ID DT
edits; `next_entry=elementary-usb4-dpin-controlled` (bypass=1, E3 image). E2
was already disarmed. Built-in HDMI has no controller while E4 is installed.
Record, checks and rollback:
[evidence/2026-10-17-e4-armed.md](evidence/2026-10-17-e4-armed.md).

## Earlier planning snapshot — 2026-10-17 (superseded by E4 armed record)

**Read first:** [evidence/2026-10-17-macos-baseline-dcpext0.md](evidence/2026-10-17-macos-baseline-dcpext0.md).
On macOS 27.0.1 the same Mac → WD22TB4 → dock HDMI → monitor chain trains a
4-lane HBR3 link ~90 ms after HPD, so the sink path works. macOS routed
`atc1-dpin0` to **`dispext0,0` (dcpext0, DPTX port 0)**; every Linux run used
`dcpext1` (`dispext1,0`). The live ADT matches the shipped DP-IN metadata
(no DT address/IRQ change). Timing (2 s connect timeout) is ruled out.

**Plan at that earlier checkpoint (superseded): E4** — patch `0015` (`ENABLE_DCPEXT0_TB_TUNNEL`) moves the tunnel to
dcpext0; staged in the repo only, not built or booted. E2 is still armed for
the next Linux boot and still targets dcpext1; the owner decides whether to
clear it and run E4 first. Gates are in the evidence note.

## Resume pointer — 2026-10-16 (after the E1 boot)

**E1 has RUN. Read its result first.** The one-shot boot
(`next_entry=elementary-usb4-dpin-controlled`) was consumed; the E1 image
(`46116374…`) is still installed on that entry. Outcome:
[evidence/2026-10-16-e1-boot-outcome-firmware-device-not-responding.md](evidence/2026-10-16-e1-boot-outcome-firmware-device-not-responding.md).

E1 did what it promised — a tunnel-mode `set_hpd` failure is no longer fatal and
the tunnel waited ~5 s, not 1 s — but the firmware still never configured the
link. The `-67` in the `connect_source` line is **our** reply to the firmware's
call 22 (`dptxport_call` maps `DEVICE_NOT_RESPONDING`/`DEVICE_NOT_STARTED`/
`INACTIVE_SINK_DETECTED` to `dptxport_tunnel_reply(..., -ENOLINK)`), **not** a
firmware-returned error and **not** a timeout. So:

- `set_hpd` (H3) is **cleared** as the wall.
- The firmware's own last substantive word before teardown was
  `DEVICE_NOT_RESPONDING` (call 22), with the tunnel DCP's RTKit syslog still
  **13** for the whole boot and no `idx=7,13,15,5,12,9,6` link-config sequence.
- H1 (firmware blocked on the sink-facing path) is the leading hypothesis; H2
  (`set_hpd` is the wrong/unsupported tunnel command) is not excluded — the
  firmware still never answers `set_hpd(1)` (it does answer `set_hpd(0)`).

Monitor ownership during that boot: **on the dock HDMI, no reaction** (no wake /
no source search) — the visible-wake gate stays unmet. External connectors all
`disconnected` (`card2-DP-1`, `card2-HDMI-A-1`); eDP only.

**Next (owner-gated, one reboot each):** E3 (instrument the DP-IN HPD notifier
and the host DP-IN AUX/DPCD status at failure — cheapest, distinguishes "no sink"
from "no AUX"); then E2 (**unbypassed DPRX**, `dprx_bypass=0` — decisive on the
sink question, the documented §9 hazard, arm the bypass before touching a cable);
then the macOS m1n1-hypervisor trace (`MACOS-TRACE-RUNBOOK.md`) if E2/E3 do not
resolve it.

**E3 is now staged (2026-10-16).** Patch `0014` adds DP-IN HPD producer logging
(`DPINDBG irq:` / `hpd_notifier event=`, plus `init/exit/power_on/power_off`
state dumps). `phy-apple-dpin.ko` `9d43d6e7…`, build-id `7beaacf6…`. The E3
image `2c036651…` is installed on `elementary-usb4-dpin-controlled` (bypass=1);
a paired, **un-armed** E2 entry `elementary-usb4-dpin-nobypass`
(`dprx_bypass=0`, same image) was added to `custom.cfg` so one reboot can run
both. **E2 is now ARMED for the next reboot** (`next_entry=elementary-usb4-dpin-nobypass`,
bypass=0, E3 image; owner decision 2026-10-16). Record:
[evidence/2026-10-16-e3-dpin-hpd-instrumentation.md](evidence/2026-10-16-e3-dpin-hpd-instrumentation.md).

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

## Second controlled-test boot — DP-IN gate cleared, DCP link-config timeout (2026-10-16 20:50)

The re-staged controlled entry ran (verified: the five in-memory module build-ids
equal the ones inside `initramfs-linux-asahi-fairydust-usb4-dpin-controlled.img`;
bypass armed on the boot itself). The automatic bridge engaged on the real dock
tunnel `0:5 <-> 1:14`, the crossbar routed `dpin0 to dispext1,0`, and the
previously-blocking DP-IN activation gate **cleared**: `phy poweron failed` = 0
occurrences and no `DP-IN activation failed:` line, so the INACTIVE-ACK handshake
succeeded with DP-IN HPD high. The failure moved one layer up: `DP source
preparation failed: -110` = `-ETIMEDOUT` from `dcp.c:436`, the DCP firmware's
`linkcfg_completion` never firing within `DPTX_CONNECT_TIMEOUT` (2 s) — the DCP
never sent the `set_active_lane_count` request, i.e. it never configured the
sink-facing DP link. Tunnel torn down; DRM external connectors still disconnected;
**no picture**, M1–M4 unmet. Full record:
[evidence/2026-10-16-controlled-test-second-boot-dpin-gate-cleared.md](evidence/2026-10-16-controlled-test-second-boot-dpin-gate-cleared.md).

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
the first section above. **Update (second controlled boot):** the `dpin_init`
Oops did not recur (0011 stale-PHY guard holds) and the DP-IN activation gate
cleared; the failure is now the DCP firmware link-config timeout (`-110`, 2 s) —
see the second-boot section above. **Update (E1 boot):** with the tunnel-mode
`set_hpd` failure made non-fatal and an 8 s linkcfg window (patch `0013`), the
`-110` wall is cleared (the tunnel waited ~5 s), but the firmware still never
configured the link and reported `DEVICE_NOT_RESPONDING` (call 22). The `-67` is
our reply to that call, not a firmware error and not a timeout; H1 (sink-facing)
leads, H2 (`set_hpd`) is not excluded. Frontier = sink/AUX. Outcome:
[evidence/2026-10-16-e1-boot-outcome-firmware-device-not-responding.md](evidence/2026-10-16-e1-boot-outcome-firmware-device-not-responding.md).

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
| Host DP-IN activation | DP-IN INACTIVE-ACK handshake succeeds with HPD high (no `phy poweron failed`, no activation-failure log) | **MET** on the second controlled boot (2026-10-16 20:50) |
| DCP DP link configured | DCP firmware sends `set_active_lane_count` (linkcfg completion) | **NOT MET**: E1 boot showed no link-config sequence; firmware reported `DEVICE_NOT_RESPONDING` (call 22) ~5 s after ACTIVATE |
| Visible monitor wake | monitor visibly leaves standby/searches for source in response to a recorded action | **NOT DEMONSTRATED** (owner: monitor on dock HDMI, no reaction during the E1 boot) |
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

- [E3: DP-IN HPD producer instrumentation — prepared and staged](evidence/2026-10-16-e3-dpin-hpd-instrumentation.md)
- [E1 boot result: `set_hpd` cleared as the wall, firmware reports the sink "device not responding"](evidence/2026-10-16-e1-boot-outcome-firmware-device-not-responding.md)
- [Second controlled-test boot: DP-IN gate cleared, DCP link-config timeout](evidence/2026-10-16-controlled-test-second-boot-dpin-gate-cleared.md)
- [DP-IN debug boot: instrumenting the DCP link-config path](evidence/2026-10-16-dpin-dbgboot-instrumentation.md) (patch `0012`, armed 2026-10-16)
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

## 2026-10-18 04:37 — Aurora `.20` + upstream-matched `boot.bin`: highest gate reached G4 (DCP side); NO picture

Payload: kernel `7.1.12-2-20261017.20-sep-ARCH`, `/boot/m1n1/boot.bin` = m1n1-aurora
1.6.1.aurora17-5 + the release's J314S tree (sha256 `9c9c2d01c3bdb278…`), entry
`elementary-aurora20`, SEP driver loaded, dock plugged in ~2 minutes after boot, then unplugged
at 04:37:24 by the owner. The machine **did not hang** on the hot-plug or unplug.

Log evidence (`journalctl -k`, boot 0 of that session):
- **G0:** `thunderbolt 0-1: new device found ...` / `Dell WD22TB4 Thunderbolt Dock`, retimer found,
  `usb 1-1: ... Fresco Logic USB2.0 Hub`, `pcie-apple b30000000.pcie: Link up`.
- **G1/G2:** `apple-dcp 289c00000.dcp: display routed to Thunderbolt DP tunnel dpin0`,
  `dcp_dptx_connect_session(port=0) ... tunnel=1 typec=1 route=borrowed`, `GET_SUPPORTS_HPD 1 usb4=1`.
- **G3:** `DPTXPort: SET_LINK_RATE 0x1e`, `USB4/DPTX: SET_ACTIVE_LANE_COUNT 4` (also
  `set_active_lane_count: unexpected lane count:4 phy: 0` warning).
- **G4 (DCP side):** `display HPD asserted`, `DCP property key=TimingElements ... nr_modes=44`,
  `dcp_hotplug() connected:1 valid_mode:0 nr_modes:44`, then
  `set_digital_out_mode ... "4096x2160": 60` and later `"1920x1080": 60` (10-bit).
  **Not captured:** the DRM connector's `status` while docked (only checked after the unplug).
- **G5: not met.** The owner reports the external screen "pretends it's seen" but displays nothing.
- Teardown on unplug: `INACTIVE_SINK_DETECTED (keep waiting for lanes)` then DEACTIVATE,
  `phy-apple-atc: Pipehandler lock not acked / Failed to lock pipehandler`,
  `pcie-apple ... tunnel reset acknowledgment timed out` (all on the unplug path).

Interpretation (unproven): the DCP firmware trained a 4-lane link and parsed EDID modes through the
Aurora path, which the fairydust experiments never reached, so G3 is cleared on this stack. The
missing step is between "DCP thinks it is scanning out" and light on the panel (DP-IN stream
enable / tunnel bandwidth, the monitor's own cable path, or the compositor not enabling the new
output). Next dock session: capture `/sys/class/drm/card*-DP-*/status`, `modetest -c`, and
Gala's monitor list while docked; try the HDMI monitor on the dock's other output; try the
second USB-C port. Everything else (unplug teardown noise) is secondary.

## 2026-10-18 04:43 — G5 MET: picture on the dock monitor (Aurora `.20` + matched `boot.bin`)

**Result:** the owner reports the dock monitor is displaying the desktop (WD22TB4, J314S, dock
plugged at ~04:42, kernel `7.1.12-2-20261017.20-sep-ARCH`, `elementary-aurora20`, SEP driver loaded).

**What made the difference (one variable):** Gala picked the monitor's preferred mode,
`3840x2160@30` (xrandr showed a 7680x4320 logical canvas at scale 0.5), and the screen stayed
dark while DRM said `DP-2 connected / enabled`, EDID 256 bytes, 38 modes. At 04:43:05 the
external output only (built-in untouched) was switched through Gala's
`org.gnome.Mutter.DisplayConfig` (`ApplyMonitorsConfig`, temporary) to `1920x1080@60.000`:

    apple-dcp 289c00000.dcp: set_digital_out_mode(color:108 timing:76) "1920x1080": 60 148500 ... 0x40
    ... depth:10 format:0 colorimetry:10

and the picture appeared. Earlier 1080p60 sets on 04:37/04:39 (before this) were not accompanied
by a reported picture, so the trigger may be the specific modeset sequence (this one
started from the 4K30 state) rather than the resolution alone — unproven.

Gates: G0-G4 met as logged above (`DP-2 connected enabled`, `Dell WD22TB4`, link rate `0x1e`,
4 lanes, EDID); **G5 met 2026-10-18 ~04:43, owner-confirmed by eye**. Not yet established: whether
4K30/4K60 can be made to work, whether it survives replug, suspend, a reboot, or the HDMI
port's other monitors; whether the dock's Ethernet works on this stack.

Tool: `mseries/display-profiles/mseries-display-profiles` (apply/nudge helpers) and the
Display Settings app already talk to the same D-Bus API; the nudge logic (`nudge_modes`, SAFE
modes 1920x1080@60/59.94) is exactly what recovered this. Next: save a display profile for the
docked layout, test replug/suspend/reboot, then try 4K60.

### Correction/addendum 04:44 — why the picture stopped and flickered

The picture seen at 04:43:05 lasted ~4 s because the user's own autostart daemon
`mseries-display-profiles watch` re-applied the saved profile `desk-4k` (3840x2160@30) on the
resulting `MonitorsChanged` (04:43:09 `set_digital_out_mode ... "3840x2160": 30`). So:
**1080p60 gives a picture; the saved 4K30 profile gives a dark screen (and the flip between
them looked like flicker).** The profile `desk-4k` (monitor id `INS:NS65…`) now stores
`1920x1080@60.000` for the external (backup `~/.config/mseries/display-profiles.json.pre-1080p-*`);
after one extra re-apply (60.000 / 59.94 timings alternating 04:43:36-41) no further modesets
were logged through 04:43:54. G5 is therefore met at 1080p60 only; whether it holds across
minutes, replug, suspend and reboot, and whether 4K works at all, are open. The name `desk-4k`
is now misleading; rename when stable.
