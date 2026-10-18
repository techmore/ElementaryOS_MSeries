# E1: non-fatal tunnel-mode HPD delivery — prepared and armed (2026-10-16)

Author: OpenCode. This implements **E1** from
[`2026-10-16-dbgboot-dcp-silent-never-configures-link.md`](2026-10-16-dbgboot-dcp-silent-never-configures-link.md).
Read [STATE-OF-PLAY](../STATE-OF-PLAY.md) first.

**Status: source patched, module built, initramfs repacked and installed, one-shot
boot armed and then RUN (2026-10-16).** Nothing else was applied.
**Result:**
[`2026-10-16-e1-boot-outcome-firmware-device-not-responding.md`](2026-10-16-e1-boot-outcome-firmware-device-not-responding.md)
— E1 engaged and cleared the `set_hpd` wall, but the firmware then reported the
tunnelled sink `DEVICE_NOT_RESPONDING`; the frontier is the sink/AUX path.

## Hypothesis under test

The debug boot showed the fatal `-110` was **our** `set_hpd(hpd=1)` timing out after
1 s, which `dptxport_hpd_work()` promoted into `link_error`, ending
`connect_source` ~1 s into its 2 s window. E1 asks: *if we stop letting that
failure kill the tunnel, does the firmware eventually drive the link?*

- **If yes** (`idx=7,13,15,5,12,9,6` appear, `linkcfg_completion` completes):
  our timeout was the artifact; the wall moves forward.
- **If no** (silence for the whole window, `waited=0 ret=-ETIMEDOUT`, all state
  zero): hypothesis H1 is confirmed — the firmware itself is blocked before its
  DP TX state machine, and the next step is the sink/AUX question (E2/E3), not
  HPD delivery.

## What changed — patch `0013` on top of `0012`

[`../0013-experimental-appledrm-e1-nonfatal-tunnel-hpd.patch`](../0013-experimental-appledrm-e1-nonfatal-tunnel-hpd.patch)
(apply after `0012`; `0012` after the `0001`–`0011` series). Two changes only:

1. `dptxep.c:dptxport_hpd_work()` — in **tunnel mode only**, a failed
   `apple_dpin_get_hpd()` or a failed `dptxport_set_hpd()` is logged and **not**
   written to `link_error` and does **not** complete `linkcfg_completion`. The
   physical (non-tunnel) path is unchanged: there the failure stays fatal.
2. `dcp.c:dcp_dptx_connect_source()` — the tunnel path waits
   `msecs_to_jiffies(8000)` on `linkcfg_completion` instead of the 2 s
   `DPTX_CONNECT_TIMEOUT`, so "slow" is distinguishable from "stuck" in one boot.
   The physical path keeps `DPTX_CONNECT_TIMEOUT`.

`set_hpd` is still *sent* (not removed): if the firmware ever accepts HPD=1 we
want to know. E1 changes only what happens when it does not.

### Why non-fatal is scoped to tunnel mode

On the working HDMI path the same firmware required no `set_hpd` at all (it is
not a DisplayPort connector, so `dcp.c` never calls it). On the physical DP path
`set_hpd` returning a hard error is treated as fatal by design. E1 only relaxes
the tunnel case, which is the one that is measured broken.

### Related measured detail (from the debug boot)

At teardown the firmware **did** answer `set_hpd(0)` (one AFK reply, `resp=0`,
which our code rejects as `-EINVAL` because it expects `resp==1`), while it never
answered `set_hpd(1)`. So the firmware implements group 8 / command 8 but did not
service the assert within 1 s — consistent with the firmware blocking while it
tries to bring the sink up, and also a hint that the `resp==1` reply check may be
wrong for the deassert case. Neither is being changed in E1; both are recorded
for the next pass.

## Build

```
make -C live-module-build/external/drm KBUILD_MODPOST_WARN=1
```

