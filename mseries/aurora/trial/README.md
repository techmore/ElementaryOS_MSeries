# J314S .20-enh1 next-boot trial — 2026-10-18

## Current selection: diagnostic one-shot armed, no reboot performed

The owner subsequently authorized exactly one diagnostic boot. Verified
`next_entry=elementary-aurora20-enh1-diagnostic`; running kernel is still `.20`.
GRUB consumes this selection before loading the kernel. If it hangs, retain the
last messages, power off if unresponsive, and select
**elementary OS (M-series full-height desktop)** at the next GRUB menu to use `.20`.
[Arming receipt](../hardware-tests/2026-10-18-j314s-enh1-diagnostic-armed.json).
Earlier staging/no-arming records below describe the prior state.


## Latest result: owner-reported hung candidate boot

The October 18 evening trial did not complete boot. The machine is back on
`.20`, no candidate journal/pstore diagnosis was retained, and `next_entry` is
empty. [Offline investigation and diagnostic preparation](../hardware-tests/2026-10-18-j314s-enh1-boot-hang.md)
records what was checked and the separate uninstalled diagnostic initramfs.
The diagnostic image is now staged separately as
`/boot/initrd.img-7.1.12-elementary-aurora20-enh1-diagnostic`, with non-default
manual entry `elementary-aurora20-enh1-diagnostic`. [Staging receipt](../hardware-tests/2026-10-18-j314s-enh1-diagnostic-staging.json)
confirms that grubenv and original kernel/initramfs/boot payload hashes are
unchanged. No test is armed and no reboot has been performed.
The original staging and proposed test steps below are historical context; do not rearm
or repeat the trial without a new explicit owner request. No candidate hardware
boot qualification or driver fix is claimed.


## Additional display acceptance for this trial

