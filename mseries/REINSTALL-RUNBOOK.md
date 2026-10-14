# Runbook: replace this install with a fresh one made by `elementary-mac-setup`

This is the real test of the installer. Everything before it was static review,
unit tests, a sandboxed run of the whole flow with stubbed tools
(`mseries/test-installer-flow.sh`), and read-only checks on the M1 Pro. Nothing
had ever run the real boot-layout, encryption, unlock-screen, auto-login or
first-boot steps. Expect to find something; the point of this page is to make
whatever breaks recoverable and to bring back enough evidence to fix it.

## 0. Before you touch anything

1. **Back up.** On the running system: `bash mseries/backup/mseries-backup.sh`
   (edit the device name `nvme0n1` in it if yours differs). Copy `secrets.tar`
   only to encrypted media. The in-place encryption of the new install rewrites
   the whole partition, and there is **no recovery key**: lose the passphrase and
   the data is gone.
2. Note anything that only exists on this machine: Wi-Fi passwords, SSH keys,
   `~/code` repos without a remote (the backup script bundles those).
3. Have a second device with this page and the Asahi docs open
   (https://asahilinux.org/docs/), and a way to reach recovery: a USB-C cable and
   a second Mac, or at least the macOS recovery partition left intact.
4. Charge the Mac and keep it on AC for the whole run. Do not power it off during
   the encryption pass (it is resumable, but do not test that by accident).

## 1. Remove this install (from macOS)

Remove the current Linux install using the Asahi uninstall procedure
(https://github.com/AsahiLinux/docs/wiki/Uninstalling-Asahi-Linux) rather than
deleting partitions by hand: it removes the boot stub and the APFS container the
installer created. Reboot into macOS afterwards and confirm macOS still boots.

## 2. Install Asahi Alarm (from macOS Terminal)

```bash
curl https://asahi-alarm.org/installer-bootstrap.sh | sh
```

Choose `Asahi Alarm Minimal (BTRFS)` and give Linux **at least 60 GB** (the
installer refuses to build with under 40 GB free). Boot into it, log in as
`root` / `root`, and get online with `nmtui`.

## 3. Run the installer

```bash
curl -fsSL https://raw.githubusercontent.com/techmore/ElementaryOS_MSeries/main/bin/elementary-mac-setup | bash
```

It asks: encrypt the disk, username, hostname, password. Then it runs by itself.
What you should see, in order (each `reboot` is automatic, on tty1):

| Step | What happens | How long | Looks like |
|---|---|---|---|
| prerequisites | full `pacman -Syu`; if the kernel changed it reboots first | 5-20 min | package output; maybe a reboot |
| 1 boot layout | `/boot` moves onto the EFI partition | 1-2 min | reboot |
| 2 encryption | on the **next boot**, in the initramfs, you **choose the disk passphrase**, then the whole partition is rewritten | 20-60+ min, silent but with progress lines every 5 s | passphrase prompt, then progress |
| (reboot) | the boot that finishes encryption still has the old kernel command line, so the setup reboots **once more** before building | 1 min | "rebooting once so the kernel command line carries the unlock parameters" |
| 3 elementary | downloads Ubuntu base, installs the desktop, builds the account, unlock screen, auto-login, default boot entry | 30-60 min | long apt output, then reboot |
| first boot | LightDM logs you in; **`elementary-mac-enhance`** then installs Brave, hardware video decode, gestures and the panel patches in the background | 15-40 min | desktop usable meanwhile |

Passphrase prompt notes: type it carefully, the keyboard layout is the one the
setup printed in its plan. The first prompt (while encrypting) is Omarchy's plain
console; from then on every boot shows the **elementary** unlock screen.

## 4. Check it (on the new system)

```bash
elementary-mac-enhance --status        # brave / video / gestures / network / quick / sound / keyboard / files / osk
sudo mseries-power status              # charge limit 80%
vainfo --display drm --device /dev/dri/renderD128   # H.264 / HEVC / VP9 decode profiles
systemctl --user status mseries-docked-lid mseries-audio-watchdog
swapon --show                          # zram
```

Then the checklist in `mseries/POST-BOOT-CHECKS.md` (trackpad over reboots,
Wi-Fi, keys, display, suspend). Audio speakers stay protected by
`speakersafetyd`; start the volume low.

## 5. If something fails

First look at the state, it is read from the machine:

```bash
elementary-mac-setup --status
```

Bring back these files (they survive reboots):

- `/var/log/elementary-mac-setup.log` - everything the resumed steps printed
- `/var/log/elementary-mac-setup-grow.log` - the elementary build
- `/var/log/elementary-mac-enhance.log` - the first-boot enhancements
- `/var/lib/elementary-mac-setup/` - markers (`grown`, `installed`, `cmdline-reboot`)
- on the Arch side: `/etc/mkinitcpio.conf`, `/boot/grub/grub.cfg`, `/etc/grub.d/40_elementary-grow`

Recovery paths, easiest first:

- **Setup stopped partway:** it resumes on every boot while its unit exists. Fix
  the cause, then `elementary-mac-setup --resume`. `--abort` stops it without
  undoing anything.
- **elementary does not boot:** pick the Asahi Alarm entry in the GRUB menu (it is
  never removed). From there `elementary-grow.sh --repair-grub`, or
  `--rollback` to delete the `@elementary` build and try again.
- **A first-boot module failed:** `elementary-mac-enhance --retry <module>`; a
  module that does not apply to the installed package version is reported
  `skipped`, not forced.
- **GRUB menu empty or only Ubuntu entries:** an Ubuntu-side `update-grub` ran.
  Boot Asahi Alarm via the firmware menu, `grub-mkconfig -o /boot/grub/grub.cfg`,
  then run `mseries/install-boot-isolation.sh` on the elementary side.
- **Encryption interrupted:** reboot; the pass resumes and asks for the same
  passphrase. `/boot.old` keeps the pre-move `/boot` until you delete it.

Details of how the kernel, initramfs and GRUB fit together: `KERNEL-FLOW.md`.
