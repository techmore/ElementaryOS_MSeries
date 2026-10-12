# Build notes — road to a testable arm64 ISO

## Where upstream stands

elementary/os `main` already builds **both** arches in CI
(`ubuntu-26.04` + `ubuntu-26.04-arm`, outputs `iso_amd64`/`iso_arm64`), and
`mkosi.conf.d/arch.arm64.conf` wires `base`, `sysupdate`, `liveiso`,
`ext-sdk`, `ext-virt`, `driver-nvidia*`, `modules-db`. So the arm64 live ISO
exists as a build artifact — the Apple Silicon question is whether it boots
on and drives M-series hardware, not whether arm64 builds at all.

## Bring-up order (proposed)

1. **Kernel capability check.** Does resolute's `linux-image-generic` (arm64)
   carry `appledrm`, `CONFIG_VIDEO_APPLE_AVD`, Apple HID/NVMe/pinctrl, and
   the brcmfmac firmware paths for 4378/4387? If yes, this project is config
   + firmware + userspace. If no, a kernel package is step zero and the
   biggest work item.
2. **New `mkosi.images/apple-silicon/` image** (or a profile drop-in) that
   installs `mseries/` files to their real paths (`/etc/modprobe.d`,
   `/etc/initramfs-tools/modules`, `/usr/lib/systemd/system`,
   `/usr/sbin`), adds the Ubuntu-archive packages from `packages.arm64`,
   and runs `update-initramfs -u` at build time. Wire it into
   `arch.arm64.conf` Dependencies.
3. **Asahi-origin packages.** Find or build Ubuntu sources for
   `asahi-audio`, `speakersafetyd`, `avd-fw`, `libva-v4l2_request-avd`
   (see `packages.arm64`). Until then, document software fallbacks.
4. **Bootloader on real hardware.** Apple Silicon boots via m1n1/u-boot;
   verify grub-efi-arm64 + shim path works from USB on a test machine, or
   document the Asahi-installer + chroot route as the interim install path.
5. **Hardware test matrix on a spare machine**: display (notch), keyboard/
   trackpad across 20+ reboot cycles (the HID race is intermittent),
   speakers + mic, Wi-Fi connect + suspend/resume, video decode (`mpv` CPU
   comparison), brightness keys.
6. **apt pinning** for the Asahi source once it exists (Ubuntu analogue of
   omarchy's `Usage = Sync` edge policy), in
   `repos/common-files/etc/apt/preferences.d/`.

## Deliberately not in this project

- Intel Mac support (T2, SPI keyboard, NVMe D3cold, `brcmfmac`
  `feature_disable`) — see PORT-MAP.md.
- Hyprland/Omarchy desktop behavior — this is Pantheon/Gala.
- Touching this Mac's bootloader or macOS install — builds happen in CI or
  containers; installs happen only to external media or a spare machine.
