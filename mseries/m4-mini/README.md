# M4 Mac mini preparation

Research target: expected Mac16,10 / J773g / T8132. Owner confirms 16 GB RAM,
1 TB SSD, 10 Gb Ethernet, macOS 27 and HDMI output. Confirm the
machine identity before producing a boot bundle. Native dual boot is not qualified.

`research.json` pins public candidate sources and companion bootloader proposals.
It is intentionally separate from `../aurora/release.json`: the installed J314S
release, installer and staging tools do not consume these research pins.

Capture the selected public source files into a new directory:

```sh
python3 mseries/m4-mini/prepare-sources.py --output /path/to/new/research-directory
```

The command downloads code/documentation only, retaining source license headers
and SHA-256 receipts. It neither builds nor installs anything. A failed fetch
leaves `INCOMPLETE`; a receipt proves capture, not hardware support. Keep the
source profile beside any derived patch or build receipt.

Start with [the current audit](UPSTREAM-AUDIT-2026-10-21.md) and
[Gravity integration](GRAVITY-INTEGRATION.md). Gravity's J773g development stack
is the selected candidate: its project reports native HDMI/DCP and GPU support.
The separate J713 Air and older mini diagnostic proposals are comparison
material. Their admission strings, firmware contracts and display routing must
not replace Gravity's matched mini profile.

DTBs, raw bootloader stages, U-Boot and Mesa have built locally. Selected AGX
and software-rendering tests pass; the full kernel Image/modules/DTBs build now passes after the required
Gravity ARM64 export patches. No M4 boot, 10 Gb link, hardware GPU, 16 GB memory-map or macOS/Recovery
acceptance has run here. Those results remain required for owner qualification.

Source capture verifies immutable revisions and hashes. Its receipt records the
actual selected files; changing the checked-in source profile invalidates older
captures by design. The retained older patch review is historical evidence,
not the current support ceiling.

Compile the captured mini DT and keep compiler diagnostics:

```sh
python3 mseries/m4-mini/build-dtb.py --capture /path/to/research-directory --output /path/to/new/build-directory
```

The builder checks capture hashes and the exact checked-in profile before
running cpp/dtc. The retained build receipt records the immutable source,
commands, output digest and warnings. The 2026-10-21 build passed with one
upstream unit-address warning: AIC node `interrupt-controller@381180000`
has first register address `0x381000000`. This remains unmodified upstream
source. `fdtget` confirms `apple,j773g` and the framebuffer's disabled state;
its memory and framebuffer properties require loader fixups. This paragraph
records the earlier Asahi DT build; the separately retained Gravity DT receipt
is the selected candidate and has its own diagnostics.

See [the mini patch review](MINI-PATCH-REVIEW.md) for the public diagnostic patch disposition and its verified digest.

## Gravity mini candidate

The expanded audit found Gravity Linux’s developer alpha with project-reported mini HDMI/DCP and GPU. See [Gravity integration](GRAVITY-INTEGRATION.md); this supersedes broad no-mini-support conclusions in the initial audit. `build-dtb.py --source gravity-mini` compiles the separately pinned mini profile. Current development heads are distinct from the published alpha bundle.

## Full Gravity source build

`build-kernel.py` checks the pinned source archive, applies the retained Gravity
config overlays and uses a distinct `-elementary-m4-gravity1` module release.
It requires work-local matching Rust library sources and an existing Clang/GNU
toolchain. Example:

```sh
python3 mseries/m4-mini/build-kernel.py --archive /path/to/linux-4fc326f.tar.gz --rust-library /path/to/rust/library --output /path/to/new/build-root --jobs 2
```

The resolved config must retain 16 KiB pages, Rust, appledrm and asahi_m4.
The script emits a success receipt only after Image, modules and DTBs build.
The corresponding native full-build steps now pass; the wrapper itself has not yet
completed an end-to-end run. Kernel and Mesa Asahi UAPI headers match byte for
byte at the pinned Gravity heads; see the receipt for the precise scope.

## Debian payload packaging

