# Expanding the existing elementary OS root on Asahi

**Status:** planning runbook only. No disk or filesystem changes have been made. The machine layout below is from owner-provided output dated 2026-10-14; reconfirm before any write.

## Reported layout

| Partition/region | Size | Role |
|---|---:|---|
| p1 | 500 MiB | Apple iBoot System Container — preserve |
| p2 | 717.1 GiB | macOS APFS |
| free gap | 112 GiB | between p2 and p3; confirm it was created by Asahi Installer |
| p3 | 2.3 GiB | Asahi APFS boot stub |
| p4 | 500 MiB | EFI, mounted at `/boot` |
| p5 | 94.7 GiB | LUKS2 containing Btrfs `/@elementary`, mounted as `/` |
| p6 | 5 GiB | Apple Recovery — never touch |

The gap is before p3/p4/p5, so p5 cannot grow into it by extending its end. The current partition map has not been re-read from the machine during this documentation task.

## Decision

Do not move or resize p3, p4, or p5. Asahi documents the stub APFS container, paired EFI partition, and Linux root as one OS unit. Its policy says it is never safe to alter or rearrange disk structures outside free space left by the Asahi Installer. The 112 GiB gap may be used for this plan only after confirming it was prepared by that installer; if it was created by another tool or its origin is unknown, stop and do not partition it. Asahi also warns that Linux tools can leave GPT entries out of physical order and says to preserve the first iBoot and final Recovery containers.

The best in-place candidate is to create a new partition only in the verified 112 GiB gap, encrypt it with LUKS2, then add its unlocked mapper device to the existing Btrfs root. Btrfs supports adding a device without moving existing data, but root then depends on both encrypted devices. The initramfs must unlock both and discover all Btrfs members before mounting `/`. If the installed elementary initramfs cannot be shown to do this reliably, stop before adding the new device. The repository's factory ISO is not hardware-boot-qualified, so it is not a verified rescue/reinstall path.

This adds usable space, not physical redundancy: both partitions remain on the same SSD. Do not balance or convert Btrfs profiles as part of this operation.

## Checkpointed procedure

### 0. Read-only preflight

From the running elementary OS, capture fresh output. Redact serial numbers or secrets; do not include key material.

```sh
lsblk -e7 -o NAME,SIZE,TYPE,FSTYPE,FSVER,UUID,PARTUUID,MOUNTPOINTS
sudo parted /dev/nvme0n1 unit s print free
sudo sfdisk --dump /dev/nvme0n1
findmnt -no SOURCE,FSTYPE,OPTIONS /
cat /proc/cmdline
cat /etc/crypttab
cat /etc/fstab
sudo btrfs filesystem show /
sudo btrfs filesystem usage -T /
sudo btrfs filesystem df /
sudo btrfs device stats /
dpkg-query -W initramfs-tools cryptsetup-initramfs btrfs-progs
```

Verify that p1–p6 match by type, size, UUID/PARTUUID, and role; Btrfs shows its expected current member and no missing devices/errors; the gap is genuinely unallocated and was left by Asahi Installer; and all boot references use stable identifiers. If installer provenance cannot be established, stop here. Do not infer it from the gap location or size. Using the mapper name shown by `lsblk`, capture `sudo cryptsetup status NAME`. Determine the installed initramfs implementation and prove it can include a second LUKS mapping and scan Btrfs devices before mounting root. Debian crypttab supports an `initramfs` option, but verify the installed version and generated image rather than assuming.

**Stop and send the output for review** if any item is unclear. Exact sector boundaries, UUIDs, current crypttab/fstab, Btrfs profiles, and initramfs behavior are not yet known, so exact partition commands cannot safely be finalized from rounded GiB output.

### 1. Backup and go-ahead

Before any partition-table write, make a full external backup of user data/configuration and restore a sample to verify it. Record LUKS passphrase/recovery details offline. Save a p5 LUKS header backup externally and verify it. Confirm macOS boots and the Mac Recovery/DFU route is known.

