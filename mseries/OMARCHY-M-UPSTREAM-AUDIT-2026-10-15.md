# Omarchy M upstream audit — 2026-10-15

Read-only review of the Omarchy M sources tracked in
[`upstreams/omarchy-m.json`](upstreams/omarchy-m.json), plus
[iconidentify/omarchy-m1-video](https://github.com/iconidentify/omarchy-m1-video),
against [`PORT-MAP.md`](PORT-MAP.md). Nothing was installed, built, imported or
booted; no kernel, bootloader, m1n1 or audio configuration was touched. Revisions
below are discovery observations, not build pins. Licenses are the repository's
declared license (GitHub metadata plus the files named); component-level review is
still required before importing any code.

## Revisions: what actually moved

| Project | Recorded 2026-10-14 | Observed 2026-10-15 | License | Apple-chip relevance |
|---|---|---|---|---|
| omacom/omarchy-mac-pkgs | 222f7a8 | 222f7a8 (unchanged) | MIT | none new |
| subedijaidip/dp-altmode-t8112 | 50b80f4 | 50b80f4 (unchanged) | GPL-2.0 | none new |
| AsahiLinux/linux `fairydust` | ce9f2eb | **ce9f2eb (unchanged)** | NOASSERTION (kernel GPL-2.0 + per-file) | none new |
| omacom/omarchy-mac-installer | 00489dd | 38ae9ac (+3) | MIT | none: edge-pipeline JSON pin and a test |
| omacom/try-omarchy | afd4f2d | 6166ca0 (+11) | MIT | none for hardware: Japanese input migration, VM migration review, ARM64 package pins, a shell-architecture proposal |
| omacom/omarchy (`quattro`) | 84cfb93 | 8a787b6 (+8) | MIT | none for Apple: ASUS/Surface/Qualcomm/NVIDIA N1x work, locale-safe `pactl` parsing, bar-click fixes |
| joshuaswarren/omarchy-mlx | 9ab220f | 8b1d5e4 (+7) | MIT | **GPU/ANE, see below** |
| iconidentify/omarchy-m1-video | not tracked | bc0090a (2026-09-20) | GPL-2.0 (kernel patches, repo) + GPL-3.0-or-later (VA-API driver) | **video decode, see below** |

Correction to an earlier same-day observation: a first pass read the repository's
default-branch head for `AsahiLinux/linux` (94fb233, a brcmfmac commit) and made
fairydust look moved. The `fairydust` branch itself is still `ce9f2eb`.

## Video decode (largest gap): iconidentify/omarchy-m1-video

Upstream carries **15 kernel patches** for the Apple AVD driver
(`drivers/media/platform/apple/avd`) and a patched VA-API driver. We carry **one**
(`mseries/fairydust/debian/0003-avd-job-segments-use-kvmalloc.patch`), which is
an independent equivalent of upstream patch 0003 (same `kvcalloc` fix for the
~8 MiB contiguous job table; upstream's report was on a T6000, i.e. M1 Pro).

Dry-run result (no kernel tree modified): all 15 upstream patches apply cleanly,
in order, to the `drivers/media/platform/apple/avd` directory of fairydust
`ce9f2eb`. Our own 0003 and upstream 0003 touch the same lines, so adopt upstream's
series *instead of* ours, not on top of it.

| Upstream patch | What it fixes | We have it? |
|---|---|---|
| 0001 | cacheable non-coherent MMAP buffers | no |
| 0002 | H.264 rejects slices referencing invalid state | no |
| 0003 | job segment table via `kvcalloc` | **yes (ours, equivalent)** |
| 0004 | H.264 slice counter reset; videos longer than 4096 slices stop decoding | no |
| 0005 | job-state tracking: completion/run race can oops the kernel and lock `/dev/video0` | no |
| 0006 | HEVC wavefront "H0 error" firmware failures, worse with several videos | no |
| 0007, 0008, 0014 | 4:2:2 chroma plane size, 4:0:0 monochrome green, 10-bit grey | no |
| 0009, 0015 | HEVC unequal bit depth crashes decoder firmware | no |
| 0010–0013 | use-after-free window, out-of-bounds read/write, leaked 8 MiB job table, requests that never complete | no |

Userspace: `libva-v4l2_request-avd` 1.3.r11 (commit `db3014f`, GPL-3.0-or-later,
source `iconidentify/libva-v4l2_request`) fixes Chrome green video, hung multi-slice
H.264, HEVC tiles/WPP hangs, blank 10-bit HEVC, a header-parser stack overflow and
several malformed-input paths. Our notes say the "VA-API bridge … already works"; the
source we use for it is not recorded in this repo.

Upstream-reported conformance (M1 T8103, bit-exact vs reference decoders): HEVC 144/147
(145 with a patched FFmpeg), H.264 73/135 (interlaced unsupported), FRExt 27/69
with opt-in High 10, VP9 216/305. Treat these as upstream results on a different Mac;
**no equivalent run exists for the M1 Pro (T6000/J314s)**.

Cautions that must travel with any adoption:

- Upstream documents two hard resets within about a minute of boot with patches 0001–0005
  and an unknown cause (issue #13 open). With all 15 patches, boot-time loading was retested
  once. Their installer refuses to run without `--i-accept-boot-risk`. Do not adopt a
  boot-loaded module on the daily machine without the recovery path in
  `fairydust/usb4/RECOVERY.md`.
- Their installer is Arch-only (pacman, hooks, linux-asahi headers). Only the patch files and
  the driver source are reusable here; packaging is ours to write for Debian-family kernels.
- The M2/M2 Max records show the AVD driver can be absent or blacklisted per model; the M1 Pro
  device tree does contain AVD nodes (`t600x-die0.dtsi`), but upstream has not qualified T6000.

Suggested next steps (none done; each needs your go-ahead because it changes the kernel build):

1. Build a disposable test kernel from fairydust + the 15 patches (replace our 0003) and run
   `mseries/check-video-decode.sh` plus their `tools/qualify-device.py`, loading the module by
   hand with `modprobe`, never at boot.
2. Record the libva-v4l2_request-avd source commit and license in `UPSTREAM-PINS.md`.
3. Add 4:0:0 / 10-bit HEVC / multi-stream concurrent cases to our decode check.

## GPU / neural engine: joshuaswarren/omarchy-mlx

New since the pin: a Vulkan `gather_qmm` decode kernel that writes several outputs per
workgroup (reported as a decode-only gain, bit-identical, receipts included), a fix so the
default LOW queue-priority request reaches device creation, and pinning of the Parakeet
speech worker to performance cores. Your existing review
([`JOSHUA-REPOSITORY-REVIEW.md`](JOSHUA-REPOSITORY-REVIEW.md)) keeps MLX/Honeykrisp and notes
this machine has no ANE node or module, so the ANE worker pin does not apply yet. The Vulkan
changes are in the MLX overlay, not in Mesa; compare against the `mesa-mlx-compute` build we
use before assuming they are present.

## Not worth porting

- omarchy-mac-installer, try-omarchy: macOS installer/VM-preview tooling and migrations for
  Arch guests. Pin-update only.
- omarchy `quattro`: no Apple-silicon hardware changes in this window. Its locale-hardening of
  `pactl` parsing is a pattern to check in our own audio helpers
  (`mseries/audio`), not a port.

## Recommended record updates (not applied here)

- `upstreams/omarchy-m.json`: refresh `observed_revision` for installer, try-omarchy, omarchy,
  omarchy-mlx; add `iconidentify/omarchy-m1-video` and `iconidentify/libva-v4l2_request`.
- `PORT-MAP.md`: change the AVD row from "Packaging and kernel gap" to point at this audit.
