# M4 Mac mini: Gravity Linux and upstream audit

**Hosted baseline result:** Revision-2 kernel, GLVND Mesa and boot-chain jobs have succeeded.
Downloaded kernel/Mesa packages and the boot bundle pass local checks. Their
prepared inputs now build the complete mkosi image graph with hosted desktop,
Mesa, ESP and GPT checks passing. Downloaded raw/GPT/ESP, active verity/signature
and corresponding-source hashes now pass local checks;
ISO assembly, installation and native M4 support remain unvalidated.
[Kernel](receipts/2026-10-21-hosted-kernel-success.json),
[Mesa](receipts/2026-10-21-hosted-mesa-success.json),
[boot chain](receipts/2026-10-21-hosted-boot-success.json),
[full-graph preflight](receipts/2026-10-21-all-hosted-image-preflight.json).

The initialization-only revision-3 kernel full build and downloaded package checks now pass.
Revision 4 now adds M4-specific terminal-timeout retention: actual M4 driver,
Rust core and C scheduler object compilation and six generic ARM64 QEMU cases
pass. Full revision-4 Image/modules/DTBs/package compilation is now running;
no scheduler-fixed package has replaced the reviewed baseline image inputs.
The combined revision-5 research recipe now selects all six reviewed scheduler
fixes. Actual M4/legacy objects compile and twelve QEMU cases pass; full r5
compilation and actual module unload remain open. Native M4 is unqualified.

**Conclusion:** Gravity has a substantive native J773g developer-alpha port with
project-reported HDMI/DCP and GPU operation. It is the strongest directly relevant
public stack found in this audit. It does not establish that elementary OS or the
owner's 16 GB / 1 TB / 10 Gb Ethernet / macOS 27 / HDMI configuration is qualified.

Current elementary preparation: the opt-in M4 profile selects the matched
kernel, Mesa revision 4 and temporary policy. A 1,626-package research desktop
root passes package, library, schema, software-rendering and Casper initramfs
checks. LightDM selects Pantheon Wayland; unqualified graphical installer
packages are omitted. The full baseline mkosi graph now builds and its raw artifact passes local verification.
ISO assembly, graphical login, native M4 operation and dual boot remain unqualified.

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

