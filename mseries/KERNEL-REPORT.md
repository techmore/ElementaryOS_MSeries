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
