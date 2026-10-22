# M4 Mac mini preparation

**Hosted baseline result:** Revision-2 kernel, GLVND Mesa and boot-chain jobs have succeeded.
Downloaded kernel/Mesa packages and the boot bundle pass local checks. Their
prepared inputs resolve the full image graph; complete image assembly and native
M4 support remain unvalidated.
[Kernel](receipts/2026-10-21-hosted-kernel-success.json),
[Mesa](receipts/2026-10-21-hosted-mesa-success.json),
[boot chain](receipts/2026-10-21-hosted-boot-success.json),
[full-graph preflight](receipts/2026-10-21-all-hosted-image-preflight.json).

The newly identified scheduler initialization backport is revision 3 and is
not included in those baseline results. Its full compile is pending below.

Research target: expected Mac16,10 / J773g / T8132. Owner confirms 16 GB RAM,
1 TB SSD, 10 Gb Ethernet, macOS 27 and HDMI output. Confirm the
machine identity before physical deployment; offline research bundle assembly does not qualify native dual boot.

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
