# How the kernel works on this port

elementary OS here has **no kernel of its own**. It borrows the one the Asahi
Alarm (Arch) side installs. Everything below follows from that.

## Who owns what

| Piece | Lives in | Owned by |
|---|---|---|
| Kernel image `vmlinuz-linux-asahi*` | ESP, mounted at `/boot` | Arch (`pacman`, `linux-asahi*` packages) |
| Initramfs `initramfs-*.img` (unlocks LUKS, shows the elementary unlock screen, mounts the root) | ESP | Arch (`mkinitcpio`, config in the Arch root) |
| GRUB and `grub.cfg`, including the `elementary OS (M-series)` entry | ESP | Arch (`/etc/grub.d/40_elementary-grow`, `grub-mkconfig`) |
| Kernel modules | `/usr/lib/modules/<version>` in **each** root | Arch for its own root; **copied** into `@elementary` |
| Apple firmware (Wi-Fi, etc.) | `/usr/lib/firmware` in each root | copied into `@elementary` |
| Desktop, apps, your files | `@elementary`, `@elementary-home` | elementary / apt |

So the Arch root (`@`) is not leftover: it is the **boot host**. Never delete it.
It is the only thing that can update the kernel or rebuild the initramfs.

## Boot sequence

1. m1n1 → U-Boot → GRUB on the ESP, which reads its config in the clear.
2. You pick (or default to) `elementary OS (M-series)`. GRUB loads the Arch
   kernel + initramfs named in the entry: `vmlinuz-<flavour>` and
   `initramfs-<flavour>.img`, where `<flavour>` is the kernel you were running
   when the entry was written (`BOOT_IMAGE` in `/proc/cmdline`).
3. The initramfs asks for the disk passphrase (elementary unlock screen),
   opens the LUKS container, and mounts the subvolume given by
   `rootflags=subvol=@elementary`.
4. systemd starts from `@elementary`; the kernel then loads modules from
   `@elementary/usr/lib/modules/<running version>` — which is why a matching copy
   must be there.

## Updating the kernel

Only the Arch side can: boot the Arch entry (the rescue system), `pacman -Syu`.
The pacman hook `90-elementary-sync-kernel.hook` then runs
`elementary-grow.sh --sync-kernel`, which copies every module tree under
`/usr/lib/modules` (and the Apple firmware) into `@elementary`. The next time you
boot elementary it runs the new kernel with matching modules. The kernel file
name does not change on update (`vmlinuz-linux-asahi` is replaced in place), so
the GRUB entry keeps working without being rewritten.

If you build your own kernel flavour (fairydust, fairydust-usb4) and it is not
installed by `pacman` under a `linux-asahi*` / `linux-aarch64*` package name, the
hook does not see it: run `sudo transform/elementary-grow.sh --sync-kernel`
yourself, then `--repair-grub` if you want the entry to point at the new flavour.

## What elementary's apt must not do

elementary's Ubuntu packages (`initramfs-tools`, `grub-efi-arm64`, `grub2-common`,
`linux-image-generic`) would, on upgrade, write unused initrd files onto the small
FAT ESP, or run `update-grub` and overwrite the Arch-generated `grub.cfg`.
`mseries/install-boot-isolation.sh` (run automatically when the root is built;
`elementary-grow.sh --isolate-boot` or running it on the booted system for older
roots) turns `update_initramfs` off, forbids Ubuntu kernel packages with an apt
pin, and replaces `update-grub`, `grub-install` and `grub-mkconfig` with no-op
stubs via a dpkg diversion.

## Failure modes, and what you see

| Symptom | Cause | Fix |
|---|---|---|
| Boots, but no Wi-Fi / no display stack | modules for the running kernel are missing in `@elementary` | `sudo transform/elementary-grow.sh --sync-kernel` |
| Prompt for the passphrase never appears, or says wrong passphrase | initramfs lacks `keymap`/`encrypt`, or typed under a different keymap | check `HOOKS` in the Arch root's mkinitcpio config |
| Unlock works, then drops to an emergency shell | entry has the wrong flavour or lost `cryptdevice=` | `transform/elementary-grow.sh --repair-grub`, check `/etc/grub.d/40_elementary-grow` |
| Boot menu has only Ubuntu entries or is empty | an Ubuntu-side `update-grub` ran | boot via the firmware menu / Arch rescue, `grub-mkconfig -o /boot/grub/grub.cfg` on the Arch side, then run the isolation script |
| `/boot` full | stray `initrd.img-*`, or `*.pre-elementary-unlock` backups | delete those; the isolation stops the first kind |
