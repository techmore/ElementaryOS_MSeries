# Pantheon does not start on the dptunnel GRUB entries (owner report) — what the logs show

2026-10-16, Claude. Read-only. Owner report: the other GRUB entries "didn't load Pantheon",
apps and terminal would not open, the mouse kept spinning. The default stock-kernel entry
(`7.1.13-3-2-ARCH`, current boot) runs Pantheon normally with the same new `boot.bin`.

## Boots involved (journal boot offsets at the time of writing)

| Boot | Entry | Result |
|---|---|---|
| -3 (09:00-11:42) | old `elementary-usb4-dptunnel`, before the 11:20 `boot.bin` change | normal: gala started 9.5 s, session ran for hours |
| -2 (11:45-11:47) | `elementary-usb4-dpin-controlled` | **gala aborted 3 s into the boot (SIGABRT, coredump saved)**; later the DP-IN oops (see the first-boot evidence note) |
| -1 (11:48:27-11:48:57) | old `elementary-usb4-dptunnel`, after the `boot.bin` change | gala `Main process exited, code=killed, status=9/KILL` 0.7 s after start; autologin session collapsed, lightdm greeter appeared, owner logged in at 14.5 s and held the power button at 36.5 s (`macsmc-input: Triggering forced shutdown!`) |
| 0 (11:49-now) | default stock | normal |

## The crash (boot -2, `coredumpctl info 1871`)

`/usr/local/lib/mseries/gala/bin/gala` aborts on a GLib assertion inside
`meta_kms_update_mode_set` (libmutter-18) called from
`meta_monitor_manager_apply_monitors_config` <- `meta_monitor_manager_ensure_configured`,
which was triggered by a **libgudev uevent** (a DRM hot-plug/change event). So: a display
hot-plug at session start makes mutter apply a monitor configuration and it asserts in KMS
mode-setting, taking the compositor down. With no compositor, Pantheon cannot start and the
cursor spins. Boot -1 shows the same shape (gala dies within a second; no coredump was kept).

## Root cause for the controlled-entry boot (boot -2): a known startup race

The assertion text recovered from the core is
`meta-kms-update.c:365:meta_kms_update_mode_set: assertion failed: (meta_kms_crtc_get_device (crtc) == update->device)`:
mutter was handed a CRTC from one KMS device while building an update for another, i.e.
a **second KMS device appeared while gala was already running**. Timeline of boot -2:

| t (s) | Event |
|---|---|
| 9.10 | lightdm autologin session opened |
| 9.59-10.27 | `io.elementary.gala@wayland` starting/started (only `simpledrm` exists) |
| 10.50 | `[drm] Initialized apple 1.0.0 for soc:display-subsystem on minor 2` (**appledrm registers**) |
| 10.88 | gala exits 134 (SIGABRT) |

In the good boot (-3) appledrm registered at 6.89 s, well before gala. This is exactly the race
already documented in `README.md` ("Login screen stalls ~2 min (gala race)"): gala starts
before the Apple DRM device exists and aborts when it appears. The repo ships the fix,
`lightdm-wait-for-drm.conf` (wait up to 30 s for `/sys/class/drm/card*-eDP-*`), but it was
**not installed** on this machine (`/etc/systemd/system/lightdm.service.d/` did not exist).
On the controlled entry appledrm registered ~3.6 s later than usual (new modules in the
initramfs and an extra `phy-apple-dpin` dependency), which widened the race window.