The owner subsequently enabled built-in VRR in the current desk profile on .20.
[Scoped smoke and explicit VRR/dock checklist](../hardware-tests/2026-10-18-j314s-vrr-and-boot-archive.md#next-kernel-vrr-acceptance)
now accompany the next-kernel trial. Kernel activation appeared in only 3/25
samples; sustained behavior remains open. Capture focus/presentation state,
validate docking/sleep separately, and match VRR plus cropped/full-height modes
on both kernels before any power comparison. The earlier frozen baseline is
unchanged. Fairydust test boot files/entries were archived; both Aurora lanes
and stock recovery remain. This documentation update does not arm a new reboot.

Owner explicitly requested staging .20-enh1 for the next boot, retaining the
running .20 as fallback, and beginning hardware/power measurements. The frozen
build remains hardware-untested until a successful candidate boot is observed.

The previous cropped-mode energy baseline is not directly comparable to the
full-height trial. Match display controls on both kernels before power A/B.

## Installed state

- Package `linux-image-elementary-aurora-enhancements`, kernel
  `7.1.12-elementary-aurora20-enh1`, from frozen build1; original package SHA256
  `185f1fa6135739d3129a9d44025b92321d926df82a8a07fd5a3bc3fd95d34992`.
- Separate image `/boot/vmlinuz-aurora20-enh1` and initramfs
  `/boot/initrd.img-7.1.12-elementary-aurora20-enh1`.
- `next_entry=elementary-aurora20-enh1`. GRUB consumes it once. The owner-approved
  trial now passes `appledrm.show_notch=1`, loading the installed native notch-aware
  Wingpanel on that same reboot. Later normal boots select `mseries-full-height`,
  which uses the retained .20 kernel with the same full-height setting. The
  visible five-second menu and cropped .20 recovery entries remain available.
  This display change is separate from the desktop profile; profile `--revert`
  does not undo the trial's flag. Restore it to 0 before trialing stock Wingpanel.
  Exact pre-change config: `/boot/grub/custom.cfg.pre-full-height-trial`.
- Existing `.20` image/initramfs and shared `boot.bin` retain their exact hashes.
  The candidate J314S DTB is byte-identical to the active .20 DTB, so no shared
  m1n1/DTB change was needed. Other kernel entries remain present.
- Exact backups and the local staging report are in
  `/var/lib/mseries-kernel-tests/staging/20261018T095901Z/` (root-private).

`prepare-trial-initrd.py` prepares an offline image from the **working Arch
mkinitcpio initramfs**. Its early CPIO bytes, init/cryptsetup/encrypt hooks,
keymap, firmware and all nonmodule entries are preserved. Only the kernel's
module tree and module list change, with the complete candidate dependency
closure and regenerated depmod indexes. Every selected module's vermagic is
checked. The real preparation selected 93 modules, including DCP fabric core,
DRM DMA, dm-crypt and btrfs. This does not prove the next root unlock succeeds.
The generated initramfs is separate from the immutable upstream build assets.

## Capture running now and after reboot

A root-owned snapshot of qualification/smoke/capture code is installed under
`/usr/local/lib/mseries-kernel-trial/`. `/etc/mseries-kernel-trial.json` pins
both installed images, selected module/DTB hashes and the shared boot payload.
The user timer `mseries-kernel-trial.timer` starts one capture per boot after
the user manager starts. The runner waits for five minutes of uptime and an
active display context, then samples SMC power/idle accounting for 120 seconds,
records CPU busy fraction and read-only input/network/Bluetooth/temperature
inventory, and runs the surfaceless GPU readback + 1 MiB fsync smoke tests.

An unsupported kernel, changed image/module/boot hashes, or mismatched live GNU
build ID is refused. Results never manufacture suspend, recovery, feature or
energy A/B acceptance. A failed kernel-health check retains its receipt and
skips the active GPU/filesystem smoke subprocess. No display/audio/power policy or experimental sleep
parameter is changed; no Touch ID sensor is opened. The timer does not reboot,
suspend, rearm the candidate, or promote a release.

```sh
systemctl --user status mseries-kernel-trial.service
journalctl --user -u mseries-kernel-trial.service --no-pager
```

Reports are private to the owner, grouped by exact kernel release and boot ID:
`~/Documents/Codex/2026-10-18/claud/outputs/aurora-kernel-trial/`.
Each completed run has `SUMMARY.md`, immutable hardware/smoke receipts, a device
inventory, raw local kernel journal and status/provenance. These are **normal
active-session observations**, not controlled idle/A/B or battery-life results.
Do not compare their medians as a kernel energy improvement.

## Hardware session order

1. Reboot normally when ready; enter the usual disk passphrase. The one-shot
   candidate should report `uname -r` = `7.1.12-elementary-aurora20-enh1`.
2. Let the desktop settle and capture complete (at least five minutes uptime
   plus the two-minute observation). Check both displays, physical input and
   current dock picture. Inspect kernel errors/PMP and the scoped smoke output.
3. Only after basic acceptance, test Wi-Fi/Bluetooth, ports/replug, thermal
   behavior and dedicated docked/undocked suspend cycles. Preserve exact controls;
   do not enable the optional Thunderbolt teardown/router-sleep flags yet.
   Touch ID probe/enrollment remains a separate targeted test.
4. Reboot again to exercise the default .20 recovery path. Further candidate
   trials require a new explicit `sudo grub-reboot elementary-aurora20-enh1`.
5. Formal power qualification needs fixed brightness, refresh, topology, power
   source and app/workload mix, long settled samples and three alternating
   AB/BA pairs. Retain raw samples; three distinct boots and sleep/recovery
   acceptance remain prerequisites for stable promotion.

Cancel the pending trial while retaining .20 as default:

```sh
sudo grub-editenv /boot/grub/grubenv unset next_entry
```

Stop further automatic observations after the experiment:

```sh
systemctl --user disable --now mseries-kernel-trial.timer
```

The current boot stays on .20 until the owner reboots. Staging, static archive
checks and baseline measurements do not count as a successful .20-enh1 boot.
