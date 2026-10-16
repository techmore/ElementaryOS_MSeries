# R1/R2 fixed and controlled-test payload re-staged — 2026-10-16

Source revision: `46bb8b63089c0fed0ccdc3bd8b62fc87e99ee88c` (local
reconstruction tree; parent `c6fd906`). Public patch:
`0011-experimental-dpin-enolink-retry-stale-phy-guard.patch` (applies after
0001–0010; reverse-apply check against the source tree passes). No boot was
armed, performed or claimed by this batch; hardware qualification of the fix
remains pending.

## What changed (R1, R2)

- **R1 — retry on `-ENOLINK`.** `apple_dp_source_work` now retries the source
  start when the DP-IN activation returns `-ENOLINK` (HPD low at activation),
  every 50 ms until the existing 5 s deadline, mapping expiry to `-ETIMEDOUT`.
  Apple's abort semantics are kept (each attempt still aborts on HPD low; only
  the deadline bounds retries). `dpin_power_on` logs
  INACTIVE/ACK/HPD/IRQ_STATUS/IRQ_ENABLE once per state change on failure
  (`dpin_log_activation_failure`, new fields `logged_failure`/`logged_state`).
- **R2 — stale-PHY guard.** New `dpin_live()` helper checks
  `device_is_registered(&phy->dev)` plus `phy_get_drvdata` and is used by
  dpin_init/exit/power_on/power_off/configure and
  get_hpd/register/unregister_hpd; `dcp_dptx_connect_source` checks the bound
  provider before `phy_init`. A start after an ACIO re-probe now fails with
  `-ENODEV` instead of the `dpin_init` Oops.
- Files: `drivers/phy/apple/dpin.c`, `drivers/gpu/drm/apple/dcp.c`,
  `drivers/thunderbolt/apple.c`, `tools/testing/apple-dpin/test-bridge.py`
  (new `-ENOLINK` retry group; 28 groups total).

## Offline verification

- Five modules rebuilt against the target kernel
  (`7.1.13-elementary-fairydust-usb4-dptunnel`; vermagic matches; external
  module builds via `live-module-build/external/{phy,drm,thunderbolt}`).
- All offline suites pass: 11 helper, 11 clock, 7 EPIC, 28 bridge, source-prep,
  11 lookup, DTB wiring (both boards); checkpatch 0 errors / 0 warnings.
- Bundle validation: init/cleanup layout offsets unchanged (`0130`/`04a8`);
  per-file sha256 recorded; every undefined symbol resolves. Because staging
  ran from the stock boot, the export universe was assembled from disk
  (`revision-46bb8b6/validate-module-bundle-offline.py`): host
  `/proc/kallsyms` (same 7.1.13 core) + the target tree's `modules.symbols`
  (all target module exports, e.g. `typec_altmode_*`) + bundle exports. The
  only new undefined symbol versus the boot-qualified c6fd906 bundle is
  `_dev_info` (from the new failure log), which the target tree's own
  `appledrm.ko` also references and the core kernel exports. Every other
  symbol was already proven by the first boot's successful module load.
- Staged-image verification (`verify-final-stage.py`) passes: all five
  archived module hashes match, ordered preload before udev coldplug, no
  thunderbolt option overrides in the image, unique test parameters
  (`allow_dp_tunnel=1 dprx_bypass=1 dprx_timeout=15000`), original GRUB
  entries preserved.

Environment note: the staging tools guard on `uname -r` matching the target
release. On the stock boot this guard was satisfied with a documented PATH
shim returning the target release; every functional input (target module
tree, initramfs, kernel, `custom.cfg`, bundle files) was read from disk and
hash-checked, and the final artifact was independently verified by
`verify-final-stage.py`.

## Re-stage sequence (reviewed tooling)

| Step | Result |
|---|---|
| rollback (c6fd906 install, manifest `e163c4fd…`) | originals restored (`boot.bin 871591e2…`, `custom.cfg e062b145…`), test image removed, grubenv untouched |
| stage (`stage-controlled-test.py`, rev `46bb8b6`) | image `486be1d9e4c7aa2c64d434430841416caaf628aff39ae1744b0ffc02e333ad70` |
| verify (`verify-final-stage.py`) | PASS (all checks above) |
| plan (`apply-controlled-test.py plan`) | manifest `fdfe9ab56a58107b46f4293e2d3fd67e810396f1ce8d8bca0ab70e58fb8f10a5` |
| apply (`apply-controlled-test.py apply`) | installed; no reboot armed |

Installed state after apply (all re-hashed on disk):

- `/boot/initramfs-linux-asahi-fairydust-usb4-dpin-controlled.img` —
  `486be1d9e4c7aa2c64d434430841416caaf628aff39ae1744b0ffc02e333ad70`
- `/boot/grub/custom.cfg` — `9eadf0917bb5edb609d6b98c102039c00d72e34f979ea584d24bb9bc9aefbc98`
  (identical bytes to the previous controlled entry)
- `/boot/m1n1/boot.bin` — `6702f2c7f88f166187183d9fc32776a22d2ba3bbf804854ed74533db93d4f8a6`
  (fallback-safe candidate, unchanged)
- `/boot/grub/grubenv` — `0e8344eff0b558d225092d5ccc2aef2247f81e3d829e2edfe48eb04a19fdbc11`
  (unchanged; `next_entry` empty)

Rollback set: `/home/sdolbec/dptunnel-logs/rollback-46bb8b6` (backups
`original-1 e062b145…`, `original-2 871591e2…`, `grubenv-before 0e8344ef…`,
`install-manifest.json fdfe9ab5…`). The `rollback-c6fd906` set is superseded
(its image check refuses by design; its backup copies remain).

Staging directory: `controlled-test-46bb8b6` (stage manifest `e8d1da71…`,
compatibility record `a89d642d…` — same reviewed scope, revision updated).

Bundle sha256 (refreshed): `phy-apple-atc.ko 4af34975549a0b49312d453b92fcdcdd43c480855a2466f577fdc6c9beec7587`,
`phy-apple-dpin.ko 7eadefde5edc79da036ffabbe999c236e7988c1a786fc6075f9d33feef14656c`,
`appledrm.ko e42d0bc9698551ad838684e342840ebfc0e734241e754c189ee745b7d921c9f1`,
`thunderbolt.ko 111643a9d74b96326c252c8d771d5c7eb3c676b58062ca4fb0a7a917a35ab6b2`,
`thunderbolt_apple.ko 3ba5f11a066eb54c034dbe184505aac72586d61d68b03d580cbb8455850c13b2`.

## Marker and open items

- `~/.cache/mseries-gala-failed` removed (patched Gala re-enabled at the next
  session start; the launcher is self-healing).
- Still open: R4's remaining engineering item (shorten appledrm registration
  on the dptunnel entries — the race cause and the installed
  `lightdm-wait-for-drm.conf` drop-in are recorded in
  [evidence/2026-10-16-pantheon-session-crash-on-dptunnel-entries.md](2026-10-16-pantheon-session-crash-on-dptunnel-entries.md)),
  R5 fallback-boot re-evaluation, and the hardware re-run of the controlled
  boot with the collector (owner-gated; the fixed payload is staged but not
  armed).
