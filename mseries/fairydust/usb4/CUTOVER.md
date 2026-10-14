# Cutover checklist: stock kernel to the CI usb4.4 kernel (this M1 Pro)

Status as of 2026-10-14. Follows `REINSTALL-RUNBOOK.md` section 0, `usb4/RECOVERY.md`
and `POST-BOOT-CHECKS.md`. Boxes marked "needs you" need `sudo` or a reboot, which an
unattended session cannot do.

## Ready (done and verified)

- [x] CI kernel package downloaded to `~/mseries-kernel-usb4.4/`, SHA256SUMS all OK
      (run 38589009211, artifact expires 2026-10-16).
- [x] `install-ci-kernel.sh` written and committed (dry run by default, takes UUIDs from
      the running system, backs up `boot.bin`, adds a non-default TEST entry).
- [x] Branch `feat/window-snapping` pushed; first-boot `network` and `quick` fixes included.
- [x] User-level backup written to `~/backup-pre-usb4-cutover` (inventory, home config,
      small documents). **Partial:** the `sudo` parts did not run (see below).
- [x] Rollback known: pick the normal GRUB entry; if the Mac stops before GRUB, restore
      `boot.bin` from macOS (`RECOVERY.md`). macOS is intact (APFS containers present).

## Done on this Mac

- [x] Dry run reviewed (UUIDs matched: root `725346d2...`, LUKS `b6276462...`, ESP `D893-79A4`).
- [x] `install-ci-kernel.sh --apply` ran: `/boot/vmlinuz-linux-asahi-fairydust-usb4`, the
      initramfs and the TEST entry in `/boot/grub/custom.cfg` exist; default entry unchanged;
      `boot.bin` backed up and untouched.
- [x] First boot of the TEST entry: kernel reached systemd, then emergency mode (see below).

## Needs you, in order

1. [ ] Install the modules into the booted root (the fix for the emergency-mode boot; see the
       "First boot result" section for the command). Check: `ls /usr/lib/modules` lists
       `7.1.13-elementary-fairydust-usb4`.
2. [ ] AC power plugged in. The battery shows "Discharging" at 100% because of the charge limit,
       so confirm the cable by eye.
3. [ ] Optional but recommended: `sudo -v && bash mseries/backup/mseries-backup.sh` so
       `secrets.tar` exists (copy it to encrypted media only). Not required for the boot test.
4. [ ] Reboot, choose "elementary OS (M-series, fairydust + USB4 test)" in GRUB.
5. [ ] Post-boot checks: `uname -r` shows `fairydust-usb4`; `lsmod | grep thunderbolt`;
       `ls /sys/bus/thunderbolt/devices`; `lsusb -t`;
       `journalctl -b -k | grep -i "graph endpoint"` is empty; `journalctl -b -p err`;
       then the rest of `POST-BOOT-CHECKS.md`.
6. [ ] After a long uptime: `bash mseries/check-video-decode.sh` (proves the 0003 AVD fix).

If the test entry fails again, reboot and pick the normal "elementary OS (M-series)" entry.

## Known limits

- Dock video does not work (DisplayPort tunnelling is not upstream). Keep the monitor on HDMI.
- Do not suspend with a USB4 link up; do not hot-plug the dock during boot or suspend.
- The CI `boot.bin` (m1n1 1.5.2) lacks the USB4 tunables. The installer keeps the current
  `boot.bin`, so expect the dock's USB2 side only until m1n1 is rebuilt with
  `build-m1n1.sh` (replaces the pre-GRUB stage: take the `boot.bin` backup first).
- The usb4.4 kernel has never been booted anywhere.

## Go / no-go

Go only if steps 1 to 3 are done and the dry run printed the UUIDs you expect
(root `725346d2...`, LUKS `b6276462...`, ESP `D893-79A4` on this Mac).

## First boot result (2026-10-14): kernel boots, /boot fails to mount

The usb4.4 kernel booted to systemd. It then dropped to emergency mode:
`FAT-fs (nvme0n1p4): IO charset iso8859-1 not found` / `Failed to mount boot.mount`.
Cause: `install-ci-kernel.sh` put the kernel modules only in the Arch root (`@`) for
`mkinitcpio`, not in the booted root (`@elementary`), so `nls_iso8859-1.ko` was not
loadable. The kernel config is fine (`NLS_ISO8859_1=m`, same as stock); no rebuild needed.
Fixed in the script. For an install made with the old script, install the modules by hand:

    d=$(mktemp -d /var/tmp/m.XXXX) && dpkg-deb -x ~/mseries-kernel-usb4.4/linux-image-*.deb "$d" \
      && sudo cp -a "$d"/lib/modules/7.1.13-elementary-fairydust-usb4 /usr/lib/modules/ \
      && sudo depmod -a 7.1.13-elementary-fairydust-usb4 && rm -rf "$d"

## Stage 2: device tree in boot.bin (dock USB4 nodes, speaker amps)

First boot of the usb4 kernel works, but with the stock `boot.bin`: no USB4 nodes (no `thunderbolt`
devices, no dock) and `tas2764: Failed to parse devicetree` (speakers) because the kernel expects the
matching device tree. `install-bootbin.sh` swaps only the `t6000-j314s` tree into `boot.bin`
(m1n1 v1.6.1, U-Boot and the other 109 trees stay byte-identical; `swap-dtb.py` passes an identity test).

    sudo bash mseries/fairydust/usb4/install-bootbin.sh ~/mseries-kernel-usb4.4            # dry run
    sudo bash mseries/fairydust/usb4/install-bootbin.sh ~/mseries-kernel-usb4.4 --apply

This changes the stage before GRUB. It writes a backup first (`/boot/m1n1/boot.bin.KNOWN-GOOD-pre-dtb-*`
and `/root/usb4-backup/`). The stock kernel's entry keeps booting with the new tree in most cases, but if
the Mac stops before GRUB, restore from macOS (`RECOVERY.md`). Unverified: whether this m1n1 generates the
USB4 tunables the driver needs; the check is `journalctl -b -k | grep -iE "tunable|acio"` after reboot.
