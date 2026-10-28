# M4 Mac mini: Gravity Linux first, elementary on top

Status 2026-10-28. Written from the installer source and Gravity's published image recipe. The first two
stages have not been run by this project, and the elementary step is untested on any hardware.

## Why this order

No installer for elementary targets the M4 mini (Omarchy's lists M4 as refused; Aurora's catalog lacks J773).
`GravityLinux/installer` is the only one that does (`j773gap`, macOS 26.6.2 firmware). It installs a Fedora 44 KDE
image: 500 MB EFI, 1 GB ext4 `/boot`, btrfs root (a subvolume, label `fedora`), `kernel-16k`, GRUB with BLS
entries, an initramfs built with `--no-hostonly`. Elementary then borrows that kernel exactly as
[KERNEL-FLOW.md](../KERNEL-FLOW.md) describes: a second btrfs subvolume, `@elementary`, with the host's modules
and firmware grafted in. Nothing in this repo needs the Gravity kernel patches merged; they are in the host kernel.

## Before you start

1. A full Time Machine backup. The installer shrinks your APFS container (it resizes the partition that holds your data).
2. AC power, a wired **USB keyboard and mouse** for the first boots (U-Boot and GRUB cannot use Bluetooth), and the
   monitor on **HDMI**. Ethernet if you have it; Wi-Fi firmware is copied by the installer.
3. At least 40 GB free for Linux. Choose 80 GB or more if you want elementary plus apps.
4. Read `scripts/bootstrap-prod.sh` and `src/main.py` in GravityLinux/installer. It runs as root and downloads its
   tarball from `cdn.gravitylinux.org` with no signature check that I could find.

## Stage 1: Gravity Linux (you, from macOS Terminal)

```bash
curl -fsSL https://install.gravitylinux.org | sh
```

Choose to resize, give Linux your space, accept the Gravity alpha image, and follow the shutdown/Recovery steps it prints.

## Stage 2: bring-up (on Gravity, first boot)

Join the network, then:

```bash
curl -fsSL https://raw.githubusercontent.com/techmore/ElementaryOS_MSeries/prep/m4-mini-aurora-installer/mseries/gravity/gravity-bringup.sh -o gravity-bringup.sh
bash gravity-bringup.sh --ssh-key "$(cat ~/.ssh/id_ed25519.pub)"
```

That installs git, gh, key-only SSH and Claude Code, and clones this repo. Start `claude` and the session carries on from the machine.

## Stage 3: elementary

```bash
cd ~/ElementaryOS_MSeries
sudo ELEMENTARY_HOST=fedora bash transform/elementary-grow.sh --dry-run
sudo ELEMENTARY_HOST=fedora bash transform/elementary-grow.sh --apply
sudo ELEMENTARY_HOST=fedora ELEMENTARY_PASSWORD_HASH="$(openssl passwd -6)" bash transform/elementary-grow.sh --finalize <user>
```

Reboot and choose "elementary OS (M-series)". Fedora stays the default and the rescue system. `--rollback` removes the
subvolumes and the boot entry.

## Known gaps

- Wi-Fi, Bluetooth and HDMI are listed as working on the M4 mini by Aurora's data; Gravity commits cover the BCM4388
  Bluetooth and display firmware 26.6.x. None of it is verified here.
- `bin/elementary-mac-setup` now runs end to end on this Fedora base: it skips the Arch boot-layout and encryption steps
  (the Gravity image is unencrypted) and installs a kernel-install plugin in place of the pacman hook. Until PR 692 merges,
  pass the branch:

  ```bash
  curl -fsSL https://raw.githubusercontent.com/techmore/ElementaryOS_MSeries/prep/m4-mini-aurora-installer/bin/elementary-mac-setup \
    | sudo ELEMENTARY_ACCEPT_M4=1 bash -s -- --ref prep/m4-mini-aurora-installer --no-encrypt --enable-ssh --ssh-key "$(cat ~/.ssh/id_ed25519.pub)"
  ```
- The elementary desktop step assumes Ubuntu noble ARM64 packages work on the 16K-page kernel.
- The Rust Pantheon apps come from `techmore/mseries-sdk-apps` and have not been built for this host.
