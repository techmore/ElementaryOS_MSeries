# Gravity M4 mini integration — 2026-10-21

Gravity Linux's September 18 developer-alpha announcement reports working J773g
HDMI/DCP and GPU. This corrects the earlier audit's incomplete upstream scope.
https://gravitylinux.org/blog/early-alpha-m4-mac-mini/

The project flags limited testing, unreliable shutdown/reboot, and missing
suspend, USB-C display and Thunderbolt/USB4. These are project reports, not
local acceptance of elementary OS or this owner's 16 GB machine.

`research.json` now pins Gravity's kernel, Mesa, bootloader, U-Boot, packaging,
installer and image-description heads. Current development heads are not asserted
to be the exact September alpha release bundle. Package specs and release
provenance must be reconciled before building an elementary boot bundle.

The new gravity-mini source profile captures its J773g DT and complete include
closure. `build-dtb.py --source gravity-mini` verifies that capture and compiles
it, retaining diagnostics. Both Asahi and Gravity source versions read 7.1.13,
but their histories diverge: Gravity is 117 commits ahead and 73 behind the
pinned Asahi head. GitHub's comparison returns exactly 300 files and is capped;
it is not a complete patch series and must not be used as one.

Unlike the initial Asahi DT, Gravity's board adds GPU, native external display,
Ethernet and protected speaker resources. Its reserved ramoops address must be
checked against the actual 16 GB loader memory map and bootloader reservations;
source compilation alone does not establish that reservation is usable.

The J713-derived Kb2uka mini tester remains a separate unsuccessful path: issue
136 reports no HDMI after OS approval on October 20 and explicitly holds new
installations. Its source fixes do not supersede Gravity's independent support.
https://github.com/Kb2uka/Omarchy-M4-Native/issues/136

Next: obtain the complete Gravity source and packaging provenance, build its
kernel with a separate module release, reconcile its Mesa UAPI and firmware
handoff, and map the required services to elementary OS without replacing the
working J314S kernel or bootloader. No mini support is enabled in the installer.

## Packaging versus current kernel

The pinned packages sources.json selects kernel dea38a96aa86679d5e24da16b799030fe07ad2f6
and bootloader f64760b501214c749788f89620c078d8b39b0453. Those differ
from the development heads. Mesa is already the same pinned revision. The
current kernel is 13 commits ahead, with 14 changed files. The direct J773g
change corrects the SPMI SID 8 USB-PD select interrupt from 64 to 65. Other
changes include Air MTP and DCP support and shared DART/display changes, so
mini regression validation still matters. The current research build includes
that interrupt correction; it is not described as the original alpha build.

The full build applies Gravity config overlays after Asahi config. In particular
CONFIG_DRM_ASAHI_M4=m is required; the unmodified Asahi fragment leaves it off.
The build wrapper checks this resolved setting rather than treating any successful
Image build as an M4 graphics build. Its first full end-to-end run is pending.

## Reviewed firmware contract

At the pinned kernel, g16.rs validates `mBoot-18000.161.10`, the private VM
region, and five aligned non-overlapping loader-reserved regions before GPU
startup. dcp.c checks actual firmware `26.6.2`. The board's native HDMI
configuration uses the enabled primary `dcp` node with HDMI-A connector and
DPTX PHY 4; older dcpext0-only experiments must not substitute for this profile.
These source-level checks make a coherent loader/firmware bundle necessary.
They have not been exercised on the owner's mini.

## U-Boot branch correction

GravityLinux/u-boot defaults to main at a44f46af, an upstream maintenance
commit. The M4 patch tip recorded in packaging is instead
a2f6913694ff26908c16948af3f8372429782263 on gravity-alpha-20260925.
The selected research pin now uses that branch. Its final change supplies
J773g Wi-Fi calibration alongside Bluetooth, with reported full Fedora
EFI boot validation. These source reports are not local hardware tests.
Default branch discovery is retained as provenance, not used for the build.

## Owner's confirmed configuration

