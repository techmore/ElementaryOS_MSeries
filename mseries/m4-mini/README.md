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

Start with [the audit](UPSTREAM-AUDIT-2026-10-21.md). The J713 basic and graphics
series modify shared T8132 code but add Air-specific PMGR/display/GPU profiles.
Do not copy those profiles onto J773g or substitute the per-kernel OS DTB for
the shared bootloader control DTB. Firmware framebuffer handoff is distinct
from native HDMI modesetting. The 16 GB memory map must come from the loader.

Next: inspect the captured display protocol and board admission conditions,
review the full candidate diffs, and determine the minimum J773g-specific port.
Build and physical tests remain outstanding. Public J713 tests cannot close
J773g HDMI, storage, thermal or macOS/Recovery acceptance gates.

Source review: the graphics backend documents a firmware-26.6.2 J713 internal-panel profile and explicit board admission. Its DT uses apple,j713-native-piodma and apple,j713-native-scanout. External-display roles remain excluded; changing a compatible string does not establish J773g HDMI support. U-Boot proposal head cc47d3b7c86deb4094dc186d26799602272e37fb differs from the earlier basic-boot revision 6c1d2d148020.

Verification: 13 immutable source files captured; mutable references rejected before output creation; qualification flags remain false; whitespace check passed. No full build or hardware boot.

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
its memory and framebuffer properties require loader fixups.

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
The first native full-build run remains pending; the wrapper itself has not yet
completed an end-to-end run. Kernel and Mesa Asahi UAPI headers match byte for
byte at the pinned Gravity heads; see the receipt for the precise scope.

## Debian payload packaging

After a successful full build, `package-kernel.py --source SOURCE --build BUILD
--archive PINNED_ARCHIVE --output NEW_DIRECTORY` produces a distinct
`linux-image-elementary-m4-gravity1` payload and copies its corresponding source
archive alongside it. It checks the source archive, resolved config, module
release, required Image/DTB/GPU artifacts, module inventory and display/GPU
vermagic. No maintainer scripts or boot files are packaged. It does not install
anything. Actual end-to-end packaging remains pending the full kernel build;
the current incomplete build was correctly rejected for its missing Image.

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