- `appledrm.ko` sha256 `882c44457e853d543df50c635cdfbb37fe8cb6d145236ab10f612d9c4bdac67c`
- build-id `90eec845166a52f688cbd1675187d73fcf8bbb1b`
- vermagic `7.1.13-elementary-fairydust-usb4-dptunnel SMP preempt mod_unload aarch64`
  (exact match with the running kernel)
- `init_module`/`cleanup_module` offsets `0x8`/`0x0`, identical to the previous
  instrumented ko; BTF skipped exactly as before (no `vmlinux` available).
- Source tree restored to clean `46bb8b6` after the build; clean + `0012` +
  `0013` byte-matches the built source.

Only `appledrm.ko` is new; `thunderbolt`, `thunderbolt_apple`, `phy-apple-atc`
and `phy-apple-dpin` are the same modules as the second controlled boot.

## Install and arm (exact)

```
# repack from the pristine controlled image, replacing only appledrm.ko:
python3 tools/repack-dpin-initramfs.py \
  --input /home/sdolbec/dptunnel-logs/dpin-dbgboot-20261016-210203/initramfs-controlled-original.img \
  --mapping <OUT>/mapping.json \
  --output <OUT>/initramfs-dpin-e1boot.img \
  --report <OUT>/repack-report.json
sudo install -m0644 <OUT>/initramfs-dpin-e1boot.img \
  /boot/initramfs-linux-asahi-fairydust-usb4-dpin-controlled.img
sudo grub-reboot elementary-usb4-dpin-controlled
```

- `<OUT>` = `/home/sdolbec/dptunnel-logs/dpin-e1boot-20261016-214205`
- `appledrm-e1.ko` (`882c4445…`), `initramfs-dpin-e1boot.img`, `mapping.json`,
  `repack-report.json`
- repack report: 1120 → 1120 entries, the **only** changed regular file is
  `…/appledrm.ko`, `unrelated_entries_preserved: true`,
  input `486be1d9…` (pristine) → output `46116374…`
- installed image sha256 verified `46116374311cd18cb265c751f436dc751297c0203d7bb605b685cb5527778cb2`
- `grub-editenv list` → `next_entry=elementary-usb4-dpin-controlled`; the default
  entry is untouched; bypass (`dprx_bypass=1`) is armed on that entry.

## After the reboot (do not skip)

```
sudo dmesg | grep DPINDBG
```

Read, in order:

1. `DPINDBG hpd_work: E1 set_hpd(1) ret=-110 ignored (tunnel)` — E1 engaged.
2. Any `apcall idx=…` in `[61.9s, +8s)`. On success expect `7,13,15,5,12,9,6`
   (and possibly `3,2,4`), then `tunnel_reply` completing with `rate!=0`.
3. `DPINDBG connect_source: waited=… ret=… rate=… lanes=…` — `waited>0 ret=0`
   with `rate!=0` is the win; `waited=0 ret=-ETIMEDOUT` with zeros is H1 confirmed.
4. `sudo dmesg | grep 28cc00000 | grep -i syslog | wc -l` — did the firmware
   start talking? (was 13 for the whole boot).

Then `tools/collect-controlled-test.py` and the external-connector status as usual.

## Safety / rollback

- Only the controlled entry's initramfs was replaced; default entry, other
  entries, kernel, `boot.bin` and root modules are unchanged. Bypass remains on;
  cables untouched. No suspend with the USB4 link attached; do not unplug the
  dock while a DPRX read is in flight (`DP-TUNNEL-RE.md` §9) — bypass is on, so
  no such read should be in flight, but the rule stands.
- Rollback to pristine:
  `sudo install -m0644 /home/sdolbec/dptunnel-logs/dpin-dbgboot-20261016-210203/initramfs-controlled-original.img /boot/initramfs-linux-asahi-fairydust-usb4-dpin-controlled.img`
  then `sudo grub-editenv /boot/grub/grubenv unset next_entry`.