16 GB RAM, 1 TB SSD, 10 Gb Ethernet, macOS 27, HDMI output. SSD free space,
actual model/board identity, monitor mode and exact boot firmware remain unknown.
The reviewed mini prior art uses BCM57762 gigabit Ethernet; it cannot qualify
the optional 10 Gb controller. Initial defconfig leaves both AQTION and TIGON3
disabled. The elementary target overlay now enables both modules and config
gates require them. The live full build was reconfigured with this overlay; both required
NIC modules are required artifacts before payload packaging.

macOS 27 on the host does not identify firmware used by the separate Linux
boot stub. The exact GPU/DCP firmware gates still apply. Do not downgrade the
host or alter its firmware to infer compatibility. The macOS/Recovery round trip
needs qualification on this specific setup.

## Desktop userspace requirements reconciled

Gravity packages 711c2a1 installs ASAHI_MESA_DEBUG=nocompress for desktop
sessions and the login compositor. The private-prefix run-mesa launcher now
adds that flag, selects the sibling EGL/DRI/Vulkan libraries and runs only the
requested child process. It does not change the current session or global
loader configuration. The Vulkan manifest is relocated in a temporary directory
so an extracted payload can be inspected without installing it. --software
forces llvmpipe OpenGL; the Asahi Vulkan selection is still hardware-only.

The rust-speakersafetyd README is an older unpinned scaffold; the current
platform spec deliberately dropped its dependency because J773g speaker
protection is in sound/soc/apple/t8132/pcm.c. That driver mutes on amplifier
fault and DMA stall and applies a thermal model; its electrical parameters
are explicitly assumptions awaiting measurement. Source review does not
qualify physical speaker safety. Preserve the kernel controls and do not
enable the proposed unavailable daemon as a substitute. Matching UCM and
PipeWire routing remain target-image integration requirements.

Gravity also ships vendor sleep policy disabling suspend, hibernate, hybrid
sleep and suspend-then-hibernate. The candidate package-policy.py payload now stages that unchanged vendor
policy with a dependency on the distinct M4 kernel. Package and staged config
resolution checks pass; no host sleep settings changed. Factory image selection
and physical runtime qualification remain open.

## Newer Aurora integration comparison

Aurora integration/aurora was rechecked at 6210b28b00369a4b3bbb769dc3e8c5a1e31d2e87
on October 21. Its Makefile reads 7.3.0, but its J773g board source still only
adds firmware-framebuffer HDMI power domains, and its Asahi Kconfig has no
Gravity DRM_ASAHI_M4 option. This selected-file review does not claim a full
Aurora hardware-support audit. A newer version number alone does not replace
the matched Gravity kernel/bootloader/Mesa contract.

Recent Atlantic RX/TX ring cleanup fixes were checked: aq_ring_rx_deinit and
aq_ring_tx_deinit are byte-identical to Gravity's pinned source. They need no
duplicate backport. Other aq_ring.c differences include AQC113 PTP timestamp
handling; these are not evidence of an M4-specific 10 Gb fix or hardware pass.
See receipts/2026-10-21-aurora-ethernet-comparison.json.

## Required ARM64 packaging exports

The first full compile reached modpost and failed because modular appledrm
references four ARM64 helpers exported by Gravity's packaging layer, not its
kernel Git tree. The wrapper now applies unchanged packaging patches 0003-0006
from packages 711c2a1 with zero fuzz and verifies the resulting pageattr.c/flush.c
hashes. The kernel packager requires the same source contract. The incremental
retry passed modpost and linked vmlinux; final module generation remains running.
The retained .hyp.data non-allocatable-section warning is not suppressed. No
firmware gates or driver functionality were removed to obtain this result.

## Completed kernel artifact validation

The corrected Image/modules/DTBs build and separate Debian payload now pass.
The Image encodes ARM64/16 KiB, DTB identifies J773g, and all 1598 modules are
present. Checked GPU/display/NIC modules have matching vermagic and AArch64
ELF headers. Extracted-package Image hash and modprobe dry-run dependency
resolution pass. Package contents are confined to the distinct module release
and documentation, with no maintainer scripts or boot writes. Atlantic's
AQC113C alias is present; no owner controller/link test has run. See the build
and package receipts. These are build/package results, not boot acceptance.

