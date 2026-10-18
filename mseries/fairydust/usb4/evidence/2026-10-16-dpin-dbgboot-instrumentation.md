# DP-IN debug boot: instrumenting the DCP link-config path (2026-10-16)

Author: OpenCode. Purpose: answer why the second controlled boot failed at
`DP source preparation failed: -110` (see
[the second-boot record](2026-10-16-controlled-test-second-boot-dpin-gate-cleared.md)).
Read-only live inspection is exhausted; the only way to see *which* DCP request
is missing is to log the DCP endpoint path and re-run.

## What changed

One module rebuilt (`appledrm.ko`) with `DPINDBG` `dev_info` lines; the other
four modules and the DTB are untouched. Patch:
[`../0012-experimental-appledrm-dpin-diagnostics.patch`](../0012-experimental-appledrm-dpin-diagnostics.patch).

Instrumented points:

- `dptxep.c:dptxport_call` — every AFK request `idx` the DCP firmware sends
  (the single dispatch point). This tells us whether `SET_ACTIVE_LANE_COUNT`
  (`idx` 6?) ever arrives.
- `dptxep.c:dptxport_set_hpd` — `hpd` value, AFK ret and reply.
- `dptxep.c:dptxport_hpd_work` / `dptxport_hpd_notify` — whether HPD=1 was
  delivered to the DCP, and the DP-IN notifier events.
- `dptxep.c:dptxport_tunnel_reply` — every `linkcfg_completion` completion with
  `phy_powered`/`link_rate`/`lane_count`.
- `dptxep.c:dptxport_request_display` — AFK ret.
- `dptxep.c:dptxport_call_set_active_lane_count` — requested lane count.
- `dcp.c:dcp_dptx_connect_source` — phy init/power result and the exact state at
  the 2 s `linkcfg_completion` timeout.

No functional change: only `dev_info` calls (plus a local `int` in
`dptxport_request_display`).

## Build and install (exact)

```
# edit source at rev 46bb8b6 (Codex tree), then:
make -C live-module-build/external/drm KBUILD_MODPOST_WARN=1   # -> appledrm.ko
# repack the controlled initramfs, replacing only appledrm.ko:
python3 tools/repack-dpin-initramfs.py \
  --input initramfs-linux-asahi-fairydust-usb4-dpin-controlled.img \
  --mapping mapping.json   --output new.img   --report report.json
sudo install -m0644 new.img /boot/initramfs-linux-asahi-fairydust-usb4-dpin-controlled.img
sudo grub-reboot elementary-usb4-dpin-controlled
```

The Codex source tree was restored to clean `46bb8b6` after the build
(`git checkout -- drivers/gpu/drm/apple/dptxep.c drivers/gpu/drm/apple/dcp.c`).

Artifacts (private, under `/home/sdolbec/dptunnel-logs/dpin-dbgboot-20261016-210203/`):
`appledrm-diag.ko` (`8cd763a8…`), `appledrm-diag-DPINDBG.patch`,
`initramfs-controlled-original.img` (`486be1d9…`, rollback source),
`initramfs-dpin-dbgboot.img` (`a6db46fa…`, the installed instrumented image),
`repack-report.json` (proves only `appledrm.ko` changed; unrelated entries
preserved).

## Safety

- Only the `elementary-usb4-dpin-controlled` entry's initramfs was replaced; the
  default entry, other entries, root modules, kernel and `boot.bin` are
  unchanged. Bypass remains armed on that entry; cables untouched.
- Rollback: `sudo install -m0644 <OUT>/initramfs-controlled-original.img
  /boot/initramfs-linux-asahi-fairydust-usb4-dpin-controlled.img` then
  `sudo grub-editenv /boot/grub/grubenv unset next_entry`.

## What to read after the boot

```
sudo dmesg | grep DPINDBG
```

Expected diagnostics: whether `hpd_work` reported `hpd=1`, whether `set_hpd`
acked, which `apcall idx` values arrive and in what order, and the
`connect_source` line — `waited=0` with everything else zero confirms the DCP
never requested lane configuration; `waited>0` nonzero `link_error` would point
elsewhere.

## RESULT (boot ran 2026-10-16, read back)

The `waited>0` branch happened: `waited=949 ret=-110 … link_error=-110`. The
`-110` is our **`set_hpd(hpd=1)` AFK call timing out after 1 s**, promoted into
`link_error` by `dptxport_hpd_work` — not the 2 s `DPTX_CONNECT_TIMEOUT`. The
firmware sent only `idx=18,10,0` and then went silent. Full decode, the
corrected attribution, and the working-path reference trace:
[2026-10-16-dbgboot-dcp-silent-never-configures-link.md](2026-10-16-dbgboot-dcp-silent-never-configures-link.md).
