# M4 Mac mini upstream readiness audit — 2026-10-21

Target: owner’s M4 / 16 GB Mac mini; expected J773g / T8132 / Mac16,10. Confirm model and Ethernet variant in macOS before producing board artifacts. No hardware access, boot, build, partition change or installation performed.

## Finding

Preparation is feasible; a qualified elementary OS dual-boot release is not established. Initial M4 support exists, and newer experimental J713 work is substantial. Do not equate the Air’s internal-panel results with Mac mini HDMI qualification. RAM capacity is not the primary blocker.

## Captured upstream inventory

Public branch and open-PR metadata was paginated for these repositories. Heads below are immutable audit anchors; inventories are discovery, not reviews of every branch. Recursive GitHub trees were truncated, so absence in those trees is inconclusive. torvalds/linux has no GitHub pull-request endpoint (404); review uses kernel mailing lists instead.

- 0xSero/mac-mini-m4-linux: `main` / `e0d67e3ff9d5595e17ae3833d2afd9fff150e51b`; 1 branches. https://github.com/0xSero/mac-mini-m4-linux
- AsahiLinux/asahi-installer: `main` / `e93743d52178b3e26e428fa05174ef549abf30cb`; 3 branches. https://github.com/AsahiLinux/asahi-installer
- AsahiLinux/linux: `asahi` / `94fb23346d522edf53722357c426a3e58030beea`; 159 branches. https://github.com/AsahiLinux/linux
- AsahiLinux/m1n1: `main` / `7cde7d1a784d851ebfee5579fa363c38b14150c0`; 15 branches. https://github.com/AsahiLinux/m1n1
- AsahiLinux/u-boot: `asahi` / `b33034a515a068381c4aa28831fb709e91300cd1`; 26 branches. https://github.com/AsahiLinux/u-boot
- Aurora-Silicon/linux: `integration/aurora` / `6210b28b00369a4b3bbb769dc3e8c5a1e31d2e87`; 98 branches. https://github.com/Aurora-Silicon/linux
- Kb2uka/Omarchy-M4-Native: `develop` / `dab72d923302ca031ce9d9cfe4925f2dbba36d9e`; 54 branches. https://github.com/Kb2uka/Omarchy-M4-Native
- UbuntuAsahi/linux: `master` / `d54ae8318eb8dccfb7b603ca02b22ca09795cff8`; 12 branches. https://github.com/UbuntuAsahi/linux
- omacom/linux-aurora: `integration/aurora` / `faed71028380b969ed9c943e3ab41d99ca3b9c1a`; 61 branches. https://github.com/omacom/linux-aurora
- stevederico/Sapporo: `master` / `77c32fc95822b3b431ef559c2bd50c513e1d8eae`; 1 branches. https://github.com/stevederico/Sapporo
- torvalds/linux: `master` / `bb29b957eaaa15be33243550d9ee576c2d601669`; 2 branches. https://github.com/torvalds/linux

## Source findings

Asahi and both Aurora integration trees contain t8132-j773g.dts. The inspected Asahi board file declares apple,j773g and keeps ps_dispext0_cpu and ps_dptx_phy powered for the firmware framebuffer. The shared framebuffer starts disabled with zero address/size and loader-populated properties. The memory node is also loader populated: do not hard-code the placeholder memory size for the 16 GB machine. This is boot handoff scaffolding, not a native HDMI driver or demonstrated scanout.

The official M4 matrix lists no installer, NVMe WIP and HDMI/GPU/Thunderbolt unready. Its linux-asahi (7.4) labels are upstream targets, not evidence that a released generic kernel supports the complete machine. https://asahilinux.org/docs/platform/feature-support/m4/

Aurora #147 is merged into omacom integration/aurora and handles M4 wait-state context loss. Aurora-Silicon #370 moves selection earlier to close a boot idle window; its report concerns J616s M4 Pro and remains an open proposal. Review both changes together before choosing a base. https://github.com/omacom/linux-aurora/pull/147

## Experimental patch candidates

### Aurora-Silicon #366: arm64: apple: add basic T8132/J713 (M4 MacBook Air) support
https://github.com/aurora-silicon/linux/pull/366 — state open, merged False; head `98a8f830df94a7dcaf7de37bfa915240afa2dda8`.

