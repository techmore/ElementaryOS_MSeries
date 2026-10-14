# Kernel capability check — Ubuntu resolute generic (arm64) vs Apple Silicon

Initial research: 2026-10-12, from Asahi docs and Ubuntu metadata. Updated
2026-10-13 with the actual built ISO kernel config and the owner's running
Fairydust config. The ISO has booted in an ARM64 VM; Mac factory-image boot
remains untested. Historical upstream capability expectations below are not
hardware-test results.

## Verified configuration gap (October 13)

Compared the local 89e959d image's `/boot/config-7.0.0-38-generic` with
`mseries/fairydust/usb4/running-config` captured from the working
`7.1.13-1-2-fairydust-usb4-ARCH` host:

| Option | Working host | Built generic image |
| --- | --- | --- |
| CONFIG_DRM_APPLE | m | Not declared |
| CONFIG_DRM_ASAHI | y | Not declared |
| CONFIG_DRM_APPLE_AUDIO | y | Not declared |
| CONFIG_RESET_APPLE_CIO | m | Not declared |
| CONFIG_USB4_APPLE_SOC | m | Not declared |
| CONFIG_VIDEO_APPLE_AVD | m | Not declared |
| CONFIG_PHY_APPLE_ATC | m | m |
| CONFIG_SND_SOC_APPLE_MCA | m | m |

This confirms a source/kernel packaging blocker for matching the installed
Mac's graphics/USB4 feature set. Missing options are reported exactly as
absent from this config, not as a physical hardware test. The generic ISO's
graphical QEMU installer uses virtual hardware and does not qualify Apple
display/GPU/audio. Next: qualify a reproducible Asahi kernel package and its
boot/firmware path before promising an M1 Pro desktop from the factory ISO.

## Base facts

- elementary `main` targets Ubuntu **resolute** (26.04); the arm64
  `linux-image-generic` resolves to a **7.0.0-xx-generic** kernel
  (packages.ubuntu.com, resolute arm64).
- Asahi feature-support tables (M1/M2, asahilinux.org/docs) record what is
  upstream at 7.0 and what remains Asahi-only.

## In upstream 7.0 (generic kernel should have these)

NVMe (5.19), PCIe incl. T6020 (5.16–6.16), cpufreq (6.2), DART with 4-level
pagetables for M2 Pro/Max/Ultra (6.18), I2C/GPIO/USB-PD (5.16), MCA (6.1+),
SPI + SPI NOR (6.15), ADP display pipe + Z2 touchbar digitizer (6.15), SMC
core/GPIO/reboot (6.17–6.18), SPMI (6.16), RTC + USB2/3 over TB ports (7.0),
brcmfmac device IDs for BCM4378/BCM4387 (6.3).

Expectation: a resolute generic arm64 kernel **boots M1/M2 to an
unaccelerated console**, sees NVMe/USB, and exposes the Wi-Fi hardware to
`brcmfmac`.

## Still Asahi-only (generic kernel lacks these)

- **Display/GPU**: DCP (`appledrm`) and the AGX GPU driver are out-of-tree
  (Rust abstractions pending; only the uAPI header merged in 6.15). No
  acceleration, no notch control, likely no backlight niceties.
- **Video decode**: `CONFIG_VIDEO_APPLE_AVD` is an unmerged patch series
  (v2 Sep 2026, reviewed but not landed). No hardware decode on generic.
- **Suspend/sleep + cpuidle**: needs Asahi's WFI/WFE hack, which upstream
  explicitly cannot take. Sleep/wake and battery life will be poor.
- **Speakers/mic**: Asahi audio DSP chain + `speakersafetyd`; bus-keeper
  bits merged for 7.1, the rest downstream.
- **SEP/Touch ID, Neural Engine, Thunderbolt/DP-alt, encoders**: WIP/TBA/
  out-of-tree.
- **Wi-Fi firmware**: `brcmfmac` drivers are upstream but Apple firmware
  blobs are NOT in linux-firmware. Asahi's installer extracts them from
  macOS into the EFI partition at install time. Any elementary install path
  needs an equivalent first-boot firmware step (see below).

## Consequences for this project

