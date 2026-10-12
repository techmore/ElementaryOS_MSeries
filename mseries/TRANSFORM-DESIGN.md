# Transform track — grow elementary OS out of a running omarchy-mac (DESIGN)

## Goal

A single command, run on a booted omarchy-mac (Apple Silicon, Asahi), that
produces a **bootable elementary OS (Pantheon on Ubuntu userspace) alongside
the existing system** — new btrfs subvolume, new bootloader entry, old
system untouched and still the default. No ISO, no USB stick, no macOS-side
installer.

## Why this track exists

The image-factory track (`mkosi.images/apple-silicon/`) must solve the
kernel, bootloader, and firmware problems from zero. The transform track
sidesteps all three: the running machine already boots (m1n1 → u-boot →
GRUB), already runs an Asahi kernel with matching modules, and already
holds the Apple Wi-Fi firmware. We reuse all of that and only swap the
userspace.

## Non-goals / hard boundaries

- Never repartition, never touch the ESP contents except through the
  distro's own GRUB tooling (a new `/etc/grub.d/` file + regen).
- Never change the default boot entry. The user selects elementary from the
  boot menu explicitly, every time, until they say otherwise.
- Never redistribute Apple firmware blobs (copied machine-local only).
- The script NEVER runs from macOS — Linux side only. From macOS this repo
  can only be read.
- Default mode is `--dry-run` (plan only). `--apply` performs changes.
  `--rollback` removes the subvolume + GRUB entry.

## Boot math (assumptions → runtime checks)

| # | Assumption | Runtime check (abort message if false) |
|---|---|---|
| 1 | aarch64 Linux, Apple device-tree | `uname -m` + `/proc/device-tree/compatible` |
| 2 | Root on btrfs | `findmnt -no FSTYPE /` |
| 3 | ≥40 GB free on `/` | `df` / `btrfs filesystem usage` |
| 4 | GRUB with `/etc/grub.d` + `grub-mkconfig` | paths + binaries present |
| 5 | Asahi kernel + initramfs in `/boot`, modules in `/usr/lib/modules/<kver>` | version cross-check |
| 6 | Network + `curl` (Ubuntu base tarball download) | probe cdimage |
| 7 | `elementary-desktop` exists in the elementary stable PPA for resolute | `apt-cache show` inside chroot after update |
| 8 | Ubuntu base tarball checksum verifies | SHA256SUMS from cdimage |

Anything failing prints what was expected, what was found, and stops
before changing anything (checks run fully in `--dry-run` too).

## Steps (`--apply`)

1. **Snapshot**: read-only btrfs snapshot of the current root subvolume to
   `@.snapshots/elementary-grow-<timestamp>` (plain `btrfs`, no snapper
   dependency). Rollback never needs it (we only add), but it exists.
2. **Subvolume**: create sibling subvolume `@elementary` at the fs top
   level (mount `subvolid=5` temporarily if `/` is itself a subvolume).
3. **Unpack**: download pinned `resolute-base-arm64.tar.gz` + SHA256SUMS
   from cdimage, verify, unpack into `@elementary`.
4. **Chroot build** (bind `/dev /proc /sys /run`, copy `resolv.conf`):
   - Ubuntu `resolute` main/universe + elementary stable + os-patches PPAs
     (keyrings fetched, fingerprints printed for the user to confirm).
   - Install `elementary-desktop`, `pipewire-pulse`, `pipewire-alsa`,
     `rtkit`, `network-manager` (already a dep — harmless), grub-pc? NO —
     never installs a bootloader. No kernel package either (reuses host).
   - Copy host `/lib/firmware/brcm/<chip>*` (chip detected via `lspci`)
     and host UCM/audio config into the new root.
   - Install the M-series layer: notch modprobe, Wi-Fi resume unit +
     script, firmware-provisioning unit + script (fetched pinned from this
     repo's raw URLs at the recorded commit).
   - Write `/etc/fstab` (UUIDs discovered from host), hostname, user
     account (mirrors invoking sudo user), enable NetworkManager +
     display manager + firmware unit (offline `systemctl enable`).
5. **Boot entry**: drop `/etc/grub.d/40_elementary-grow` (additive,
   `rootflags=subvol=@elementary`, host kernel + initramfs paths),
   `grub-mkconfig` to regenerate. Default order unchanged by construction
   (new entry appended; `GRUB_DEFAULT` untouched).
6. **Report**: print the boot-menu label, the rollback command, and the
   post-boot checklist (trackpad over reboots, Wi-Fi, keys, display).

## Rollback (`--rollback`)

Delete `@elementary`, remove the grub.d file, regenerate GRUB, drop the
temp mounts. Leaves the snapshot until the user deletes it. One command,
no reboot required.

## Known gaps (v1)

- **Speakers**: `speakersafetyd` has no Ubuntu package; speakers stay muted
  until the Asahi audio packaging work lands (same gap as the image track).
- **GPU/video decode**: inherited from the host Asahi kernel side — works
  to the extent omarchy-mac works, since it's the same kernel/modules.
- **HID race fix**: inherited from the host initramfs (omarchy-mac quattro
  already early-loads HID there); the new root adds no initramfs of its own.
- ** elementary installer / encryption / dual fstab edge cases**: out of
  scope; this is a power-user path, documented as such.
- **Untested**: the authoring machine (macOS) cannot execute any of this.
  First run must be `--dry-run` on the real machine, output reviewed, and
  only then `--apply` with a snapshot in place.
