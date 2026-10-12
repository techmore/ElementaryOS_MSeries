# ElementaryOS M-Series (Apple Silicon port scaffolding)

Experimental project: build **elementary OS** (Pantheon, Ubuntu-based,
`mkosi` image builder) for **Apple Silicon Macs (M1/M2/…)**, informed by the
Apple Silicon hardware knowledge in
[omacom/omarchy-mac](https://github.com/omacom/omarchy-mac) (`quattro`
branch).

Upstream bases (pinned at first commit — see `mseries/UPSTREAM-PINS.md`):
- build system: [elementary/os](https://github.com/elementary/os) `main`
- Apple Silicon hardware scripts: [omacom/omarchy-mac](https://github.com/omacom/omarchy-mac) `quattro`

## Status: booted M1 Pro desktop; factory ISO still unverified

The owner confirms elementary OS 9 boots on a 2021 14-inch M1 Pro using
the transformed system. See [desktop setup](DESKTOP-SETUP.md) for reproducible
Command shortcuts, Pantheon brightness keys, Signal ARM64, CodexBar Linux and
its native Wingpanel quota dropdown.
[Ambient keyboard lighting](keyboard-backlight/README.md) is available through
`bash mseries/install-keyboard-backlight.sh`, using the AOP sensor and UPower.

`mkosi.images/apple-silicon/` (arm64-only directory image) carries the
ported layer and is wired into the arm64 live ISO profile and the sysupdate
image via `ExtraTrees`. This factory ISO path has not been hardware-verified.
See `mseries/PORT-MAP.md` for the per-fix analysis, `mseries/KERNEL-REPORT.md`
for the kernel verdict, and `mseries/BUILD-NOTES.md` for what remains.

## Why a port, not a cherry-pick

omarchy-mac is **Arch Linux** (`pacman`, `mkinitcpio`, Hyprland); elementary
is **Ubuntu** (`apt`, `initramfs-tools`, Pantheon/Gala, `casper` live ISO).
Package names, initramfs tooling, and the desktop stack all differ, so each
fix is translated to its Ubuntu/mkosi equivalent rather than copied. Hyprland-
and pacman-specific pieces are documented as out of scope.

## Safety: this cannot break your laptop

Everything here is **build-time scaffolding**. It only takes effect when
someone explicitly builds an ISO (`just do-daily` on a build machine or the
GitHub workflow) and then boots *that ISO* on separate media. Cloning this
repo, reading it, and pushing commits do not touch your bootloader, your
macOS install, or the existing Omarchy ISO on your NAS.

## Layout

Two tracks, one shared hardware layer:

- **Image factory** (`mkosi.images/apple-silicon/` + arm64 wiring): builds
  a bootable live ISO in CI. Long-term clean path; blocked on kernel +
  firmware work (see KERNEL-REPORT.md, KERNEL-SOURCE.md).
- **Transform** (`transform/elementary-grow.sh`, design in
  `mseries/TRANSFORM-DESIGN.md`): single command run on a booted
  omarchy-mac that grows an elementary boot entry alongside the existing
  system (new subvolume, reused Asahi kernel, additive GRUB entry).
  Untested — dry-run review on the real machine comes first.

- `mseries/PORT-MAP.md` — every omarchy-mac Apple fix, mapped to
  portable / N-A with reasons.
- `mseries/UPSTREAM-PINS.md` — exact upstream commits this is based on.
- `mseries/KERNEL-REPORT.md` — Ubuntu generic kernel vs Apple Silicon
  verdict (boots unaccelerated; daily-driver needs an Asahi kernel).
- `mseries/BUILD-NOTES.md` — what is needed to get to a testable arm64 ISO.
- `mseries/USB-C-DOCK-DP-ALT-MODE.md` — why USB-C dock video/mouse
  (Dell WD19S) does not work on stock `linux-asahi`, with live evidence
  from a MacBookPro18,3 (M1 Pro) and the `fairydust` DP-Alt-Mode path.
- `mseries/fairydust/` — helper to build the experimental `fairydust`
  DP-Alt-Mode kernel on the Arch/omarchy side.
- `mseries/packages.arm64` — package rationale for the Apple Silicon layer.
  Includes Signal Desktop (`signal-desktop` apt repo + Flathub `org.signal.Signal`)
  and the DP-Alt-Mode kernel config bits.
- `mkosi.images/apple-silicon/` — the build wiring: `mkosi.conf`,
  `mkosi.extra/` (final-path config files + resume script),
  `mkosi.postinst.chroot`, `mkosi.finalize`. Arm64-only; wired into
  `mkosi.conf.d/arch.arm64.conf`, the liveiso aarch64 profile, and a new
  `mkosi.images/sysupdate/mkosi.conf.d/arch.arm64.conf`.

## License

Upstream `LICENSE` (GPLv3) is unchanged and covers the build system this
derives from. The `mseries/` overlay is contributed under the same license.