## Combined candidate payload overlay

`stage-stack.py --kernel KERNEL_DEB --mesa MESA_DEB --policy POLICY_DEB
--output NEW_DIRECTORY` verifies all three package hashes against retained
receipts before extracting into a new root. It runs no package scripts or
installation commands. Combined-root module dependency, sleep config and
isolated llvmpipe render/readback checks pass. Invalid package hashes are
rejected before output creation. This overlay contains no base OS, initramfs,
EFI or firmware; base package dependencies and M4 hardware remain unqualified.
A complete factory image and graphical session activation are still required.

## Configured base userspace validation

A minimal resolute/elementary root was configured using mmdebstrap 1.5.7-3
in user/mount/PID namespaces with automatic subordinate IDs and map-root-user.
188 packages are configured; dpkg --audit passes. Revision 3 of the private
Mesa package now explicitly depends on libegl1, libgl1 and libvulkan1: the
configured-root render test exposed missing libEGL.so.1 in revision 2. The
revision 3 test passes with only the root's libraries and private read-only
proc mount. Its payload files/symlinks match revision 2 byte-for-byte.

For post-bootstrap APT operations, restore a temporary test resolver and
install the existing elementary PPA public key with an explicit signed-by
source entry; strict APT update then passes without disabling signatures.
The initial default subordinate mapping could not traverse private home; a
single-ID mapping could not represent package group 42. The successful mapping
is `unshare --user --map-auto --map-root-user --mount --pid --fork`, running
mmdebstrap in root mode inside that namespace. No home permissions changed.
This is minimal userspace acceptance, not a complete elementary desktop,
initramfs, EFI bundle, physical boot or M4 GPU qualification.

## Configured-root initramfs

`build-initramfs.py --root CONFIGURED_CANDIDATE_ROOT --output NEW_DIRECTORY`
builds in user/mount/PID namespaces and inspects the resulting archive. It
checks the pinned Image and module-local config hashes, confirms required
module contents and the early load list, and rejects the live / root. The
end-to-end run passes with 1090 members. Apple NVMe, PCIe, keyboard and Magic
Mouse modules are present and early-loaded. Ext4, USB HID and xHCI are built
into this kernel. Kernel package revision 2 adds config-RELEASE under the
module directory; all older payload bytes match. Policy revision 2 adds the
initramfs module list and initramfs-tools dependency. Neither package writes
boot files or has maintainer scripts.

The firmware warnings remain in the receipt, including the Apple ASMedia
controller file. Its applicability to the owner's actual USB topology is
unverified; other warnings name unrelated SoCs in the broad defconfig. No
proprietary blob was imported. Archive assembly does not prove storage reads,
USB input, display, firmware handoff or boot on the M4. Unsigned EFI assembly now passes as described below.

## Unsigned research EFI assembly

`build-efi.py --tools WORK_LOCAL_EFI_TOOLS --kernel VERIFIED_IMAGE
--initramfs VERIFIED_INITRAMFS_DIRECTORY --cmdline EXPLICIT_CMDLINE_FILE
--output NEW_DIRECTORY` assembles an unsigned ARM64 UKI. It verifies the
retained tool/stub/package hashes and kernel/initramfs hashes, refuses an
incomplete initramfs, and requires exactly one nonempty root= target. An
empty ukify configuration prevents host settings from entering the artifact.
It verifies exact embedded .linux/.initrd bytes and .cmdline/.uname/.osrel
metadata, and rejects .dtb/.dtbauto sections so the matched bootloader remains
responsible for the fixed-up handoff.

