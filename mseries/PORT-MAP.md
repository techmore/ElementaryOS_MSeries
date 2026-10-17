# Port map: Omarchy Mac hardware behavior → elementary OS 9

This map separates the historical scaffold from the maintained package
reference and from hardware verification. Presence in the repository does not
mean the mkosi image has been built or tested.

## Current Apple Silicon package reference

The maintained source is
[omacom/omarchy-mac-pkgs](https://github.com/omacom/omarchy-mac-pkgs), main at
commit 222f7a8599bbdd287ac6a95362cd51c5b024baae (audited 2026-10-13). Its
packages target Arch Linux and have their own staging, package tests, and
integration-test contract. This elementary project uses them as a behavioral
reference only; translate relevant changes to Ubuntu/mkosi and Pantheon/Gala.
The source boundary is documented in
[CONTRIBUTING.md](https://github.com/omacom/omarchy-mac-pkgs/blob/main/CONTRIBUTING.md).

| Current package source | Hardware behavior | Elementary translation | Status |
|---|---|---|---|
| `omarchy-mac/bin/omarchy-wifi-resume-fix` and its systemd unit | Recover supported Apple Broadcom Wi-Fi after resume. | The image layer has a systemd recovery unit and firmware provisioner. | Present in source; factory-image path not verified. |
| `omarchy-mac/bin/omarchy-audio-asahi-mic-map` and WirePlumber configuration | Route the Asahi DSP microphone into the desktop audio graph. | Requires an Ubuntu audio-session integration and the Asahi DSP packages. | Headset-mic priority rule ported (`mseries/audio/asahi-headset-mic.conf`). The stereo-mapping tool (`omarchy-audio-asahi-mic-map`, a pactl/pw-dump/parec reconciler) is **deliberately not ported**: its stated reason is Quickshell-specific (that shell wants a stereo `Audio/Source` for its level meter and volume control). Pantheon's sound indicator uses libpulse and accepts a mono source. Revisit only if an app records silence from the built-in mic on this desktop. |
| `omarchy-mac` speaker-safety preset and setup entrypoint | Keep the Apple speaker safety daemon installed and enabled. | Desktop install scripts provide speakersafetyd and an optional Asahi DSP chain; the factory image does not install this path yet. | Desktop audio output passed with the matched PipeWire LV2 plugin; preserve safety service. |
| Optional Tether continuity add-on | Direct iPhone SMS/iMessage mirroring and OTP handoff to a Linux browser; does not require a Mac relay. | Removable ARM64 package installer and opt-in Brave native-host helper; keep out of the base image pending iPhone/Brave qualification. | Upstream v0.2.37 is MIT and checksum-pinned. Current BlueZ 5.85 is below the upstream 5.86 minimum for Messages; see `mseries/TETHER-CONTINUITY.md`. |
| `omarchy-mac-boot/files/etc/mkinitcpio.conf.d/92-omarchy-mac-hid.conf` | Load Apple input and dock drivers early in an Arch initramfs. | The image overlay uses initramfs-tools and carries its own Apple HID module list. | Present in source; factory-image path not verified. |
| AVD dependencies documented by the package README and Omarchy runtime | Provide Apple video-decode firmware and the VA-API bridge. | Needs an Ubuntu kernel with AVD support, firmware provisioning, and userspace bridge. | VA-API bridge build integration is present at c653eaa; factory build, kernel/firmware provisioning and codec/client qualification remain open. |
| `omarchy-mac/bin/omarchy-battery-charge-limit` | Configure a persistent Apple SMC charge threshold. | No equivalent M-Series settings interface is currently documented. | Candidate enhancement; first confirm supported sysfs controls on this host. |
| `omarchy-mac-boot` lifecycle hooks, vendor firmware and Limine/U-Boot support | Maintain the Arch boot chain and encrypted-install lifecycle. | elementary's mkosi, initramfs-tools and GRUB/Asahi path have different contracts. | Do not copy; translate only independently verified behavior. |
| USB4 suspend behavior in the current Fairydust kernel | ACIO refuses suspend while a USB4 dock link is active. | A future kernel handshake or docked-lid policy is needed. | Known issue: system remains awake with its display off. |
| Historical `omarchy-mac` quattro ambient keyboard automation | Adjust keyboard LEDs from the AOP illuminance sensor and pause for manual changes. | `mseries/keyboard-backlight/backlight.py` uses the ALS sensor and UPower in Pantheon. | Implemented; measured on the M1 Pro at 141 lx. Lock/lid and suspend qualification remains. |
| `omarchy-mac/bin/omarchy-audio-watchdog` (checked 2026-10-14 at omarchy-mac-pkgs 222f7a8) | Restarts PipeWire/WirePlumber when asahi-audio's DSP filter chains wedge WirePlumber at logout or resume (hung `pactl`, full-CPU main thread). Restarts only while the screen is unlocked, with a restart budget. | We run the same asahi-audio DSP chain through the PipeWire LV2 plugin, so the same failure applies. Needs a Pantheon-safe port (no Quickshell handling). | **Ported 2026-10-14** as `mseries/audio/audio-watchdog.py` (user service, enabled by `enhance.sh`): same restart budget and settle rules, no Quickshell handling; lock state from logind `LockedHint` (unverified on Pantheon). |
| OpenCode Desktop (anomalyco/opencode `v2`, Electron; not part of omarchy-mac-pkgs) | Upstream ships only an amd64 .deb. | `opencode-desktop/build-opencode-desktop.sh` builds the arm64 .deb from source (rev 4617210) and repacks its control file for Ubuntu 26.04 t64 names (`libgtk-3-0t64`, `libatspi2.0-0t64`). Dev channel, package `opencode-dev` 2.0.26, MIT. | Built and installed on the owner desktop 2026-10-16; `ldd` clean. **Not launched yet.** |
| `omarchy-mac/bin/omarchy-mac-setup-keyboard` | Hands Apple function-key mode (`hid_apple fnmode`) to the kernel default (3, auto) and retires generated `hid_apple.conf` lines. | No `/etc/modprobe.d/hid_apple.conf` exists here, yet the running value is `fnmode=1` (media keys first). Find which initramfs or module option sets it and decide the default deliberately. | **Open.** Behavior differs from upstream's default; needs owner preference. |
| `omarchy-mac/bin/omarchy-mac-setup-system` Broadcom quirk removal | Removes the Intel-only `brcmfmac feature_disable=0x82000` line, which breaks Apple Silicon Wi-Fi. | `/etc/modprobe.d/brcmfmac.conf` is absent on the M1 Pro. | **Verified clean 2026-10-14.** Keep the guard in the image tests. |
| `omarchy-mac/bin/omarchy-battery-charge-limit` | Persistent SMC charge threshold. | `mseries-power` plus the quick-settings switch; `macsmc-battery/charge_control_end_threshold` reads 80. | **Ported and verified 2026-10-14.** |
| `omarchy-mac/bin/omarchy-mac-setup-system` speaker-safety preset | Enable `speakersafetyd` once. | `speakersafetyd` is active on the M1 Pro. | **Ported on desktop; factory image still missing the install path.** |

Mac-only changes to the installed Omarchy packages stay in
`omacom/omarchy-mac-pkgs`; general Omarchy behavior belongs upstream, and
one-shot installation changes belong in the Omarchy Mac installer. No code in
those repositories was changed by this elementary audit.

## Original scaffold snapshot (historical)

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
| `install/hardware/apple/video-decode.sh` | `avd-fw` firmware + `libva-v4l2_request-avd` VA-API bridge | **BRIDGE BUILD INTEGRATED; UNQUALIFIED** | Factory builds the pinned VA-API bridge into `/usr`. Firmware and `CONFIG_VIDEO_APPLE_AVD` remain separate gaps; upstream reports no supported matrix rows. Build and hardware codec/client qualification remain pending. |
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
