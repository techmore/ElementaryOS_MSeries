# Controlled test, first hardware boot — outcome (2026-10-16)

First live execution of the c6fd906 bridge revision (patches 0001–0010,
fallback-safe boot.bin, five rebuilt modules in the dedicated initramfs).
The boot ran exactly as staged; the bridge engaged on the real dock DP tunnel
and failed. No picture; no unbypassed DPRX evidence; collector not run.
Companion analysis (register/code reading of the two bugs):
[2026-10-16-controlled-test-first-boot.md](2026-10-16-controlled-test-first-boot.md).

## Boot facts (journal boot -2)

- Window: 2026-10-16 11:45:04 – 11:47:13 EDT (ended with an orderly reboot at
  ~11:47:08).
- Kernel: `7.1.13-elementary-fairydust-usb4-dptunnel #dp1` (intended kernel).
- Cmdline contained exactly:
  `thunderbolt.allow_dp_tunnel=1 thunderbolt.dprx_bypass=1 thunderbolt.dprx_timeout=15000`.
- All five rebuilt modules were loaded (from the Oops module list):
  `thunderbolt_apple(O) thunderbolt(O) appledrm(O) phy_apple_dpin(O) phy_apple_atc(O)`.

## Successes

1. **Fallback-safe DT accepted on hardware.** No `DP source disabled (...)`
   warning and no `-EINVAL`: the new `apple,dp-source` / `apple,dp-in-port` /
   `apple,dp-tunnel-phy` chain resolved and the source init succeeded.
2. **The bridge engaged automatically on the real dock tunnel.** The ordered
   workqueue `apple-dp-source` ran `apple_dp_source_work [thunderbolt_apple]`,
   and the designed chain executed live for the first time:
   `apple_dp_source_work` → `apple_dcp_dp_source_start [appledrm]` →
   `dcp_dptx_connect_source [appledrm]` → `phy_init` (succeeded) →
   `phy_power_on` (reached DP-IN activation).
3. **The DP-IN handshake gave a definitive answer instead of a timeout.**
   `phy poweron failed --> -67` is the activation gate reporting DP-IN HPD low
   — a real state, not the 5 s deadline (the deadline path logs `-EAGAIN`).
4. **Dock USB4 data path worked on this boot.** Dell dock hubs enumerated at
   11:46:34–35 (`0bda:5487`, `0bda:5413`, Intel `8087:0b40`).
5. **Failure containment.** The Oops killed only the workqueue worker; the
   kernel stayed up, the owner recovered the machine, and nothing needed
   rollback. Staged install and rollback set remain intact (boot.bin still
   `6702f2c7…`; test entry present; `next_entry` empty).
6. **Evidence preserved** (journal exports + hashes below).

## Failures

### F1 — first source attempt fails fast: `-ENOLINK` (-67) at DP-IN activation

```
Oct 16 11:45:09 eos kernel: phy phy-b01e50000.phy.12: phy poweron failed --> -67
Oct 16 11:45:09 eos kernel: thunderbolt-apple-nhi b01f00000.nhi: DP source preparation failed: -67
Oct 16 11:45:09 eos kernel: thunderbolt-apple-nhi b01f00000.nhi: 0:5 <-> 1:14 (DP): not active, tearing down
```

- `-67` is `-ENOLINK`; the PHY-core message pins it to `phy_power_on` →
  `dpin_power_on` → `apple_dpin_set_inactive(io, 0)` (activate, dpin.c:159).
  Per the recovered handshake (`dpin-handshake.h`), activating returns
  `-ENOLINK` when the DP-IN HPD level bit is low. The attempt was ~4 s after
  bring-up; the dock's DP-IN HPD had not asserted yet (or does not in this
  state). The rollback deactivation in `dpin_power_on` succeeded silently
  (no "inactive rollback failed" message).
- The worker treats `-ENOLINK` as final (only `-EAGAIN`/`-EPROBE_DEFER`/
  `-EINPROGRESS` retry until the 5 s deadline), so `source->failed` was set
  and the tunnel was torn down immediately. No "DP source ready" line.

### F2 — second source attempt Oopses in `dpin_init` (NULL device)

```
Oct 16 11:46:33 eos kernel: Internal error: Oops: 0000000096000004 [#1]  SMP
Oct 16 11:46:33 eos kernel: CPU: 9 UID: 0 PID: 12 Comm: kworker/u40:0 Tainted: G S         O        7.1.13-elementary-fairydust-usb4-dptunnel #dp1 PREEMPT(full)
Oct 16 11:46:33 eos kernel: Workqueue: apple-dp-source apple_dp_source_work [thunderbolt_apple]
Oct 16 11:46:33 eos kernel: pc : __pm_runtime_resume+0x28/0xc0
Oct 16 11:46:33 eos kernel: lr : dpin_init+0x2c/0x140 [phy_apple_dpin]
Oct 16 11:46:33 eos kernel: x0 : 0000000000000000
Oct 16 11:46:33 eos kernel: Call trace:
Oct 16 11:46:33 eos kernel:  __pm_runtime_resume+0x28/0xc0 (P)
Oct 16 11:46:33 eos kernel:  dpin_init+0x2c/0x140 [phy_apple_dpin]
Oct 16 11:46:33 eos kernel:  phy_init+0x78/0x148
Oct 16 11:46:33 eos kernel:  dcp_dptx_connect_source+0x268/0x3a8 [appledrm]
Oct 16 11:46:33 eos kernel:  apple_dcp_dp_source_start+0xe4/0x158 [appledrm]
Oct 16 11:46:33 eos kernel:  apple_dp_source_work+0x88/0x200 [thunderbolt_apple]
Oct 16 11:46:33 eos kernel:  process_one_work+0x168/0x510
Oct 16 11:46:33 eos kernel:  worker_thread+0x194/0x318
Oct 16 11:46:33 eos kernel:  kthread+0x120/0x140
Oct 16 11:46:33 eos kernel:  ret_from_fork+0x10/0x20
```

