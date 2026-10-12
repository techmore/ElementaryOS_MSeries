# ElementaryOS M-Series (Apple Silicon port scaffolding)

Experimental project: build **elementary OS** (Pantheon, Ubuntu-based,
`mkosi` image builder) for **Apple Silicon Macs (M1/M2/…)**, informed by the
Apple Silicon hardware knowledge in
[omacom/omarchy-mac](https://github.com/omacom/omarchy-mac) (`quattro`
branch).

Upstream bases (pinned at first commit — see `mseries/UPSTREAM-PINS.md`):
- build system: [elementary/os](https://github.com/elementary/os) `main`
- Apple Silicon hardware scripts: [omacom/omarchy-mac](https://github.com/omacom/omarchy-mac) `quattro`

## Status: research scaffolding, NOT a bootable ISO

This first commit adds **ported, compositor-agnostic hardware support**
(kernel modules, firmware notes, modprobe, initramfs, systemd units) as an
additive `mseries/` overlay. It does **not** yet wire these into the mkosi
build, and no ISO has been built or tested. See `mseries/PORT-MAP.md` for the
per-fix analysis and `mseries/BUILD-NOTES.md` for what remains.

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

- `mseries/PORT-MAP.md` — every omarchy-mac Apple fix, mapped to
  portable / N-A with reasons.
- `mseries/UPSTREAM-PINS.md` — exact upstream commits this is based on.
- `mseries/BUILD-NOTES.md` — what is needed to get to a testable arm64 ISO.
- `mseries/packages.arm64` — Ubuntu package list for the Apple Silicon
  layer (to be wired into a mkosi image).
- `mseries/modprobe.d/` — `appledrm` notch option (Asahi only).
- `mseries/initramfs-tools/` — early-load `hid_apple`, `hid_magicmouse`
  (Ubuntu equivalent of omarchy's mkinitcpio HID-race fix).
- `mseries/systemd/system/` + `mseries/sbin/` — Wi-Fi resume recovery
  service and script (ported from omarchy, `brcmfmac` reload on wedge).

## License

Upstream `LICENSE` (GPLv3) is unchanged and covers the build system this
derives from. The `mseries/` overlay is contributed under the same license.
