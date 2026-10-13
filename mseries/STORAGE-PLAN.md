# Cleanup and Linux storage expansion

Audited 2026-10-13. This is a plan, not an executed partition resize.

## Current layout

The 931.8 GiB internal SSD is fully allocated, approximately:

| Region | Size | Purpose |
| --- | ---: | --- |
| First Apple container | 0.49 GiB | iBoot system data — preserve |
| Large APFS container | 828.9 GiB | Apple/macOS allocation; used/free space not yet measured |
| Asahi APFS stub | 2.33 GiB | Apple boot integration — preserve |
| EFI partition | 0.49 GiB | Linux boot files/m1n1 — preserve |
| Encrypted Linux partition | 94.7 GiB | Btrfs root and home |
| Last Apple container | 5 GiB | Recovery — preserve |

There is no significant unallocated space after the Linux partition.
Shrinking the large APFS container would release space **before** the Asahi
stub/EFI/Linux partitions, not directly after the existing Linux root.

## Practical first expansion

1. Back up important files and verify the recovery route before any resize.
2. Boot Apple Recovery (or macOS if available). In Terminal, capture the
   read-only output of `diskutil list` and `diskutil apfs list`. Identify
   containers afresh; disk numbers can change. Determine the large APFS
   container's used space and supported shrink limit before choosing a size.
3. Prepare a reviewed resize plan using Apple's command-line tooling. The
   amount reclaimable is not known merely from the 828.9 GiB allocation.
4. Use released space for a **separate Linux build/data filesystem**, mounted
   at a build directory. Keep the existing encrypted root and boot partitions
   in place. This increases Linux's usable internal storage without moving
   its installed OS. Choose encryption and boot-independent mounting before
   formatting anything. No such changes have been authorized or executed.

This leaves `/` at its current size. If the goal is to enlarge `/` itself,
plan an offline backup-and-migration/repartition operation after inspecting
APFS capacity and verifying backup media. Do not move the mounted encrypted
root or promise that Btrfs alone can consume nonadjacent APFS space. Adding
another device to the root Btrfs pool would also require a separate review
of encryption, early-boot unlock, and recovery dependencies.

Asahi's [partitioning guide](https://asahilinux.org/docs/sw/partitioning-cheatsheet/)
explains the boot stub/EFI relationship and recommends `diskutil` instead
of the graphical Disk Utility for this layout. The first/last Apple system
containers must remain intact. This Linux session cannot supply APFS's
actual shrink limits.

## Cleanup performed with owner authorization

- Removed Hugging Face hub/xet downloads, preserving other top-level account
  metadata. These models need downloading again before local use.
- Cleared pip, Playwright browser downloads, Brave cache, and downloaded APT
  packages. Installed applications remain; Playwright browsers may need
  reinstalling before browser tests.
- Saved Fairydust's missing build input as `fairydust/usb4/config` and the
  running kernel configuration as `fairydust/usb4/running-config`.
- Archived both extracted source trees into
  `/home/admin/fairydust-usb4/source-trees-before-cleanup.tar.zst` (452 MiB),
  passed `zstd -t`, then removed only `base/src` and `work/linux-fairydust`.
  Kept source archives, package files, resolution notes, and recovery copies.
- Explicitly approved snapshot cleanup: 4, 5, 6, 7 and migration copies
  `elementary-grow-20261012-102330`, `elementary-grow-20261012-102435`.
  Preserve snapshot 8, migration copy `elementary-grow-20261012-102513`,
  and every installed OS root including the active @elementary/@elementary-home.

Btrfs snapshots share extents, so their apparent 16–18 GiB sizes are not
reclaimable individually. Use measured filesystem free space after deletion,
not the sum of directory sizes. See LOCAL-BUILD.md for the current capacity
check; do not remove older OS roots as if they were caches.

Measured result after cleanup and Btrfs deletion synchronization: **49.6 GiB
free**, up from **37.4 GiB**. All six approved snapshot deletions completed;
latest rollback copies and active roots remain. This is still **10.4 GiB
below** the local full-build guard. No partition or filesystem resize ran.