**Gate:** no GPT write or formatting until the backup is verified and the owner explicitly confirms the reviewed target and commands.

### 2. Create one partition inside the gap

Use fresh sector-level output to select aligned start/end sectors strictly inside the 112 GiB free range. Create one Linux partition there only. Do not use rounded GiB figures as sector boundaries. If Linux `fdisk` appends an out-of-order GPT entry, follow Asahi's documented expert fix-partition-order operation. Then re-check the GPT and PARTUUIDs; entry numbers may change.

**Checkpoint:** confirm p1–p6 remain present with unchanged physical starts/PARTUUIDs, the new partition is entirely within the former gap, and no other region changed. Stop on any mismatch.

### 3. Encrypt and test early unlock

Only after explicit confirmation of the new partition path, initialize that new partition as LUKS2 and open it under a distinct mapper name such as `root-extra`. This erases the selected partition; never substitute p1–p6. Back up the new LUKS header externally.

Add the new LUKS UUID to `/etc/crypttab` using syntax supported by the installed initramfs. For Debian initramfs-tools, the candidate form is:

```text
root-extra UUID=<new-LUKS-UUID> none luks,initramfs
```

Rebuild initramfs (`sudo update-initramfs -u -k all` for initramfs-tools). Inspect it and its hook order to confirm it contains the required cryptsetup/Btrfs tools, unlocks `root-extra`, scans all Btrfs members, and does so before root mount. Do not use a plaintext keyfile.

**Checkpoint:** if unlock or scan cannot be verified, stop and leave the new LUKS partition outside the root filesystem. Reboot once while root is still single-device to confirm the extra mapping unlocks and the original root still boots. Recover before proceeding if boot fails.

### 4. Add it to the current Btrfs root

After the initramfs test succeeds, open the new LUKS mapping and run the reviewed `btrfs device add /dev/mapper/root-extra /` command. Do not run `mkfs.btrfs`; this is an addition to the existing filesystem. Do not balance or convert profiles.

**Checkpoint:** capture `btrfs filesystem show /`, `btrfs filesystem usage -T /`, `btrfs filesystem df /`, and `btrfs device stats /`. Confirm the new device is present, capacity grew by about the new partition size less LUKS overhead, profiles are understood, and no errors were reported. Reboot; confirm both LUKS mappings unlock, `/@elementary` mounts, and `/` has the larger capacity. Keep the external backup until multiple cold boots and clean filesystem checks.

## Rollback boundary

Before `btrfs device add`, the new partition can remain unused while p5 is still the only Btrfs member. After addition, never delete or reformat that partition directly. Reverting requires both devices unlocked and a successful Btrfs device removal after allocated chunks are moved; that needs its own reviewed plan. If root cannot boot, use the verified recovery route or restore the backup.

## Official references

- [Asahi Partitioning Cheatsheet](https://asahilinux.org/docs/sw/partitioning-cheatsheet/) — special partitions, OS unit, GPT ordering, and cleanup.
- [Asahi Distribution Guidelines](https://asahilinux.org/docs/alt/policy/) — only alter disk structures in free space prepared by Asahi Installer.
- [Asahi FAQ](https://asahilinux.org/docs/project/faq/) — Apple Silicon cannot boot a plain USB OS; internal macOS is needed for install/repair operations.
- [Btrfs device management](https://btrfs.readthedocs.io/en/latest/btrfs-device.html) and [filesystem documentation](https://btrfs.readthedocs.io/en/latest/btrfs-man5.html) — device-add behavior and multi-device initramfs scanning.
- [Debian crypttab(5)](https://manpages.debian.org/trixie/cryptsetup/crypttab.5.en.html) — `initramfs` option.
- [ElementaryOS M-Series repo](https://github.com/techmore/ElementaryOS_MSeries) — current handoff records factory-image hardware qualification status.
