# Backup before a fresh install

Written 2026-10-14 from the running M1 Pro (MacBookPro18,3), kernel 7.1.13-1-2-fairydust-usb4, elementary OS 9 Early Access. No fixes were made while preparing this. The backup script is read-only.

## Run it

```sh
bash mseries/backup/mseries-backup.sh        # writes ~/backup-pre-reinstall-<date>/
```

It needs passwordless sudo for `/etc` and `/boot`. The first run on 2026-10-14 produced 334 MB and passed a checksum verification (`SHA256SUMS` inside the folder).

**The folder is on the disk that will be wiped.** Nothing is safe until it is copied off the machine. At the time of writing, `/mnt/backup` (about 240 GiB free earlier) and `/mnt/nas14tb` were empty, unmounted directories, so no destination was reachable. Copy the folder to an external disk or another machine, then check `sha256sum -c SHA256SUMS` there. `secrets.tar` holds Wi-Fi keys, SSH and GPG keys, keyrings, tokens and Tailscale state: copy it only to encrypted media.

## What is in the backup

| Part | Contents |
| --- | --- |
| `inventory/` | Partition table, UUIDs, fstab, crypttab, btrfs subvolumes, package lists (dpkg, apt-manual, snap, Flatpak, pip), enabled services and timers, loaded modules, kernel command line, dconf and Pantheon settings, GRUB config, boot-entry listing, power and audio state |
| `config/etc.tar.gz` | `/etc` without shadow files, host SSH keys, Wi-Fi connections and credential stores |
| `config/usr-local.tar.gz` | `/usr/local`, including the saved original Wi-Fi resume script |
| `boot/boot-vfat.tar.gz` | The whole `/boot` ESP: m1n1 `boot.bin` plus the `KNOWN-GOOD` copies, GRUB, three kernels and initramfs images, and **`vendorfw` (Apple firmware extracted from this Mac; never redistribute)** |
| `home/` | Dotfiles, `~/.local/bin` and `libexec`, user systemd units, app and agent settings (Claude, Codex, OpenCode, Crush, mseries state), and small non-git documents |
| `git/` | Diffs and untracked files for repos with uncommitted work, plus a bundle for any repo with no remote |
| `secrets.tar` | See above |

## What is not in it, and why

| Item | Size | Reason / action |
| --- | --- | --- |
| Git repositories with a remote | 4.3 GB in `~/code` | Every repo in `~/code` was clean and fully pushed on 2026-10-14. Re-clone them. |
| Local model weights and MLX runtime (`~/.local/share/mlx-omarchy`, Hugging Face cache) | about 7 GB | Re-downloadable. |
| Podman containers, Flatpak data | 5.1 GB + 3.4 GB | Re-installable; see `inventory/flatpak-list.txt`. |
| `~/Downloads` | 8.8 GB | **Not copied. Look through it before wiping.** |
| OS 9 build trees, test ISOs, Fairydust deb build (`~/Documents/os9-*`, `~/fairydust-usb4`) | about 18 GB | Rebuildable from the repo; the installed kernel files and their checksums are in `/boot` and `fairydust-installed-before-retirement.sha256`. |
| Browser profiles and app caches | | Not captured. Sign in again, or copy a profile by hand if you need local history. |
| The macOS partitions (`nvme0n1p1`, `p2`, `p3`, `p6`) | 720 GB | Leave untouched. They hold iBoot and the stub that starts m1n1. |

Forks with local, uncommitted edits (coreglass, elementary-panel-power, mesa-mlx-compute, omarchy-ane) are saved as diffs under `git/`.

## Disk layout to preserve

`nvme0n1p4` (500 MB, EFI, `/boot`) and `nvme0n1p5` (94.7 GB, LUKS, btrfs with `@elementary` and `@elementary-home`). A reinstall should reuse these two partitions. See `inventory/partition-table.txt` and `blkid.txt` for exact values.

## Restore order

1. Boot the new install; unlock and mount; restore `/boot/vendorfw` only if the installer did not extract firmware.
2. Re-clone `~/code`; `git apply` the saved diffs where still wanted.
3. Restore `home/` archives, then `secrets.tar` (permissions matter for `.ssh` and `.gnupg`).
4. Reinstall packages from `inventory/apt-manual.txt`.
5. Re-run the project installers (`mseries/install-*.sh`) and re-enable the user units.
6. Check `m1n1/boot.bin.KNOWN-GOOD-*` before changing anything about boot.

## State to compare after the reinstall

Dock hub, mouse and Ethernet worked; displays did not. Lid-open resume worked, but the login needed the power button. Open bugs and the parity gaps are in [`BUG-FIX-ROADMAP.md`](BUG-FIX-ROADMAP.md) and [`ROADMAP.md`](ROADMAP.md); the public view is the [GitHub Pages site](https://techmore.github.io/ElementaryOS_MSeries/).
