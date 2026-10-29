# Aurora 7.2 wip5 on the J314S (M1 Pro 14"): install record, 2026-10-29

This page lets the laptop be rebuilt without this session's notes. wip5 is unified72 revision 7: omacom/linux-aurora
`2f725546` (7.2.11) with patches 0001–0005 (PR #698), built in CI run 40866985442. The package is
`linux-image-elementary-aurora72-wip5_7.2.11+elementary.aurora72.wip5-1_arm64.deb`, sha256 `658746f5…ace62` (CI `SHA256SUMS`).

## Result

- **Boots** (first good boot 2026-10-29 10:58 EDT). Working: internal panel, external DP monitor, GPU (asahi), Wi-Fi, the six
  tas2764 speaker amps (they log "Failed to parse devicetree" on the first probe and bind on the retry), cs42l84, SEP driver.
- No new kernel errors against wip4, apart from three `apple-dcp … Failed to get dp-phy: -517` probe deferrals.
- Not yet checked by the owner: dock replug, suspend and resume.
- wip4 stays the GRUB default. wip5 is the entry `elementary-aurora72-wip5-trial`.

## How to install it (the way that works)

```bash
sudo bash mseries/aurora/unified72/wip5/stage-wip5.sh ~/.cache/mseries-kernel/wip5/linux-image-elementary-aurora72-wip5_7.2.11+elementary.aurora72.wip5-1_arm64.deb
sudo grub-reboot elementary-aurora72-wip5-trial && sudo reboot
```

`stage-wip5.sh` installs the package, copies `vmlinuz`, and builds the initramfs by **retargeting the working wip4 one**
with `mseries/aurora/prepare-trial-initrd.py`, then audits it with `audit-trial-initrd.py`. The audit checks that the early
archive and every non-module entry are unchanged and that all 91 modules match the package. Last, it copies the wip4 GRUB
entry as a TRIAL entry.

**Why not mkinitramfs:** the J314S boots an Arch mkinitcpio initramfs. The kernel line carries `cryptdevice=`, and the image's
hooks are `base asahi udev … encrypt`, with plymouth. initramfs-tools ignores `cryptdevice=`. The first wip5 staging
used `mkinitramfs` and died before the passphrase prompt on every boot, leaving no journal. mkinitcpio itself is not
installed on this machine, so retargeting is the only path.

## Graphical unlock screen

The initramfs already has plymouth with the elementary theme, and the `encrypt` hook asks through `plymouth ask-for-password`.
The trial entries boot with `loglevel=7` and no `splash`, so the prompt is plain text with no cue. To get the graphical prompt
on the wip5 entry only:

```bash
sudo cp /boot/grub/custom.cfg /boot/grub/custom.cfg.before-splash && sudo sed -i '/linux \/vmlinuz-aurora72-wip5 /s/loglevel=7/quiet splash loglevel=3/' /boot/grub/custom.cfg
```

## Touch ID on wip5

On wip5 with the default guard (`xart_guard` 1), the enclave **matches** the enrolled finger. fprintd lists
`#0: right-index-finger`. The host then fails the verify: the kernel logs `xART guard: refused to rewrite a kind-4 record this
Linux install did not create`, then `post-match identity-bag snapshot failed`. That is the documented cold-boot M1 behaviour
([../../../aurora-sep/XART-GUARD.md](../../../aurora-sep/XART-GUARD.md)). The maintainers' reference M1 Pro runs `xart_guard=0` daily.

Owner decision, 2026-10-29: try it with a backup first. `touchid-guard-off.sh` does both steps:

1. A byte-exact, read-only `dd` of `nvme0n1p1` (iBootSystemContainer, where xART lives), `nvme0n2` and `nvme0n3`, each
   verified against the device. They go to `/var/lib/mseries-kernel-tests/xart-backup-<UTC>/` (root only, with `SHA256SUMS` and
   `layout.txt`). **These images are this Mac's enclave state. Never commit them.** Keep a second copy off the machine (for
   example a root-only directory on the SER8). Otherwise a wiped laptop loses the only way to restore them.
2. A separate GRUB entry, `elementary-aurora72-wip5-xartguard-off-trial`, the wip5 entry plus `apple_sep.xart_guard=0`. The
   normal wip5 entry keeps the guard on. Nothing is armed. Undo: copy `custom.cfg.before` back from the backup directory.

Test order: boot the guard-off entry once, run `fprintd-verify` (enrol again only if it fails), then boot macOS and check that
macOS Touch ID still works. Write the results here and in [TOUCH-ID-STATE.md](../../../aurora-sep/TOUCH-ID-STATE.md).

**Restoring xART is a last resort.** Writing `nvme0n1p1` back with `dd` replaces the whole Apple boot container. Do it only if
macOS Touch ID or boot breaks *and* the steps the maintainers suggest have failed. Do it from this Linux install or from
recovery, never while macOS is running, and only with the image from the same Mac.
