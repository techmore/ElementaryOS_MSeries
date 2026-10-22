# Build notes — road to a testable arm64 ISO

## New installer and YouTube guest pass — 2026-10-18

Run [39128555434](https://github.com/techmore/ElementaryOS_MSeries/actions/runs/39128555434)
built the factory Brave image from `5c0c60e`. Independent checksum, blank-disk
installation and default installed generic UKI boot passed. The installed launcher,
YouTube dock logo and 480p/1080p video with decoded audio passed in an ARM64 KVM
guest with virgl. [Receipt and limits](video-decode/receipts/factory-2026-10-18/README.md).
Fairydust was disabled for this build; physical Apple qualification remains pending.

## Where upstream stands

elementary/os `main` already builds **both** arches in CI
(`ubuntu-26.04` + `ubuntu-26.04-arm`, outputs `iso_amd64`/`iso_arm64`), and
`mkosi.conf.d/arch.arm64.conf` wires `base`, `sysupdate`, `liveiso`,
`ext-sdk`, `ext-virt`, `driver-nvidia*`, `modules-db`. So the arm64 live ISO
exists as a build artifact — the Apple Silicon question is whether it boots
on and drives M-series hardware, not whether arm64 builds at all.

## Bring-up order (proposed)

Implementation started 2026-10-13: the manual **OS 9 M-series experimental
build** workflow saves installer/checksum artifacts and logs without upstream
publishing credentials. The arm64 liveiso/sysupdate consumers now install
the pruned hardware overlay's runtime packages explicitly. The first full image build succeeded in run 38396499561. Hardware
qualification remains pending; see FIRST-ISO-BUILD.md. See `OS9-HANDOFF.md`.

1. **Kernel decision (see KERNEL-REPORT.md).** Resolute's generic 7.0 arm64
   kernel should boot M1/M2 unaccelerated, but GPU/DCP, AVD decode, sleep,
   and audio need an Asahi-flavoured kernel — evaluate Ubuntu Asahi
   (https://ubuntuasahi.org/) kernel debs for version pinning + apt source.
2. **Build wiring — first arm64 build passed.** `mkosi.images/apple-silicon/`
   (Format=directory, arm64-only) ships modprobe/initramfs config, the
   Wi-Fi resume unit + script, and appends HID modules in postinst; it is
   wired into `arch.arm64.conf` Dependencies, the liveiso aarch64 profile
   (`ExtraTrees`), and sysupdate (`ExtraTrees` + HID `KernelInitrdModules`
   in `mkosi.images/sysupdate/mkosi.conf.d/arch.arm64.conf`). The first arm64 build succeeded; next qualify the generic-kernel boot
   path and verify the produced installer (see FIRST-ISO-BUILD.md).
3. **Asahi-origin packages.** `asahi-audio`, `alsa-ucm-conf-asahi`, and
   `speakersafetyd` are available from Ubuntu resolute/universe. The factory
   image now packages and enables `speakersafetyd` alone; the first-boot DSP
   chain remains excluded until its volume behavior is qualified. The
   transformed desktop passed an output check with the matching PipeWire LV2
   filter plugin, which does not qualify factory-image audio. `avd-fw` and
   `libva-v4l2_request-avd` still need a confirmed Ubuntu source (see
   `packages.arm64`). [Focused receipt](upstream-audits/factory/2026-10-21T2228-0400-speaker-safety.md).
4. **Bootloader on real hardware.** Apple Silicon boots via m1n1/u-boot;
   verify grub-efi-arm64 + shim path works from USB on a test machine, or
   document the Asahi-installer + chroot route as the interim install path.
5. **Hardware test matrix on a spare machine**: display (notch), keyboard/
   trackpad across 20+ reboot cycles (the HID race is intermittent),
   speakers + mic, Wi-Fi connect + suspend/resume, video decode (`mpv` CPU
   comparison), brightness keys, **USB-C dock video + downstream USB**
   (blocked on DP Alt Mode — see `mseries/USB-C-DOCK-DP-ALT-MODE.md`).
6. **apt pinning** for the Asahi source once it exists (Ubuntu analogue of
   omarchy's `Usage = Sync` edge policy), in
   `repos/common-files/etc/apt/preferences.d/`.

## Deliberately not in this project

- Intel Mac support (T2, SPI keyboard, NVMe D3cold, `brcmfmac`
  `feature_disable`) — see PORT-MAP.md.
- Hyprland/Omarchy desktop behavior — this is Pantheon/Gala.
- Touching this Mac's bootloader or macOS install — builds happen in CI or
  containers; installs happen only to external media or a spare machine.

## October 18 factory build and installed-boot corrections

The factory builders run through `build-in-image.chroot` because the build tools
and target development libraries are installed by BuildPackages inside the image;
the mkosi tools tree is a different execution root. Builder pins and output
paths are unchanged.

Ubuntu ARM64's vmlinuz may be an EFI wrapper containing a `.linux` payload and
DTB resources. Nesting that relocatable wrapper inside a generated systemd UKI
fails the inner-kernel relocation check. The ARM64 overlay supplies
`prepare-uki-kernels`; sysupdate runs it before generating UKIs. Original vendor
bytes and hashes are retained under `/usr/share/doc/mseries-kernel-inputs`.
Plain Linux EFI images and complete existing UKIs are left alone. Unexpected
initrd/command-line payloads and invalid inner EFI images fail closed. The live
ISO's GRUB/casper kernel path is unchanged. Apple DTB/boot qualification remains
open; the installed generic-kernel diagnostic was performed only in QEMU/KVM.
