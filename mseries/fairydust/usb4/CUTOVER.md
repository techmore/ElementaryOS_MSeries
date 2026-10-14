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

## Needs you, in order

1. [ ] Re-run the backup with sudo so `secrets.tar`, `blkid`, `parted` and the btrfs
       subvolume list exist. Copy `secrets.tar` to encrypted media only.
       `sudo -v && bash mseries/backup/mseries-backup.sh`
2. [ ] Plug in AC power and keep the Mac on it for the whole run.
3. [ ] Dry run, read every line:
       `sudo bash mseries/fairydust/usb4/install-ci-kernel.sh ~/mseries-kernel-usb4.4`
4. [ ] Apply: same command with `--apply`. The default boot entry does not change.
5. [ ] Reboot, choose "elementary OS (M-series, fairydust + USB4 test)" in GRUB.
6. [ ] Post-boot checks: `uname -r` shows `fairydust-usb4`; `lsmod | grep thunderbolt`;
       `ls /sys/bus/thunderbolt/devices`; `lsusb -t`;
       `journalctl -b -k | grep -i "graph endpoint"` is empty; then the rest of
       `POST-BOOT-CHECKS.md`.
7. [ ] After a long uptime: `bash mseries/check-video-decode.sh` (proves the 0003 AVD fix).

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
