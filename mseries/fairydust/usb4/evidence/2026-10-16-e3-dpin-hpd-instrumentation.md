# E3: DP-IN HPD producer instrumentation — prepared and staged (2026-10-16)

Author: OpenCode. Implements **E3** from
[`2026-10-16-dbgboot-dcp-silent-never-configures-link.md`](2026-10-16-dbgboot-dcp-silent-never-configures-link.md)
and the E1 follow-up. Read [STATE-OF-PLAY](../STATE-OF-PLAY.md) first.

**Status: instrumentation written, module built, initramfs repacked, staged on the
`elementary-usb4-dpin-controlled` entry. No boot armed or performed.**

## Why E3, and what it can and cannot answer

The E1 boot established that the DCP firmware never configures the link and
reports the tunnelled sink `DEVICE_NOT_RESPONDING` (see
[the E1 outcome](2026-10-16-e1-boot-outcome-firmware-device-not-responding.md)).
Two questions remain, and the audit says the **DP-IN block has no AUX/DPCD
register** (`dpin-handshake.h`: only HPD/IRQ/INACTIVE/ACK), so "no sink" vs "no
AUX" cannot be answered by reading a DP-IN register:

1. **did the DP-IN HPD producer ever fire?** The consumer
   (`dptxport_hpd_notify`, patch `0012`) logged nothing on the E1 boot, but that
   only proves the *consumer* stayed quiet.
2. **can the host reach the sink over the tunnel at all?** That is the real AUX
   question, and it is only answered by a **real DPRX read with `dprx_bypass=0`
   (E2)**. E3 therefore deliberately does **not** pretend to read AUX; it is
   paired with a ready-but-unarmed E2 entry (below) so one reboot can do both.

## What changed — patch `0014` (only `phy-apple-dpin.ko`)

[`../0014-experimental-dpin-hpd-instrumentation.patch`](../0014-experimental-dpin-hpd-instrumentation.patch)
(apply after `0011`; it does not touch the files `0012`/`0013` change, so it is
orthogonal to them). `dev_info` only, no functional change:

- `dpin_irq()`: one `DPINDBG irq:` line per HPD interrupt with the ack result and
  raw `HPD`/`STATUS`, plus a `DPINDBG hpd_notifier event=` line naming the event
  actually pushed to the chain — this is the producer-side answer to question 1.
- new static `dpin_dump_state()` dumps
  `INACTIVE/ACK/HPD/STATUS/ENABLE init/active/fault` at `init`, `exit`,
  `power_on`, `power_on-fail` and `power_off`.

`checkpatch --terse -f`: 0 errors, 1 warning (a pre-existing `kzalloc` style
warning in the same file; the added lines introduce none).

## Build

```
make -C live-module-build/external/phy KBUILD_MODPOST_WARN=1
```

- `phy-apple-dpin.ko` sha256
  `9d43d6e77e2d4fc19f4ef785549b19d9cf7eea29ce36eb77a8954e632522ab08`
- build-id `7beaacf6f5f2c4ba213da5ba65c662f46701c4c7` (previous instrumented
  module was `f1e65d6c…`)
- vermagic `7.1.13-elementary-fairydust-usb4-dptunnel SMP preempt mod_unload aarch64`
  (exact match with the running kernel)
- undefined-symbol delta vs the previous module is only `_dev_info` (the added
  calls); `dpin_dump_state` is `static`. BTF skipped as before (no `vmlinux`).
- source tree restored to clean `master` after the build; patch `0014` is the
  only artefact.

## Repack and install (exact)

```
OUT=/home/sdolbec/dptunnel-logs/dpin-e3boot-20261016-234246
python3 tools/repack-dpin-initramfs.py \
  --input /home/sdolbec/dptunnel-logs/dpin-e1boot-20261016-214205/initramfs-dpin-e1boot.img \
  --mapping "$OUT/mapping.json" --output "$OUT/initramfs-dpin-e3boot.img" \
  --report "$OUT/repack-report.json"
sudo install -m0644 "$OUT/initramfs-dpin-e3boot.img" \
  /boot/initramfs-linux-asahi-fairydust-usb4-dpin-controlled.img
```

- repack report: `1120 → 1120` entries, the **only** changed regular file is
  `…/phy/apple/phy-apple-dpin.ko`, `unrelated_entries_preserved: true`,
  input `46116374…` (E1) → output `2c036651…`.
- installed image sha256 verified `2c036651415dbd363d7fed1a744e35b174a35037a7763ddcb19b37f7f958a20e`.
- E1 image preserved: `$OUT/initramfs-controlled-e1-installed.img` (`46116374…`).
- `custom.cfg` backed up at `$OUT/custom.cfg.before-e3`.
- **Nothing was armed.** `grub-editenv list` → `next_entry=` (empty).

## The paired E2 entry (staged, not armed)

A new GRUB entry was appended to `/boot/grub/custom.cfg`:

```
menuentry 'elementary OS (DP-IN controlled test, unbypassed DPRX / E2)' --id elementary-usb4-dpin-nobypass
    … thunderbolt.allow_dp_tunnel=1 thunderbolt.dprx_bypass=0 thunderbolt.dprx_timeout=15000
    initrd /initramfs-linux-asahi-fairydust-usb4-dpin-controlled.img   # same E3 image
```

So one reboot can run **both**: E3 instrumentation (always on) and the real DPRX
read (E2 entry). E2 is the documented §9 hazard —
**do not unplug the dock while a DPRX read is in flight**; with `dprx_timeout=15000`
the read completes or times out in ≤15 s, after which the cable is safe. The
existing `elementary-usb4-dpin-controlled` entry (bypass=1) is the safe fallback.

Read after the boot, in order: `sudo dmesg | grep -E 'DPINDBG|DPRX|0:5|1:14'`;
the E3 lines `DPINDBG irq:` / `DPINDBG hpd_notifier` / `DPINDBG init|power_on…`;
then the tunnel `connect_source` line as usual.

## Rollback

```
sudo install -m0644 /home/sdolbec/dptunnel-logs/dpin-e1boot-20261016-214205/initramfs-dpin-e1boot.img \
  /boot/initramfs-linux-asahi-fairydust-usb4-dpin-controlled.img   # back to E1
sudo cp -a /home/sdolbec/dptunnel-logs/dpin-e3boot-20261016-234246/custom.cfg.before-e3 /boot/grub/custom.cfg
sudo grub-editenv /boot/grub/grubenv unset next_entry
```

## Related fix

`test-dp-tunnel.sh`'s verdict was corrected in the same batch: it compared
`dprx_bypass` to `1` though sysfs reports `Y`, and only matched the pre-`DPINDBG`
log wording, so it printed "Nothing yet" on the E1 boot. It now normalises
`Y`/`1`, recognises `DPINDBG connect_source` / `DPINDBG apcall idx=`, and reports
the `-67`/`-110` cases explicitly. `shellcheck -S warning` is clean.
