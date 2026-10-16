# WD22TB4 dock video — state of play (read first)

Updated 2026-10-16. This is the cumulative frontier ledger. Preserve measured
advances and do not re-run discovery without a new reason.

## Current result

**No monitor picture through the dock. No unbypassed DPRX completion or EDID
has been demonstrated.** A separate live test fixed selection of the dock's
HDMI-facing DP OUT adapter. The new DP-IN handshake/tunnel-clock series is
implemented and offline checked, but has not been installed or tested live.

Owner constraints remain **no kernel installation, no M1 reboot, no cable
moves** for this implementation. Keep the Dell dock on M1 Pro left-front
(nearest trackpad), HDMI on the Amazon Basics monitor, and the Neo connected
separately. Preserve the Neo's occupied firmware connection. Primary chat
must not block on SSH; remote work needs delegated workers and hard timeouts.
Active progress updates are requested every 30 seconds.

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
connect triggered solely by HPD. No new live action is authorized here.

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

- [Current implementation / DeepSeek next task](DPIN-IMPLEMENTATION.md)
- [Offline validation record](evidence/2026-10-16-dpin-offline-validation.json)
- [REA derived findings](REA-DPIN-FINDINGS.md)
- [Ghidra corroboration](evidence/2026-10-16-ghidra-dpin-crosscheck.md)
- [Earlier HPD fix live result](evidence/2026-10-16-hpd-fix-tested-module-only-rebuild.md)
- [Earlier address-level RE foothold](evidence/2026-10-16-re-foothold-for-remaining-subsequences.md)
- [Original audit](DPIN-AUX-AUDIT.md), [routing RE](DP-TUNNEL-RE.md)

Keep raw Apple binaries, decompiler output and raw machine captures private.
