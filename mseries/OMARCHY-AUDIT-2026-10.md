# Omarchy Mac optimization audit — 2026-10-12

Target: elementary OS on MacBookPro18,3 (M1 Pro / j314s).
Observed kernel: `7.1.13-1-2-fairydust-usb4-ARCH`.
The initial port used omacom/omarchy-mac quattro at
ba546a61f881c1fe9d79d75ec050eab048b8cb63. The current package source was
audited separately on 2026-10-13; see the source refresh below.

## Source refresh — 2026-10-13

The maintained Apple Silicon package repository is
[omacom/omarchy-mac-pkgs](https://github.com/omacom/omarchy-mac-pkgs), checked
at main commit 222f7a8599bbdd287ac6a95362cd51c5b024baae. Its packages are
Arch-specific add-ons; each stages independently into DESTDIR and owns its
package tests, with separate integration tests for runtime contracts. Mac-only
installed hardware behavior belongs there, general desktop behavior belongs in
omacom/omarchy, and one-shot installation belongs in the installer repo.

For this elementary port, treat those packages as the current behavioral
reference. Do not copy Arch packages or package-manager hooks into Ubuntu.
Translate only useful hardware behavior into apt/mkosi and Pantheon/Gala, and
keep any change in its proper upstream repository.

## What our code already carries

| Area | Local implementation | Audit disposition |
| --- | --- | --- |
| Display brightness and OSD | `mkosi.images/apple-silicon/overlay/usr/libexec/mseries-brightness`, `mseries/apply-desktop-settings.py` | Pantheon-specific translation already present; preserve the working path. |
| Command shortcuts, screenshots, window controls | `mseries/apply-desktop-settings.py` | Already translated for Gala; Hyprland bindings should not be copied. |
| Wi-Fi firmware and resume | Apple image firmware/resume scripts and systemd services | The recovery script now has focused regression coverage; factory-image provisioning and live suspend/resume still need an M1 Pro image test. |
| Early Apple HID loading | Apple image initramfs module configuration | Port exists; check the actual booted Arch initramfs as well as the Ubuntu image. |
| Dock USB and Ethernet | `mseries/fairydust/usb4/` | USB2 peripherals and USB3 Ethernet verified in the kit's current report; older desktop/port-map wording was stale. DP tunneling remains a separate unresolved feature. |
| Gestures | `mseries/install-touchegg.sh` | Pantheon integration exists; verify gestures after session restart. |
| Panel integration | CodexBar, Signal, clockright and network installers | Existing elementary integrations, outside Omarchy hardware porting. |

Code presence is not a fresh hardware regression test. This audit did not reboot,
cycle the dock, suspend the machine or benchmark the GPU.

## Highest-value gaps

Audit correction, 2026-10-13: the earlier list wrongly marked ambient keyboard
lighting as missing. `mseries/keyboard-backlight/backlight.py` already reads the
AOP ALS sensor, changes only the keyboard through UPower, and pauses after manual
adjustments. On the M1 Pro it adjusted the keyboard from 0 to 59/255 at 141 lx.
The remaining work is interactive qualification of appearance, lock/lid and
suspend/resume behavior, not another port.

The transformed desktop also now has a tested internal-speaker path:
speakersafetyd protects the amplifier, the Asahi DSP packages supply the model
profile, and a PipeWire LV2 filter plugin built for Ubuntu's exact PipeWire
version enables the DSP graph. The audio check passed after installation. The
factory image still lacks this install path; do not enable internal speakers
without the safety daemon and preserve the existing volume during setup.

1. **Hardware video decoding.** `mseries/packages.arm64` still marks `avd-fw`
   and `libva-v4l2_request-avd` as TODO. Upstream
   package documentation identifies both as dependencies: a firmware blob
   alone does not make browser VA-API work. No `/dev/video*` was observed in
   this audit. Validate the kernel configuration, firmware, userspace bridge
   and an actual decoded video before promising lower CPU/power use.
2. **Image audio packaging.** The tested desktop install is described above,
   but `mseries/packages.arm64` does not yet reproduce its complete safe DSP
   chain. Carry the pinned PipeWire LV2 build and audio package sources into the
   image only after their build and volume-preservation path are reviewed.
3. **Touch ID / SEP.** The old categorical unsupported statement is outdated.
   [Omarchy's official September announcement](https://omarchy.org/news/2026/09/introducing-omarchy-m/)
   reports SEP-based Touch ID work and lists it as an initial-release target.
   [SiliconForested's September 29 X post](https://x.com/SiliconForested/status/2104994209434574999)
   advertises a test kernel with Thunderbolt, SEP and AVD work.
   Direct X access returned HTTP 403; the post was discovered via
   [this community archive](https://www.omarchyarchive.com/posts/siliconforested-omarchy-mac-test-kernel/).
   The [Asahi M1 matrix](https://github.com/AsahiLinux/docs/blob/main/docs/platform/feature-support/m1.md)
   still lists TouchID as TBA. No `/dev/*sep*` was observed here, which alone
   does not prove absence of all SEP support. Obtain the exact M1 Pro-supported
   source/release, firmware protocol, enrollment service and PAM instructions;
   validate enrollment, unlock and password fallback before enabling it.
   Intel T1/T2 and VM host authentication bridges are different implementations.
4. **USB4 sleep and dock video.** The current kernel can bring up dock hubs,
   input and Ethernet. ACIO blocks suspend while a USB4 link is up; a separate
   non-USB4 Type-C path can lose devices after suspend. DP tunnelling remains
   unsupported. See `ROADMAP.md` and `fairydust/usb4/README.md`.

## Combining elementary beta with Omarchy M beta

Use elementary as the desktop/package base and selectively port hardware
components. Omarchy's pacman hooks, package repositories and Hyprland settings
cannot be merged into Ubuntu/Pantheon as a single update stream.

Recommended experiment lanes:

- Baseline: record the current kernel, DTBs, m1n1, firmware, Mesa, package versions
  and working rescue boot entry before changing any component.
- Desktop: elementary beta updates plus our reproducible Pantheon settings.
- Hardware: one pinned Omarchy/Asahi kernel or firmware change per trial, with
  the original boot artifacts and recovery procedure retained.
- Compute: isolated Python environment and private Vulkan driver for MLX,
  avoiding replacement of the compositor's Mesa libraries.

For each lane record boot-to-login time, idle CPU/RAM and power at a fixed
brightness, suspend/resume success, Wi-Fi recovery, dock/monitor behavior,
video CPU utilization and thermals. Repeat comparable workloads at least three
times with the same power source and temperature conditions. Report median and
range, errors and the exact versions; no performance claim follows from this audit.

## Local AI: Ollama and MLX

[Ollama hardware documentation](https://docs.ollama.com/gpu) describes Linux
Vulkan support; its Apple Metal path is not a Linux backend. Actual Apple GPU
selection and successful model execution must be checked on this installation.
Ollama was not found on PATH during this audit.

[joshuaswarren/omarchy-mlx](https://github.com/joshuaswarren/omarchy-mlx)
is a relevant experimental Linux port: MLX APIs use a Honeykrisp Vulkan backend
rather than Metal. Its documentation requires a patched compute driver for the
advertised results. It also describes ANE work, but M1/M1 Max results must not
be assumed to cover this M1 Pro. Start with GPU inference; treat ANE as a
separate model-specific experiment.

Next implementation: inspect its current installer and Python wheel ABI,
package Ubuntu dependencies, keep the Vulkan ICD private, then benchmark a
small fixed quantized model against CPU inference. Record prompt processing,
time to first token, decode tokens/sec, peak RAM, correctness and thermals.
An MLX server and Ollama are separate runtimes; check API compatibility before
connecting OpenCode or CodexBar to either. No runtime, large model or kernel
was installed as part of this audit.

## OpenCode Desktop

Already installed: native ARM64 Debian package `opencode` 2.0.27, executable
`/opt/OpenCode/ai.opencode.desktop`. The visible desktop launcher was invoked
successfully and an application process appeared. Interactive sign-in and
inference were not tested. The separate terminal executable remains at
`~/.opencode/bin/opencode`. GitHub's legacy latest release endpoint returned
1.19.0; it was downloaded and checksum-verified in `/tmp`, but not installed
because it would downgrade the existing desktop.
