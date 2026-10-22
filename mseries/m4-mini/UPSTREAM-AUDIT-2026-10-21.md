# M4 Mac mini: Gravity Linux and upstream audit

**Conclusion:** Gravity has a substantive native J773g developer-alpha port with
project-reported HDMI/DCP and GPU operation. It is the strongest directly relevant
public stack found in this audit. It does not establish that elementary OS or the
owner's 16 GB / 1 TB / 10 Gb Ethernet / macOS 27 / HDMI configuration is qualified.

Current elementary preparation: the opt-in M4 profile selects the matched
kernel, Mesa revision 4 and temporary policy. A 1,626-package research desktop
root passes package, library, schema, software-rendering and Casper initramfs
checks. LightDM selects Pantheon Wayland; unqualified graphical installer
packages are omitted. The actual factory base build has passed; live/sysupdate assembly remains open. No complete
factory image, graphical login, native M4 operation or dual boot has passed.

The audit inspected source, branch history, packaging provenance and selected
production tests. Compilation and synthetic tests are distinguished from physical
hardware results throughout. No kernel, graphics library, partition or bootloader
was installed on the owner's system.

| Component | Selected source | Finding |
|---|---|---|
| Kernel | GravityLinux/linux, gravity-m4, `4fc326f6c25ccceb7515e2635c22e01fde5d3bac` | Linux 7.1.13 with M4-specific storage, display, GPU, radio and speaker changes |
| Mesa | GravityLinux/mesa, `87ac51d411f0e58a9433567ec2666f457be89e1d` | Asahi OpenGL/Vulkan code; UAPI header matches the selected kernel byte for byte |
| Bootloader | GravityLinux/bootloader, `f02d4a52017915febb222539636b5b025a70407a` | Both raw stages compile; development head differs from packaging pin |
| U-Boot | GravityLinux/u-boot, gravity-alpha-20260925, `a2f6913694ff26908c16948af3f8372429782263` | Native apple_m1 build passes; includes NVMe and per-radio calibration handoff |
| Packaging | GravityLinux/packages, `711c2a110416d28010ccdd118b83111776bff207` | Fedora 44 packaging, source lock and upstream attribution |
| Installer | GravityLinux/installer, `6420623289fe7544cb8589b658355e57f0290fcc` | Explicit J773gap admission; separate 26.6.2 firmware stub |
| Image | GravityLinux/kiwi-descriptions, `07bf52cb2866069c072eb03a8f23af9839d0397c` | Fedora image descriptions; not an elementary OS image |
| Runtime scripts | GravityLinux/scripts, `12418e50125a72749a75917db578db55ea42704c` | Fedora/Asahi integration layer, also selected by packaging |

The full pins and local receipts live beside this report in research.json and
receipts/. Development heads are not represented as the exact September alpha
binary bundle.

Gravity's [September alpha announcement](https://gravitylinux.org/blog/early-alpha-m4-mac-mini/)
reports HDMI/DCP and GPU support. It calls out limited testing, unreliable
shutdown/reboot, and missing suspend, USB-C display and Thunderbolt/USB4. Its
OpenGL/GLES claims do not establish complete Vulkan conformance.