- Fault: data abort, level 0 translation fault at `[0x1d0]`; `x0 = 0`:
  `dpin_init` called `pm_runtime_resume_and_get(dpin->dev)` with a NULL
  `dpin->dev` (`dpin.c:99`). The Oops killed the `apple-dp-source` worker;
  the tunnel was torn down again at 11:46:48.
- Context: before this attempt the USB4 link dropped and re-initialized
  (`oob_hotplug status:0x2` at 11:46:27/11:46:30; a local script logged
  "dock gone: released the lid-switch inhibitor"; ACIO RTKit re-"Initializing"
  at 11:46:30; USB re-enumeration at 11:46:34). A stale/freed DP-IN drvdata
  after a re-probe in that window is the leading hypothesis; `dcp->phy` is
  cached by the DCP (`dcp.c:1361`), so a phy lifetime change is not
  re-resolved. Pin this when fixing (guard + re-resolution or refcount).

### F3 — desktop session race (not a bridge bug) and follow-on boots

- Gala started 11:45:07 in the same second appledrm registered its DRM card
  (minor 2). It enumerated `/dev/dri` too early, picked `simpledrm` (card0)
  as primary, and crashed when the apple card took over the framebuffer and
  simpledrm disappeared mid-modeset:

  ```
  gala: Added device '/dev/dri/card0' (simpledrm) using atomic mode setting.
  gala: Failed to open gpu '/dev/dri/card1': No suitable mode setting backend found
  gala: Created gbm renderer for '/dev/dri/card0'
  gala: Integrated GPU /dev/dri/card0 selected as primary
  gala: drmModeRmFB: No such device
  gala: Failed to ensure KMS FB ID on /dev/dri/card0: drmModeAddFB2WithModifiers failed: No such device
  mseries-gala[1871]: libmutter:ERROR:../src/backends/native/meta-kms-update.c:365:meta_kms_update_mode_set: assertion failed: (meta_kms_crtc_get_device (crtc) == update->device)
  mseries-gala[1871]: Bail out! ...
  systemd-coredump[2333]: Process 1871 (gala) of user 1000 terminated abnormally with signal 6/ABRT, processing...
  mseries-gala[3110]: patched Gala failed after under 15 s (rc=134); disabled until /home/sdolbec/.cache/mseries-gala-failed is removed
  ```

  In the known-good boot (-3) Gala ran after the apple card was already up
  (`GPU /dev/dri/card2 selected primary from builtin panel presence`). The
  race is boot timing, not the bridge.
- Because the session was unusable, the planned collector was **not run**.
- Owner recovery on this boot: short power presses, lid close → suspend
  attempts correctly vetoed by ACIO ("unable to suspend while a
  USB4/Thunderbolt connection is active"), then an orderly reboot at ~11:47:08.
- Next boot (-1, normal dptunnel entry, no bypass): patched Gala stayed
  disabled by the marker; stock Gala started and correctly picked the apple
  card, then was SIGKILLed after ~0.7 s (killer not identified in the captured
  logs); the owner logged in again and a GNOME session (gnome-shell) started
  at 11:48:36; the machine was force-powered-off at 11:48:57.
- Current boot (0): stock kernel, machine usable, dock USB4 down.

## Next steps (continuation)

1. Fix F2 (NULL `dpin->dev` in `dpin_init`) — hard blocker; one Oops per live
   attempt is not acceptable. Decide the phy/drvdata lifetime handling around
   USB4 re-init/re-probe.
2. Decide F1: retry `-ENOLINK` within the source deadline (treat as "not ready
   yet") and/or wait for DP-IN HPD before/while activating; cross-check against
   the recovered macOS behavior with the already-pinned REA pipeline
   ([REA-DPIN-FINDINGS.md](../REA-DPIN-FINDINGS.md)) before changing the
   handshake.
3. Fix the Gala/simpledrm race for test boots (make the session wait for the
   apple DRM card; the lightdm DRM-wait drop-in is the natural place) and
   remove `/home/sdolbec/.cache/mseries-gala-failed` before the next test boot.
4. Re-run the one-shot controlled boot after 1–3; run the collector on a
   healthy boot; keep bypass armed on the first re-run.
5. Rollback remains available and unused; the staged install is intact.
6. Stop-rule note: this boot used bypass, so the unbypassed DPRX question is
   still unanswered; fix the above before deciding on a macOS trace.

## Evidence (this machine, outside the repo)

Saved journal exports (sha256):

- boot-1-full.log `938704e3cc6bdd7df4533361c30fb280c41b79da52fb0482401835650ae52405`
- boot-2-full.log `ac1835a6f1ee8b6fc9a4d9a2ed23aac9d2ae592d3dfda9570a0318270c621f79`
- boot-2-kernel.log `da5d15bc44c41e2d980f9c0bd9b5b46c9e312cb7de87a3c716609da3e2b248b9`
- boot-3-kernel.log `663879f4c4fd5a5e87038a5f64fc53b81aac7efa6f414de9a63b0da83f08c797`

Directory: `/home/sdolbec/dptunnel-logs/controlled-c6fd906-outcome/`

REA reference (already used for the DP-IN RE): <https://github.com/morluto/rea>