Add basic support for the 13-inch M4 MacBook Air (J713) on `integration/aurora`.

The series adds:

- T8132/J713 device trees, bindings, and a kernel configuration fragment.
- NVMe, PCIe/Wi-Fi, GPIO, USB and Type-C controller support, including SuperSpeed host operation on the qualified ATC1 port.
- BCM4388 Bluetooth, per-machine calibration and a shared radio DART with explicitly managed Wi-Fi/Bluetooth streams.
- Keyboard and trackpad support through the retained MTP/RTKit session.
- PMGR ownership handling, memory-controller integration, CPU frequency control, and PMP thermal reporting.
- Explicitly enabled, bounded NVRAM writes for boot-volume selection.

Display uses the firmware framebuffer with software rendering. Native GPU and DCP support are a separate series.

USB3 and Bluetooth are two additional commits. USB3 uses banked PHY calibration, checks inherited common-domain state before admission, and supports the USB side of multifunction USB/DP adapters without mapping the display crossbar or enabling external display output. ATC0 stays USB2. Bluetooth uses a bounded high DMA aperture and owned SIDs 1/2; unrelated streams and legacy Broadcom register layouts remain unchanged. Unmasked DART reporting and a fault IRQ are required; detected mapping faults quarantine the owned streams while retaining published DMA state.

Validation:

- The exact Linux tip `98a8f830df94`, m1n1 `cda8314d` and U-Boot `6c1d2d148020` were built and reboot-tested together on J713. Runtime versions, per-kernel DT import markers, NVMe root, Wi-Fi/SSH, retained MTP devices and zero kernel taint were verified.
- Bluetooth passed controller initialization, a 10-second LE discovery with received advertising reports, three HCI power cycles, and concurrent Wi-Fi gateway traffic. No pending radio DART faults or quarantine were observed. Pairing and individual Bluetooth profiles were not tested.
- Earlier integrated USB3 testing at `e9061708e7fd` negotiated ATC1 at 5 Gbit/s and completed two direct, read-only 512 MiB reads at 132/132 MB/s with matching checksums and no new USB errors. On the exact final basic boot, the drive was connected to ATC0: USB2 fallback passed two matching 512 MiB reads at 39 MB/s. A repeat ATC1 SuperSpeed test on the final tip is pending the physical port move; no drive writes or writable mounts were used.
- Linux Image/modules/DTBs built with `CONFIG_WERROR=y`; eight host selftest scripts, binding validation, inherited-PMGR policy checks and the module-form DART WERROR object check passed. Negative controls confirmed that the selftests detect the reviewed failure paths.
- Opus reviewed the design and added commits read-only. Findings were addressed; the final review found no blocking issues.

Earlier basic-series validation includes repeated physical display/keyboard/trackpad checks and a successful Omarchy → macOS → Omarchy round trip using one-time boot selection. NVRAM erase, rollover and interrupted updates remain unqualified. The existing `speakersafetyd` configuration failure remains outside this series.