The [packaging provenance](https://github.com/GravityLinux/packages/blob/711c2a110416d28010ccdd118b83111776bff207/UPSTREAM.md)
traces the kernel source packaging to Asahi, Mesa packaging to Fedora, bootloader
to m1n1, and platform/remix integration to Fedora Asahi. The declared Asahi base
is `3988dac1664c05fa7c8310fcad8eee10428b5f43`. Gravity's current branch is 70
commits ahead of it; the complete GitHub comparison has 124 changed files.

Against the newer Asahi snapshot `94fb23346d522edf53722357c426a3e58030beea`,
Gravity's graph is 117 ahead and 73 behind. That graph's capped comparison is not
a complete endpoint diff. Comparing the two complete canonical source archives
instead found 104 modified, 34 added and one removed file, across 93,960 and
93,993 non-directory entries respectively. This is a complete content inventory,
not a semantic review of every changed line. Much of the delta is Apple DRM/GPU,
T8132 device trees, audio and firmware integration. There is no basis to treat
this branch as generic mainline Linux support, or to assume it includes every
newer Asahi fix. Inherited v7.3 tags do not change the M4 branch's 7.1.13 version.

The [package source locks](https://github.com/GravityLinux/packages/blob/711c2a110416d28010ccdd118b83111776bff207/sources.json)
select kernel `dea38a96aa86679d5e24da16b799030fe07ad2f6`, rather than the current
development head. The latter adds 13 commits across 14 files, including the mini's
SPMI SID 8 USB-PD select-IRQ correction from 64 to 65, plus shared Air MTP/DCP
changes. Those Air changes require mini regression checks. Packaging also selects
an older bootloader revision. Default U-Boot main is upstream code; the correct
Gravity patch branch is gravity-alpha-20260925.

| Feature | Public/source evidence | Meaning for this owner's mini |
|---|---|---|
| Internal NVMe | Dedicated T8132 ANS2 queue-register handling and enabled board SSD; alpha reports operation | Stronger than older failed diagnostics; no local durability or standalone boot test |
| HDMI | Native 26.6 DCP implementation and J773g HDMI-A/PHY configuration; alpha report | Credible working path, but monitor/mode and owner's hardware untested |
| GPU | Separate asahi_m4 driver and matching Mesa UAPI | Driver must be enabled explicitly; firmware/loader contract remains mandatory |
| Wi-Fi/BT | Sakhalin firmware plus per-radio factory calibration | Common firmware copy alone cannot replace MAC-bound calibration |
| 10 Gb Ethernet | AQtion driver is available; no specific CTO-mini physical pass found | Controller identity, PCIe/DART route, link and sustained traffic remain open |
| Speaker | Kernel-protected J773g PCM/amp/thermal implementation | Different from legacy userspace safety profiles; no local acoustic/thermal qualification |
| Reboot/suspend/TB | Published alpha limitations | Not suitable to promise normal desktop lifecycle behavior yet |
| macOS 27 | Installer source checks a minimum host version and selects a separate 26.6.2 stub | Host version alone is not a blocker or proof of compatible boot firmware |

The GPU driver checks `mBoot-18000.161.10`, its private VM region and five
aligned, non-overlapping reserved regions. DCP requires actual firmware 26.6.2.
The source GPU DT intentionally starts disabled until loader fixups provide the
handoff. These checks must remain intact. The installer selection method accepted
a synthetic macOS 27.0/J773g fixture and chose 26.6.2. Apple's referenced IPSW
answered HTTP 200 to HEAD; that is availability evidence only, not current Apple
signing eligibility or a successful installation.

The U-Boot patch stack includes T8132 memory/NVMe support, RTKit servicing during
controller waits, reset handling, and calibration injection. Wi-Fi WCAL and
Bluetooth BTBF records are bound to the original radio address. U-Boot accepts
bounded BLOB files on the matching ESP and preserves calibration already supplied
in the DT. Reusing another Mac's calibration is not a substitute for extraction
on the target machine. No proprietary blobs were imported here.

The kernel's NVMe delta includes separate T8132 IO queue registers, avoiding the
legacy register interpretation at the same offset. The PCIe delta introduces
port power-controller setup before initialization. DART adds validated canonical
SID remapping, rejects invalid/chained maps, and refuses remapping locked DARTs.
These are source findings; they do not prove fault recovery or isolation on the
owner's hardware.

The upstream DCP AFK fragmentation boundary test passed normally and under address
and undefined-behavior sanitizers. It covers bounds, ordering, truncation,
sequence wrap and completion, not physical HDMI. Both raw m1n1 stages and selected
U-Boot compile. Gravity Mesa compilation, five selected upstream test groups (366 compiler,
10 launcher and five geometry cases, plus two disassembler groups), and private
DESTDIR staging now pass. Isolated software OpenGL creation/render/readback also
passes using llvmpipe. This is userspace loading evidence, not an M4 GPU or
Vulkan device test. The full M4 kernel build remains running. The secondary
Asahi comparison build was stopped to conserve shared filesystem capacity,
retaining its sources/config/logs; it has no successful full-build result.

Omarchy MX's [Stable kernel config](https://github.com/maralcbr/omarchy-pkgs/blob/7e2f6cfec1b3e412ad4fd6ed9611be275a246b30/pkgbuilds/linux-aurora-stable/config#L2702)
and its RC/Edge equivalents enable AQTION=m and TIGON3=m. The owner's lead is
supported at the driver-configuration level. Its [current installer scope](https://github.com/maralcbr/omarchy-mx-mac/blob/72f1906722fd042a54f1e1973610f62dd019531f/README.md)
explicitly admits M1/M2 and excludes M4, so that evidence cannot qualify an M4
10 Gb mini. The elementary candidate now requires both NIC modules too.

The older 0xSero mini diagnostics and J713-derived Omarchy tester remain useful
prior art, but their published NVMe/HDMI failures are not the ceiling of current
Gravity support. Similarly, the official Asahi M4 matrix describes that project's
integration status rather than all downstream forks.

For elementary OS, the appropriate next step is a matched, separately packaged
candidate: kernel/modules/DTB, raw loader stages, U-Boot, Mesa and machine-local
firmware. The draft preparation lane preserves the installed J314S stack. It adds
J773g BCM4388 provisioning, signature checks and firmware fixtures, with explicit
AQtion/tg3 build gates. Hardware boot, 10 Gb traffic, thermal behavior, HDMI,
shutdown/reboot and macOS/Recovery round trips are still required before calling
this setup ready for dual boot.

`package-mesa.py --stage STAGE --source SOURCE --archive PINNED_ARCHIVE
--validation BUILD_RECEIPT --output NEW_DIRECTORY` verifies the five-group
validation receipt, all four graphics library hashes and corresponding source
archive before building an arm64 Debian payload. Packaging passed; the 98 payload
members are confined to the private prefix and documentation, with no maintainer
scripts. An extracted-package llvmpipe EGL render/readback test passed. Missing
manifest and mismatched library hashes were rejected before output creation.
This package requires the build host ABI (including libc6 >= 2.43), so rebuild
against the intended image ABI before distribution. Dependency scanner warnings
are retained in the receipt; no M4 hardware or Vulkan qualification is implied.

The isolated Mesa launcher now preserves Gravity's `nocompress` session flag.
Its extracted-package software rendering and private path/manifest lifecycle
checks passed. Current platform packaging dropped the proposed speakersafetyd
dependency in favor of J773g kernel protection; the kernel explicitly describes
electrical parameters as assumptions awaiting measurement. Physical speaker
safety remains unqualified. Gravity also blocks system sleep through vendor
policy; equivalent M4 image policy and matched UCM routing remain open.

The candidate M4 sleep-policy Debian package now builds with six unchanged
Gravity vendor configuration files, a dependency on the distinct M4 kernel and
no maintainer scripts. Staged systemd config resolution and payload hash checks
pass. It has not been installed or enabled in the factory image. Full current
Asahi UCM/audio tree inventory finds no J773g/t8132-specific profile paths;
actual mini card discovery/routing still needs qualification.

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

Base-image preflight: an empty-status APT simulation resolves the three local
packages and minimal boot userspace (164 packages) against resolute plus the
configured elementary patches. This initial preflight was followed by the
configured-root acceptance described below. The actual kernel is a direct ARM64 EFI input
with zero relocation directory, and the factory UKI preparer leaves it
unchanged. Six preparer tests pass. Initramfs and research EFI generation
subsequently passed the scoped checks described below.

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

## Mainline and owner qualification boundary

Current mainline torvalds/linux 4df4d2a577db2d3d57b888bcfb1206fc74661d16
reports 7.3.0 in its Makefile. At that exact head the J773g DT path returns
404, DRM Makefile has no Apple/Asahi entries, and Apple NVMe has no
apple,t8132-nvme-ans2 match. Gravity contains the latter match. This selected
source comparison does not claim a full mainline semantic audit. Gravity's
selected kernel/Mesa heads were rechecked and remain unchanged.

See QUALIFICATION.md for evidence versus outstanding native gates. The new
macos-inventory.sh collects filtered read-only host facts; macOS execution
is not yet tested. No source/build result qualifies the owner's 10 Gb variant,
16 GB loader map, complete desktop or macOS/Recovery round trip.

## Final loader memory capture check

`check-memory-handoff.py --dtb FINAL_LOADER_DTB` checks J773g declared RAM
ranges and ramoops bounds/collisions. It rejects zero-size source placeholders,
invalid RAM alignment, overlapping RAM, an out-of-RAM ramoops range and
collision with another reservation. Six regression tests pass. The retained
unfixed source DT is rejected. A synthetic 16 GB declared map passes, but
that does not establish the owner's physical memory map. Unrelated reserved
regions need not have RAM page alignment; this is not a complete firmware
reservation validator. GPU/DCP source gates remain separate and mandatory.

Factory integration remains unfinished: the default base profile selects
linux-image-generic, while the opt-in M4 profile selects the research kernel. The standalone M4 package/EFI tests do not
constitute an enabled M4 factory installer or complete desktop image.

## Opt-in factory package selection

The new `m4-mini` mkosi profile selects exact kernel revision 2, Mesa revision 4
and policy revision 2 packages in the base image, and adds Apple NVMe/PCIe/
keyboard/Magic Mouse modules to the live ISO initrd settings. It asserts arm64
and rejects combination with the incompatible Fairydust stack. Normal builds
retain their generic kernel and package sets. Supply the three verified local
Debian packages in a directory passed to `--package-directory`; mkosi converts
that directory into a local package repository.

For configuration review, run `mkosi --profile=m4-mini --architecture=arm64
--package-directory=/path/to/candidate-debs --image-version=20261021 summary`.
The pinned mkosi 28~devel parser passes default/M4/Fairydust and negative
architecture/conflict tests using test-mkosi-profile.py --mkosi-source SOURCE.
This establishes configuration selection only. No complete M4 ISO has built;
full desktop and firmware handoff remain open; private graphics activation
is now separately tested below.
Installer/hardware qualification flags remain false.

## M4-only graphics activation

The opt-in profile includes an extra tree and a chroot post-install hook that
refreshes the target root's loader cache. Ordinary GLVND applications select
the private EGL/GLX/GBM libraries; a Vulkan manifest points to the matched
private driver. User units and LightDM children receive Gravity's nocompress
workaround. Default builds omit these files and this hook.

Real mkosi parser tests verify selection exactly once. The hook was replayed
inside the configured minimal ARM64 root, followed by EGL software rendering
without launcher, LD_LIBRARY_PATH or vendor/DRI overrides: Mesa 26.3.0-devel
loaded and pixel readback passed. The user environment generator emitted the
workaround. This does not qualify hardware acceleration, Vulkan conformance,
a complete elementary session, or a full factory image. The owner's M4 is
unavailable; physical firmware, HDMI, memory and 10 Gb checks remain open.

[Activation receipt](receipts/2026-10-21-factory-graphics.json).

## Installed-image retention correction

The installed sysupdate artifact copies only `/usr`. Mesa package revision 4
therefore stores all private graphics bytes in `/usr/lib/elementary-m4-gravity1`.
It retains compatibility with the compiled `/opt` prefix through a symlink and
vendor tmpfiles configuration. The M4 profile uses canonical `/usr` paths for
ldconfig and the global Vulkan manifest. The factory hook removes only an
empty obsolete prefix directory that dpkg may preserve during upgrade.

The r3-to-r4 upgrade passes in the isolated configured root with a clean dpkg
audit. `test-factory-retention.py --root ROOT --smoke COMPILED_EGL_TEST` masks
`/opt` with empty tmpfs and makes `/usr` read-only: tmpfiles restoration and
both unwrapped and launcher software rendering pass with Mesa 26.3. All
original staged Mesa files/symlinks retain their contents. This is scoped
retention evidence, not a complete installed image or desktop boot.

The M4 live profile overrides the disk-erasing `elementary-install` command
with a refusal because it cannot preserve macOS. The graphical installer
session is not covered by this command override; the later M4 live-profile
change below omits its packages entirely. Do not
use this research image for installation. A partition-preserving Apple adapter
is still required. The separate M4 live hook described below now supplies the `/boot` kernel
copy expected by `assemble-iso.sh`; full ISO integration remains open.

[Current Mesa package receipt](receipts/2026-10-21-gravity-mesa-package-r4.json).

## Live-kernel staging and installed storage drivers

The M4 live profile now selects a chroot post-install hook that checks for a
single module tree, verifies the pinned Image/config hashes, stages the kernel
in `/boot`, and creates or updates its initramfs. This satisfies the kernel
path used by `assemble-iso.sh`; the standalone kernel package still has no
host boot hooks. The M4 sysupdate profile adds Apple NVMe and PCIe drivers to
the existing installed-image initrd settings. Default builds omit both changes.

`test-live-kernel.py --root ROOT --receipt NEW_JSON` replays the real hook in
an isolated configured root with Casper installed. The retained run passes
pinned kernel identity, Casper live scripts, overlayfs and early Apple storage
and input checks. The initial creation path also passed before adding Casper;
the final Casper-qualified replay covers the update path. Missing firmware
warnings remain visible, including the Apple ASMedia image. No full factory
ISO, installed desktop or physical boot has passed. Gravity kernel/Mesa and
Asahi kernel heads were rechecked and still match the recorded revisions.

[Live staging receipt](receipts/2026-10-21-live-kernel-staging.json).

## Full elementary dependency closure

The combined factory invocation uses both `--profile=daily` and
`--profile=m4-mini`. Real mkosi parser checks verify that daily/common
repository trees are available through SandboxTrees before package install.
The full elementary desktop/minimal/standard/live/installer-session dependency
plan resolves with 1,411 additions and no additional kernel image. The reused
test root first required aligning eleven newer Ubuntu systemd packages with
the elementary package family; pin 999 alone does not downgrade existing
packages. Factory ordering already supplies these preferences early.

That installation subsequently configured with the board-specific fixes below;
dependency closure alone does not establish a working graphical session. Service
starts are blocked in the target root, and no running-host packages change.
[Dependency receipt](receipts/2026-10-21-desktop-resolution.json).

## Configured elementary desktop

The first configured full desktop root had 1,628 packages. The initial install
failed in the foreign X13s initramfs firmware hook. M4's live profile therefore
selects `elementary-live` common dependencies directly, without the X13s/X1E
board packages; ordinary builds retain their metapackage. This failure was in
the firmware-light test root, not proof that every generic factory root fails.

After removing those board packages, configuration passes.
`check-desktop-root.py --root ROOT --receipt NEW_JSON` verifies package audit,
dependencies, Gala/Wingpanel/LightDM libraries, strict schemas and Pantheon
session files. Both Mesa rendering modes and the full-desktop Casper kernel
hook replay pass too. Firmware/root-device warnings remain recorded. No
graphical session or native GPU/HDMI operation was tested.

The generic live installer package sets LightDM's default to the installer session;
its user unit launches the graphical installer directly. The command-line
refusal does not disable that path. Installer admission remains false until
the live session and Apple partition-preserving workflow are integrated.

[Configured-desktop receipt](receipts/2026-10-21-configured-desktop.json).

## Research live-session selection

The M4 live profile now omits the graphical installer and installer-session
packages. Generic images retain them through the `!m4-mini` live drop-in. A
profile-only LightDM configuration selects `pantheon-wayland` for normal login
and autologin; Casper supplies the live user. This removes the unqualified
GUI-installer path, while the command-line installer continues to refuse
whole-disk erasure. It does not implement the desired Apple dual-boot adapter.

The resulting 1,626-package research root passes package/library/schema checks.
`lightdm --show-config` confirms both session settings, and the installer binary,
session file and user service are absent. Mesa software rendering with persistent
`/usr` and the Casper initramfs hook pass after the package changes. No graphical
login or native GPU/HDMI operation was tested. A fresh empty-status APT closure of the actual profile public package names
also excludes the installer/session and foreign board packages, including
transitive recommendations. Private M4 packages are validated separately.
The actual factory base build has passed; complete live/sysupdate assembly remains open.

[Research-session receipt](receipts/2026-10-21-research-session.json).

## Actual factory base artifact

The native mkosi base-only build exited successfully and produced a 6.6G
directory with 1,650 configured packages. Package/dependency, desktop-library,
schema/session-file checks pass on that actual output. Image/config/J773g DTB
hashes, 1,598 module files and GPU/display/NIC module dependency checks match
the validated package. Both Mesa rendering modes pass with read-only `/usr`
and initially empty `/opt`. A base directory is not a bootable live/sysupdate
image or evidence of graphical login, native GPU/HDMI or dual boot.

`check-desktop-root.py --kind=factory-base --root ROOT --receipt NEW_JSON`
checks the base's own contract without requiring live-only Casper/autologin.
The default mode still checks the research live session. Both inspection
runners support explicit `--id-map=single` when subordinate-ID helpers are
blocked. The refreshed runner has `NoNewPrivs=1`; full-ID mapping is currently
unavailable. Single mapping is not used to claim full image-build ownership.

The complete pinned Gravity installer archive matches the earlier selected
source captures. All 26 upstream fixture/mock tests pass. Its raw partition
images must fit destinations and have 4 KiB-aligned sizes; EFI trees and
firmware/installer-data can be copied to the new ESP. An elementary DPS/verity
partition export, writable root, release metadata and native acceptance are
still required. No macOS disk write or Recovery check was performed.

[Factory base receipt](receipts/2026-10-21-factory-base.json),
[installer offline receipt](receipts/2026-10-21-installer-offline.json).

## Installer partition metadata contract

`audit-installer-contract.py --archive PINNED_TAR --receipt NEW_JSON` exercises
the pinned Gravity code with mocked disk methods and in-memory ZIP fixtures.
It verifies exact ARM64 `/usr`/verity type selection, partition chaining and
expansion, and rejection of unaligned/oversized raw images before device open.
No native disk command runs. Actual macOS reporting of the custom GUIDs remains
unmeasured; the fixtures deliberately model exact GUID strings.

The audit also demonstrates a remaining adapter gap: this partition path sends
only type, `%noformat%` label and size to diskutil. It does not restore exported
GPT labels, unique partition UUIDs or attributes. This matters to the current
elementary label filters and verity/spare-slot layout. The DPS specifies UUID
relationships for verity discovery and a no-auto flag for excluded partitions.
[Discoverable Partitions Specification](https://uapi-group.org/specifications/specs/discoverable_partitions_specification/).

A direct raw-image reuse therefore has no verified path to satisfy the complete
elementary GPT contract. The audit reports support/admission **false**; it is
not an installer or owner disk plan. A metadata-preserving adapter, real split
artifacts, ESP handoff and native macOS/Recovery acceptance remain required.
Gravity, Asahi, Aurora and mainline heads were rechecked and remain unchanged.

[Partition-contract receipt](receipts/2026-10-21-installer-partition-contract.json).

## Metadata-preserving export preparation

On Linux, run `python3 mseries/m4-mini/export-partitions.py --image IMAGE.raw
--output NEW_DIRECTORY` to export validated source GPT metadata. Repeated
`--extract INDEX` options additionally extract selected partition payloads.
The input must be a regular file, not a symlink or device. Both GPT copies and
their CRCs/ranges must agree; duplicate UUIDs and overlapping entries are
rejected. The manifest retains exact type/unique GUIDs, labels, all attribute
bits, geometry and hashes, alongside original header/table bytes.

These are **source-image** metadata, not a destination disk restore plan. An
Apple dual-boot importer must allocate authorized new ranges while preserving
existing macOS entries. It must not overwrite the Mac's whole GPT with these
headers. Destination geometry/disk identity require separate validation.

Six tests pass on sgdisk-produced 512-byte and converted synthetic 4096-byte
fixtures, payload/source integrity, corruption/overlap and input rejection.
The suite is wired into hardware-support CI; remote CI success is not claimed.
No complete M4 sysupdate image was available for a real export. This tool does
not implement native import or make a bundle installable. Full assembly still
requires subordinate-ID mapping, currently blocked by the execution runner's
NoNewPrivs setting. Physical M4/Recovery/HDMI/10 Gb checks remain open.

[Exporter receipt](receipts/2026-10-21-partition-export.json).

## Hosted kernel-only research build

The existing artifact-only OS 9 workflow now accepts `m4_kernel_only=true`
with both Fairydust inputs false. It builds the immutable Gravity source on
a hosted ARM runner with Rust 1.99.0/matched library sources and LLVM 21, then
packages and inspects the candidate. Ordinary image and Fairydust jobs are
skipped for this selection. Artifacts retain corresponding source, build
recipes/configuration, toolchain records and checksums; no release is published.

`check-kernel-package.py` ties the candidate to its own build/package receipts
and checks kernel/DTB identity, 16 KiB pages, module count/architecture/release,
dependencies and absence of package hooks. Local r2 inspection passes. This
does not promote a fresh CI binary into factory pins or qualify M4 hardware.
Candidate hashes can differ across build environments. Full matched Mesa/boot
chain and image assembly remain separate requirements.

[Hosted preflight](receipts/2026-10-21-hosted-kernel-preflight.json).

Hosted kernel-only run [39698975678](https://github.com/techmore/ElementaryOS_MSeries/actions/runs/39698975678)
was dispatched at source `2798237e`. The initial snapshot confirms the M4 job
is active and ordinary/Fairydust jobs are skipped. No hosted compile/package
result is claimed yet; follow the live run before retrying.
[Dispatch snapshot](receipts/2026-10-21-hosted-kernel-run.json).

## Hosted Mesa-only research build

`m4_userspace_only=true` (other research/Fairydust flags false) selects a
separate artifact-only hosted Mesa job. Its concurrency group allows the
already-running kernel job to continue. It uses the pinned source, explicit
Asahi/llvmpipe/OpenGL/Vulkan/X11/Wayland/LLVM options, five upstream test groups
and software smoke. Source, recipes, toolchain/test records and unpromoted
packages are retained as CI artifacts. No image or release is published.

The builder checks the selected kernel/Mesa DRM UAPI hash.
`check-mesa-package.py` ties fresh package/library bytes to their build receipts,
checks persistent layout/no hooks, and runs the packaged private launcher with
the software test. Local r4 passes. These checks do not establish native M4
GPU operation, Vulkan conformance or factory promotion. Hosted dispatch/result
remains separate from this preflight.

[Hosted Mesa preflight](receipts/2026-10-21-hosted-mesa-preflight.json).

Hosted Mesa-only run [39700250329](https://github.com/techmore/ElementaryOS_MSeries/actions/runs/39700250329)
was dispatched at source `eece8d5f`; it later failed during setup. Its
image/kernel/Fairydust jobs were skipped.
Kernel run `39698975678` remains active independently. No hosted Mesa compilation result is claimed; corrected setup is described below. [Dispatch snapshot](receipts/2026-10-21-hosted-mesa-run.json).

## Candidate image inputs and Mesa setup correction

`prepare-image-inputs.py` accepts trusted kernel/Mesa packages with their build
and packaging receipts plus the compiled software test. It invokes the current
package checkers, retains matching source archives and receipts, builds the
temporary M4 policy, and rechecks copied bytes. Its output contains `packages/`,
`records/`, `candidate.json` and a candidate-only live-kernel hash patch. It does
not apply that patch or alter the checked-in factory package/hash references.
The patch keeps checksum validation and changes only hashes to a validated
component. Use it only in an explicitly selected disposable candidate build.

The actual local r2/r4 rehearsal passes; its hashes need no patch. Three
patch-format checks pass for no-op, differing-hash fixture and unknown baseline.
This is not acceptance of fresh hosted candidates or a completed image.

The first two hosted Mesa attempts stopped in setup for omitted split Wayland
backend and X11 VidMode development packages. The corrected hosted dependency
list now explicitly covers all 18 packages in the independent successful local
capture, enforced by a regression test. No source, driver/platform selection or
upstream tests were disabled. The original kernel build remains separate.

[Image-input preflight](receipts/2026-10-21-image-inputs-preflight.json),
[second setup failure](receipts/2026-10-21-hosted-mesa-failure-2.json).

### Corrected hosted Mesa retry

Run [39702973626](https://github.com/techmore/ElementaryOS_MSeries/actions/runs/39702973626)
uses source `77f9561ce40e0e1d59b03d720a3c4efddf856441`, including the complete
captured development dependency list. Its dispatch snapshot is retained in
[the retry receipt](receipts/2026-10-21-hosted-mesa-retry-3.json). The dependency
regression and three image-input patch tests pass locally. The earlier kernel
run `39698975678` remains independently active at this snapshot. Neither run
has a successful hosted result yet. Owner hardware is unavailable; continue
public-source preparation without claiming HDMI, 10 Gb traffic, or dual-boot
qualification.

### Latest public source refresh

A fresh API check found the seven selected Gravity stack heads, Asahi `asahi`,
and Aurora `integration/aurora` unchanged. Mainline advanced to
`4403278e4ea2f654f8130a5c03eb8b4516a0f201` (7.3.0). Its J773g DT path still
returns 404; the DRM Makefile has no Apple/Asahi entry and Apple NVMe still lacks
the T8132 match. The 157-commit comparison lists 98 changed files, below the
API file cap; shared PM/scheduler changes are not thereby semantically qualified
for this downstream kernel. There is no evidence here for replacing the matched
Gravity M4 stack with mainline. Retained [head observations](receipts/2026-10-21-source-head-refresh.json)
and [exact mainline checks](receipts/2026-10-21-mainline-refresh.json).

### Hosted candidate provenance before image input preparation

`fetch-hosted-candidates.py` requires explicit run IDs and full recipe source
commits. It checks the GitHub repository, source repository, workflow path,
manual-dispatch event, successful completed run and component job, and exactly
one unexpired candidate artifact. It rejects archive traversal/symlinks and
checks the embedded source commit and package/source checksums. Downloads stay
in a new workspace marked `INCOMPLETE` until both components pass. GitHub
provenance is not an independent signature or a hardware result. The existing
package validators must still pass through `prepare-image-inputs.py`.

After both selected runs succeed, retrieve with:

```sh
python3 mseries/m4-mini/fetch-hosted-candidates.py \
  --kernel-run 39698975678 \
  --kernel-source 2798237ed0b3cd386385e8ec0d92a10fb0987db7 \
  --mesa-run 39704499140 \
  --mesa-source 84bf7a7c2b75afc49ba7904a8e3abd728ec9f32a \
  --output /path/to/new-candidate-download
```

The resulting `kernel/` and `mesa/` each contain `receipt.json` (package record),
`build-receipt.json`, the component `.deb`, and corresponding source archive.
Mesa also retains `mesa-software` for package checking. No downloaded recipe
is executed by retrieval. Five local test groups pass; a live incomplete run
is rejected before workspace creation. Successful retrieval is pending.
[Preflight receipt](receipts/2026-10-21-hosted-intake-preflight.json).

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

### Disposable GPT/FAT boot-file readback

`check-boot-esp-fixture.py --bundle VERIFIED_BOOT_BIN --receipt NEW_JSON`
creates only a temporary 96 MiB regular image with a 64 MiB FAT32 ESP. It
places the verified M4 bundle at `/m1n1/boot.bin`, then uses the existing ESP
readback verifier to locate the GPT ESP and check the extracted file hash.
A deliberately corrupted replacement must fail the same verifier. Both cases
pass; the temporary image is removed. No loop device, mount, real disk or boot
authorization is involved. Required tools are `sgdisk`, `mkfs.vfat`, `mmd`,
`mcopy`, and `sfdisk`; this run extracted mtools/fdisk work-locally without
installing packages on the host.

This verifies FAT/GPT mechanics with the actual bundle, not full mkosi output,
EFI executable discovery, firmware handoff or native boot. Those gates remain
open. [Fixture receipt](receipts/2026-10-21-boot-esp-fixture.json).

### Third hosted Mesa result and GLVND correction

Run `39702973626` compiled/staged Mesa, passed all five selected AGX groups,
and passed the llvmpipe EGL rendering check. It then failed receipt creation:
missing GLVND development files made Mesa's automatic selection produce
standalone EGL/GLX instead of the vendor libraries required by packaging.
This is not package success. The hosted dependency list now includes
`libglvnd-dev`, and the build wrapper explicitly requires `-Dglvnd=enabled`
to fail during setup if the intended layout is unavailable. Two workflow
regressions verify prerequisites and the explicit option. Prior local vendor
library tests remain historical evidence; corrected hosted replay is pending.
[Failure and successful substeps](receipts/2026-10-21-hosted-mesa-failure-3.json).

Corrected GLVND replay: [39704499140](https://github.com/techmore/ElementaryOS_MSeries/actions/runs/39704499140), source `84bf7a7c2b75afc49ba7904a8e3abd728ec9f32a`. No completed result yet. [Dispatch snapshot](receipts/2026-10-21-hosted-mesa-retry-4.json).

### Complete-graph research image driver

`build-research-image.py` now consumes the trusted prepared input directory and
verified boot bundle, rechecks package/source hashes, and stages them in a new
disposable source clone. It permits only the reviewed live-kernel hash patch,
keeps the main checkout unchanged and retains corresponding source and input
records. It selects `daily` + `m4-mini` without dependency overrides, preserving
the Apple Silicon desktop overlay and full image graph.

```sh
python3 mseries/m4-mini/build-research-image.py \
  --inputs /path/to/validated-image-inputs \
  --boot-bundle /path/to/verified-chain/boot.bin \
  --mkosi-source /path/to/trusted-mkosi-source \
  --image-version 20261022013000 \
  --output /path/to/new-image-workspace --summary-only
```

Actual summary resolution passes for all 11 images, including base,
apple-silicon, liveiso and sysupdate, using the existing local validated
packages. Removing `--summary-only` invokes genkey and the full native mkosi
build using automatic subordinate IDs; it never falls back to a single-ID
build. The execution preflight in this environment correctly rejects the
blocked newuidmap operation before creating an output workspace or starting
mkosi. Thus no full-image build result is claimed. ISO assembly, output/ESP
content checks, install adapter and native qualification remain separate work.
[Driver preflight](receipts/2026-10-21-full-image-driver-preflight.json).

### Disposable image-key generation

The full-profile native `mkosi genkey` command succeeds in the disposable
source clone. The generated public certificate matches its private key;
self-signed certificate verification passes and private-key permissions are
0600. Only public certificate metadata and public-key digest are recorded;
private keys remain work-local and were not enrolled. This verifies the key
preparation step, not verity-image creation, Secure Boot, macOS authorization,
or native boot. [Key-generation receipt](receipts/2026-10-21-image-keygen.json).

The image driver now derives its permitted kernel patch from `git show` at the
selected source commit, matching the clone snapshot rather than unrelated
working-copy edits. Three existing kernel-patch regressions pass. Full build
execution remains subject to the documented subordinate-ID restriction.

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

### Hosted boot-chain replay preparation

The registered daily workflow now accepts `m4_boot_only=true` to build the
selected bootloader stages, source-pinned U-Boot and captured Gravity J773g DTB,
assemble their reviewed bundle, and run the disposable FAT/GPT check. Its
concurrency suffix allows the existing kernel and Mesa runs to continue;
ordinary image and Fairydust jobs are excluded. The candidate artifact retains
corresponding bootloader/U-Boot/DT source, resolved Rust dependency sources and
reproduction scripts in their original relative layout. No signing/enrollment
or release publication step is included.

The bootloader wrapper now explicitly fixes its build tag to `f02d4a5`; a native
replay produces the unchanged reviewed stage hashes. Workflow parsing, shell
syntax and selection checks pass. Hosted replay remains required, including
checking whether this runner reproduces the reviewed artifact hashes.
[Preflight](receipts/2026-10-21-hosted-boot-preflight.json).
