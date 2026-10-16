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
