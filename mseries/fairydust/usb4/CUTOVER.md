# Fairydust USB4 kernel on the M1 Pro

Current status, verified on 2026-10-14 on a 14-inch M1 Pro (`MacBookPro18,3`,
J314s) with a Dell USB-C dock. This records the transformed desktop path; the
factory ISO remains a separate, unverified installation path.

## Verified

- The CI kernel package `7.1.13-elementary-fairydust-usb4` boots from a
  non-default GRUB test entry. The normal entry remains the fallback.
- `/boot`, the encrypted root, the Pantheon session, Wi-Fi, display and GPU
  work with this kernel.
- The matching J314s device tree fixes the speaker amplifier probe and exposes
  the dock's USB4 nodes.
- The dock hub, mouse, keyboard, USB audio and USB3 Ethernet work with the
  matching device tree and pinned newer m1n1.

## Limits and next checks

- DisplayPort tunnelling over USB4 is not implemented upstream; use the Mac's
  HDMI port for an external display.
- Suspend is unsafe while a USB4 link is active. Disconnect the dock before
  suspending.
- The `0003` AVD allocation fix has not been checked after long uptime. Run
  `bash mseries/check-video-decode.sh` on the usb4.4 kernel after the system has
  been up for a while, without manually compacting memory first.
- These results do not qualify the factory ISO or the one-command installer.

## Recovery and tools

Read [`RECOVERY.md`](RECOVERY.md) before changing the boot image. Installer
scripts are dry-run first and make timestamped backups before applying boot
changes. The current helpers are:

- `install-ci-kernel.sh` and `install-modules.sh` for the test kernel and its
  modules.
- `install-bootbin.sh` and `swap-dtb.py` for the J314s device tree.
- `build-m1n1-local.sh`, `install-m1n1-bootbin.sh` and `swap-m1n1.py` for the
  pinned m1n1 binary needed by dock Ethernet.

The original normal GRUB entry remains the first rollback option. For recovery
before GRUB starts, follow `RECOVERY.md` from macOS using the saved known-good
`boot.bin` copy.