The full assembly test passes. Manual assembly and two wrapper runs produce
the same 64,882,176-byte artifact and SHA-256. The offline command line uses
root=LABEL=eos-m4-test; that is a test filesystem contract, not an observed
owner partition. No boot entry, EFI partition or installed loader changed.
This unsigned artifact is not an installation image or boot qualification:
matched firmware/loader handoff, actual root identity, full desktop support
and M4/macOS/Recovery tests remain outstanding.

### M4 bootloader packaging configuration correction

The earlier raw-source stage builds omitted Gravity packaging's required
`NO_DISPLAY` setting. Packaging `711c2a1` explicitly enables it in both stages
to leave the firmware framebuffer in place. The pinned source already supports
the equivalent `NO_DISPLAY=1` make option; `build-bootloader.py` now passes it,
verifies the generated `NO_DISPLAY` and stage-specific `CHAINLOADING` definitions,
and preserves those headers beside the binaries. A failed build leaves an
`INCOMPLETE` marker. No driver or firmware gate was removed.

Both stages rebuilt successfully. The revised stage-2 SHA-256 is
`33681f104822aaac4c6b77fab74d0d9da6f25b158b17ed283d1d9f03721760a4`;
stage 1 is `69aa13d28160821b78870a883500d744e97d10922b05287121288c41bf607acf`.
These supersede the earlier raw-source binaries for M4 configuration purposes;
the old receipts remain historical compile evidence. This is build parity with
the reviewed bring-up setting, not a display or boot test. Neither stage was
deployed or authorized. [Corrected build receipt](receipts/2026-10-21-gravity-bootloader-nodisplay.json).

### Matched J773g boot-chain assembly

`assemble-boot-chain.py --bootloader CORRECTED_STAGE_DIRECTORY --u-boot
VERIFIED_NODTB_BINARY --dtb VERIFIED_J773G_DTB --output NEW_DIRECTORY`
now verifies all inputs against the reviewed corrected stage/kernel/U-Boot
receipts, confirms the exact J773g compatible list, and assembles stage 2 +
board DTB + deterministic-metadata gzip(U-Boot). The ordering follows pinned
Gravity scripts `12418e5:update-m1n1`. Stage 1 remains a separate artifact.
No configuration overrides are appended.

Actual assembly passes with a 1,516,614-byte `boot.bin`, SHA-256
`304d55fb324865d9f2db056eb08cf2c8af204d952b337e757a6c8ad6401a1e22`.
Readback checks component boundaries and decompressed U-Boot bytes. The older
bootloader lacking NO_DISPLAY is rejected before output creation. This bundle
is research-only: source DTB firmware/memory fixups, authorized stage-1 handoff,
ESP placement/readback in the complete image and native boot remain unverified.
No ESP or macOS configuration was written.
[Assembly receipt](receipts/2026-10-21-research-boot-chain.json).

### M4 sysupdate image boot overlay

The M4-only sysupdate profile now includes `%C/mkosi.extra` and runs
`verify-boot-chain.chroot` before partition assembly. The hook requires the
reviewed bundle as a regular file at `/efi/m1n1/boot.bin` and checks its exact
SHA-256. The existing sysupdate ESP definition copies `/efi:/`, so this supplies
the stage-2 path in the image. Default and Fairydust profiles do not gain the
overlay or hook. The binary is intentionally ignored by Git and must be rebuilt
and explicitly staged for each disposable image checkout:

```sh
install -D -m 0644 /path/to/verified-chain/boot.bin \
  mkosi.images/sysupdate/mkosi.profiles/m4-mini/mkosi.extra/efi/m1n1/boot.bin
```

This worktree has the verified research bundle staged. A fresh checkout without
that bundle will fail the M4 image check rather than silently omit it. Real mkosi
profile resolution passes, and an isolated synthetic-root hook rehearsal passes
all four cases: verified bytes accepted; corrupted, missing and symlinked inputs
rejected. This is profile/hook validation, not complete factory image assembly,
ESP readback or authorized stage-1/native boot. The installer remains unsupported.
[Overlay receipt](receipts/2026-10-21-image-boot-overlay.json).

### Source-pinned U-Boot wrapper