1. **A daily-driver image needs an Asahi-flavoured kernel**, not
   `linux-image-generic`. Candidate source: the community Ubuntu Asahi
   project (https://ubuntuasahi.org/) kernel debs; evaluate version
   pinning + apt source before wiring into `base` or `apple-silicon`.
2. **Generic image scope remains limited**: graphical installer startup has
   been observed in an ARM64 VM. Boot, framebuffer, storage, USB, firmware,
   and sleep on a physical M1 Pro remain unverified for that image. Do not
   infer Mac desktop readiness from virtual-hardware boot.
3. **Wi-Fi firmware extraction** must be designed regardless of kernel
   choice: copy Apple firmware from macOS at install time (Asahi installer
   precedent), never redistribute the blobs.
4. **Verify before claiming**: diff the actual resolute arm64 kernel config
   (`CONFIG_ARCH_APPLE`, `CONFIG_VIDEO_APPLE_AVD`, `CONFIG_DRM_APPLE_*`,
   `CONFIG_NVME_APPLE`, `CONFIG_BRCMFMAC*`) from Ubuntu's kernel git or a
   built image's `/boot/config-*`, and confirm `linux-firmware` contents
   for `brcm/brcmfmac4378*` / `brcmfmac4387*` and `apple/avd-fw*`.

## Signed Ubuntu Asahi candidate inspected — October 13

Public upstream recipe at
[UbuntuAsahi/ubuntu-asahi](https://github.com/UbuntuAsahi/ubuntu-asahi/tree/ed2868b96efe0eaa32fe87b706eba5071f679e1c)
targets resolute and selects `linux-asahi-arm`. Read-only archive inspection
confirmed the resolute arm64 candidate `7.0.0-1002.2` (metapackage version
`7.0.0.1002.2`). No repository was added to the host and no package installed.

Provenance chain checked:

- [Launchpad archive API](https://api.launchpad.net/1.0/~ubuntu-asahi/+archive/ubuntu/ubuntu-asahi)
  reports signing fingerprint `F5BFDB467341BF02DBC113AB39CC27E17A201624`.
- `gpgv` verified the [resolute InRelease](https://ppa.launchpadcontent.net/ubuntu-asahi/ubuntu-asahi/ubuntu/dists/resolute/InRelease)
  signature against that key, fetched from keyserver.ubuntu.com.
- SHA-256 of arm64 Packages.gz matched the signed release:
  `ce75a0e9d6754659842d4d818ad057869780a9900783ab505f6e891c86ffda06`.
- Kernel image package hash matched index:
  `6e67ce4a2ae4d49c2f74f3e186db1a663e9360345b5cea62ae06b656462b0bbb`.
- Companion buildinfo package hash matched index:
  `007d8fca1a96586a35c9cd0f2c4654fa4b40ee3d038a813842ca09484c21526e`.

Its buildinfo config SHA-256 is
`dd30cbe7c40305abdbbd63e6271ab26330894fdc5bb3b7a6c0902a565710528e`.
`check-kernel-config.py` passes baseline symbols: 16K pages=y, DRM_APPLE=m,
DRM_ASAHI=m, DRM_APPLE_AUDIO=y, PHY_APPLE_ATC=m, SND_SOC_APPLE_MCA=m.
RESET_APPLE_CIO, USB4_APPLE_SOC and VIDEO_APPLE_AVD are absent, so the
`--require fairydust` gate fails. The preserved working host config passes
that stricter gate. This is a candidate for baseline packaging, not parity
with the working custom kernel or a verified hardware boot.

The upstream chroot recipe explicitly assembles m1n1 + Apple DTBs + gzip'd
U-Boot into its image ESP. Kernel postinst invokes kernel hooks, initramfs
and bootloader updates. Adapt these only inside an isolated image build;
never run the upstream chroot recipe against this host. Before integration:
inspect modules/DTBs, pin source/license and dependencies, simulate apt
resolution in resolute, and design firmware and image-only boot hooks.

Reproduce a config gate (exit 1 means missing required options):

```bash
python3 mseries/check-kernel-config.py /path/to/extracted/config
python3 mseries/check-kernel-config.py /path/to/extracted/config --require fairydust
```

Six regression checks cover absent/disabled options, module-vs-page ABI,
invalid input, the preserved working kernel, and required built-in VM console.
CI runs them. Passing the
gate does not prove module contents, firmware availability or hardware boot.


## Native Fairydust Debian package built — October 13

The port in `mseries/fairydust/debian/` built successfully on native ARM64.
Pinned Fairydust source + project USB4 patch, all ten CPU jobs, config gate,
DTB race fix and package dependency metadata are recorded in its README. The
resulting private `.deb` is version `7.1.13+elementary.usb4.3`; after adding
built-in PL011 console support for direct VM testing, its image SHA256 is
`6047f67c33c78fd4c614adadb619aa612919e151497d3941fe8949ae08e084f3`.
Contents include modules for appledrm, ATC PHY, Thunderbolt/Apple ACIO, CIO
reset and AVD, plus `t6000-j314s.dtb`. Direct QEMU/KVM boot reached an
initramfs userspace marker; see `VM-SMOKE-TEST.md`. It has not been installed
as an OS or booted on Mac hardware. Next: adapt its `/boot` and initramfs
maintainer hooks to an isolated mkosi profile, add the matching pinned
m1n1/DTBs and dependencies, then test that installed-system image. The generic
installer is verified separately.

## m1n1 stage-2 assembly audit — October 13

Inspected the hash-pinned Ubuntu Asahi packages without installing them. The
m1n1 package supplies `/usr/lib/m1n1/m1n1.bin` and `/etc/m1n1.conf`; U-Boot
supplies `/usr/lib/u-boot/apple_m1/u-boot-nodtb.bin`. Neither package contains
`update-m1n1`. Ubuntu's separate `asahi-scripts` 20250713-1ubuntu1 package
contains that tool and kernel hooks; its verified SHA-256 is
`374780681de7d2b555cbbd0c8a7e7a07e235defdfa84778c26ece398587efcf9`. Its
default DTB lookup does not point at our kernel package's
`/usr/lib/linux-image-7.1.13-elementary-fairydust-usb4/apple` directory, so an
installed profile must explicitly pin both `DTBS` and `U_BOOT` before enabling
kernel-triggered updates.

In `/tmp` only, assembled and checked an Asahi stage-2 payload from the pinned
m1n1/U-Boot packages plus the Fairydust package's 41 `t6*.dtb`/`t81*.dtb`
files. The 5,028,827-byte result SHA-256 is
`3ad88d5e46b78ea693a5dc54cf05bd8762fe45ac49ee5c70cdb8c49884657eb2`. Checks
confirmed the m1n1 prefix, FDT magic on each DTB, USB4 tunable/DROM strings in
m1n1, and that the gzip member expands byte-for-byte to the pinned U-Boot
binary. This matches the documented Asahi concatenation order. The test file
was not copied into an ISO, disk image or ESP.

Next: integrate an explicit DTB/U-Boot selection in the Fairydust image, put
the assembled payload at the correct ESP path in a disposable install image,
and boot that image in QEMU where possible. The host's shared ESP remains out
of scope. See the [Asahi boot-process guide](https://github.com/AsahiLinux/docs/blob/main/docs/alt/boot-process-guide.md)
and [upstream update-m1n1 script](https://github.com/AsahiLinux/asahi-scripts/blob/main/update-m1n1)
for the reference payload layout and implementation.

## Reproducible m1n1 payload assembly — October 13

Added `debian/assemble-m1n1-bootbin.py` as a non-root, image-local equivalent
of the upstream concatenation recipe. It requires the M1 Pro
`t6000-j314s.dtb`, validates every selected Apple DTB's FDT header, sorts the
DTBs, writes a deterministic gzip member for U-Boot, filters m1n1 config to
the upstream-supported keys, and atomically replaces only the requested
output file. It never locates, mounts, or writes an ESP. Four integration
tests cover payload layout/reproducibility, invalid-DTB preservation, missing
M1 Pro DTB failure, and refusing to overwrite a source DTB.

Ran it against the exact locally built kernel package and hash-pinned m1n1
and U-Boot packages. It selected all 41 Apple DTBs and generated a 5,028,282
byte payload with SHA-256
`049c5bf29e5e4f379e44e8ef8fffce3a018ede03ee19676c98cc6ee6e8608f8d`.
The gzip member at offset 4,729,699 expands byte-for-byte to the packaged
635,960-byte U-Boot binary. This reproducible result differs from the earlier
manual assembly's gzip timestamp/metadata; both contain the same binaries and
DTBs.

The Fairydust workflow now extracts the generated payload into its temporary
`sysupdate/mkosi.extra/efi/m1n1/boot.bin` tree. The sysupdate ESP definition
copies `/efi` to the ESP root, producing the Asahi-required
`/m1n1/boot.bin` path in the disposable target disk image. Before ISO
assembly, `verify-m1n1-esp.py` reads that disk image's GPT, copies the ESP file
out through mtools without mounting or writing the image, and requires its
SHA-256 to match the generated payload. The staged file exists only in the
opt-in Fairydust CI workspace; no host ESP is involved. This integration is
implemented. The first full CI build completed mkosi and produced a
timestamped whole-disk image plus separate partition images, but the workflow's
overbroad `elementary_*.raw` guard counted partition images as disk images and
stopped before ESP verification. The selector is now restricted to the exact
timestamped whole-disk filename. The rerun, [GitHub Actions run 38479577898](https://github.com/techmore/ElementaryOS_MSeries/actions/runs/38479577898),
passed end to end. Its read-only ESP check found `/m1n1/boot.bin` at GPT ESP
offset 1,048,576 and verified all 5,028,282 bytes against SHA-256
`049c5bf29e5e4f379e44e8ef8fffce3a018ede03ee19676c98cc6ee6e8608f8d`.
The experimental installer is
`elementaryos-9.0-daily-arm64.20261013230825.iso` (7,482,648,576 bytes),
SHA-256 `89c74fa25ac72dd8f20f7eb42e456c929ed828f791f77af3edb6f5ce1b7b259d`.
It is available as the run's `os9-mseries-arm64-38479577898` artifact for
seven days. The ESP was checked inside the disposable image; this does not
qualify boot on Apple hardware.
