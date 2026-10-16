# Recovery if the bootloader (m1n1 boot.bin) breaks

> **Stale file names (checked 2026-10-16):** the quoted note below names `boot.bin.KNOWN-GOOD-usb4-test` and `boot.bin.KNOWN-GOOD-fairydust-original`, which are not present in `/boot/m1n1/`. Files that exist: `boot.bin.KNOWN-GOOD-pre-usb4-20261015-152345` (most recent), `...-20261015-140455`, `...-pre-usb4-20261014-135219`, `...-pre-m1n1-20261014-142142`, `...-pre-dtb-20261014-141046`. Use one of those in step 4 and re-check with `ls` first. See `REVIEW-2026-10-16-GAPS.md`.

> Copy of `/boot/m1n1/RECOVERY.txt` on the Asahi ESP (the ESP copy is readable from macOS).

```
RECOVERY NOTES (readable from macOS - this is the Asahi EFI system partition, FAT32)
=====================================================================================
Written 2026-10-12 before replacing the m1n1 bootloader with a newer build (USB4 tunables).

SYMPTOM: after the change the Mac does not reach GRUB / shows m1n1 errors / black screen / reboots.
CAUSE:   m1n1/boot.bin is the stage that runs BEFORE GRUB. If it is bad, no OS (elementary, Omarchy)
         can boot, because they all sit behind it. GRUB's other entries cannot help.

FIX (needs macOS; the Linux disk is encrypted, but THIS partition is not):
 1. Power off. Hold the power button until "Loading startup options" appears. Choose macOS
    (or Options -> Continue to macOS Recovery).
 2. Open Terminal (macOS, or Utilities -> Terminal in Recovery).
 3. Find and mount the Asahi ESP (label "EFI - ASAHI", 500 MB, FAT32):
        diskutil list | grep -i "EFI - ASAHI"       # e.g. disk0s4
        diskutil mount disk0s4                       # mounts at /Volumes/EFI - ASAHI
 4. Restore a known-good boot image (pick ONE):
        cd "/Volumes/EFI - ASAHI/m1n1"
        cp boot.bin.KNOWN-GOOD-usb4-test boot.bin            # old m1n1 v1.6.1 + USB4 device trees (last working)
        # or, to go all the way back:
        cp boot.bin.KNOWN-GOOD-fairydust-original boot.bin   # state before any USB4 work
 5. diskutil unmount "/Volumes/EFI - ASAHI"   then restart.

FILES HERE:
  boot.bin                              current image (whatever was last written)
  boot.bin.old                          previous image (overwritten on every update-m1n1 run)
  boot.bin.KNOWN-GOOD-usb4-test         m1n1 v1.6.1 + fixed USB4 DTBs; booted fine on 7.1.13-1-2-fairydust-usb4
  boot.bin.KNOWN-GOOD-fairydust-original  original fairydust DTB image from before the USB4 port
Details: ElementaryOS_MSeries/mseries/fairydust/usb4/README.md
```

Note: the default startup volume is now Linux (`sudo asahi-bless --set-boot "Asahi Alarm Minimal (BTRFS)" -y`). To get to
macOS for the recovery steps above, hold the power button until the boot picker appears and choose Macintosh HD, or run
`sudo asahi-bless --set-boot-macos -y` from Linux first.
