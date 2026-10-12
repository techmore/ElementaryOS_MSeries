# Port map: omarchy-mac (quattro) Apple fixes → elementary (Ubuntu/mkosi)

This is the original scaffold port map, not a current hardware status report.
For the October 12 review, current dock support, Touch ID research and local AI
plan, see [the optimization audit](OMARCHY-AUDIT-2026-10.md).

Source: https://github.com/omacom/omarchy-mac, branch `quattro`,
`install/hardware/apple/`, `bin/omarchy-hw-apple`, `bin/omarchy-audio-asahi-mic-map`,
`docs/apple-silicon-trackpad.md`, `docs/arm-package-sources.md`.
Target: https://github.com/elementary/os `main` (Ubuntu resolute, mkosi,
initramfs-tools, Pantheon).

Legend: **PORTED** = translated into `mseries/` in this commit.
**DOCUMENTED** = analyzed, no file yet (needs hardware testing or repo work).
**OUT OF SCOPE** = correctly does not apply to this target.

## Apple Silicon (M-series) — in scope

| omarchy source | What it does | Disposition | Notes |
|---|---|---|---|
| `install/hardware/apple/audio.sh` | pipewire-pulse + rtkit + asahi-audio + speakersafetyd, enable daemon | **PORTED** (packages + units) | Ubuntu names: `pipewire-pulse`, `pipewire-alsa`, `rtkit`. `asahi-audio`/`speakersafetyd` are NOT in Ubuntu archives — `mseries/packages.arm64` lists them as TODO needing an Asahi PPA or source build. Daemon enable logic preserved as a first-boot unit note. |
| `install/hardware/apple/video-decode.sh` | `avd-fw` firmware + `libva-v4l2_request-avd` VA-API bridge | **DOCUMENTED** | Firmware blob + translator have no Ubuntu-resolute package names confirmed. Listed in `packages.arm64` as TODO. Kernel side (`CONFIG_VIDEO_APPLE_AVD=m`) is a kernel-config question for BUILD-NOTES. |
| `install/hardware/apple/fix-asahi-hid-race.sh` | early-load `hid_apple`, `hid_magicmouse` via mkinitcpio so trackpad never rebinds mid-boot | **PORTED** | Ubuntu uses initramfs-tools, not mkinitcpio: `mseries/initramfs-tools/modules.d/apple-silicon.conf`. See omarchy `docs/apple-silicon-trackpad.md` for the race analysis (linked, not copied). |
| `install/hardware/apple/fix-wifi-resume.sh` | systemd unit after suspend that reloads `brcmfmac` when firmware wedges (BCM4378/BCM4387, aarch64 only) | **PORTED** | `mseries/systemd/system/omarchy-wifi-resume-fix.service` + `mseries/sbin/mseries-wifi-resume-fix`. Unit is init-system-agnostic systemd; script rewritten for `modprobe`/`NetworkManager` without pacman helpers. BCM4388 (M2 Max/Ultra) deliberately excluded per upstream testing. |
| `install/hardware/apple/enable-notch.sh` | Enable notch pixels for notch-aware bars | **NOT ENABLED ON PANTHEON** | Wingpanel centers the clock and has no notch-avoidance support; the Apple Silicon image leaves the default cropped 16:10 mode enabled. |
| `bin/omarchy-hw-apple` | gate: aarch64 + `apple,` in device-tree compatible | **PORTED** (as pattern) | Every ported script keeps the same gate (`uname -m` + `/proc/device-tree/compatible` containing `apple,`) so a Raspberry Pi never picks up the Asahi stack. |
| `bin/omarchy-audio-asahi-mic-map` + `default/wireplumber/…asahi-headset-mic.conf` | Asahi mic stereo-map reconciliation | **DOCUMENTED** | Python tool is largely distro-agnostic but plugs into Omarchy's WirePlumber/service layout; needs re-homing to elementary's audio session before carrying over. |
| `bin/omarchy-brightness-display-apple` (`asdcontrol`) | Apple Studio/XDR display brightness | **DOCUMENTED** | `asdcontrol`/`tobi-try` are omarchy-edge-only packages (see `docs/arm-package-sources.md`); no Ubuntu source confirmed. |
| `docs/arm-package-sources.md` edge-repo policy | pacman `Usage = Sync` + explicit `omarchy/…` selection | **OUT OF SCOPE** (pattern noted) | pacman-only. The *pattern* (pin Apple-specific packages from a dedicated source, keep the rest rolling) should be re-expressed as apt pinning (`repos/common-files/etc/apt/preferences.d/`) once an Asahi PPA exists. |

## New findings (captured on hardware, not ported from omarchy)

| Area | Finding | Disposition | Notes |
|---|---|---|---|
| USB-C dock video (Dell WD19S) | Dock displays need **DisplayPort Alt Mode**; Asahi M1 `DP Alt Mode`/`Thunderbolt` are both **WIP**, so dock video/mouse do not work on stock `linux-asahi`. | **DOCUMENTED + build kit** | New doc `mseries/USB-C-DOCK-DP-ALT-MODE.md`. Live evidence: no DP DRM connector, `ATCPHY_PIPEHANDLER_STATE_USB4 not implemented`, `Failed to lock pipehandler`. Real fix = experimental `fairydust` kernel; build kit `mseries/fairydust/` (PKGBUILD + build-and-install.sh + verify.sh), blessed port = front-left on j314. |
| Signal Desktop messaging app | elementary ships Flatpak + Flathub (AppCenter). `org.signal.Signal` is aarch64-clean and installed as a user Flatpak on the live transform. | **PORTED** (packages) | `mseries/packages.arm64` lists it; `transform/elementary-grow.sh` adds Signal's official apt repo and installs `signal-desktop` into the new root so both transport paths exist. |

## Intel Macs (T2, SPI keyboard, NVMe, Broadcom-STA) — out of scope for M-series

| omarchy source | Disposition | Reason |
|---|---|---|
| `fix-t2.sh` (linux-t2, t2bce, t2fanrd) | **OUT OF SCOPE** | Intel T2 machines only; Apple Silicon has no T2 bridge. |
| `fix-spi-keyboard.sh` (2015–2017 MacBooks) | **OUT OF SCOPE** | Pre-T2 Intel keyboard controller. |
| `fix-suspend-nvme.sh` (2015–2017 PCI NVMe) | **OUT OF SCOPE** | Same Intel generation. |
| `fix-brcmfmac-supplicant.sh` (`feature_disable=0x82000`) | **OUT OF SCOPE — do NOT apply** | Upstream gates this to `x86_64` on purpose: on Apple Silicon BCM4378/BCM4387 the firmware offload is the half that *works*; disabling it wedges auth (upstream #7439). |

## Compositor/desktop-specific — out of scope

| omarchy source | Reason |
|---|---|
| `electron-gl.sh`, Hyprland monitor/bar configs, `enable-notch` *bar* intent | Hyprland/Electron launcher wrapping; elementary ships Gala/Pantheon. Notch modprobe option itself is carried (display full-height), bar integration is not. |
| `install/helpers/arm-package-sources.sh`, `fix-arm-packages.sh`, mirror/channel/test scripts | pacman + omarchy edge-repo machinery; no Ubuntu equivalent in this commit. |
