# Aurora SEP kernel: second-boot plan (written 2026-10-17)

Why: the first boot of `7.1.12-2-20261015.19-sep-ARCH` brought the Secure
Enclave up, then the machine hung ~34 s in with no panic logged. See
[aurora-touchid-state.md](aurora-touchid-state.md) and the top entry of
[OS9-HANDOFF.md](OS9-HANDOFF.md). Nothing here has been run on a boot yet.

## Already prepared (this session)

- journald drop-in `/etc/systemd/journald.conf.d/zz-aurora-freeze-hunt.conf`
  (`SyncIntervalSec=1s`, `RateLimitIntervalSec=0`) so the last seconds before a
  freeze reach disk. Installed and journald restarted; harmless on any kernel.
  **Remove after the test:** `sudo rm /etc/systemd/journald.conf.d/zz-aurora-freeze-hunt.conf && sudo systemctl restart systemd-journald`
- No GRUB or m1n1 change was made. Fallback is any other GRUB entry (default
  `elementary-mseries` is unchanged).

## Observations to act on before booting

1. The GRUB entry `elementary-aurora-sep` (in `/boot/grub/custom.cfg`) still
   carries the dptunnel experiment flags
   `thunderbolt.allow_dp_tunnel=1 thunderbolt.dprx_bypass=1 thunderbolt.dprx_timeout=15000`.
   They belong to the fairydust kernels; on Aurora they are probably ignored but
   are an uncontrolled variable. For a clean test, use a copy of the entry
   without them, and without `quiet` (loglevel 3 hides kernel warnings).
2. Boot with the dock detached (earlier community j314s reports of flaky boots).
3. Journal ends abruptly on a hard reset, so the real uptime may exceed 34 s.

## Test sequence (needs owner OK for the boot)

1. Boot the Aurora entry once, dock detached, nothing launched by hand.
2. Note wall-clock time of the freeze, and whether the screen froze, went
   black, or the machine reset by itself.
3. After recovering on any kernel: `journalctl -b -1 -o short-monotonic | tail -60`
   and check `/sys/fs/pstore` (needs root).
4. Only if it stays up for several minutes: `ls /dev/sep-bio`, `fprintd-list $USER`,
   then `sudo aurora-touchid-setup`.

## Suspects

SEP background activity after ready; the ported `spi@39b108000` fingerprint
node; DCP/display ("DCP took too long to respond to LAS stats"); an unrelated
fault in this kernel build. To separate them, an optional bisect is booting with
the pre-fingerprint DTB (`/boot/m1n1/boot.bin.pre-fingerprint-20261017-103254`);
that changes the bootloader payload, so it needs explicit owner approval.

## Update 2026-10-17: clean GRUB entry added

Added `elementary-aurora-sep-clean` ("CLEAN freeze test, no dock flags") to
`/boot/grub/custom.cfg`: same kernel and initramfs, no `thunderbolt.*` flags, no
`quiet`/`splash`, `loglevel=7`. The original `elementary-aurora-sep` entry and the
default are untouched; the pre-edit file is saved as
`/boot/grub/custom.cfg.pre-aurora-clean-*`. Nothing was armed (`grub-reboot` not
run). To boot it once: pick it in the GRUB menu, or `sudo grub-reboot elementary-aurora-sep-clean`
(owner decision). Revert: restore the saved `custom.cfg`.

## Result of the clean-entry boots — 2026-10-17 22:03–22:05

Booted `elementary-aurora-sep-clean` (loglevel=7, no thunderbolt flags, journald
sync 1 s). Owner reports the machine keeps crashing.

- Boot A (22:03:21, journal ends 22:03:44, last entry 33.0 s): ended with no
  panic/oops/shutdown in the log, again with the desktop up. Same ~33 s as the
  first freeze (~34 s), which points to something deterministic at that point of
  startup, not random. Last events: mseries-dark-mode.service (32.97 s), ibus
  im-config, Claude Desktop GTK assertion.
- Boot B (22:04:50): still alive at 46 s+ when checked; `/dev/sep-bio` exists
  (root-only, char 10:261); `fprintd` inactive (on demand). SEP firmware accepted
  as before. Journal errors only: `tas2764 3-003c: Failed to parse devicetree`
  (speaker amp on this DTB), brcmf p2p -52, bluetooth flag warnings.
- pstore empty; PMU reports "1 boot error(s) and 0 panic(s)" after the reset.
- Nothing from SEP/DCP/SPI-fingerprint precedes either stop.

Open: whether Boot B froze later, whether a hardware watchdog/SMC reset (not a
kernel panic) is the cause, and the tas2764 devicetree warning (new on this
kernel/DTB; stock kernel path unchecked). Stock `7.1.13-3-2-ARCH` is stable and
remains the default. No further Aurora boots until the owner decides.
