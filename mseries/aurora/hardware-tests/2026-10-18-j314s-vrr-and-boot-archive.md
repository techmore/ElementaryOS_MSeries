# J314S boot archive and built-in VRR — October 18, 2026

The owner reports the dock works on the running Aurora `.20`, and both displays
look normal after enabling built-in VRR. The setting remains enabled in the
current `desk-4k` profile. The twelve-second fullscreen test observed kernel VRR
activation **briefly**; sustained adaptive refresh remains unqualified.

## Boot space reclaimed

`/boot` initially had about 23 MiB free (96% used), while the main Linux
filesystem had about 93 GiB free. Two verified local archives reclaimed space:

| Archive | Files | Space recovered |
| --- | --- | --- |
| Older `m1n1/boot.bin.pre-*` backups | 4 | 34.48 MiB |
| Fairydust USB4 / DP-IN / VRR test kernels and initramfs images | 7 | 157.15 MiB |

The [archive receipt](2026-10-18-j314s-boot-archive.json) retains every filename,
size and SHA256. Files were copied to the main filesystem, checksum-verified
and fsynced before their `/boot` originals were removed. Six corresponding
`elementary-usb4-*` entries were removed from `custom.cfg`; the generated
`grub.cfg` sources that file, so no regeneration was needed. Both GRUB syntax
checks passed. `/boot` then had **214.02 MiB free, approximately 58% used**.

Both Aurora kernels and their initramfs images, stock Asahi recovery, active
m1n1/EFI bootloaders, generated menu and one-shot environment were unchanged by
this cleanup. Kernel module directories remain on the main filesystem. These
are checks at archive time; subsequent independent full-height menu changes
have separate records. Preserved recovery files do not prove a recovery boot.

Private Codex outputs retain the restorable binary archives, complete prior
menus, environment and manifests under `bootloader-backups-20261018-060834` and
`fairydust-test-kernels-20261018-062354`. Binary firmware/kernel backups and raw
machine configuration are not Git source assets and remain local.

To restore an archived test later, copy its exact kernel/initramfs pair back to
`/boot`, merge its archived entry into the **current** `custom.cfg`, and check
syntax and every referenced file. For an archived bootloader, use the verified
copy from the local archive rather than the old `/boot/m1n1/boot.bin.pre-*` path.
Do not blindly overwrite a newer menu, reinstate a stale one-shot choice, or
swap the shared boot payload: historical Fairydust device-tree compatibility
still needs review. Maintain enough free boot space for recovery.

## VRR observations

Kernel: `7.1.12-2-20261017.20-sep-ARCH`. This is a new observation after the
experimental exp1 freeze; the immutable freeze and earlier receipts are unchanged.
The [sanitized receipt](2026-10-18-j314s-vrr-smoke.json) records the sampled state.

| Output | Selected mode | Scale / position | Role |
| --- | --- | --- | --- |
| Built-in `eDP-1` | `3024x1890@120.000+vrr` | 2 / `(0, 0)` | Primary |
| Dock `DP-2` | Fixed `1920x1080@60.000` | 1 / `(1512, 0)` | Secondary |

The driver advertises 24–120 Hz on the built-in panel. That range is a capability,
not measured scanout timing. The first temporary selection reverted within seconds
because the existing profile watcher reapplied its saved fixed-120-Hz mode.
Changing **only** the built-in mode in the matching desk profile retained VRR;
the laptop-only profile and `monitors.xml` were left unchanged. The watcher
executable was not modified. Its existing external-mode nudge briefly selected
59.94 Hz during reapply, then restored 60 Hz.

A native fullscreen animation on `eDP-1` requested 24/60/90-fps content for twelve
seconds. Of 25 DRM samples, three (approximately 1–2 seconds after sampling began)
had built-in `VRR_ENABLED=1`. It returned to zero while the animation continued.
The dock remained connected at fixed 1080p/60 in all sampled animation states.
VRR stayed selected after the app closed. The owner subsequently confirmed
both displays look normal and requested keeping the setting.

This establishes selected VRR, a kernel activation path and a scoped dock/visual
smoke result. It **does not establish sustained VRR, optical refresh timing,
suspend/resume stability, or battery savings**. The focus state was not recorded
in this first probe; compositor focus/policy and presentation timing need
investigation. The dock's specific physical HDMI/DP port was not independently
checked. No kernel or boot changes were made for the VRR experiment.

## Read-only state and controlled content tools

The [DisplayConfig interface](https://github.com/GNOME/mutter/blob/main/data/dbus-interfaces/org.gnome.Mutter.DisplayConfig.xml)
reports the selected mode, including fixed versus variable mode properties.
Use that together with the kernel property, not the mode name alone.

```sh
gdctl show --modes --properties
cc -Wall -Wextra -Werror -O2 mseries/hardware/drm-vrr-state.c \
  -o /tmp/mseries-drm-vrr-state $(pkg-config --cflags --libs libdrm)
# Discover the display-subsystem DRM card on this boot; IDs can change.
/tmp/mseries-drm-vrr-state /dev/dri/cardN
```

The libdrm helper opens only the explicitly supplied node read-only and prints
connector connection/capability and CRTC `VRR_ENABLED`. It changes no modes and
requires permission to read that device. It does not measure panel cadence.

The content probe requires GTK4, PyGObject and Cairo GI support. It does not enable
VRR or touch display configuration. It opens its own built-in fullscreen window
for twelve seconds; Escape closes it sooner. It refuses an existing output:

```sh
python3 mseries/hardware/vrr-fullscreen-probe.py \
  --connector eDP-1 --output /path/to/private/new-content-observation.json
```

Sample the read-only DRM helper alongside it. The public probe now records
window active/fullscreen state for the next investigation. These are portable
adaptations of the local tools; publishing them did not run another screen test.

## Next-kernel VRR acceptance

1. Record kernel release, live identity and image/initramfs hashes. Keep the
   working `.20` and stock recovery paths. Rediscover DRM node and CRTC IDs.
2. Capture current profile, mode, scale, layout, color, brightness and full-height
   versus cropped display state. This VRR change and the later full-height trial
   invalidate an unmatched earlier fixed/cropped power comparison.
3. Preserve the dock's fixed 1080p/60 configuration. Run fixed-120-Hz baseline and
   built-in VRR trials with an independent rollback and matching saved profile.
   Inspect/save all settings before editing; do not copy private profiles to Git.
4. Capture kernel VRR properties alongside 24/60/90-fps fullscreen content,
   application presentation timing and active/fullscreen/focus state. Explain
   the brief 3/25 activation result before recording sustained VRR as passed.
5. Check flicker, blanking, tearing, cursor, video and fullscreen transitions
   with user observation. Compare display/Thunderbolt faults with fixed baseline.
6. Separately test long dock idle, lock/DPMS, dock unplug/replug, laptop-only
   profile and suspend/resume. Retain exact modes/layout and observed dock picture.
7. Keep failures and pending tests explicit. No release promotion or energy claim
   follows from a selectable mode, a short test, or a successful build.

For the current desk profile, rollback means restoring its original built-in
fixed-120-Hz mode and applying the captured dual-monitor layout. Keep the
external settings intact. The private output archive includes an exact rollback
command for this machine; a raw profile contains monitor identities and stays private.
