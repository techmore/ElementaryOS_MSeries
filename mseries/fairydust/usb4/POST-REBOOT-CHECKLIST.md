# Batched reboot: pre-flight, GRUB entry, post-reboot checks

2026-10-16, Claude. **Nothing here has been applied.** Written so any agent can
run or review the reboot without re-deriving it. Evidence behind each item is in
[REVIEW-2026-10-16-GAPS.md](REVIEW-2026-10-16-GAPS.md) (IDs N1-N4, B1-B8). Hardware
facts stay in [STATE-OF-PLAY.md](STATE-OF-PLAY.md); append results there, not here.
The owner approves each step that touches boot config, the ESP or `/usr/lib/modules`.

## A. Pre-flight (all read-only, do before any write)

1. Bundle present and consistent: `deployment/` has `phy-apple-atc.ko`,
   `phy-apple-dpin.ko`, `appledrm.ko`, `thunderbolt.ko`, `thunderbolt_apple.ko`,
   `boot-dpin.bin`; `module-validation.json` vermagic equals `uname -r`
   (`7.1.13-elementary-fairydust-usb4-dptunnel`), no `+` suffix.
2. Repacked initramfs exists and `lsinitcpio`/`lsinitramfs` shows the five modules
   (the earlier initramfs once carried a stale `appledrm.ko`). **Not yet produced (N3).**
3. Known-good boot images exist: `ls /boot/m1n1/boot.bin.KNOWN-GOOD-*`; rollback
   target is `...-pre-usb4-20261015-152345`. Re-check `RECOVERY.md` names a file that
   exists (N2, repo copy corrected; ESP copy not verified).
4. `boot-validation.json` lists only the three property changes plus
   `phy@e50000`/`phy@e58000`, and `prefix_suffix_unchanged: true`.
5. Know the recovery path without Linux: power button -> Macintosh HD -> mount
   "EFI - ASAHI" -> copy a KNOWN-GOOD image to `boot.bin` (`RECOVERY.md`).

## B. GRUB entry (owner's decision, N1)

Add a **new** entry; leave `elementary-usb4-dptunnel` untouched as the fallback.
Same line as the existing entry plus the two parameters:

```
thunderbolt.allow_dp_tunnel=1 thunderbolt.dprx_bypass=1 thunderbolt.dprx_timeout=15000
```

Why: `dprx_bypass` resets on boot, and `dprx_timeout` is `0444`, so only the command
line can set either before the dock enumerates. The current entry has
`dprx_timeout=3600000` and no bypass.

## C. Apply order (owner-approved, one write at a time)

1. Modules into `/usr/lib/modules/<kv>/` + `depmod -a <kv>` (no nested `<kv>/<kv>`).
2. Repacked initramfs under the new entry's name only.
3. New GRUB entry.
4. `boot.bin` last (it affects every entry). Keep the pre-write copy.
5. Do not change the default boot entry; select the new one once with `grub-reboot`.
6. Dock and monitor attached as in STATE-OF-PLAY; do not move cables during boot.

## D. Post-reboot checks (in this order, record raw output)

| # | Check | Good | Bad / meaning |
|---|---|---|---|
| 1 | `uname -r`; `cat /proc/cmdline` | dptunnel kernel; shows `dprx_bypass=1` | wrong entry booted |
| 2 | `cat /sys/module/thunderbolt/parameters/dprx_bypass` | `Y` | `N`: stop, do not touch the cable |
| 3 | `lsmod \| grep -E 'phy_apple_dpin\|appledrm\|thunderbolt'` | all present | dpin missing: B2-class failure |
| 4 | `journalctl -k -b \| grep -i -E 'dp.source\|dpin\|dcp_dptx\|DPRX'` | a "DP source ready ... before DPRX" style line, no timeout storm | storm of `DPRX read timeout`: bypass not effective |
| 5 | USB4 still up: dock hub, Ethernet, mouse enumerate | yes | NHI probe failed: B1; roll back `boot.bin` |
| 6 | Source errno if it fails | `-EAGAIN/-EPROBE_DEFER/-ETIMEDOUT` DCP not ready; `-EINVAL/-ENODEV` PHY NULL; `-EBUSY` owned elsewhere | note which |
| 7 | Did the 5 s source deadline fire (N4)? | source ready within 5 s | "failed" at ~5 s is a timing limit, not a hardware wall |
| 8 | `bash test-dp-tunnel.sh` (fixed collector) | per-connector `card*-DP-*`/`HDMI-*` state | eDP no longer counts |

What does **not** count as progress: a bypassed "DPRX capabilities read completed"
line; tunnel path "activation complete"; USB data or Ethernet working.
Progress ladder, unchanged: DP-IN ACK/clock lock -> real DPRX with bypass off ->
EDID/modes -> picture.

## E. Bypass-off step (separate, later boot or later step)

Only after D passes and the teardown hazard is understood (`DP-TUNNEL-RE.md` §9,
`DPRX-TEARDOWN-BACKPORT-PLAN.md`). Arm bypass before any unplug. A DPRX read in
flight while unplugging has wedged the port before.

## F. Reporting

Append the raw results (commands + output, kernel and bundle SHA-256s) under a dated
heading in `STATE-OF-PLAY.md`, update the gap ledger statuses, and add a line to
`OS9-HANDOFF.md`. One agent holds the Git write at a time (AGENTS.md).