After a successful full build, `package-kernel.py --source SOURCE --build BUILD
--archive PINNED_ARCHIVE --output NEW_DIRECTORY` produces a distinct
`linux-image-elementary-m4-gravity1` payload and copies its corresponding source
archive alongside it. It checks the source archive, resolved config, module
release, required Image/DTB/GPU artifacts, module inventory and display/GPU
vermagic. No maintainer scripts or boot files are packaged. It does not install
anything. End-to-end packaging now passes after the full build completed. The earlier
incomplete build was correctly rejected for its missing Image.

The driver source requires GPU boot-firmware identifier `mBoot-18000.161.10`
and DCP actual firmware `26.6.2`. GPU firmware regions must be populated by the
matched loader; the source DT intentionally disables the GPU before that fixup.
Do not bypass these driver gates or label a DT/module build as runtime support.

## Isolated graphics userspace

`build-mesa.py --archive PINNED_MESA_ARCHIVE --output NEW_DIRECTORY` builds
the pinned Gravity Mesa with Asahi OpenGL, Asahi Vulkan, llvmpipe, X11 and
Wayland. It enables upstream tests, runs the upstream AGX compiler, Apple9 launcher/geometry and disassembler tests, and stages under a DESTDIR
with prefix /opt/elementary-m4-gravity1. It does not replace system Mesa or
activate a session. Optional --pkg-config-path supports extracted work-local
development packages. The direct build, five selected upstream test groups and private-prefix staging now pass. An isolated llvmpipe context/render/readback smoke test passes too. The complete wrapper replay has not run; these results do not qualify the M4 GPU.

## Matched raw bootloader build

`build-bootloader.py --source PINNED_GIT_CHECKOUT --cargo-home WORK_CARGO_CACHE
--output NEW_DIRECTORY --jobs 2` checks the exact Gravity commit, clean tracked
source and artwork submodule before building stage 2 and chainloading stage 1.
Both stages compiled successfully; their SHA-256 receipt is retained. The raw
binary target omits the optional packaging-supplied Gravity logo. No installed
bootloader, OS authorization, boot configuration or startup selection changed.
These are development-head artifacts, not copies of the original alpha release.

Gravity U-Boot at gravity-alpha-20260925/a2f6913 also builds with native
`make O=NEW_BUILD apple_m1_defconfig` then `make O=BUILD -j1`. Retained receipt
includes u-boot-nodtb.bin, the boot-chain payload; the generated generic control
DTB must not replace the matched J773g loader handoff by assumption. No EFI boot
or runtime calibration test has run locally.

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

The package includes `opt/elementary-m4-gravity1/bin/run-mesa -- COMMAND`.
It selects only that command's private EGL/DRI/Vulkan libraries and adds Gravity's
`ASAHI_MESA_DEBUG=nocompress` session requirement. `--software -- COMMAND` forces
llvmpipe OpenGL for smoke tests; it does not provide a software Vulkan driver.
An extracted payload works because the launcher relocates its temporary Vulkan
manifest. No global environment, loader config or current compositor is changed.

## Candidate M4 image power policy

`package-policy.py --output NEW_DIRECTORY` packages unchanged MIT-licensed
Gravity vendor sleep settings. The arm64 package depends on the separately
named M4 kernel payload, ships six vendor config files and has no maintainer
scripts. Staged `systemd-analyze cat-config` resolves the sleep/logind drop-ins;
payload hash and control checks pass. It is not installed by this work and
does not enable the M4 installer. Remove through a package revision when M4
sleep is qualified. Administrator overrides remain possible.

Current complete upstream trees of alsa-ucm-conf-asahi (1473329) and
asahi-audio (ab1b469) contain no J773g/t8132 paths. This is a profile inventory,
not proof that direct ALSA playback fails. Confirm actual card names and routing
on the mini before adding a model profile; do not reuse older Mac DSP assets.

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
session is not yet qualified or disabled by this command override. Do not
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

The isolated full-desktop installation is still running; closure does not
constitute successful package configuration or a graphical session. Service
starts are blocked in the target root, and no running-host packages change.
[Dependency receipt](receipts/2026-10-21-desktop-resolution.json).

## Configured elementary desktop

The full desktop root now has 1,628 configured packages. The initial install
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

The live installer package sets LightDM's default to the installer session;
its user unit launches the graphical installer directly. The command-line
refusal does not disable that path. Installer admission remains false until
the live session and Apple partition-preserving workflow are integrated.

[Configured-desktop receipt](receipts/2026-10-21-configured-desktop.json).
