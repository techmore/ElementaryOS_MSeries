# Cleanup and Linux storage expansion

Updated 2026-10-14. The 2026-10-13 layout and capacity notes below the cleanup section are historical; the current reported layout is summarized here. This is planning only: no partition, LUKS, or Btrfs changes were performed for this request.

## Current reported layout

Owner-provided output describes a 931.8 GiB internal SSD:

| Region | Size | Purpose |
| --- | ---: | --- |
| p1 | 500 MiB | iBoot System Container — preserve |
| p2 | 717.1 GiB | macOS APFS |
| Free gap | 112 GiB | Before Asahi partitions; origin must be confirmed |
| p3 | 2.3 GiB | Asahi APFS boot stub — preserve |
| p4 | 500 MiB | EFI, mounted at `/boot` — preserve |
| p5 | 94.7 GiB | LUKS2 containing Btrfs `/@elementary`, mounted as `/` and `/home` |
| p6 | 5 GiB | Apple Recovery — never touch |

The gap precedes the Asahi stub/EFI/Linux root unit, so p5 cannot be extended into it by growing its end. Asahi's [partitioning cheatsheet](https://asahilinux.org/docs/sw/partitioning-cheatsheet/) says to preserve the first iBoot and last System Recovery partitions, treats the stub, EFI, and Linux root as one logical OS unit, and warns against unsorted GPT entries. The [distribution guidelines](https://asahilinux.org/docs/alt/policy/) say disk changes must be limited to free space left by the Asahi Installer. Therefore, do not use this gap unless its Asahi Installer provenance is confirmed; if it was created by a different tool or the origin is unknown, stop.

## Safest candidate for enlarging `/`

If the gap passes that provenance check, the candidate is to create a separate partition wholly inside the gap, encrypt it as a new LUKS2 volume, verify that the installed initramfs can unlock it early, reboot once while the existing root is still single-device, and only then add the mapper to the existing Btrfs filesystem with `btrfs device add`. This increases Btrfs capacity without moving p3/p4/p5. It makes root depend on both encrypted volumes and both remaining on the same physical SSD; it adds no physical redundancy. Do not run `mkfs.btrfs`, balance, or profile conversion as part of the plan.

This is a checkpointed proposal, not authorization to write the GPT or format a device. Before any destructive step, require fresh sector-level output, a verified external backup and LUKS header backup, a confirmed recovery route, a reviewed exact target, and the owner's explicit confirmation. If initramfs early-unlock and Btrfs discovery cannot be proven for this installation, leave the new partition unused and do not add it to root. The repository's factory ISO is not hardware-boot-qualified and must not be treated as a verified recovery path.

See [`procedures/ROOT-EXPANSION.md`](procedures/ROOT-EXPANSION.md) for the read-only preflight, checkpoints, rollback boundary, and official references. The next action is to capture and review that preflight output; do not run partition operations yet.

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

## Old OS retired after explicit approval

The owner subsequently approved retiring @, @home, @log, @fresh, @factory,
@/.snapshots (including snapshot 8), and the final elementary-grow migration
snapshot. Those eight subvolumes were deleted and deletion synchronized.
Only active @elementary (ID 278) and @elementary-home (ID 279) remain.

Before deletion, private local archives captured the old home/configuration
and current boot files under `/home/admin/Documents/storage-recovery/`:
- `old-omarchy-home-and-config.tar.zst` (4,364,425,132 bytes).
- `boot-before-old-os-retirement.tar.zst` (213,071,734 bytes).
Both passed zstd integrity checks. The root-owned directory is mode 0700;
archives are private and are not published in this repository. Ephemeral
Unix sockets were omitted by tar, as expected.

Three stale Omarchy GRUB entries were removed from the old generated
10_linux section after syntax checks. The custom elementary USB4 default,
root/home mounts, and bootloader binaries were preserved. SHA-256 verification
before/after confirmed the active Fairydust kernel, initramfs, m1n1 boot.bin,
and known-good USB4 recovery image unchanged. No reboot/boot qualification
is implied by those checks.

Free space is now **69.4 GiB**, passing the 60 GiB local image-build guard.
No partition resize, metadata-profile change, balance, or filesystem rebuild
was performed. Btrfs metadata and its DUP protection remain required.

The old Omarchy fallback and legacy Arch rebuild chroot are retired. Legacy
Fairydust scripts that mount @/@home cannot be used on this host until a new
Arch build environment is prepared. Rebuild inputs, patches, installed
kernel/modules, and known-good boot recovery copies remain available.
