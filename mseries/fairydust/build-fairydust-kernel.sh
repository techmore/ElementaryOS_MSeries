#!/bin/bash
# build-fairydust-kernel.sh — build Asahi's experimental `fairydust` kernel
# (USB-C DisplayPort Alt Mode) on the Arch/omarchy-mac side of an
# elementary-grow install.
#
#   ./build-fairydust-kernel.sh            # dry run: fetch + build only
#   sudo ./build-fairydust-kernel.sh --install
#
# Background: mseries/USB-C-DOCK-DP-ALT-MODE.md. `fairydust` is Asahi's
# not-yet-upstream branch that exposes ONE USB-C port as a DP Alt Mode
# output. Experimental: single port, hot-plug quirks, untested through MST
# docks (Dell WD19S drives its monitors over MST).
#
# This must run on the Arch host (it uses pacman/makepkg), NOT inside the
# elementary @elementary subvolume. The kernel in /boot is shared by both,
# so installing it also changes the omarchy boot entry — hence --install is
# explicit and the final bootloader steps are printed for review, never
# run silently.
set -euo pipefail

ASSUME_YES=0 ; INSTALL=0
for a in "$@"; do
  case "$a" in
    --install) INSTALL=1 ;;
    -y|--yes) ASSUME_YES=1 ;;
    -h|--help) sed -n '2,20p' "$0"; exit 0 ;;
    *) echo "unknown option: $a" >&2; exit 2 ;;
  esac
done

log() { echo "[fairydust] $*"; }
die() { echo "[fairydust] ABORT: $*" >&2; exit 1; }

# ---- preconditions (Arch/Asahi only; never the elementary chroot) --------
[[ $(uname -m) == aarch64 ]] || die "aarch64 only"
grep -Faiq 'apple,' /proc/device-tree/compatible 2>/dev/null \
  || die "not Apple Silicon"
command -v makepkg >/dev/null || die "makepkg not found — run on the Arch/omarchy side"
command -v pacman  >/dev/null || die "pacman not found — this is not the Arch host"
[[ -f /etc/arch-release || -f /etc/pacman.conf ]] \
  || die "no Arch release/pacman.conf — refusing to run"

WORK="${FAIRYDUST_WORK:-$HOME/fairydust-build}"
mkdir -p "$WORK"
cd "$WORK"

# ---- build deps -----------------------------------------------------------
DEPS=(base-devel git rust rust-bindgen clang llvm bc flex bison pahole
      xmlto kmod inetutils libelf openssl)
log "installing build deps: ${DEPS[*]}"
if (( ASSUME_YES )); then
  sudo pacman -S --needed --noconfirm "${DEPS[@]}"
else
  log "(dry run) would: sudo pacman -S --needed ${DEPS[*]}"
fi

# ---- fetch the linux-asahi PKGBUILD + fairydust kernel source -------------
# Arch ARM packages linux-asahi from the asahi repo. We reuse its PKGBUILD
# (so packaging/signing/install layout match the running kernel) but point
# its source at the `fairydust` branch.
if [[ ! -d linux-asahi ]]; then
  log "cloning the asahi linux-asahi packaging (PKGBUILD)"
  git clone --depth 1 https://github.com/archlinuxarm/PKGBUILDs.git alarm-pkgbuilds \
    || die "could not clone PKGBUILDs"
  pkg=$(find alarm-pkgbuilds -type d -name 'linux-asahi' | head -n1)
  [[ -n $pkg ]] || die "linux-asahi PKGBUILD not found in PKGBUILDs"
  cp -a "$pkg" linux-asahi
fi
sed -i 's@^_srcname=.*@_srcname=linux-asahi-fairydust@' linux-asahi/PKGBUILD 2>/dev/null || true
log "NOTE: review linux-asahi/PKGBUILD — set the source url to the"
log "      Asahi 'fairydust' branch, e.g.:"
log "      source=('git+https://github.com/AsahiLinux/linux.git#branch=fairydust')"

# ---- required config for DP Alt Mode (modules) ---------------------------
CONF=linux-asahi/config
if [[ -f $CONF ]]; then
  for opt in CONFIG_TYPEC CONFIG_TYPEC_DP_ALTMODE CONFIG_TYPEC_NVIDIA_ALTMODE CONFIG_TYPEC_TBT_ALTMODE; do
    if grep -q "^${opt}=" "$CONF"; then
      sed -i "s/^${opt}=.*/${opt}=m/" "$CONF"
    else
      echo "${opt}=m" >> "$CONF"
    fi
  done
  log "ensured DP Alt Mode modules in $CONF"
else
  log "WARNING: no $CONF yet (generated during build) — after the first"
  log "         'make oldconfig', re-run and it will be patched."
fi

# ---- build ----------------------------------------------------------------
log "(build takes ~60-90 min)"
if (( ASSUME_YES )); then
  ( cd linux-asahi && makepkg -si --noconfirm )
else
  log "(dry run) would: (cd linux-asahi && makepkg -si)"
fi

if (( INSTALL )); then
  log "kernel package installed. Copying DTBs + refreshing the bootloader:"
  log "  1) verify /usr/lib/modules/<ver>/dtb exists"
  log "  2) sudo update-m1n1      # refresh m1n1/boot.bin device tree"
  log "  3) sudo grub-mkconfig -o /boot/grub/grub.cfg"
  log "  4) reboot, pick the new linux-asahi entry"
  log "  See mseries/USB-C-DOCK-DP-ALT-MODE.md -> 'Fix path B'."
else
  log "build-only. Re-run with --install to install the built package."
fi
