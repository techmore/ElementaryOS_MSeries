# Experimental elementary Debian kernel build

Build-only packaging of the same pinned Fairydust source and USB4 patch used
on the working M1 Pro. This does not install packages or write host boot files.
The legacy Arch chroot is unnecessary. Keep the generic VM image separate
until this kernel, modules, DTBs and boot integration are qualified.

## Pinned inputs

- AsahiLinux/linux `ce9f2eba72c061a50b2d790450e90af3439d8c24`, GPL-2.0.
- Archive: `https://codeload.github.com/AsahiLinux/linux/tar.gz/ce9f2eba72c061a50b2d790450e90af3439d8c24`.
- SHA-256 `20ce358acffff4b3de86201975cd68c7aaf241ae010ec3cca9422bbe2b7f34aa`.
- `../usb4/config` and USB4 patch are hash-checked by build.sh. The patch
  includes the Apple router USB3 bandwidth-allocation quirk fix.
- Feature flags match the Arch recipe; only the release suffix changes to
  `7.1.13-elementary-fairydust-usb4` to keep it separate from installed kernels.
- PL011 and its console are built in so native ARM64 VM smoke tests can confirm
  the kernel reaches userspace over QEMU's serial console.
- USB4 also needs m1n1 `57a9339ffd1876e78297b17d34dece8cff8fa1ba`
  and matching DTBs. Kernel packaging alone does not provide those tunables.

## Build

Native aarch64, ordinary user. Build dependencies include make, gcc, flex,
bison, bc, cpio, rsync, libelf-dev, libdw-dev, libssl-dev, dwarves, clang,
libclang-dev, rustc, rust-src, bindgen, dpkg-dev, fakeroot and debhelper.
`make rustavailable` checks the actual source/toolchain combination. The pinned
config enables Rust kernel modules, so the Rust toolchain must include its
matching `rust-src` component; the CI job installs that component into the
active stable rustup toolchain before building.

```bash
export FAIRYDUST_WORKDIR=/absolute/path/to/fresh-work-directory
export FAIRYDUST_SOURCE_ARCHIVE=/absolute/path/to/pinned-source.tar.gz
bash mseries/fairydust/debian/build.sh --prepare
bash mseries/fairydust/debian/build.sh --compile
```

When updating a prepared tree to a newer repository config, run
`build.sh --reconfigure` before `--compile`. Resume modes need the preserved
source tree but no longer need the original source archive.

`--build` prepares and compiles in one run. `--compile` resumes an existing
prepared tree. Do not edit that tree between preparation and compilation.
Preparation requires 5 GiB free; a fresh build requires 40 GiB at start.
Resuming a prepared tree requires 12 GiB. Both build modes stop the process
group if free space falls below 8 GiB. These are conservative guards, not a
measured peak-space guarantee. Debug/BTF stays in the kernel; a separate
434 MiB debug-symbol package is omitted by default.
Jobs default to all CPUs, with explicit dpkg parallelism; `FAIRYDUST_JOBS`
overrides this. The package build includes no installer/host boot operations.

Generated .deb files and checksums go into the work directory. Inspect their
kernel image, modules, DTBs, dependencies and maintainer hooks before adding
them to an isolated image build. Do not install linux-libc-dev or debug/header
outputs blindly on the host. Source archive, config, patch and GPL notices
must accompany any distributed kernel binary.

## Build result — October 13

Native ARM64 build completed as a Debian package. It took about 12 minutes
including modules, device trees and package creation, using up to 10 jobs.
Source/config/patch hashes passed; `olddefconfig`, Rust availability, and the
strict Fairydust config gate passed. The first packaging attempt exposed a
parallel DTB directory-creation race; build patch 0002 precreates that path.
The successful `7.1.13+elementary.usb4.3` Linux image package has SHA-256
`6047f67c33c78fd4c614adadb619aa612919e151497d3941fe8949ae08e084f3`.
This rebuild includes built-in PL011 serial support for ARM64 VM diagnostics.

Package content inspection confirmed:

- Kernel image + modules for `7.1.13-elementary-fairydust-usb4`.
- `appledrm`, Apple ATC PHY, Apple Thunderbolt, CIO reset and Apple AVD modules.
- `t6000-j314s.dtb` for the owner's MacBookPro18,3.
- Runtime dependencies on kmod, linux-base and initramfs-tools (with Ubuntu's
  linux-initramfs-tool alternative).
- Generic Debian kernel maintainer hooks request initramfs updates and pass a
  `/boot/vmlinuz-*` path. Those hooks need adaptation and testing in mkosi.

## Direct kernel VM smoke test

The package kernel booted in QEMU/KVM directly to a temporary initramfs and
executed its `/init` process. The script expands the package's compressed ARM64
kernel image first, uses the host's statically linked BusyBox only inside the
temporary guest initramfs, and attaches no disk or network device:

```bash
VM_CPUS=2 mseries/fairydust/debian/vm-kernel-smoke-test.sh \
  /path/to/linux-image-7.1.13-elementary-fairydust-usb4_7.1.13+elementary.usb4.3_arm64.deb
```

Verified October 13 against package SHA-256
`6047f67c33c78fd4c614adadb619aa612919e151497d3941fe8949ae08e084f3`.
Serial output reached `Run /init as init process`, printed the script's
`FAIRYDUST_KERNEL_USERSPACE_HANDOFF_OK` marker, then powered down. This
qualifies kernel decompression, generic ARM64 QEMU boot and userspace handoff.
It does not test Apple DTBs, m1n1/ESP assembly, installed-system initramfs,
display, audio, USB4 or Mac hardware. No driver is qualified on hardware.
The kernel package is not installed on the host and no release binary is
committed; artifacts remain in `/home/admin/Documents/os9-fairydust-deb-20261013`.

USB4 still needs the pinned m1n1 tunables and Apple DTB/ESP integration.

- Work: `/home/admin/Documents/os9-fairydust-deb-20261013`
- Log: `/home/admin/Documents/os9-fairydust-build.log`
- [Live local kernel monitor](http://127.0.0.1:8767/kernel.html)
- `systemctl --user status elementary-fairydust-deb-20261013f.service`

The monitor.py helper publishes service state for the existing loopback-only
HTTP server. It stops after reporting completion/failure. A build failure or
stopped low-space guard needs review, not automatic package installation.

## 7.1.13+elementary.usb4.4 (video-decode fix)

`usb4.4` adds `0003-avd-job-segments-use-kvmalloc.patch`. The `apple_avd` driver allocated about 8 MiB of
physically contiguous memory (`kzalloc` of `MAX_SLICES` x `struct avd_segment`, an order-10 allocation on
16K pages) for every decode job. Once memory is fragmented the allocation fails
(`page allocation failure: order:10` in dmesg) and hardware video decode errors out or hangs; observed on an
M1 Pro after about 85 minutes of desktop use, and cured by `echo 1 > /proc/sys/vm/compact_memory`. The
segments are only read by the CPU, so `kvcalloc`/`kvfree` is sufficient. The patch applies cleanly
(`patch --fuzz=0`) to the pinned `ce9f2eba72c0` source; it has not been compiled or run yet - the `usb4.3`
hashes recorded above describe the build without it. After building `usb4.4`, repeat a 1080p VA-API decode
(`mseries/install-video-decode.sh`) on a machine that has been up for a while without compacting memory first.