Use the matching [m1n1 #35](https://github.com/aurora-silicon/m1n1/pull/35) and [U-Boot #7](https://github.com/aurora-silicon/u-boot/pull/7) calibration handoffs. The tested bundle preserves the legacy shared control DTB's USB2 topology and radio SID16 profile; the per-kernel DTB supplies USB3 topology and managed radio SIDs 1/2. The boot-source control DTB needs the ATC/Bluetooth aliases documented by those series. Check the selected OS source and completion markers: a rejected EFI DT fixup can leave the stub using the original firmware tree.

Qualification is limited to ATC1 at 5 Gbit/s; 10 Gbit/s, repeated hot-plugging and DP/HDMI output remain unqualified. Suspend is refused while the retained USB/radio resources are owned, and managed radio ownership blocks kexec/kdump for the boot. A Bluetooth transport failure requiring reset needs a platform reboot; automatic in-place reset/reprobe is refused on the high-window path. Manual Bluetooth unbind/module unload and fault injection/IRQ delivery have not been qualified. Speaker protection, keyboard backlight and complete firmware thermal-policy qualification remain gaps.


### Aurora-Silicon #367: drm/asahi, apple: add native J713/T8132 graphics
https://github.com/aurora-silicon/linux/pull/367 — state open, merged False; head `49c5d9994fec1b94cdce004bfa19c950c06b119e`.

Add native graphics for the J713/T8132 Apple M4 platform: a G16G firmware
backend in Rust Asahi and an internal-panel IOMFB backend in the common C Apple
DCP driver. This builds on the M4 basic bring-up series (#366), including its
USB3/Bluetooth support, and requires the matching m1n1/U-Boot handoff.

The GPU uses the existing Mesa UAPI and shared DRM/GEM, GPUVM, scheduler and
fence interfaces. The series adds private command memory per VM, tracked
firmware-visible lifetimes, bounded render-queue backpressure, retained display
DART ownership and fault handling, PMP votes, and GPU thermal-governor and
package-budget inputs. Initial scanout is cleared to black. Radio and display
DART ownership are kept independent. New files are dual licensed; existing
licences are preserved.

Validation on kernel `49c5d9994fec` with Mesa `91ac7e2cd86`:

- Full kernel, modules and device-tree build passes with WERROR enabled.
- 23 GPU CPU suites, 62 display groups, 8 targeted error-path groups, and the
  USB3/Bluetooth regression scripts pass, including their negative controls.
- Reboot-tested as `7.2.10-m4_asahi_rebase1`: both retained display DARTs
  admitted, their shared fault IRQ registered, and native KMS/Rust Asahi active.
  No masked-fault refusal or host failure was observed. Display, built-in keyboard
  and trackpad were confirmed working; no startup diagnostic pattern appeared.
- Native OpenGL 4.6 render, compute and geometry checks pass. Concurrent
  rendering/compute for 32 seconds and two blank/unblank cycles pass.
- Bluetooth LE discovery, three controller power cycles and concurrent Wi-Fi
  traffic pass on this same boot.
- The additional DCP error harness passes GCC and Clang: six production cases,
  the module API guard, five Kconfig cases and six runtime mutation controls.
  Ordinary built-in and modular DART configuration builds also pass.

Previous revision `5f8bc03dbefe` also passed VM/isolation/backpressure checks
and focused API tests: GL 80 passes with 6 known readback-tolerance failures;
Vulkan 101 passes with 22 unsupported cases. Those focused CTS results have
not been rerun on this rebased revision.

This is an experimental internal-panel profile. Rendering VMs pin about
0.7 GiB each, and an aborted firmware receipt disables that command class until
reboot. Physical reset, firmware telemetry freshness and full display power
policy remain unqualified. Suspend, hibernate and kexec are blocked while
native graphics owns DMA. DCP PMU/power-LUT diagnostics still prevent full
platform qualification. Keep the default strict IOMMU domains; administrative
switches to DMA-FQ are unqualified. These bounded tests do not establish full
conformance or full-platform qualification.


### Aurora-Silicon #370: arm64: idle: decide on the register-saving WFI before the first idle
https://github.com/aurora-silicon/linux/pull/370 — state open, merged False; head `34649b455f4a744002f6e46e33bab751790261eb`.

The M4-class cores lose x0-x15 and the FP/SIMD registers in WFI; integration/aurora already selects the
register-saving WFI for every M4-or-later part (midr_is_apple_m4_or_later()). It decides in an early_initcall,
though, and the boot CPU can idle in the window between rest_init() and the early initcalls. Decide from
smp_prepare_boot_cpu() instead. Static keys cannot be flipped that early, so the decision becomes a
__ro_after_init flag (one load per idle entry).

**Hardware tested on:** Apple MacBook Pro (16-inch, M4 Pro, 2024), J616s / T6040, macOS 26.x firmware, booted by our own loader with our private T6040 device tree.

**How tested:** A register self-test (5 WFIs on each of the 14 CPUs, woken by a 2 ms timer) saw x0-x15 and FP/SIMD change
on every CPU that slept. With the early decision the J616s boots and runs daily with idle=wfi. It closes the window that
was the likely cause of an intermittent boot hang before the framebuffer console came up; the hang did not recur, but
that is not proof.

**Not tested / limits:** The earlier decision also changes timing on the other M4-or-later SoCs, which we cannot test.

**Base:** `integration/aurora` (44d5afc79d). Built and checked there (aurora's defconfig, W=1 on every touched object, checkpatch --strict). Hardware testing was done on our daily tree, which is based on aurora-wip (Linux 7.1.12) and runs this code.

🤖 Generated with [Claude Code](https://claude.com/claude-code)

https://claude.ai/code/session_01K4TC3f2CpzFxhnEziL9wcg


### Aurora-Silicon #238: Add APIF MMIO transport and SPTM guest IOMMU providers
https://github.com/aurora-silicon/linux/pull/238 — state open, merged False; head `007b579dcd3ec1fa37ab8fe7598ece655a953ade`.

Introduce Aurora Platform Interface over Memory-Mapped I/O (APIF MMIO)
for a trusted Linux guest under Aura and SPTM. The transport forwards
native selectors, six arguments and opaque results unchanged; peripheral
policy stays in Linux.

- Add a synchronous version-2 transport with per-consumer buffers, atomic
  submission, prefix-completion validation and ordered client revocation.
- Add `apple-dart-apif` with stream grouping, retained-root adoption,
  shared IOVA allocation, mapping rollback and native table ownership.
  Translate DMA backing and page-list pointers before native calls;
  retain uncertain frames instead of attaching duplicate tables.
- Add `apple-sart-apif` through the existing SART consumer API, preserving
  raw MMIO behavior. Handle void MAP and status-returning UNMAP locally.
- Describe transport/providers in DT bindings and document the ABI.
  Explicit firmware metadata selects units, streams and aperture rules.
- Extend the existing Apple wait-state handling to captured T6050 CPU
  parts 0x064/0x065 and share the predicate with timed-delay avoidance.
  Preserve existing CPU ranges and the existing task TSO interface.

This series is based on `aurora-wip` (`c679c8a75`). It excludes GPU backend
changes, unrelated private-branch work, board DT enablement, probe-time
mapping self-tests and routine successful-call logging. A version-2 Aura
monitor and matching guest DT are required; existing boots are not switched
to these providers automatically.

Validation: driver code at `fcfe58107`, contact/ABI documentation at
`007b579dc`:

- Native AArch64 **Image build passed** with all APIF providers enabled,
  Clang 22 and GNU ld 2.46, using a minimal 16 KiB-page configuration.
- Production-function selftests passed for transport completion, DART
  ownership/list translation and SART return handling.
- All three binding schemas passed `dt-doc-validate`; whitespace checks
  passed; checkpatch reported no errors. GPL-2.0-only binding notices
  follow the project's licensing policy.
- LLD's full Image link failed with a section-address convergence error
  on this configuration; the GNU ld build completed successfully.

Hardware qualification of this cleaned version-2 integration is pending.
Unknown firmware SART grants are not advertised as inherited, and lost
native table completion requires recovery. No GPU changes or unqualified
hardware artifacts are deployed by this PR.

Non-GPU m5 integration still required:

- Convert the guest DT to version-2 transport phandles and provider
  properties, preserving DMA apertures, force masks and retained SIDs.
  Enable the APIF providers in the guest kernel configuration; the SART
  backend currently requires APPLE_SART=y.
- Port the resident-SPTM NVMe consumer: native queue setup and per-request
  TCB registration/invalidation, 16 KiB SART grants, pinned queue-page and
  RTKit handoff, and synchronous durability-preserving flush completion.
- Port the preinitialized PCIe host/MSI path and its controlled native
  port-reset/DART-power integration for the N1 path.
- Port the M5 PMP v2 consumer/protocol and its RTKit buffer-lifetime rules
  when enabling that DART-backed power-management device.

The version-2 page is now 0x61ff0000, outside the sixteen retained unit
aliases. The previously chosen 0x61f20000 is occupied by an existing
external-display DART alias on m5. The companion Aura change includes
production address-classification tests and passed all CI checks.

The internal optional EL1 register-probe harness is diagnostic and is
not required for DART/SART operation.


### Aurora-Silicon #241: nvme: apple: Add resident ANS support over native APIF
https://github.com/aurora-silicon/linux/pull/241 — state open, merged False; head `9ee6782ef9b2d76f68f4c7f5d2f21751f6483eb3`.

Resident ANS cannot use raw NVMMU programming or replace queue addresses pinned by a previous boot owner. Add `apple,nvme-apif` with Linux-owned native table-6 call construction, TCB/page-list translation, and four validated reserved queue pages.

Preserve the public driver's recovery, quarantine, controller lifetime and synchronous post-M4 flush fixes. A lost MAP response keeps the request live; completion or cancellation must confirm native UNMAP before releasing DMA backing. Retain backing after failed SART unmaps. No per-call success logging, payload copies or GPU changes.

This is the first PR in the non-GPU integration stack, based on `apif-mmio` (#238). Later PCIe, PMP and guest-wiring PRs will build on it.

The new profile requires a coherent identity DMA aperture and an explicitly quiesced RTKit handoff with four 16 KiB `no-map` queue reservations. It deliberately rejects the internal version-1 live-session handoff: CC.EN/RDY does not prove mailbox or retained-buffer ownership. Existing raw profiles preserve their adoption path. The boot producer must supply this documented contract before hardware testing.

Validation: native AArch64 `Image` build with Clang and GNU ld; binding schema validation; APIF host fault tests including queue commands without payload, void MAP results, failed UNMAP, lost replies, offset DMA rejection and the 257-page boundary. The source has been reviewed for ownership, teardown and publication provenance. Hardware boot, read/write/flush durability, reset and unbind qualification remain pending.

All commits are signed off by Dj <hey@djdev.me>.


## Mini-specific prior art

The 0xSero mini project explicitly reports no working installation. Its August status records one host-assisted Ethernet/SSH RAM boot, ANS mailbox faults for NVMe, and no proven physical HDMI modeset. These are dated contributor reports, not tests repeated here. https://github.com/0xSero/mac-mini-m4-linux

## Integration plan and acceptance gates

1. Confirm Mac model, macOS/firmware version, SSD capacity/free space, 1/10 Gb Ethernet and intended HDMI monitor. Retain macOS and Recovery. Record hardware inventory without changing partitions.
2. Choose an immutable kernel/m1n1/U-Boot/firmware/Mesa bundle. Start with #366 dependencies and separately evaluate #367; port board resources from J713 to J773g only with captured ADT evidence. Neither APIF #238 nor resident ANS #241 is a drop-in alternative: both require explicit boot-producer contracts and have pending hardware qualification.
3. Audit all touched DMA ownership, DART streams, reserved memory and PMGR domains. Verify early idle handling before the first CPU idle. Build the exact J773g DTB and 16 KiB kernel/modules; validate bindings and bootloader fixups.
4. First qualify RAM/initramfs boot with serial capture; then read-only NVMe enumeration and repeatable reads. Require controlled write/flush durability tests on disposable storage before internal-root use. A hypervisor boot must be labeled separately from standalone boot.
5. Qualify native mini HDMI at a recorded mode, USB keyboard/mouse, Ethernet and thermal behavior. Test cold boot, warm reboot and return to macOS/Recovery. Do not inherit Air panel, Wi-Fi or USB-port qualification.
6. Integrate the elementary root only after the board bundle passes. Preserve the repository’s Arch boot-host ownership and exact kernel/module matching described in KERNEL-FLOW.md; the factory image is a separate unqualified route. Gate any installer by board identity and verified supported firmware.
7. Test GPU/Mesa together, including memory pressure on 16 GB. #367 reports about 0.7 GiB pinned per rendering VM; measure available memory, multi-process desktop behavior and failed-firmware recovery. Suspend/kexec restrictions must be represented honestly.

## Audit limits and remaining work

This is a pinned ecosystem/readiness audit with targeted device-tree and proposal inspection. It is not a line-by-line audit of all kernels, a security certification, or a completed M4 port. Full changed-file review of the candidate series, kernel builds and physical J773g qualification remain required. Ubuntu default-branch absence of M4 files does not establish absence across its 12 branches; similarly generic mainline needs a targeted subtree/mailing-list check. No support ETA is established.
