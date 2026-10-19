# J314S dock hotplug, desktop startup and old module cleanup — 2026-10-18

Later [desktop startup repair](../../display-space/STARTUP-FIX-2026-10-18.md)
addresses the panel sizing, stale-mode and disabled-dock readiness paths below.
Fresh-login verification remains pending; dock/audio faults remain open.

Follow-up to the [earlier boot archive and VRR result](2026-10-18-j314s-vrr-and-boot-archive.md).
The owner reported that unplugging/replugging the dock appeared to make audio
start, the native top bar was initially overstretched, and startup had large
delays. These are owner observations, not a controlled reproduction. The earlier
scoped dock/visual pass remains valid; this session does not establish reliable
hotplug, display audio, sustained VRR or suspend/resume.

## Observed host state

- elementary OS 9 Early Access / Ubuntu 26.04.1, aarch64 J314S/M1 Pro.
- Running kernel: `7.1.12-2-20261017.20-sep-ARCH` (Aurora `.20`). The current
  command line selects `appledrm.show_notch=1`; `appledrm.hdmi_audio=1` is absent.
  A separate non-default display-audio test entry exists, but was not selected
  or changed by this session. Presence of that entry proves no audio result.
- `/boot` is a 499 MiB FAT partition, about 285 MiB used / 215 MiB available
  at the initial check (58%). This cleanup concerns modules on the main Linux
  filesystem, not another boot-partition cleanup.
- `wpctl status` showed the built-in headphone sink, J314 speaker convolver as
  configured default, and network audio sinks. No dock/HDMI sink was listed in
  that snapshot. No playback test or audio routing change was performed.

## Startup, display and dock evidence

Journal wall-clock entries below are October 18 in America/New_York; monotonic
values are seconds after kernel start. These observations are correlated with
the reported symptoms, but do not prove a shared root cause.

| Observation | Evidence and limit |
| --- | --- |
| System boot timing | `systemd-analyze`: kernel 7.560 s + userspace 6.876 s = 14.437 s; graphical target after 4.771 s of userspace (about 12.3 s total). This excludes earlier firmware/boot-menu time and does not measure time until the whole desktop feels ready. |
| Service timing | `systemd-analyze blame`: Incus 4.456 s; Incus startup 2.241 s; LightDM 1.098 s. Blame times overlap and are not proof of the critical path. Services were not disabled. |
| Rejected display configuration | At +12.796 s and +62.944 s Gala rejected saved `3024x1890@120.000`. `~/.config/monitors.xml` requests that mode at scale 1.5; the current eDP sysfs modes list `3024x1964`. This is consistent with a stale cropped-display configuration after full-height boot; it does not independently explain the top-bar rendering. |
| Panel startup | At +17.941 s Gala reported `1 panels failed to start in time, showing the others`. Wingpanel also logged GTK layout assertions. The failed panel was not identified by that message. |
| Dock hotplug faults | Around 13:08:16–17 the kernel logged repeated USB `-71` transfer/reset failures, a PCIe tunnel reset acknowledgment timeout and ATC pipehandler lock failure. Reconnect/device enumeration messages followed around 13:08:22–28. No controlled cable or dock comparison was made. |
| Ethernet firmware | Dock Ethernet twice failed to load `rtl_nic/rtl8153b-2.fw` with `-2`; the corresponding firmware file is absent. This is a separate concrete finding, not proof of the audio/display cause. |
| Audio logs | WirePlumber logged unaligned filter latency after the hotplug sequence; PipeWire logged network-audio latency warnings. Neither establishes dock audio playback. |

## Completed cleanup

The earlier boot archive left module directories behind. This session removed
three obsolete, non-running trees from `/usr/lib/modules` (`/lib/modules`
resolves to the same location):

- `7.1.12-2-20261015.19-sep-ARCH` — approximately 173 MiB.
- `7.1.13-elementary-fairydust-usb4` — approximately 116 MiB.
- `7.1.13-elementary-fairydust-usb4-dptunnel` — approximately 124 MiB.

Before removal, each tree was checked against the running release, all installed
dpkg file lists, and both active GRUB configuration files. None was running,
package-owned, or referenced by the active menus. The complete trees were
archived locally; all **5,771 regular files** were SHA-256 compared against the
archive, with directory and symlink checks, before deleting originals.
GNU tar's initial comparison reported timestamp differences; the cleanup
stopped without deleting anything. Content verification then passed and the
removal completed. The private gzip archive is **130,429,171 bytes**, SHA-256
`afce98bf806fd6b4e5dce210f18cdb97b0c2cb7b14df4d15d909e7741c281df3`.
It remains in the owner's Codex outputs at `2026-10-18/pok/outputs/old-kernel-modules.tar.gz`.
No binary backup or raw machine configuration is committed to Git.

Retained trees:

- Running `.20`: `7.1.12-2-20261017.20-sep-ARCH`.
- Installed `.20-enh1` trial: `7.1.12-elementary-aurora20-enh1`, owned by
  `linux-image-elementary-aurora-enhancements`.
- Original Asahi fallback: `7.1.13-3-2-ARCH`.

The archive is smaller than the removed trees, but no before/after physical
free-space measurement was retained; do not treat summed directory sizes as
measured Btrfs space recovery. [Machine-readable receipt](2026-10-18-j314s-module-cleanup.json).
No bootloader, kernel image, initramfs, m1n1 payload, default/one-shot entry,
display settings or running audio stack was changed. Both `grub-script-check`
checks passed. Retaining fallback files does not prove fallback boot compatibility.

## Recovery and follow-up

For module recovery, verify the archive hash, inspect its members and extract
only the required `usr/lib/modules/<release>` tree with root permissions relative
to `/`; then regenerate that release's module metadata with `depmod -a <release>`.
Restore the matching kernel/initramfs from the separate earlier boot archive if
needed. Modules alone do not restore a bootable entry; shared m1n1/DT compatibility
still needs review. Never overwrite newer boot menus from a historical backup.

Next investigation should capture the active display configuration and profile
watcher alongside the saved configuration before reconciling full-height versus
cropped modes. Identify the late panel rather than assuming it was Wingpanel.
Record audio device/routing state and kernel/userspace logs before and after a
controlled dock cycle, and distinguish speakers, headphones, network audio and
display audio. Check the missing Ethernet firmware separately. A fresh boot and
hotplug comparison is needed to measure improvement; this cleanup does not claim
to fix the reported symptoms or advance the HDMI physical-port qualification.

Read-only commands used: `uname -a`, `/proc/cmdline`, `dpkg-query`, installed
`/var/lib/dpkg/info/*.list` inspection, `df -h`, `du -sh /lib/modules/*`,
`systemd-analyze`, `systemd-analyze blame`, `journalctl -b`, `wpctl status`,
eDP sysfs modes, and inspection of `monitors.xml`, GRUB files/environment.
Mutation was limited to creating the verified private archive and removing the
three named obsolete module trees. No reboot, logout or audio restart was run.
