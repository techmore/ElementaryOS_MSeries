# Automatic DCP source bridge before DPRX

2026-10-16. Apply experimental patches **0007, 0008, 0009** after 0001–0006.
Keep the tested 0003 HDMI-adapter preference. This is original experimental
Linux source plus attributed upstream lifetime fixes, not hardware-qualified
USB4 video support. [STATE-OF-PLAY](STATE-OF-PLAY.md) records hardware results.

## Later fallback fix and controlled-test plan

Patch 0010 supersedes the earlier global-DT blocker and PHY lookup description
below. It preserves legacy phys, adds a separate managed DP-IN reference and
uses an isolated test initramfs. Read [CONTROLLED-TEST.md](CONTROLLED-TEST.md)
for final artifacts, fresh build evidence and current deployment status.
The earlier checkpoint and qualification limits remain historical evidence.

## Stopped at source checkpoint — 2026-10-16

The owner requested a natural stopping point. Patches 0007–0009 now save the
DCP-before-DPRX bridge with source ownership, cancellation and router lifetime
handling. Final changed module builds pass; 27 bridge groups plus the earlier
29 logic groups pass, along with two board checks. Clean patch application
byte-matches 14 reviewed source files. These are offline checks, not monitor
progress: no new wake, unbypassed DPRX response, EDID/modes or picture.

No new driver, initramfs or boot payload was installed or loaded; no reboot
or cable change occurred in this batch. Only the build dependency pahole was
installed. The prepared boot payload remains a private candidate.

**Resume blocker:** the global boot.bin device tree replaces DCP's PHY with a
new DP-IN provider. Resolve default/fallback-kernel compatibility and a tested
rollback plan before deployment; a stock kernel may lack that provider.
Initramfs/module staging and the first hardware test remain undone. Do not
install the prepared payload merely because the source checks passed.

See [bridge implementation and validation](DCP-SOURCE-BRIDGE.md).

## Owner authorization and current action

The owner explicitly changed the earlier constraint: dependencies/drivers may
be installed, and reboot/cable changes are allowed when needed, **batched**.
The proposed first test leaves the dock and HDMI where they are and uses one
reboot, after the deployment blocker above is resolved. No repeated macOS switches or cable exercises are required.
Read the latest deployment status in OS9-HANDOFF before acting; do not infer
installation or a successful boot from this source document.

## Implemented sequence

The NHI has an optional paired DT mapping, `apple,dp-source` and
`apple,dp-in-port`. Only j314s's experimental ACIO1/NHI maps host DP-IN port5
to dcpext1. The source's `phys` must name an enabled T6000 DP-IN provider
under that same ACIO, with port5/index0 or port6/index1. Other ports and NHIs
retain the normal path. A malformed property pair fails probe; deep mapping
or optional display-workqueue setup failures warn and disable the bridge,
preserving USB4 data support.

Normal activation enables the paths and both adapters, then requests a source
reference. The request only queues a separate ordered/freezable source worker.
That worker calls DCP **outside `tb->lock` and outside its own state mutex**.
It initializes and powers on DP-IN before sending DCP connect/requestDisplay,
so source activation does not wait for a downstream DCP ACTIVATE callback.
The callback sees the existing powered reference and does not double-acquire.
A tunneled DCP requires its PHY; missing/not-yet-bound providers fail or defer
probe rather than becoming an optional null-PHY success.

DPRX work checks source readiness before any DPRX register read, including
when `dprx_bypass` is enabled. Pending DCP readiness retries within a bounded
source deadline. A source failure is classified separately from an ordinary
DPRX read timeout and fails promptly. Preparation returns success only after
PHY activation, link rate and lanes are present with no link error.

Firmware-discovered host DP tunnels adopt the same source and asynchronous
DPRX path without toggling the discovered paths. Unmapped/other-platform
tunnels are unchanged. Duplicate start does not acquire another work reference;
a still-running canceled work item is rejected rather than reused unsafely.
Suspend/resume remains unqualified; the DP-IN draft refuses system suspend
while its provider is initialized.

Per-NHI source users are counted. Last release queues stop. Generations prevent
an in-flight start from publishing readiness after cancellation. Stop precedes
a replacement generation; cleanup failures preserve ownership and block
restarting until cleanup succeeds. DCP source calls serialize with platform
removal and component unbind. NHI removal drains source work outside the TB
lock before ACIO powers down.

## Lifetime prerequisites incorporated

The CM-owned DP tunnel retains its domain reference until destruction, covering
canceled work and allocation/activation errors. Pending DP and source-owned
active DP tunnels deactivate during domain stop. Cancellation is checked under
the domain lock in both the DPRX worker and completion callback before touching
adapters. Allocated HopIDs retain their routers until release; KUnit fixtures
initialize those device references correctly.