`build-uboot.py --archive PINNED_CODELOAD_ARCHIVE --output NEW_DIRECTORY
--jobs 2` now replays the selected Gravity `a2f6913` M4 branch as a separate
candidate. It verifies the public archive SHA-256, uses the archive's source
timestamp through SOURCE_DATE_EPOCH and UTC, and supplies an explicit
`-gravity-a2f6913` version suffix. Source and build directories remain separate;
required ARM64/Apple/EFI settings and AArch64 ELF output are checked.

The complete native wrapper passes. Its resolved `.config` is byte-identical
to the earlier successful U-Boot configuration. Invalid source is rejected
before creating output. This is not a bit-for-bit reproduction claim: the
manual build embedded its wall-clock timestamp, and the new candidate has its
own retained artifact hashes. The reviewed assembled boot bundle still uses
the earlier verified U-Boot bytes; no golden references, ESP or boot settings
were changed. A separately validated candidate bundle is required before using
new U-Boot bytes in an image.
[Wrapper build receipt](receipts/2026-10-21-gravity-uboot-wrapper.json).

### Repeatable U-Boot and updated research boot reference

Two independent clean runs of the new U-Boot wrapper produced identical
`u-boot.bin`, `u-boot-nodtb.bin` and `.config` with the same compiler/environment.
This establishes local repeatability only, not cross-toolchain reproducibility.
[Two-build receipt](receipts/2026-10-21-uboot-repeatability.json).

The research assembler now selects that wrapper-built U-Boot. Its new bundle
SHA-256 is `00be0b4fe11fff44c68247e6484b747ee1b0ac91ce9078b084e8a7e6d235f808`.
The M4-only image hash hook and image-driver/ESP-fixture references now select
this explicit research revision; the rebuilt bytes are staged in this worktree.
Older manually timed U-Boot/bundle receipts remain historical. Existing
installer/hardware flags remain false; this is not release promotion or a
physical deployment. Complete mkosi profile isolation checks pass. The actual
new bundle also passes disposable GPT/FAT readback and corrupt-file rejection.
[New bundle](receipts/2026-10-21-repeatable-boot-chain.json),
[new ESP fixture](receipts/2026-10-21-repeatable-boot-esp.json).

### Shared scheduler lifetime/timeout follow-up remains open

Review of Aurora's earlier scheduler commits identifies additional shared
protocol differences beyond revision 3's initialization fix. Gravity jobs do
not hold a scheduler allocation reference after submission; entity cancellation
can use deferred work. Its timeout and run callbacks each create a mutable
reference to the complete Rust job. M4 returns NoDevice on timeout, while the
newer protocol explicitly retains ENODEV jobs and separates timeout state.
Gravity also calls stop before fini; Aurora's change to that sequence depends
on matching cancellation/parent-fence handling.

These source facts warrant an older-API lifetime/concurrency review, not a blind
copy of the newer G17 wrapper. They do not prove a reproduced native M4 fault.
Revision 3 remains an initialization-only candidate; even successful compilation
cannot close deferred dependency teardown, aliasing, late completion and
NoDevice retention gates. No scheduler-wide safety qualification is claimed.
The exact source hashes, upstream commit references and required follow-up
cases are retained in the [review receipt](receipts/2026-10-21-scheduler-lifetime-review.json).

Unpromoted scheduler allocation-owner candidate: Aurora 7ba04b6 is adapted
after revision-4 retention. Actual M4 driver/Rust core/C scheduler object
compilation passes. Seven generic ARM64 QEMU cases pass, including a new forced
entity-fini/deferred-dependency case that retains scheduler allocation after all
entity/handle owners drop, then releases it after cleanup. Removing only the
job-held allocation Arc fails the early-release assertion as expected.
`prepare-scheduler-kunit.py --experimental-owner` replays the pinned archive,
production compatibility, owner and test patches without fuzz; its scheduler
source is byte-identical to the seven-case positive run. See the four
`2026-10-21-scheduler-owner-*` receipts (object build, positive, negative, replay).
The candidate is stored under `gravity/experimental/owner` and is not selected
by normal kernel/package/image manifests. Module callback/code lifetime and
mutable callback aliasing still require review. No installed host component
changed. Baseline image run 39714779495 and initialization-only r3 kernel
39709872273 remain live; r4 kernel 39715540751 remains pending.

