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

## Likely trigger (not proven)

On the dptunnel kernels the DCP for the external pipe (`28cc00000`, `tunnel: 1`) is wired to
the DP-IN path and emits connector/hot-plug events (`oob_hotplug`,
`dcp_hotplug() connected:0 valid_mode:0`) very early in the boot. The stock kernel has no
such path, which fits it being unaffected. Why boot -3 (same kernel, earlier `boot.bin`) did
not crash is not explained by this analysis: the 11:20 `boot.bin` change is the only known
difference, so treat the new device tree as the suspect for the **old** entry too. That
contradicts the "fallback boot untested but statically fine" assumption in
`CONTROLLED-TEST.md`; the fallback was in fact tested by the owner and failed.

## What to do

- **Daily use: boot the default stock entry.** It works with the current `boot.bin`.
- Do not assume the older dptunnel entry is a safe fallback until this is understood.
- Next engineering step (Codex/DeepSeek): find which uevent/connector triggers the mutter
  assert (`udevadm monitor -k -s drm` during a test boot, plus `journalctl -b` for the gala
  lines just before the abort), and decide whether the experiment should keep the external
  DCP connector from reporting a connected/invalid-mode state to userspace until a real mode
  exists. A test boot needs the owner and must not be run unattended.
- Rolling `boot.bin` back to `boot.bin.KNOWN-GOOD-pre-usb4-20261015-152345` would restore the
  pre-11:20 state for the old entry, but that is a boot-chain change and the owner's call.