The HopID changes and cancellation/stop guards adapt Sven Peter's published
[v3 HopID fix](https://lists.openwall.net/linux-kernel/2026/08/29/303),
[canceled-work fix](https://lists.openwall.net/linux-kernel/2026/08/29/305), and
[domain-stop fix](https://lists.openwall.net/linux-kernel/2026/08/29/302).
Derived-source hashes and scope are in the validation record. This is not a
claim that the complete upstream six-patch series has been backported or that
Apple's unplug hazard is hardware-qualified. The first boot keeps bypass on.

## Checks completed

- 27 production bridge/worker/gate/refcount/adoption/HopID test groups;
  the earlier 29 production-logic groups still pass.
- Actual compiled target and control board mapping checks, binding documents
  and NHI-filtered DTB schema validation pass without diagnostics.
- Full changed Thunderbolt/Apple NHI/Apple DRM and PHY module builds complete.
  No full kernel Image or production Rust driver rebuild is claimed.
- Every new module matches the running kernel's full vermagic, expected
  init/cleanup relocation offsets and required loaded/bundled export names.
- Clean patch application reconstructs the reviewed source byte-for-byte.
  Checkpatch reports zero errors and one generic new-file MAINTAINERS warning.
- Five boot-payload checks and five initramfs preservation/rejection checks.
  Fake-MMIO/transport tests do not qualify actual firmware timing or concurrency.

Run from the patched kernel tree:

```sh
python3 tools/testing/apple-dpin/test-bridge.py .
python3 tools/testing/apple-dpin/test-clock.py .
python3 tools/testing/apple-dpin/test-connection.py .
python3 tools/testing/apple-dpin/test-dtb.py \
  "$OUT/arch/arm64/boot/dts/apple/t6000-j314s.dtb" \
  "$OUT/arch/arm64/boot/dts/apple/t6001-j314c.dtb"
```

[Validation record](evidence/2026-10-16-dcp-source-bridge-validation.json)
contains the patch/module/payload hashes and exact qualification boundaries.

## Correct module-only build for this machine

Start from `/proc/config.gz`, merge `dpin-live-module.config`, and use an
isolated output. Pass **`LOCALVERSION=` explicitly to every make**, including
`modules_prepare`, to avoid a Git `+` suffix. Use `M` for each source directory
and `MO` for a separate external-module output directory. Build PHY, DRM, then
Thunderbolt; pass the preceding `Module.symvers` with `KBUILD_EXTRA_SYMBOLS`.
`KBUILD_MODPOST_WARN=1` is required without a complete kernel symbol table;
independently resolve every undefined symbol against real exports before use.

**Retain CONFIG_DEBUG_INFO_BTF_MODULES.** Disabling it changed the cleanup
pointer offset from the installed kernel's `0x4a8` to `0x490`, despite matching
vermagic and total structure size. The earlier module-only recipe was wrong
about ABI neutrality. Install pahole if necessary; missing `vmlinux` can skip
actual BTF data generation while retaining the structure layout. Clean external
module outputs after changing config: cached objects otherwise retain the old
layout. Rust is disabled only for these C modules; the running kernel and its
existing Rust GPU driver are not rebuilt or replaced.

The live bundle contains `phy-apple-atc.ko`, **`phy-apple-dpin.ko`**,
`appledrm.ko`, `thunderbolt.ko`, and `thunderbolt_apple.ko`. It preserves 0003.

## Prepared boot payload and rollback

[`tools/prepare-dpin-boot.py`](tools/prepare-dpin-boot.py) writes a new output
file and never overwrites inputs. It replaces exactly one embedded j314s FDT,
normalizes phandle references, and rejects semantic changes beyond the two
DP-IN nodes, DCP PHY reference and paired NHI mapping. All other original boot
payload bytes are preserved. The original contains 110 valid embedded FDTs;
a raw magic count alone included a false positive.

[`tools/repack-dpin-initramfs.py`](tools/repack-dpin-initramfs.py) similarly
prepares a fresh output from the existing gzip/newc archive. It changes the
specified regular module/metadata files and verifies every unrelated archive
entry's metadata and contents are preserved. It rejects ambiguous archives,
unsafe paths and nonregular replacement targets. The old initramfs includes
appledrm/ATC, so root-filesystem module updates alone would leave stale drivers
loaded. The new image must contain the same bundle and regenerated dependency
metadata.

Before deployment, retain original modules, module metadata, boot.bin,
initramfs and GRUB custom entries in a recorded rollback directory. A single
one-shot GRUB entry should use the existing kernel image, the paired module
bundle/initramfs/DT, **`dprx_bypass=1` and `dprx_timeout=12000`**, not the old
one-hour timeout. Capture kernel messages and external DP/HDMI connector
status, mode and EDID validity after boot. Do not count eDP as dock success.
No direct MMIO pokes, force-link loops, cable moves or macOS boot are required
for this first automatic-start test.

The acceptance ladder is: real DP-IN ACK/clock/DCP responses -> external
connector EDID/modes -> visible picture. A bypassed DPRX message is not a real
DPRX response; an unbypassed test remains a separate qualification step.

## DeepSeek / Claude coordination

The existing OpenCode dock session was sent the design and Git ownership note.
Its streamed review timed out; a separate standalone attempt failed transport.
The shared repo subsequently supplied a separate DeepSeek review (B1–B8) and
Claude's gap/design notes; these were read, preserved and incorporated.
B1/B2 now have graceful bridge disable/mandatory PHY handling. B3 explicitly
leaves unmapped ports alone. B4 now reads readiness once and tests the actual
DPRX worker. B5 only reports EBUSY for retained PHY ownership after failed
unbind, not normal cleanup. B6 retains serialization. B7 validates the limited
T6000 port/index mapping. B8 has locked cancellation checks and router lifetime
protection. Independent runtime qualification is still outstanding.