Unpromoted module/work lifetime follow-up to the owner split: Aurora c163a8d's
shared module pinning, DRM fops ownership and permanent work-disable changes
are adapted under `gravity/experimental/module`. Both actual M4 and legacy
Asahi driver objects, Rust core and both C scheduler objects compile. Eight
generic ARM64 QEMU cases pass; removing only permanent work disables fails
the new stable-state assertion. A fresh pinned-archive preparation reproduces
the exact tested scheduler source without fuzz via --experimental-module.
The fake backend has MODULE=None, so native/loadable module refcounts and
unload remain untested; the new case is not exhaustive completion-race stress.
The initial test compile failed on enum binding prefixes and was corrected
against generated bindings, preserving the assertion. Five module follow-up
receipts retain compile, positive/negative, failure and source replay evidence.
All 12 tracked upstream heads were rechecked; none changed from the previous
observation (upstream-head-refresh-2 receipt). Normal manifests remain revision
4; mutable callback aliasing remains open. Image 39714779495 and r3 kernel
39709872273 remain live; r4 kernel 39715540751 is pending.

The complete baseline r2 mkosi image graph succeeded in run 39714779495
(source 0b2afea8). Hosted checks cover the 1,650-package base and 1,741-package
live roots, desktop libraries/schemas/dependencies, Mesa software rendering
and /usr retention, actual sysupdate ESP bundle bytes and valid GPT export.
The raw image is 17,482,960,896 bytes; the 8.16 GB research artifact is still
downloading in native session 57043. Local raw verification is not yet claimed.
This is not ISO assembly, graphical login, installer import, native boot or
scheduler-fixed image qualification: reviewed image inputs remain r2.

The unpromoted alias candidate adapts Aurora 0f89327's independent TimeoutData
contract after owner/module layers. Actual M4 and legacy driver/Rust/C objects
compile, and nine generic ARM64 QEMU cases pass, including a timeout callback
forced to execute while run still mutates submission state. Fresh source replay
is byte-identical to the tested scheduler. This is not exhaustive Rust memory-
model or actual module-unload proof. See scheduler-alias receipts and
--experimental-alias. Final cancellation/accounting review remains open.
Revision-4 full kernel run 39715540751 remains live.

2026-10-22 follow-up: the downloaded baseline image is now locally verified.
All six compressed raw checksums pass; decompressed source SHA256 f8eb8865bba9
afad8064ec27ddeaa69e561e8ab560d9db7850daadb489b2f152 (17,482,960,896 bytes)
matches the hosted record. GPT headers/entries/geometry/GUIDs/labels/attributes
match, ESP boot.bin matches the reviewed hosted bundle, and active data/hash
payloads verify against the signed root hash. The embedded certificate's
fingerprint and CMS signature verify; this establishes internal consistency,
not external signer trust or Apple enrollment. All eight corresponding-source
archives match reviewed component/mkosi hashes. Future image builds now retain
actual active-verity verification and source checksums. Local ESP validation
used the already extracted sfdisk/mtools without installing host packages.

The complete experimental scheduler candidate now adds matched final
cancellation/accounting and removal of reset-style stop from finalization.
Actual M4/legacy driver/Rust/C objects compile and twelve generic ARM64 QEMU
cases pass, including credits/score cleanup and preservation of completed EIO.
The isolated pre-fix negative fails score==0 cleanly; earlier helper-panic and
broad-negative timeout attempts are retained separately as superseded harness
evidence. Fresh --experimental-teardown preparation matches the tested source.
Normal manifests remain research kernel revision 4; a full combined candidate
build and actual module-unload exercise remain open. Revision-4 full build
39715540751 is still live. ISO, installer import and native M4 remain unqualified.
