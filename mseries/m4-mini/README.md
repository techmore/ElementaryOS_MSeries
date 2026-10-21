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