Hosted boot-only replay [39706164509](https://github.com/techmore/ElementaryOS_MSeries/actions/runs/39706164509) dispatched at `43abd72757d13a72d537ad69f932ca899e8fed65`. No completed result yet. [Dispatch snapshot](receipts/2026-10-21-hosted-boot-run.json).

### Hosted Mesa build and downloaded-package validation pass

Corrected run [39704499140](https://github.com/techmore/ElementaryOS_MSeries/actions/runs/39704499140)
at recipe `84bf7a7c2b75afc49ba7904a8e3abd728ec9f32a` completed successfully.
The GLVND-enabled source build, five selected AGX test groups, software
render/readback, packaging and hosted package checks all pass. Downloaded
artifact provenance was checked against the successful own-repository workflow
and component job. Package/source checksums pass, and a local replay on the
actual downloaded package verifies four ARM64 library hashes/ELF identities,
persistent /usr layout, absence of package hooks and llvmpipe rendering.

The hosted package SHA-256 is
`6c9b77f135a8d00ad31a68351d7f695aba6b0861e2e2e47a4d78834a26d11b2a`;
this is a separately retained candidate at the same source/version, not a
silent replacement of the earlier local package hash. Kernel and boot-chain
hosted jobs remain active at this snapshot. Full-image assembly, native
M4 GPU/HDMI and Vulkan conformance remain unverified.
[Successful build, provenance and local checks](receipts/2026-10-21-hosted-mesa-success.json).

### Hosted boot replay correction

Boot run `39706164509` compiled both stages and U-Boot, then source capture
failed with HTTP429. The job now captures the 14 required Gravity DT members
from the complete checksum-pinned kernel archive. A local replay produces the
exact reviewed DTB. That archive is retained with candidate corresponding source.

Hosted records also show different stage-1/U-Boot bytes from local builds;
stage 1 contains Cargo checkout paths, and identical source/config/compiler
labels do not guarantee cross-environment binary identity. The assembler now
accepts an explicitly paired set of trusted fresh build receipts, verifies
reviewed source/config contracts and stage headers, and checks each binary
against those receipts. Its default still requires the reviewed golden hashes.
The FAT fixture can consume the resulting trusted candidate assembly receipt.
Local fresh-receipt assembly/readback/corruption checks pass; a wrong-source
receipt is rejected before output. No fresh candidate is a factory promotion.
[Failure, component records and corrective checks](receipts/2026-10-21-hosted-boot-failure-1.json).

Corrected boot-chain run [39706878433](https://github.com/techmore/ElementaryOS_MSeries/actions/runs/39706878433) dispatched at `5527c5d52bb92fbd8505a6b83c72d5a4c2ea606c`. Result pending. [Dispatch snapshot](receipts/2026-10-21-hosted-boot-retry-2.json).

### All hosted components verified and integrated into full-graph preflight

Kernel run `39698975678` and corrected boot run `39706878433` succeeded.
Own-repository run/job/source provenance and complete artifact checksums were
verified before local checks. Downloaded kernel package validation passes
Image/config/DTB hashes, 16 KiB ARM64 header, all 1598 modules and required
module ELF/vermagic/dependency checks. The hosted boot bundle passes local
FAT/GPT readback and corruption rejection, with corresponding sources retained.

The image driver now accepts an explicit trusted fresh boot-assembly receipt,
requiring the pinned bootloader/U-Boot/kernel identities, reviewed DTB and
NO_DISPLAY configuration. Two boundary/patch test groups pass, and six intake
groups pass. Optional paired `--boot-run`/`--boot-source` inputs add boot artifacts
to the provenance retriever without changing the existing kernel/Mesa usage.

Prepared hosted kernel + Mesa, local policy and hosted boot inputs resolve all
11 mkosi images. Both real candidate hash patches apply only in the disposable
clone; its only tracked changes are the two kernel/boot hash hooks. The main
checkout's reference hashes remain unchanged. This is a summary preflight, not
a complete image, ISO, installer or native M4 result. Source/kernel dates alone
do not close HDMI, 10 Gb Ethernet, GPU, firmware or macOS/Recovery gates.
[Integrated preflight](receipts/2026-10-21-all-hosted-image-preflight.json).

### Full hosted image-only build preparation

The daily workflow now accepts `m4_image_only=true`. It consumes only the three
reviewed run/source pairs in `hosted-inputs.json`, revalidates successful job and
artifact provenance, prepares matched inputs and invokes the complete image
driver with checksum-pinned mkosi `f7e3288`. It uses the normal subordinate-ID
build path, preserves every configured dependency image, and checks the resulting
raw sysupdate ESP against the selected boot bundle before GPT export/compression.

The job retains build records on failure and research raw/source artifacts on
success. It does not publish a release, assemble an ISO, run an installer or
qualify hardware. YAML/shell/isolation checks and 13 relevant tests pass; actual
hosted execution is required before claiming any full-image result.
[Preflight](receipts/2026-10-21-hosted-image-preflight.json).

Full hosted image run [39708207843](https://github.com/techmore/ElementaryOS_MSeries/actions/runs/39708207843) dispatched at `2a61c2ac3ac52feafef4dc1884eb6b8d6d970b55`. Completion and output validation are pending. [Dispatch snapshot](receipts/2026-10-21-hosted-image-run.json).

### First full-image attempt and runner execution correction

Run `39708207843` passed artifact provenance/checksums, kernel/Mesa package
checks, matched input preparation, mkosi checksum and full-graph resolution.
It failed before key generation: UID mapping worked but unprivileged mount
namespace propagation was denied. No image build completed.

The image job now explicitly invokes the build as root on the ephemeral GitHub
runner; the driver requires both root identity and the explicit CI environment.
It does not alter runner security settings or the local NoNewPrivs restriction.
Hosted-root inspections retain private mount/PID namespaces and preserve real
package ownership. Normal local mapping behavior remains unchanged.

The job also now requires the project's existing built-desktop payload check,
base/live package/library/schema/session validation and live Mesa retention
after assembly. Six desktop-wiring tests, one boundary group covering all three
root-mode programs and two candidate-boot groups pass. Workflow syntax passes.
Hosted root execution and complete image acceptance remain pending replay.
[Failure and correction receipt](receipts/2026-10-21-hosted-image-failure-1.json).

Corrected full-image replay [39708881382](https://github.com/techmore/ElementaryOS_MSeries/actions/runs/39708881382) dispatched at `1aafd4fd781da36712c15d69eedcfb11cbcc1a25`. Hosted execution and acceptance results pending. [Dispatch snapshot](receipts/2026-10-21-hosted-image-retry-2.json).

### New Aurora scheduler fix applies to the M4 candidate

A fresh head check found Gravity, Asahi, mainline and Omarchy MX unchanged,
while Aurora advanced to `ed55042c712afb987608e3633cb926116ca1962e`. Its three-commit
delta includes C scheduler `free_guilty` initialization and zeroing the C storage
in the Rust wrapper (origins `6c2d17f`, `0d1871c`). Gravity has both affected
patterns, and M4 `g16_drm` constructs this shared scheduler. The G17 timeout
scenario itself has not been reproduced on M4.

An elementary compatibility patch ports only the two initialization changes
to Gravity's older API, separate from the unchanged Gravity ARM64 packaging
exports. It applies without fuzz to exact pinned archive files; source-result
hash gates pass. The build/package wrapper stages revision 3 with this patch
and retains its provenance. Revision 3 validation requires the recorded
compatibility manifest. Compilation and runtime validation are pending; the
newer Aurora owner/lifetime refactor and KUnit suite are not implicitly ported.

The active full-image run still uses revision 2 and is baseline assembly
evidence only. Its completion cannot prove this newly discovered issue fixed.
No reference image/package promotion has occurred; a validated revision-3
kernel and matched image replay are needed before accepting the updated stack.
[Head observations and backport preflight](receipts/2026-10-21-scheduler-backport-preflight.json).

Revision-3 scheduler kernel run [39709872273](https://github.com/techmore/ElementaryOS_MSeries/actions/runs/39709872273) dispatched at `645ee9085def4cdd0d591a403e977727d87682dc`. Source preflight passes; full compile/package results remain pending. [Dispatch snapshot](receipts/2026-10-21-scheduler-kernel-run.json).

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

### Separate kernel scheduler KUnit candidate

The older kernel provides Rust KUnit and faux-device support. A test-only patch
now adapts Aurora's three poisoned-storage/delayed-fence cases to its older
JobImpl API and exposes constructor allocation injection. This test patch is
kept outside the normal kernel package manifest. It does not change production
M4 timeout behavior or imply that the remaining lifetime protocol is ported.

`prepare-scheduler-kunit.py` verifies/extracts the pinned kernel, applies the
reviewed production patches and then the separately hashed test patch into
a new source tree. The ARM64 KUnit runner is compiling it natively with
Clang 21 and matching work-local Rust 1.99 sources; QEMU uses TCG with networking
disabled and no storage device. No TAP/test result exists yet. Initial Kconfig
and rust-src location setup failures are retained. Source preparation and a
live compile are not scheduler or hardware test passes.
[Preparation record](receipts/2026-10-21-scheduler-kunit-preparation.json).

KUnit compile follow-up: the first source compile stopped before testing on
older faux-device typestate and an existing KUnit-only iosys_map assertion
helper's missing Debug bound. The isolated patch now uses the actual older
Device type and bounds that test assertion method. A fresh no-fuzz patch replay
reproduces both current test-tree files exactly. The same native build directory
is resumed under session 92953; no runtime pass is claimed. Production kernel
patch manifests are unchanged by these test repairs.
[Repair record](receipts/2026-10-21-scheduler-kunit-api-repair.json).

### Baseline full-image second attempt reaches repart, then fails

Run `39708881382` is a terminal failure, not an active build. Explicit hosted
root passed key generation and proceeded through configured images to sysupdate
filesystem/GPT assembly, unsigned UKI generation and ESP formatting. The
partition-extraction step then failed with `Verity signature partition is empty`
using tools-tree systemd-repart 259.9. Final desktop/root/retention and completed
artifact checks did not run, and no complete image is accepted.

The active/spare signature handling must be traced before another image replay;
signature policy must not be disabled to obtain a build. Scheduler-fixed r3
compilation and the isolated KUnit build continue independently.
[Second image failure](receipts/2026-10-21-hosted-image-failure-2.json).

### Standby split export fix verified with active verity intact

The empty-signature failure is reproduced with the exact Ubuntu systemd-repart
259.9 tool version in a small file-backed fixture. Repart defaults SplitName
to the partition type, so even empty standby slots were exported. The three
standby definitions now set `SplitName=-`; their GPT reservations, labels,
UUIDs, sizes and attributes are retained. Active data/hash/signature exports
and signature policy remain enabled.

The corrected fixture succeeds, has byte-equivalent parsed GPT metadata to
the failing case, emits no empty standby exports, and passes both OpenSSL
certificate/signature verification and veritysetup data/hash verification.
The full-image job now runs this fixture before assembly and preserves its
logs. Default/M4/Fairydust profile resolution still passes. This is not yet a
full-image success. [Fixture and tool hashes](receipts/2026-10-21-repart-standby-fix.json).
The [upstream repart definition](https://github.com/systemd/systemd/blob/v259/man/repart.d.xml)
documents the SplitName default and `-` opt-out.

### Kernel scheduler KUnit positive result

All three adapted upstream cases pass in a real ARM64 QEMU kernel: dirty
storage starts clean, late completion after repeated timeouts, and repeated
timeouts with out-of-order completions/teardown. This is a generic virt machine
with fake fences, not an M4 GPU/firmware/display test. The emitted runner uses
an accelerator fallback list; earlier planned TCG wording is not proof of
the actual selected backend. Broader lifetime/aliasing/NoDevice gates remain
open. A dirty-storage-only negative control is running separately, followed
by restoring and retesting the positive sources.
[Positive KUnit result](receipts/2026-10-21-scheduler-kunit-positive.json).

Standby-split-corrected image replay [39713917690](https://github.com/techmore/ElementaryOS_MSeries/actions/runs/39713917690) dispatched at `cc10d6ef85fa4111ef0ed207979e24084d4bfb64`. This remains the revision-2 baseline image; fixed scheduler kernel compilation is separate. [Dispatch snapshot](receipts/2026-10-21-hosted-image-retry-3.json).

Public-source follow-up: the scheduler negative control failed the poisoned-storage
test with initialization removed, then all three tests passed after source restoration
(2-vCPU generic ARM64 QEMU; no M4 GPU runtime). See
`mseries/m4-mini/receipts/2026-10-21-scheduler-kunit-control.json`.
Image replay 39713917690 stopped before assembly because the synthetic fixture
user-ID namespace was denied by CI. The fixture now supports the same explicit
root-plus-GITHUB_ACTIONS guard as the image builder; local non-CI use is rejected
before creating output. Runner security settings remain unchanged. The scheduler
fixed kernel build 39709872273 remains in progress. Hardware remains unavailable.

The added NoDevice diagnostic reproduces an unreleased job after terminal timeout
and hardware-fence completion on generic ARM64 QEMU. This is stronger than the
earlier source-only finding; it does not measure an M4 GPU failure rate. See
`mseries/m4-mini/receipts/2026-10-21-scheduler-nodevice-control.json`.
The diagnostic patch is excluded from both production compatibility and normal
KUnit manifests. An opt-in retention adaptation is being tested separately.
Image replay 39714367674 passed signed active-slot/identical-GPT fixture checks,
then failed copying the receipt from the private root-owned fixture directory.
The workflow now exports only named public diagnostics using `sudo install`;
the signing key remains private. Full image assembly did not start in this run.

The opt-in NoDevice retention diagnostic adapted from Aurora 0f89327 passes
all four generic ARM64 QEMU cases, including the cleanup case that failed
without retention. See `mseries/m4-mini/receipts/2026-10-21-scheduler-nodevice-retention.json`.
This optional test patch is excluded from normal kernel/test manifests. It is
not a production M4 backport: backend opt-in, allocation ownership, timeout
aliasing, cancellation and full g16-enabled compilation still require review.
All modified test source files were restored. Full image replay 39714779495
uses source 0b2afea8 and the reviewed baseline r2 components; it is separate
from initialization-fixed r3 kernel build 39709872273.

Six-case NoDevice retention diagnostic: completion during the timeout callback
and unfinished-job teardown/late parent signalling both pass, along with the
previous four cases, on generic 2-vCPU ARM64 QEMU. See
`mseries/m4-mini/receipts/2026-10-21-scheduler-nodevice-boundaries.json`.
An unpromoted production-API candidate is staged in `gravity/experimental`: a
default-false JobImpl opt-in enables retention specifically for M4 SubmissionJob.
Actual Rust core, M4 driver and C scheduler object compilation is running in a
separate local source/output tree. No installed kernel or normal build manifest
is changed by this candidate; allocation-owner and callback-aliasing review
remain open. Image replay 39714779495 has passed the fixture/input steps and
is executing the full mkosi graph. Kernel r3 run 39709872273 is still compiling.

Revision-4 kernel recipe now includes the default-false terminal-timeout
retention contract, with only M4 SubmissionJob opting in. Actual M4 driver,
Rust core and C scheduler objects compile using the full M4 configuration;
all six cases also pass through the associated-constant API on generic ARM64
QEMU. Source/config/hash gates pass. The package validator now binds r3 and r4
to distinct exact compatibility manifests, preserving the initialization-only
r3 identity. The existing downloaded baseline r2 package still validates.
Full r4 Image/modules/DTBs/package compilation is required before changing
reviewed image inputs. The earlier production-API prototype is now selected
by the r4 recipe; no kernel has been installed. Shared allocation-owner and
mutable timeout-aliasing reviews remain open.

The current revision-4 compatibility and normal testing manifests now replay
without fuzz and pass all six ARM64 QEMU cases; see
`mseries/m4-mini/receipts/2026-10-21-scheduler-r4-kunit.json`. Full hosted
revision-4 build 39715540751 is pending behind live initialization-only r3 run
39709872273; source is 25504a70b0df4df52654974de9df5e3074ab4973. Baseline
image replay 39714779495 remains live in full graph assembly. Preserve these
run identities; do not restart them on an observation timeout. Neither full
r4 compilation nor image completion is claimed. Hardware remains unavailable.

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

Initialization-only kernel revision 3 completed successfully in hosted run
39709872273. The downloaded package and source archive pass complete payload
checksum checks, own-repository/workflow/source provenance checks and current
version-specific package validation (1,598 modules, 16 KiB Image, J773g DTB,
module identity/dependencies, no hooks). Package SHA256 is
60ff6803c34f01c733950cf13ddeec785047e638809fd6338c6fdccbbe801a5c.
Its receipt contains initialization only: it is not credited with r4 retention
or the unpromoted owner/module candidates. Full r4 run 39715540751 is now
in progress. Baseline image run 39714779495 remains live, using reviewed r2
inputs; no complete image or hardware result is claimed. See hosted-kernel-r3-success.

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

2026-10-22 combined kernel recipe: revision 5 now selects initialization, M4
retention, allocation owner, callback module/DRM fops ownership, permanent work
drain, disjoint timeout state and matched final cancellation/accounting.
The six patches are unchanged from the compiled/12-case-tested candidates.
Fresh default preparation replays them without fuzz and reproduces the exact
tested scheduler. Normal-source gates also pass with only the test patch
reversed. Frozen r3/r4 source and patch gates pass, and the downloaded r3 package
still validates against its own initialization-only manifest. Historical staged
options explicitly use r4, avoiding duplicate application on the new default.
Full r5 Image/modules/DTBs/package compilation is the next gate; r4 run
39715540751 remains live. Reviewed image inputs stay r2 until a newer full
package passes download checks. Module unload, ISO, installer import and native
M4 remain unqualified. No installed host component changed.

2026-10-22 r5 and module-lifetime update: full combined research kernel run
39721608135 is pending at source ab32b7f0748f2898b5e19f4f60d5032917d93051,
behind live r4 run 39715540751. Both remain unpromoted full-build gates.
A new reproducible diskless ARM64 QEMU/TCG fixture loads a real C backend module
against the reviewed shared scheduler. Pending deferred cleanup keeps the module
busy; dependency completion releases it and unload succeeds. The missing-owner
negative detects no module reference and powers off before attempting unsafe
unload. Both use the same kernel/config/BusyBox/init; no host module is loaded.
The fixture and positive/negative receipts are retained under testing/module-lifetime.

This closes only the shared C callback-module path. Source follow-up observes
that M4 Execution signals job completion before its pump callback returns;
File::drop waits those fences, not an explicit WorkItem join. Registration/device
ownership may provide further guarantees and must be traced before selecting
a fix. This is an inference from reviewed entry points, not a native fault
reproduction. The generic C fixture does not cover this Rust worker. See
m4-worker-module-follow-up receipt. M4 driver unload and firmware/native
qualification remain open; baseline image integrity is already checked.

Latest public-source refresh: all twelve selected heads remain unchanged.
A complete public branch inventory records 3 Gravity, 159 Asahi and 96 Aurora
heads; inventory is not semantic qualification. The M4 PR1/PR2 branches still
match existing research pins. Aurora fix/apple-m4-wait-state at 3f0822d adds an
M4+ register-preserving idle/WFxT path; Gravity's selected idle implementation
differs. Applicability and shipping boot/runtime policy require review before
porting low-level code or adding new flags. Gravity scripts at the package URL
is an additional policy reference to inspect. No idle patch/flag is selected
from this observation. The current Gravity announcement still describes a
developer alpha with limited testing; its HDMI claim is not owner hardware
qualification. The source wait-state follow-up receipt bounds these uncertainties.

New upstream intake to review next: Asahi apple-soc/dt-7.4 at a8ac6027e82415f4
and asahi-wip-7.2 at 236788cd2602a24c both contain t8132-j773g.dts and T8132
SoC/PMGR/common board files. This is a filename inventory, not GPU/DCP/storage
or firmware compatibility qualification. Compare their actual driver coverage
and contracts with the complete Gravity stack before selecting a new kernel
base or transplanting DT data. The earlier selected Asahi integration head
remains unchanged; these staging branches require a separate applicability pass.

Revision-4 research kernel run [39715540751](https://github.com/techmore/ElementaryOS_MSeries/actions/runs/39715540751) succeeded. The downloaded package independently passes Image/config/J773g/16 KiB/module checks (1,598 modules), with initialization and M4 terminal-retention fixes. Combined revision 5 run 39721608135 is building; neither result qualifies native hardware. Evidence: `mseries/m4-mini/receipts/2026-10-22-hosted-kernel-r4-success.json`.

Public staging-source comparison now covers pinned Asahi dt-7.4, drivers-7.4,
and wip-7.2 paths, beyond filename inventory. The reviewed J773g trees retain a
loader framebuffer, but lack Gravity's native T8132 GPU/DCP/NVMe/PCIe nodes.
Their reviewed NVMe match tables lack the T8132-specific hardware descriptor;
wip-7.2 Asahi DRM depends on BROKEN and lacks Gravity's g16 implementation.
Gravity's UAPI also adds fragment-barrier flags absent from these Asahi headers.
Retain the complete Gravity stack; newer branch numbers do not establish an
M4 desktop replacement. See receipts/2026-10-22-asahi-staging-contract-comparison.json
under mseries/m4-mini (source paths/hashes and explicit scope).

All 31 files of pinned Gravity scripts 12418e5 were reviewed for idle/WFxT flag
literals; none were found. This does not cover external GRUB defaults or prove
an idle workaround necessary. Exact pinned bootloader chickens.c matches the
local source (SHA256 757971865794c78e605082de1dda00a52b43bfc117df57affdfe5bdd1c39adbb):
M4 features omit apple_sysregs_unlocked and select SLEEP_NONE, so the guarded
WFI-retention register code must not be claimed as an M4 setup guarantee.
No speculative idle flags/assembly change is selected.

Worker follow-up traces foreign devres DRM registration and platform post-unbind
private-data release. Generic Arc workqueue dispatch does not explicitly pin
module code. More importantly, reviewed DRM Device::release intentionally does
not drop its data, citing possible uninitialized storage. ARef release therefore
is not proof that scheduler/RTKit destructors run. Trace C unregister, file release,
and RTKit callbacks before choosing an M4 worker join/resource fix; do not simply
enable the commented destructor. Source evidence is retained in
mseries/m4-mini/receipts/2026-10-22-m4-registration-worker-follow-up.json.

DRM/RTKit release-order follow-up now checks C internals. drm_dev_unregister
has no generic pump join; the reviewed Rust VTABLE provides no M4 unload hook.
Gravity Device::new already uses a temporary release=None vtable through fallible
data initialization, then publishes its full vtable. Aurora ed55042 uses the
corresponding constructor pattern with normal initialized-data destruction.
Gravity's old release leak is therefore not justified solely by the constructor's
current initialization path, but restoring synchronous Drop still needs final
DeviceRef callback-context/deadlock and unbind-before-devres review. In the actual
RTKit destructor, mailbox stop and workqueue destruction precede callback-data
free; the leak means that boundary cannot currently be assumed to run.
No speculative global-workqueue flush or destructor patch is selected. Evidence:
mseries/m4-mini/receipts/2026-10-22-m4-drm-rtkit-release-order.json.

The next hosted image workflow now assembles a distinct unpromoted ARM64 UEFI
research ISO from the full checked live root and raw image, using a hosted-root-only
assembler. It requires the exact reviewed kernel, one module tree, early NVMe/PCIe
modules and the unchanged research installer guard; preserves source root ownership;
checks UEFI boot-catalog presence; reads the ISO back and hashes kernel/initrd/both
squashfs payloads; and decompresses the embedded raw image to compare its full hash.
The generic installer remains unavailable. It uses native runner GRUB/xorriso,
without changing owner-host boot software. Diagnostics survive failed assembly.
Preflight passed Python/YAML parsing, small regular-file raw/live squashfs readback,
exclusion of the ISO staging template from the live filesystem and rejection of
non-hosted execution before output creation. This is not a successful full ISO;
that requires a new hosted graph build with retained live root. Wait for r5 kernel
success/download validation, update image inputs coherently, then run the combined
image/ISO workflow once. Evidence: receipts/2026-10-22-iso-assembly-preflight.json
under mseries/m4-mini.

An actual small synthetic ARM64 EFI ISO fixture now passes native GRUB assembly,
xorriso UEFI catalog inspection and full ISO extraction; kernel-placeholder and
compressed-raw payload hashes match, and embedded raw decompression roundtrips.
The extracted EFI/BOOT/BOOTAA64.EFI is a valid AArch64 (0xaa64) PE executable.
The placeholder kernel was never executed: this proves packaging/tool behavior,
not boot or desktop qualification. A first isolated-tool attempt lacked mformat;
existing isolated mtools corrected that PATH, and production now checks mformat/
mcopy up front (hosted mtools was already installed). Production also verifies
AArch64 EFI fallback readback. No owner-host packages or boot configuration were
installed. Receipt: mseries/m4-mini/receipts/2026-10-22-iso-uefi-fixture.json.

Additional teardown ordering concern remains source-only: normal C scheduler
free_job executes on work_free_job, while SchedulerOwner destruction calls fini,
which synchronously disables work_free_job. A final device reference released
from that callback must not synchronously destroy its own scheduler. This is a
reason to retain explicit producer joins/deferred destruction in any candidate,
not a native failure claim or justification for the existing resource leak.

A regular-file-only partition import prototype now closes the metadata-copy
algorithm gap in isolation. import-partitions-regular.py creates a NEW copy of
a GPT template, requires explicit exact-size/all-zero/reserved-type/empty-label
slots, revalidates exported binary metadata against its manifest, and transfers
all selected GUIDs/labels/attributes/payloads while preserving destination geometry,
disk identity and every byte outside allowed writes. Both GPT copies/CRCs and
payloads are checked after import; incomplete outputs remain marked. Original
template/device/symlink/occupied-slot handling is fail-closed. This is not wired
to macOS or installer admission, and does not constitute a live-GPT transaction.

Ten independent regular-file tests pass (28.777s), using sgdisk fixtures, existing
simulated macOS/Recovery entries/data, active/spare-style payloads, Unicode labels,
all attribute bits, corruption/collision/size/occupied-slot/device rejection, and
512-byte source to synthetic 4096-byte destination geometry. Two hosted-workflow
tests pass too; the importer suite is added to hardware-support CI, whose remote
result is not yet claimed. Receipt: mseries/m4-mini/receipts/2026-10-22-regular-partition-import-tests.json.
Native allocation, GPT update/recovery semantics, real APFS preservation, ESP handoff,
writable root, signature trust and macOS Recovery acceptance remain open. R5 run
39721608135 was rechecked live while this work proceeded; no duplicate was started.

Actual baseline-image active payload import now passes, beyond tiny fixtures:
signature (16 KiB), hash (400 MiB) and usr (7 GiB) from image run 39714779495
were relocated into different slots/LBAs in a new 9 GiB regular-image copy.
All selected source metadata/payload hashes match; destination disk identity,
unselected entries/bytes and original template remain unchanged. Independent
sgdisk metadata/CRC checks pass. Source payload bytes equal the previously
verity/CMS-verified export; cryptographic tools were not rerun in this copy trial.
The template has simulated macOS/Recovery byte ranges, not actual APFS filesystems;
this is baseline r2 payload evidence, not r5, native allocation or installation.
Receipt: mseries/m4-mini/receipts/2026-10-22-real-active-partition-import.json.

Open proposal intake found Gravity Mesa PR1 at immutable 208d4a4, eight linear
commits directly atop selected 87ac51d. Claims include Sway/zathura/mpv fixes,
Apple9 blit recursion, tile helper formats, clear accounting, modifier/external
image capabilities and Honeykrisp rodata placement. Exact changed Git blobs,
before/after hashes, commit chain and unchanged UAPI are recorded. A separate
native full build is now running under work/m4-mesa-pr1-build (resume.py, terminal
session 79442). An initial missing wayland-egl-backend configuration dependency
was resolved with the existing work-local pkg-config path; failure log retained.
Do not restart on observation timeout. No selected Mesa package/hash changed.
Review remains open for blanket uniform metadata on helper shaders, compositor
imports and low-rodata allocation failure (the proposal falls back to the old
USC address if allocation fails). Compile/software tests cannot qualify these
M4 GPU behaviors. Source intake receipt records the scope and concerns.

Gravity Linux PR3 (BCM4387 suspend) and PR4 (M5 J704) are additionally inventoried.
M1 author-reported suspend tests do not enable M4 sleep; M5 inventory does not
qualify the plain M4 mini. These proposals are unselected. R5 kernel run
39721608135 remains live; existing job is retained, without duplicate dispatch.

A separate unselected Mesa follow-up candidate now handles the PR1 rodata
allocation boundary. It factors upload allocation, checks executable/mirror BO
allocation and the mirror's entire extent below 2^40, propagates errors through
both compile/deserialization callers, and removes the high-USC fallback from fast
linking. Source review confirms both API error callers destroy partial shaders
and unreference both BOs; actual Vulkan API fault injection remains untested.
Candidate path: mseries/m4-mini/gravity/mesa-candidates/rodata-errors, requiring
exact PR1 head 208d4a4 and manifest before/after/patch hashes. Zero-fuzz replay
matches the candidate source without altering the still-running PR build.

Eight verbatim upload-helper cases pass native ASan/UBSan with mock allocation:
normal/no-rodata, each allocation failure, address/extent limits, the last fitting
extent and UINT64_MAX. A false-success negative fails the rodata allocation
assertion as expected. This is helper code execution, not a DRM device, Vulkan
API destructor test, GPU firmware test or full-driver compile. Full real-driver
compile must follow terminal completion of the unmodified PR1 build before any
selection/package change. Receipt: mseries/m4-mini/receipts/2026-10-22-mesa-rodata-helper-tests.json.
The PR's helper-uniformity/compositor behavior remains separately under review.
R5 kernel 39721608135 and isolated Mesa session 79442 were both revalidated live.

The full unmodified Mesa PR1 now builds and stages successfully; all five selected
AGX groups and isolated llvmpipe pass. The rodata candidate also compiles against
the real driver (both API error-return paths and Vulkan library), passes the same
five groups/software smoke and retains its eight helper fault-injection cases.
The original PR1 source was restored after the candidate build. Existing build
outputs are last-candidate objects; do not reuse them as an unmodified PR1 result
without rebuilding. Original PR1 stage/receipts remain preserved separately.
Receipts: 2026-10-22-mesa-pr1-native-build.json and
2026-10-22-mesa-rodata-native-build.json under mseries/m4-mini/receipts.

A separate diagnostic links the actual built NIR library and runs PR1's verbatim
uniform-marker function/block. Reference analysis classifies fragment layer-id
as divergent; after adding the workgroup input selecting the helper path, PR1
clears layer-id's divergence and labels the metadata valid. The actual layered
store helper reads that intrinsic. This confirms a metadata inconsistency, not
rendered corruption or a native crash. Ordinary Apple9 API bodies use a separate
early-NIR native pipeline, so do not generalize this diagnostic to every shader.
The full proposal stays unselected pending correct helper-specific handling and
compositor/GPU coverage. Reproduce with testing/mesa/check-helper-divergence.py;
receipt 2026-10-22-mesa-helper-divergence-finding.json retains source/object hashes.
Selected Mesa package/image inputs remain unchanged. R5 kernel 39721608135 remains
live; kernel download/validation and coherent updated image/ISO build are next.

A combined unselected Mesa candidate replaces PR1's blanket uniform marker with
a scoped NIR compiler option for the known fragment tile-helper workgroup-ID
read. Normal layer/input divergence and uniform optimization passes remain active;
shared-base/workgroup-index fragment reads are still rejected. The option is
scoped to one compiler invocation and its original pointer is restored at return.
The five-file divergence patch plus separately tested rodata patch bind six
source files. Exact before/after hash and zero-fuzz reverse/forward replay pass.
Public candidate: gravity/mesa-candidates/helper-divergence under mseries/m4-mini.

Full combined build is live in work/m4-mesa-divergence-candidate/compile.py,
terminal session 37929. It temporarily installs SIX candidate source files in
work/m4-mesa-pr1-build; its finally block restores all PR1 originals. Do not modify
these sources or restart on observation timeout. After build it will run five
AGX groups, seven actual-NIR semantic/assertion cases, staging and llvmpipe.
Those outcomes are pending, not passes. Source/header compiler units have begun
rebuilding without a terminal failure. The new test runner is
mseries/m4-mini/testing/mesa/test-helper-divergence.py; three negative guards run
as user processes with core dumps disabled, never as kernel/hardware faults.
Source receipt: 2026-10-22-mesa-helper-divergence-source-preflight.json.
R5 kernel run 39721608135 is also still live. No selected image/package inputs
or native hardware/installer flags changed.

Hosted image intake now resolves package filenames from the already verified
artifact receipt instead of hardcoding revision 2 in the workflow. A new wrapper
requires one correct-component ARM64 basename, regular package and matching hash,
then delegates to the unchanged full semantic/version/source checkers. It does
not choose a run or relax provenance/version gates. Four boundary tests and two
existing workflow tests pass. Actual downloaded r2/r4 kernel and Mesa names/hashes
were checked, and a full isolated r4/Mesa preparation rehearsal passes existing
kernel/Mesa/retention/software checks and policy staging. Selected component runs
and base profile version remain unchanged until r5 succeeds and is independently
validated. Receipt: 2026-10-22-hosted-name-intake-rehearsal.json under
mseries/m4-mini/receipts. Both modified workflow YAML files parse successfully.

Combined Mesa compiler candidate session 37929 remains live, rebuilding the
actual compiler/NIR libraries and dependent tests. Seven NIR cases are still
pending. The remote r5 kernel 39721608135 is also live; neither build was restarted.

Combined Mesa PR1 + rodata-errors + scoped helper-divergence build now PASSES.
All five AGX groups, four actual-NIR semantic cases, three expected stage guards,
private staging and isolated llvmpipe pass. The helper keeps layer and derived
sum divergent while workgroup ID is uniform; ordinary fragment and compute
behavior remain correct, and no-opt-in/index/shared fragment cases hit expected
assertions. These are userspace tests with core dumps disabled, not kernel faults.
All six PR1 source originals were restored after the completed trial. Existing
build outputs are the combined candidate; do not reuse as PR1 without rebuild.
Receipts: 2026-10-22-mesa-combined-candidate-build.json and
2026-10-22-mesa-helper-divergence-tests.json under mseries/m4-mini/receipts.

The corrected candidate is still unselected by the production research recipe.
Next: bind all eight public PR changes plus the two reviewed follow-ups into a
versioned Mesa compatibility/source manifest, retain historical v4 validation,
include the exact patches in corresponding-source/reproduction artifacts, build
and check a fresh research package, then update image inputs only after successful
hosted component verification. Native full tile-pipeline rendering, compositor
DMA-BUF imports and hardware remain unqualified. R5 kernel 39721608135 is live.