**Done 2026-10-16 (Claude, owner's machine):** installed the drop-in as documented
(`sudo install -D -m0644 lightdm-wait-for-drm.conf /etc/systemd/system/lightdm.service.d/wait-for-drm.conf`,
`systemctl daemon-reload`). lightdm was **not** restarted, so it takes effect at the next boot;
revert by deleting that file. Not yet verified on a dptunnel boot.

### Why appledrm registered 3.6 s late (measured, cause not proven)

Kernel-log timeline, good boot (-3) versus the controlled entry (-2):

| Event | -3 (good) | -2 (controlled) |
|---|---|---|
| crossbar `Switched dpin0 to dispext1,0` | 6.88 s | 8.18 s |
| `bound 38bc / 289c / 28cc` | 6.88 / 6.88 / 6.88 s | 8.18 / 8.21 / 8.22 s |
| `DCP booted` 38bc / 289c / 28cc | 6.888 / 6.891 / 6.893 s | **8.25 / 9.28 / 10.37 s** |
| `[drm] Initialized apple ... minor 2` | 6.893 s | **10.503 s** |

Two separate delays: (1) everything starts ~1.2 s later (`Failed to get dp-xbar: -517` at 7.0 s, then
the NHI/thunderbolt module probes at 8.17 s; the new initramfs also carries `thunderbolt`,
`thunderbolt_apple` and `phy-apple-dpin`, and it is 5 MB larger), and (2) the three DCP firmware
boots finish about 1 s apart instead of within 5 ms. The DRM device registers only after the last
DCP boots, so it lands at 10.5 s. The old-entry boot (-1) shows the early pattern (DRM at 6.63 s),
so the new modules/initramfs are the common factor in the late registration. Which of the new
pieces causes the serialised DCP boots is the open question for Codex/DeepSeek (candidates: the
managed `apple,dp-tunnel-phy` lookup deferring DCP 28cc until the ACIO child exists, and the extra
module-load work in the initramfs). The lightdm drop-in removes the *symptom* (gala starting
first) but registration at 10.5 s still delays the desktop by ~3.6 s on these entries.

## Boot -1 (old entry after the new boot.bin) is not explained by this

There appledrm registered early (6.63 s) and gala was `KILL`ed (status 9) 0.7 s after start,
with no coredump. The drop-in would not obviously help. Open: why gala was killed (no kernel
OOM or oops in that window); one observed difference from boot -3 is that the new `boot.bin`
was in place. Treat the old entry as unreliable until a boot with the drop-in installed is read.

## What to do

- **Daily use: boot the default stock entry.**
- Next dptunnel test boot: with the drop-in installed, check
  `journalctl -b | grep -E "Initialized apple|gala@wayland"` (appledrm must register before
  gala) and `coredumpctl list` for a new gala core.
- Engineering follow-up (Codex/DeepSeek): shorten appledrm registration on the dptunnel
  entries or keep `dcpext1`'s phy dependency from delaying the whole display subsystem.
- Rolling `boot.bin` back to `boot.bin.KNOWN-GOOD-pre-usb4-20261015-152345` stays an owner call.

## Probe-chain analysis of the late registration (DeepSeek/OpenCode, static)

Source-level check of the probe graph (revision `46bb8b6`; public patches
0004/0007/0010):

- `dcp_platform_probe` now calls `devm_apple_dpin_phy_get()` at probe time for
  nodes with `apple,dp-tunnel`, and the getter returns `-EPROBE_DEFER` until
  the DP-IN provider device is **bound**. So `dispext1`'s probe — and the DCP
  firmware boot and DRM registration that wait for it — is now gated behind
  the DP-IN phy binding.
- The DP-IN phy (`dpin1_0`) is a **child of the USB4 ACIO node**
  (`cio@b01ac0000` in `t600x-dieX.dtsi`) and its probe needs `atcphy1`
  (`devm_phy_get("atc-phy")`). The ACIO and ATC PHY are bound by the USB4
  modules (`thunderbolt_apple`, `phy-apple-atc`).
- `fw_devlink` additionally creates edges from the new phandles:
  `dispext1 → dpin1_0` (`apple,dp-tunnel-phy`) and `NHI → dispext1`
  (`apple,dp-source` on the NHI, consumed at NHI probe by
  `apple_dp_source_init`). The USB4 NHI therefore also waits for the DCP:
  the display and USB4 stacks now probe in one ordering chain instead of
  independently.

Net: on the controlled entry the external DCP cannot probe before the USB4
stack is up, and the ~1 s steps in the measured DCP boots
(8.25 → 9.28 → 10.37 s) match deferred-probe retries, ending with appledrm at
10.5 s (vs 6.9 s). This is a probe-ordering effect of the new binding, not a
regression in a single driver; the `-ENOLINK`/Oops fixes are unrelated to it.

To confirm on the next test boot (read-only): `journalctl -k -b | grep -iE
"deferred|cycle|EPROBE"`, `cat /sys/kernel/debug/devices_deferred` after
login, and the `[drm] Initialized apple` / DCP timestamps.

Options for review (not implemented):

1. **Accept**: the drop-in removes the session crash; the desktop starts
   ~3.6 s later only on the dptunnel entries.
2. **Remove the probe-time edge**: make the DCP↔DP-IN reference non-phandle
   (resolve at connect time through the existing `apple_dp_source` mapping and
   the ACIO parent) so `dispext1` no longer waits for the USB4 stack. This
   changes binding 0004/0007 and needs a review pass.
3. **Keep the binding, shorten the USB4 bring-up**: the ACIO/ATC/NHI probes
   currently complete at ~8.2 s; the DCP chain then adds two ~1 s retries.
